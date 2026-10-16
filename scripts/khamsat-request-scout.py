#!/usr/bin/env python3
"""One-pass, read-only Khamsat community request scout using the owner's browser."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
from urllib.parse import urlparse


LISTING = "https://khamsat.com/community/requests"
STATE = Path.home() / ".local/share/okal/khamsat"
PROFILE = Path.home() / ".local/share/okal/freelance/browser"
CONFIG = Path.home() / ".config/okal/khamsat-watch.json"
DEFAULT_CONFIG = {
    "keywords": ["python", "بايثون", "ذكاء اصطناعي", "تحليل بيانات",
                 "power bi", "لوحة بيانات", "sql", "أتمتة", "automation"],
    "exclude_terms": ["مراهنات", "casino", "سبام"],
}


def request_url(value: str) -> str:
    """Only an individual request on the expected HTTPS host is accepted."""
    parsed = urlparse(value)
    if (parsed.scheme != "https" or parsed.hostname not in {"khamsat.com", "www.khamsat.com"}
            or parsed.username or parsed.password or parsed.port is not None
            or parsed.params or parsed.fragment):
        raise ValueError("Expected an HTTPS Khamsat community request link")
    if not re.fullmatch(r"/community/requests/\d+(?:-[^/]+)?/?", parsed.path):
        raise ValueError("Expected /community/requests/<number>-<title>")
    return "https://khamsat.com" + parsed.path.rstrip("/")


def request_id(value: str) -> str:
    return re.match(r"https://khamsat.com/community/requests/(\d+)", request_url(value)).group(1)


def save(path: Path, value: dict) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.chmod(0o600)
    temp.replace(path)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def settings(path: Path) -> dict:
    if not path.is_file():
        raise ValueError(f"Create private settings with --init first: {path}")
    data = load(path)
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")
    for key in ("keywords", "exclude_terms"):
        if (not isinstance(data.get(key), list) or
                any(not isinstance(x, str) or not x.strip() for x in data[key])):
            raise ValueError(f"Expected a list of nonempty strings: {key}")
    if not data["keywords"]:
        raise ValueError("Add at least one keyword")
    return data


def matches(title: str, config: dict) -> bool:
    text = title.casefold()
    return (any(word.casefold() in text for word in config["keywords"])
            and not any(word.casefold() in text for word in config["exclude_terms"]))


def merge_queue(old: list[dict], found: list[dict]) -> list[dict]:
    """Retain unreviewed candidates; latest scan cannot erase them."""
    by_id = {str(row["id"]): row for row in old}
    by_id.update({str(row["id"]): row for row in found})
    return list(by_id.values())[-200:]


def scan(state: Path, profile: Path, config: dict, limit: int) -> None:
    if not profile.is_dir():
        raise RuntimeError(f"Saved local browser profile not found: {profile}")
    from playwright.sync_api import sync_playwright

    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock_path = profile.parent / ".browser.lock"
    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(lock_fd, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Freelance browser profile is open in another process") from exc
        with sync_playwright() as playwright:
            options = {"user_data_dir": str(profile), "headless": False,
                       "locale": "ar-EG", "no_viewport": True, "args": ["--start-maximized"]}
            if os.environ.get("OKAL_FREELANCE_CHROMIUM"):
                options["executable_path"] = os.environ["OKAL_FREELANCE_CHROMIUM"]
            context = playwright.chromium.launch_persistent_context(**options)
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(LISTING, wait_until="domcontentloaded", timeout=30000)
                if page.url.split("?", 1)[0].rstrip("/") != LISTING:
                    raise RuntimeError("Khamsat did not show the requests listing. Check sign-in in the visible browser")
                links = page.locator('a[href*="/community/requests/"]').evaluate_all(
                    "els => els.map(a => ({url: a.href, title: a.innerText.trim()}))"
                )
                candidates = {}
                for link in links:
                    try:
                        url = request_url(link["url"])
                        title = link["title"].strip()
                        if title and matches(title, config):
                            candidates.setdefault(request_id(url), {"id": request_id(url),
                                                                    "url": url, "title": title})
                    except (ValueError, KeyError, AttributeError):
                        continue
                if not links:
                    raise RuntimeError("No request links were visible; inspect the page manually. No retry loop ran")
                queue_path = state / "queue.json"
                previous = load(queue_path).get("requests", []) if queue_path.exists() else []
                seen = {str(row["id"]) for row in previous}
                found = []
                for item in list(candidates.values()):
                    if item["id"] in seen or len(found) >= limit:
                        continue
                    page.goto(item["url"], wait_until="domcontentloaded", timeout=30000)
                    if request_id(page.url) != item["id"]:
                        raise RuntimeError("Request redirected; stop and inspect the site manually")
                    item["visible_text"] = page.locator("body").inner_text(timeout=15000)[:8000]
                    item["found_at"] = datetime.now(timezone.utc).isoformat()
                    found.append(item)
                save(queue_path, {"listing": LISTING, "checked_at": datetime.now(timezone.utc).isoformat(),
                                  "requests": merge_queue(previous, found)})
                print(f"Checked {len(links)} links; {len(found)} new candidates. Queue: {queue_path}")
                for item in found:
                    print(f'{item["title"]}: {item["url"]}')
                print("Read-only scan. No comment or offer was sent.")
            finally:
                context.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--init", action="store_true", help="Create private keyword settings if absent")
    action.add_argument("--scan", action="store_true", help="Inspect the listing once with saved browser")
    parser.add_argument("--limit", type=int, default=10, help="Maximum new requests to inspect (1-20)")
    args = parser.parse_args()
    if args.init:
        if CONFIG.exists():
            print(f"Kept existing settings: {CONFIG}")
        else:
            save(CONFIG, DEFAULT_CONFIG)
            print(f"Created private settings: {CONFIG}")
        return 0
    if not 1 <= args.limit <= 20:
        parser.error("--limit must be between 1 and 20")
    try:
        scan(STATE, PROFILE, settings(CONFIG), args.limit)
    except (ValueError, RuntimeError, ImportError) as exc:
        parser.exit(1, f"Khamsat scout: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
