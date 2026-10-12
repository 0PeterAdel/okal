"""Offline checks for public job feeds and the owner-saved LinkedIn handoff."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).with_name("find-job-offers.py")
spec = importlib.util.spec_from_file_location("job_offers", SCRIPT)
offers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(offers)


class JobDiscoveryTests(unittest.TestCase):
    def test_himalayas_location_restrictions_and_dates(self):
        job = dict(title="Python Developer", companyName="Example",
                   guid="https://himalayas.app/companies/example/jobs/python-1",
                   applicationLink="https://example.com/apply/1",
                   locationRestrictions=["Germany"], pubDate=1791763200)
        self.assertIsNone(offers.normalize_himalayas(job))
        job["locationRestrictions"] = [{"alpha2": "EG", "name": "Egypt"}]
        result = offers.normalize_himalayas(job)
        self.assertIn("Egypt", result["location"])
        self.assertEqual(result["source_url"], job["guid"])
        self.assertRegex(result["published"], r"^\d{4}-\d{2}-\d{2}$")
        job["locationRestrictions"] = []
        self.assertIn("worldwide", offers.normalize_himalayas(job)["location"])

    def test_remotive_source_and_senior_filter(self):
        job = dict(id=1, title="Senior Python Developer", company_name="Example",
                   url="https://remotive.com/remote-jobs/software-dev/test-1",
                   candidate_required_location="Worldwide", description="<p>Python</p>")
        normalized = offers.normalize_remotive(job)
        self.assertEqual(normalized["description"], "Python")
        self.assertIsNone(offers.score_job(normalized, ["Python Developer"]))
        job["title"] = "Junior Python Developer"
        self.assertGreater(offers.score_job(offers.normalize_remotive(job), ["Python Developer"])["rank_score"], 0)
        job["url"] = "https://bad.example/remote-jobs/software-dev/test-1"
        self.assertIsNone(offers.normalize_remotive(job))

    def test_country_allowlist_and_generic_engineer_do_not_make_a_lead(self):
        base = dict(id=1, title="Software Engineer / AI Code Trainer (Python)",
                    company_name="Example", description="Python",
                    url="https://remotive.com/remote-jobs/software-dev/example-1")
        restricted = dict(base, candidate_required_location="USA, UK, India, Pakistan")
        self.assertIsNone(offers.normalize_remotive(restricted))
        excluded = dict(base, candidate_required_location="Worldwide excluding Egypt")
        self.assertIsNone(offers.normalize_remotive(excluded))
        unknown = dict(base, candidate_required_location="")
        self.assertIsNone(offers.normalize_remotive(unknown))
        worldwide = dict(base, candidate_required_location="Worldwide")
        self.assertIsNotNone(offers.score_job(offers.normalize_remotive(worldwide),
                                              ["Python Developer", "AI Engineer"]))
        desk = dict(worldwide, title="Tier III Service Desk Engineer")
        self.assertIsNone(offers.score_job(offers.normalize_remotive(desk),
                                            ["Python Developer", "AI Engineer"]))

    def test_himalayas_metadata_seniority_blocks_staff_role(self):
        job = offers.normalize_himalayas(dict(
            title="AI Engineer", companyName="Example", seniority=["Staff"],
            applicationLink="https://himalayas.app/companies/example/jobs/ai-engineer",
            locationRestrictions=[]))
        self.assertIsNone(offers.score_job(job, ["AI Engineer"]))

    def test_linkedin_only_owner_saved_real_job_urls(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "links.json"
            job = {"url": "https://www.linkedin.com/jobs/view/12345/",
                   "title": "AI Engineer", "company": "Example",
                   "description": "<p>Python and AI</p>"}
            path.write_text(json.dumps({"jobs": [job]}))
            self.assertEqual(offers.load_linkedin(path)[0]["description"], "Python and AI")
            for bad in ("https://linkedln.com/jobs/view/12345/",
                        "https://www.linkedin.com/jobs/view/12345/other"):
                job["url"] = bad
                path.write_text(json.dumps({"jobs": [job]}))
                with self.assertRaises(ValueError):
                    offers.load_linkedin(path)

    def test_offline_pipeline_and_private_review_report(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            profile = root / "owner.json"
            linkedin = root / "linkedin.json"
            profile.write_text(json.dumps({"preferences": {
                "job_titles": ["Python Developer", "AI Engineer"],
                "job_search_queries": {"himalayas": ["python"], "remotive": []}}}))
            linkedin.write_text(json.dumps({"jobs": [{
                "url": "https://www.linkedin.com/jobs/view/123/",
                "title": "Python Developer", "company": "Example", "description": "Python"}]}))
            url = offers.HIMALAYAS + "?q=python&sort=recent&page=1"
            key = offers.hashlib.sha256(url.encode()).hexdigest() + ".json"
            cache = root / "cache"
            cache.mkdir()
            (cache / key).write_text(json.dumps({"jobs": [
                {"guid": "h1", "title": "AI Engineer", "companyName": "Test",
                 "applicationLink": "https://example.com/apply/1", "locationRestrictions": []}]}))
            args = ["--profile", str(profile), "--linkedin-file", str(linkedin),
                    "--cache-dir", str(cache), "--out-dir", str(root / "out"), "--offline"]
            with patch.object(offers, "urlopen", side_effect=AssertionError("network used")):
                self.assertEqual(offers.main(args), 0)
            report = json.loads((root / "out/leads.json").read_text())
            self.assertEqual(len(report["leads"]), 2)
            self.assertEqual(report["submission"], "not_submitted")
            self.assertEqual((root / "out/leads.json").stat().st_mode & 0o777, 0o600)
            self.assertIn("Himalayas", (root / "out/leads.md").read_text())

    def test_rejects_bad_queries_without_network(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            profile = root / "owner.json"
            profile.write_text(json.dumps({"preferences": {
                "job_titles": ["Python Developer"],
                "job_search_queries": {"himalayas": "python", "remotive": []}}}))
            with patch.object(offers, "urlopen", side_effect=AssertionError("network used")):
                self.assertEqual(offers.main(["--profile", str(profile), "--out-dir", str(root)]), 1)


if __name__ == "__main__":
    unittest.main()
