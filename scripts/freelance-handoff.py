#!/usr/bin/env python3
"""Structured, local Khamsat handoff for the main and freelance agents.

Only scans and draft preparation are exposed. Publication remains in the
owner's separate control page with per-reply confirmation.
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import sys


def sibling(filename: str, name: str):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


scout = sibling("khamsat-request-scout.py", "freelance_scout")
control = sibling("khamsat-control.py", "freelance_control")


def status() -> dict:
    queue = control.private_json(scout.STATE / "queue.json", {"requests": []})
    receipts = control.private_json(control.reply.RECEIPTS, {"requests": {}}).get("requests", {})
    drafts = control.private_json(control.DRAFTS, {"requests": {}}).get("requests", {})
    if not isinstance(queue.get("requests"), list) or not isinstance(receipts, dict) or not isinstance(drafts, dict):
        raise ValueError("Invalid private Khamsat state")
    items = []
    for row in queue["requests"]:
        if not isinstance(row, dict):
            raise ValueError("Invalid queued request")
        rid = str(row.get("id", ""))
        url = scout.request_url(row.get("url", ""))
        if scout.request_id(url) != rid:
            raise ValueError("Queued request ID does not match its URL")
        receipt = receipts.get(rid, {})
        if not isinstance(receipt, dict):
            raise ValueError("Invalid reply receipt")
        title = row.get("title", "")
        if not isinstance(title, str):
            raise ValueError("Invalid queued request title")
        items.append({"id": rid, "url": url, "title": title[:500],
                      "status": receipt.get("status", "draft" if rid in drafts else "candidate"),
                      "has_draft": rid in drafts})
    return {"schema_version": "okal.freelance.handoff.v1", "source": "khamsat",
            "control_url": "http://127.0.0.1:8788/", "checked_at": queue.get("checked_at"),
            "last_scan": queue.get("last_scan"), "requests": items,
            "pending_ids": sorted(rid for rid, row in receipts.items()
                                  if isinstance(row, dict) and row.get("status") == "pending")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("status", help="Read locally saved requests and receipts")
    sub.add_parser("scan", help="Scan Khamsat read-only with the saved browser")
    draft = sub.add_parser("draft", help="Prepare a local proposal draft")
    draft.add_argument("request_id", help="Numeric request ID from the queue")
    args = parser.parse_args()
    try:
        if args.action == "scan":
            config = scout.settings(scout.CONFIG)
            output = io.StringIO()
            with redirect_stdout(output):
                scout.scan(scout.STATE, scout.PROFILE, config, config["candidate_limit"])
            print(output.getvalue(), file=sys.stderr, end="")
        elif args.action == "draft":
            if not args.request_id.isascii() or not args.request_id.isdecimal():
                raise ValueError("Expected a numeric request ID")
            warning = control.preview(args.request_id)
            report = status()
            if not any(row["id"] == args.request_id and row["has_draft"] for row in report["requests"]):
                raise RuntimeError("Draft was not saved")
            report["draft_id"] = args.request_id
            report["draft_warning"] = warning
            report["draft_text"] = control.private_json(control.DRAFTS, {"requests": {}})["requests"][args.request_id]["text"]
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0
        print(json.dumps(status(), ensure_ascii=False, indent=2))
        return 0
    except (ValueError, RuntimeError, OSError, KeyError, TypeError) as exc:
        print(f"Freelance handoff: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
