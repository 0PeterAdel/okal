#!/usr/bin/env python3
"""Prepare a private, reviewable English CV PDF from owner-verified facts.

Input files stay on the owner's machine. This never reads LinkedIn or applies.
"""

import argparse
from collections import defaultdict
from datetime import datetime
from html import escape
import json
import os
from pathlib import Path
import re
import sys


SECTIONS = ("Experience", "Projects", "Education", "Skills", "Awards")
WORDS = re.compile(r"[a-zA-Z][a-zA-Z0-9+#.\-]{2,}")


def read_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def prepare(profile: dict, job: dict) -> tuple[dict, list[dict]]:
    if profile.get("schema_version") != "okal.owner.v1":
        raise ValueError("Owner profile schema_version must be okal.owner.v1")
    reviewed = profile.get("reviewed_at", "")
    try:
        datetime.fromisoformat(reviewed)
    except (TypeError, ValueError):
        raise ValueError("Review the private owner profile and set reviewed_at to an ISO date") from None
    identity = profile.get("identity")
    if not isinstance(identity, dict) or not all(
        isinstance(identity.get(k), str) and identity[k].strip() for k in ("name", "email")
    ):
        raise ValueError("Reviewed name and email are required")
    if not all(isinstance(job.get(k), str) and job[k].strip()
               for k in ("title", "company", "url", "description")):
        raise ValueError("Job needs title, company, URL, and full description")
    from urllib.parse import urlparse
    url = urlparse(job["url"])
    if url.scheme != "https" or not url.hostname:
        raise ValueError("Job URL must use HTTPS")
    facts = profile.get("facts", [])
    if not isinstance(facts, list):
        raise ValueError("facts must be a list")
    by_id = {}
    for fact in facts:
        if not isinstance(fact, dict) or not isinstance(fact.get("id"), str):
            raise ValueError("Every fact needs a stable id")
        if fact["id"] in by_id:
            raise ValueError(f"Duplicate fact id: {fact['id']}")
        by_id[fact["id"]] = fact
    requested = job.get("fact_ids")
    if requested is not None:
        if not isinstance(requested, list) or not requested or not all(isinstance(x, str) for x in requested):
            raise ValueError("fact_ids must be a nonempty list of strings")
        if len(set(requested)) != len(requested):
            raise ValueError("Duplicate fact_ids")
        if any(x not in by_id for x in requested):
            raise ValueError("Job selects an unknown fact id")
        chosen = [by_id[x] for x in requested]
    else:
        description = set(word.lower() for word in WORDS.findall(job["description"]))
        verified = [f for f in facts if f.get("verified") is True]
        chosen = sorted(verified, key=lambda f: -len(
            description & {w.lower() for w in WORDS.findall(str(f.get("text", "")))}
        ))[:12]
    if not chosen:
        raise ValueError("No verified facts selected; complete the owner profile")
    for fact in chosen:
        if (fact.get("verified") is not True or fact.get("section") not in SECTIONS or
            not all(isinstance(fact.get(k), str) and fact[k].strip() for k in ("text", "source"))):
            raise ValueError(f"Fact {fact['id']} has no verified text, source, or section")
    printable = [identity.get(k, "") for k in ("name", "email", "location", "linkedin", "portfolio")]
    printable += [job["title"]] + [f["text"] for f in chosen]
    if any(re.search(r"[\u0600-\u06ff]", str(part)) for part in printable):
        raise ValueError("This CV template currently supports English text; use reviewed English facts")
    return identity, chosen


def render_pdf(path: Path, identity: dict, job: dict, facts: list[dict]) -> None:
    try:
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, KeepTogether
    except ImportError as exc:
        raise ValueError("Install the optional PDF dependency: python -m pip install reportlab") from exc

    font = "Helvetica"
    for candidate in ("/usr/share/fonts/TTF/DejaVuSans.ttf",
                      "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if Path(candidate).is_file():
            pdfmetrics.registerFont(TTFont("OkalDejaVu", candidate))
            font = "OkalDejaVu"
            break
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Owner", parent=styles["Title"], fontName=font,
                              fontSize=18, leading=22, textColor=colors.HexColor("#152536")))
    styles.add(ParagraphStyle(name="Contact", fontName=font, fontSize=9, leading=13,
                              alignment=TA_CENTER, spaceAfter=10))
    styles.add(ParagraphStyle(name="Meta", fontName=font, fontSize=9,
                              leading=13, spaceAfter=6))
    styles.add(ParagraphStyle(name="Fact", fontName=font, fontSize=9, leading=14,
                              leftIndent=12, firstLineIndent=-8, spaceAfter=5))
    styles.add(ParagraphStyle(name="SectionTitle", fontName=font, fontSize=11,
                              leading=15, spaceBefore=12, spaceAfter=5,
                              textColor=colors.HexColor("#166787")))
    doc = SimpleDocTemplate(str(path), pagesize=(595.28, 841.89), rightMargin=48,
                            leftMargin=48, topMargin=42, bottomMargin=42)
    details = [identity.get(k, "") for k in ("email", "location", "linkedin", "portfolio")]
    contact = "  |  ".join(escape(s.strip()) for s in details if isinstance(s, str) and s.strip())
    story = [Paragraph(escape(identity["name"]), styles["Owner"]),
             Paragraph(contact, styles["Contact"]),
             Paragraph("Target role: " + escape(job["title"]), styles["Meta"]), Spacer(1, 8)]
    groups = defaultdict(list)
    for fact in facts:
        groups[fact["section"]].append(fact["text"])
    for section in SECTIONS:
        if groups[section]:
            story.append(Paragraph(section, styles["SectionTitle"]))
            for fact in groups[section]:
                story.append(KeepTogether([Paragraph("&#8226; " + escape(fact), styles["Fact"])]))
    doc.build(story)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        profile, job = read_json(args.profile), read_json(args.job)
        identity, facts = prepare(profile, job)
        out = args.out_dir.resolve()
        out.mkdir(parents=True, exist_ok=True, mode=0o700)
        pdf, packet = out / "cv.pdf", out / "review.json"
        if pdf.exists() or packet.exists():
            raise ValueError("Output already exists; use a new directory for each job")
        old_mask = os.umask(0o077)
        try:
            render_pdf(pdf, identity, job, facts)
            packet.write_text(json.dumps({
                "status": "pending_human_review", "submission": "not_submitted",
                "job": {k: job[k] for k in ("title", "company", "url")},
                "selected_facts": [{k: f[k] for k in ("id", "text", "source")} for f in facts],
                "cv": str(pdf),
            }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        finally:
            os.umask(old_mask)
        pdf.chmod(0o600)
        packet.chmod(0o600)
        print(f"CV: {pdf}\nReview packet: {packet}\nApplication not submitted.")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Application preparation error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
