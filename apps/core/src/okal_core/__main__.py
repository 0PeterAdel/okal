"""Local operator CLI; account/provider credentials are never accepted here."""

import argparse
import json
import os
from pathlib import Path
import sys

from .models import SummaryInput
from .store import Store


def main():
    parser = argparse.ArgumentParser(description="Okal local read-only core")
    default = (
        Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state")))
        / "okal-core"
    )
    parser.add_argument("--state-dir", type=Path, default=default)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    morning = commands.add_parser(
        "morning", help="Offline voice-ready daily briefing from saved evidence"
    )
    morning.add_argument("--notify", action="store_true",
                         help="Optional once-daily local desktop notification")
    mail = commands.add_parser(
        "mail", help="optional Gmail backend; explicit local onboarding"
    )
    mail.add_argument("mail_args", nargs=argparse.REMAINDER)
    tasks = commands.add_parser(
        "tasks", help="Owner-approved local tasks; never writes to Gmail or Calendar"
    )
    task_commands = tasks.add_subparsers(dest="task_command", required=True)
    t = task_commands.add_parser("list")
    t.add_argument("--status", choices=("open", "done", "dismissed", "all"),
                   default="open")
    t.add_argument("--limit", type=int, default=100)
    t = task_commands.add_parser("add")
    t.add_argument("--title", required=True)
    t.add_argument("--notes", default="")
    t.add_argument("--due", help="Explicit ISO-8601 timestamp WITH timezone")
    t = task_commands.add_parser("from-mail")
    t.add_argument("message_id")
    t.add_argument("--title")
    t.add_argument("--due", help="Owner-verified ISO-8601 timestamp WITH timezone")
    t.add_argument("--approve", action="store_true",
                   help="Explicitly create local task; never sends email")
    for verb in ("done", "dismiss"):
        t = task_commands.add_parser(verb)
        t.add_argument("task_id")
    commands.add_parser("demo", help="insert labeled fixtures, never connect to Gmail")
    issue = commands.add_parser(
        "device-add", help="print a read token once; keep it private"
    )
    issue.add_argument("name")
    issue.add_argument("--days", type=int, default=30)
    commands.add_parser("devices")
    revoke = commands.add_parser("device-revoke")
    revoke.add_argument("id")
    backup = commands.add_parser("backup")
    backup.add_argument("destination", type=Path)
    serve = commands.add_parser("serve")
    serve.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    os.umask(0o077)
    if args.command == "serve" and not 1024 <= args.port <= 65535:
        parser.error("port must be between 1024 and 65535")
    try:
        store = Store(args.state_dir)
        if args.command == "morning":
            from .morning import morning_brief, notify_login_once

            result = notify_login_once(store) if args.notify else morning_brief(store)
            print(json.dumps(result, ensure_ascii=True, indent=2))
            return 0
        if args.command == "mail":
            from .mail.cli import main as mail_main

            return mail_main(store, args.mail_args)
        if args.command == "tasks":
            from .tasks import TaskBoard
            board = TaskBoard(store)
            if args.task_command == "list":
                result = board.list(args.status, args.limit)
            elif args.task_command == "add":
                result = board.add(args.title, args.notes, args.due)
            elif args.task_command == "from-mail":
                from .mail.private import config
                cfg = config(store)
                result = board.from_mail(
                    cfg.account, args.message_id, args.title,
                    args.due, approve=args.approve,
                )
            else:
                result = board.transition(
                    args.task_id,
                    "done" if args.task_command == "done" else "dismissed",
                )
            print(json.dumps(result, ensure_ascii=True, indent=2))
            return 0
        if args.command == "device-add":
            print(
                json.dumps(store.issue_device(args.name, args.days), ensure_ascii=False)
            )
        elif args.command == "devices":
            print(json.dumps(store.list_devices(), ensure_ascii=False))
        elif args.command == "device-revoke":
            if not store.revoke_device(args.id):
                parser.error("device not found")
            print("Device revoked")
        elif args.command == "backup":
            store.backup(args.destination)
            print(
                "Private SQLite backup created; it includes token verifiers and summaries"
            )
        elif args.command == "demo":
            for workflow, title, body in (
                (
                    "mail",
                    "ملخص البريد التجريبي",
                    "بيانات عرض فقط — لم يتم ربط Gmail أو قراءة أي بريد.",
                ),
                (
                    "planning",
                    "خطة اليوم التجريبية",
                    "مساحة واحدة لملخصاتك. التقويم والمهام غير متصلين بعد.",
                ),
            ):
                store.record_success(
                    SummaryInput(
                        workflow=workflow,
                        account_ref="fixture",
                        occurrence="demo-v1",
                        title=title,
                        body=body,
                        data_kind="fixture",
                    )
                )
            print("Demo fixtures ready (no live account data)")
        elif args.command == "serve":
            import uvicorn
            from .api import create_app
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def lifecycle(app):
                worker = None
                if (store.directory / "mail" / "config.json").exists():
                    from .mail.scheduler import Worker

                    worker = Worker(store)
                    worker.start()
                try:
                    yield
                finally:
                    if worker:
                        worker.stop()

            uvicorn.run(
                create_app(store, args.port, lifespan=lifecycle),
                host="127.0.0.1",
                port=args.port,
                workers=1,
                access_log=False,
                proxy_headers=False,
                server_header=False,
            )
        else:
            print("Private core state ready")
    except (ValueError, OSError) as exc:
        print(f"Core setup failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
