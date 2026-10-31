"""Synthetic restart/catch-up coverage; no real Gmail, Ollama or network."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from okal_core.api import create_app
from okal_core.store import Store
from okal_core.mail.contracts import Config, Insight, Message, MailError
from okal_core.mail.history import HistoryState, run, local_status
from okal_core.mail.private import root, write_private, read_private
from okal_core.mail.provider import Gmail, READ, GoogleTransport
from okal_core.mail.scheduler import Worker


def incoming(mid, ts):
    return Message(
        id=mid, thread_id="ff", received_ms=ts * 1000,
        sender="Tester <test@example.com>", recipient="owner@example.com",
        reply_to="", cc="", bcc="", subject="Scheduled work",
        body="Please review the plan", rfc_id="<test@example.com>",
        labels=["INBOX", "UNREAD"],
    )


class Provider:
    def __init__(self, now):
        self.items = {"aa": incoming("aa", now - 100)}
        self.cursor = "100"
        self.delta = (self.cursor, [], 0)
        self.expired = False
        self.collections = 0

    def check_account(self, address):
        assert address == "owner@example.com"

    def history_marker(self):
        return self.cursor

    def collect(self, start, end, limit):
        self.collections += 1
        result = [m for m in self.items.values()
                  if start * 1000 <= m.received_ms < end * 1000]
        if len(result) > limit:
            raise MailError("message_budget_exceeded_narrow_interval")
        return result

    def history_changes(self, old, limit):
        if self.expired:
            raise MailError("history_cursor_expired")
        return self.delta

    def get_optional(self, mid):
        return self.items.get(mid)


class Model:
    def __init__(self):
        self.calls = []
        self.fail = False

    def summarize(self, m):
        self.calls.append(m.id)
        if self.fail:
            raise MailError("invalid_model_output")
        return Insight(source_id=m.id, category="action",
                       summary="Review schedule / راجع الموعد",
                       suggested_action="Read the original email")


class HistoryTests(unittest.TestCase):
    def setUp(self):
        guard = patch("socket.socket.connect",
                      side_effect=AssertionError("network forbidden"))
        guard.start()
        self.addCleanup(guard.stop)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.now = 1_800_000_000
        self.store = Store(Path(tmp.name) / "state", clock=lambda: self.now)
        self.cfg = Config(account="owner@example.com", model="local:test",
                          model_digest="a" * 64, sync_enabled=True)
        self.api = Provider(self.now)
        self.model = Model()

    def test_bootstrap_then_history_delta_no_duplicate_messages(self):
        first = run(self.store, self.cfg, self.api, self.model)
        self.assertEqual(first["status"], "initial_24h_backfill")
        self.assertEqual(first["processed"], 1)
        self.assertEqual(HistoryState(self.store).current(self.cfg.account)["cursor"], "100")
        self.assertEqual(self.model.calls, ["aa"])
        self.now += 3600
        self.api.items["bb"] = incoming("bb", self.now - 200)
        self.api.delta = ("110", ["aa", "bb"], 0)
        second = run(self.store, self.cfg, self.api, self.model)
        self.assertEqual(second["processed"], 1)
        self.assertEqual(self.model.calls, ["aa", "bb"])
        self.assertEqual(HistoryState(self.store).current(self.cfg.account)["cursor"], "110")
        self.assertEqual(len(self.store.list_summaries()["items"]), 2)
        third = run(self.store, self.cfg, self.api, self.model)
        self.assertEqual(third["processed"], 0)
        self.assertEqual(len(self.store.list_summaries()["items"]), 2)
        reopen = Store(self.store.directory, clock=lambda: self.now)
        self.assertEqual(HistoryState(reopen).current(self.cfg.account)["cursor"], "110")
        self.assertEqual(len(HistoryState(reopen).recent(self.cfg.account)), 2)

    def test_high_volume_incremental_history_never_skips_unprocessed_ids(self):
        first = run(self.store, self.cfg, self.api, self.model)
        self.assertEqual(first["processed"], 1)
        original_checked = HistoryState(self.store).current(self.cfg.account)["checked_at"]
        self.now += 3600
        ids = [format(256 + index, "x") for index in range(45)]
        self.api.items.update({mid: incoming(mid, self.now - 60) for mid in ids})
        self.api.delta = ("210", ids, 0)

        part = run(self.store, self.cfg, self.api, self.model)
        self.assertEqual(part["status"], "history_chunk_pending")
        self.assertEqual(part["processed"], 30)
        self.assertEqual(HistoryState(self.store).current(self.cfg.account)["cursor"], "100")
        self.assertEqual(HistoryState(self.store).current(self.cfg.account)["checked_at"],
                         original_checked)
        self.now += 301
        final = run(self.store, self.cfg, self.api, self.model)
        self.assertEqual(final["processed"], 15)
        self.assertEqual(HistoryState(self.store).current(self.cfg.account)["cursor"], "210")
        self.assertEqual(len(set(self.model.calls)), 46)
        self.assertEqual(len(self.model.calls), 46)

    def test_explicit_prune_removes_old_triage_but_keeps_seen_tombstones(self):
        run(self.store, self.cfg, self.api, self.model)
        state = HistoryState(self.store)
        self.assertEqual(len(state.recent(self.cfg.account)), 1)
        from okal_core.mail.state import MailState

        result = MailState(self.store).prune(self.now + 1)
        self.assertEqual(result["history_briefings_deleted"], 1)
        self.assertEqual(len(state.recent(self.cfg.account)), 0)
        self.assertIn("aa", state.seen(self.cfg.account, ["aa"]))
        self.assertEqual(state.current(self.cfg.account)["cursor"], "100")

    def test_model_failure_keeps_cursor_and_retries_after_restart(self):
        run(self.store, self.cfg, self.api, self.model)
        self.now += 3600
        self.api.items["bb"] = incoming("bb", self.now - 1)
        self.api.delta = ("150", ["bb"], 0)
        self.model.fail = True
        with self.assertRaisesRegex(MailError, "invalid_model_output"):
            run(self.store, self.cfg, self.api, self.model)
        status = local_status(self.store, self.cfg.account)
        self.assertEqual(status["state"], "failed_last_attempt")
        self.assertEqual(HistoryState(self.store).current(self.cfg.account)["cursor"], "100")
        self.model.fail = False
        another_store = Store(self.store.directory, clock=lambda: self.now + 310)
        out = run(another_store, self.cfg, self.api, self.model)
        self.assertEqual(out["processed"], 1)
        self.assertEqual(HistoryState(another_store).current(self.cfg.account)["cursor"], "150")
        self.assertIsNone(local_status(another_store, self.cfg.account)["last_error"])

    def test_expired_history_recovers_visible_mail_with_explicit_caveat(self):
        run(self.store, self.cfg, self.api, self.model)
        self.now += 3 * 3600
        self.api.expired = True
        self.api.cursor = "250"
        self.api.items["cc"] = incoming("cc", self.now - 60)
        out = run(self.store, self.cfg, self.api, self.model)
        self.assertTrue(out["recovered"])
        self.assertEqual(out["processed"], 1)
        self.assertEqual(HistoryState(self.store).current(self.cfg.account)["cursor"], "250")
        content = self.store.list_summaries()["items"][0]["body"]
        self.assertIn("history expired", content)
        self.assertEqual(self.model.calls, ["aa", "cc"])

    def test_more_than_31_days_expired_fails_without_skipping(self):
        run(self.store, self.cfg, self.api, self.model)
        self.now += 32 * 86400
        self.api.expired = True
        self.api.cursor = "900"
        with self.assertRaisesRegex(MailError, "window_exceeded"):
            run(self.store, self.cfg, self.api, self.model)
        self.assertEqual(HistoryState(self.store).current(self.cfg.account)["cursor"], "100")
        self.assertEqual(self.api.collections, 1)

    def test_checkpoint_compare_and_swap_rejects_lost_updates(self):
        state = HistoryState(self.store)
        run(self.store, self.cfg, self.api, self.model)
        with self.assertRaisesRegex(MailError, "checkpoint_changed"):
            state.commit(self.cfg.account, None, "150", "history_delta", [], "")
        self.assertEqual(state.current(self.cfg.account)["cursor"], "100")

    def test_local_status_never_initializes_history_tables(self):
        first = local_status(self.store, self.cfg.account)
        self.assertEqual(first["state"], "never_run")
        with self.store.connect() as db:
            self.assertFalse(db.execute(
                "SELECT 1 FROM sqlite_master WHERE name='mail_sync_state'").fetchone())

    def test_worker_immediate_first_sync_then_throttles(self):
        write_private(root(self.store) / "config.json", self.cfg.model_dump())
        called = []
        def fake_run(cfg):
            called.append(cfg.account)
            current = HistoryState(self.store).current(cfg.account)
            HistoryState(self.store).commit(cfg.account,
                current["cursor"] if current else None,
                str(100 + len(called)), "history_delta", [], "")
        worker = Worker(self.store, sync_run=fake_run)
        worker.tick()
        self.assertEqual(called, [self.cfg.account])
        worker.tick()
        self.assertEqual(len(called), 1)
        self.now += 301
        worker.tick()
        self.assertEqual(len(called), 2)

    def test_worker_failure_recorded_without_crashing_local_inbox(self):
        write_private(root(self.store) / "config.json", self.cfg.model_dump())
        worker = Worker(self.store, sync_run=lambda cfg: (_ for _ in ()).throw(
            MailError("authorization_required")))
        worker.tick()
        self.assertEqual(local_status(self.store, self.cfg.account)["state"],
                         "failed_last_attempt")
        self.assertEqual(local_status(self.store, self.cfg.account)["last_error"],
                         "authorization_required")

    def test_provider_history_pages_and_budgets(self):
        service = MagicMock()
        service.users.return_value.history.return_value.list.return_value.execute.side_effect = [
            {"history": [{"messagesAdded": [{"message": {"id": "aa"}}]}],
             "nextPageToken": "next", "historyId": "109"},
            {"history": [{"messagesAdded": [{"message": {"id": "bb"}}],
                          "messagesDeleted": [{"message": {"id": "cc"}}]}],
             "historyId": "120"},
        ]
        marker, mids, deleted = Gmail(service).history_changes("100", 3)
        self.assertEqual((marker, mids, deleted), ("120", ["aa", "bb"], 1))
        service.users.return_value.history.return_value.list.return_value.execute.side_effect = None
        service.users.return_value.history.return_value.list.return_value.execute.return_value = {
            "history": [{"messagesAdded": [{"message": {"id": "aa"}},
                                          {"message": {"id": "bb"}}]}],
            "historyId": "125",
        }
        with self.assertRaisesRegex(MailError, "budget"):
            Gmail(service).history_changes("100", 1)

    def test_refresh_token_rotation_persisted_and_retained(self):
        class FakeCred:
            valid = False

            def __init__(self):
                self.token = "short-lived-access-token"
                self.refresh_token = "refresh-rotated"

            def refresh(self, request):
                self.token = "new-access-token"

            def to_json(self):
                import json
                return json.dumps({
                    "token": self.token,
                    # Simulate a library/token endpoint that omits refresh_token
                    # when only the access credential is rotated.
                    "refresh_token": None,
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "scopes": [READ],
                    "client_id": "synthetic",
                    "client_secret": "synthetic",
                })

        path = root(self.store) / "token.json"
        write_private(path, {
            "scopes": [READ],
            "token_uri": "https://oauth2.googleapis.com/token",
            "refresh_token": "original-refresh",
            "token": "old-access",
            "client_id": "synthetic", "client_secret": "synthetic",
        })
        cred = FakeCred()
        provider = MagicMock()
        with patch("google.oauth2.credentials.Credentials.from_authorized_user_info",
                   return_value=cred), patch.object(
                       Gmail, "from_credentials", return_value=provider):
            self.assertIs(Gmail.open(self.store, self.cfg), provider)
        saved = read_private(path)
        self.assertEqual(saved["token"], "new-access-token")
        self.assertEqual(saved["refresh_token"], "original-refresh")
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_transport_persists_credential_after_before_request_refresh(self):
        import httpx

        class FakeCred:
            token = "old"

            def before_request(self, request, method, uri, headers):
                self.token = "renewed"
                headers["Authorization"] = "Bearer renewed"

        persisted = []
        client = httpx.Client(transport=httpx.MockTransport(
            lambda req: httpx.Response(200, json={"historyId": "100"})
        ), trust_env=False)
        credential = FakeCred()
        transport = GoogleTransport(
            credential, client=client, persist=lambda cred: persisted.append(cred.token)
        )
        try:
            response, payload = transport.request(
                "https://gmail.googleapis.com/gmail/v1/users/me/profile"
            )
        finally:
            transport.close()
        self.assertEqual(int(response.status), 200)
        self.assertIn(b"100", payload)
        self.assertEqual(persisted, ["renewed"])

    def test_authenticated_structured_triage_no_provider_access(self):
        run(self.store, self.cfg, self.api, self.model)
        write_private(root(self.store) / "config.json", self.cfg.model_dump())
        token = self.store.issue_device("browser")["token"]
        with TestClient(create_app(self.store), base_url="http://127.0.0.1:8766",
                        client=("127.0.0.1", 1234)) as client:
            self.assertEqual(client.get("/api/v1/mail/triage").status_code, 401)
            response = client.get("/api/v1/mail/triage",
                                  headers={"Authorization": "Bearer " + token})
            self.assertEqual(response.status_code, 200)
            item = response.json()["items"][0]
            self.assertEqual(item["category"], "action")
            self.assertEqual(item["subject"], "Scheduled work")
            self.assertNotIn("Please review the plan", str(response.json()))
            self.assertIn("mail.google.com", item["link"])


if __name__ == "__main__":
    unittest.main()
