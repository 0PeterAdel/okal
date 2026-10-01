#!/usr/bin/env python3
"""Compare private Voice Lab JSON reports without loading any ASR model."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


def _mean(rows: list[dict], key: str) -> float | None:
    values = [row[key] for row in rows if row.get(key) is not None]
    return statistics.mean(values) if values else None


def _median(rows: list[dict], key: str) -> float | None:
    values = [row[key] for row in rows if row.get(key) is not None]
    return statistics.median(values) if values else None


def _maximum(rows: list[dict], key: str) -> float | None:
    values = [row[key] for row in rows if row.get(key) is not None]
    return max(values) if values else None


def _fmt(value: float | None, *, percent: bool = False) -> str:
    if value is None:
        return "-"
    if percent:
        return f"{value * 100:.1f}%"
    return f"{value:.3f}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare Okal STT Voice Lab reports")
    parser.add_argument("reports", nargs="+", type=Path)
    args = parser.parse_args()

    print("| report | mode | completed | WER | norm WER | CER | critical recall | median latency | peak torch VRAM |")
    print("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for path in args.reports:
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = [row for row in payload.get("cases", []) if row.get("ok")]
        total = len(payload.get("cases", []))
        mode = f"{payload.get('backend', '?')}/{payload.get('language', 'auto')}"
        if payload.get("language_hints"):
            mode += " + hints*"
        print(
            f"| {path.stem} | {mode} | {len(rows)}/{total} | "
            f"{_fmt(_mean(rows, 'wer'))} | "
            f"{_fmt(_mean(rows, 'normalized_wer'))} | "
            f"{_fmt(_mean(rows, 'cer'))} | "
            f"{_fmt(_mean(rows, 'critical_term_recall'), percent=True)} | "
            f"{_fmt(_median(rows, 'latency_seconds'))}s | "
            f"{_fmt(_maximum(rows, 'torch_peak_memory_mb'))} MB |"
        )

    print()
    print("* language-hinted reports use the benchmark answer key for pure-language clips and are diagnostic only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
