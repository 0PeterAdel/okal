"""Opt-in, best-effort Gmail desktop alerts with no private message content."""
from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

from okal_core.store import Store
from okal_core.mail.contracts import Config
from okal_core.mail.desktop_alerts import (
    claim_new_mail_notice, maybe_notify, desktop_new_mail_notice,
)
from okal_core.mail.scheduler import Worker
from okal_core.mail.private import root, write_private, config
from okal_core.mail.history import HistoryState
from okal_core.mail.cli import main


class DesktopAlertTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.now = [1800000000]
        self.store = Store(Path(tmp.name)/"private",clock=lambda:self.now[0])
        self.cfg=Config(account="owner@example.com",model="local:test",
                        model_digest="a"*64,sync_enabled=True,
                        notify_new_mail=True)

    def result(self, **kwargs):
        return {"status":"history_delta","processed":2,
                "run_id":"a"*32,**kwargs}

    def test_opt_in_only_and_exactly_once_across_store_reopen(self):
        called=[]
        data=self.result()
        self.assertFalse(maybe_notify(self.store,data,enabled=False,
                                       deliver=called.append))
        self.assertEqual(called,[])
        self.assertTrue(maybe_notify(self.store,data,enabled=True,
                                      deliver=lambda n:called.append(n) or True))
        self.assertEqual(called,[2])
        self.assertFalse(maybe_notify(Store(self.store.directory,
                              clock=lambda:self.now[0]),data,enabled=True,
                              deliver=lambda _:called.append(99)))
        self.assertEqual(called,[2])

    def test_no_notifications_for_initial_backfill_and_non_new_events(self):
        for row in (
            self.result(status="initial_24h_backfill"),
            self.result(status="history_expired_visible_mail_backfill"),
            self.result(processed=0),
            self.result(processed=True),
            self.result(run_id=None),
            self.result(run_id="../../secret"),
            {"status":"history_delta","processed":3},
            None,
        ):
            with self.subTest(row=row):
                self.assertFalse(claim_new_mail_notice(self.store,row))
        with self.store.connect() as db:
            self.assertIsNone(db.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE name='mail_desktop_alert_claims'").fetchone())

    def test_failed_notification_is_not_repeated_on_restarted_core(self):
        def broken(_):
            raise RuntimeError("private desktop unavailable")
        self.assertFalse(maybe_notify(self.store,self.result(),enabled=True,
                                      deliver=broken))
        self.assertFalse(maybe_notify(self.store,self.result(),enabled=True,
                                      deliver=lambda _:True))

    def test_os_notification_is_generic_count_only(self):
        with patch("okal_core.mail.desktop_alerts.shutil.which",
                   return_value="/usr/bin/notify-send"),patch(
            "okal_core.mail.desktop_alerts.subprocess.run",
            return_value=Mock(returncode=0)) as runner:
            self.assertTrue(desktop_new_mail_notice(2))
        args=runner.call_args.args[0]
        self.assertIn("OKAL",str(args))
        self.assertIn("2",str(args))
        self.assertNotIn("owner@example.com",str(args))
        self.assertNotIn("subject",str(args).lower())
        self.assertNotIn("gmail.com",str(args))
        self.assertNotIn("shell",str(runner.call_args.kwargs))
        self.assertEqual(runner.call_args.kwargs["timeout"],3)
        self.assertFalse(desktop_new_mail_notice(0))

    def test_scheduler_notifies_only_for_new_incremental_run(self):
        write_private(root(self.store)/"config.json",self.cfg.model_dump())
        HistoryState(self.store).commit(
            self.cfg.account,None,"100","initial_24h_backfill",[],"")
        calls=[]
        def run_sync(cfg):
            current=HistoryState(self.store).current(cfg.account)
            HistoryState(self.store).commit(
                cfg.account,current["cursor"],"110","history_delta",[],"")
            return self.result(run_id="b"*32)
        worker=Worker(self.store,sync_run=run_sync,
                      desktop_alert=lambda n:calls.append(n) or True)
        self.now[0]+=301
        worker.tick()
        worker.tick()
        self.assertEqual(calls,[2])

    def test_cli_toggle_does_not_modify_gmail_credentials_or_send(self):
        write_private(root(self.store)/"config.json",
                      self.cfg.model_copy(update={"notify_new_mail":False}).model_dump())
        output=io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(self.store,["notifications","on"]),0)
        self.assertTrue(config(self.store).notify_new_mail)
        self.assertFalse(config(self.store).send_enabled)
        self.assertNotIn("owner@example.com",output.getvalue())
        self.assertIn("true",output.getvalue().lower())
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(self.store,["notifications","off"]),0)
        self.assertFalse(config(self.store).notify_new_mail)


if __name__=="__main__":
    unittest.main()
