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
    for memory in memories:
        if memory.get('key') not in {'communication.language', 'language', 'preferred language'}:
            continue
        content = memory['content']
        if (re.search(r'technical doc|documentation|التوثيق|توثيق', content, re.I)
                and not re.search(r'document|docs?\b|توثيق|مستند', message, re.I)):
            continue
        language = language_in(content)
        if language:
            return language
    return 'Egyptian Arabic' if re.search(r'[\u0600-\u06ff]', message) else 'English'


def reply_style(message,memories):
    def detect(value):
        if re.search(r'(?:avoid|do not|don.t|no|مش عايز).{0,25}(?:long|detailed|introduction|مقدم|طويل)',value,re.I):return 'brief'
        if re.search(r'(?:avoid|do not|don.t|not|مش عايز).{0,20}(?:brief|concise|short|مختصر)',value,re.I):return 'detailed'
        if re.search(r'\b(?:brief|concise|short|direct)\w*\b|مختصر|الموضوع على طول',value,re.I):return 'brief'
        if re.search(r'\b(?:detailed|in detail|background explanation)\b|بالتفصيل|ردود طويلة',value,re.I):return 'detailed'
    if not re.search(r'[?؟]',message) and re.search(r'please|answer|reply|explain|عايز|جاوب|رد',message,re.I):
        current=detect(message)
        if current:return current
    for memory in memories:
        if memory.get('key')=='communication.style':
            style=detect(memory['content'])
            if style:return style
    return 'default'
