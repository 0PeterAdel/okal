"""Configuration for local voice providers. No secret or remote endpoint is used."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
STT_BACKENDS = frozenset({"faster-whisper", "whisper.cpp", "cohere", "qwencleo", "audiocpp"})
DEFAULT_STT_MODELS = {
    "faster-whisper": "mohammedaly22/whisper-large-v3-turbo-egyptian-code-switching",
    "whisper.cpp": "mohammedaly22/whisper-large-v3-turbo-egyptian-code-switching",
    "cohere": "CohereLabs/cohere-transcribe-arabic-07-2026",
    "qwencleo": "mohammedaly22/QwenCleo-ASR",
    "audiocpp": "mohammedaly22/QwenCleo-ASR-GGUF",
}
TORCH_DTYPES = frozenset({"float16", "bfloat16", "float32"})
STT_LANGUAGES = frozenset({"auto", "ar", "en"})


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
    stt_language_mode: str = "auto"
    stt_language: str = "auto"
    stt_torch_dtype: str = "bfloat16"
    stt_hotwords: str | None = None
    whisper_bin: str = "whisper-cli"
    whisper_model: Path = _data_home() / "okal/models/whisper/ggml-large-v3-turbo-q5_0.bin"
    audiocpp_endpoint: str = "http://127.0.0.1:18080"
    audiocpp_prompt: str = ""
    ollama_endpoint: str = "http://127.0.0.1:11434"
    router_model: str = "qwen3:0.6b"
    conversation_model: str | None = None
    review_transcript: bool = False
    voicetut_enabled: bool = False
    voicetut_python: Path | None = None
    voicetut_speaker: str = "Asmaa"
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
        backend = os.environ.get("OKAL_STT_BACKEND", "faster-whisper")
        if backend not in STT_BACKENDS:
            raise ValueError(f"OKAL_STT_BACKEND must be one of: {', '.join(sorted(STT_BACKENDS))}")
        language_mode = os.environ.get("OKAL_STT_LANGUAGE_MODE", "auto")
        if language_mode not in {"auto", "dual"}:
            raise ValueError("OKAL_STT_LANGUAGE_MODE must be auto or dual")
        language = os.environ.get("OKAL_STT_LANGUAGE", "auto")
        if language not in STT_LANGUAGES:
            raise ValueError("OKAL_STT_LANGUAGE must be auto, ar, or en")
        torch_dtype = os.environ.get("OKAL_STT_TORCH_DTYPE", "bfloat16")
        if torch_dtype not in TORCH_DTYPES:
            raise ValueError("OKAL_STT_TORCH_DTYPE must be float16, bfloat16, or float32")
        endpoint = validate_loopback_endpoint(
            os.environ.get("OKAL_OLLAMA_ENDPOINT", "http://127.0.0.1:11434")
        )
        return cls(
            stt_backend=backend,
            stt_model=os.environ.get("OKAL_STT_MODEL", DEFAULT_STT_MODELS[backend]),
            stt_model_dir=_optional_path("OKAL_STT_MODEL_DIR"),
            stt_device=os.environ.get("OKAL_STT_DEVICE", "cuda"),
            stt_compute_type=os.environ.get("OKAL_STT_COMPUTE_TYPE", "float16"),
            stt_beam_size=int(os.environ.get("OKAL_STT_BEAM_SIZE", "3")),
            stt_vad_filter=os.environ.get("OKAL_STT_VAD", "1") not in {"0", "false", "no"},
            stt_language_mode=language_mode,
            stt_language=language,
            stt_torch_dtype=torch_dtype,
            stt_hotwords=os.environ.get("OKAL_STT_HOTWORDS", "").strip() or None,
            whisper_bin=os.environ.get("OKAL_WHISPER_BIN", "whisper-cli"),
            whisper_model=Path(
                os.environ.get(
                    "OKAL_WHISPER_MODEL",
                    data / "okal/models/whisper/ggml-large-v3-turbo-q5_0.bin",
                )
            ),
            audiocpp_endpoint=validate_loopback_endpoint(
                os.environ.get("OKAL_AUDIOCPP_ENDPOINT", "http://127.0.0.1:18080")
            ),
            audiocpp_prompt=os.environ.get("OKAL_AUDIOCPP_PROMPT", "").strip(),
            ollama_endpoint=endpoint,
            router_model=os.environ.get("OKAL_ROUTER_MODEL", "qwen3:0.6b"),
            conversation_model=os.environ.get("OKAL_CONVERSATION_MODEL", "").strip() or None,
            review_transcript=os.environ.get("OKAL_VOICE_REVIEW_TRANSCRIPT", "0").lower() in {"1", "true", "yes"},
            voicetut_enabled=os.environ.get("OKAL_VOICETUT_ENABLED", "0").lower() in {"1", "true", "yes"},
            voicetut_python=_optional_path("OKAL_VOICETUT_PYTHON"),
            voicetut_speaker=os.environ.get("OKAL_VOICETUT_SPEAKER", "Asmaa"),
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
