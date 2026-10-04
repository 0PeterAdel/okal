"""Isolated offline VoiceTut renderer, invoked by the voice service."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .tts_lab import SPEAKERS, check_cache


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--speaker", choices=SPEAKERS, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    os.environ["HF_HUB_OFFLINE"] = "1"
    model_path, missing = check_cache((args.speaker,))
    if missing:
        print("VoiceTut cache incomplete: " + ", ".join(missing), file=sys.stderr)
        return 2
    text = sys.stdin.read(4096).strip()
    if not text:
        print("empty speech text", file=sys.stderr)
        return 2
    try:
        from voicetut_tts import VoiceTutTTS

        engine = VoiceTutTTS.from_pretrained(str(model_path))
        engine.synthesize(text, speaker=args.speaker, num_step=32, output=str(args.output))
        if not args.output.is_file() or args.output.stat().st_size == 0:
            raise RuntimeError("no audio produced")
    except Exception as exc:
        print(f"VoiceTut synthesis failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
