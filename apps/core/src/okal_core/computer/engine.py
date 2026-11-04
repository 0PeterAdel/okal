"""Durable bounded action lifecycle. No model output can widen a permission."""

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import threading
import time
import uuid

from ..intelligence import Intelligence, SECRET, identifier, text
from ..mail.inference import LocalModel
from ..mail.private import config
from ..store import Conflict, private_file
from .contracts import Policy, Plan, Result, Denied, Cancelled, digest
from .files import Files
from .registry import registry


class Context:
    def __init__(self, engine, run_id, step_id, tool, preview, policy):
        self.engine = engine
        self.store = engine.store
        self.run_id = run_id
        self.step_id = step_id
        self.tool = tool
        self.preview = preview
        self.policy = policy
        self.policy_revision = engine.policy()["revision"]
        self.expected_policy_digest = None
        self.files = Files(policy.roots, self.store.directory)
        self.deadline = time.monotonic() + tool.timeout

    def check(self):
        if time.monotonic() > self.deadline:
            raise TimeoutError("tool_timeout")
        current = self.engine.policy()
        if (
            self.expected_policy_digest
            and digest(current) != self.expected_policy_digest
        ):
            raise Denied("permission_revision_changed")
        if current["revision"] != self.policy_revision or digest(
            current["policy"]
        ) != digest(self.policy.model_dump()):
            raise Denied("permission_changed")
        if self.run_id:
            with self.store.connect() as db:
                row = db.execute(
                    "SELECT cancel,expires_at FROM computer_runs WHERE id=?",
                    (self.run_id,),
                ).fetchone()
                if not row or row[0]:
                    raise Cancelled("owner_cancelled")
                if row[1] < int(self.store.clock()):
                    raise Denied("execution_authorization_expired")

    def checkpoint(self, result):
        if self.run_id:
            self.engine.event(
                self.run_id, self.step_id, "verified_partial", result.model_dump()
            )


