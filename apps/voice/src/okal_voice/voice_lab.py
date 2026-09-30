"""Offline 12-utterance STT benchmark for Egyptian Arabic/code-switching."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import os
import statistics
import time
from pathlib import Path

from .config import VoiceConfig
from .providers import ProviderError, build_stt

CASES = [
    ("ar_01", "افتح لي المتصفح وخلي الصفحة دي قدامي"),
    ("ar_02", "عايز أكتب رسالة لبيتر وأقول له مساء الخير"),
    ("ar_03", "شغل الواي فاي لو سمحت وبعدها افتح التيرمنال"),
    ("ar_04", "اقرأ لي الملف ده وقولي أهم حاجة فيه"),
    ("ar_05", "خلي الصوت واطي شوية وبعدين شغل الموسيقى"),
    ("en_01", "Open the terminal and show me the current directory"),
    ("en_02", "Read the latest report and summarize the important points"),
    ("en_03", "Create a new branch for the voice experiment"),
    ("mix_01", "افتح VS Code وخليني أشوف الـ project بتاعنا"),
    ("mix_02", "عايزك تعمل git status وبعدها tell me what changed"),
    ("mix_03", "شغل the browser وافتح GitHub على الـ Okal repository"),
    ("mix_04", "ممكن تعمل a quick summary للـ issue دي بالمصري؟"),
]


def _wer(reference: str, hypothesis: str) -> float | None:
    try:
        from jiwer import wer
    except ImportError:
        return None
    return float(wer(reference, hypothesis))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local Okal STT voice lab")
    parser.add_argument("audio_dir", type=Path, nargs="?", help="Directory containing CASE_ID.wav files")
    parser.add_argument("--list-cases", action="store_true", help="Print case IDs and phrases for the recorder")
    parser.add_argument("--language-hints", action="store_true", help="Diagnostic: force ar/en for known-language cases; mixed cases stay automatic")
    parser.add_argument("--language-probes", action="store_true", help="Diagnostic: transcribe every clip automatically and with both ar/en candidates")
    parser.add_argument("--output", type=Path, default=Path("voice-lab-results.json"))
    args = parser.parse_args()

    if args.list_cases:
        for case_id, reference in CASES:
            print(f"{case_id}\t{reference}")
        return 0
    if args.audio_dir is None:
        parser.error("audio_dir is required unless --list-cases is used")
    if args.language_hints and args.language_probes:
        parser.error("select one diagnostic mode at a time")

    config = VoiceConfig.from_env()
    if (args.language_hints or args.language_probes) and config.stt_backend != "faster-whisper":
        parser.error("language diagnostics require faster-whisper")
    stt = build_stt(config)
    results: list[dict] = []
    for case_id, reference in CASES:
        audio = args.audio_dir / f"{case_id}.wav"
        row = {"id": case_id, "reference": reference, "audio": str(audio), "ok": False}
        if not audio.is_file():
            row["error"] = "missing recording"
            results.append(row)
            continue
        started = time.perf_counter()
        try:
            if args.language_probes:
                transcript, language, row["auto_metadata"] = stt.transcribe_with_metadata(audio)
            else:
                language_hint = case_id.split("_", 1)[0] if args.language_hints else None
                if language_hint == "mix":
                    language_hint = None
                if language_hint:
                    row["language_hint"] = language_hint
                    transcript, language = stt.transcribe(audio, language_hint=language_hint)
                else:
                    transcript, language = stt.transcribe(audio)
            row.update(
                ok=True,
                transcript=transcript,
                language=language,
                latency_seconds=round(time.perf_counter() - started, 3),
                wer=_wer(reference, transcript),
            )
            if args.language_probes:
                row["probes"] = {}
                for hint in ("ar", "en"):
                    probe_started = time.perf_counter()
                    try:
                        candidate, _, metadata = stt.transcribe_with_metadata(audio, language_hint=hint)
                        row["probes"][hint] = {
                            "transcript": candidate,
                            "wer": _wer(reference, candidate),
                            "latency_seconds": round(time.perf_counter() - probe_started, 3),
                            "mean_logprob": metadata["mean_logprob"],
                        }
                    except ProviderError as exc:
                        row["probes"][hint] = {"error": str(exc)}
        except ProviderError as exc:
            row["error"] = str(exc)
        results.append(row)

    completed = [r for r in results if r["ok"]]
    groups = {}
    for prefix in ("ar", "en", "mix"):
        group = [r for r in results if r["id"].startswith(prefix + "_")]
        measured = [r for r in group if r["ok"]]
        scores = [r["wer"] for r in measured if r["wer"] is not None]
        groups[prefix] = {
            "completed": len(measured),
            "total": len(group),
            "mean_wer": round(statistics.mean(scores), 3) if scores else None,
            "median_latency_seconds": round(statistics.median(r["latency_seconds"] for r in measured), 3) if measured else None,
        }
    summary = {
        "schema_version": "okal.voice.lab.v1",
        "backend": config.stt_backend,
        "model": config.stt_model_dir.as_posix() if config.stt_model_dir else config.stt_model,
        "device": config.stt_device,
        "compute_type": config.stt_compute_type,
        "language_mode": config.stt_language_mode,
        "language_hints": args.language_hints,
        "language_probes": args.language_probes,
        "groups": groups,
        "cases": results,
    }
    output_fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(output_fd, "w", encoding="utf-8") as output:
        os.fchmod(output.fileno(), 0o600)
        json.dump(summary, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print(f"Voice Lab: {len(completed)}/{len(results)} recordings completed")
    for name, group in groups.items():
        print(f"  {name}: {group['completed']}/{group['total']}  mean WER: {group['mean_wer']}  median latency: {group['median_latency_seconds']}s")
    for error, count in Counter(r.get("error", "unknown error") for r in results if not r["ok"]).items():
        print(f"  failed ({count} cases): {error}")
    print(f"Results: {args.output}")
    return 0 if len(completed) == len(results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
