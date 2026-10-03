"""Generate private VoiceTut samples for a listening decision on target hardware."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path


SPEAKERS = ("Asmaa", "Hanan", "Mohamed", "Omar")
VOICE_REPO = "mohammedaly22/VoiceTut-TTS"
TOKENIZER_REPO = "eustlb/higgs-audio-v2-tokenizer"
PHRASES = {
    "greeting": "أهلاً يا بيتر، عامل إيه؟ أنا معاك، قول لي تحب نبدأ بإيه.",
    "assistant": "تمام، هبص على آخر تعديل في المشروع وألخصهولك ببساطة.",
    "mixed": "فتحت الـ README، وفيه setup steps بسيطة. تحب نمشي فيها واحدة واحدة؟",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Listen to Egyptian VoiceTut TTS candidates")
    parser.add_argument("--output", type=Path, default=Path("voice-lab-tts"))
    parser.add_argument("--speaker", choices=SPEAKERS, action="append")
    parser.add_argument("--list-speakers", action="store_true")
    parser.add_argument("--cache-status", action="store_true", help="Inspect local model files without network or CUDA")
    parser.add_argument("--download-missing", action="store_true", help="Fetch only inference files into the existing cache")
    return parser


def cached_snapshot(repo: str) -> Path | None:
    """Find the cached main revision without asking the Hub for metadata."""
    cache = Path(os.environ.get("HF_HUB_CACHE") or Path(os.environ.get("HF_HOME", Path.home() / ".cache/huggingface")) / "hub")
    root = cache / ("models--" + repo.replace("/", "--"))
    ref = root / "refs/main"
    if not ref.is_file():
        return None
    revision = ref.read_text(encoding="utf-8").strip()
    if len(revision) != 40 or any(ch not in "0123456789abcdef" for ch in revision):
        return None
    return root / "snapshots" / revision


def check_cache(speakers: tuple[str, ...]) -> tuple[Path | None, list[str]]:
    voice = cached_snapshot(VOICE_REPO)
    tokenizer = cached_snapshot(TOKENIZER_REPO)
    expected = (
        (voice, "VoiceTut", "config.json", 1),
        (voice, "VoiceTut", "model.safetensors", 2_000_000_000),
        (voice, "VoiceTut", "tokenizer.json", 1),
        (voice, "VoiceTut", "reference_speakers/references.json", 1),
        *((voice, "VoiceTut", f"reference_speakers/{speaker}_clean.wav", 1) for speaker in speakers),
        (tokenizer, "Higgs audio tokenizer", "config.json", 1),
        (tokenizer, "Higgs audio tokenizer", "model.safetensors", 700_000_000),
        (tokenizer, "Higgs audio tokenizer", "preprocessor_config.json", 1),
    )
    missing = [
        f"{label}: {name}"
        for root, label, name, minimum in expected
        if root is None or not (root / name).is_file() or (root / name).stat().st_size < minimum
    ]
    return voice, missing


def download_missing(speakers: tuple[str, ...]) -> None:
    """Download inference files one by one, preserving cached and partial blobs."""
    from huggingface_hub import hf_hub_download

    groups = (
        (VOICE_REPO, (
            ("config.json", 1),
            ("tokenizer.json", 1),
            ("tokenizer_config.json", 1),
            ("chat_template.jinja", 1),
            ("reference_speakers/references.json", 1),
            *((f"reference_speakers/{speaker}_clean.wav", 1) for speaker in speakers),
            ("model.safetensors", 2_000_000_000),
        )),
        (TOKENIZER_REPO, (
            ("config.json", 1),
            ("preprocessor_config.json", 1),
            ("model.safetensors", 700_000_000),
        )),
    )
    for repo, files in groups:
        snapshot = cached_snapshot(repo)
        # A commit hash keeps the same ETags and partial blob names across
        # separate runs even if the upstream main branch moves in between.
        revision = snapshot.name if snapshot is not None else "main"
        for name, minimum in files:
            path = snapshot / name if snapshot is not None else None
            if path is not None and path.is_file() and path.stat().st_size >= minimum:
                print(f"Cached: {repo}/{name}", flush=True)
                continue
            print(f"Fetching: {repo}/{name} (safe to retry with this same command)", flush=True)
            hf_hub_download(repo, name, revision=revision)
            if snapshot is None:
                snapshot = cached_snapshot(repo)
                if snapshot is None:
                    raise RuntimeError(f"Hub did not cache a pinned revision for {repo}")
                revision = snapshot.name
    _, missing = check_cache(speakers)
    if missing:
        raise RuntimeError("Download returned but required files remain missing: " + ", ".join(missing))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.list_speakers:
        print("\n".join(SPEAKERS))
        return 0
    speakers = tuple(dict.fromkeys(args.speaker or SPEAKERS))
    if args.download_missing:
        if os.environ.get("HF_HUB_OFFLINE", "").lower() in {"1", "true", "yes", "on"}:
            raise SystemExit("HF_HUB_OFFLINE is enabled. Unset it before --download-missing.")
        download_missing(speakers)
        print("Inference files ready in the existing cache. Run --cache-status, then try one speaker.")
        return 0
    model_path, missing = check_cache(speakers)
    if missing:
        print("VoiceTut local cache is incomplete. No download started. Missing:")
        for item in missing:
            print(f"  {item}")
        return 2
    if args.cache_status:
        print("VoiceTut and audio tokenizer are cached for the selected speakers. No download started.")
        return 0
    # The upstream loader resolves missing components from the Hub; disable
    # those requests even if its cache layout changes after this preflight.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.umask(0o077)
    try:
        import torch
        from voicetut_tts import VoiceTutTTS
    except ImportError as exc:
        raise SystemExit(f"VoiceTut dependencies missing: {exc}. Run --setup.") from exc
    if not torch.cuda.is_available():
        raise SystemExit("CUDA is unavailable in the isolated VoiceTut environment.")
    engine = VoiceTutTTS.from_pretrained(str(model_path))
    args.output.mkdir(mode=0o700, parents=True, exist_ok=True)
    results = []
    for speaker in speakers:
        for name, text in PHRASES.items():
            path = args.output / f"{speaker.lower()}-{name}.wav"
            torch.cuda.reset_peak_memory_stats()
            start = time.monotonic()
            engine.synthesize(text, speaker=speaker, num_step=32, output=str(path))
            if not path.is_file() or path.stat().st_size == 0:
                raise SystemExit(f"No audio produced: {path}")
            result = {
                "speaker": speaker, "case": name, "text": text, "file": str(path),
                "seconds": round(time.monotonic() - start, 3),
                "peak_vram_gb": round(torch.cuda.max_memory_reserved() / 1024**3, 3),
            }
            results.append(result)
            print(f'{path} | {result["seconds"]}s | {result["peak_vram_gb"]} GB peak')
    report = args.output / "manifest.json"
    report.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Listen and compare the WAV files. Private report: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
