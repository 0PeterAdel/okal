"""Long Gmail content must be summarizable without automatic manual quarantine.

Synthetic 6–110k-character messages and an injected deterministic local model.
No external Gmail or Ollama requests, and no real user messages.
"""
import base64
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock

from okal_core.mail.contracts import Config, InsightPayload, MailError
from okal_core.mail.history import HistoryState, run, recent_quarantines, recent_evidence
from okal_core.mail.inference import (
    LocalModel, _bounded_email_sections, LONG_EMAIL_MAX_CHUNKS
)
from okal_core.mail.provider import parse_full, Gmail
from okal_core.store import Store


def raw_message(body, mid="ab"):
    encoded=base64.urlsafe_b64encode(body.encode("utf-8")).decode()
    return {
        "id":mid,"threadId":"ff","internalDate":"1800000000000",
        "labelIds":["INBOX","UNREAD"],
        "payload":{
            "mimeType":"text/plain",
            "headers":[
                {"name":"From","value":"Sender <sender@example.com>"},
                {"name":"To","value":"owner@example.com"},
                {"name":"Subject","value":"Very long report"},
                {"name":"Message-ID","value":"<report@example.com>"},
                {"name":"Content-Type","value":"text/plain; charset=UTF-8"},
            ],
            "body":{"data":encoded,"size":len(body.encode("utf-8"))}
        }
    }


class ModelHarness(LocalModel):
    def __init__(self):
        self.calls=[]

    def generate(self,schema,system,data,*,reuse_model=False):
        self.calls.append((system,data,reuse_model))
        # All outputs come from a hypothetical local GGUF, never internet.
        return InsightPayload(category="action",summary="تقرير يحتاج مراجعة",
                              suggested_action="راجع التقرير الأصلي")


class LongMailTests(unittest.TestCase):
    def test_message_of_twelve_thousand_characters_is_no_longer_truncated(self):
        body="تقرير الشركة وتحديثاتها. "*560
        message=parse_full(raw_message(body))
        self.assertGreater(len(message.body),8000)
        self.assertFalse(message.truncated)
        self.assertEqual(message.body_total_chars,len(body.strip()))
        model=ModelHarness()
        result=model.summarize(message)
        self.assertEqual(result.source_id,"ab")
        self.assertNotIn("ملخص جزئي",result.summary)
        self.assertGreater(len(model.calls),1)
        self.assertEqual(model.calls[-1][1]["source_coverage_partial"],False)
        self.assertTrue(all(len(call[1].get("body_excerpt",""))<=2800
                            for call in model.calls))

    def test_too_long_for_one_context_gets_bounded_map_reduce_and_disclosure(self):
        body=("GitHub workflow notification: review PR and status.\n"*3000)
        message=parse_full(raw_message(body))
        self.assertTrue(message.truncated)
        self.assertEqual(len(message.body),96000)
        self.assertEqual(message.body_total_chars,len(body))
        model=ModelHarness()
        result=model.summarize(message)
        self.assertEqual(len(model.calls),LONG_EMAIL_MAX_CHUNKS+1)
        self.assertTrue(result.summary.startswith("ملخص جزئي"))
        self.assertLessEqual(len(result.summary),240)
        self.assertTrue(model.calls[-1][1]["source_coverage_partial"])
        self.assertLess(model.calls[-1][1]["examined_chars"],len(body))
        self.assertFalse(model.calls[-1][2])
        self.assertTrue(all(x[2] for x in model.calls[:-1]))

    def test_inline_text_attachment_is_read_only_and_does_not_fetch_files(self):
        body="Long native plain email text. "*600
        row=raw_message(body)
        encoded=row["payload"]["body"]["data"]
        row["payload"]["body"]={"attachmentId":"body123","size":len(body)}
        # Gmail often returns long message content in MIME attachmentId.
        service=MagicMock()
        get=service.users.return_value.messages.return_value.get
        get.return_value.execute.return_value=row
        attachments=service.users.return_value.messages.return_value.attachments
        attachments.return_value.get.return_value.execute.return_value={"data":encoded}
        api=Gmail(service)
        fetched=api.get_optional("ab")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.body_total_chars,len(body.strip()))
        self.assertFalse(fetched.truncated)
        self.assertEqual(attachments.return_value.get.call_count,1)
        self.assertEqual(attachments.return_value.get.call_args.kwargs["messageId"],"ab")
        # Standalone pure parser never fetches attachment bytes implicitly.
        with self.assertRaisesRegex(MailError,"body_requires_attachment_fetch_manual_review"):
            parse_full(row)

    def test_small_message_uses_single_pass_and_preserves_source_identity(self):
        message=parse_full(raw_message("Please review the attached draft."))
        model=ModelHarness()
        result=model.summarize(message)
        self.assertEqual(result.source_id,"ab")
        self.assertEqual(len(model.calls),1)
        self.assertEqual(model.calls[0][1]["body"],message.body)

    def test_section_sampler_includes_end_of_oversized_mail(self):
        text="A"*10000+"MID"*12000+"Z"*10000
        chunks,partial,covered=_bounded_email_sections(text)
        self.assertTrue(partial)
        self.assertEqual(len(chunks),8)
        self.assertTrue(chunks[0].startswith("AAA"))
        self.assertTrue(chunks[-1].endswith("ZZZ"))
        self.assertLess(covered,len(text))

    def test_preexisting_long_quarantine_is_repaired_without_duplicate_seen(self):
        now=[1800000000]
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store=Store(Path(tmp.name)/"state",clock=lambda:now[0])
        cfg=Config(account="owner@example.com",model="local:test",
                   model_digest="a"*64,sync_enabled=True)
        state=HistoryState(store)
        api=MagicMock()
        api.history_marker.return_value="100"
        api.collect.return_value=[]
        api.history_changes.return_value=("101",[],0)
        api.get_optional.return_value=parse_full(raw_message("Action note. "*1000))
        api.check_account.return_value=None
        api.message_visibility.return_value="present"
        model=MagicMock()
        model.summarize.return_value=__import__(
            "okal_core.mail.contracts",fromlist=["Insight"]).Insight(
                source_id="ab",category="action",summary="مراجعة تقرير",
                suggested_action="فتح التقرير"
        )
        result=run(store,cfg,api,model)
        self.assertEqual(result["processed"],0)
        with store.connect() as db,db:
            db.execute(
                "INSERT INTO mail_sync_quarantine VALUES(?,?,?,?)",
                (cfg.account,"ab",
                 "message_body_truncated_narrow_scope_or_review_manually",
                 now[0])
            )
            db.execute("INSERT INTO mail_sync_seen VALUES(?,?)",
                       (cfg.account,"ab"))
        now[0]+=3600
        second=run(store,cfg,api,model)
        self.assertEqual(second["processed"],1)
        self.assertEqual(recent_quarantines(store,cfg.account),[])
        self.assertEqual(len(recent_evidence(store,cfg.account)),1)
        self.assertEqual(state.seen(cfg.account,["ab"]),{"ab"})
        now[0]+=3600
        third=run(store,cfg,api,model)
        self.assertEqual(third["processed"],0)
        self.assertEqual(model.summarize.call_count,1)
        # No repeated Gmail lookup after successful re-analysis.
        self.assertEqual(api.get_optional.call_count,1)


if __name__=="__main__":
    unittest.main()
