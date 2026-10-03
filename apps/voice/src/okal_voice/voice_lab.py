"""Offline 12-utterance STT benchmark for Egyptian Arabic/code-switching."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import os
import re
import statistics
import time
import unicodedata
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

HOLDOUT_CASES = [
    ("ar_01", "اقفل نافذة المتصفح وافتح محرر النصوص"),
    ("ar_02", "قول لي الساعة كام ودرجة حرارة الجهاز دلوقتي"),
    ("ar_03", "جهز رسالة لبيتر تقول له الاجتماع اتأجل لبكرة"),
    ("ar_04", "هات آخر تعديل حصل في المشروع واشرحه ببساطة"),
    ("ar_05", "افتح مجلد التنزيلات ودور على أحدث ملف"),
    ("en_01", "Show me the last three commits in this repository"),
    ("en_02", "Open my downloads folder and find the newest PDF"),
    ("en_03", "Summarize today's notes in two short sentences"),
    ("mix_01", "افتح الـ terminal واعرض آخر خمس commits"),
    ("mix_02", "دور على ملف README وقولي الـ main points"),
    ("mix_03", "عايز أعمل new issue عن مشكلة المايك"),
    ("mix_04", "شغل الـ browser وافتح pull request رقم عشرة"),
]

VOCABULARY_CASES = [
    ("ar_01", "اقفل النافذة الحالية وافتح مجلد الصور"),
    ("ar_02", "هات درجة حرارة المعالج وقولي المروحة شغالة ولا لأ"),
    ("ar_03", "اكتب ملاحظة جديدة في ملف المصروفات"),
    ("ar_04", "اقرأ لي عنوان آخر ملف في التنزيلات"),
    ("en_01", "Find the README for this project and read the setup steps"),
    ("en_02", "Show the last five commits without opening the editor"),
    ("en_03", "Tell me whether the latest notes were saved today"),
    ("mix_01", "افتح GitHub وشوف الـ pull request اللي اتعمل امبارح"),
    ("mix_02", "اعمل git status وبعدها افتح VS Code"),
    ("mix_03", "شغل الواي فاي وقولي عدد التغييرات في المشروع"),
    ("mix_04", "افتح ملف الملاحظات وقولي آخر سطرين"),
    ("mix_05", "افتح التيرمنال واعرض آخر سبع commits"),
]

SUITES = {"baseline": CASES, "holdout": HOLDOUT_CASES, "vocabulary": VOCABULARY_CASES}

CRITICAL_VOCAB = (
    "pull request", "git status", "VS Code", "GitHub", "Wi-Fi", "README",
    "commits", "branch", "issue", "browser", "terminal", "repository", "project",
    "report", "PDF", "downloads", "notes",
    "افتح", "اقفل", "شغل", "اكتب", "اقرأ", "اعرض", "دور", "هات", "جهز",
    "رسالة", "ملف", "التنزيلات", "الواي فاي",
)
_ARABIC_DIACRITICS = re.compile(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]")
_NON_TEXT = re.compile(r"[^\w\u0600-\u06ff+#]+", re.UNICODE)


def _normalize_for_score(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold().replace("ـ", "")
    text = _ARABIC_DIACRITICS.sub("", text)
    text = text.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي"}))
    text = re.sub(r"(^|\s)ال(?=[a-z0-9+#])", r"\1", text)
    return " ".join(_NON_TEXT.sub(" ", text).split())


def _wer(reference: str, hypothesis: str) -> float | None:
    try:
        from jiwer import wer
    except ImportError:
        return None
    return float(wer(reference, hypothesis))


def _cer(reference: str, hypothesis: str) -> float | None:
    try:
        from jiwer import cer
    except ImportError:
        return None
    return float(cer(reference, hypothesis))


def _critical_terms(reference: str) -> list[str]:
    normalized = _normalize_for_score(reference)
    return [term for term in CRITICAL_VOCAB if _normalize_for_score(term) in normalized]


def _critical_term_recall(
    reference: str, hypothesis: str
) -> tuple[float | None, list[str], list[str]]:
    required = _critical_terms(reference)
    if not required:
        return None, [], []
    normalized_hypothesis = _normalize_for_score(hypothesis)
    matched = [term for term in required if _normalize_for_score(term) in normalized_hypothesis]
    return len(matched) / len(required), required, matched


def _reset_torch_peak_memory() -> None:
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
    except (ImportError, RuntimeError):
        pass


def _torch_peak_memory_mb() -> float | None:
    try:
        import torch
        if not torch.cuda.is_available():
            return None
        peak = int(torch.cuda.max_memory_reserved())
    except (ImportError, RuntimeError):
        return None
    return round(peak / (1024 * 1024), 1) if peak else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local Okal STT voice lab")
    parser.add_argument("audio_dir", type=Path, nargs="?", help="Directory containing CASE_ID.wav files")
    parser.add_argument("--suite", choices=SUITES, default="baseline", help="Phrase set, with a separate recording directory for each suite")
    parser.add_argument("--list-cases", action="store_true", help="Print case IDs and phrases for the recorder")
    parser.add_argument("--language-hints", action="store_true", help="Diagnostic: force ar/en for known-language cases; mixed cases stay automatic")
    parser.add_argument("--language-probes", action="store_true", help="Diagnostic: transcribe every clip automatically and with both ar/en candidates")
    parser.add_argument("--output", type=Path, default=Path("voice-lab-results.json"))
    args = parser.parse_args()
    cases = SUITES[args.suite]

    if args.list_cases:
        for case_id, reference in cases:
            print(f"{case_id}\t{reference}")
        return 0
    if args.audio_dir is None:
        parser.error("audio_dir is required unless --list-cases is used")
    if args.language_hints and args.language_probes:
        parser.error("select one diagnostic mode at a time")

    config = VoiceConfig.from_env()
    if args.language_probes and config.stt_backend != "faster-whisper":
        parser.error("language probes require faster-whisper decoder metadata")
    if args.language_hints and config.stt_backend == "whisper.cpp":
        parser.error("language hints are not supported by whisper.cpp")
    stt = build_stt(config)
    preparation_error = None
    if hasattr(stt, "prepare") and any(
        (args.audio_dir / f"{case_id}.wav").is_file() for case_id, _ in cases
    ):
        try:
            stt.prepare()
        except ProviderError as exc:
            preparation_error = str(exc)
    results: list[dict] = []
    for case_id, reference in cases:
        audio = args.audio_dir / f"{case_id}.wav"
        row = {"id": case_id, "reference": reference, "audio": str(audio), "ok": False}
        if not audio.is_file():
            row["error"] = "missing recording"
            results.append(row)
            continue
        if preparation_error is not None:
            row["error"] = preparation_error
            results.append(row)
            continue
        _reset_torch_peak_memory()
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
            normalized_reference = _normalize_for_score(reference)
            normalized_transcript = _normalize_for_score(transcript)
            critical_recall, required_terms, matched_terms = _critical_term_recall(
                reference, transcript
            )
            row.update(
                ok=True,
                transcript=transcript,
                language=language,
                latency_seconds=round(time.perf_counter() - started, 3),
                wer=_wer(reference, transcript),
                normalized_wer=_wer(normalized_reference, normalized_transcript),
                cer=_cer(normalized_reference, normalized_transcript),
                critical_term_recall=critical_recall,
                critical_terms=required_terms,
                critical_terms_matched=matched_terms,
                torch_peak_memory_mb=_torch_peak_memory_mb(),
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
        normalized_scores = [r["normalized_wer"] for r in measured if r["normalized_wer"] is not None]
        cer_scores = [r["cer"] for r in measured if r["cer"] is not None]
        critical_scores = [
            r["critical_term_recall"] for r in measured if r["critical_term_recall"] is not None
        ]
        memory_scores = [
            r["torch_peak_memory_mb"] for r in measured if r["torch_peak_memory_mb"] is not None
        ]
        groups[prefix] = {
            "completed": len(measured),
            "total": len(group),
            "mean_wer": round(statistics.mean(scores), 3) if scores else None,
            "mean_normalized_wer": round(statistics.mean(normalized_scores), 3)
            if normalized_scores else None,
            "mean_cer": round(statistics.mean(cer_scores), 3) if cer_scores else None,
            "mean_critical_term_recall": round(statistics.mean(critical_scores), 3)
            if critical_scores else None,
            "median_latency_seconds": round(
                statistics.median(r["latency_seconds"] for r in measured), 3
            ) if measured else None,
            "max_torch_peak_memory_mb": max(memory_scores) if memory_scores else None,
        }
    summary = {
        "schema_version": "okal.voice.lab.v1",
        "backend": config.stt_backend,
        "model": config.stt_model_dir.as_posix() if config.stt_model_dir else config.stt_model,
        "device": config.stt_device,
        "compute_type": config.stt_compute_type,
        "language_mode": config.stt_language_mode,
        "language": config.stt_language,
        "torch_dtype": config.stt_torch_dtype,
        "hotwords": config.stt_hotwords,
        "suite": args.suite,
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
        print(
            f"  {name}: {group['completed']}/{group['total']}  "
            f"WER: {group['mean_wer']}  norm WER: {group['mean_normalized_wer']}  "
            f"critical: {group['mean_critical_term_recall']}  "
            f"median latency: {group['median_latency_seconds']}s"
        )
    for error, count in Counter(r.get("error", "unknown error") for r in results if not r["ok"]).items():
        print(f"  failed ({count} cases): {error}")
    print(f"Results: {args.output}")
    return 0 if len(completed) == len(results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
