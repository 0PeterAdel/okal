import json
import unittest
from contextlib import AbstractContextManager
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from okal_voice.candidate_stt import CohereTranscribe, QwenCleoAsr, _candidate_source
from okal_voice.config import VoiceConfig
from okal_voice.contracts import RouteKind
from okal_voice.providers import FasterWhisper, OllamaConversation, OllamaRouter, ProviderError, WhisperCpp, build_stt


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
        self.assertEqual(sent["keep_alive"], "5m")

    def test_large_conversation_model_has_no_tools_and_unloads(self):
        opener = mock.Mock(return_value=Response({"message": {"content": "أهلاً، أنا معاك."}}))
        chat = OllamaConversation(VoiceConfig(conversation_model="command-r7b-arabic"), opener=opener)
        self.assertEqual(chat.reply("عامل إيه؟"), "أهلاً، أنا معاك.")
        sent = json.loads(opener.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(sent["model"], "command-r7b-arabic")
        self.assertEqual(sent["keep_alive"], 0)
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

    def test_candidate_backends_ignore_legacy_whisper_model_directory(self):
        config = VoiceConfig(
            stt_backend="cohere",
            stt_model="CohereLabs/cohere-transcribe-arabic-07-2026",
            stt_model_dir=Path("/tmp/legacy-whisper-ct2"),
        )
        self.assertEqual(
            _candidate_source(config),
            "CohereLabs/cohere-transcribe-arabic-07-2026",
        )

    def test_candidate_backends_are_explicit(self):
        self.assertIsInstance(
            build_stt(VoiceConfig(stt_backend="cohere")),
            CohereTranscribe,
        )
        self.assertIsInstance(
            build_stt(VoiceConfig(stt_backend="qwencleo")),
            QwenCleoAsr,
        )

    def test_language_hint_is_diagnostic_and_auto_detection_stays_default(self):
        model = mock.Mock()
        model.transcribe.return_value = ([SimpleNamespace(text="Open the terminal")], SimpleNamespace(language="en"))
        stt = FasterWhisper(VoiceConfig())
        with mock.patch.object(stt, "_load", return_value=model):
            self.assertEqual(stt.transcribe(Path("en_01.wav")), ("Open the terminal", "en"))
            self.assertNotIn("language", model.transcribe.call_args.kwargs)
            self.assertNotIn("hotwords", model.transcribe.call_args.kwargs)
            self.assertEqual(stt.transcribe(Path("en_01.wav"), language_hint="en"), ("Open the terminal", "en"))
            self.assertEqual(model.transcribe.call_args.kwargs["language"], "en")

        with self.assertRaises(ValueError):
            stt.transcribe(Path("en_01.wav"), language_hint="mixed")
        self.assertEqual(model.transcribe.call_count, 2)

    def test_hotwords_apply_to_both_dual_decodes(self):
        model = mock.Mock()
        model.transcribe.side_effect = [
            ([SimpleNamespace(text="ريدمي", avg_logprob=-0.8)], SimpleNamespace(language="ar")),
            ([SimpleNamespace(text="README", avg_logprob=-0.4)], SimpleNamespace(language="en")),
        ]
        stt = FasterWhisper(VoiceConfig(stt_language_mode="dual", stt_hotwords="README, pull request"))
        with mock.patch.object(stt, "_load", return_value=model):
            self.assertEqual(stt.transcribe(Path("mix_02.wav")), ("README", "en"))
        self.assertEqual(len(model.transcribe.call_args_list), 2)
        self.assertTrue(all(call.kwargs["hotwords"] == "README, pull request"
                            for call in model.transcribe.call_args_list))

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

    def test_dual_mode_rescues_english_without_changing_arabic_or_default(self):
        model = mock.Mock()
        arabic = ([SimpleNamespace(text="كلام عربي", avg_logprob=-1.1)], SimpleNamespace(language="ar"))
        english = ([SimpleNamespace(text="Read the latest report", avg_logprob=-0.4)],
                   SimpleNamespace(language="en"))
        stt = FasterWhisper(VoiceConfig(stt_language_mode="dual"))
        with mock.patch.object(stt, "_load", return_value=model):
            model.transcribe.side_effect = [arabic, english]
            self.assertEqual(stt.transcribe(Path("en_02.wav")), ("Read the latest report", "en"))
            self.assertEqual(model.transcribe.call_args_list[1].kwargs["language"], "en")

            model.transcribe.reset_mock(side_effect=True)
            model.transcribe.side_effect = [
                ([SimpleNamespace(text="افتح المتصفح", avg_logprob=-0.3)], SimpleNamespace(language="ar")),
                ([SimpleNamespace(text="Open the browser", avg_logprob=-1.2)], SimpleNamespace(language="en")),
            ]
            self.assertEqual(stt.transcribe(Path("ar_01.wav")), ("افتح المتصفح", "ar"))

            model.transcribe.reset_mock(side_effect=True)
            model.transcribe.return_value = english
            self.assertEqual(stt.transcribe(Path("en_01.wav")), ("Read the latest report", "en"))
            self.assertEqual(model.transcribe.call_count, 1)

    def test_dual_mode_keeps_auto_if_english_candidate_fails(self):
        model = mock.Mock()
        model.transcribe.side_effect = [
            ([SimpleNamespace(text="الكلام العربي", avg_logprob=-0.3)], SimpleNamespace(language="ar")),
            RuntimeError("decoder unavailable"),
        ]
        stt = FasterWhisper(VoiceConfig(stt_language_mode="dual"))
        with mock.patch.object(stt, "_load", return_value=model):
            self.assertEqual(stt.transcribe(Path("ar_01.wav")), ("الكلام العربي", "ar"))


if __name__ == "__main__":
    unittest.main()
