"""Safe on-demand Gmail reader and explicit UI Trash approval tests."""
import base64
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from okal_core.api import create_app
from okal_core.mail.contracts import Config, Insight, MailError
from okal_core.mail.history import HistoryState
from okal_core.mail.private import root, write_private
from okal_core.mail.ui_trash_auth import configure_pin, verify_pin
from okal_core.mail.viewer import read_native, allowed_source
from okal_core.store import Store


def encoded(s):
    return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")


class InboxViewerDeleteTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = Store(Path(tmp.name) / "state", clock=lambda: 1800000000)
        self.cfg = Config(account="owner@example.com", model="local:tiny",
            model_digest="a"*64, local_only_confirmed=True,
            trash_enabled=True, sync_enabled=True)
        write_private(root(self.store) / "config.json", self.cfg.model_dump())
        HistoryState(self.store)
        self.meta = {"id":"aa", "subject":"Original <body>", "sender":"Updates",
            "received_ms":1800000000000, "labels":["INBOX"],
            "attachment_count":0}
        with self.store.connect() as db, db:
            db.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?)",
                       ("run-aa", "mail", "acct", "aa-source",
                        "digest", 1800000000, "succeeded"))
            db.execute("INSERT INTO mail_sync_insights VALUES(?,?,?,?,?)",
                       ("run-aa",self.cfg.account,"aa",json.dumps(self.meta),
                        Insight(source_id="aa",category="action",
                            summary="محتاج مراجعة",suggested_action="").model_dump_json()))
        self.gmail = MagicMock()
        self.gmail.service.users.return_value.messages.return_value.get.return_value = "request"
        self.gmail.service.users.return_value.messages.return_value.attachments.return_value.get.return_value = "attachment"
        self.gmail.close.return_value = None

    def fake_mail(self):
        return {"id":"aa", "sizeEstimate":2000,
                "payload":{"mimeType":"multipart/related",
                  "headers":[
                    {"name":"Subject","value":"Original <body>"},
                    {"name":"From","value":"Updates <updates@example.com>"},
                    {"name":"To","value":"owner@example.com"},
                    {"name":"Date","value":"Sun, 1 Nov 2026 10:00:00 +0200"},
                  ], "parts":[
                    {"mimeType":"text/html",
                     "body":{"data":encoded('<h1>Hello</h1><img src="cid:logo123"><script>alert(1)</script>')}},
                    {"mimeType":"image/png",
                     "headers":[{"name":"Content-ID","value":"<logo123>"}],
                     "body":{"data":base64.urlsafe_b64encode(b"PNG_SAFE_BYTES").decode()}}]}}

    def test_full_read_uses_native_gmail_and_embeds_cid_image(self):
        self.gmail.call.return_value = self.fake_mail()
        with patch("okal_core.mail.viewer.Gmail.open", return_value=self.gmail):
            message = read_native(self.store, "aa")
        self.assertEqual(message["subject"],"Original <body>")
        self.assertIn("data:image/png;base64,",message["html"])
        self.assertEqual(message["inline_images"],1)
        self.assertTrue(message["remote_images_blocked_by_default"])
        self.gmail.close.assert_called_once()

    def test_local_source_provenance_blocks_unknown_id(self):
        with self.assertRaisesRegex(MailError,"viewer_source_not_in_local_inbox"):
            allowed_source(self.store,self.cfg.account,"bb")
        with self.assertRaisesRegex(MailError,"viewer_invalid_message_id"):
            allowed_source(self.store,self.cfg.account,"../x")

    def test_full_read_never_confuses_changed_native_subject(self):
        changed = self.fake_mail()
        changed["payload"]["headers"][0]["value"] = "Changed"
        self.gmail.call.return_value = changed
        with patch("okal_core.mail.viewer.Gmail.open",return_value=self.gmail):
            with self.assertRaisesRegex(MailError,"source_changed"):
                read_native(self.store,"aa")

    def test_ui_pin_is_hashed_and_five_invalid_attempts_lock_it(self):
        configure_pin(self.store, "long-private-PIN-12345")
        private = (root(self.store)/"ui-trash-pin.json").read_text()
        self.assertNotIn("long-private-PIN-12345",private)
        for _ in range(5):
            with self.assertRaisesRegex(MailError,"pin_invalid"):
                verify_pin(self.store,"wrong")
        with self.assertRaisesRegex(MailError,"temporarily_locked"):
            verify_pin(self.store,"long-private-PIN-12345")

    def test_unconfigured_browser_post_denied_even_on_loopback(self):
        with TestClient(create_app(self.store,require_read_key=False),
                        base_url="http://127.0.0.1:8766",
                        client=("127.0.0.1",12501)) as client:
            r = client.post("/api/v1/mail/trash",
                headers={"Origin":"http://evil.example","Content-Type":"application/json"},
                json={"ids":["aa"],"pin":"foo","confirmed":True,
                      "approval_digest":"a"*64})
            self.assertEqual(r.status_code,403)
            r = client.post("/api/v1/mail/trash",
                headers={"Origin":"http://127.0.0.1:8766",
                         "Sec-Fetch-Site":"same-origin"},
                json={"ids":["aa"],"pin":"invalid","confirmed":True,
                      "approval_digest":"a"*64})
            self.assertEqual(r.status_code,429)

    def test_ui_preview_and_delete_are_separate_and_verified(self):
        configure_pin(self.store,"super-long-PIN-for-delete")
        native = {"id":"aa","labelIds":["INBOX"],
                  "payload":{"headers":[{"name":"Subject",
                                        "value":"Original <body>"}]}}
        self.gmail.call.return_value = native
        self.gmail.move_to_trash.return_value = {"id":"aa","labelIds":["TRASH"]}
        headers={"Origin":"http://127.0.0.1:8766",
                 "Sec-Fetch-Site":"same-origin"}
        with patch("okal_core.mail.provider.Gmail.open",return_value=self.gmail):
            with TestClient(create_app(self.store,require_read_key=False),
                            base_url="http://127.0.0.1:8766",
                            client=("127.0.0.1",12501)) as client:
                preview = client.post("/api/v1/mail/trash/preview",
                    headers=headers,json={"ids":["aa"]})
                self.assertEqual(preview.status_code,200,preview.text)
                digest = preview.json()["approval_digest"]
                self.assertEqual(preview.json()["items"][0]["subject"],"Original <body>")
                self.gmail.move_to_trash.assert_not_called()
                wrong = client.post("/api/v1/mail/trash",headers=headers,
                    json={"ids":["aa"],"pin":"super-long-PIN-for-delete",
                          "confirmed":True,"approval_digest":"f"*64})
                self.assertEqual(wrong.status_code,409)
                self.gmail.move_to_trash.assert_not_called()
                result=client.post("/api/v1/mail/trash",headers=headers,
                    json={"ids":["aa"],"pin":"super-long-PIN-for-delete",
                          "confirmed":True,"approval_digest":digest})
                self.assertEqual(result.status_code,200,result.text)
                self.assertEqual(result.json()["status"],"confirmed_trash")
                self.gmail.move_to_trash.assert_called_once_with("aa")


if __name__ == "__main__":
    unittest.main()
