"""Prepare faster-whisper feature metadata for the selected fine-tuned model."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _read_model_json(source: str, filename: str) -> dict:
    directory = Path(source)
    if directory.is_dir():
        path = directory / filename
    else:
        from huggingface_hub import hf_hub_download

        path = Path(hf_hub_download(repo_id=source, filename=filename))
    return json.loads(path.read_text(encoding="utf-8"))


def preprocessor_config(source: str) -> dict:
    processor = _read_model_json(source, "processor_config.json")
    model = _read_model_json(source, "config.json")
    feature = processor.get("feature_extractor")
    if not isinstance(feature, dict):
        raise ValueError("processor_config.json has no feature_extractor object")
    feature_size = feature.get("feature_size")
    mel_bins = model.get("num_mel_bins")
    if not isinstance(feature_size, int) or feature_size <= 0 or feature_size != mel_bins:
        raise ValueError(f"feature size {feature_size!r} does not match model mel bins {mel_bins!r}")
    if feature.get("sampling_rate") != 16000:
        raise ValueError("the feature extractor must use 16 kHz audio")
    return feature


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract the fine-tuned Whisper feature configuration")
    parser.add_argument("source", help="Hugging Face model ID or local model directory")
    args = parser.parse_args()
    try:
        print(json.dumps(preprocessor_config(args.source), ensure_ascii=False))
    except (OSError, ValueError, ImportError) as exc:
        print(f"Cannot prepare Whisper feature configuration: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
