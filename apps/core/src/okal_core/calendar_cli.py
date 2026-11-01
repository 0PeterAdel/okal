"""Explicit operator-only Google Calendar controls; never exposed to browser."""
import argparse
import json
import sys

from .calendar_google import (
    CalendarGoogleError, _service, authorize, configured_accounts,
    list_calendars, status, sync_calendar, validate_calendar_id,
)


def emit(result):
    print(json.dumps(result, ensure_ascii=True, indent=2))


def main(store, argv):
    parser = argparse.ArgumentParser(prog="okal calendar",
                                     description="Local Google Calendar operator controls")
    actions = parser.add_subparsers(dest="action", required=True)
    check = actions.add_parser("status", help="No-network auth and sync status")
    check.add_argument("--account", default="default")
    actions.add_parser("accounts", help="List configured account ALIASES only")
    auth = actions.add_parser("authorize", help="Browser-based Google desktop OAuth")
    auth.add_argument("--account", default="default")
    auth.add_argument("--client-secrets", required=True,
                      help="Local private 0600 Desktop OAuth JSON path")
    ls = actions.add_parser("calendars", help="Discover calendars in this account")
    ls.add_argument("--account", default="default")
    sync = actions.add_parser("sync", help="Run explicit provider read-only sync")
    sync.add_argument("--account", default="default")
    sync.add_argument("--calendar", default="primary",
                      help="Calendar ID, or primary (default)")
    sync.add_argument("--all", action="store_true",
                      help="Sync all readable calendars (bounded to 20)")
    args = parser.parse_args(argv)
    try:
        if args.action == "accounts":
            emit({"account_aliases": configured_accounts(store)})
        elif args.action == "status":
            emit(status(store, args.account))
        elif args.action == "authorize":
            emit(authorize(store, args.client_secrets, args.account))
        elif args.action == "calendars":
            emit({"calendars": list_calendars(_service(store, args.account)),
                  "external_writes": False})
        elif args.action == "sync":
            service = _service(store, args.account)
            calendars = list_calendars(service)
            targets = (calendars if args.all else
                       [next((c for c in calendars if c["id"] == args.calendar or
                              (args.calendar == "primary" and c["primary"])), None)])
            if args.all and len(targets) > 20:
                raise CalendarGoogleError("too_many_calendars_select_individually")
            if not targets or any(x is None for x in targets):
                raise CalendarGoogleError("calendar_not_accessible_select_id_from_calendars")
            results = []
            for item in targets:
                if item["access"] not in {"reader", "writer", "owner", "freeBusyReader"}:
                    continue
                results.append(sync_calendar(
                    store, args.account, validate_calendar_id(item["id"]),
                    service=service, calendar_timezone=item["timezone"]
                ))
            emit({"results": results, "external_writes": False})
        return 0
    except (CalendarGoogleError, OSError, ValueError) as exc:
        print(f"Calendar operation failed: {exc}", file=sys.stderr)
        return 1
