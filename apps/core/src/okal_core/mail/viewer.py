"""On-demand full Gmail message viewer: read-only, bounded and source-verified.

No Mail AI summary body is mistaken for an original email. The browser opens
a sandboxed, script-disabled iframe and remote image URLs remain blocked unless
the user explicitly opts in for the current viewed message. CID inline images
are resolved via authenticated Gmail attachment reads and embedded as data URLs.
"""
import base64
from html import unescape
from email.header import decode_header, make_header
from email.message import Message as EmailMessage
import json
import re
from urllib.parse import quote, unquote

from .contracts import MailError
from .private import config
from .provider import Gmail

ID = re.compile(r"^[a-fA-F0-9]{1,64}$")
SAFE_IMAGE = {"image/png", "image/jpeg", "image/webp", "image/gif", "image/avif"}
MAX_HTML = 1_500_000
MAX_TEXT = 2_000_000
MAX_IMAGE = 1_500_000
MAX_EMBEDDED_TOTAL = 5_000_000
MAX_PARTS = 100


def _decode_b64(value, maximum):
    if not isinstance(value, str) or len(value) > maximum * 2:
        raise MailError("viewer_part_exceeds_budget")
    try:
        out = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except (ValueError, base64.binascii.Error):
        raise MailError("viewer_invalid_mime_encoding") from None
    if len(out) > maximum:
        raise MailError("viewer_part_exceeds_budget")
    return out


def _text(data, maximum, mime_charset="utf-8"):
    raw = _decode_b64(data, maximum)
    charset = (mime_charset or "utf-8").strip().lower()
    if not re.fullmatch(r"[a-z0-9._-]{1,50}", charset):
        charset = "utf-8"
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def _mime_text(api, mid, part, maximum):
    body = part.get("body", {})
    size = body.get("size", 0)
    if not isinstance(size, int) or size < 0 or size > maximum:
        raise MailError("viewer_part_exceeds_budget")
    data = body.get("data")
    if data is None and body.get("attachmentId"):
        attachment_id = body["attachmentId"]
        if not isinstance(attachment_id, str) or not re.fullmatch(
            r"[A-Za-z0-9_-]{1,1024}", attachment_id
        ):
            raise MailError("viewer_invalid_attachment_id")
        remote = api.call(
            api.service.users().messages().attachments().get(
                userId="me", messageId=mid, id=attachment_id,
            ),
            missing="viewer_text_part_unavailable",
        )
        data = remote.get("data")
    if data is None:
        return ""
    header = EmailMessage()
    content_type = _header(part.get("headers", []), "Content-Type")
    header["Content-Type"] = content_type or part.get("mimeType", "text/plain")
    return _text(data, maximum, header.get_content_charset("utf-8"))


def _header(headers, label):
    for header in headers:
        if str(header.get("name", "")).casefold() == label.casefold():
            value = str(header.get("value", ""))[:4096]
            try:
                return str(make_header(decode_header(value)))[:1000]
            except (ValueError, UnicodeError):
                return value[:1000]
    return ""


