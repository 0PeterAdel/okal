"""Owner-only UI Trash approval PIN — independent from passwordless dashboard reads.

The PIN never enters a URL, file in plaintext, browser storage or logs. Strong
KDF with random salt; five failed attempts lock out approval for 15 minutes.
This gate is for accidental action/other local web content, not malware with
the owner's OS privileges. Browser API MUST check exact same-origin and
only recoverably move owner-selected messages to Gmail Trash.
"""
import hashlib
import hmac
import json
import os
from pathlib import Path

from .contracts import MailError
from .private import root, read_private, write_private

ITERATIONS = 350_000
MIN_LENGTH = 12
MAX_LENGTH = 128
LOCKOUT_SECONDS = 900


def _path(store):
    return root(store) / "ui-trash-pin.json"


def configure_pin(store, pin):
    if (not isinstance(pin, str) or not MIN_LENGTH <= len(pin) <= MAX_LENGTH
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in pin)):
        raise MailError("ui_trash_pin_requires_12_to_128_characters")
    salt = os.urandom(24)
    digest = hashlib.pbkdf2_hmac(
        "sha256", pin.encode("utf-8"), salt, ITERATIONS
    )
    write_private(_path(store), {
        "version": 1, "salt": salt.hex(), "digest": digest.hex(),
        "attempts": 0, "blocked_until": 0,
    })
    return {"configured": True, "scope": "recoverable_trash_only",
            "note": "The UI delete PIN is not the browser read key."}


def pin_configured(store):
    return _path(store).exists()


def verify_pin(store, candidate):
    if not isinstance(candidate, str) or len(candidate) > MAX_LENGTH:
        raise MailError("ui_trash_pin_invalid")
    path = _path(store)
    try:
        data = read_private(path)
        if data.get("version") != 1:
            raise ValueError()
        salt = bytes.fromhex(data["salt"])
        expected = bytes.fromhex(data["digest"])
        attempts = int(data["attempts"])
        blocked = int(data["blocked_until"])
        if len(salt) != 24 or len(expected) != 32 or attempts < 0:
            raise ValueError()
    except (ValueError, KeyError, TypeError, OSError):
        raise MailError("ui_trash_pin_not_configured") from None

    now = int(store.clock())
    if blocked > now:
        raise MailError("ui_trash_pin_temporarily_locked")
    got = hashlib.pbkdf2_hmac("sha256", candidate.encode(), salt, ITERATIONS)
    if not hmac.compare_digest(got, expected):
        attempts += 1
        data["attempts"] = attempts
        if attempts >= 5:
            data["blocked_until"] = now + LOCKOUT_SECONDS
            data["attempts"] = 0
        write_private(path, data)
        raise MailError("ui_trash_pin_invalid")
    data["attempts"] = 0
    data["blocked_until"] = 0
    write_private(path, data)
    return True
