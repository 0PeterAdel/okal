"""Owner-viewed mail is hidden locally; Gmail UNREAD events hide without re-analysis."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from okal_core.api import create_app
from okal_core.mail.contracts import Config, Insight
from okal_core.mail.history import HistoryState, recent_evidence
from okal_core.mail.inbox_visibility import upsert_unread, restore_unread_view
from okal_core.mail.private import root,write_private
from okal_core.mail.provider import Gmail
from okal_core.store import Store


class ReadProjectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/"data",clock=lambda:1800000000)
        self.cfg=Config(account="owner@example.com",model="local:test",
                        model_digest="a"*64,trash_enabled=True,sync_enabled=True)
        write_private(root(self.store)/"config.json",self.cfg.model_dump())
        HistoryState(self.store)
        with self.store.connect() as db,db:
            db.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?)",
              ("a"*32,"mail","acct","history:test","digest",1799999999,"succeeded"))
            db.execute("INSERT INTO mail_sync_insights VALUES(?,?,?,?,?)",
              ("a"*32,self.cfg.account,"aa",json.dumps({
                "id":"aa","subject":"Check PR","sender":"GitHub <notifications@github.com>",
                "labels":["UNREAD","INBOX"],"received_ms":1799999999000,
                "attachment_count":0}),Insight(
                source_id="aa",category="action",
                summary="Review workflow","suggested_action":"Open GitHub"
              ).model_dump_json()))
        self.client=TestClient(create_app(self.store,require_read_key=False),
            base_url="http://127.0.0.1:8766",
            client=("127.0.0.1",1234))
        self.addCleanup(self.client.close)
        self.headers={"Origin":"http://127.0.0.1:8766",
                      "Sec-Fetch-Site":"same-origin"}

    def test_viewed_hides_immediately_and_preserves_original_evidence(self):
        self.assertEqual(len(recent_evidence(self.store,self.cfg.account)),1)
        self.assertEqual(len(self.client.get("/api/v1/mail/triage").json()["items"]),1)
        answer=self.client.post("/api/v1/mail/viewed",headers=self.headers,
                                json={"message_id":"aa"})
        self.assertEqual(answer.status_code,200,answer.text)
        self.assertEqual(answer.json()["gmail_modified"],False)
        repeat=self.client.post("/api/v1/mail/viewed",headers=self.headers,
                                json={"message_id":"aa"})
        self.assertEqual(repeat.status_code,200,repeat.text)
        self.assertEqual(recent_evidence(self.store,self.cfg.account),[])
        self.assertEqual(self.client.get("/api/v1/mail/triage").json()["items"],[])
        with self.store.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM mail_sync_insights")
                             .fetchone()[0],1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM mail_local_seen")
                             .fetchone()[0],1)
        self.assertEqual(recent_evidence(
            Store(self.store.directory,clock=lambda:1800000500),
            self.cfg.account),[])

    def test_native_gmail_read_hides_and_explicit_unread_restores(self):
        with self.store.connect() as db,db:
            upsert_unread(db,self.cfg.account,"aa",False,1800000000)
        self.assertEqual(recent_evidence(self.store,self.cfg.account),[])
        with self.store.connect() as db,db:
            upsert_unread(db,self.cfg.account,"aa",True,1800000100)
        self.assertEqual(len(recent_evidence(self.store,self.cfg.account)),1)

    def test_onsite_viewed_then_explicit_unread_can_requeue(self):
        self.client.post("/api/v1/mail/viewed",headers=self.headers,
                         json={"message_id":"aa"})
        with self.store.connect() as db,db:
            upsert_unread(db,self.cfg.account,"aa",True,1800000100)
        self.assertEqual(recent_evidence(self.store,self.cfg.account),[])
        restore_unread_view(self.store,self.cfg.account,"aa")
        self.assertEqual(len(recent_evidence(self.store,self.cfg.account)),1)

    def test_write_rejected_cross_site_and_unknown_source(self):
        denied=self.client.post("/api/v1/mail/viewed",
            headers={"Origin":"https://untrusted.example"},
            json={"message_id":"aa"})
        self.assertEqual(denied.status_code,403)
        unknown=self.client.post("/api/v1/mail/viewed",
            headers=self.headers,json={"message_id":"ab"})
        self.assertEqual(unknown.status_code,409)
        self.assertEqual(len(recent_evidence(self.store,self.cfg.account)),1)

    def test_google_history_reads_native_label_changes_without_model_calls(self):
        api=Gmail(MagicMock())
        api.call=MagicMock(return_value={
            "historyId":"105",
            "history":[{
                "labelsRemoved":[{"message":{"id":"aa"},"labelIds":["UNREAD"]}],
                "labelsAdded":[{"message":{"id":"ab"},"labelIds":["UNREAD"]}]
            }]
        })
        delta=api.history_changes("100",10000)
        self.assertEqual(delta.read_updates,{"aa":False,"ab":True})
        self.assertEqual(list(delta),["105",[],0])
        self.assertEqual(delta.visibility,{})


if __name__=="__main__":
    unittest.main()
