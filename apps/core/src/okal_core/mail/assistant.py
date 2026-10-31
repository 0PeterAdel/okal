"""Offline-first Inbox Actions: deterministic previews over saved Gmail evidence.

Inspired by Gmail triage helpers, Inbox Zero's rule approach and Workspace
email-to-task, without importing third-party agents or increasing OAuth scopes.

Never invokes Gmail, Ollama, sends/replies/archives, or writes external tasks.
The model's saved suggestions are untrusted proposals, not tool instructions.
"""
import re
from email.utils import parseaddr
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .contracts import Insight, MailError, Strict
from .history import recent_evidence, recent_quarantines
from .private import read_private, root
from .workflows import source_link


Bucket = Literal["task_review", "reply_review", "read_later", "manual_review"]
Priority = Literal["high", "normal", "low"]
Category = Literal["action", "information", "low_priority"]


class Rule(Strict):
    name: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,39}$")
    sender_domain: str | None = Field(default=None, max_length=180)
    subject_contains: str | None = Field(default=None, min_length=2, max_length=80)
    category: Category | None = None
    label: Literal["INBOX", "UNREAD", "STARRED"] | None = None
    bucket: Bucket
    priority: Priority

    @field_validator("sender_domain")
    @classmethod
    def validate_domain(cls, v):
        if v is not None and not re.fullmatch(
            r"(?:[a-z0-9-]{1,63}\.)+[a-z]{2,63}", v
        ):
            raise ValueError("invalid_sender_domain")
        return v

    @model_validator(mode="after")
    def ensure_selector(self):
        if not any((self.sender_domain, self.subject_contains, self.category, self.label)):
            raise ValueError("rule_requires_selector")
        return self


class Rules(Strict):
    version: Literal[1] = 1
    rules: list[Rule] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def distinct_names(self):
        names = [r.name for r in self.rules]
        if len(names) != len(set(names)):
            raise ValueError("duplicate_rule_name")
        return self


DEFAULT_RULES = Rules(rules=[
    Rule(name="action-task", category="action",
         bucket="task_review", priority="high"),
    Rule(name="low-priority", category="low_priority",
         bucket="read_later", priority="low"),
    Rule(name="information", category="information",
         bucket="read_later", priority="normal"),
])


def rules_for(store):
    path = root(store) / "assistant-rules.json"
    if not path.exists() and not path.is_symlink():
        return DEFAULT_RULES, "builtin"
    try:
        return Rules.model_validate(read_private(path)), "private_config"
    except (OSError, ValueError, TypeError):
        raise MailError("assistant_rules_invalid_or_unsafe") from None


def choose_rule(meta, insight, rules):
    # From headers are not authenticated identity. A matching rule only
    # influences LOCAL REVIEW priority, never authorizes an external write.
    sender = parseaddr(meta["sender"])[1].casefold()
    domain = sender.rsplit("@", 1)[-1] if "@" in sender else ""
    subject = meta["subject"].casefold()
    labels = set(meta["labels"])
    for rule in rules.rules:
        if rule.sender_domain and domain != rule.sender_domain:
            continue
        if rule.subject_contains and rule.subject_contains.casefold() not in subject:
            continue
        if rule.category and insight.category != rule.category:
            continue
        if rule.label and rule.label not in labels:
            continue
        return rule
    # Empty/partial owner policies must never create hidden auto rules.
    return None


