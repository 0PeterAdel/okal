"""Gmail Trash performed outside OKAL must disappear from all current local views.

Synthetic provider events only. No actual Gmail calls or model inference.
Saved provenance and history summaries remain an immutable audit trail.
"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock

from okal_core.mail.assistant import proposals
from okal_core.mail.contracts import Config, Insight, MailError, Message
from okal_core.mail.history import (
    HistoryState, local_status, recent_evidence, recent_quarantines, run
)
from okal_core.mail.provider import Gmail, HistoryDelta
from okal_core.morning import morning_brief
from okal_core.store import Store


class SyntheticGmail:
    def __init__(self, now):
        self.items = {
            "aa": Message(
                id="aa", thread_id="ff", received_ms=(now-80)*1000,
                sender="Person <person@example.com>", recipient="owner@example.com",
                reply_to="", cc="", bcc="", subject="Real planning mail",
                body="Review the verified agenda", rfc_id="<mail@example.com>",
                labels=["INBOX","UNREAD"], attachment_count=0,
            )
        }
        self.delta = HistoryDelta("100", [], 0, {})
        self.visibility = {"aa": "present"}
        self.probes = []

    def check_account(self, account):
        assert account == "owner@example.com"

    def history_marker(self):
        return "100"

    def collect(self, start, end, limit, quarantine=None):
        return list(self.items.values())

    def history_changes(self, marker, limit):
        return self.delta

    def message_visibility(self, mid):
        self.probes.append(mid)
        if mid not in self.visibility:
            raise MailError("provider_read_failed")
        return self.visibility[mid]

    def get_optional(self, mid):
        return self.items.get(mid)


class TestExternalGmailDeletion(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.now = 1800000000
        self.store = Store(Path(tmp.name)/"state", clock=lambda: self.now)
        self.cfg = Config(account="owner@example.com", model="local:test",
                          model_digest="a"*64, sync_enabled=True)
        self.api = SyntheticGmail(self.now)
        self.model = MagicMock()
        self.model.summarize.side_effect = lambda m: Insight(
            source_id=m.id, category="action", summary="راجع تفاصيل الموعد",
            suggested_action="Review source mail"
        )

    def baseline(self):
        self.assertEqual(run(self.store,self.cfg,self.api,self.model)["processed"],1)
        self.assertEqual(len(recent_evidence(self.store,self.cfg.account)),1)

    def test_external_gmail_trash_event_disappears_from_triage_and_actions(self):
        self.baseline()
        self.api.delta = HistoryDelta("200", [], 0, {"aa":"trashed"})
        outcome = run(self.store,self.cfg,self.api,self.model)
        self.assertEqual(outcome["processed"],0)
        self.assertEqual(HistoryState(self.store).current(self.cfg.account)["cursor"],"200")
        self.assertEqual(recent_evidence(self.store,self.cfg.account),[])
        self.assertEqual(proposals(self.store,self.cfg.account)["total_in_sample"],0)
        # The old provenance and seen-set are preserved for audit/deduplication.
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM mail_sync_insights").fetchone()[0],1)
            self.assertEqual(db.execute(
                "SELECT status FROM mail_sync_visibility WHERE message_id='aa'"
            ).fetchone()[0],"trashed")
        self.assertIn("aa",HistoryState(self.store).seen(self.cfg.account,["aa"]))

    def test_old_deleted_message_reconciles_even_when_history_does_not_contain_event(self):
        self.baseline()
        # The previous service checkpoint advanced before this feature existed.
        self.api.delta = HistoryDelta("101", [], 0, {})
        self.api.visibility["aa"] = "trashed"
        self.api.probes.clear()
        run(self.store,self.cfg,self.api,self.model)
        self.assertEqual(self.api.probes,["aa"])
        self.assertFalse(recent_evidence(self.store,self.cfg.account))
        self.assertEqual(morning_brief(self.store)["new_action_emails"],[])
        # Reconciliation is not repeated every tick: 24-hour cooldown.
        self.api.probes.clear()
        run(self.store,self.cfg,self.api,self.model)
        self.assertEqual(self.api.probes,[])

    def test_permanent_delete_hides_and_restore_from_trash_shows_existing_record(self):
        self.baseline()
        self.api.delta = HistoryDelta("200", [], 1, {"aa":"deleted"})
        run(self.store,self.cfg,self.api,self.model)
        self.assertFalse(recent_evidence(self.store,self.cfg.account))
        self.api.delta = HistoryDelta("300", [], 0, {"aa":"present"})
        run(self.store,self.cfg,self.api,self.model)
        self.assertEqual(len(recent_evidence(self.store,self.cfg.account)),1)

    def test_quarantined_source_disappears_and_review_counts_update(self):
        self.baseline()
        with self.store.connect() as db, db:
            db.execute("INSERT INTO mail_sync_quarantine VALUES(?,?,?,?)",
                       (self.cfg.account,"bb","unreadable_message",self.now))
        self.api.visibility["bb"]="trashed"
        self.api.delta=HistoryDelta("110", [], 0, {})
        self.assertEqual(len(recent_quarantines(self.store,self.cfg.account)),1)
        run(self.store,self.cfg,self.api,self.model)
        self.assertEqual(len(recent_quarantines(self.store,self.cfg.account)),0)
        self.assertEqual(local_status(self.store,self.cfg.account)["manual_review_count"],0)
        self.assertEqual(morning_brief(self.store)["manual_review_count"],0)

    def test_native_probe_failure_does_not_advance_cursor_or_hide_anything(self):
        self.baseline()
        self.api.delta=HistoryDelta("200",[],0,{})
        self.api.visibility.pop("aa")
        with self.assertRaisesRegex(MailError,"provider_read_failed"):
            run(self.store,self.cfg,self.api,self.model)
        self.assertEqual(HistoryState(self.store).current(self.cfg.account)["cursor"],"100")
        self.assertEqual(len(recent_evidence(self.store,self.cfg.account)),1)

    def test_native_history_parses_label_added_removed_and_deleted(self):
        service=MagicMock()
        service.users.return_value.history.return_value.list.return_value.execute.return_value={
            "historyId":"250",
            "history":[
                {"labelsAdded":[{"message":{"id":"aa"},"labelIds":["TRASH"]}]},
                {"labelsRemoved":[{"message":{"id":"aa"},"labelIds":["TRASH"]}]},
                {"labelsAdded":[{"message":{"id":"bb"},"labelIds":["TRASH"]}]},
                {"messagesDeleted":[{"message":{"id":"cc"}}]},
            ],
        }
        result=Gmail(service).history_changes("100",100)
        cursor,ids,deleted=result
        self.assertEqual((cursor,ids,deleted),("250",[],1))
        self.assertEqual(result.visibility,{
            "aa":"present", "bb":"trashed", "cc":"deleted",
        })
        args=service.users.return_value.history.return_value.list.call_args.kwargs
        self.assertIn("labelAdded",args["historyTypes"])
        self.assertIn("labelRemoved",args["historyTypes"])

    def test_current_gmail_visibility_reads_minimal_labels_or_404(self):
        service=MagicMock()
        service.users.return_value.messages.return_value.get.return_value.execute.return_value={
            "id":"aa","labelIds":["INBOX","TRASH"]
        }
        provider=Gmail(service)
        self.assertEqual(provider.message_visibility("aa"),"trashed")
        service.users.return_value.messages.return_value.get.return_value.execute.return_value={
            "id":"aa","labelIds":["INBOX"]
        }
        self.assertEqual(provider.message_visibility("aa"),"present")


if __name__ == "__main__":
    unittest.main()