def allowed_source(store, account, mid):
    if not isinstance(mid, str) or not ID.fullmatch(mid):
        raise MailError("viewer_invalid_message_id")
    with store.connect() as db:
        tables = {row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        if "mail_sync_insights" in tables:
            row = db.execute(
                "SELECT metadata FROM mail_sync_insights WHERE account=? "
                "AND message_id=? LIMIT 1", (account, mid)
            ).fetchone()
            if row is not None:
                try:
                    meta = json.loads(row["metadata"])
                    if meta.get("id") == mid:
                        return meta
                except (TypeError, ValueError):
                    pass
        # Quarantined messages remain openable for human review.
        if "mail_sync_quarantine" in tables:
            row = db.execute(
                "SELECT 1 FROM mail_sync_quarantine WHERE account=? AND message_id=? "
                "LIMIT 1", (account, mid)
            ).fetchone()
            if row:
                return None
    raise MailError("viewer_source_not_in_local_inbox")


def saved_analysis(store, account, mid):
    """Keep AI commentary clearly separate from the original Gmail message."""
    from .contracts import Insight

    with store.connect() as db:
        row = db.execute(
            "SELECT insight FROM mail_sync_insights WHERE account=? "
            "AND message_id=? ORDER BY rowid DESC LIMIT 1",
            (account, mid),
        ).fetchone()
    if row is None:
        return {
            "ai_summary": "الرسالة محتاجة مراجعة يدوية؛ مفيش تلخيص AI موثوق محفوظ.",
            "ai_suggested_action": "", "ai_category": "manual_review",
        }
    try:
        insight = Insight.model_validate_json(row["insight"])
        if insight.source_id != mid:
            raise ValueError("invalid_source")
        from .owner_voice import owner_voice
        owner = config(store).owner_name
        return {
            "ai_summary": owner_voice(insight.summary, owner)[:900],
            "ai_suggested_action": owner_voice(insight.suggested_action, owner)[:400],
            "ai_category": insight.category,
        }
    except (ValueError, TypeError):
        raise MailError("viewer_saved_ai_source_invalid") from None


def read_native(store, mid):
    cfg = config(store)
    account = cfg.account.casefold()
    saved = allowed_source(store, account, mid)
    api = Gmail.open(store, cfg)
    try:
        mail = api.call(
            api.service.users().messages().get(
                userId="me", id=mid, format="full"
            ), missing="viewer_message_missing_in_gmail"
        )
        if mail.get("id") != mid:
            raise MailError("viewer_native_message_mismatch")
        if int(mail.get("sizeEstimate", 0)) > 9_000_000:
            raise MailError("viewer_message_too_large_open_gmail")
        payload = mail.get("payload")
        if not isinstance(payload, dict):
            raise MailError("viewer_missing_mime_payload")
        headers = payload.get("headers", [])
        if not isinstance(headers, list):
            raise MailError("viewer_missing_mime_payload")
        subject = _header(headers, "Subject")
        if saved is not None and subject != saved.get("subject"):
            raise MailError("viewer_source_changed_refresh_gmail")
        sender = _header(headers, "From")
        recipient = _header(headers, "To")
        date = _header(headers, "Date")
        plain, html = "", ""
        images = {}
        location_images = {}
        attachments = []
        skipped_images = 0
        used, count = 0, 0
        stack = [payload]
        while stack:
            part = stack.pop()
            count += 1
            if count > MAX_PARTS:
                raise MailError("viewer_mime_too_complex")
            if not isinstance(part, dict):
                continue
            parts = part.get("parts", [])
            if isinstance(parts, list):
                stack.extend(reversed(parts[:MAX_PARTS]))
            kind = str(part.get("mimeType", "")).split(";", 1)[0].lower()
            body = part.get("body", {})
            if not isinstance(body, dict):
                continue
            if kind == "text/html" and not html:
                html = _mime_text(api, mid, part, MAX_HTML)
            elif kind == "text/plain" and not plain:
                plain = _mime_text(api, mid, part, MAX_TEXT)
            elif kind in SAFE_IMAGE:
                part_headers = part.get("headers", [])
                content_id = _header(part_headers, "Content-ID").strip("<>")
                content_location = _header(part_headers, "Content-Location").strip()
                estimated = int(body.get("size") or 0)
                if estimated > MAX_IMAGE or used + estimated > MAX_EMBEDDED_TOTAL:
                    skipped_images += 1
                    if not content_id and not content_location:
                        attachments.append({
                            "name": str(part.get("filename") or "Large image")[:180],
                            "mime_type": kind, "inline": False,
                            "too_large_for_preview": True,
                        })
                    continue
                if body.get("data"):
                    raw = _decode_b64(body["data"], MAX_IMAGE)
                elif body.get("attachmentId"):
                    raw_response = api.call(
                        api.service.users().messages().attachments().get(
                            userId="me", messageId=mid,
                            id=str(body["attachmentId"])
                        ), missing="viewer_inline_image_missing"
                    )
                    raw = _decode_b64(raw_response.get("data", ""), MAX_IMAGE)
                else:
                    continue
                if used + len(raw) > MAX_EMBEDDED_TOTAL:
                    skipped_images += 1
                    continue
                used += len(raw)
                data_url = ("data:" + kind + ";base64," +
                            base64.b64encode(raw).decode("ascii"))
                if content_id:
                    images[unquote(unescape(content_id)).casefold()] = data_url
                if (content_location and len(content_location) <= 1000
                        and content_location.startswith(("https://", "http://"))):
                    location_images[unescape(content_location)] = data_url
                if not content_id and not content_location:
                    attachments.append({
                        "name": str(part.get("filename") or "Attached image")[:180],
                        "mime_type": kind, "inline": False, "data_url": data_url,
                    })
            elif part.get("filename"):
                attachments.append({
                    "name": str(part.get("filename", ""))[:180],
                    "mime_type": kind[:100], "inline": False,
                })

        # Resolve quoted, unquoted and URL-encoded CID images inside
        # sandboxed HTML (including inline CSS url(cid:...)). This also
        # handles Content-ID: <foo@domain> and cid:foo%40domain variants.
        def replace_cid(match):
            original = match.group(0)
            cid = unquote(unescape(match.group(1))).strip("<>").casefold()
            return images.get(cid, original)

        # Some multipart/related senders reference the image by its exact
        # Content-Location URL instead of cid:. Local bytes take priority
        # over requesting a remote URL, even with remote images disabled.
        def replace_location(match):
            original = match.group(0)
            url = unescape(match.group("url"))
            image = location_images.get(url)
            return (match.group("prefix") + image + match.group("quote")
                    if image else original)

        if html:
            html = re.sub(
                r"(?i)cid:(<[^<>]{1,512}>|[^\s\"'<>),;]{1,512})",
                replace_cid, html
            )
            if location_images:
                html = re.sub(
                    r"(?i)(?P<prefix>\b(?:src|background)\s*=\s*"
                    r"(?P<quote>['\"]))(?!data:)(?P<url>https?://[^\"']+)(?P=quote)",
                    replace_location, html
                )
        if len(html.encode("utf-8")) > 8_000_000:
            raise MailError("viewer_html_with_images_too_large")
        commentary = saved_analysis(store, account, mid)
        return {
            **commentary,
            "id": mid, "subject": subject, "from": sender, "to": recipient,
            "date": date, "html": html, "text": plain,
            "labels": [label for label in mail.get("labelIds", [])
                       if isinstance(label,str)][:40],
            "inline_images": len(images) + len(location_images),
            "skipped_inline_images": skipped_images,
            "external_images_detected": bool(re.search(
                r"(?i)\b(?:src|srcset|data-src|data-original|data-lazy-src|data-srcset|data-lazy-srcset|background|data-background)"
                r"\s*=\s*['\"]?(?:https?://|//)|"
                r"url\(\s*['\"]?(?:https?://|//)",
                html
            )),
            "attachments": attachments[:30],
            "remote_images_blocked_by_default": False,
            "remote_images_enabled_on_open": True,
            "source": "native_gmail_full_message_read_on_demand",
            "gmail_link": "https://mail.google.com/mail/?authuser=" +
            quote(account, safe="") + "#all/" + mid,
        }
    finally:
        api.close()
