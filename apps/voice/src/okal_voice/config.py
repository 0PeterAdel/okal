"""Configuration for local voice providers. No secret or remote endpoint is used."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def _data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))


def validate_loopback_endpoint(endpoint: str) -> str:
    parsed = urlparse(endpoint)
    if parsed.scheme != "http" or parsed.hostname not in LOOPBACK_HOSTS:
        raise ValueError("model endpoint must be plain HTTP on loopback")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("model endpoint cannot contain credentials, query, or fragment")
    return endpoint.rstrip("/")


@dataclass(frozen=True, slots=True)
class VoiceConfig:
    stt_backend: str = "faster-whisper"
    stt_model: str = "mohammedaly22/whisper-large-v3-turbo-egyptian-code-switching"
    stt_model_dir: Path | None = None
    stt_device: str = "cuda"
    stt_compute_type: str = "float16"
    stt_beam_size: int = 3
    stt_vad_filter: bool = True
    whisper_bin: str = "whisper-cli"
    whisper_model: Path = _data_home() / "okal/models/whisper/ggml-large-v3-turbo-q5_0.bin"
    ollama_endpoint: str = "http://127.0.0.1:11434"
    router_model: str = "qwen3:0.6b"
    silma_enabled: bool = True
    silma_ref_audio: Path | None = None
    silma_ref_text: str | None = None
    silma_speed: float = 1.0
    piper_bin: str = "piper"
    piper_ar_model: Path | None = None
    piper_en_model: Path | None = None
    espeak_bin: str = "espeak-ng"
    sample_rate: int = 16000
    min_audio_seconds: float = 0.25
    request_timeout_seconds: float = 20.0

    @classmethod
    def from_env(cls) -> "VoiceConfig":
        data = _data_home()
        endpoint = validate_loopback_endpoint(
            os.environ.get("OKAL_OLLAMA_ENDPOINT", "http://127.0.0.1:11434")
        )
        return cls(
            stt_backend=os.environ.get("OKAL_STT_BACKEND", "faster-whisper"),
            stt_model=os.environ.get(
                "OKAL_STT_MODEL",
                "mohammedaly22/whisper-large-v3-turbo-egyptian-code-switching",
            ),
            stt_model_dir=_optional_path("OKAL_STT_MODEL_DIR"),
            stt_device=os.environ.get("OKAL_STT_DEVICE", "cuda"),
            stt_compute_type=os.environ.get("OKAL_STT_COMPUTE_TYPE", "float16"),
            stt_beam_size=int(os.environ.get("OKAL_STT_BEAM_SIZE", "3")),
            stt_vad_filter=os.environ.get("OKAL_STT_VAD", "1") not in {"0", "false", "no"},
            whisper_bin=os.environ.get("OKAL_WHISPER_BIN", "whisper-cli"),
            whisper_model=Path(
                os.environ.get(
                    "OKAL_WHISPER_MODEL",
                    data / "okal/models/whisper/ggml-large-v3-turbo-q5_0.bin",
                )
            ),
            ollama_endpoint=endpoint,
            router_model=os.environ.get("OKAL_ROUTER_MODEL", "qwen3:0.6b"),
            silma_enabled=os.environ.get("OKAL_SILMA_ENABLED", "1") not in {"0", "false", "no"},
            silma_ref_audio=_optional_path("OKAL_SILMA_REF_AUDIO"),
            silma_ref_text=os.environ.get("OKAL_SILMA_REF_TEXT") or None,
            silma_speed=float(os.environ.get("OKAL_SILMA_SPEED", "1.0")),
            piper_bin=os.environ.get("OKAL_PIPER_BIN", "piper"),
            piper_ar_model=_optional_path("OKAL_PIPER_AR_MODEL"),
            piper_en_model=_optional_path("OKAL_PIPER_EN_MODEL"),
            espeak_bin=os.environ.get("OKAL_ESPEAK_BIN", "espeak-ng"),
        )


def _optional_path(name: str) -> Path | None:
    value = os.environ.get(name, "").strip()
    return Path(value) if value else None
