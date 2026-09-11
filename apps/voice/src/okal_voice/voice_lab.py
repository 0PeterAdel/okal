"""Offline 12-utterance STT benchmark for Egyptian Arabic/code-switching."""

from __future__ import annotations

import argparse
import json
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
    parser.add_argument("audio_dir", type=Path, help="Directory containing CASE_ID.wav files")
    parser.add_argument("--output", type=Path, default=Path("voice-lab-results.json"))
    args = parser.parse_args()

    config = VoiceConfig.from_env()
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
            transcript, language = stt.transcribe(audio)
            row.update(
                ok=True,
                transcript=transcript,
                language=language,
                latency_seconds=round(time.perf_counter() - started, 3),
                wer=_wer(reference, transcript),
            )
        except ProviderError as exc:
            row["error"] = str(exc)
        results.append(row)

    summary = {
        "schema_version": "okal.voice.lab.v1",
        "backend": config.stt_backend,
        "model": config.stt_model_dir.as_posix() if config.stt_model_dir else config.stt_model,
        "device": config.stt_device,
        "compute_type": config.stt_compute_type,
        "cases": results,
    }
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    completed = [r for r in results if r["ok"]]
    print(f"Voice Lab: {len(completed)}/{len(results)} recordings completed")
    print(f"Results: {args.output}")
    return 0 if completed else 2


if __name__ == "__main__":
    raise SystemExit(main())
