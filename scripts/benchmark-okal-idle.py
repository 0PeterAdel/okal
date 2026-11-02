#!/usr/bin/env python3
"""Local-only user-systemd CPU/RSS sampling. Never accesses OKAL private data.

Usage: python3 scripts/benchmark-okal-idle.py --samples 12 --interval 5
CPU percent is process usage of ONE logical core (100% = one full core).
"""
import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

SERVICE = "okal-core.service"


def service_pid():
    try:
        result = subprocess.run(
            ["systemctl", "--user", "show", SERVICE,
             "--property=MainPID", "--value"],
            check=False, text=True, capture_output=True, timeout=3,
        )
        if result.returncode != 0:
            return 0
        raw = result.stdout.strip()
        return int(raw) if raw.isascii() and raw.isdigit() else 0
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return 0


def parse_proc_stat(raw):
    """Exclude parenthesized process name, which may include spaces or ')'."""
    end = raw.rfind(")")
    if end < 1 or not raw.startswith(tuple(str(d) for d in range(1, 10))):
        raise ValueError("invalid_proc_stat")
    tail = raw[end + 2:].split()
    if len(tail) < 13:
        raise ValueError("short_proc_stat")
    return int(tail[11]) + int(tail[12])


def proc_metrics(pid):
    if type(pid) is not int or pid <= 0:
        return None
    try:
        base = Path("/proc") / str(pid)
        ticks = parse_proc_stat((base / "stat").read_text())
        rss = 0
        for line in (base / "status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                words = line.split()
                if len(words) != 3 or words[2] != "kB":
                    return None
                rss = int(words[1])
                break
        return {"pid": pid, "cpu_ticks": ticks, "rss_kib": rss}
    except (FileNotFoundError, PermissionError, ValueError, OSError):
        return None


def summarize(samples, ticks_per_second):
    if not samples or ticks_per_second <= 0:
        raise ValueError("invalid_benchmark_data")
    cpu, pid_changes = [], 0
    busy, rss = 0, []
    for index, row in enumerate(samples):
        item = row["metrics"]
        if item is not None:
            busy += 1
            rss.append(item["rss_kib"])
        if index == 0:
            continue
        prev = samples[index - 1]
        older = prev["metrics"]
        if older is None or item is None or older["pid"] != item["pid"]:
            if older is not None and item is not None and older["pid"] != item["pid"]:
                pid_changes += 1
            continue
        elapsed = row["elapsed"] - prev["elapsed"]
        delta = item["cpu_ticks"] - older["cpu_ticks"]
        if elapsed <= 0 or delta < 0:
            continue
        cpu.append(100 * delta / ticks_per_second / elapsed)
    return {
        "service": SERVICE,
        "duration_seconds": round(samples[-1]["elapsed"] - samples[0]["elapsed"], 2),
        "samples": len(samples),
        "available_samples": busy,
        "pid_changes": pid_changes,
        "cpu_percent_avg_single_core": round(sum(cpu) / len(cpu), 2)
        if cpu else None,
        "cpu_percent_peak_single_core": round(max(cpu), 2) if cpu else None,
        "rss_mib_peak": round(max(rss) / 1024, 2) if rss else None,
        "rss_mib_last": round(rss[-1] / 1024, 2) if rss else None,
        "measurement_limit": (
            "One user-systemd MainPID, not child processes or GPU VRAM. "
            "No Gmail/Calendar network requests are made by this benchmark."
        ),
    }


def measure(samples=12, interval=5, *, pid_reader=service_pid,
            sampler=proc_metrics, sleeper=time.sleep,
            clock=time.monotonic):
    if type(samples) is not int or not 2 <= samples <= 240:
        raise ValueError("samples_out_of_range")
    if (not isinstance(interval, (int, float))
            or isinstance(interval, bool)
            or not math.isfinite(interval)
            or not 0.2 <= interval <= 60):
        raise ValueError("interval_out_of_range")
    readings = []
    start = clock()
    for i in range(samples):
        if i:
            sleeper(interval)
        pid = pid_reader()
        readings.append({
            "elapsed": clock() - start,
            "metrics": sampler(pid) if pid else None,
        })
    return summarize(readings, os.sysconf("SC_CLK_TCK"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=12)
    parser.add_argument("--interval", type=float, default=5)
    parser.add_argument("--out", type=Path,
                        help="Optional private JSON output, created with 0600")
    args = parser.parse_args(argv)
    try:
        report = measure(args.samples, args.interval)
        output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.out:
            # Never silently replace a prior measurement; owner-only file.
            descriptor = os.open(
                args.out, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(output)
        print(output, end="")
        return 0
    except (ValueError, OSError) as exc:
        print("Benchmark failed: invalid settings, output path or process data.",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
