"""Optional next-generation local ASR candidates used by the Voice Lab."""

from __future__ import annotations

from pathlib import Path

from .config import VoiceConfig
from .providers import ProviderError


def _torch_dtype(torch, name: str):
    return {
        "float16": torch.float16,
        "bfloat16": torch.bfloat16,
        "float32": torch.float32,
    }[name]


def _device_name(configured: str) -> str:
    if configured == "cuda":
        return "cuda:0"
    return configured


def _language_code(value: object, fallback: str = "mixed") -> str:
    text = str(value or "").strip().lower()
    if text in {"ar", "arabic"} or text.startswith("arab"):
        return "ar"
    if text in {"en", "english"} or text.startswith("engl"):
        return "en"
    return fallback


class CohereTranscribe:
    """Cohere Transcribe Arabic via Transformers 5.x in an isolated environment."""

    def __init__(self, config: VoiceConfig):
        self.config = config
        self._runtime = None

    def _load(self):
        if self._runtime is not None:
            return self._runtime
        try:
            import torch
            from transformers import AutoProcessor, CohereAsrForConditionalGeneration
            from transformers.audio_utils import load_audio
        except ImportError as exc:
            raise ProviderError(
                "Cohere STT dependencies are missing; run "
                "`bash scripts/setup-stt-tournament.sh`"
            ) from exc

        source = str(self.config.stt_model_dir or self.config.stt_model)
        dtype = _torch_dtype(torch, self.config.stt_torch_dtype)
        try:
            processor = AutoProcessor.from_pretrained(source)
            load_kwargs = {"dtype": dtype}
            if self.config.stt_device == "auto":
                load_kwargs["device_map"] = "auto"
            model = CohereAsrForConditionalGeneration.from_pretrained(source, **load_kwargs)
            if self.config.stt_device != "auto":
                model = model.to(_device_name(self.config.stt_device))
            model.eval()
        except Exception as exc:
            raise ProviderError(f"failed to load Cohere Transcribe Arabic: {exc}") from exc

        self._runtime = (torch, processor, model, load_audio)
        return self._runtime

    def prepare(self) -> None:
        self._load()

    def transcribe(
        self, audio_path: Path, *, language_hint: str | None = None
    ) -> tuple[str, str]:
        if language_hint not in {None, "ar", "en"}:
            raise ValueError("language hint must be ar or en")
        language = language_hint or self.config.stt_language
        if language not in {"ar", "en"}:
            raise ProviderError(
                "Cohere Transcribe Arabic needs a pre-selected language; "
                "set OKAL_STT_LANGUAGE=ar or en"
            )

        torch, processor, model, load_audio = self._load()
        try:
            audio = load_audio(str(audio_path), sampling_rate=16000)
            inputs = processor(
                audio, sampling_rate=16000, return_tensors="pt", language=language
            )
            inputs = inputs.to(model.device)
            for key, value in list(inputs.items()):
                if hasattr(value, "is_floating_point") and value.is_floating_point():
                    inputs[key] = value.to(dtype=model.dtype)
            with torch.inference_mode():
                outputs = model.generate(**inputs, max_new_tokens=256)
            decoded = processor.decode(outputs, skip_special_tokens=True)
            if isinstance(decoded, list):
                text = " ".join(str(item).strip() for item in decoded if str(item).strip())
            else:
                text = str(decoded).strip()
        except Exception as exc:
            raise ProviderError(f"Cohere transcription failed: {exc}") from exc
        if not text:
            raise ProviderError("Cohere Transcribe Arabic returned an empty transcript")
        return text, language


class QwenCleoAsr:
    """QwenCleo checkpoint through the upstream qwen-asr transformers backend."""

    def __init__(self, config: VoiceConfig):
        self.config = config
        self._runtime = None

    def _load(self):
        if self._runtime is not None:
            return self._runtime
        try:
            import torch
            from qwen_asr import Qwen3ASRModel
        except ImportError as exc:
            raise ProviderError(
                "QwenCleo STT dependencies are missing; run "
                "`bash scripts/setup-stt-tournament.sh`"
            ) from exc

        source = str(self.config.stt_model_dir or self.config.stt_model)
        dtype = _torch_dtype(torch, self.config.stt_torch_dtype)
        device_map = _device_name(self.config.stt_device)
        try:
            model = Qwen3ASRModel.from_pretrained(
                source,
                dtype=dtype,
                device_map=device_map,
                max_inference_batch_size=1,
                max_new_tokens=256,
            )
        except Exception as exc:
            raise ProviderError(f"failed to load QwenCleo ASR: {exc}") from exc
        self._runtime = (torch, model)
        return self._runtime

    def prepare(self) -> None:
        self._load()

    def transcribe(
        self, audio_path: Path, *, language_hint: str | None = None
    ) -> tuple[str, str]:
        if language_hint not in {None, "ar", "en"}:
            raise ValueError("language hint must be ar or en")
        selected = language_hint or self.config.stt_language
        qwen_language = {"auto": None, "ar": "Arabic", "en": "English"}[selected]

        _, model = self._load()
        try:
            results = model.transcribe(audio=str(audio_path), language=qwen_language)
            result = results[0]
            text = str(result.text).strip()
            language = _language_code(
                getattr(result, "language", None),
                fallback=selected if selected in {"ar", "en"} else "mixed",
            )
        except Exception as exc:
            raise ProviderError(f"QwenCleo transcription failed: {exc}") from exc
        if not text:
            raise ProviderError("QwenCleo ASR returned an empty transcript")
        return text, language
