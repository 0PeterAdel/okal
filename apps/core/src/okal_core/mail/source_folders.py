"""Conservative, read-only source/topic hints for locally cached Gmail records.

These are navigation labels, never sender authentication, model outputs,
Gmail labels, action permissions, or instructions from the email body.
Unclear GitHub notifications deliberately stay under "other".
"""

import re
from email.utils import parseaddr


def _from_domain(sender: str) -> str:
    address = parseaddr(sender if isinstance(sender, str) else "")[1]
    if address.count("@") != 1:
        return ""
    domain = address.rsplit("@", 1)[-1].lower().strip(".")
    return domain if re.fullmatch(r"[a-z0-9.-]+", domain) else ""


def _domain_is(domain: str, *owners: str) -> bool:
    return any(domain == owner or domain.endswith("." + owner)
               for owner in owners)


def classify_message(sender: str, subject: str) -> dict[str, str]:
    """Assign stable source/topic IDs using only saved sender/subject.

    This method does not contact Gmail, fetch body/attachments or write labels.
    The sender shown by Gmail is not cryptographically authenticated here.
    """
    domain = _from_domain(sender)
    title = subject if isinstance(subject, str) else ""
    if _domain_is(domain, "github.com"):
        source = "github"
    elif _domain_is(domain, "linkedin.com", "linkedinmail.com"):
        source = "linkedin"
    elif _domain_is(domain, "atlassian.net", "atlassian.com",
                    "jira.com", "bitbucket.org"):
        source = "atlassian"
    elif _domain_is(domain, "google.com", "gmail.com", "googlemail.com"):
        source = "google"
    elif _domain_is(domain, "cloudflare.com"):
        source = "cloudflare"
    elif _domain_is(domain, "khamsat.com", "mostaql.com", "upwork.com",
                    "fiverr.com", "freelancer.com"):
        source = "freelance"
    elif _domain_is(domain, "microsoft.com", "microsoftonline.com",
                    "outlook.com"):
        source = "microsoft"
    else:
        return {"source_group": "other", "source_type": "other"}

    if source != "github":
        return {"source_group": source, "source_type": "other"}

    # Order matters: a security alert mentioning a PR is still a security alert.
    rules = (
        ("security", r"\b(?:security alert|dependabot alert|vulnerabilit(?:y|ies)|"
                     r"secret scanning|code scanning|security advisory|"
                     r"compromised token)\b"),
        ("actions", r"\b(?:workflow(?: run)?|github actions?|run failed|"
                    r"run succeeded|check(?:s| suite| run)? failed|"
                    r"ci failed|pipeline|build failed|deployment failed)\b"),
        ("pull_requests", r"\b(?:pull requests?|pr)\s*#?\d{1,8}\b|"
                          r"\b(?:requested your review|review requested|"
                          r"reviewed your pull request|"
                          r"approved your pull request)\b"),
        ("issues", r"\bissue\s*#?\d{1,8}\b|"
                   r"\b(?:opened an issue|closed an issue|"
                   r"assigned you an issue|mentioned you in an issue)\b"),
        ("discussions", r"\bdiscussions?\s*#?\d{1,8}\b|"
                        r"\bnew discussion\b"),
        ("releases", r"\b(?:new release|release published|"
                     r"published a release|release v?\d)\b"),
        ("repositories", r"\b(?:repository invitation|"
                         r"invited you to collaborate|repository access|"
                         r"added you to a repository)\b"),
    )
    for topic, pattern in rules:
        if re.search(pattern, title, re.IGNORECASE):
            return {"source_group": source, "source_type": topic}
    return {"source_group": source, "source_type": "other"}
