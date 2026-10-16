#!/usr/bin/env python3
"""Publish one locally generated, fact-grounded X post per Cairo day."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


CONFIG = Path.home() / ".config/okal/x-publisher.json"
KEYS = Path.home() / ".config/okal/x-user-keys.json"
STATE = Path.home() / ".local/share/okal/x-publisher/state.json"
POST_URL = "https://api.x.com/2/tweets"
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"


def private_json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError(f"Missing private file or permissions are too broad: {path} (chmod 600)")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    path.parent.chmod(0o700)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp.replace(path)


@contextmanager
def exclusive_state():
    STATE.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    lock = STATE.with_suffix(".lock")
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


def escape(value: str) -> str:
    return quote(str(value), safe="~-._")


def oauth_header(keys: dict, method: str, url: str, *, nonce: str, timestamp: int) -> str:
    names = ("consumer_key", "consumer_secret", "access_token", "access_token_secret")
    if any(not isinstance(keys.get(name), str) or not keys[name] for name in names):
        raise ValueError("X user credentials are incomplete")
    values = {"oauth_consumer_key": keys["consumer_key"], "oauth_nonce": nonce,
              "oauth_signature_method": "HMAC-SHA1", "oauth_timestamp": str(timestamp),
              "oauth_token": keys["access_token"], "oauth_version": "1.0"}
    normalized = "&".join(f"{escape(k)}={escape(v)}" for k, v in sorted(values.items()))
    base = "&".join(escape(x) for x in (method, url, normalized))
    key = f'{escape(keys["consumer_secret"])}&{escape(keys["access_token_secret"])}'
    digest = hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()
    import base64
    values["oauth_signature"] = base64.b64encode(digest).decode()
    return "OAuth " + ", ".join(f'{escape(k)}="{escape(v)}"' for k, v in sorted(values.items()))


def choose_fact(settings: dict, day: str) -> dict:
    facts = settings.get("facts")
    if not isinstance(facts, list) or not facts:
        raise ValueError("Add at least one owner-verified fact to x-publisher.json")
    for row in facts:
        if not isinstance(row, dict) or not isinstance(row.get("text"), str) or not row["text"].strip():
            raise ValueError("Each fact needs nonempty text")
    return facts[datetime.fromisoformat(day).toordinal() % len(facts)]


def generate(settings: dict, fact: dict) -> str:
    anchor = fact["text"].strip()
    if len(anchor) > 230:
        raise ValueError("A fact must be at most 230 characters")
    prompt = ("اكتب منشور X واحدًا طبيعيًا ومفيدًا بصوت Peter عن Python/AI/البرمجة. "
              "لا تخترع إنجازات أو أرقام أو اقتباسات أو روابط. "
              "لا تضع مقدمات أو تفكير أو markdown. يجب أن تظهر الجملة المثبتة التالية حرفيًا في النص: "
              + anchor + "\nالمعلومة المثبتة فقط: " + anchor)
    request = json.dumps({"model": settings.get("ollama_model", "okal-qwen3.5-4b-64k"),
                          "prompt": prompt, "stream": False,
                          "options": {"num_predict": 180, "temperature": 0.3}}, ensure_ascii=False).encode()
    with urlopen(Request(OLLAMA_URL, request, {"Content-Type": "application/json"}), timeout=180) as response:
        text = json.load(response).get("response", "").strip()
    if not text or anchor not in text or "<think>" in text or len(text) > 280 or "http" in text:
        raise ValueError("Local model output failed the fact and length checks; nothing was published")
    return text


def publish(text: str, keys: dict) -> str:
    header = oauth_header(keys, "POST", POST_URL, nonce=secrets.token_hex(16), timestamp=int(time.time()))
    body = json.dumps({"text": text}, ensure_ascii=False).encode()
    req = Request(POST_URL, body, {"Authorization": header, "Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=30) as response:
            payload = json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f"X refused the post: HTTP {exc.code}; no automatic retry") from exc
    except URLError as exc:
        raise RuntimeError("X post status is uncertain after a network error; check X before retrying") from exc
    post_id = payload.get("data", {}).get("id")
    if not isinstance(post_id, str) or not post_id.isdigit():
        raise RuntimeError("X response has no post ID; check X before retrying")
    return post_id


def run(*, dry_run: bool = False) -> str:
    day = datetime.now(ZoneInfo("Africa/Cairo")).date().isoformat()
    with exclusive_state():
        settings = private_json(CONFIG)
        if settings.get("enabled") is not True:
            raise ValueError("Set enabled to true in private settings to publish")
        state = private_json(STATE) if STATE.exists() else {}
        if state.get("day") == day:
            raise ValueError("Today's post has already been attempted; check the receipt before retrying")
        fact = choose_fact(settings, day)
        text = generate(settings, fact)
        if dry_run:
            return text
        keys = private_json(KEYS)
        # A crash or timeout after sending must never silently create a second post.
        atomic_json(STATE, {"day": day, "status": "pending", "text": text})
        post_id = publish(text, keys)
        atomic_json(STATE, {"day": day, "status": "published", "post_id": post_id,
                            "url": f"https://x.com/i/web/status/{post_id}", "text": text})
        return f"Published https://x.com/i/web/status/{post_id}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Generate and validate without publishing")
    parser.add_argument("--status", action="store_true", help="Show local receipt without authentication")
    args = parser.parse_args()
    try:
        if args.status:
            print(json.dumps(private_json(STATE) if STATE.exists() else {}, ensure_ascii=False, indent=2))
        else:
            print(run(dry_run=args.dry_run))
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        parser.exit(1, f"Okal X publisher: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
