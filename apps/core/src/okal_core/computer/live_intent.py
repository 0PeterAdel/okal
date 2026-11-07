"""Bounded owner-request interpretation for live public facts.

This is a *routing hint*, not an authorization, search result or LLM response.
No user account content, memory or previous tool output can trigger public I/O.
"""
from dataclasses import dataclass
import re


WEATHER = re.compile(
    r"(?:\bweather\b|\btemperature\b|درجة\s+الحرار(?:ة|ه)|"
    r"الحرار(?:ة|ه)|الطقس|طقس|حالة\s+الجو|الجو\s+(?:عامل|عاملة|إيه|ايه|كيف))",
    re.I,
)
HARDWARE_TEMP = re.compile(
    r"(?:cpu|gpu|المعالج|البروسيسور|كارت\s*الشاشة|الهارد|البطارية|"
    r"درجة\s+حرارة\s+الجهاز|جهازي|اللابتوب|laptop)",
    re.I,
)
DAY = re.compile(r"(?:بكرة|بكره|غد(?:ا|ً)?|tomorrow)", re.I)
RIYAL = re.compile(r"(?:ريال|riyal|\bsar\b)", re.I)
EGP = re.compile(r"(?:جنيه\s*(?:مصري)?|مصري|egyptian|\begp\b)", re.I)
EXPLICIT_PAIR = re.compile(
    r"(?:مقابل|قدام|بالدولار|بالجنيه|باليورو|to\s+(?:egp|usd|eur)|"
    r"against|versus|\b(?:usd|eur|egp)\b)",
    re.I,
)
FRESH_RATE = re.compile(
    r"(?:سعر|بكام|كام|صرف|تحويل|exchange|price|rate|today|اليوم|"
    r"النهارده|النهاردة|دلوقتي|الآن|الان)",
    re.I,
)
BROWSE_VERB = re.compile(
    r"^\s*(?:بروس|بروز|براوز|browse)(?:\s|[،,:؟?])",
    re.I,
)
CITY_AFTER_IN = re.compile(
    r"(?:\b(?:in|at)\s+|(?:في|داخل)\s+)([\u0600-\u06ffa-zA-Z][\u0600-\u06ffa-zA-Z\s-]{1,55})",
    re.I,
)
CITY_AFTER_WEATHER = re.compile(
    r"(?:\bweather\s+|\btemperature\s+(?:at|in)\s+|(?:الطقس|طقس)\s+)"
    r"([\u0600-\u06ffa-zA-Z][\u0600-\u06ffa-zA-Z\s-]{1,55})",
    re.I,
)
PLACE_STOP = re.compile(
    r"\s+(?:كام|النهاردة|النهارده|النهاردة|اليوم|دلوقتي|حالياً|حاليا|"
    r"الآن|الان|بكرة|بكره|غدا|بالتفصيل|today|now|tomorrow|right now)\b.*$",
    re.I,
)
UNSPECIFIED = {
    "المكان", "المدينة", "مدينتي", "الموقع", "عندي", "هنا", "الجو",
    "مصر", "egypt", "my city", "here", "my location", "البلد",
    "تمام", "خلاص", "لأ", "لا", "cancel", "شكرا", "شكرًا",
    "اليوم", "النهاردة", "النهارده", "دلوقتي", "هنا", "بلدي", "في بلدي",
}


@dataclass(frozen=True)
class LiveIntent:
    kind: str
    query: str = ""
    answer: str = ""


def _place(message, followup=False):
    text = message.strip().strip(" .،؛؟?!")
    found = CITY_AFTER_IN.search(text) or CITY_AFTER_WEATHER.search(text)
    candidate = found.group(1) if found else (text if followup else "")
    candidate = PLACE_STOP.sub("", candidate).strip(" ،.؟?!")
    if candidate.startswith("مدينة "):
        candidate = candidate[6:]
    if (not candidate or len(candidate) > 48 or len(candidate.split()) > 4
            or candidate.casefold() in UNSPECIFIED
            or re.search(r"\d|[/:@]", candidate)):
        return ""
    # A follow-up consists solely of the city, not an arbitrary instruction.
    if followup and re.search(r"(?:ابحث|افتح|نفذ|شغل|بروس|browse|http)", candidate, re.I):
        return ""
    return candidate


def live_intent(message, *, weather_followup=False):
    """Identify a current public-data question; never return observed facts."""
    if not isinstance(message, str) or not message.strip() or len(message) > 900:
        return None
    text = message.strip()
    weather = bool(WEATHER.search(text)) and not HARDWARE_TEMP.search(text)
    if weather or (weather_followup and len(text) <= 70):
        city = _place(text, followup=not weather)
        if not city and not weather:
            # A new, unrelated short owner turn cancels the pending city slot.
            return None
        if not city:
            return LiveIntent(
                kind="location_required",
                answer="أقدر أبحث عن درجة الحرارة الحالية، بس في أنهي مدينة؟ "
                       "قول اسم المدينة بس (مثلاً: أسيوط أو القاهرة) وهجيب معلومات من مصدر ويب فعلي.",
            )
        period = "غدًا" if DAY.search(text) else "اليوم"
        return LiveIntent(
            kind="weather_search",
            query=f"درجة الحرارة حالة الطقس {city} {period}",
        )
    if RIYAL.search(text) and FRESH_RATE.search(text):
        if not EXPLICIT_PAIR.search(text) and not EGP.search(text):
            return LiveIntent(
                kind="rate_search",
                query="سعر الريال السعودي مقابل الجنيه المصري اليوم SAR EGP",
                answer="هبحث عن سعر الريال السعودي مقابل الجنيه المصري باعتباره المقصود؛ لو تقصد عملة تانية قولّي.",
            )
        # Keep explicitly requested currencies; never change USD/EUR to EGP.
        return LiveIntent(kind="rate_search", query=text[:180])
    return None


def public_search_query(message):
    """Remove conversational browser preamble, not private owner content."""
    text = BROWSE_VERB.sub("", message.strip(), count=1).strip(" ،.؟?!")
    text = re.sub(r"^(?:كدا|كده)?\s*(?:و?شوف(?:لي)?|دور(?:لي)?|ابحث)\s*", "", text)
    return (text or message).strip()[:180]
