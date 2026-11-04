"""Read-only Gmail navigation labels must not guess providers from lookalikes."""

import unittest

from okal_core.mail.source_folders import classify_message


class MailSourceFoldersTests(unittest.TestCase):
    def check(self, sender, subject, group, kind):
        self.assertEqual(
            classify_message(sender, subject),
            {"source_group": group, "source_type": kind},
        )

    def test_github_topics(self):
        sender = "GitHub <notifications@github.com>"
        self.check(sender, "[0PeterAdel/okal] PR #84 updated",
                   "github", "pull_requests")
        self.check(sender, "[0PeterAdel/okal] Pull Request #12 reviewed",
                   "github", "pull_requests")
        self.check(sender, "[0PeterAdel/okal] Issue #12 updated",
                   "github", "issues")
        self.check(sender, "[0PeterAdel/okal] Workflow run failed",
                   "github", "actions")
        self.check(sender, "[0PeterAdel/okal] Dependabot alert",
                   "github", "security")
        self.check(sender, "[0PeterAdel/okal] New discussion #5",
                   "github", "discussions")
        self.check(sender, "[0PeterAdel/okal] Release published: v1",
                   "github", "releases")
        self.check(sender, "[0PeterAdel/okal] Repository invitation",
                   "github", "repositories")

    def test_ambiguous_issue_number_never_guessed_to_be_pr(self):
        self.check("notifications@github.com",
                   "[0PeterAdel/okal] Fix bad sync (#52)",
                   "github", "other")

    def test_security_alert_wins_over_pr_keyword(self):
        self.check("notifications@github.com",
                   "Security alert on PR #52", "github", "security")

    def test_sender_domains_are_exact_boundaries(self):
        self.check("Alert <notifications@github.com.attacker.test>",
                   "PR #123", "other", "other")
        self.check("notifications@mygithub.com", "PR #123", "other", "other")
        self.check("notifications@github.com", "PR #123",
                   "github", "pull_requests")
        self.check("alerts@sub.github.com", "Issue #15",
                   "github", "issues")
        self.check("Fake github.com <alert@evil.example>", "PR #5",
                   "other", "other")
        self.check("GitHub", "PR #5", "other", "other")

    def test_other_sources_are_grouped_not_modified(self):
        for sender, group in (
            ("updates@linkedin.com", "linkedin"),
            ("notify@linkedinmail.com", "linkedin"),
            ("jira@acme.atlassian.net", "atlassian"),
            ("calendar-notification@google.com", "google"),
            ("alerts@cloudflare.com", "cloudflare"),
            ("alerts@mostaql.com", "freelance"),
            ("jobs@upwork.com", "freelance"),
            ("hello@microsoft.com", "microsoft"),
            ("hello@example.org", "other"),
        ):
            with self.subTest(sender=sender):
                self.check(sender, "PR #99", group, "other")

    def test_non_strings_do_not_create_false_source(self):
        self.check(None, None, "other", "other")


if __name__ == "__main__":
    unittest.main()
