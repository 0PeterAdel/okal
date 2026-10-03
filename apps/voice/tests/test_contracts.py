import json
import unittest

from okal_voice.contracts import ContractError, RouteDecision, RouteKind, VoicePhase, VoiceSnapshot


class RouteDecisionTests(unittest.TestCase):
    def payload(self, **changes):
        value = {
            "route": "conversation",
            "language": "ar",
            "summary": "تحية",
            "reply": "أهلاً يا بيتر",
            "confidence": 0.95,
        }
        value.update(changes)
        return json.dumps(value, ensure_ascii=False)

    def test_accepts_exact_contract(self):
        decision = RouteDecision.from_json(self.payload())
        self.assertEqual(decision.route, RouteKind.CONVERSATION)
        self.assertEqual(decision.language, "ar")

    def test_rejects_executable_extra_field(self):
        with self.assertRaises(ContractError):
            RouteDecision.from_json(self.payload(command="rm -rf /"))

    def test_rejects_unknown_route(self):
        with self.assertRaises(ContractError):
            RouteDecision.from_json(self.payload(route="shell"))

    def test_rejects_empty_conversation_reply(self):
        with self.assertRaises(ContractError):
            RouteDecision.from_json(self.payload(reply=""))

    def test_rejects_non_finite_confidence(self):
        with self.assertRaises(ContractError):
            RouteDecision.from_json(self.payload(confidence=float("nan")))


class VoiceSnapshotTests(unittest.TestCase):
    def test_round_trip_preserves_schema(self):
        original = VoiceSnapshot.new(VoicePhase.LISTENING, session_id="abc", now=100)
        loaded = VoiceSnapshot.from_dict(original.as_dict())
        self.assertEqual(loaded, original)

    def test_stale_state_is_detected(self):
        snapshot = VoiceSnapshot.new(VoicePhase.LISTENING, now=100)
        self.assertFalse(snapshot.is_fresh(now=1001, max_age=900))


if __name__ == "__main__":
    unittest.main()
