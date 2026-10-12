#!/usr/bin/env python3
"""Collect reviewable job leads from public APIs and owner-saved LinkedIn links.

No browser session, LinkedIn scraping, application submission, or CV generation.
"""

import argparse
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


HIMALAYAS = "https://himalayas.app/jobs/api/search"
REMOTIVE = "https://remotive.com/api/remote-jobs"
CACHE_SECONDS = 24 * 60 * 60
MAX_BYTES = 8 * 1024 * 1024
SENIOR_TITLE = re.compile(r"\b(senior|sr\.?|principal|staff|lead|director|head of|manager)\b", re.I)
STOPWORDS = {"and", "the", "for", "of", "applied", "junior", "entry", "level"}


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def get_text(self):
        return re.sub(r"\s+", " ", unescape(" ".join(self.parts))).strip()


def clean_html(value):
    parser = PlainText()
    parser.feed(str(value or ""))
    return parser.get_text()


def https_url(value, host=None):
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.hostname) and (
        host is None or parsed.hostname == host or parsed.hostname.endswith("." + host)
    )


def date_string(value):
    if isinstance(value, (int, float)):
        # The published API has returned seconds and its docs also describe milliseconds.
        seconds = value / 1000 if value > 10**11 else value
        return datetime.fromtimestamp(seconds, timezone.utc).date().isoformat()
    if isinstance(value, str):
        return value[:10]
    return ""


def normalize_himalayas(job):
    if not isinstance(job, dict) or not https_url(job.get("applicationLink")):
        return None
    location = job.get("locationRestrictions")
    if not isinstance(location, list):
        location_status = "location unknown; check listing"
    elif not location:
        location_status = "worldwide (check timezone and listing)"
    else:
        countries = {
            (c.get("alpha2") or c.get("name") or "").casefold()
            if isinstance(c, dict) else str(c).casefold()
            for c in location
        }
        if not countries.intersection({"eg", "egypt"}):
            return None  # Explicitly excludes Egypt.
        location_status = "Egypt listed (check timezone and listing)"
    title, company = job.get("title"), job.get("companyName")
    if not isinstance(title, str) or not isinstance(company, str) or not title.strip() or not company.strip():
        return None
    return {
        "source": "Himalayas", "source_url": (
            job.get("guid") if https_url(job.get("guid"), "himalayas.app")
            else "https://himalayas.app"
        ),
        "id": str(job.get("guid") or job["applicationLink"]), "title": title.strip(),
        "company": company.strip(), "url": job["applicationLink"],
        "description": clean_html(job.get("description") or job.get("excerpt")),
        "published": date_string(job.get("pubDate")),
        "location": location_status, "seniority": job.get("seniority") or [],
        "employment_type": job.get("employmentType") or "",
    }


def normalize_remotive(job):
    if not isinstance(job, dict) or not https_url(job.get("url"), "remotive.com"):
        return None
    title, company = job.get("title"), job.get("company_name")
    if not isinstance(title, str) or not isinstance(company, str) or not title.strip() or not company.strip():
        return None
    required = job.get("candidate_required_location") or "not specified"
    location = (
        "worldwide (check listing)" if str(required).casefold() in {"worldwide", "anywhere"}
        else str(required) + " (check eligibility)"
    )
    return {
        "source": "Remotive", "source_url": job["url"],
        "id": str(job.get("id") or job["url"]), "title": title.strip(),
        "company": company.strip(), "url": job["url"],
        "description": clean_html(job.get("description")),
        "published": date_string(job.get("publication_date")),
        "location": location, "seniority": [], "employment_type": job.get("job_type") or "",
    }


def load_linkedin(path):
    if not path or not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        raise ValueError("LinkedIn links file needs a jobs array")
    jobs = []
    for job in data["jobs"]:
        if not isinstance(job, dict):
            raise ValueError("Every saved LinkedIn job must be an object")
        url = job.get("url")
        if not https_url(url, "linkedin.com") or not re.fullmatch(r"/jobs/view/\d+/?", urlparse(url).path):
            raise ValueError("LinkedIn job URL must be an HTTPS /jobs/view/<id> link")
        if not all(isinstance(job.get(key), str) and job[key].strip()
                   for key in ("title", "company", "description")):
            raise ValueError("Each LinkedIn job needs its actual title, company and description")
        jobs.append({
            "source": "LinkedIn (owner saved)", "source_url": "https://www.linkedin.com/jobs/",
            "id": urlparse(url).path.rstrip("/").split("/")[-1],
            "title": job["title"].strip(), "company": job["company"].strip(), "url": url,
            "description": clean_html(job["description"]),
            "published": date_string(job.get("published")),
            "location": "check original listing", "seniority": [],
            "employment_type": job.get("employment_type") or "",
        })
    return jobs


def read_cached_json(url, cache_dir, offline=False):
    key = hashlib.sha256(url.encode()).hexdigest()
    path = cache_dir / (key + ".json")
    if path.is_file() and (offline or time.time() - path.stat().st_mtime < CACHE_SECONDS):
        return json.loads(path.read_text(encoding="utf-8")), "cache"
    if offline:
        raise ValueError("No cached response for " + urlparse(url).hostname)
    request = Request(url, headers={"User-Agent": "OkalCareer/0.1 (personal job search)"})
    with urlopen(request, timeout=20) as response:
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Job API response exceeds 8 MiB")
    data = json.loads(raw)
    write_private(path, json.dumps(data, ensure_ascii=False))
    return data, "network"


def write_private(path, content):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    old_mask = os.umask(0o077)
    try:
        temp.write_text(content, encoding="utf-8")
        temp.replace(path)
        path.chmod(0o600)
    finally:
        os.umask(old_mask)


