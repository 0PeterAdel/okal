"""Local operator commands. HTTP read tokens never grant these capabilities."""

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

from .contracts import Config, Draft, MailError
from .private import config, locked, read_private, root, write_private
from .state import MailState


def emit(value):
    # Escapes terminal controls and bidi overrides in untrusted mail/model output.
    print(json.dumps(value, ensure_ascii=True, indent=2))


def instant(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise MailError("timestamp_needs_timezone")
    return int(parsed.timestamp())


def main(store, argv):
    p = argparse.ArgumentParser(
        prog="okal mail",
        description="Local Gmail operator; no automatic account writes",
    )
    commands = p.add_subparsers(dest="command", required=True)
    c = commands.add_parser("configure")
    c.add_argument("--file", type=Path, required=True)
    c = commands.add_parser("authorize")
    c.add_argument("--client", type=Path, required=True)
    c.add_argument("--enable-send", action="store_true")
    commands.add_parser("status")
    commands.add_parser("doctor")
    c = commands.add_parser("digest")
    c.add_argument("--start")
    c.add_argument("--end")
    c = commands.add_parser("sources")
    c.add_argument("job_id")
    c = commands.add_parser("search")
    c.add_argument("query")
    c.add_argument("--limit", type=int, default=20)
    c = commands.add_parser("read")
    c.add_argument("message_id")
    c = commands.add_parser("followup")
    c.add_argument("message_id")
    c = commands.add_parser("draft")
    c.add_argument(
        "--file",
        type=Path,
        required=True,
        help="private JSON: recipient, subject, body",
    )
    c = commands.add_parser("reply")
    c.add_argument("message_id")
    c.add_argument("--instruction", required=True)
    commands.add_parser("drafts")
    for name in ("preview", "send", "reconcile"):
        c = commands.add_parser(name)
        c.add_argument("draft_id")
    c = commands.add_parser("schedule")
    c.add_argument("at", help="HH:MM in configured timezone, or off")
    commands.add_parser("pause-sending")
    c = commands.add_parser("prune")
    c.add_argument("--confirm-delete-old-digests", action="store_true", required=True)
    args = p.parse_args(argv)
    model = None
    api = None
    try:
        with locked(store):
            if args.command == "configure":
                cfg = Config.model_validate(read_private(args.file))
                if cfg.send_enabled or cfg.daily_at:
                    raise MailError("configure_with_sending_and_schedule_off")
                path = root(store) / "config.json"
                if path.exists():
                    old = config(store)
                    if old.account.casefold() != cfg.account.casefold():
                        raise MailError(
                            "account_change_requires_separate_state_directory"
                        )
                    if old.send_enabled:
                        raise MailError(
                            "pause_and_reauthorize_readonly_before_reconfigure"
                        )
                write_private(path, cfg.model_dump())
                emit({"configured": True, "sending": False, "schedule": False})
                return 0
            state = MailState(store)
            if args.command == "status":
                emit(
                    {
                        "configured": (root(store) / "config.json").exists(),
                        "jobs": state.jobs(),
                        "drafts": state.drafts(),
                        "schedule": state.schedule_status(),
                    }
                )
                return 0
            cfg = config(store)
            if args.command == "authorize":
                from .provider import authorize

                authorize(store, cfg, args.client, args.enable_send)
                emit({"authorized": True, "send_enabled": args.enable_send})
            elif args.command in {"schedule", "pause-sending"}:
                if args.command == "schedule":
                    cfg = Config.model_validate(
                        {
                            **cfg.model_dump(),
                            "daily_at": None if args.at == "off" else args.at,
                        }
                    )
                else:
                    cfg.send_enabled = False
                write_private(root(store) / "config.json", cfg.model_dump())
                emit(
                    {
                        "daily_at": cfg.daily_at,
                        "send_enabled": cfg.send_enabled,
                        "note": "pause-sending is local; reauthorize read-only to remove the Google send scope",
                    }
                )
            elif args.command == "sources":
                emit(state.sources(args.job_id))
            elif args.command == "draft":
                emit(
                    {
                        "draft_id": state.new_draft(
                            cfg.account, Draft.model_validate(read_private(args.file))
                        )
                    }
                )
            elif args.command == "drafts":
                emit(state.drafts())
            elif args.command == "preview":
                emit(state.preview(args.draft_id))
            elif args.command == "prune":
                emit(state.prune(int(store.clock()) - cfg.retention_days * 86400))
            else:
                from .provider import Gmail
                from .inference import LocalModel
                from . import workflows

                api = Gmail.open(store, cfg, sending=args.command == "send")
                if args.command in {"digest", "doctor", "reply"}:
                    model = LocalModel(cfg)
                if args.command == "doctor":
                    model.verify()
                    emit(
                        {
                            "account_matches": True,
                            "local_model_matches": True,
                            "send_enabled": cfg.send_enabled,
                            "daily_at": cfg.daily_at,
                            "live_digest_quality_tested": False,
                        }
                    )
                elif args.command == "digest":
                    end = instant(args.end) if args.end else int(store.clock())
                    start = (
                        instant(args.start)
                        if args.start
                        else state.progress(cfg.account)
                    )
                    start = start if start is not None else end - 86400
                    emit(workflows.digest(store, cfg, api, model, start, end))
                elif args.command == "search":
                    emit(workflows.search(api, args.query, args.limit))
                elif args.command == "read":
                    emit(api.get(args.message_id).model_dump())
                elif args.command == "followup":
                    emit(workflows.followup(api, args.message_id))
                elif args.command == "reply":
                    emit(
                        {
                            "draft_id": workflows.reply_draft(
                                store,
                                cfg,
                                api,
                                model,
                                args.message_id,
                                args.instruction,
                            )
                        }
                    )
                elif args.command == "send":
                    if not sys.stdin.isatty() or not sys.stdout.isatty():
                        raise MailError("interactive_terminal_required_for_send")
                    preview = state.preview(args.draft_id)
                    emit(preview)
                    expected = "SEND " + preview["approval_digest"]
                    answer = input(
                        "After reviewing the exact content, type SEND followed by the full approval_digest: "
                    )
                    if answer != expected:
                        raise MailError("send_cancelled")
                    emit(
                        workflows.send_reviewed(
                            store, cfg, api, args.draft_id, preview["approval_digest"]
                        )
                    )
                elif args.command == "reconcile":
                    emit(workflows.reconcile(store, cfg, api, args.draft_id))
        return 0
    except MailError as exc:
        print("Mail: " + str(exc), file=sys.stderr)
    except Exception:
        print(
            "Mail: setup_or_operation_failed; check private config, dependencies and authorization",
            file=sys.stderr,
        )
    finally:
        if model:
            model.close()
        if api:
            api.close()
    return 1
