#!/usr/bin/env python3
"""Preflight a source ledger for an unpublished social draft.

This checks literal evidence only. It cannot decide whether a quotation supports
the claim, whether the text is appropriate, or whether the owner approves it.
"""

import argparse
import json
from pathlib import Path
import subprocess
import sys


def check(draft_path: Path, root: Path) -> list[str]:
    errors: list[str] = []
    try:
        data = json.loads(draft_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [f"Cannot read draft JSON: {exc}"]
    if not isinstance(data, dict):
        return ["Draft must be a JSON object"]

    platform = data.get("platform")
    if platform not in ("x", "linkedin"):
        errors.append("platform must be x or linkedin")
    text = data.get("text")
    if not isinstance(text, str) or not text.strip():
        errors.append("text must be a nonempty string")
    evidence = data.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        return errors + ["evidence must be a nonempty list"]

    for index, item in enumerate(evidence, 1):
        label = f"evidence[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        claim, source, quote = (item.get(key) for key in ("claim", "source", "quote"))
        if not all(isinstance(value, str) and value.strip() for value in (claim, source, quote)):
            errors.append(f"{label} needs nonempty claim, source, and quote strings")
            continue
        if isinstance(text, str) and claim not in text:
            errors.append(f"{label} claim is absent from draft text")
        rel = Path(source)
        if rel.is_absolute() or ".." in rel.parts or not rel.parts:
            errors.append(f"{label} source must be a repository-relative path")
            continue
        target = (root / rel).resolve()
        if not target.is_relative_to(root.resolve()) or not target.is_file():
            errors.append(f"{label} source is not a regular file inside the repository")
            continue
        tracked = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--error-unmatch", "--", source],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
        if tracked.returncode:
            errors.append(f"{label} source is not tracked by git")
            continue
        try:
            content = target.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            errors.append(f"{label} source is not readable UTF-8 text")
            continue
        if quote not in content:
            errors.append(f"{label} quote is absent from {source}")
        else:
            print(f"{label}: {claim!r} -> {source}: {quote!r}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("draft", type=Path, help="JSON draft; this tool never publishes")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    errors = check(args.draft, root)
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if errors:
        return 1
    print("Literal evidence checks passed. MANUAL REVIEW REQUIRED: check every claim's meaning, wording, and final platform text before approval. No post was published.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