class Engine:
    def __init__(self, store):
        self.store = store
        self.tools = registry()
        self.workers = set()
        self.guard = threading.Lock()
        with store.connect() as db, db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "CREATE TABLE IF NOT EXISTS computer_schema(version INTEGER NOT NULL)"
            )
            row = db.execute("SELECT version FROM computer_schema").fetchone()
            if row and row[0] != 1:
                raise ValueError("unsupported_computer_schema")
            if not row:
                db.execute("INSERT INTO computer_schema VALUES(1)")
            db.execute("""CREATE TABLE IF NOT EXISTS computer_policy(
                id INTEGER PRIMARY KEY CHECK(id=1),revision INTEGER NOT NULL,payload TEXT NOT NULL)""")
            db.execute(
                "INSERT OR IGNORE INTO computer_policy VALUES(1,1,?)",
                (json.dumps(Policy().model_dump()),),
            )
            db.execute("""CREATE TABLE IF NOT EXISTS computer_runs(
                id TEXT PRIMARY KEY,conversation_id TEXT NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
                request_id TEXT NOT NULL UNIQUE,request_digest TEXT NOT NULL,
                instruction TEXT NOT NULL,plan TEXT NOT NULL,preview TEXT NOT NULL,
                policy_digest TEXT NOT NULL,approval_digest TEXT NOT NULL,
                status TEXT NOT NULL,cancel INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,expires_at INTEGER NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS computer_steps(
                id TEXT PRIMARY KEY,run_id TEXT NOT NULL REFERENCES computer_runs(id) ON DELETE CASCADE,
                position INTEGER NOT NULL,status TEXT NOT NULL,result TEXT,error TEXT,
                UNIQUE(run_id,position))""")
            db.execute("""CREATE TABLE IF NOT EXISTS computer_events(
                seq INTEGER PRIMARY KEY AUTOINCREMENT,run_id TEXT NOT NULL REFERENCES computer_runs(id) ON DELETE CASCADE,
                step_id TEXT,kind TEXT NOT NULL,created_at INTEGER NOT NULL,payload TEXT NOT NULL)""")

        # A free process lock proves no live executor owns these started
        # steps. A restart preserves ambiguity instead of replaying writes.
        try:
            with self.lock(), store.connect() as db, db:
                db.execute(
                    "UPDATE computer_runs SET status='needs_reconciliation' WHERE status='running'"
                )
                db.execute(
                    "UPDATE computer_steps SET status='needs_reconciliation',error='executor_interrupted' WHERE status='running'"
                )
        except Conflict:
            pass

    def event(self, run_id, step_id, kind, payload):
        encoded = json.dumps(payload, ensure_ascii=False)
        if len(encoded.encode()) > 100000:
            raise ValueError("receipt_size_limit")
        if SECRET.search(encoded):
            raise Denied("credential_like_receipt_rejected")
        with self.store.connect() as db, db:
            db.execute(
                "INSERT INTO computer_events(run_id,step_id,kind,created_at,payload) VALUES(?,?,?,?,?)",
                (run_id, step_id, kind, int(self.store.clock()), encoded),
            )

    def policy(self):
        with self.store.connect() as db:
            row = db.execute(
                "SELECT revision,payload FROM computer_policy WHERE id=1"
            ).fetchone()
            return {"revision": row[0], "policy": json.loads(row[1])}

    def configure(self, payload, revision):
        if type(revision) is not int:
            raise ValueError("invalid_policy_revision")
        policy = Policy.model_validate(payload)
        if len(set(policy.tools)) != len(policy.tools) or any(
            name not in self.tools for name in policy.tools
        ):
            raise ValueError("unknown_or_duplicate_tool")
        for grant in policy.roots:
            if grant.root != os.path.normpath(grant.root) or grant.root in {
                "/",
                "/home",
                "/tmp",
                "/usr",
                "/etc",
                "/var",
                "/run",
            }:
                raise Denied("specific_owner_directory_required")
            files = Files([grant], self.store.directory)
            with files.directory(grant.root):
                pass
        from .browser import network

        network(policy.browser_origins)
        for account in policy.accounts:
            text(account, 200)
        for name, profile in policy.commands.items():
            if not re.fullmatch("[a-zA-Z0-9_-]{1,60}", name):
                raise ValueError("invalid_profile_name")
            if not profile.argv[0].startswith("/usr/bin/") or Path(
                profile.argv[0]
            ).name in {"sudo", "su", "pkexec", "doas"}:
                raise Denied("unprivileged_system_executable_required")
            for arg in profile.argv:
                text(arg, 2000)
        if any(
            not re.fullmatch("[a-zA-Z0-9][a-zA-Z0-9_.-]{0,99}", a)
            for a in policy.applications
        ):
            raise ValueError("invalid_desktop_application")
        with self.store.connect() as db, db:
            changed = db.execute(
                "UPDATE computer_policy SET revision=revision+1,payload=? WHERE id=1 AND revision=?",
                (json.dumps(policy.model_dump()), revision),
            ).rowcount
            if changed != 1:
                raise Conflict("policy_revision_changed")
        return self.policy()

    def capabilities(self):
        import importlib.util, shutil

        return {
            "schema_version": 1,
            "tools": [t.manifest() for t in self.tools.values()],
            "policy": self.policy(),
            "readiness": {
                "browser": bool(
                    importlib.util.find_spec("playwright") and shutil.which("chromium")
                ),
                "pdf": bool(shutil.which("pdftotext")),
                "command_sandbox": bool(shutil.which("bwrap")),
                "desktop": bool(os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")),
            },
            "external_account_writes": "Use existing provider review/confirmation UI; no new send authority.",
        }

    def _authorize(self, tool, policy):
        if tool.name not in policy.tools:
            raise Denied("tool_not_granted")
        if tool.risk != "read" and policy.mode == "read_only":
            raise Denied("read_only_mode")

    def propose(self, conversation_id, request_id, instruction, plan=None, infer=None):
        identifier(conversation_id)
        identifier(request_id)
        instruction = text(instruction, 900)
        Intelligence(self.store).get(conversation_id)
        if isinstance(plan, Plan):
            plan = plan.model_copy(deep=True)
        request_digest = digest(
            {
                "conversation_id": conversation_id,
                "instruction": instruction,
                "plan": plan.model_dump() if isinstance(plan, Plan) else plan,
            }
        )
        with self.store.connect() as db:
            old = db.execute(
                "SELECT id,request_digest FROM computer_runs WHERE request_id=?",
                (request_id,),
            ).fetchone()
        if old:
            if old["request_digest"] != request_digest:
                raise Conflict("action_request_changed")
            return self.get(old["id"])
        policy_record = self.policy()
        policy = Policy.model_validate(policy_record["policy"])
        if plan is None:
            manifests = [self.tools[n].manifest() for n in policy.tools]
            # Small-model planning sees only owner-selected tools, scopes and
            # preceding owner context; it never sees credentials or web text.
            with self.store.connect() as db:
                owner_history = [
                    r[0][:300]
                    for r in db.execute(
                        "SELECT user_text FROM chat_turns WHERE conversation_id=? AND status='complete' ORDER BY seq DESC LIMIT 3",
                        (conversation_id,),
                    )
                ]
                previous = db.execute(
                    "SELECT s.result FROM computer_steps s JOIN computer_runs r ON r.id=s.run_id "
                    "WHERE r.conversation_id=? AND s.status='verified' AND r.policy_digest=? ORDER BY r.created_at DESC,s.position DESC LIMIT 2",
                    (conversation_id, digest(policy_record)),
                ).fetchall()
            previous_evidence = []
            for saved in previous:
                evidence = json.loads(saved[0]).get("evidence", {})
                selected = {
                    k: v
                    for k, v in evidence.items()
                    if k in {"path", "task_id", "id", "messages", "files", "url"}
                }
                previous_evidence.append(
                    json.dumps(selected, ensure_ascii=False)[:1000]
                )
            context = {
                "RECENT_OWNER_QUOTES": owner_history,
                "PREVIOUS_VERIFIED_TOOL_EVIDENCE_UNTRUSTED_DATA": previous_evidence,
                "OWNER_REQUEST": instruction,
                "SCOPES": [g.model_dump() for g in policy.roots],
                "BROWSER_ORIGINS": policy.browser_origins,
                "COMMAND_PROFILES": list(policy.commands),
                "MAIL_ACCOUNTS": policy.accounts,
                "TOOLS": [
                    {
                        "name": m["name"],
                        "description": m["description"],
                        "input_schema": m["input_schema"],
                    }
                    for m in manifests
                ],
            }
            if not manifests:
                raise Denied("configure_action_permissions_first")
            if len(json.dumps(context).encode()) > 25000:
                raise ValueError("narrow_enabled_tools_for_local_model")
            if infer is not None:
                plan = Plan.model_validate(infer(context))
            else:
                model = LocalModel(config(self.store))
                try:
                    plan = model.generate(
                        Plan,
                        "Propose a bounded plan for the OWNER_REQUEST using ONLY granted TOOLS and SCOPES. "
                        "Use exact absolute paths from the request/scopes, never invent personal resources. "
                        "You cannot authorize execution or modify permissions. Do not put shell commands in arguments. "
                        "Each step needs tool and arguments exactly matching its schema. At most 10 steps. "
                        "For organize folders use files.organize. For comparing reports use documents.report. "
                        "For web research use browser.read then files.write only if the owner requested a report; "
                        "never invent research results in file contents. Prefer source-grounded tools.",
                        context,
                    )
                finally:
                    model.close()
        plan = Plan.model_validate(
            plan.model_dump() if isinstance(plan, Plan) else plan
        )
        if SECRET.search(json.dumps(plan.model_dump(), ensure_ascii=False)):
            raise Denied("sensitive_plan_rejected")
        previews = []
        produced = {}
        for step in plan.steps:
            tool = self.tools.get(step.tool)
            if not tool:
                raise Denied("unknown_tool")
            self._authorize(tool, policy)
            args = tool.schema.model_validate(step.arguments)
            step.arguments = args.model_dump()
            ctx = Context(self, None, uuid.uuid4().hex, tool, {}, policy)
            ctx.expected_policy_digest = digest(policy_record)
            ctx.check()
            preview = tool.preview(ctx, args)
            for resource in preview.get("resources", []):
                path = resource["path"]
                if path in produced:
                    resource.clear()
                    resource.update(
                        path=path, kind="from_verified_step", position=produced[path]
                    )
            previews.append(preview)
            if tool.name in {"files.write", "files.mkdir"}:
                produced[args.path] = len(previews) - 1
            if tool.name in {"files.copy", "files.move"}:
                produced[args.destination] = len(previews) - 1
            if hasattr(args, "output"):
                produced[args.output] = len(previews) - 1
            if getattr(args, "download_to", None):
                produced[args.download_to] = len(previews) - 1
        run_id = uuid.uuid4().hex
        snapshot = {
            "plan": plan.model_dump(),
            "previews": previews,
            "policy": policy_record,
        }
        if len(json.dumps(snapshot, ensure_ascii=False).encode()) > 90000:
            raise ValueError("narrow_action_preview_size")
        approval = digest(snapshot)
        now = int(self.store.clock())
        approval_required = any(
            self.tools[s.tool].risk == "consequential"
            or self.tools[s.tool].risk == "local_write"
            and policy.mode == "assisted"
            for s in plan.steps
        )
        with self.store.connect() as db, db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute(
                "SELECT id,request_digest FROM computer_runs WHERE request_id=?",
                (request_id,),
            ).fetchone()
            if old:
                if old["request_digest"] != request_digest:
                    raise Conflict("action_request_changed")
                run_id = old["id"]
            else:
                if (
                    db.execute("SELECT COUNT(*) FROM computer_runs").fetchone()[0]
                    >= 1000
                ):
                    raise ValueError("action_history_limit")
                db.execute(
                    "INSERT INTO computer_runs(id,conversation_id,request_id,request_digest,instruction,plan,preview,"
                    "policy_digest,approval_digest,status,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        run_id,
                        conversation_id,
                        request_id,
                        request_digest,
                        instruction,
                        json.dumps(plan.model_dump()),
                        json.dumps(previews),
                        digest(policy_record),
                        approval,
                        "awaiting_approval" if approval_required else "ready",
                        now,
                        now + 600,
                    ),
                )
                for position, step in enumerate(plan.steps):
                    db.execute(
                        "INSERT INTO computer_steps VALUES(?,?,?,'pending',NULL,NULL)",
                        (uuid.uuid4().hex, run_id, position),
                    )
        self.event(
            run_id, None, "planned", {"approval_digest": approval, "preview": previews}
        )
        return self.get(run_id)

    def get(self, run_id):
        identifier(run_id)
        with self.store.connect() as db:
            row = db.execute(
                "SELECT * FROM computer_runs WHERE id=?", (run_id,)
            ).fetchone()
            if not row:
                raise ValueError("action_not_found")
            value = dict(row)
            for name in ("plan", "preview"):
                value[name] = json.loads(value[name])
            value["steps"] = [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM computer_steps WHERE run_id=? ORDER BY position",
                    (run_id,),
                )
            ]
            for step in value["steps"]:
                step["result"] = json.loads(step["result"]) if step["result"] else None
            value["events"] = [
                dict(r)
                for r in db.execute(
                    "SELECT seq,step_id,kind,created_at,payload FROM computer_events "
                    "WHERE run_id=? ORDER BY seq DESC LIMIT 100",
                    (run_id,),
                )
            ]
        value.pop("request_digest")
        value.pop("policy_digest")
        return value

    def history(self, conversation_id):
        identifier(conversation_id)
        with self.store.connect() as db:
            return {
                "items": [
                    dict(r)
                    for r in db.execute(
                        "SELECT id,instruction,status,created_at FROM computer_runs "
                        "WHERE conversation_id=? ORDER BY created_at DESC,id DESC LIMIT 50",
                        (conversation_id,),
                    )
                ]
            }

    def cancel(self, run_id):
        identifier(run_id)
        with self.store.connect() as db, db:
            db.execute(
                "UPDATE computer_runs SET cancel=1,status=CASE WHEN status IN ('ready','awaiting_approval') "
                "THEN 'cancelled' ELSE status END WHERE id=?",
                (run_id,),
            )
        self.event(run_id, None, "cancel_requested", {})
        return self.get(run_id)

    @contextmanager
    def lock(self):
        path = self.store.directory / "computer-execution.lock"
        private_file(path)
        fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise Conflict("another_action_is_running") from None
            yield
        finally:
            os.close(fd)

    def execute(self, run_id, approval_digest=None):
        identifier(run_id)
        with self.lock():
            with self.store.connect() as db, db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute(
                    "SELECT * FROM computer_runs WHERE id=?", (run_id,)
                ).fetchone()
                if not row:
                    raise ValueError("action_not_found")
                if row["status"] in {
                    "succeeded",
                    "cancelled",
                    "failed",
                    "needs_reconciliation",
                    "recovered",
                }:
                    return self.get(run_id)
                running = db.execute(
                    "SELECT id FROM computer_steps WHERE run_id=? AND status='running'",
                    (run_id,),
                ).fetchone()
                if running:
                    db.execute(
                        "UPDATE computer_runs SET status='needs_reconciliation' WHERE id=?",
                        (run_id,),
                    )
                    return self.get(run_id)
                policy = Policy.model_validate(self.policy()["policy"])
                if row["policy_digest"] != digest(self.policy()):
                    raise Denied("plan_permissions_changed_replan")
                if row["expires_at"] < int(self.store.clock()):
                    raise Denied("plan_expired_replan")
                if (
                    row["status"] == "awaiting_approval"
                    and approval_digest != row["approval_digest"]
                ):
                    raise Denied("exact_preview_approval_required")
                if row["cancel"]:
                    return self.get(run_id)
                db.execute(
                    "UPDATE computer_runs SET status='running' WHERE id=?", (run_id,)
                )
            self.event(
                run_id,
                None,
                "execution_authorized",
                {"approval_digest": row["approval_digest"]},
            )
            plan = Plan.model_validate_json(row["plan"])
            previews = json.loads(row["preview"])
            for position, step in enumerate(plan.steps):
                with self.store.connect() as db, db:
                    record = db.execute(
                        "SELECT * FROM computer_steps WHERE run_id=? AND position=?",
                        (run_id, position),
                    ).fetchone()
                    if record["status"] == "verified":
                        continue
                    db.execute(
                        "UPDATE computer_steps SET status='running' WHERE id=?",
                        (record["id"],),
                    )
                tool = self.tools[step.tool]
                ctx = Context(
                    self, run_id, record["id"], tool, previews[position], policy
                )
                ctx.expected_policy_digest = row["policy_digest"]
                try:
                    ctx.check()
                    self._authorize(tool, policy)
                    for resource in ctx.preview.get("resources", []):
                        expected = resource
                        if resource["kind"] == "from_verified_step":
                            with self.store.connect() as db:
                                previous = db.execute(
                                    "SELECT result FROM computer_steps WHERE run_id=? AND position=? AND status='verified'",
                                    (run_id, resource["position"]),
                                ).fetchone()
                            changes = (
                                json.loads(previous["result"])["changes"]
                                if previous
                                else []
                            )
                            expected = next(
                                (
                                    c
                                    for c in changes
                                    if c.get("path") == resource["path"]
                                ),
                                None,
                            )
                            if expected is None:
                                raise ValueError("prior_step_postcondition_missing")
                        ctx.files.check(expected)
                    args = tool.schema.model_validate(step.arguments)
                    self.event(
                        run_id,
                        record["id"],
                        "attempted",
                        {"tool": tool.name, "arguments": step.arguments},
                    )
                    output = Result.model_validate(tool.handler(ctx, args).model_dump())
                    if not output.verified:
                        raise ValueError("unverified_tool_result")
                    encoded = json.dumps(output.model_dump(), ensure_ascii=False)
                    if SECRET.search(encoded) or len(encoded.encode()) > 100000:
                        raise Denied("sensitive_or_oversized_result")
                    self.event(run_id, record["id"], "verified", output.model_dump())
                    with self.store.connect() as db, db:
                        db.execute(
                            "UPDATE computer_steps SET status='verified',result=? WHERE id=?",
                            (encoded, record["id"]),
                        )
                except Exception as exc:
                    # Writes may have partially happened. Never retry them on
                    # restart or label their failure as no change.
                    state = (
                        "cancelled"
                        if isinstance(exc, Cancelled) and tool.risk == "read"
                        else "failed"
                        if tool.risk == "read"
                        else "needs_reconciliation"
                    )
                    code = (
                        str(exc)
                        if isinstance(exc, (ValueError, TimeoutError))
                        else type(exc).__name__
                    )
                    if SECRET.search(code):
                        code = "redacted_error"
                    self.event(
                        run_id,
                        record["id"],
                        "stopped",
                        {"state": state, "code": code[:200]},
                    )
                    with self.store.connect() as db, db:
                        db.execute(
                            "UPDATE computer_steps SET status=?,error=? WHERE id=?",
                            (state, code[:200], record["id"]),
                        )
                        db.execute(
                            "UPDATE computer_runs SET status=? WHERE id=?",
                            (state, run_id),
                        )
                    return self.get(run_id)
            with self.store.connect() as db, db:
                db.execute(
                    "UPDATE computer_runs SET status='succeeded' WHERE id=?", (run_id,)
                )
            return self.get(run_id)

    def resume(self, run_id, approval_digest):
        value = self.get(run_id)
        if value["approval_digest"] != approval_digest:
            raise Denied("exact_resume_approval_required")
        if value["status"] not in {"failed", "cancelled"}:
            raise Denied("ambiguous_writes_require_reconciliation")
        if any(s["status"] == "needs_reconciliation" for s in value["steps"]):
            raise Denied("ambiguous_writes_require_reconciliation")
        with self.lock(), self.store.connect() as db, db:
            db.execute(
                "UPDATE computer_steps SET status='pending',error=NULL WHERE run_id=? AND status IN ('failed','cancelled')",
                (run_id,),
            )
            db.execute(
                "UPDATE computer_runs SET status='awaiting_approval',cancel=0,expires_at=? WHERE id=?",
                (int(self.store.clock()) + 600, run_id),
            )
        self.event(
            run_id, None, "resume_requested", {"approval_digest": approval_digest}
        )
        return self.start(run_id, approval_digest)

    def start(self, run_id, approval_digest=None):
        identifier(run_id)
        # Actual authorization happens again inside execute, immediately before
        # dispatch. A duplicate start cannot create a second executor.
        with self.guard:
            if run_id not in self.workers:
                self.workers.add(run_id)

                def work():
                    try:
                        self.execute(run_id, approval_digest)
                    except Exception as exc:
                        try:
                            self.event(
                                run_id,
                                None,
                                "dispatch_denied",
                                {"code": type(exc).__name__},
                            )
                        except Exception:
                            pass
                    finally:
                        with self.guard:
                            self.workers.discard(run_id)

                threading.Thread(target=work, daemon=True, name="okal-action").start()
        return self.get(run_id)

    def recover(self, run_id, approval_digest):
        """Explicit recovery only; never an automatic retry of a partial write."""
        with self.lock():
            value = self.get(run_id)
            if value["status"] == "recovered":
                return value
            if approval_digest != value["approval_digest"]:
                raise Denied("exact_recovery_approval_required")
            if value["status"] not in {
                "succeeded",
                "needs_reconciliation",
                "cancelled",
                "failed",
            }:
                raise Denied("stop_execution_before_recovery")
            policy = Policy.model_validate(self.policy()["policy"])
            if policy.mode == "read_only":
                raise Denied("read_only_mode")
            if any(step["tool"] not in policy.tools for step in value["plan"]["steps"]):
                raise Denied("recovery_tool_permission_revoked")
            operations = []
            seen = set()
            # Both completed and verified partial results contain usable
            # inverses. Deduplicate checkpoints repeated by a final receipt.
            with self.store.connect() as db:
                all_events = [
                    dict(r)
                    for r in db.execute(
                        "SELECT kind,payload FROM computer_events WHERE run_id=? ORDER BY seq",
                        (run_id,),
                    )
                ]
            recovered = {
                digest(json.loads(e["payload"]))
                for e in all_events
                if e["kind"] == "recovery_verified"
            }
            for event in all_events:
                if event["kind"] not in {"verified", "verified_partial"}:
                    continue
                payload = json.loads(event["payload"])
                for operation in payload.get("recovery", []):
                    key = digest(operation)
                    if key not in seen and key not in recovered:
                        seen.add(key)
                        operations.append(operation)
            if not operations:
                raise ValueError("no_supported_automatic_recovery_inspect_receipts")
            self.event(run_id, None, "recovery_started", {"operations": operations})
            files = Files(policy.roots, self.store.directory)
            try:
                for operation in reversed(operations):
                    action = operation["action"]
                    if action == "move_back":
                        source = files.snapshot(
                            operation["source"],
                            True,
                            internal=operation.get("internal", False),
                        )
                        destination = files.snapshot(operation["destination"], True)
                        if (
                            source.get("sha256") != operation["sha256"]
                            or destination["kind"] != "missing"
                        ):
                            raise Conflict("recovery_resource_changed")
                        files.move(
                            operation["source"],
                            operation["destination"],
                            internal=operation.get("internal", False),
                        )
                        if (
                            files.snapshot(operation["destination"])["sha256"]
                            != operation["sha256"]
                        ):
                            raise Conflict("recovery_verification_failed")
                    elif action == "trash_created":
                        snapshot = files.snapshot(operation["path"], True)
                        if snapshot.get("sha256") != operation["sha256"]:
                            raise Conflict("recovery_resource_changed")
                        from .registry import trash, PathInput

                        ctx = Context(
                            self,
                            run_id,
                            uuid.uuid4().hex,
                            self.tools["files.trash"],
                            {},
                            policy,
                        )
                        output = trash(ctx, PathInput(path=operation["path"]))
                        self.event(
                            run_id,
                            None,
                            "recovery_preserved_created_file",
                            output.model_dump(),
                        )
                    elif action == "remove_empty_directory":
                        snapshot = files.snapshot(operation["path"], True)
                        if snapshot.get("inode") != operation["inode"]:
                            raise Conflict("recovery_directory_changed")
                        with files.parent(operation["path"], True) as (fd, name):
                            os.rmdir(name, dir_fd=fd)
                            os.fsync(fd)
                    self.event(run_id, None, "recovery_verified", operation)
            except Exception:
                with self.store.connect() as db, db:
                    db.execute(
                        "UPDATE computer_runs SET status='needs_reconciliation' WHERE id=?",
                        (run_id,),
                    )
                raise
            with self.store.connect() as db, db:
                db.execute(
                    "UPDATE computer_runs SET status='recovered' WHERE id=?", (run_id,)
                )
            return self.get(run_id)
