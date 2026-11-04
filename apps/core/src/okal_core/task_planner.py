"""Local-first task planning, read-only agenda and optional desktop reminders.

All deadlines are explicitly owner-entered timezone-aware datetimes. No AI
guesses, Google Calendar calls, paid service or background Gmail modifications.
Each reminder is a *one-shot* local notification: claim before notifying,
and never repeat uncertain notify-send deliveries automatically.
"""
from datetime import datetime, timedelta
import re
import shutil
import subprocess
import threading
from zoneinfo import ZoneInfo

from .tasks import TaskBoard, TASK_STATES, ID_PATTERN, validated_title, validated_notes, due_timestamp

REMINDER_LEADS = (0, 5, 15, 60, 1440)
ZONE = ZoneInfo("Africa/Cairo")
SAFE_TITLE = re.compile(r"[\x00-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]")


def validate_lead(minutes, due_at):
    if minutes is None:
        return None
    if type(minutes) is not int or minutes not in REMINDER_LEADS:
        raise ValueError("invalid_local_reminder_lead")
    if due_at is None:
        raise ValueError("local_reminder_requires_owner_due_time")
    return minutes


class TaskPlanner:
    def __init__(self, store):
        self.store = store
        self.board = TaskBoard(store)

    def _init(self, db):
        self.board._init(db)
        db.execute("""CREATE TABLE IF NOT EXISTS task_reminders (
            task_id TEXT PRIMARY KEY REFERENCES local_tasks(id) ON DELETE CASCADE,
            lead_minutes INTEGER NOT NULL CHECK(lead_minutes IN (0,5,15,60,1440)),
            fire_at INTEGER NOT NULL,
            status TEXT NOT NULL CHECK(status IN
                ('scheduled','attempting','sent','failed','missed','cancelled')),
            updated_at INTEGER NOT NULL,
            notified_at INTEGER
        )""")
        db.execute("""CREATE INDEX IF NOT EXISTS task_reminders_due
            ON task_reminders(status,fire_at)""")

    def list(self, status="open", limit=100):
        result = self.board.list(status=status, limit=limit)
        if not self.board._exists():
            result["reminders"] = {"scheduled":0,"failed":0,"missed":0}
            return result
        with self.store.connect() as db:
            tables = {r[0] for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            reminders = {}
            if "task_reminders" in tables:
                reminders = {r["task_id"]: dict(r) for r in db.execute(
                    "SELECT task_id,lead_minutes,fire_at,status,notified_at "
                    "FROM task_reminders"
                )}
        for item in result["items"]:
            item["reminder"] = reminders.get(item["id"])
        result["reminders"] = {
            status_name:sum(x["status"]==status_name for x in reminders.values())
            for status_name in ("scheduled","sent","failed","missed")
        }
        result["local_reminder_backend"] = "notify-send_if_session_available"
        return result

    def agenda(self, days=7):
        if type(days) is not int or not 1 <= days <= 31:
            raise ValueError("invalid_agenda_window")
        rows = self.list("open",100)["items"]
        today = datetime.fromtimestamp(int(self.store.clock()),ZONE).date()
        groups = {"overdue":[],"today":[],"upcoming":[],"unscheduled":[]}
        for row in rows:
            due_at = row["due_at"]
            if due_at is None:
                group = "unscheduled"
            else:
                date = datetime.fromtimestamp(due_at,ZONE).date()
                if date < today:
                    group = "overdue"
                elif date == today:
                    group = "today"
                elif date < today+timedelta(days=days):
                    group = "upcoming"
                else:
                    continue
            groups[group].append(row)
        return {
            "timezone":"Africa/Cairo",
            "date":today.isoformat(),
            "window_days":days,
            "groups":groups,
            "counts":{k:len(v) for k,v in groups.items()},
            "data_source":"approved_local_tasks_only",
            "has_google_calendar":False,
            "external_writes":False,
        }

    def _save_reminder(self, db, task_id, due_at, minutes, now, was_open=True):
        self._init(db)
        if minutes is None:
            db.execute("DELETE FROM task_reminders WHERE task_id=?",(task_id,))
            return
        validate_lead(minutes,due_at)
        db.execute("""INSERT INTO task_reminders VALUES
            (?,?,?,'scheduled',?,NULL)
            ON CONFLICT(task_id) DO UPDATE SET
                lead_minutes=excluded.lead_minutes,fire_at=excluded.fire_at,
                status='scheduled',updated_at=excluded.updated_at,
                notified_at=NULL""", (task_id, minutes, due_at-minutes*60, now))

    def create(self, title, notes="", due=None, reminder_minutes=None):
        # Validate all fields BEFORE a task is inserted, so rejected reminder
        # settings never leave an unwanted partial task in the database.
        clean_title=validated_title(title)
        clean_notes=validated_notes(notes)
        when=due_timestamp(due)
        lead=validate_lead(reminder_minutes,when)
        result=self.board.add(clean_title,clean_notes,due)
        if lead is not None:
            now=int(self.store.clock())
            with self.store.connect() as db,db:
                db.execute("BEGIN IMMEDIATE")
                self._save_reminder(db,result["task_id"],when,lead,now)
        return {**result,"reminder_minutes":lead,"owner_confirmed":True}

    def from_mail(self,account,mid,title=None,due=None,reminder_minutes=None):
        # No model-inferred date or generated title. Owner explicitly clicks
        # Create Task; duplicated IDs remain idempotent.
        when=due_timestamp(due)
        lead=validate_lead(reminder_minutes,when)
        result=self.board.from_mail(account,mid,title,due,approve=True)
        if result["status"]!="already_recorded" and lead is not None:
            with self.store.connect() as db,db:
                db.execute("BEGIN IMMEDIATE")
                self._save_reminder(db,result["task_id"],when,lead,int(self.store.clock()))
        return {**result,"reminder_minutes":lead if result["status"]!="already_recorded" else None}

    def edit(self,task_id,title,notes,due,reminder_minutes=None):
        if not isinstance(task_id,str) or not ID_PATTERN.fullmatch(task_id):
            raise ValueError("invalid_task_id")
        clean_title=validated_title(title)
        clean_notes=validated_notes(notes)
        when=due_timestamp(due)
        lead=validate_lead(reminder_minutes,when)
        now=int(self.store.clock())
        with self.store.connect() as db,db:
            db.execute("BEGIN IMMEDIATE")
            self._init(db)
            updated=db.execute(
                "UPDATE local_tasks SET title=?,notes=?,due_at=?,updated_at=? "
                "WHERE id=? AND status='open'",
                (clean_title,clean_notes,when,now,task_id)
            ).rowcount
            if updated!=1:
                raise ValueError("task_not_open_or_not_found")
            self._save_reminder(db,task_id,when,lead,now)
        return {"task_id":task_id,"status":"open","updated":True,
                "reminder_minutes":lead,"external_writes":False}

    def transition(self,task_id,status):
        if not isinstance(task_id,str) or not ID_PATTERN.fullmatch(task_id):
            raise ValueError("invalid_task_id")
        if status not in {"done","dismissed","open"}:
            raise ValueError("invalid_task_transition")
        now=int(self.store.clock())
        with self.store.connect() as db,db:
            db.execute("BEGIN IMMEDIATE")
            self._init(db)
            row=db.execute(
                "SELECT status FROM local_tasks WHERE id=?",(task_id,)
            ).fetchone()
            if row is None:
                raise ValueError("task_not_found")
            if row["status"]==status:
                return {"task_id":task_id,"status":status,"replayed":True}
            if status=="open" and row["status"] not in {"done","dismissed"}:
                raise ValueError("invalid_task_transition")
            if status!="open" and row["status"]!="open":
                raise ValueError("task_not_open")
            db.execute(
                "UPDATE local_tasks SET status=?,updated_at=? WHERE id=?",
                (status,now,task_id)
            )
            # Restoring a task does not reactivate an expired reminder; owner
            # must explicitly edit and schedule a new notification.
            if status!="open":
                db.execute("UPDATE task_reminders SET status='cancelled',"
                           "updated_at=? WHERE task_id=? AND status='scheduled'",
                           (now,task_id))
        return {"task_id":task_id,"status":status,"replayed":False}

    def claim_due(self,limit=10):
        """Claim reminders transactionally before external desktop notification."""
        now=int(self.store.clock())
        with self.store.connect() as db,db:
            db.execute("BEGIN IMMEDIATE")
            self._init(db)
            rows=db.execute("""SELECT r.task_id,t.title,r.fire_at,r.lead_minutes
                FROM task_reminders r JOIN local_tasks t ON t.id=r.task_id
                WHERE t.status='open' AND r.status='scheduled' AND r.fire_at<=?
                ORDER BY r.fire_at ASC LIMIT ?""",(now,limit)).fetchall()
            events=[]
            for row in rows:
                status="missed" if now-row["fire_at"]>900 else "attempting"
                count=db.execute(
                    "UPDATE task_reminders SET status=?,updated_at=? "
                    "WHERE task_id=? AND status='scheduled'",
                    (status,now,row["task_id"])
                ).rowcount
                if count==1 and status=="attempting":
                    events.append(dict(row))
        return events

    def finish_notification(self,task_id,success):
        if not isinstance(task_id,str) or not ID_PATTERN.fullmatch(task_id):
            raise ValueError("invalid_task_id")
        now=int(self.store.clock())
        with self.store.connect() as db,db:
            db.execute(
                "UPDATE task_reminders SET status=?,updated_at=?,notified_at=? "
                "WHERE task_id=? AND status='attempting'",
                ("sent" if success else "failed",now,now if success else None,task_id)
            )


def safe_notification_text(value):
    return SAFE_TITLE.sub(" ",str(value))[:115].strip()


def desktop_notify(title, lead_minutes):
    exe=shutil.which("notify-send")
    if not exe:
        return False
    heading="OKAL — تذكير بالمهمة"
    body=safe_notification_text(title)
    suffix=("الموعد الآن" if lead_minutes==0 else
            "متبقي " + str(lead_minutes) + " دقيقة" if lead_minutes<60 else
            "متبقي " + str(lead_minutes//60) + " ساعة")
    try:
        result=subprocess.run(
            [exe,"--app-name=OKAL","--expire-time=12000",
             heading,body+" · "+suffix],
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,timeout=4,check=False
        )
        return result.returncode==0
    except (OSError,subprocess.TimeoutExpired):
        return False


class ReminderWorker:
    def __init__(self,store,notify=desktop_notify,interval=30):
        self.store=store
        self.notify=notify
        self.interval=interval
        self.stop_event=threading.Event()
        self.thread=None

    def tick(self):
        planner=TaskPlanner(self.store)
        for event in planner.claim_due():
            ok=False
            try:
                ok=bool(self.notify(event["title"],event["lead_minutes"]))
            except Exception:
                ok=False
            planner.finish_notification(event["task_id"],ok)
        from .local_calendar import LocalCalendar
        local = LocalCalendar(self.store)
        for event in local.claim_due():
            try:
                ok = bool(self.notify(event["title"], event["reminder_minutes"]))
            except Exception:
                ok = False
            local.finish_notification(event["id"], event["revision"], ok)

    def loop(self):
        while not self.stop_event.is_set():
            try:
                self.tick()
            except Exception:
                # Never leak private task text into logs or interrupt Core.
                pass
            self.stop_event.wait(self.interval)

    def start(self):
        self.thread=threading.Thread(target=self.loop,name="okal-reminders",
                                     daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=2)
