import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("check-social-draft.py")


class SocialDraftChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "scripts").mkdir()
        shutil.copy2(SCRIPT, self.root / "scripts/check-social-draft.py")
        (self.root / "README.md").write_text("Okal is a local-first assistant.\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "add", "README.md"], check=True)
        self.draft = self.root / "draft.json"
        self.data = {
            "platform": "x",
            "text": "Okal is a local-first assistant.",
            "evidence": [{
                "claim": "Okal is a local-first assistant.",
                "source": "README.md",
                "quote": "Okal is a local-first assistant.",
            }],
        }

    def run_check(self):
        self.draft.write_text(json.dumps(self.data), encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(self.root / "scripts/check-social-draft.py"), str(self.draft)],
            capture_output=True, text=True,
        )

    def test_tracked_exact_evidence_needs_manual_review(self):
        result = self.run_check()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("MANUAL REVIEW REQUIRED", result.stdout)

    def test_invented_quote_is_rejected(self):
        self.data["evidence"][0]["quote"] = "Okal publishes via an API."
        result = self.run_check()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("quote is absent", result.stderr)

    def test_untracked_source_is_rejected(self):
        (self.root / "private.txt").write_text("secret", encoding="utf-8")
        self.data["evidence"][0].update(source="private.txt", quote="secret")
        result = self.run_check()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("not tracked", result.stderr)

    def test_path_escape_is_rejected(self):
        self.data["evidence"][0]["source"] = "../outside.txt"
        result = self.run_check()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("repository-relative", result.stderr)

    def test_claim_must_appear_in_post(self):
        self.data["evidence"][0]["claim"] = "The API published a post."
        result = self.run_check()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("claim is absent", result.stderr)


if __name__ == "__main__":
    unittest.main()
