"""Owner-facing wording for one-user Gmail intelligence.

The analysis is addressed to the mailbox owner, never to a separate person.
Only explicitly marked *recipient* phrases are normalized; do not replace
legitimate reports ABOUT another person with the same name.
"""
import re


def owner_voice(text, name="بيتر"):
    if not isinstance(text, str):
        return text
    if not isinstance(name, str) or not name.strip():
        return text
    alias = name.strip()
    # Convert name only when it is a recipient of an email/notification.
    # Avoid rewriting "عن بيتر" and other third-party references.
    variants = [alias]
    first = alias.split()[0]
    if first != alias and len(first) >= 3:
        variants.append(first)
    # For this explicitly configured Egyptian-Arabic owner's first name,
    # English mail headers also often write Peter. No arbitrary names guessed.
    if first == "بيتر":
        variants.append("Peter")
    for target in sorted(set(variants), key=len, reverse=True):
        pattern = re.escape(target)
        if target == "Peter":
            # Arabic prefix "لـ" before the Latin given name.
            text = re.sub(
                r"(?:\bإلى\s+|\bلـ?\s*)" + pattern + r"(?![\w])",
                "لك" ,text,flags=re.IGNORECASE
            )
        else:
            # Recognize only mail recipient phrasing. Do not globally erase
            # the user's name from legitimate message content.
            text = re.sub(
                r"(?:\bإلى\s+|\bلـ?\s*)" + pattern + r"(?![\w\u0600-\u06ff])",
                "لك", text
            )
    return text
