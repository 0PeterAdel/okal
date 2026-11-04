"""Owner-local appointments, goals, replay protection and offline daily facts."""
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from fastapi.testclient import TestClient
from okal_core.store import Store
from okal_core.local_calendar import LocalCalendar, LocalCalendarConflict
from okal_core.task_planner import ReminderWorker
from okal_core.calendar_core import CalendarCore
from okal_core.daily_brief import view
from okal_core.api import create_app

class CommitmentsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / 'state'
        self.now = [1793754000]
        self.store = Store(self.path, clock=lambda: self.now[0])
        self.cal = LocalCalendar(self.store)

    def payload(self, **changes):
        def iso(delta):
            return datetime.fromtimestamp(self.now[0]+delta, timezone.utc).isoformat()
        value = dict(id='a'*32, revision=0, kind='event', title='Review fixture',
                     notes='Private fixture', start=iso(3600), end=iso(7200),
                     target_date=None, reminder_minutes=15)
        value.update(changes)
        return value

    def test_restart_replay_edit_and_stale_write(self):
        payload = self.payload()
        self.cal.save(payload)
        reopened = LocalCalendar(Store(self.path, clock=lambda: self.now[0]))
        self.assertTrue(reopened.save(payload)['replayed'])
        reopened.save(dict(payload, revision=1, title='Changed'))
        self.assertEqual(reopened.save(payload)['revision'], 2)
        self.assertEqual(reopened.list()['items'][0]['title'], 'Changed')
        with self.assertRaises(LocalCalendarConflict):
            reopened.save(dict(payload, revision=1))
        with self.assertRaises(LocalCalendarConflict):
            reopened.save(dict(payload, title='Different request'))
        reopened.transition(payload['id'], 2, 'done')
        self.assertEqual(reopened.list()['items'], [])
        self.assertEqual(reopened.list(True)['items'][0]['reminder_status'], 'cancelled')

    def test_goal_date_has_no_busy_time(self):
        self.cal.save(self.payload(kind='goal', start=None, end=None,
                                  target_date='2026-11-10', reminder_minutes=None))
        self.assertEqual(CalendarCore(self.store).agenda()['items'], [])
        result = view(self.store)
        self.assertTrue(result['details'][0]['date_only'])
        self.assertEqual(result['details'][0]['when'], '2026-11-10')
        self.assertFalse(result['planning_requested'])
        self.assertFalse(result['voice_enabled'])

    def test_event_in_unified_agenda_and_brief(self):
        self.cal.save(self.payload())
        result = CalendarCore(self.store).agenda()
        self.assertEqual(result['items'][0]['calendar_id'], 'okal')
        brief = view(self.store)
        self.assertLessEqual(len(brief['brief_points']), 5)
        self.assertIn('Review fixture', brief['spoken_text'])
        self.assertTrue(brief['mail_sync_stale'])
        self.assertEqual(brief['sources']['gmail'], 'unverified')

    def test_claim_survives_restart_and_failure_is_not_retried(self):
        self.cal.save(self.payload())
        self.now[0] += 2700
        calls = []
        worker = ReminderWorker(self.store, notify=lambda t,m: calls.append(t) or False)
        worker.tick()
        ReminderWorker(Store(self.path, clock=lambda:self.now[0]), notify=lambda t,m:calls.append(t)).tick()
        self.assertEqual(calls, ['Review fixture'])
        self.assertEqual(self.cal.list()['items'][0]['reminder_status'], 'failed')

    def test_missed_and_cancelled_never_notify(self):
        self.cal.save(self.payload())
        self.cal.save(self.payload(id='b'*32))
        self.cal.transition('b'*32, 1, 'cancelled')
        self.now[0] += 5000
        calls=[]
        ReminderWorker(self.store, notify=lambda t,m:calls.append(t)).tick()
        self.assertEqual(calls, [])
        self.assertEqual(self.cal.list()['items'][0]['reminder_status'], 'missed')

    def test_edit_during_notification_cannot_overwrite_new_schedule(self):
        payload = self.payload()
        self.cal.save(payload)
        self.now[0] += 2700
        claimed = self.cal.claim_due()[0]
        self.cal.save(self.payload(revision=1))
        self.cal.finish_notification(claimed['id'], claimed['revision'], True)
        self.assertEqual(self.cal.list()['items'][0]['reminder_status'], 'scheduled')

    def test_title_edit_does_not_rearm(self):
        payload = self.payload()
        self.cal.save(payload)
        self.now[0] += 2700
        self.cal.claim_due()
        self.cal.save(dict(payload, revision=1, title='Rename'))
        self.assertEqual(self.cal.claim_due(), [])
        self.assertEqual(self.cal.list()['items'][0]['reminder_status'], 'attempting')

    def test_invalid_intervals_and_dates_leave_no_items(self):
        for changes in ({'end':None}, {'revision':True}, {'reminder_minutes':7},
                        {'kind':'goal', 'target_date':'2026-02-30', 'start':None, 'end':None, 'reminder_minutes':None}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.cal.save(self.payload(**changes))
        self.assertEqual(self.cal.list()['items'], [])

    def test_reads_do_not_create_local_tables(self):
        with self.store.connect() as db:
            before = list(db.execute('SELECT name FROM sqlite_master'))
        view(self.store)
        self.cal.list()
        with self.store.connect() as db:
            after = list(db.execute('SELECT name FROM sqlite_master'))
        self.assertEqual(before, after)

    def test_api_same_origin_cas_and_unicode(self):
        client = TestClient(create_app(self.store, require_read_key=False),
                            base_url='http://127.0.0.1:8766', client=('127.0.0.1',12001))
        self.addCleanup(client.close)
        url='/api/v1/calendar/local/save'
        payload=self.payload(notes='م'*1900)
        self.assertEqual(client.post(url, json=payload).status_code, 401)
        headers={'Origin':'http://127.0.0.1:8766','Sec-Fetch-Site':'same-origin'}
        self.assertEqual(client.post(url, json=payload, headers=headers).status_code, 200)
        self.assertEqual(client.post(url, json=dict(payload,title='Changed'), headers=headers).status_code,409)
        self.assertEqual(len(client.get('/api/v1/calendar/local').json()['items']),1)
        self.assertEqual(client.post(url, json=payload, headers=dict(headers,Origin='https://evil.example')).status_code,403)

    def test_read_bearer_cannot_write_and_nonlocal_is_denied(self):
        client = TestClient(create_app(self.store, require_read_key=True),
                            base_url='http://127.0.0.1:8766', client=('127.0.0.1',12001))
        self.addCleanup(client.close)
        token=self.store.issue_device('owner')['token']
        headers={'Authorization':'Bearer '+token,'Origin':'http://127.0.0.1:8766','Sec-Fetch-Site':'same-origin'}
        self.assertEqual(client.get('/api/v1/calendar/local',headers=headers).status_code,200)
        self.assertEqual(client.post('/api/v1/calendar/local/save',json=self.payload(),headers=headers).status_code,403)
        remote = TestClient(create_app(self.store, require_read_key=False),
                            base_url='http://127.0.0.1:8766',client=('192.0.2.1',12001))
        self.addCleanup(remote.close)
        self.assertEqual(remote.get('/api/v1/calendar/local').status_code,403)

    def test_saved_all_day_event_remains_date_only(self):
        CalendarCore(self.store).ingest('google','fixture','primary', [{
            'id':'all-day-fixture','title':'Date-only fixture',
            'start':'2026-11-05T00:00:00+02:00','end':'2026-11-06T00:00:00+02:00',
            'updated':'2026-11-04T00:00:00+02:00','all_day':True,'timezone':'Africa/Cairo'}])
        row=next(r for r in view(self.store)['details'] if r['title']=='Date-only fixture')
        self.assertTrue(row['date_only'])
        self.assertEqual(row['when'],'2026-11-05')

    def test_past_records_cannot_crowd_current_calendar_window(self):
        old=self.payload(start='2020-01-01T08:00:00Z',end='2020-01-01T09:00:00Z')
        self.cal.save(old)
        with self.store.connect() as db, db:
            columns=[r[1] for r in db.execute('PRAGMA table_info(local_commitments)')]
            row=dict(db.execute('SELECT * FROM local_commitments').fetchone())
            for i in range(501):
                row['id']=f'{i:032x}'
                db.execute('INSERT INTO local_commitments VALUES('+','.join('?' for _ in columns)+')',tuple(row[k] for k in columns))
        self.cal.save(self.payload(id='b'*32))
        self.assertEqual(CalendarCore(self.store).agenda()['items'][0]['event_id'],'b'*32)
        self.assertIn('Review fixture',view(self.store)['spoken_text'])
