"""On-demand full Gmail message viewer: read-only, bounded and source-verified.

No Mail AI summary body is mistaken for an original email. The browser opens
a sandboxed, script-disabled iframe and remote image URLs remain blocked unless
the user explicitly opts in for the current viewed message. CID inline images
are resolved via authenticated Gmail attachment reads and embedded as data URLs.
"""
import base64
from email.header import decode_header, make_header
import json
import re
from urllib.parse import quote

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


def _text(data, maximum):
    raw = _decode_b64(data, maximum)
    return raw.decode("utf-8", errors="replace")


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
        attachments = []
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
            if kind == "text/html" and not html and body.get("data"):
                html = _text(body["data"], MAX_HTML)
            elif kind == "text/plain" and not plain and body.get("data"):
                plain = _text(body["data"], MAX_TEXT)
            elif kind in SAFE_IMAGE:
                content_id = _header(part.get("headers", []), "Content-ID").strip("<>")
                estimated = int(body.get("size") or 0)
                if estimated > MAX_IMAGE or used + estimated > MAX_EMBEDDED_TOTAL:
                    if not content_id:
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
                    continue
                used += len(raw)
                data_url = ("data:" + kind + ";base64," +
                            base64.b64encode(raw).decode("ascii"))
                if content_id:
                    images[content_id.casefold()] = data_url
                else:
                    attachments.append({
                        "name": str(part.get("filename") or "Attached image")[:180],
                        "mime_type": kind, "inline": False, "data_url": data_url,
                    })
            elif part.get("filename"):
                attachments.append({
                    "name": str(part.get("filename", ""))[:180],
                    "mime_type": kind[:100], "inline": False,
                })

        # Replace CID image links with the fetched, verified MIME image bytes.
        # Images that are not present remain broken, not remote.
        def replace_cid(match):
            cid = match.group(2).strip("<>").casefold()
            data_url = images.get(cid)
            if not data_url:
                return match.group(0)
            return match.group(1) + data_url + match.group(3)

        if html:
            html = re.sub(
                r'(?i)(["\'])cid:([^"\'\s<>]+)(["\'])',
                replace_cid, html
            )
        if len(html.encode("utf-8")) > 8_000_000:
            raise MailError("viewer_html_with_images_too_large")
        return {
            "id": mid, "subject": subject, "from": sender, "to": recipient,
            "date": date, "html": html, "text": plain,
            "inline_images": len(images), "attachments": attachments[:30],
            "remote_images_blocked_by_default": True,
            "source": "native_gmail_full_message_read_on_demand",
            "gmail_link": "https://mail.google.com/mail/?authuser=" +
            quote(account, safe="") + "#all/" + mid,
        }
    finally:
        api.close()
