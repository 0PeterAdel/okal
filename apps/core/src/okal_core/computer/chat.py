"""Natural owner requests can propose actions; quoted documents never dispatch."""

import re
import shlex

from .engine import Engine
from .contracts import Plan, Step

# Only explicit owner-directed machine questions use a deterministic read-only
# status plan. Casual uses of "space" or "disk" in unrelated topics do not.
DEVICE_STATUS = re.compile(
    r"\b(?:how many|number of|list|show|check|what(?:'s| is)?|free|available)\b"
    r".{0,65}\b(?:disks?|drives?|storage|disk space|hard drives?|mounted drives?)\b|"
    r"\b(?:lsblk|df -h|disk usage|storage capacity|disk capacity)\b|"
    r"(?:كام|كم|عدد|اعرض|وريني|شوف|المساحة|مساحة|متوصل|متوصلة).{0,65}"
    r"(?:هارد|هاردات|الهارد|الأقراص|الاقراص|ديسك|ديسكات|مساحة التخزين|مساحة الجهاز)|"
    r"(?:مساحة|سعة).{0,35}(?:هارد|تخزين|الهارد|القرص|الهاردات)",
    re.I,
)

# Explicit web requests only: source content/assistant quotes never dispatch.
WEB_SEARCH = re.compile(
    r"\b(?:search (?:the )?web|search online|look up online|browse (?:the )?(?:web|internet)|google for|research online)\b|"
    r"(?:ابحث|إبحث|دور|دوّر|شوف|هات|تصفح|اتصفح).{0,70}(?:النت|الإنترنت|الانترنت|الويب|جوجل|اونلاين|أونلاين)|"
    r"(?:آخر|اخر|أحدث|احدث).{0,45}(?:الأخبار|الاخبار|أخبار|اخبار|تحديثات|تحديث)",
    re.I,
)
WEB_OPEN = re.compile(
    r"(?:\b(?:open|browse|read)\b|(?:افتح|تصفح|اقرأ|اقرا)).{0,80}(https://[^\s<>]+)",
    re.I,
)

# Direct literal owner command only; no free-form model-generated shell text.
OWNER_TERMINAL = re.compile(
    r"^\s*(?:run|execute|نفذ|نفّذ|شغل|شغّل)\s*"
    r"(?:command|الأمر|الامر)?\s*"
    r"(?:in (?:the )?terminal|في الترمينال|على الترمينال)?\s*[:：]\s*(.+)$",
    re.I | re.S,
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
    terminal = OWNER_TERMINAL.match(message)
    web_search = None if terminal else WEB_SEARCH.search(message)
    web_open = None if terminal else WEB_OPEN.search(message)
    device_status = bool(DEVICE_STATUS.search(message)) and not (web_search or web_open or terminal)
    if not (terminal or device_status or web_search or web_open or ACTION.search(message)):
        return None
    engine = Engine(store)
    enabled = engine.policy()["policy"]["tools"]
    required = (
        "system.terminal" if terminal else
        "browser.public_read" if web_open else
        "browser.search" if web_search else
        "system.status" if device_status else None
    )
    if required and required not in enabled:
        return {
            "answer": "الأداة " + required + " محتاجة تتفعل مرة واحدة من Actions / صلاحيات الكمبيوتر. مش هخمن نتيجة من الإنترنت أو جهازك.",
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
        explicit_plan = None
        if terminal:
            parts = shlex.split(terminal.group(1).strip().strip("`"))
            if not parts or len(parts) > 20:
                raise ValueError("invalid_owner_terminal_command")
            if not parts[0].startswith("/"):
                if not re.fullmatch(r"[a-zA-Z0-9_.+\-]{1,100}", parts[0]):
                    raise ValueError("absolute_usr_bin_command_required")
                parts[0] = "/usr/bin/" + parts[0]
            explicit_plan = Plan(
                understanding="الأمر اللي كتبته جاهز لمراجعتك؛ مش هيتنفذ إلا بعد موافقتك على argv بالضبط.",
                steps=[Step(tool="system.terminal", arguments={"argv": parts})],
            )
        elif device_status:
            explicit_plan = Plan(
                understanding="هفحص الأقراص ومساحة التخزين من الجهاز نفسه، وأعرض نتيجة موثقة بدون تغيير أي ملف.",
                steps=[Step(tool="system.status", arguments={})],
            )
        elif web_open:
            url = web_open.group(1).rstrip(".,،؛؟)")
            explicit_plan = Plan(
                understanding="هفتح صفحة HTTPS العامة للقراءة فقط؛ النتيجة من المتصفح الفعلي.",
                steps=[Step(tool="browser.public_read", arguments={"url": url})],
            )
        elif web_search:
            query = message[:180]
            explicit_plan = Plan(
                understanding="هبحث على الإنترنت عن طلبك وأعرض مصادر فعلية؛ الاستعلام بيُرسل لمحرك بحث خارجي.",
                steps=[Step(tool="browser.search", arguments={"query": query})],
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
