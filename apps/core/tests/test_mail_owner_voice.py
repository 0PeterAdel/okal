"""Account-owner voice in new and previously saved summaries; no mailbox use."""
from unittest import TestCase
from unittest.mock import MagicMock, patch
from contextlib import contextmanager

from okal_core.mail.owner_voice import owner_voice
from okal_core.mail.inference import LocalModel
from okal_core.mail.contracts import Config, InsightPayload
from okal_core.mail.viewer import saved_analysis


class SyntheticOwnerModel(LocalModel):
    def __init__(self, rendered):
        self.cfg = Config(account="owner@example.com",model="local:test",
                          model_digest="a"*64)
        self.rendered = rendered
        self.calls = []

    def generate(self, schema, system, data, *, reuse_model=False):
        self.calls.append((system,data))
        return self.rendered


class OwnerVoiceTests(TestCase):
    def test_rizon_recipient_example_becomes_direct_address(self):
        line = ("Rizon أرسلت إيميل ترويجي لبيتر عن تفعيل ETFs والأسهم العالمية "
                "(مثل S&P 500 وApple)، مع إمكانية البدء بـ $1 فقط.")
        output = owner_voice(line)
        self.assertIn("إيميل ترويجي لك",output)
        self.assertNotIn("لبيتر",output)
        self.assertIn("$1",output)
        self.assertIn("S&P 500",output)

    def test_does_not_erase_genuine_other_people_or_modify_subject_facts(self):
        for source in [
            "محمد شارك منشورًا عن بيتر، واستعرض مشروعه.",
            "بيتر فاز بجائزة في المؤتمر.",
            "الأستاذ بيتر هو المتحدث التالي.",
            "Peter reviewed the article about Peter.",
        ]:
            self.assertEqual(owner_voice(source),source)

    def test_owner_voice_applies_to_short_ai_output(self):
        source=MagicMock(id="aa",sender="Rizon",subject="ETFs",body="Hello",
                         body_total_chars=5,truncated=False,attachment_count=0)
        model=SyntheticOwnerModel(InsightPayload(
            category="low_priority",
            summary="Rizon أرسلت إيميل ترويجي لبيتر عن ETFs.",
            suggested_action="يمكن لبيتر مراجعة العرض."
        ))
        output=model.summarize(source)
        self.assertEqual(output.source_id,"aa")
        self.assertIn("إيميل ترويجي لك",output.summary)
        self.assertNotIn("لبيتر",output.suggested_action)
        self.assertIn("addressed DIRECTLY",model.calls[0][0])

    def test_stored_ai_summary_is_rephrased_only_for_display(self):
        insight=('{"category":"low_priority","summary":'
                 '"Rizon أرسلت إيميل ترويجي لبيتر عن ETFs.",'
                 '"suggested_action":"يمكن لبيتر مراجعة العرض.",'
                 '"source_id":"aa"}')
        row={"insight":insight}

        @contextmanager
        def fake_connection():
            db=MagicMock()
            db.execute.return_value.fetchone.return_value=row
            yield db

        store=MagicMock()
        store.connect.side_effect=fake_connection
        with patch("okal_core.mail.viewer.config",return_value=MagicMock(
                owner_name="بيتر")):
            result=saved_analysis(store,"owner@example.com","aa")
        self.assertIn("لك",result["ai_summary"])
        self.assertNotIn("لبيتر",result["ai_summary"])
        self.assertEqual(row["insight"],insight) # no rewrite persisted
