"""Isolated offline VoiceTut renderer, invoked by the voice service."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .tts_lab import SPEAKERS, check_cache


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--speaker", choices=SPEAKERS, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--serve", action="store_true")
    args = parser.parse_args(argv)
    if not args.serve and args.output is None:
        parser.error("--output is required outside --serve")
    os.environ["HF_HUB_OFFLINE"] = "1"
    model_path, missing = check_cache((args.speaker,))
    if missing:
        print("VoiceTut cache incomplete: " + ", ".join(missing), file=sys.stderr)
        return 2
    try:
        from voicetut_tts import VoiceTutTTS

        engine = VoiceTutTTS.from_pretrained(str(model_path))
    except Exception as exc:
        print(f"VoiceTut load failed: {exc}", file=sys.stderr)
        return 1
    if args.serve:
        print('OKAL_TTS {"ready":true}', flush=True)
        for line in sys.stdin:
            try:
                request = json.loads(line)
                text = request["text"]
                output = Path(request["output"])
                if not isinstance(text, str) or not text.strip() or len(text) > 4000:
                    raise ValueError("invalid speech text")
                engine.synthesize(text, speaker=args.speaker, num_step=32, output=str(output))
                if not output.is_file() or output.stat().st_size == 0:
                    raise RuntimeError("no audio produced")
                result = {"ok": True}
            except Exception as exc:  # isolate individual synthesis failures
                result = {"ok": False, "error": str(exc)[:300]}
            print("OKAL_TTS " + json.dumps(result, ensure_ascii=False), flush=True)
        return 0
    text = sys.stdin.read(4096).strip()
    if not text:
        print("empty speech text", file=sys.stderr)
        return 2
    try:
        engine.synthesize(text, speaker=args.speaker, num_step=32, output=str(args.output))
        if not args.output.is_file() or args.output.stat().st_size == 0:
            raise RuntimeError("no audio produced")
    except Exception as exc:
        print(f"VoiceTut synthesis failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
