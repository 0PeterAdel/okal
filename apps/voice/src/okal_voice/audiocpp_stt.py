"""Optional loopback adapter for the QwenCleo audio.cpp lab candidate."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import VoiceConfig
from .providers import ProviderError


class AudioCppAsr:
    def __init__(self, config: VoiceConfig, *, opener=urlopen):
        self.config = config
        self.opener = opener

    def transcribe(self, audio_path: Path, *, language_hint: str | None = None) -> tuple[str, str]:
        if language_hint not in {None, "ar", "en"}:
            raise ValueError("language hint must be ar or en")
        selected = language_hint or self.config.stt_language
        language = {"auto": "", "ar": "Arabic", "en": "English"}[selected]
        try:
            audio = audio_path.read_bytes()
        except OSError as exc:
            raise ProviderError(f"cannot read audio for audio.cpp: {exc}") from exc
        if not audio or len(audio) > 16 * 1024 * 1024:
            raise ProviderError("audio.cpp lab requires a nonempty WAV under 16 MiB")
        boundary = "okal-" + uuid.uuid4().hex
        payload = bytearray()
        fields = [("model", "qwencleo")]
        if language:
            fields.append(("language", language))
        for name, value in fields:
            payload.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
        payload.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"speech.wav\"\r\nContent-Type: audio/wav\r\n\r\n".encode())
        payload.extend(audio)
        payload.extend(f"\r\n--{boundary}--\r\n".encode())
        request = Request(
            self.config.audiocpp_endpoint + "/v1/audio/transcriptions",
            data=bytes(payload),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        try:
            with self.opener(request, timeout=120) as response:
                result = json.loads(response.read(65536))
            text = str(result["text"]).strip()
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, KeyError, TypeError) as exc:
            raise ProviderError(f"audio.cpp transcription failed: {exc}") from exc
        if not text:
            raise ProviderError("audio.cpp returned an empty transcript")
        return text, selected if selected in {"ar", "en"} else "mixed"
