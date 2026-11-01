"""Short-lived single-use confirmation tickets for localhost Gmail Trash.

A browser can read the local dashboard without a password, but it can only
move mail after requesting a Gmail-native preview and confirming its exact
selection in the UI. This nonce is never persisted, never authorizes a
different selection, and cannot be replayed after a request is attempted.

Boundary assumes an owner-only loopback desktop; not a substitute for OS
account isolation. Google OAuth gmail.modify remains mandatory.
"""
import hmac
import secrets
import threading


class PendingTrashConfirmations:
    MAX_PENDING = 48
    TTL_SECONDS = 120

    def __init__(self, clock):
        self.clock = clock
        self._pending = {}
        self._guard = threading.Lock()

    def issue(self, ids, digest):
        now = int(self.clock())
        token = secrets.token_urlsafe(32)
        with self._guard:
            self._pending = {
                key: value for key, value in self._pending.items()
                if value[2] > now
            }
            if len(self._pending) >= self.MAX_PENDING:
                # Conservative: expire the oldest pending preview first.
                oldest = min(self._pending, key=lambda k: self._pending[k][2])
                self._pending.pop(oldest, None)
            self._pending[token] = (tuple(ids), digest, now + self.TTL_SECONDS)
        return token

    def consume(self, ids, digest, token):
        if not isinstance(token, str) or len(token) > 90:
            return False
        with self._guard:
            record = self._pending.pop(token, None)
        if record is None:
            return False
        original_ids, original_digest, expires_at = record
        return (
            int(self.clock()) < expires_at
            and tuple(ids) == original_ids
            and isinstance(digest, str)
            and hmac.compare_digest(digest, original_digest)
        )
