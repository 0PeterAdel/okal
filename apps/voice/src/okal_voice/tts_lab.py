"""Generate private VoiceTut samples for a listening decision on target hardware."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path


SPEAKERS = ("Asmaa", "Hanan", "Mohamed", "Omar")
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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.list_speakers:
        print("\n".join(SPEAKERS))
        return 0
    os.umask(0o077)
    try:
        import torch
        from voicetut_tts import VoiceTutTTS
    except ImportError as exc:
        raise SystemExit(f"VoiceTut dependencies missing: {exc}. Run --setup.") from exc
    if not torch.cuda.is_available():
        raise SystemExit("CUDA is unavailable in the isolated VoiceTut environment.")
    engine = VoiceTutTTS.from_pretrained("mohammedaly22/VoiceTut-TTS")
    args.output.mkdir(mode=0o700, parents=True, exist_ok=True)
    results = []
    for speaker in dict.fromkeys(args.speaker or SPEAKERS):
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
