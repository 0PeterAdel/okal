"""Explicit operator Google Tasks controls; never a write API."""
import argparse
import json
import sys

from .google_tasks import GoogleTasksError, cached, status, sync


def main(store, argv):
    parser = argparse.ArgumentParser(prog="okal tasks-google")
    cmds = parser.add_subparsers(dest="action", required=True)
    cmds.add_parser("status")
    cmds.add_parser("sync")
    ls = cmds.add_parser("list")
    ls.add_argument("--limit", type=int, default=50)
    args = parser.parse_args(argv)
    try:
        if args.action == "status":
            result = status(store)
        elif args.action == "sync":
            result = sync(store)
        else:
            result = cached(store, limit=args.limit)
    except (ValueError, OSError):
        # A provider exception or a local identity must never leak into stderr.
        print("Google Tasks operation failed; see local status and OAuth setup.",
              file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0
