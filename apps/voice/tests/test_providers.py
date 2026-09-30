import json
import unittest
from contextlib import AbstractContextManager
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from okal_voice.config import VoiceConfig
from okal_voice.contracts import RouteKind
from okal_voice.providers import FasterWhisper, OllamaRouter, ProviderError, WhisperCpp, build_stt


class Response(AbstractContextManager):
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload, ensure_ascii=False).encode()

    def __exit__(self, *args):
        return False


class RouterTests(unittest.TestCase):
    def test_validates_structured_local_response(self):
        content = json.dumps({
            "route": "task",
            "language": "ar",
            "summary": "افتح مهمة",
            "reply": "فهمت الطلب وسأمرره للنواة.",
            "confidence": 0.9,
        }, ensure_ascii=False)
        opener = mock.Mock(return_value=Response({"message": {"content": content}}))
        router = OllamaRouter(VoiceConfig(), opener=opener)
        decision = router.route("اعمل مهمة جديدة")
        self.assertEqual(decision.route, RouteKind.TASK)
        request = opener.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:11434/api/chat")
        sent = json.loads(request.data.decode("utf-8"))
        self.assertFalse(sent["think"])
        self.assertNotIn("tools", sent)

    def test_malformed_output_fails_closed(self):
        opener = mock.Mock(return_value=Response({"message": {"content": "not json"}}))
        with self.assertRaises(ProviderError):
            OllamaRouter(VoiceConfig(), opener=opener).route("hello")

    def test_empty_transcript_never_calls_provider(self):
        opener = mock.Mock()
        with self.assertRaises(ProviderError):
            OllamaRouter(VoiceConfig(), opener=opener).route("   ")
        opener.assert_not_called()


class SttSelectionTests(unittest.TestCase):
    def test_default_backend_is_faster_whisper(self):
        stt = build_stt(VoiceConfig())
        self.assertEqual(type(stt).__name__, "FasterWhisper")

    def test_whisper_cpp_is_explicit_fallback(self):
        stt = build_stt(VoiceConfig(stt_backend="whisper.cpp"))
        self.assertIsInstance(stt, WhisperCpp)

    def test_language_hint_is_diagnostic_and_auto_detection_stays_default(self):
        model = mock.Mock()
        model.transcribe.return_value = ([SimpleNamespace(text="Open the terminal")], SimpleNamespace(language="en"))
        stt = FasterWhisper(VoiceConfig())
        with mock.patch.object(stt, "_load", return_value=model):
            self.assertEqual(stt.transcribe(Path("en_01.wav")), ("Open the terminal", "en"))
            self.assertNotIn("language", model.transcribe.call_args.kwargs)
            self.assertEqual(stt.transcribe(Path("en_01.wav"), language_hint="en"), ("Open the terminal", "en"))
            self.assertEqual(model.transcribe.call_args.kwargs["language"], "en")

        with self.assertRaises(ValueError):
            stt.transcribe(Path("en_01.wav"), language_hint="mixed")
        self.assertEqual(model.transcribe.call_count, 2)

    def test_probe_exposes_auto_language_probabilities_and_candidate_score(self):
        model = mock.Mock()
        model.transcribe.return_value = (
            [SimpleNamespace(text="Read the report", avg_logprob=-0.4)],
            SimpleNamespace(language="ar", language_probability=0.62,
                            all_language_probs=[("ar", 0.62), ("en", 0.34), ("fr", 0.04)]),
        )
        stt = FasterWhisper(VoiceConfig())
        with mock.patch.object(stt, "_load", return_value=model):
            text, language, metadata = stt.transcribe_with_metadata(Path("en_02.wav"))
            self.assertEqual((text, language), ("Read the report", "ar"))
            self.assertEqual(metadata, {
                "language_probability": 0.62,
                "language_probabilities": {"ar": 0.62, "en": 0.34},
                "mean_logprob": -0.4,
            })
            _, _, forced_metadata = stt.transcribe_with_metadata(Path("en_02.wav"), language_hint="en")
            self.assertIsNone(forced_metadata["language_probability"])
            self.assertEqual(forced_metadata["language_probabilities"], {})
            self.assertEqual(model.transcribe.call_args.kwargs["language"], "en")


if __name__ == "__main__":
    unittest.main()
