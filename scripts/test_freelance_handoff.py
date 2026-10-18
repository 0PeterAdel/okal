"""The coordinator's Khamsat handoff reports receipts and cannot publish."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("freelance_handoff", Path(__file__).with_name("freelance-handoff.py"))
handoff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(handoff)


class HandoffTests(unittest.TestCase):
    def test_status_shows_pending_and_draft_without_private_text(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            url1 = "https://khamsat.com/community/requests/123-python"
            url2 = "https://khamsat.com/community/requests/124-ai"
            handoff.scout.save(state / "queue.json", {"checked_at": "today", "requests": [
                {"id": "123", "url": url1, "title": "Python", "description": "private detail"},
                {"id": "124", "url": url2, "title": "AI"}]})
            handoff.scout.save(state / "drafts.json", {"requests": {"124": {"text": "private draft"}}})
            handoff.scout.save(state / "replies.json", {"requests": {"123": {"status": "pending", "text": "private posted"}}})
            with patch.object(handoff.scout, "STATE", state), \
                 patch.object(handoff.control, "DRAFTS", state / "drafts.json"), \
                 patch.object(handoff.control.reply, "RECEIPTS", state / "replies.json"):
                report = handoff.status()
            self.assertEqual(report["pending_ids"], ["123"])
            self.assertEqual([row["status"] for row in report["requests"]], ["pending", "draft"])
            self.assertNotIn("private", json.dumps(report))

    def test_invalid_queue_id_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            handoff.scout.save(state / "queue.json", {"requests": [{
                "id": "999", "url": "https://khamsat.com/community/requests/123-python", "title": "Python"}]})
            with patch.object(handoff.scout, "STATE", state):
                with self.assertRaisesRegex(ValueError, "does not match"):
                    handoff.status()

    def test_cli_has_no_submission_action(self):
        source = Path(__file__).with_name("freelance-handoff.py").read_text()
        self.assertNotIn('add_parser("submit"', source)
        self.assertNotIn("reply.run(", source)


if __name__ == "__main__":
    unittest.main()
