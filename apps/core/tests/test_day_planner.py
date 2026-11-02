"""Local Plan My Day contract: explicit estimates, safe tentative slots, approval."""
from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from okal_core.api import create_app
from okal_core.calendar_core import CalendarCore
from okal_core.day_planner import DayPlanManager
from okal_core.store import Store
from okal_core.task_planner import TaskPlanner


CAIRO = ZoneInfo("Africa/Cairo")


def payload(date="2026-11-02", tasks=None, start="09:00", end="14:00"):
    return {"date":date, "work_start":start, "work_end":end,
            "tasks":tasks if tasks is not None else []}


class LocalDayPlanningTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.now = int(datetime(2026,11,2,8,tzinfo=CAIRO).timestamp())
        self.store = Store(Path(directory.name)/"private", clock=lambda:self.now)
        self.planner = DayPlanManager(self.store)
        self.board = TaskPlanner(self.store)
        self.calendar = CalendarCore(self.store)
        self.first = self.board.create("Fix OKAL UX")["task_id"]
        self.second = self.board.create("Write project plan")["task_id"]

    def selection(self, key=None, minutes=60, priority="normal"):
        return {"task_id":key or self.first,"minutes":minutes,"priority":priority}

    def event(self, title="Meeting", begin="2026-11-02T10:00:00+02:00",
              finish="2026-11-02T11:00:00+02:00", **changes):
        row = {"id":title,"title":title,"start":begin,"end":finish,
               "timezone":"Africa/Cairo",
               "updated":"2026-11-01T08:00:00+02:00"}
        row.update(changes)
        return row

    def test_priority_and_meetings_produce_tentative_non_overlapping_blocks(self):
        self.calendar.ingest("google","default","primary",[self.event()])
        result = self.planner.preview(payload(tasks=[
            self.selection(self.second,90,"normal"),
            self.selection(self.first,60,"high"),
        ]))
        self.assertEqual(len(result["blocks"]),2)
        first,second=result["blocks"]
        self.assertEqual(first["task_id"],self.first)
        self.assertEqual(first["start_ts"],
            int(datetime(2026,11,2,9,tzinfo=CAIRO).timestamp()))
        self.assertEqual(second["start_ts"],
            int(datetime(2026,11,2,11,tzinfo=CAIRO).timestamp()))
        self.assertLessEqual(first["end_ts"],second["start_ts"])
        self.assertFalse(result["availability_verified"])
        self.assertTrue(result["owner_review_required"])
        self.assertFalse(result["external_reads"])
        self.assertFalse(result["external_writes"])
        self.assertFalse(result["ai_actions_executed"])

    def test_no_duration_guessed_and_strict_bounded_owner_input(self):
        for invalid in (
            payload(), payload(tasks=[self.selection(minutes=0)]),
            payload(tasks=[self.selection(minutes=True)]),
            payload(tasks=[self.selection(minutes=25)]),
            payload(tasks=[self.selection(priority="unknown")]),
            payload(tasks=[self.selection(),self.selection()]),
            payload(tasks=[self.selection()],date="2026-11-09"),
            payload(tasks=[self.selection()],start="10:10"),
            payload(tasks=[self.selection()],start="16:00",end="10:00"),
            payload(tasks=[self.selection()],start="00:00",end="23:00"),
            payload(tasks=[self.selection()],date="not-a-date"),
            payload(tasks=[self.selection()],date="2026-11-01"),
        ):
            with self.subTest(input=invalid),self.assertRaises(ValueError):
                self.planner.preview(invalid)

    def test_deadline_never_missed_silently(self):
        due="2026-11-02T09:30:00+02:00"
        self.board.edit(self.first,"Fix OKAL UX","",due)
        result=self.planner.preview(payload(tasks=[self.selection(minutes=60)]))
        self.assertEqual(result["blocks"],[])
        self.assertEqual(result["unplaced"][0]["reason"],
                         "deadline_or_window_too_short")

    def test_all_day_busy_blocks_every_slot_and_instant_is_not_busy(self):
        self.calendar.ingest("google","default","primary",[
            self.event("all-day","2026-11-02T00:00:00+02:00",
                       "2026-11-03T00:00:00+02:00", all_day=True)
        ])
        result=self.planner.preview(payload(tasks=[self.selection()]))
        self.assertEqual(result["blocks"],[])
        # Separate slot exercise: zero-duration event should never block a slot.
        self.calendar.ingest("google","default","primary",[
            self.event("all-day","2026-11-02T00:00:00+02:00",
                       "2026-11-03T00:00:00+02:00",
                       all_day=True,cancelled=True,
                       updated="2026-11-01T09:00:00+02:00"),
            self.event("instant","2026-11-02T09:00:00+02:00",
                       "2026-11-02T09:00:00+02:00"),
        ])
        result=self.planner.preview(payload(tasks=[self.selection()]))
        self.assertEqual(result["blocks"][0]["start_ts"],
                         int(datetime(2026,11,2,9,tzinfo=CAIRO).timestamp()))

    def test_approval_is_local_single_use_with_saved_history(self):
        preview=self.planner.preview(payload(tasks=[self.selection()]))
        response=self.planner.confirm(preview["confirmation_token"],True)
        self.assertEqual(response["status"],"saved_locally_only")
        self.assertEqual(response["blocks_saved"],1)
        self.assertEqual(response["google_events_created"],0)
        self.assertEqual(response["task_deadlines_changed"],0)
        self.assertFalse(response["external_writes"])
        history=self.planner.saved()
        self.assertEqual(len(history["items"]),1)
        self.assertEqual(history["items"][0]["blocks"][0]["title"],"Fix OKAL UX")
        self.assertFalse(history["external_writes"])
        with self.assertRaisesRegex(ValueError,"consumed"):
            self.planner.confirm(preview["confirmation_token"],True)

    def test_no_implicit_confirmation_or_expired_ticket(self):
        preview=self.planner.preview(payload(tasks=[self.selection()]))
        with self.assertRaisesRegex(ValueError,"confirmation"):
            self.planner.confirm(preview["confirmation_token"],False)
        # Explicit refusal did not consume the ticket.
        self.now += 601
        with self.assertRaisesRegex(ValueError,"expired"):
            self.planner.confirm(preview["confirmation_token"],True)

    def test_calendar_change_invalidates_pending_local_plan(self):
        preview=self.planner.preview(payload(tasks=[self.selection()]))
        self.calendar.ingest("google","default","primary",[self.event()])
        with self.assertRaisesRegex(ValueError,"sources_changed"):
            self.planner.confirm(preview["confirmation_token"],True)
        self.assertEqual(self.planner.saved()["items"],[])

    def test_task_change_or_completion_invalidates_pending_plan(self):
        preview=self.planner.preview(payload(tasks=[self.selection()]))
        self.board.edit(self.first,"Changed task","",None)
        with self.assertRaisesRegex(ValueError,"sources_changed"):
            self.planner.confirm(preview["confirmation_token"],True)
        another=self.planner.preview(payload(tasks=[self.selection()]))
        self.board.transition(self.first,"done")
        with self.assertRaisesRegex(ValueError,"task_closed_or_not_found"):
            self.planner.confirm(another["confirmation_token"],True)
        self.assertEqual(self.planner.saved()["items"],[])

    def test_provider_coverage_not_verified_even_without_busy_events(self):
        preview=self.planner.preview(payload(tasks=[self.selection()]))
        self.assertEqual(preview["coverage_status"],"cached_sources_unverified")
        self.assertFalse(preview["availability_verified"])
        self.assertEqual(preview["blocks"][0]["status"],"tentative_local_only")

    def test_web_requires_same_origin_confirm_and_existing_session(self):
        app = create_app(self.store)
        with TestClient(app,base_url="http://127.0.0.1:8766",
                        client=("127.0.0.1",1234)) as client:
            body=payload(tasks=[self.selection()])
            self.assertEqual(client.post(
                "/api/v1/calendar/day-plan/preview",json=body).status_code,401)
            headers={"Origin":"http://127.0.0.1:8766",
                     "Sec-Fetch-Site":"same-origin"}
            preview=client.post("/api/v1/calendar/day-plan/preview",
                                json=body,headers=headers)
            self.assertEqual(preview.status_code,200,preview.text)
            self.assertEqual(client.get(
                "/api/v1/calendar/day-plan/saved").status_code,200)
            ticket=preview.json()["confirmation_token"]
            confirm=client.post("/api/v1/calendar/day-plan/confirm",
                json={"confirmation_token":ticket,"confirmed":True},
                headers=headers)
            self.assertEqual(confirm.status_code,200,confirm.text)
            self.assertEqual(confirm.json()["google_events_created"],0)
            self.assertEqual(client.post(
                "/api/v1/calendar/day-plan/confirm",
                json={"confirmation_token":ticket,"confirmed":True},
                headers=headers).status_code,409)

    def test_protected_web_denies_unauthorized_read(self):
        with TestClient(
            create_app(self.store,require_read_key=True),
            base_url="http://127.0.0.1:8766",
            client=("127.0.0.1",1234),
        ) as client:
            self.assertEqual(client.get(
                "/api/v1/calendar/day-plan/saved").status_code,401)
            self.assertEqual(client.post(
                "/api/v1/calendar/day-plan/preview",json=payload(
                    tasks=[self.selection()]),
                headers={"Origin":"http://127.0.0.1:8766"}
            ).status_code,401)


if __name__=="__main__":
    unittest.main()
