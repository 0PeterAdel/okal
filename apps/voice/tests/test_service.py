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


class FakeConversation:
    def __init__(self):
        self.calls = []

    def reply(self, transcript):
        self.calls.append(transcript)
        return "يا أهلا، أنا معاك. تحب نبدأ بإيه؟"


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
        self.addCleanup(self.finish_pipeline)

    def finish_pipeline(self):
        pipeline = self.service._pipeline
        if pipeline is not None:
            pipeline.join(timeout=2)
            self.assertFalse(pipeline.is_alive(), "voice pipeline did not finish")

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
        self.service.ask("hello")
        self.wait_for(VoicePhase.ERROR)
        self.assertEqual(self.tts.calls, [])

    def test_tts_failure_keeps_text_visible_without_rerouting(self):
        self.tts.failure = ProviderError("no voice")
        self.service.ask("hello")
        self.wait_for(VoicePhase.ERROR)
        self.assertEqual(self.router.calls, ["hello"])
        self.assertIn("مساء النور", self.store.read().text)

    def test_empty_typed_request_is_blocked(self):
        response = self.service.ask("  ")
        self.assertFalse(response["ok"])
        self.assertEqual(self.service.phase, VoicePhase.BLOCKED)

    def test_arabic_greeting_remains_egyptian_when_router_answers_in_english(self):
        self.router.route = lambda _: RouteDecision(
            RouteKind.CONVERSATION, "en", "English greeting", "May you have a peaceful day, Peter.", 0.8
        )
        self.service.ask("مساء الخير يا بيتر")
        self.wait_for(VoicePhase.IDLE)
        self.assertEqual(self.tts.calls, [("مساء النور يا بيتر، أنا معاك. تحب نبدأ بإيه؟", "ar")])
        self.assertEqual(self.store.read().language, "ar")

    def test_english_reply_keeps_english(self):
        self.router.route = lambda _: RouteDecision(
            RouteKind.CONVERSATION, "ar", "تحية", "Good evening, Peter.", 0.8
        )
        self.service.ask("Good evening, Peter")
        self.wait_for(VoicePhase.IDLE)
        self.assertEqual(self.tts.calls, [("Good evening, Peter.", "en")])

    def test_say_speaks_exact_text_without_router_or_conversation(self):
        self.service.conversation = FakeConversation()
        response = self.service.handle({"command": "say", "text": "مساء الخير يا بيتر"})
        self.assertEqual(response, {"ok": True, "phase": "speaking"})
        self.wait_for(VoicePhase.IDLE)
        self.assertEqual(self.tts.calls, [("مساء الخير يا بيتر", "ar")])
        self.assertEqual(self.router.calls, [])
        self.assertEqual(self.service.conversation.calls, [])
        self.assertFalse(self.store.route_path.exists())

    def test_opt_in_conversation_uses_large_model_only_for_chat(self):
        conversation = FakeConversation()
        self.service.conversation = conversation
        self.service.ask("مساء الخير")
        self.wait_for(VoicePhase.IDLE)
        self.assertEqual(conversation.calls, ["مساء الخير"])
        self.assertEqual(self.tts.calls[-1][0], "يا أهلا، أنا معاك. تحب نبدأ بإيه؟")
        self.router.route = lambda _: RouteDecision(
            RouteKind.TASK, "ar", "فتح المتصفح", "فهمت طلبك", 0.9
        )
        self.service.ask("افتح المتصفح")
        self.wait_for(VoicePhase.IDLE)
        self.assertEqual(conversation.calls, ["مساء الخير"])
        self.assertEqual(self.tts.calls[-1][0], "فهمت طلبك")


if __name__ == "__main__":
    unittest.main()
