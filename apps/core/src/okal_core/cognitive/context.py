"""Narrow personalization policy; memory never acquires tool authority."""
import re

LANGUAGE = re.compile(
    r'\b(?:answer|reply|respond|speak|talk|write|use)(?:\s+\w+){0,5}?\s+(?:in\s+)?'
    r'(Egyptian Arabic|English|Arabic)\b|'
    r'\b(English|Egyptian Arabic|Arabic)\s+(?:please|only)\b|'
    r'(بالمصري|بالعربي المصري|بالإنجليزي|بالانجليزي|بالعربي|باللغة العربية)', re.I)


def language_in(value):
    match = LANGUAGE.search(value)
    if not match:
        stripped = value.strip().casefold()
        return {'english': 'English', 'arabic': 'Arabic', 'egyptian arabic': 'Egyptian Arabic'}.get(stripped)
    result = next(v for v in match.groups() if v is not None).casefold()
    if result in {'english', 'بالإنجليزي', 'بالانجليزي'}:
        return 'English'
    if result in {'egyptian arabic', 'بالمصري', 'بالعربي المصري'}:
        return 'Egyptian Arabic'
    return 'Arabic'


def reply_language(message, memories):
    explicit = language_in(message)
    if explicit:
        return explicit
    language_keys={'communication.language','communication.language.technical_docs','language','preferred language'}
    candidates=[m for m in memories if m.get('key') in language_keys]
    # Retrieval orders scopes by authority. Within one scope, a matching
    # conditional preference is more specific than its general default.
    scopes=list(dict.fromkeys(m.get('scope','owner') for m in candidates))
    technical=bool(re.search(r'document|docs?\b|توثيق|مستند',message,re.I))
    for scope in scopes:
        grouped=[m for m in candidates if m.get('scope','owner')==scope]
        def conditional(m):
            return m['key'].endswith('.technical_docs') or bool(re.search(r'technical doc|documentation|التوثيق|توثيق',m['content'],re.I))
        for memory in sorted(grouped,key=lambda m:not conditional(m)):
            if conditional(memory) and not technical:continue
            language=language_in(memory['content'])
            if language:return language
    return 'Egyptian Arabic' if re.search(r'[\u0600-\u06ff]', message) else 'English'


def reply_style(message,memories):
    def detect(value):
        if re.search(r'(?:avoid|do not|don.t|no|مش عايز).{0,25}(?:long|detailed|introduction|مقدم|طويل)',value,re.I):return 'brief'
        if re.search(r'(?:avoid|do not|don.t|not|مش عايز).{0,20}(?:brief|concise|short|مختصر)',value,re.I):return 'detailed'
        if re.search(r'\b(?:brief|concise|short|direct)\w*\b|مختصر|موجز|باختصار|اختصر|مباشر|قصير|الموضوع على طول',value,re.I):return 'brief'
        if re.search(r'\b(?:detailed|in detail|background explanation)\b|بالتفصيل|ردود طويلة|مفصل|مفصّل|مطول|مطوّل',value,re.I):return 'detailed'
    if not re.search(r'[?؟]',message) and re.search(r'please|answer|reply|explain|عايز|جاوب|رد',message,re.I):
        current=detect(message)
        if current:return current
    for memory in memories:
        if memory.get('key') in {'communication.style','communication.language','communication.structure'}:
            style=detect(memory['content'])
            if style:return style
    return 'default'


def preference_question_focus(message):
    """Trusted task guidance for broad recall questions, never memory authority."""
    if re.search(r'my name|owner name|what name.*(?:tell|remember)|address me|'
                 r'اسمي|الاسم الذي|تناديني',message,re.I):
        return ('This question asks for the owner-stated name. Quote the exact remembered '
                'profile.name statement if available. Preserve the original spelling verbatim, '
                'including Latin letters inside an Arabic answer; never transliterate or guess. ')
    if (re.search(r'language|dialect|لغة|لهج|لغوي',message,re.I)
            and re.search(r'\b(?:me|my|normally|default|prefer)\b|تكلمني|تحدثني|أسلوبي|أفض|لغتي',message,re.I)):
        return ('This question asks for the remembered reply language or dialect. State the '
                'applicable communication.language preference and its exceptions if remembered. '
                'Keep response length preferences separate and attribute the preference to the owner. ')
    if (re.search(r'introduction|background|response length|ردود|مختصر|مقدمة|تصحيح.*الرد',message,re.I)
            and re.search(r'\b(?:me|my|i|prefer|latest)\b|أنا|عايز|بحب|فاكر',message,re.I)):
        return ('This question asks about response length or introductory/background text in '
                'your answers. Use the latest communication.style statement if remembered. '
                'A preference for brief, direct replies concerns introductory text too. '
                'Interpret introductions as the beginning of your replies, and attribute the preference to the owner. ')
    if re.search(r'how.*(?:communicat|talk|speak)|communication (?:style|preferences)|'
                 r'(?:تكلمني|تكلّمني|تحدثني).*(?:إزاي|ازاي|كيف)|طريقة (?:الرد|الكلام)',message,re.I):
        return ('This question asks about saved communication preferences. Explicitly mention BOTH '
                'the remembered default language and the latest response style when available. '
                'Attribute them to the owner: say "you prefer" or "أنت بتفضل", never "I want". ')
    return ''
