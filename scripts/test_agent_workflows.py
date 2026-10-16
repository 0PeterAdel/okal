"""Boundary tests for the social handoff and fact-locked job packet."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


def load(filename):
    spec = importlib.util.spec_from_file_location(filename.replace("-", "_"), Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


postiz = load("postiz-x-draft.py")
career = load("prepare-job-application.py")


class DraftHandoff(unittest.TestCase):
    def test_postiz_receives_unpublished_draft_only(self):
        data = postiz.payload("Source-backed draft", "x-channel-1")

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self, *_):
                return b'[{"postId":"p123"}]'

        with patch.object(postiz, "urlopen", return_value=Response()) as send:
            result = postiz.create_draft("https://api.postiz.com/public/v1/posts", "secret", data)
        body = json.loads(send.call_args.args[0].data)
        self.assertEqual("draft", body["type"])
        self.assertEqual("x", body["posts"][0]["settings"]["__type"])
        self.assertEqual("p123", result[0]["postId"])

    def test_private_or_insecure_endpoint_is_refused(self):
        for value in ("http://postiz.example/api", "file:///tmp/postiz", "https://token@postiz.example/api"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                postiz.endpoint(value)


class CareerPacket(unittest.TestCase):
    def setUp(self):
        self.profile = {
            "schema_version": "okal.owner.v1", "reviewed_at": "2026-10-12",
            "identity": {"name": "Test Candidate", "email": "candidate@example.invalid"},
            "facts": [
                {"id": "project", "section": "Projects", "text": "Built a Python dashboard",
                 "source": "Portfolio entry A", "verified": True},
                {"id": "rumor", "section": "Awards", "text": "Won a major prize",
                 "source": "Unconfirmed note", "verified": False},
            ],
        }
        self.job = {"title": "Python Developer", "company": "Sample Co",
                    "url": "https://www.linkedin.com/jobs/view/123/",
                    "description": "Python dashboard experience required"}

    def test_unverified_claim_never_enters_automatic_cv(self):
        _, selected = career.prepare(self.profile, self.job)
        self.assertEqual(["project"], [x["id"] for x in selected])
        self.job["fact_ids"] = ["rumor"]
        with self.assertRaisesRegex(ValueError, "verified"):
            career.prepare(self.profile, self.job)

    def test_verified_source_and_reviewed_identity_required(self):
        self.profile["reviewed_at"] = ""
        with self.assertRaisesRegex(ValueError, "reviewed_at"):
            career.prepare(self.profile, self.job)
        self.profile["reviewed_at"] = "2026-10-12"
        self.profile["facts"][0]["source"] = ""
        with self.assertRaisesRegex(ValueError, "source"):
            career.prepare(self.profile, self.job)

    def test_pdf_contains_only_selected_fact(self):
        try:
            import reportlab  # noqa: F401
        except ImportError:
            self.skipTest("Optional reportlab dependency is absent")
        identity, selected = career.prepare(self.profile, self.job)
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "cv.pdf"
            career.render_pdf(pdf, identity, self.job, selected)
            self.assertTrue(pdf.read_bytes().startswith(b"%PDF"))
            self.assertGreater(pdf.stat().st_size, 500)


if __name__ == "__main__":
    unittest.main()
