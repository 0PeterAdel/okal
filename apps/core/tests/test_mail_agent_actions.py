"""Mail Agent V1: read/unread/archive require owner approval; draft/task stay local."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from okal_core.api import create_app
from okal_core.mail.contracts import Config, Insight, Message, MailError
from okal_core.mail.history import HistoryState, recent_evidence
from okal_core.mail.operations import preview
from okal_core.mail.private import root, write_private
from okal_core.mail.state import MailState
from okal_core.store import Store


class AgentActionsTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store=Store(Path(tmp.name)/"state",clock=lambda:1800000000)
        self.cfg=Config(account="owner@example.com",model="local:test",
            model_digest="a"*64,trash_enabled=True,sync_enabled=True,
            local_only_confirmed=True)
        write_private(root(self.store)/"config.json",self.cfg.model_dump())
        HistoryState(self.store)
        MailState(self.store)
        meta={"id":"aa","subject":"Project update","sender":"Manager <manager@example.com>",
              "labels":["INBOX","UNREAD"],"received_ms":1799999999000,
              "thread_id":"ff"}
        with self.store.connect() as db,db:
            db.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?)",
              ("a"*32,"mail","acct","mail-agent","digest",1800000000,"succeeded"))
            db.execute("INSERT INTO mail_sync_insights VALUES(?,?,?,?,?)",
              ("a"*32,self.cfg.account,"aa",json.dumps(meta),Insight(
                  source_id="aa",category="action",summary="Review update",
                  suggested_action="Reply after review").model_dump_json()))
        self.api=MagicMock()
        self.api.close.return_value=None
        self.api.service.users.return_value.messages.return_value.get.return_value="get"
        self.api.service.users.return_value.messages.return_value.modify.return_value="modify"
        self.meta={"id":"aa","labelIds":["INBOX","UNREAD"],
          "payload":{"headers":[{"name":"Subject","value":"Project update"}]}}
        self.minimal={"id":"aa","labelIds":["INBOX"]}
        self.headers={"Origin":"http://127.0.0.1:8766",
                      "Sec-Fetch-Site":"same-origin"}
        self.client=TestClient(create_app(self.store,require_read_key=False),
             base_url="http://127.0.0.1:8766",
             client=("127.0.0.1",12000))
        self.addCleanup(self.client.close)

    def _preview(self, action="mark_read"):
        r=self.client.post("/api/v1/mail/actions/preview",headers=self.headers,
            json={"ids":["aa"],"action":action})
        self.assertEqual(r.status_code,200,r.text)
        return r.json()

    def _commit(self,p,action="mark_read"):
        return self.client.post("/api/v1/mail/actions/commit",headers=self.headers,
            json={"ids":["aa"],"action":action,"approval_digest":p["approval_digest"],
                "confirmation_token":p["confirmation_token"],"confirmed":True})

    def test_native_preview_is_readonly_and_confirmed_read_updates_gmail_once(self):
        self.api.call.side_effect=[self.meta,self.meta,self.meta,{"id":"aa"},self.minimal]
        with patch("okal_core.mail.provider.Gmail.open",return_value=self.api):
            p=self._preview()
            self.assertEqual(p["count"],1)
            self.assertFalse(p["external_writes"])
            self.api.service.users.return_value.messages.return_value.modify.assert_not_called()
            result=self._commit(p)
            self.assertEqual(result.status_code,200,result.text)
            self.assertEqual(result.json()["status"],"confirmed")
            self.assertEqual(result.json()["action"],"mark_read")
            mod=self.api.service.users.return_value.messages.return_value.modify
            self.assertEqual(mod.call_count,1)
            self.assertEqual(mod.call_args.kwargs["body"]["removeLabelIds"],["UNREAD"])
            replay=self._commit(p)
            self.assertEqual(replay.status_code,409)
            self.assertEqual(mod.call_count,1)

    def test_archive_disappears_from_saved_active_inbox_but_keeps_evidence(self):
        after={"id":"aa","labelIds":[]}
        self.api.call.side_effect=[self.meta,self.meta,self.meta,{"id":"aa"},after]
        with patch("okal_core.mail.provider.Gmail.open",return_value=self.api):
            p=self._preview("archive")
            r=self._commit(p,"archive")
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(recent_evidence(self.store,self.cfg.account),[])
        with self.store.connect() as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM mail_sync_insights").fetchone()[0],1)

    def test_modify_scope_absent_disallows_commit_and_cross_site_requests(self):
        cfg=self.cfg.model_copy(update={"trash_enabled":False})
        write_private(root(self.store)/"config.json",cfg.model_dump())
        denied=self.client.post("/api/v1/mail/actions/commit",headers=self.headers,
            json={"ids":["aa"],"action":"archive",
                "approval_digest":"a"*64,"confirmation_token":"x"*43,
                "confirmed":True})
        self.assertEqual(denied.status_code,403)
        other=self.client.post("/api/v1/mail/tasks/from-message",
            headers={"Origin":"http://evil.example"},
            json={"message_id":"aa"})
        self.assertEqual(other.status_code,403)

    def test_invalid_action_id_does_not_issue_ticket_or_access_gmail(self):
        with patch("okal_core.mail.provider.Gmail.open",return_value=self.api):
            r=self.client.post("/api/v1/mail/actions/preview",
                headers=self.headers,json={"ids":[{"unexpected":1}],"action":"archive"})
        self.assertEqual(r.status_code,409)
        self.api.call.assert_not_called()

    def test_local_task_button_creates_exactly_one_local_task(self):
        for i in range(2):
            r=self.client.post("/api/v1/mail/tasks/from-message",
                headers=self.headers,json={"message_id":"aa"})
            self.assertEqual(r.status_code,200,r.text)
            self.assertIn(r.json()["status"],{"open","already_recorded","created","approved"})
        with self.store.connect() as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM local_tasks WHERE source_id='aa'").fetchone()[0],1)

    def test_local_ollama_reply_draft_and_owner_revision_never_send(self):
        source=Message(id="aa",thread_id="ff",received_ms=1799999999000,
           sender="Manager <manager@example.com>",recipient="owner@example.com",
           reply_to="",cc="",bcc="",subject="Project update",
           body="Can you review this?",rfc_id="<native@example.com>",
           labels=["INBOX"])
        self.api.get.return_value=source
        model=MagicMock()
        model.draft_reply.return_value="Thank you. I will review."
        with (patch("okal_core.mail.provider.Gmail.open",return_value=self.api),
              patch("okal_core.mail.inference.LocalModel",return_value=model)):
            r=self.client.post("/api/v1/mail/reply-drafts/generate",
                headers=self.headers,json={"message_id":"aa","language":"en"})
        self.assertEqual(r.status_code,200,r.text)
        original=r.json()
        self.assertEqual(original["sent"],False)
        self.assertEqual(original["recipient"],"manager@example.com")
        self.assertEqual(original["body"],"Thank you. I will review.")
        mod=self.client.post("/api/v1/mail/reply-drafts/revise",
            headers=self.headers,json={
                "draft_id":original["draft_id"],"body":"Thank you for your email."
            })
        self.assertEqual(mod.status_code,200,mod.text)
        self.assertEqual(mod.json()["sent"],False)
        self.assertNotEqual(mod.json()["draft_id"],original["draft_id"])
        self.api.send.assert_not_called()


if __name__=="__main__":
    unittest.main()
