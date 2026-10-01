#!/usr/bin/env python3
"""Compare private Voice Lab JSON reports without loading any ASR model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _fmt(value: float | None, *, percent: bool = False, suffix: str = "") -> str:
    if value is None:
        return "-"
    if percent:
        return f"{value * 100:.1f}%"
    return f"{value:.3f}{suffix}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare Okal STT Voice Lab reports")
    parser.add_argument("reports", nargs="+", type=Path)
    args = parser.parse_args()

    print(
        "| report | backend/mode | group | done | WER | norm WER | CER | "
        "critical recall | median latency | peak torch VRAM |"
    )
    print("|---|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for path in args.reports:
        payload = json.loads(path.read_text(encoding="utf-8"))
        mode = f"{payload.get('backend', '?')}/{payload.get('language', 'legacy')}"
        if payload.get("language_hints"):
            mode += " + hints*"
        for group_name in ("ar", "en", "mix"):
            group = payload.get("groups", {}).get(group_name, {})
            print(
                f"| {path.stem} | {mode} | {group_name} | "
                f"{group.get('completed', 0)}/{group.get('total', 0)} | "
                f"{_fmt(group.get('mean_wer'))} | "
                f"{_fmt(group.get('mean_normalized_wer'))} | "
                f"{_fmt(group.get('mean_cer'))} | "
                f"{_fmt(group.get('mean_critical_term_recall'), percent=True)} | "
                f"{_fmt(group.get('median_latency_seconds'), suffix='s')} | "
                f"{_fmt(group.get('max_torch_peak_memory_mb'), suffix=' MB')} |"
            )

    print()
    print("* hinted reports use the benchmark answer key for pure-language clips and are diagnostic only.")
    print("* legacy reports created before the extra metrics show '-' for those columns.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
