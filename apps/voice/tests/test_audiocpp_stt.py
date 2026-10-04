import io
import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError

from okal_voice.audiocpp_stt import AudioCppAsr
from okal_voice.config import VoiceConfig
from okal_voice.providers import ProviderError


class AudioCppSttTests(unittest.TestCase):
    def test_local_request_uses_arabic_hint_and_returns_transcript(self):
        calls = []

        def opener(request, timeout):
            calls.append((request, timeout))
            return io.BytesIO(json.dumps({"text": "افتح VS Code"}).encode())

        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "clip.wav"
            audio.write_bytes(b"RIFFfake")
            text, language = AudioCppAsr(VoiceConfig(stt_language="ar"), opener=opener).transcribe(audio)
        self.assertEqual((text, language), ("افتح VS Code", "ar"))
        request, timeout = calls[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:18080/v1/audio/transcriptions")
        self.assertEqual(timeout, 120)
        self.assertIn(b'name="language"', request.data)
        self.assertIn(b"Arabic", request.data)
        self.assertIn(b"RIFFfake", request.data)

    def test_english_probe_explicitly_changes_language(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "clip.wav"
            audio.write_bytes(b"RIFF")
            stt = AudioCppAsr(VoiceConfig(stt_language="ar"), opener=lambda request, timeout: io.BytesIO(b'{"text":"Open terminal"}'))
            self.assertEqual(stt.transcribe(audio, language_hint="en"), ("Open terminal", "en"))

    def test_auto_does_not_force_language(self):
        requests = []
        def opener(request, timeout):
            requests.append(request)
            return io.BytesIO(b'{"text":"Hello"}')
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "clip.wav"
            audio.write_bytes(b"RIFF")
            self.assertEqual(AudioCppAsr(VoiceConfig(stt_language="auto"), opener=opener).transcribe(audio), ("Hello", "mixed"))
        self.assertNotIn(b'name="language"', requests[0].data)

    def test_empty_audio_fails_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "clip.wav"
            audio.touch()
            with self.assertRaises(ProviderError):
                AudioCppAsr(VoiceConfig(), opener=lambda *_args, **_kwargs: self.fail("network called")).transcribe(audio)

    def test_server_error_includes_bounded_response_detail(self):
        def opener(request, timeout):
            raise HTTPError(request.full_url, 500, "Internal Server Error", {}, io.BytesIO(b'{"error":"model load failed"}'))
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "clip.wav"
            audio.write_bytes(b"RIFF")
            with self.assertRaisesRegex(ProviderError, "model load failed"):
                AudioCppAsr(VoiceConfig(), opener=opener).transcribe(audio)


if __name__ == "__main__":
    unittest.main()
