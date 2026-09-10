import json
import unittest
from contextlib import AbstractContextManager
from unittest import mock

from okal_voice.config import VoiceConfig
from okal_voice.contracts import RouteKind
from okal_voice.providers import OllamaRouter, ProviderError


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


if __name__ == "__main__":
    unittest.main()
