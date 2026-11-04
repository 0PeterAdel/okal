"""Natural owner requests can propose actions; quoted documents never dispatch."""

import re

from .engine import Engine

ACTION = re.compile(
    r"\b(?:organize|move|rename|copy|delete|trash|download|browse|research|open|launch|focus)\b|"
    r"\b(?:read|compare|summarize|find|search|create|write|prepare|draft)\b.{0,100}\b(?:files?|folders?|documents?|reports?|tasks?|workspace|directory|emails?|repl(?:y|ies))\b|"
    r"(?:جهز|جهّز|اكتب|نظم|نظّم|رتب|رتّب|انقل|انسخ|احذف|افتح|شغل|شغّل|ابحث|اقرأ|اقرا|قارن|لخص|لخّص|أنشئ|انشئ).{0,100}"
    r"(?:ملف|مجلد|تقارير|تقرير|مستند|متصفح|برنامج|مهمة|مهام|مساحة|بريد|إيميل|رد)",
    re.I,
)


def propose_for_chat(store, conversation_id, request_id, message):
    if re.search(r"^(?:continue|resume|كمل|كمّل|استكمل)\b", message.strip(), re.I):
        engine = Engine(store)
        previous = engine.history(conversation_id)["items"]
        if previous:
            return {
                "answer": "Previous action / الإجراء السابق: " + previous[0]["status"],
                "action_run": previous[0]["id"],
                "proposal": None,
                "mode": "action_plan",
                "saved": False,
                "voice_enabled": False,
                "source": "durable_action_receipt",
            }
    if not ACTION.search(message):
        return None
    engine = Engine(store)
    if not engine.policy()["policy"]["tools"]:
        return {
            "answer": "Computer actions need explicit permissions first. Open Actions / صلاحيات الكمبيوتر to grant tools and specific folders.",
            "proposal": None,
            "mode": "action_plan",
            "saved": False,
            "voice_enabled": False,
            "source": "action_permission_policy",
        }
    try:
        run = engine.propose(conversation_id, request_id, message)
        return {
            "answer": run["plan"]["understanding"],
            "action_run": run["id"],
            "proposal": None,
            "mode": "action_plan",
            "saved": False,
            "voice_enabled": False,
            "source": "proposed_action_plan",
        }
    except (ValueError, OSError):
        return {
            "answer": "The action plan was not executed. Check the configured scope and tool readiness, then revise the request.",
            "proposal": None,
            "mode": "action_plan",
            "saved": False,
            "voice_enabled": False,
            "source": "action_plan_unavailable",
        }
