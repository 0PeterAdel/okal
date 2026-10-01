import unittest
from unittest.mock import patch

from okal_voice.config import VoiceConfig, validate_loopback_endpoint


class LoopbackPolicyTests(unittest.TestCase):
    def test_allows_loopback(self):
        self.assertEqual(validate_loopback_endpoint("http://127.0.0.1:11434/"), "http://127.0.0.1:11434")
        self.assertEqual(validate_loopback_endpoint("http://localhost:11434"), "http://localhost:11434")

    def test_denies_remote_and_tls_endpoints(self):
        for endpoint in ("https://127.0.0.1:11434", "http://example.com", "https://api.openai.com"):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                validate_loopback_endpoint(endpoint)

    def test_denies_embedded_credentials(self):
        with self.assertRaises(ValueError):
            validate_loopback_endpoint("http://user:pass@127.0.0.1:11434")

    def test_dual_language_selection_requires_explicit_opt_in(self):
        with patch.dict("os.environ", {"OKAL_STT_LANGUAGE_MODE": "dual"}):
            self.assertEqual(VoiceConfig.from_env().stt_language_mode, "dual")
        with patch.dict("os.environ", {"OKAL_STT_LANGUAGE_MODE": "invalid"}):
            with self.assertRaisesRegex(ValueError, "OKAL_STT_LANGUAGE_MODE"):
                VoiceConfig.from_env()

    def test_hotwords_are_opt_in(self):
        with patch.dict("os.environ", {"OKAL_STT_HOTWORDS": "  README, pull request  "}):
            self.assertEqual(VoiceConfig.from_env().stt_hotwords, "README, pull request")
        with patch.dict("os.environ", {"OKAL_STT_HOTWORDS": "   "}):
            self.assertIsNone(VoiceConfig.from_env().stt_hotwords)


if __name__ == "__main__":
    unittest.main()
