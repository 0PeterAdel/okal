"""Offline checks for the real publishing boundary and duplicate guard."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("x_publish", Path(__file__).with_name("okal-x-publish.py"))
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)


class XPublisherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = patch.object(publisher, "CONFIG", self.root / "config.json")
        self.keys = patch.object(publisher, "KEYS", self.root / "keys.json")
        self.state = patch.object(publisher, "STATE", self.root / "state.json")
        for item in (self.config, self.keys, self.state):
            item.start()
            self.addCleanup(item.stop)
        publisher.atomic_json(publisher.CONFIG, {"enabled": True, "facts": [{"text": "fact"}]})
        publisher.atomic_json(publisher.KEYS, {"consumer_key": "ck", "consumer_secret": "cs",
                                               "access_token": "at", "access_token_secret": "as"})

    def test_auth_is_user_context_oauth_and_has_signature(self):
        header = publisher.oauth_header(publisher.private_json(publisher.KEYS), "POST",
                                        publisher.POST_URL, nonce="n", timestamp=123)
        self.assertIn('oauth_token="at"', header)
        self.assertIn('oauth_signature="', header)
        self.assertNotIn("cs", header)

    def test_real_publish_once_and_receipt(self):
        with patch.object(publisher, "generate", return_value="fact — tip"), \
             patch.object(publisher, "publish", return_value="123456") as send:
            self.assertIn("123456", publisher.run())
            self.assertEqual(send.call_count, 1)
            self.assertEqual(publisher.private_json(publisher.STATE)["status"], "published")
            with self.assertRaisesRegex(ValueError, "already been attempted"):
                publisher.run()

    def test_ambiguous_error_leaves_pending_receipt(self):
        with patch.object(publisher, "generate", return_value="fact"), \
             patch.object(publisher, "publish", side_effect=RuntimeError("network uncertain")):
            with self.assertRaises(RuntimeError):
                publisher.run()
        self.assertEqual(publisher.private_json(publisher.STATE)["status"], "pending")

    def test_disabled_or_missing_credentials_cannot_publish(self):
        publisher.atomic_json(publisher.CONFIG, {"enabled": False, "facts": [{"text": "fact"}]})
        with patch.object(publisher, "publish") as send:
            with self.assertRaisesRegex(ValueError, "enabled"):
                publisher.run()
            send.assert_not_called()

    def test_dry_run_does_not_mark_today(self):
        with patch.object(publisher, "generate", return_value="fact"), \
             patch.object(publisher, "publish") as send:
            self.assertEqual(publisher.run(dry_run=True), "fact")
            send.assert_not_called()
        self.assertFalse(publisher.STATE.exists())


if __name__ == "__main__":
    unittest.main()
