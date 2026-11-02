"""Explicit operator-only Google Calendar controls; never exposed to browser."""
import argparse
import json
import sys

from .calendar_google import (
    CalendarGoogleError, _service, authorize, configured_accounts,
    list_calendars, status, sync_calendar, validate_calendar_id,
    record_sync_failure,
)

# Strict allowlist: provider HTTP bodies and OAuth diagnostics never reach CLI
# JSON output or logs. Failed calendar indices are local listing positions.
SAFE_SYNC_ERRORS = frozenset({
    "google_calendar_provider_request_failed",
    "google_calendar_reauthorization_required",
    "google_calendar_missing_sync_token",
    "google_calendar_event_budget_exceeded",
    "google_calendar_event_page_budget_exceeded",
    "google_calendar_sync_token_expired",
    "calendar_sync_already_running",
    "google_calendar_event_nonpositive_interval",
    "google_calendar_event_overlong_interval",
    "invalid_calendar_event_interval",
    "google_calendar_sync_failed",
})


def safe_sync_error(exc):
    code = str(exc)
    return code if code in SAFE_SYNC_ERRORS else "google_calendar_sync_failed"


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
    audit = actions.add_parser(
        "audit", help="Read-only live coverage audit, sanitized ordinals"
    )
    audit.add_argument("--account", default="default")
    audit.add_argument("--days", type=int, choices=range(1, 15), default=7)
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
        elif args.action == "audit":
            from .calendar_audit import audit_google_calendar
            emit(audit_google_calendar(store, args.account, days=args.days))
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
            results, failures, skipped = [], [], 0
            for number, item in enumerate(targets, start=1):
                if item["access"] not in {"reader", "writer", "owner", "freeBusyReader"}:
                    skipped += 1
                    continue
                try:
                    results.append(sync_calendar(
                        store, args.account, validate_calendar_id(item["id"]),
                        service=service, calendar_timezone=item["timezone"]
                    ))
                except Exception as exc:
                    # Do NOT advance the failed calendar's cursor or omit an
                    # invalid event. Let independent calendars continue.
                    code = safe_sync_error(exc)
                    try:
                        record_sync_failure(store, args.account, item["id"], code)
                    except (OSError, ValueError):
                        # Never replace the primary per-calendar error or leak
                        # provider response details via a status-write error.
                        pass
                    if not args.all:
                        print(f"Calendar operation failed: {code}", file=sys.stderr)
                        return 1
                    failures.append({"calendar_number": number, "error_code": code})
            emit({
                "results": results,
                "successful_calendars": len(results),
                "failed_calendars": len(failures),
                "failures": failures,
                "unreadable_calendars": skipped,
                "sync_status": (
                    "partial" if failures or skipped else "complete"
                ),
                "external_writes": False,
                "note": "A failed calendar retains its prior sync checkpoint.",
            })
            # Exit non-zero for PARTIAL coverage even though JSON remains
            # parseable and successful calendar results are preserved.
            return 2 if failures or skipped else 0
        return 0
    except (CalendarGoogleError, OSError, ValueError) as exc:
        if args.action == "sync":
            # Never let invalid user input turn error reporting into traceback.
            try:
                record_sync_failure(store, args.account, args.calendar, exc)
            except (CalendarGoogleError, OSError, ValueError):
                pass
        code = safe_sync_error(exc) if args.action == "sync" else str(exc)
        print(f"Calendar operation failed: {code}", file=sys.stderr)
        return 1
    except Exception:
        # Provider library errors can include HTTP response text; don't echo it.
        print("Calendar operation failed: google_calendar_provider_error", file=sys.stderr)
        return 1
