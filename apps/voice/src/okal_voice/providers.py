"""Replaceable local STT, routing, and TTS provider adapters."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import VoiceConfig, validate_loopback_endpoint
from .contracts import ContractError, RouteDecision


class ProviderError(RuntimeError):
    pass


class FasterWhisper:
    """Resident local Whisper backend using CTranslate2/faster-whisper."""

    def __init__(self, config: VoiceConfig):
        self.config = config
        self._model = None

    def _load(self):
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise ProviderError(
                    "faster-whisper is not installed; run `pip install -e '.[stt]'`"
                ) from exc
            model_source = str(self.config.stt_model_dir or self.config.stt_model)
            try:
                self._model = WhisperModel(
                    model_source,
                    device=self.config.stt_device,
                    compute_type=self.config.stt_compute_type,
                )
            except Exception as exc:  # provider boundary: surface actionable error
                raise ProviderError(f"failed to load faster-whisper model: {exc}") from exc
        return self._model

    def transcribe(self, audio_path: Path) -> tuple[str, str]:
        model = self._load()
        try:
            segments, info = model.transcribe(
                str(audio_path),
                beam_size=self.config.stt_beam_size,
                vad_filter=self.config.stt_vad_filter,
                condition_on_previous_text=False,
                task="transcribe",
            )
            text = " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
        except Exception as exc:
            raise ProviderError(f"faster-whisper transcription failed: {exc}") from exc
        if not text:
            raise ProviderError("faster-whisper returned an empty transcript")
        language = getattr(info, "language", "unknown")
        return text, language if language in {"ar", "en"} else "mixed"


class WhisperCpp:
    """Compatibility fallback for machines that have not installed faster-whisper yet."""

    def __init__(self, config: VoiceConfig):
        self.config = config

    def transcribe(self, audio_path: Path) -> tuple[str, str]:
        executable = shutil.which(self.config.whisper_bin)
        if not executable:
            raise ProviderError(f"{self.config.whisper_bin} is not installed")
        if not self.config.whisper_model.is_file():
            raise ProviderError(f"Whisper model is missing: {self.config.whisper_model}")
        output_stem = audio_path.with_suffix("")
        command = [
            executable,
            "--model", str(self.config.whisper_model),
            "--file", str(audio_path),
            "--language", "auto",
            "--output-json", "--output-file", str(output_stem), "--no-prints",
        ]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=120)
        if completed.returncode != 0:
            raise ProviderError((completed.stderr or completed.stdout or "Whisper failed").strip())
        result_path = Path(f"{output_stem}.json")
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            text = " ".join(
                str(segment.get("text", "")).strip()
                for segment in payload.get("transcription", [])
                if isinstance(segment, dict)
            ).strip()
            language = str(payload.get("result", {}).get("language", "unknown"))
        except (OSError, json.JSONDecodeError, AttributeError) as exc:
            raise ProviderError("Whisper returned unreadable JSON") from exc
        finally:
            result_path.unlink(missing_ok=True)
        if not text:
            raise ProviderError("Whisper returned an empty transcript")
        return text, language if language in {"ar", "en"} else "mixed"


def build_stt(config: VoiceConfig):
    if config.stt_backend == "whisper.cpp":
        return WhisperCpp(config)
    return FasterWhisper(config)


ROUTER_SCHEMA = {
    "type": "object",
    "properties": {
        "route": {"type": "string", "enum": ["conversation", "task", "dictation", "clarify", "blocked"]},
        "language": {"type": "string", "enum": ["ar", "en", "mixed", "unknown"]},
        "summary": {"type": "string"},
        "reply": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["route", "language", "summary", "reply", "confidence"],
    "additionalProperties": False,
}

ROUTER_SYSTEM = """You are Okal's tiny local intent router. Understand Egyptian Arabic and English.
Return only JSON matching the supplied schema. You have no tools and no permission to act.
Routes: conversation for ordinary chat and questions; task for a request that should later be
handled by the governed kernel; dictation only when the user explicitly asks to type/write their
words; clarify when the intended route is genuinely unclear; blocked for requests to bypass safety.
Keep summary and reply short. Reply in the user's language. Never emit commands, code to execute,
tool names, credentials, or authorization decisions. For task, acknowledge that it was understood
and will be handed to the governed kernel; do not claim it ran."""


class OllamaRouter:
    def __init__(self, config: VoiceConfig, *, opener: Callable = urlopen):
        self.config = config
        self.endpoint = validate_loopback_endpoint(config.ollama_endpoint)
        self.opener = opener

    def route(self, transcript: str) -> RouteDecision:
        transcript = " ".join(transcript.strip().split())
        if not transcript:
            raise ProviderError("cannot route an empty transcript")
        body = json.dumps(
            {
                "model": self.config.router_model,
                "stream": False,
                "format": ROUTER_SCHEMA,
                "messages": [
                    {"role": "system", "content": ROUTER_SYSTEM},
                    {"role": "user", "content": transcript},
                ],
                "think": False,
                "options": {"temperature": 0, "num_ctx": 2048, "num_predict": 180},
            },
            ensure_ascii=False,
        ).encode("utf-8")
        request = Request(
            f"{self.endpoint}/api/chat", data=body, method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with self.opener(request, timeout=self.config.request_timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise ProviderError(f"local Ollama router is unavailable: {exc}") from exc
        try:
            content = payload["message"]["content"]
            return RouteDecision.from_json(content)
        except (KeyError, TypeError, ContractError) as exc:
            raise ProviderError(f"router response failed its contract: {exc}") from exc


class SilmaTts:
    """Local SILMA v1 adapter. Voice cloning requires an authorized reference clip."""

    def __init__(self, config: VoiceConfig):
        self.config = config

    def speak(self, text: str, language: str) -> str:
        if not self.config.silma_enabled or not self.config.silma_ref_audio:
            raise ProviderError("SILMA is disabled or no authorized reference audio is configured")
        if not self.config.silma_ref_audio.is_file():
            raise ProviderError(f"SILMA reference audio is missing: {self.config.silma_ref_audio}")
        try:
            from silma_tts.api import SilmaTTS
        except ImportError as exc:
            raise ProviderError("SILMA is not installed; run `pip install -e '.[tts]'`") from exc
        output = Path(tempfile.mkstemp(prefix="okal-silma-", suffix=".wav")[1])
        try:
            engine = SilmaTTS()
            engine.infer(
                ref_file=str(self.config.silma_ref_audio),
                ref_text=self.config.silma_ref_text,
                gen_text=text,
                file_wave=str(output),
                speed=self.config.silma_speed,
            )
            player = shutil.which("pw-play")
            if not player:
                raise ProviderError("pw-play is not installed")
            played = subprocess.run([player, str(output)], capture_output=True, text=True, timeout=90)
            if played.returncode != 0:
                raise ProviderError((played.stderr or "audio playback failed").strip())
            return "silma-tts"
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(f"SILMA synthesis failed: {exc}") from exc
        finally:
            output.unlink(missing_ok=True)


class LocalTts:
    def __init__(self, config: VoiceConfig):
        self.config = config

    def speak(self, text: str, language: str) -> str:
        text = " ".join(text.strip().split())
        if not text:
            raise ProviderError("cannot speak empty text")
        if self.config.silma_enabled and self.config.silma_ref_audio:
            try:
                return SilmaTts(self.config).speak(text, language)
            except ProviderError:
                pass
        model = self.config.piper_ar_model if language in {"ar", "mixed"} else self.config.piper_en_model
        piper = shutil.which(self.config.piper_bin)
        player = shutil.which("pw-play")
        if piper and player and model and model.is_file():
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
                wav_path = Path(handle.name)
            try:
                generated = subprocess.run(
                    [piper, "--model", str(model), "--output-file", str(wav_path)],
                    input=text, capture_output=True, text=True, timeout=60,
                )
                if generated.returncode != 0:
                    raise ProviderError((generated.stderr or "Piper failed").strip())
                played = subprocess.run([player, str(wav_path)], capture_output=True, text=True, timeout=60)
                if played.returncode != 0:
                    raise ProviderError((played.stderr or "audio playback failed").strip())
                return "piper"
            finally:
                wav_path.unlink(missing_ok=True)
        espeak = shutil.which(self.config.espeak_bin)
        if espeak:
            voice = "ar" if language in {"ar", "mixed"} else "en-us"
            completed = subprocess.run([espeak, "-v", voice, text], capture_output=True, text=True, timeout=60)
            if completed.returncode == 0:
                return "espeak-ng"
            raise ProviderError((completed.stderr or "espeak-ng failed").strip())
        raise ProviderError("no local TTS provider is ready; the text remains visible")
