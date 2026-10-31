"""One optional core-owned read scheduler; never invokes draft/send workflows."""

from datetime import datetime, timezone
import logging
import threading

from .contracts import MailError
from .private import config, locked, root
from .state import MailState

log = logging.getLogger("okal.mail")


def next_due(cfg, now):
    from apscheduler.triggers.cron import CronTrigger

    hour, minute = cfg.daily_at.split(":")
    value = CronTrigger(
        hour=int(hour), minute=int(minute), timezone=cfg.timezone
    ).get_next_fire_time(None, datetime.fromtimestamp(now, timezone.utc))
    return int(value.timestamp())


class Worker:
    def __init__(self, store, run=None, sync_run=None):
        self.store = store
        self.stop_event = threading.Event()
        self.run = run or self.live_run
        self.sync_run = sync_run or self.live_sync_run
        self.thread = None

    def live_run(self, cfg, start, end):
        from .inference import LocalModel
        from .provider import Gmail
        from .workflows import digest

        model = LocalModel(cfg)
        api = None
        try:
            api = Gmail.open(self.store, cfg)
            return digest(self.store, cfg, api, model, start, end)
        finally:
            model.close()
            if api:
                api.close()

    def live_sync_run(self, cfg):
        from .inference import LocalModel
        from .provider import Gmail
        from .history import run

        model = LocalModel(cfg)
        api = None
        try:
            api = Gmail.open(self.store, cfg)
            return run(self.store, cfg, api, model)
        finally:
            model.close()
            if api:
                api.close()

    def tick(self):
        if not (root(self.store) / "config.json").exists():
            return
        with locked(self.store):
            cfg = config(self.store)
            state = MailState(self.store)
            now = int(self.store.clock())
            if cfg.sync_enabled:
                from .history import HistoryState

                history = HistoryState(self.store)
                if history.due(cfg.account, now):
                    try:
                        self.sync_run(cfg)
                    except Exception:
                        # Unattended reads retry after the persisted attempt; no sending.
                        history.failure(cfg.account, "sync_failed_check_local_doctor")
                        log.warning("Gmail sync failed; inspect local mail sync status")
            signature = f"{cfg.account.casefold()}:{cfg.timezone}:{cfg.daily_at}"
            with self.store.connect() as db, db:
                previous = db.execute(
                    "SELECT value FROM mail_meta WHERE key='schedule'"
                ).fetchone()
                if not cfg.daily_at:
                    db.execute(
                        "DELETE FROM mail_meta WHERE key IN ('schedule','next_due','retry_after','attempts')"
                    )
                    return
                if previous is None or previous[0] != signature:
                    for key, value in {
                        "schedule": signature,
                        "next_due": str(next_due(cfg, now + 1)),
                        "attempts": "0",
                        "retry_after": "0",
                    }.items():
                        db.execute(
                            "INSERT OR REPLACE INTO mail_meta VALUES(?,?)", (key, value)
                        )
                    return  # Enabling/changing schedule never immediately reads mail.
                values = dict(db.execute("SELECT key,value FROM mail_meta"))
            due = int(values["next_due"])
            if now < max(due, int(values.get("retry_after", "0"))):
                return
            start = state.progress(cfg.account)
            start = start if start is not None else due - 86400
            if start >= now:
                return
            try:
                self.run(cfg, start, now)
            except Exception:
                attempts = min(int(values.get("attempts", "0")) + 1, 5)
                # Up to four quick retries, then cool down until the next daily slot.
                retry = (
                    now + min(60 * 2**attempts, 3600)
                    if attempts < 5
                    else next_due(cfg, now + 1)
                )
                with self.store.connect() as db, db:
                    db.execute(
                        "INSERT OR REPLACE INTO mail_meta VALUES('retry_after',?)",
                        (str(retry),),
                    )
                    db.execute(
                        "INSERT OR REPLACE INTO mail_meta VALUES('attempts',?)",
                        (str(attempts),),
                    )
                    db.execute(
                        "INSERT OR REPLACE INTO mail_meta VALUES('last_scheduler_result','failed_check_mail_jobs_or_doctor')"
                    )
                log.warning(
                    "mail schedule failed; inspect local mail status (no automatic sending)"
                )
                return
            with self.store.connect() as db, db:
                for key, value in {
                    "next_due": str(next_due(cfg, now + 1)),
                    "retry_after": "0",
                    "attempts": "0",
                    "last_scheduler_result": "succeeded",
                }.items():
                    db.execute(
                        "INSERT OR REPLACE INTO mail_meta VALUES(?,?)", (key, value)
                    )

    def loop(self):
        while not self.stop_event.is_set():
            try:
                self.tick()
            except MailError:
                pass  # Busy manual operation / invalid setup; never log private values.
            except Exception:
                log.warning("mail worker paused by setup error; use local doctor")
            self.stop_event.wait(30)

    def start(self):
        self.thread = threading.Thread(target=self.loop, name="okal-mail", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=2)
        # Process termination may interrupt read work; its checkpoint stays unchanged.
