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
        self.assertFalse(message["remote_images_blocked_by_default"])
        self.gmail.close.assert_called_once()

    def test_local_source_provenance_blocks_unknown_id(self):
        with self.assertRaisesRegex(MailError,"viewer_source_not_in_local_inbox"):
            allowed_source(self.store,self.cfg.account,"bb")
        with self.assertRaisesRegex(MailError,"viewer_invalid_message_id"):
            allowed_source(self.store,self.cfg.account,"../x")

    def test_original_message_reads_charset_and_attachment_backed_body(self):
        arabic = "صباح الخير، عندك اجتماع الساعة 4"
        raw = base64.urlsafe_b64encode(arabic.encode("windows-1256")).decode()
        original = self.fake_mail()
        original["payload"]["parts"] = [{
            "mimeType":"text/plain",
            "headers":[{"name":"Content-Type",
                        "value":"text/plain; charset=windows-1256"}],
            "body":{"size":len(arabic.encode("windows-1256")),
                    "attachmentId":"textBody123"},
        }]
        self.gmail.call.side_effect=[original,{"data":raw}]
        with patch("okal_core.mail.viewer.Gmail.open",return_value=self.gmail):
            out=read_native(self.store,"aa")
        self.assertEqual(out["text"],arabic)
        self.assertEqual(out["ai_summary"],"محتاج مراجعة")
        self.assertEqual(out["ai_category"],"action")
        self.assertEqual(out["ai_suggested_action"],"")
        self.assertEqual(self.gmail.call.call_count,2)

    def test_full_read_never_confuses_changed_native_subject(self):
        changed = self.fake_mail()
        changed["payload"]["headers"][0]["value"] = "Changed"
        self.gmail.call.return_value = changed
        with patch("okal_core.mail.viewer.Gmail.open",return_value=self.gmail):
            with self.assertRaisesRegex(MailError,"source_changed"):
                read_native(self.store,"aa")

    def test_cross_site_and_missing_confirmation_block_delete(self):
        with TestClient(create_app(self.store, require_read_key=False),
                        base_url="http://127.0.0.1:8766",
                        client=("127.0.0.1",12501)) as client:
            denied = client.post("/api/v1/mail/trash",
                headers={"Origin":"http://evil.example"},
                json={"ids":["aa"],"confirmed":True,
                      "approval_digest":"a"*64,
                      "confirmation_token":"x"*43})
            self.assertEqual(denied.status_code,403)
            missing = client.post("/api/v1/mail/trash",
                headers={"Origin":"http://127.0.0.1:8766",
                         "Sec-Fetch-Site":"same-origin"},
                json={"ids":["aa"],"confirmed":True,
                      "approval_digest":"a"*64})
            self.assertEqual(missing.status_code,400)

    def test_delete_requires_gmail_modify_even_without_password(self):
        cfg = self.cfg.model_copy(update={"trash_enabled":False})
        write_private(root(self.store)/"config.json",cfg.model_dump())
        headers={"Origin":"http://127.0.0.1:8766",
                 "Sec-Fetch-Site":"same-origin"}
        with TestClient(create_app(self.store, require_read_key=False),
                        base_url="http://127.0.0.1:8766",
                        client=("127.0.0.1",12501)) as client:
            out = client.post("/api/v1/mail/trash", headers=headers,
                json={"ids":["aa"],"confirmed":True,"approval_digest":"a"*64,
                      "confirmation_token":"x"*43})
            self.assertEqual(out.status_code,403)
            self.assertEqual(
                out.json()["detail"],"trash_permission_disabled_reauthorize"
            )

    def test_native_preview_confirm_button_delete_and_replay_rejected(self):
        native={"id":"aa","labelIds":["INBOX"],
                "payload":{"headers":[{"name":"Subject",
                                       "value":"Original <body>"}]}}
        self.gmail.call.return_value=native
        self.gmail.move_to_trash.return_value={"id":"aa","labelIds":["TRASH"]}
        headers={"Origin":"http://127.0.0.1:8766",
                 "Sec-Fetch-Site":"same-origin"}
        with patch("okal_core.mail.provider.Gmail.open",return_value=self.gmail):
            with TestClient(create_app(self.store,require_read_key=False),
                            base_url="http://127.0.0.1:8766",
                            client=("127.0.0.1",12501)) as client:
                preview = client.post("/api/v1/mail/trash/preview",
                    headers=headers,json={"ids":["aa"]})
                self.assertEqual(preview.status_code,200,preview.text)
                payload=preview.json()
                digest=payload["approval_digest"]
                ticket=payload["confirmation_token"]
                self.assertEqual(payload["items"][0]["subject"],"Original <body>")
                self.assertEqual(payload["confirmation_expires_seconds"],120)
                self.gmail.move_to_trash.assert_not_called()
                wrong = client.post("/api/v1/mail/trash",headers=headers,
                    json={"ids":["aa"],"confirmed":True,
                          "approval_digest":"f"*64,"confirmation_token":ticket})
                self.assertEqual(wrong.status_code,409)
                self.gmail.move_to_trash.assert_not_called()
                # Invalid approval consumes its one-time token: re-preview.
                fresh=client.post("/api/v1/mail/trash/preview",
                    headers=headers,json={"ids":["aa"]}).json()
                result=client.post("/api/v1/mail/trash",headers=headers,
                    json={"ids":["aa"],"confirmed":True,
                          "approval_digest":fresh["approval_digest"],
                          "confirmation_token":fresh["confirmation_token"]})
                self.assertEqual(result.status_code,200,result.text)
                self.assertEqual(result.json()["status"],"confirmed_trash")
                self.gmail.move_to_trash.assert_called_once_with("aa")
                replay=client.post("/api/v1/mail/trash",headers=headers,
                    json={"ids":["aa"],"confirmed":True,
                          "approval_digest":fresh["approval_digest"],
                          "confirmation_token":fresh["confirmation_token"]})
                self.assertEqual(replay.status_code,409)
                self.assertEqual(self.gmail.move_to_trash.call_count,1)

    def test_preview_ticket_expires_and_cannot_authorize_trash(self):
        now=[1800000000]
        self.store.clock=lambda:now[0]
        native={"id":"aa","labelIds":["INBOX"],"payload":{"headers":[
            {"name":"Subject","value":"Original <body>"}
        ]}}
        self.gmail.call.return_value=native
        headers={"Origin":"http://127.0.0.1:8766",
                 "Sec-Fetch-Site":"same-origin"}
        with patch("okal_core.mail.provider.Gmail.open",return_value=self.gmail):
            with TestClient(create_app(self.store,require_read_key=False),
                            base_url="http://127.0.0.1:8766",
                            client=("127.0.0.1",12501)) as client:
                preview=client.post("/api/v1/mail/trash/preview",
                    headers=headers,json={"ids":["aa"]}).json()
                now[0] += 121
                result=client.post("/api/v1/mail/trash",headers=headers,
                    json={"ids":["aa"],"confirmed":True,
                          "approval_digest":preview["approval_digest"],
                          "confirmation_token":preview["confirmation_token"]})
                self.assertEqual(result.status_code,409)
                self.assertEqual(result.json()["detail"],
                                 "trash_confirmation_expired_or_invalid")
                self.gmail.move_to_trash.assert_not_called()

    def test_protected_mode_rejects_unpaired_delete_even_with_preview_token(self):
        headers={"Origin":"http://127.0.0.1:8766",
                 "Sec-Fetch-Site":"same-origin"}
        with TestClient(create_app(self.store,require_read_key=True),
                        base_url="http://127.0.0.1:8766",
                        client=("127.0.0.1",12501)) as client:
            r=client.post("/api/v1/mail/trash",headers=headers,
                json={"ids":["aa"],"confirmed":True,
                      "approval_digest":"a"*64,"confirmation_token":"x"*43})
            self.assertEqual(r.status_code,401)




if __name__ == "__main__":
    unittest.main()
