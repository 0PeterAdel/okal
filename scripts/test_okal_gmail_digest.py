"""Offline Gmail pagination and progress tests."""

import base64
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch


spec = importlib.util.spec_from_file_location("gmail_digest", Path(__file__).with_name("okal-gmail-digest.py"))
digest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(digest)


class GmailDigestTests(unittest.TestCase):
    def test_prefers_plain_text_and_decodes_nested_payload(self):
        value = base64.urlsafe_b64encode("مرحبًا يا بيتر".encode()).decode()
        self.assertEqual(digest.body_text({"parts": [{"mimeType": "text/plain", "body": {"data": value}}]}),
                         "مرحبًا يا بيتر")

    def test_paginates_and_filters_precise_interval(self):
        api = MagicMock()
        messages = api.users.return_value.messages.return_value
        messages.list.return_value.execute.side_effect = [
            {"messages": [{"id": "1"}], "nextPageToken": "next"},
            {"messages": [{"id": "2"}]},
        ]
        messages.get.return_value.execute.side_effect = [
            {"internalDate": "2000", "payload": {"headers": [{"name": "Subject", "value": "hello"}]}},
            {"internalDate": "5000", "payload": {"headers": []}},
        ]
        result = digest.collect(api, datetime.fromtimestamp(1, timezone.utc),
                                datetime.fromtimestamp(3, timezone.utc))
        self.assertEqual([m["id"] for m in result], ["1"])
        self.assertEqual(messages.list.call_count, 2)

    def test_failed_summarizer_does_not_advance_state(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with patch.object(digest, "REPORTS", root), patch.object(digest, "STATE", root / "state.json"), \
                 patch.object(digest, "service", return_value=(object(), {"ollama_model": "local"})), \
                 patch.object(digest, "collect", return_value=[{"id": "1"}]), \
                 patch.object(digest, "summarize", side_effect=RuntimeError("model offline")):
                with self.assertRaises(RuntimeError):
                    digest.digest()
                self.assertFalse(digest.STATE.exists())

    def test_private_file_rejects_world_readable_token(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "token.json"
            path.write_text(json.dumps({"access_token": "test"}))
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                digest.private_file(path)


if __name__ == "__main__":
    unittest.main()
