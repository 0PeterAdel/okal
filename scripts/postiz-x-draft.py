#!/usr/bin/env python3
"""Check a source-backed X post and optionally save it as a Postiz draft.

This adapter never asks Postiz to schedule or publish a post.
"""

import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent.parent
CHECKER = Path(__file__).with_name("check-social-draft.py")


def check_draft(path: Path) -> dict:
    spec = importlib.util.spec_from_file_location("okal_social_checker", CHECKER)
    if spec is None or spec.loader is None:
        raise ValueError("Social evidence checker is missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    errors = module.check(path, ROOT)
    if errors:
        raise ValueError("; ".join(errors))
    data = json.loads(path.read_text(encoding="utf-8"))
    if data["platform"] != "x":
        raise ValueError("Only X drafts are supported")
    if len(data["text"]) > 280:
        raise ValueError("Draft exceeds the conservative 280-character X limit")
    return data


def payload(text: str, integration_id: str) -> dict:
    if not integration_id.strip():
        raise ValueError("Postiz X integration ID is required")
    return {
        "type": "draft",
        "date": datetime.now(timezone.utc).isoformat(),
        "shortLink": False,
        "tags": [],
        "posts": [{
            "integration": {"id": integration_id},
            "value": [{"content": text, "image": []}],
            "settings": {
                "__type": "x",
                "who_can_reply_post": "everyone",
                "made_with_ai": True,
                "paid_partnership": False,
            },
        }],
    }


def endpoint(base: str) -> str:
    parts = urlparse(base)
    if (parts.scheme != "https" and
            not (parts.scheme == "http" and parts.hostname in ("localhost", "127.0.0.1"))):
        raise ValueError("Postiz API URL must use HTTPS or local loopback HTTP")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("Postiz API URL may not contain credentials, query, or fragment")
    return base.rstrip("/") + "/posts"


def create_draft(url: str, key: str, data: dict) -> list:
    if not key:
        raise ValueError("Set OKAL_POSTIZ_API_KEY locally; never put it in a draft")
    request = Request(url, data=json.dumps(data).encode("utf-8"), method="POST", headers={
        "Authorization": key,
        "Content-Type": "application/json",
    })
    with urlopen(request, timeout=25) as response:
        receipt = json.load(response)
    if not isinstance(receipt, list) or not receipt or not receipt[0].get("postId"):
        raise ValueError("Postiz response had no postId; inspect Postiz before retrying")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("draft", type=Path, help="JSON file accepted by check-social-draft.py")
    parser.add_argument("--create-draft", action="store_true", help="Write an unpublished draft to Postiz")
    args = parser.parse_args()
    try:
        draft = check_draft(args.draft)
        integration = os.environ.get("OKAL_POSTIZ_X_INTEGRATION_ID", "")
        # A dry run still works without an account or token.
        data = payload(draft["text"], integration or "UNCONFIGURED_X_INTEGRATION")
        if not args.create_draft:
            print(json.dumps(data, ensure_ascii=False, indent=2))
            print("Dry run only. Review every factual claim before sending this draft to Postiz.")
            return 0
        if not integration:
            raise ValueError("Set OKAL_POSTIZ_X_INTEGRATION_ID from the connected X channel")
        url = endpoint(os.environ.get("OKAL_POSTIZ_API_URL", "https://api.postiz.com/public/v1"))
        receipt = create_draft(url, os.environ.get("OKAL_POSTIZ_API_KEY", ""), data)
        print(json.dumps({"status": "draft", "postId": receipt[0]["postId"]}))
        print("Review the exact draft in Postiz. It was not scheduled or published.")
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"Postiz draft error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