def proposals(store, account, limit=60, include_items=True):
    if type(limit) is not int or not 1 <= limit <= 60:
        raise MailError("assistant_invalid_limit")
    rules, rules_source = rules_for(store)
    with store.connect() as db:
        available = {
            row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    if not {"mail_sync_insights", "mail_sync_quarantine"} <= available:
        return {
            "state": "awaiting_saved_gmail_insights", "items": [],
            "counts": {"task_review": 0, "reply_review": 0,
                       "read_later": 0, "manual_review": 0},
            "total_in_sample": 0, "rules_source": rules_source,
            "external_writes": False, "tasks_created": 0,
            "calendar_events_created": 0,
            "coverage": "latest_saved_messages_only",
        }

    output = []
    seen = set()
    for row in recent_evidence(store, account, limit):
        meta = row["metadata"]
        try:
            insight = Insight.model_validate(row["insight"])
            mid = meta["id"]
            if (not isinstance(mid, str)
                    or not re.fullmatch(r"[a-fA-F0-9]{1,64}", mid)
                    or insight.source_id != mid
                    or not isinstance(meta["subject"], str)
                    or not isinstance(meta["sender"], str)
                    or not isinstance(meta["labels"], list)
                    or not all(isinstance(label, str) for label in meta["labels"])):
                raise ValueError("invalid_provenance")
        except (KeyError, TypeError, ValueError):
            raise MailError("assistant_saved_evidence_invalid") from None
        if mid in seen:
            continue
        seen.add(mid)
        matched = choose_rule(meta, insight, rules)
        if matched is None:
            # Rules override built-ins only when explicitly set in the private
            # file; unrecognized messages stay read-later rather than disappear.
            bucket = "read_later"
            priority = "normal"
            rule_name = None
        else:
            bucket, priority, rule_name = (
                matched.bucket, matched.priority, matched.name
            )
        if bucket == "manual_review":
            task_title = "Review original email / راجع الرسالة الأصلية"
        else:
            task_title = insight.suggested_action.strip() or (
                "Review email / راجع البريد"
            )
        link = source_link(account, mid)
        output.append({
            "source_id": mid, "source_link": link,
            "subject": meta["subject"], "sender": meta["sender"],
            "received_ms": meta.get("received_ms"),
            "summary": insight.summary, "category": insight.category,
            "suggested_action": insight.suggested_action,
            "bucket": bucket, "priority": priority, "rule": rule_name,
            "attachments_unreviewed": bool(meta.get("attachment_count", 0)),
            "proposed_task": {
                "title": task_title,
                "due_date": None,  # Unverified dates are NOT promoted.
                "source_link": link,
                "target": "local_review_only",
                "status": "suggested_not_created",
            } if bucket in ("task_review", "manual_review") else None,
            "reply_draft_status": "not_created_requires_owner_instruction"
                if bucket == "reply_review" else None,
            "needs_owner_approval": True,
        })
    for row in recent_quarantines(store, account, limit):
        mid = row["message_id"]
        if mid in seen or not re.fullmatch(r"[a-fA-F0-9]{1,64}", mid):
            continue
        seen.add(mid)
        link = source_link(account, mid)
        output.append({
            "source_id": mid, "source_link": link,
            "subject": "Original message requires manual review",
            "sender": "Gmail", "received_ms": row["detected_at"] * 1000,
            "summary": "Unreadable or incomplete email / تعذّر تحليل الرسالة",
            "category": "manual_review", "suggested_action": "",
            "bucket": "manual_review", "priority": "high",
            "rule": None, "attachments_unreviewed": True,
            "proposed_task": {
                "title": "Review source email / مراجعة البريد الأصلي",
                "due_date": None, "source_link": link,
                "target": "local_review_only",
                "status": "suggested_not_created",
            },
            "reply_draft_status": None, "needs_owner_approval": True,
        })
    counts = {key: sum(item["bucket"] == key for item in output)
              for key in ("task_review", "reply_review",
                          "read_later", "manual_review")}
    # Group manual review and high-priority work first, while keeping order
    # stable within each bucket. This is a preview, not urgency verification.
    order = {"manual_review": 0, "reply_review": 1,
             "task_review": 2, "read_later": 3}
    output.sort(key=lambda x: (order[x["bucket"]],
                               {"high": 0, "normal": 1, "low": 2}[x["priority"]]))
    return {
        "state": "local_suggestion_preview",
        "items": output if include_items else [],
        "counts": counts, "total_in_sample": len(output),
        "rules_source": rules_source,
        "rule_count": len(rules.rules),
        "external_writes": False, "tasks_created": 0,
        "calendar_events_created": 0,
        "reply_drafts_created": 0,
        "coverage": "latest_saved_messages_only",
        "note": "Stored AI summaries and sender headers are untrusted. Verify with Gmail; deadlines and replies need explicit owner review.",
    }
