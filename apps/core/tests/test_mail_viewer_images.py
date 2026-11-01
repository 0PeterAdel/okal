"""Synthetic viewer MIME images: no Gmail account, network or external pixels."""
import base64
from unittest import TestCase
from unittest.mock import MagicMock, patch

from okal_core.mail.viewer import read_native


def encoded(data):
    return base64.urlsafe_b64encode(data).decode("ascii")


def email_part(html, cid="logo@newsletter", location="https://assets.example/logo.png"):
    return {
        "id":"aa", "threadId":"bb", "sizeEstimate":12000,
        "labelIds":["INBOX"],
        "payload":{
            "mimeType":"multipart/related",
            "headers":[
                {"name":"Subject","value":"Visual newsletter"},
                {"name":"From","value":"newsletter@example.com"},
                {"name":"To","value":"owner@example.com"},
                {"name":"Date","value":"Sun, 1 Nov 2026 18:00:00 +0200"}
            ],
            "parts":[
                {"mimeType":"text/html", "body":{"size":len(html.encode()),
                 "data":encoded(html.encode())}},
                {"mimeType":"image/png", "headers":[
                    {"name":"Content-ID","value":"<"+cid+">"},
                    {"name":"Content-Location","value":location},
                ],"body":{"size":11,"data":encoded(b"syntheticPNG")}},
            ],
        }
    }


class ViewerImageTests(TestCase):
    def open(self, message):
        api=MagicMock()
        api.call.return_value=message
        api.close.return_value=None
        with patch("okal_core.mail.viewer.config",return_value=MagicMock(
            account="owner@example.com"
        )),patch("okal_core.mail.viewer.allowed_source",
             return_value={"id":"aa","subject":"Visual newsletter"}),patch(
            "okal_core.mail.viewer.saved_analysis",return_value={
                "ai_summary":"Test","ai_suggested_action":"",
                "ai_category":"information"
            }),patch("okal_core.mail.viewer.Gmail.open",return_value=api):
            result=read_native(object(),"aa")
        return result,api

    def test_unquoted_and_encoded_cid_images_resolve_locally(self):
        html=('<html><head><style>.logo{background-image:url(cid:logo%40newsletter)}</style>'
              '</head><body><img src=cid:logo%40newsletter>'
              '<img src="cid:logo@newsletter"></body></html>')
        result,api=self.open(email_part(html))
        self.assertIn("data:image/png;base64,",result["html"])
        self.assertNotIn("cid:",result["html"].lower())
        self.assertGreaterEqual(result["inline_images"],1)
        self.assertFalse(result["external_images_detected"])
        self.assertFalse(result["remote_images_blocked_by_default"])
        self.assertEqual(api.call.call_count,1)

    def test_content_location_image_is_embedded_before_remote_consent(self):
        html=('<html><body><img src="https://assets.example/logo.png">'
              '<img src="https://remote.example/tracker.jpg"></body></html>')
        result,api=self.open(email_part(html))
        self.assertNotIn('src="https://assets.example/logo.png"',result["html"])
        self.assertIn('src="data:image/png;base64,',result["html"])
        self.assertIn('src="https://remote.example/tracker.jpg"',result["html"])
        self.assertTrue(result["external_images_detected"])
        self.assertEqual(api.call.call_count,1)  # no external fetch

    def test_unsupported_gmail_image_does_not_load_remote_automatically(self):
        html='<img src="https://external.example/image.png">'
        result,api=self.open(email_part(html))
        self.assertFalse(result["remote_images_blocked_by_default"])
        self.assertIn("https://external.example/image.png",result["html"])
        self.assertEqual(api.call.call_count,1)

    def test_large_inline_image_reports_skipped_and_never_fetches(self):
        html='<img src="cid:big@newsletter">'
        msg=email_part(html)
        msg["payload"]["parts"][1]["headers"]=[
            {"name":"Content-ID","value":"<big@newsletter>"}
        ]
        msg["payload"]["parts"][1]["body"]={"size":2_000_000,
                                            "attachmentId":"not-fetched"}
        result,api=self.open(msg)
        self.assertEqual(result["skipped_inline_images"],1)
        self.assertIn("cid:big@newsletter",result["html"])
        self.assertEqual(api.call.call_count,1)

    def test_deferred_original_and_responsive_srcsets_are_recognized(self):
        # LinkedIn/Alison-style media may not have a normal src at all.
        # The client must offer opt-in; no remote host is fetched here.
        html=('<html><body><picture>'
              '<source data-srcset="https://cdn.example/a.jpg 1x, '
              'https://cdn.example/b.jpg 2x">'
              '<img data-original="https://cdn.example/hero.png?key=1&amp;size=2" '
              'src="data:image/gif;base64,AA=="></picture>'
              '<img data-lazy-src="https://cdn.example/avatar.jpg">'
              '</body></html>')
        result,api=self.open(email_part(html))
        self.assertTrue(result["external_images_detected"])
        self.assertIn("data-original=",result["html"])
        self.assertIn("data-srcset=",result["html"])
        self.assertEqual(api.call.call_count,1)  # never proxy remote pixels

    def test_html_body_is_kept_out_of_parent_dom_by_client_contract(self):
        # Only a string is returned. HTML is not parsed into the API DOM.
        html='<img src="cid:logo@newsletter" onerror="alert(1)">'
        result,_=self.open(email_part(html))
        self.assertIn('onerror="alert(1)"',result["html"])
        # JS never evaluates this string; it is rendered in sandbox="" with
        # script-src 'none'. See browser-side CSP and markup regression tests.
