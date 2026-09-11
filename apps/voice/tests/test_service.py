import tempfile
import time
import unittest
from pathlib import Path

from okal_voice.config import VoiceConfig
from okal_voice.contracts import RouteDecision, RouteKind, VoicePhase
from okal_voice.providers import ProviderError
from okal_voice.runtime import StateStore
from okal_voice.service import VoiceService


class FakeCapture:
    def __init__(self, root, duration=1.0):
        self.root = root
        self.duration = duration
        self.active = False

    def start(self):
        self.active = True

    def stop(self):
        self.active = False
        path = self.root / "speech.wav"
        path.write_bytes(b"RIFFfake")
        return path, self.duration

    def cancel(self):
        self.active = False


class FakeStt:
    def transcribe(self, audio_path):
        return "مساء الخير", "ar"


class FakeRouter:
    def __init__(self, failure=None):
        self.failure = failure
        self.calls = []

    def route(self, transcript):
        self.calls.append(transcript)
        if self.failure:
            raise self.failure
        return RouteDecision(RouteKind.CONVERSATION, "ar", "تحية", "مساء النور يا بيتر", 0.99)


class FakeTts:
    def __init__(self, failure=None):
        self.failure = failure
        self.calls = []

    def speak(self, text, language):
        self.calls.append((text, language))
        if self.failure:
            raise self.failure
        return "fake"


class VoiceServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "runtime"
        self.store = StateStore(self.root)
        self.capture = FakeCapture(self.root)
        self.router = FakeRouter()
        self.tts = FakeTts()
        self.service = VoiceService(
            VoiceConfig(),
            self.store,
            capture=self.capture,
            stt=FakeStt(),
            router=self.router,
            tts=self.tts,
        )

    def wait_for(self, phase, timeout=2):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.service.phase is phase:
                return
            time.sleep(0.01)
        self.fail(f"service did not reach {phase}; current={self.service.phase}")

    def test_toggle_captures_routes_and_speaks_without_actions(self):
        self.assertEqual(self.service.toggle()["phase"], "listening")
        self.assertTrue(self.capture.active)
        self.assertEqual(self.service.toggle()["phase"], "transcribing")
        self.wait_for(VoicePhase.IDLE)
        self.assertFalse(self.capture.active)
        self.assertEqual(self.router.calls, ["مساء الخير"])
        self.assertEqual(self.tts.calls, [("مساء النور يا بيتر", "ar")])
        route = self.store.route_path.read_text(encoding="utf-8")
        self.assertIn('"authority":"classification-only"', route)

    def test_short_audio_is_blocked_and_not_routed(self):
        self.capture.duration = 0.1
        self.service.toggle()
        response = self.service.toggle()
        self.assertFalse(response["ok"])
        self.assertEqual(self.service.phase, VoicePhase.BLOCKED)
        self.assertEqual(self.router.calls, [])

    def test_cancel_physically_stops_capture(self):
        self.service.toggle()
        self.service.cancel()
        self.assertFalse(self.capture.active)
        self.assertEqual(self.service.phase, VoicePhase.IDLE)

    def test_router_failure_is_visible_and_never_speaks(self):
        self.router.failure = ProviderError("bad router")
        self.service.say("hello")
        self.wait_for(VoicePhase.ERROR)
        self.assertEqual(self.tts.calls, [])

    def test_tts_failure_keeps_text_visible_without_rerouting(self):
        self.tts.failure = ProviderError("no voice")
        self.service.say("hello")
        self.wait_for(VoicePhase.ERROR)
        self.assertEqual(self.router.calls, ["hello"])
        self.assertIn("مساء النور", self.store.read().text)

    def test_empty_typed_request_is_blocked(self):
        response = self.service.say("  ")
        self.assertFalse(response["ok"])
        self.assertEqual(self.service.phase, VoicePhase.BLOCKED)


if __name__ == "__main__":
    unittest.main()
