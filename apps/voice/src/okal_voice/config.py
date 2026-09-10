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
    whisper_bin: str = "whisper-cli"
    whisper_model: Path = _data_home() / "okal/models/whisper/ggml-large-v3-turbo-q5_0.bin"
    ollama_endpoint: str = "http://127.0.0.1:11434"
    router_model: str = "qwen3:0.6b"
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
            whisper_bin=os.environ.get("OKAL_WHISPER_BIN", "whisper-cli"),
            whisper_model=Path(
                os.environ.get(
                    "OKAL_WHISPER_MODEL",
                    data / "okal/models/whisper/ggml-large-v3-turbo-q5_0.bin",
                )
            ),
            ollama_endpoint=endpoint,
            router_model=os.environ.get("OKAL_ROUTER_MODEL", "qwen3:0.6b"),
            piper_bin=os.environ.get("OKAL_PIPER_BIN", "piper"),
            piper_ar_model=_optional_path("OKAL_PIPER_AR_MODEL"),
            piper_en_model=_optional_path("OKAL_PIPER_EN_MODEL"),
            espeak_bin=os.environ.get("OKAL_ESPEAK_BIN", "espeak-ng"),
        )


def _optional_path(name: str) -> Path | None:
    value = os.environ.get(name, "").strip()
    return Path(value) if value else None
