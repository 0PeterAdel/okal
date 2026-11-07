"""Natural owner requests can propose actions; quoted documents never dispatch."""

import re

from .engine import Engine
from .contracts import Plan, Step

# Only explicit owner-directed machine questions use a deterministic read-only
# status plan. Casual uses of "space" or "disk" in unrelated topics do not.
DEVICE_STATUS = re.compile(
    r"\\b(?:how many|number of|list|show|check|what(?:'s| is)?|free|available)\\b"
    r".{0,65}\\b(?:disks?|drives?|storage|disk space|hard drives?|mounted drives?)\\b|"
    r"\\b(?:lsblk|df -h|disk usage|storage capacity|disk capacity)\\b|"
    r"(?:كام|كم|عدد|اعرض|وريني|شوف|المساحة|مساحة|متوصل|متوصلة).{0,65}"
    r"(?:هارد|هاردات|الهارد|الأقراص|الاقراص|ديسك|ديسكات|مساحة التخزين|مساحة الجهاز)|"
    r"(?:مساحة|سعة).{0,35}(?:هارد|تخزين|الهارد|القرص|الهاردات)",
    re.I,
)

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
    device_status = bool(DEVICE_STATUS.search(message))
    if not (device_status or ACTION.search(message)):
        return None
    engine = Engine(store)
    enabled = engine.policy()["policy"]["tools"]
    if device_status and "system.status" not in enabled:
        return {
            "answer": "معلومات الجهاز تحتاج تفعيل system.status من Actions / صلاحيات الكمبيوتر. مش هخمن عدد الأقراص أو المساحة.",
            "proposal": None,
            "mode": "action_plan",
            "saved": False,
            "voice_enabled": False,
            "source": "action_permission_policy",
        }
    if not enabled:
        return {
            "answer": "Computer actions need explicit permissions first. Open Actions / صلاحيات الكمبيوتر to grant tools and specific folders.",
            "proposal": None,
            "mode": "action_plan",
            "saved": False,
            "voice_enabled": False,
            "source": "action_permission_policy",
        }
    try:
        explicit_plan = (
            Plan(
                understanding="هفحص الأقراص ومساحة التخزين من الجهاز نفسه، وأعرض نتيجة موثقة بدون تغيير أي ملف.",
                steps=[Step(tool="system.status", arguments={})],
            )
            if device_status else None
        )
        run = engine.propose(conversation_id, request_id, message, plan=explicit_plan)
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
