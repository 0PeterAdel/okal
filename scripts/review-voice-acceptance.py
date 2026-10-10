#!/usr/bin/env python3
"""Prepare a human semantic review and score it without guessing from WER."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/voice/src"))
from okal_voice.acceptance_cases import CASES  # noqa: E402

EXPECTED = {case_id: (phrase, intent, target, details) for case_id, phrase, intent, target, details in CASES}
COUNTS = {"ar": 15, "en": 10, "mix": 15}
FIELDS = ("intent_ok", "target_ok", "details_ok", "unsafe_action")


def _read(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return payload


def _write_private(path: Path, payload: dict) -> None:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite an existing review: {path}")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def prepare(report: Path, output: Path) -> None:
    result = _read(report)
    rows = result.get("cases")
    if result.get("suite") != "acceptance" or not isinstance(rows, list) or len(rows) != len(CASES):
        raise ValueError("Expected a complete 40-case acceptance Voice Lab report")
    by_id = {row.get("id"): row for row in rows}
    if len(by_id) != len(CASES) or set(by_id) != set(EXPECTED):
        raise ValueError("Acceptance case IDs are missing or repeated")
    prepared = []
    for case_id, (reference, intent, target, details) in EXPECTED.items():
        row = by_id[case_id]
        if row.get("reference") != reference:
            raise ValueError(f"Reference changed for {case_id}")
        prepared.append({
            "id": case_id, "reference": reference, "transcript": row.get("transcript", ""),
            "recognition_ok": row.get("ok") is True,
            "check_intent": intent, "check_target": target, "check_details": details,
            "intent_ok": None, "target_ok": None, "details_ok": None,
            "unsafe_action": None, "notes": "",
        })
    _write_private(output, {
        "schema_version": "okal.voice.acceptance.review.v1",
        "model": result.get("model"), "backend": result.get("backend"),
        "source_report": str(report), "cases": prepared,
    })
    print(f"Review created: {output}")
    print("For every row, set intent_ok/target_ok/details_ok and unsafe_action to true or false.")
    print("A failed transcription is a failed command. Leave no null values before scoring.")


def score(path: Path) -> tuple[dict, bool]:
    review = _read(path)
    rows = review.get("cases")
    if review.get("schema_version") != "okal.voice.acceptance.review.v1" or not isinstance(rows, list):
        raise ValueError(f"Invalid acceptance review in {path}")
    by_id = {row.get("id"): row for row in rows}
    if len(rows) != 40 or len(by_id) != 40 or set(by_id) != set(EXPECTED):
        raise ValueError(f"Review must contain all 40 unique acceptance cases: {path}")
    summary: dict[str, dict] = {}
    incomplete = []
    for prefix, total in COUNTS.items():
        group = [by_id[case_id] for case_id in EXPECTED if case_id.startswith(prefix + "_")]
        assert len(group) == total
        passed = 0
        unsafe = 0
        for row in group:
            case_id = row["id"]
            if row.get("reference") != EXPECTED[case_id][0] or (
                row.get("check_intent"), row.get("check_target"), row.get("check_details")
            ) != EXPECTED[case_id][1:]:
                raise ValueError(f"Rubric changed for {case_id}; regenerate the review")
            if not all(type(row.get(field)) is bool for field in FIELDS):
                incomplete.append(case_id)
                continue
            if row["unsafe_action"]:
                unsafe += 1
            if row.get("recognition_ok") is True and all(row[field] for field in FIELDS[:3]) and not row["unsafe_action"]:
                passed += 1
        summary[prefix] = {"passed": passed, "total": total, "rate": passed / total,
                           "required": math.ceil(total * 0.70), "unsafe": unsafe}
    if incomplete:
        raise ValueError(f"Review all four booleans for every case; incomplete: {', '.join(incomplete)}")
    gate = all(group["passed"] >= group["required"] and group["unsafe"] == 0
               for group in summary.values())
    return summary, gate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    make = sub.add_parser("prepare", help="Generate a private, blank semantic review from a Voice Lab report")
    make.add_argument("report", type=Path)
    make.add_argument("--output", type=Path, required=True)
    grade = sub.add_parser("score", help="Count fully reviewed intent, target and detail success")
    grade.add_argument("reviews", type=Path, nargs="+")
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            prepare(args.report, args.output)
            return 0
        failed = False
        for path in args.reviews:
            summary, gate = score(path)
            print(f"{path} | {'PASS' if gate else 'BELOW 70%'}")
            for name, row in summary.items():
                print(f"  {name}: {row['passed']}/{row['total']} ({row['rate']:.1%}); "
                      f"required {row['required']}; unsafe flips {row['unsafe']}")
            failed |= not gate
        return 2 if failed else 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(2, f"Acceptance review error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
