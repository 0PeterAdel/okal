"""SQLite planner, native Gmail→Tasks and local notification acceptance.

All tests run with a fake clock and injected notifier. No real desktop
notification, Google account or network access is invoked.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from okal_core.api import create_app
from okal_core.mail.contracts import Config, Insight
from okal_core.mail.history import HistoryState
from okal_core.mail.private import root, write_private
from okal_core.store import Store
from okal_core.task_planner import TaskPlanner, ReminderWorker


class PlannerTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.now=[1793500000]
        self.state=Path(tmp.name)/"state"
        self.store=Store(self.state,clock=lambda:self.now[0])
        self.planner=TaskPlanner(self.store)
        self.headers={"Origin":"http://127.0.0.1:8766",
                      "Sec-Fetch-Site":"same-origin"}
        self.client=TestClient(create_app(self.store,require_read_key=False),
            base_url="http://127.0.0.1:8766",
            client=("127.0.0.1",12001))
        self.addCleanup(self.client.close)

    def later(self,seconds=7200):
        return datetime.fromtimestamp(
            self.now[0]+seconds,timezone.utc
        ).isoformat()

    def test_persistent_due_time_and_readonly_weekly_agenda(self):
        due=self.later()
        row=self.planner.create("تسليم المرحلة","Review code",due,15)
        self.assertEqual(row["status"],"open")
        other=TaskPlanner(Store(self.state,clock=lambda:self.now[0]))
        records=other.list()["items"]
        self.assertEqual(len(records),1)
        self.assertEqual(records[0]["notes"],"Review code")
        self.assertEqual(records[0]["reminder"]["lead_minutes"],15)
        agenda=other.agenda(7)
        self.assertEqual(agenda["timezone"],"Africa/Cairo")
        self.assertEqual(sum(agenda["counts"].values()),1)
        self.assertFalse(agenda["has_google_calendar"])

    def test_invalid_reminder_is_rejected_before_task_creation(self):
        with self.assertRaisesRegex(ValueError,"local_reminder_requires_owner_due_time"):
            self.planner.create("No due","",None,15)
        with self.assertRaisesRegex(ValueError,"invalid_local_reminder_lead"):
            self.planner.create("Bad","",self.later(),7)
        self.assertEqual(self.planner.list()["items"],[])

    def test_owner_complete_reopen_and_cancelled_reminder_never_fires(self):
        row=self.planner.create("Complete","",self.later(3600),15)
        key=row["task_id"]
        self.planner.transition(key,"done")
        self.assertEqual(self.planner.list()["items"],[])
        self.planner.transition(key,"open")
        reminder=self.planner.list()["items"][0]["reminder"]
        self.assertEqual(reminder["status"],"cancelled")
        self.now[0]+=4000
        events=[]
        ReminderWorker(self.store,notify=lambda title,lead:events.append(title)).tick()
        self.assertEqual(events,[])
        self.assertEqual(self.planner.list()["items"][0]["status"],"open")

    def test_edit_reschedules_and_missed_reminders_do_not_notify(self):
        row=self.planner.create("First","",self.later(),60)
        key=row["task_id"]
        self.planner.edit(key,"Updated","revised",self.later(4000),5)
        self.assertEqual(self.planner.list()["items"][0]["title"],"Updated")
        self.now[0]+=6000
        hits=[]
        ReminderWorker(self.store,notify=lambda t,m:hits.append(t)).tick()
        self.assertEqual(hits,[])
        self.assertEqual(self.planner.list()["items"][0]["reminder"]["status"],"missed")

    def test_reminder_notifies_at_most_once_even_after_restart(self):
        row=self.planner.create("Take break","",self.later(2400),15)
        self.now[0]+=1600
        hits=[]
        worker=ReminderWorker(self.store,notify=lambda title,lead:
            hits.append((title,lead)) or True)
        worker.tick()
        worker.tick()
        other=ReminderWorker(Store(self.state,clock=lambda:self.now[0]),
            notify=lambda title,lead:hits.append(("duplicate",lead)) or True)
        other.tick()
        self.assertEqual(hits,[("Take break",15)])
        self.assertEqual(self.planner.list()["items"][0]["reminder"]["status"],"sent")

    def test_failed_desktop_delivery_not_silently_repeated(self):
        self.planner.create("Desktop","",self.later(900),0)
        self.now[0]+=900
        hits=[]
        worker=ReminderWorker(self.store,notify=lambda title,lead:
            hits.append(title) or False)
        worker.tick()
        worker.tick()
        self.assertEqual(hits,["Desktop"])
        self.assertEqual(self.planner.list()["items"][0]["reminder"]["status"],"failed")

    def test_api_owner_create_edit_done_history_reopen(self):
        create=self.client.post("/api/v1/tasks/create",headers=self.headers,json={
            "title":"New task","notes":"From dashboard",
            "due":self.later(),"reminder_minutes":15
        })
        self.assertEqual(create.status_code,200,create.text)
        key=create.json()["task_id"]
        agenda=self.client.get("/api/v1/planner")
        self.assertEqual(agenda.status_code,200)
        self.assertEqual(sum(agenda.json()["counts"].values()),1)
        edit=self.client.post("/api/v1/tasks/edit",headers=self.headers,json={
            "task_id":key,"title":"Updated title","notes":"",
            "due":None,"reminder_minutes":None
        })
        self.assertEqual(edit.status_code,200,edit.text)
        self.assertIsNone(self.planner.list()["items"][0]["due_at"])
        done=self.client.post("/api/v1/tasks/transition",headers=self.headers,
            json={"task_id":key,"status":"done"})
        self.assertEqual(done.status_code,200)
        self.assertEqual(self.client.get("/api/v1/tasks").json()["items"],[])
        all_rows=self.client.get("/api/v1/tasks/history").json()["items"]
        self.assertEqual(all_rows[0]["status"],"done")
        reopen=self.client.post("/api/v1/tasks/transition",headers=self.headers,
            json={"task_id":key,"status":"open"})
        self.assertEqual(reopen.status_code,200)
        self.assertEqual(len(self.planner.list()["items"]),1)

    def test_local_write_rejects_cross_site_and_invalid_due(self):
        bad=self.client.post("/api/v1/tasks/create",
            headers={"Origin":"http://evil.example"},
            json={"title":"X","notes":"","due":None,"reminder_minutes":None})
        self.assertEqual(bad.status_code,403)
        unknown=self.client.post("/api/v1/tasks/create",headers=self.headers,
            json={"title":"X","notes":"","due":"tomorrow","reminder_minutes":15})
        self.assertEqual(unknown.status_code,422)
        self.assertEqual(self.planner.list()["items"],[])

    def test_gmail_task_source_idempotent_without_inventing_deadline(self):
        cfg=Config(account="owner@example.com",model="local:test",
                   model_digest="a"*64,sync_enabled=True)
        write_private(root(self.store)/"config.json",cfg.model_dump())
        HistoryState(self.store)
        metadata={"id":"aa","subject":"Action mail","sender":"Sender",
                  "labels":["INBOX"],"received_ms":self.now[0]*1000}
        with self.store.connect() as db,db:
            db.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?)",
              ("a"*32,"mail","acct","mail-plan","digest",self.now[0],"succeeded"))
            db.execute("INSERT INTO mail_sync_insights VALUES(?,?,?,?,?)",
              ("a"*32,cfg.account,"aa",json.dumps(metadata),Insight(
                  source_id="aa",category="action",summary="Review project",
                  suggested_action="Review").model_dump_json()))
        for idx in range(2):
            res=self.client.post("/api/v1/mail/tasks/from-message",
                headers=self.headers,json={"message_id":"aa","due":None,
                                           "reminder_minutes":None})
            self.assertEqual(res.status_code,200,res.text)
            self.assertEqual(res.json()["status"],"open" if idx==0
                              else "already_recorded")
        self.assertEqual(len(self.planner.list()["items"]),1)
        self.assertIsNone(self.planner.list()["items"][0]["due_at"])


if __name__=="__main__":
    unittest.main()