def score_job(job, titles):
    title = job["title"].casefold()
    if SENIOR_TITLE.search(title) and not any(SENIOR_TITLE.search(t) for t in titles):
        return None
    tokens = set(re.findall(r"[a-z]{2,}", " ".join(titles).casefold())) - STOPWORDS
    matches = sorted(t for t in tokens if re.search(r"\b" + re.escape(t) + r"\b", title))
    if not matches:
        return None
    score = len(matches) * 2
    if re.search(r"\b(junior|entry|graduate|intern|trainee)\b", title):
        score += 3
    if "worldwide" in job["location"] or "Egypt listed" in job["location"]:
        score += 2
    job["match_signals"] = matches
    job["rank_score"] = score  # Search-order signal, not an eligibility or hiring probability.
    return job


def markdown(report):
    lines = [
        "# Job leads for review", "",
        "Sources: Himalayas (https://himalayas.app), Remotive (https://remotive.com), "
        "and owner-saved LinkedIn links. Open each original listing to check eligibility and availability.",
        "Nothing has been submitted.", "",
    ]
    for index, job in enumerate(report["leads"], 1):
        title = job["title"].replace("[", r"\[").replace("]", r"\]")
        company = job["company"].replace("[", r"\[").replace("]", r"\]")
        lines += [
            f"{index}. [{title} — {company}]({job['url']})",
            f"   - Source: [{job['source']}]({job['source_url']}) | Published: {job['published'] or 'unknown'}",
            f"   - Location: {job['location']} | Match signals: {', '.join(job['match_signals'])}",
            "",
        ]
    if not report["leads"]:
        lines.append("No matching leads in this fetch. Check the source statuses and broaden terms.")
    if report["source_errors"]:
        lines += ["", "Source errors:", *("- " + e for e in report["source_errors"])]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=Path.home() / ".config/okal/owner-profile.json")
    parser.add_argument("--linkedin-file", type=Path, default=Path.home() / ".config/okal/linkedin-jobs.json")
    parser.add_argument("--out-dir", type=Path, default=Path.home() / ".local/share/okal/job-leads")
    parser.add_argument("--cache-dir", type=Path, default=Path.home() / ".cache/okal/job-feeds")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--offline", action="store_true", help="Use only cached API responses")
    args = parser.parse_args(argv)
    try:
        profile = json.loads(args.profile.read_text(encoding="utf-8"))
        titles = profile["preferences"]["job_titles"]
        if not isinstance(titles, list) or not titles or not all(isinstance(t, str) and t.strip() for t in titles):
            raise ValueError("owner profile needs nonempty preferences.job_titles")
        if not 1 <= args.limit <= 50:
            raise ValueError("--limit must be between 1 and 50")
        # Max three Himalayas and two Remotive searches per daily cache window.
        queries = profile.get("preferences", {}).get("job_search_queries") or {}
        if not isinstance(queries, dict):
            raise ValueError("preferences.job_search_queries must be an object")
        h_queries = queries.get("himalayas", ["python", "AI", "software"])
        r_queries = queries.get("remotive", ["python", "data"])
        if not isinstance(h_queries, list) or not isinstance(r_queries, list):
            raise ValueError("Job search queries must be arrays")
        if not all(isinstance(q, str) and 1 <= len(q.strip()) <= 60 for q in h_queries + r_queries):
            raise ValueError("Job search queries must be short strings")
        if len(h_queries) > 3 or len(r_queries) > 2:
            raise ValueError("Max 3 Himalayas queries and 2 Remotive queries per daily cache window")
        args.cache_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        jobs, statuses, errors = [], [], []
        for source, base, query_list, normalizer, param in (
            ("Himalayas", HIMALAYAS, h_queries, normalize_himalayas, "q"),
            ("Remotive", REMOTIVE, r_queries, normalize_remotive, "search"),
        ):
            for query in query_list:
                params = {param: query}
                if source == "Himalayas":
                    params.update(sort="recent", page=1)
                else:
                    params["limit"] = 50
                url = base + "?" + urlencode(params)
                try:
                    payload, mode = read_cached_json(url, args.cache_dir, args.offline)
                    if not isinstance(payload.get("jobs"), list):
                        raise ValueError("API response has no jobs array")
                    jobs.extend(filter(None, (normalizer(j) for j in payload["jobs"])))
                    statuses.append(f"{source} {query}: {mode}, {len(payload['jobs'])} listings")
                except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
                    errors.append(f"{source} {query}: {type(exc).__name__}: {exc}")
        jobs.extend(load_linkedin(args.linkedin_file))
        if not statuses and not jobs:
            raise ValueError("No job source available: " + "; ".join(errors))
        ranked = {}
        for job in jobs:
            candidate = score_job(job, titles)
            if candidate:
                key = job["source"] + ":" + job["id"]
                ranked[key] = candidate
        chosen = sorted(ranked.values(), key=lambda j: (-j["rank_score"], j["source"], j["id"]))[:args.limit]
        report = {
            "schema_version": "okal.job_leads.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "review_only", "submission": "not_submitted",
            "source_status": statuses, "source_errors": errors, "leads": chosen,
        }
        args.out_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        write_private(args.out_dir / "leads.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        write_private(args.out_dir / "leads.md", markdown(report))
        print(f"Leads: {len(chosen)} | report: {args.out_dir / 'leads.md'}")
        for status in statuses:
            print(status)
        for error in errors:
            print("Warning: " + error, file=sys.stderr)
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print("Job search error: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
