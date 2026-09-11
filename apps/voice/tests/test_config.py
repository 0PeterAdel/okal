import unittest

from okal_voice.config import validate_loopback_endpoint


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


if __name__ == "__main__":
    unittest.main()
