"""Google's official OAuth/API libraries behind a bounded Gmail adapter."""

import base64
from email import policy
from email.message import Message as HeaderMessage
from email.parser import BytesParser
from html.parser import HTMLParser
import json
import re
import time

from .contracts import MailError, Message
from .private import read_private, root, write_private

READ = "https://www.googleapis.com/auth/gmail.readonly"
SEND = "https://www.googleapis.com/auth/gmail.send"
RAW_LIMIT = 8 * 1024 * 1024


class GoogleTransport:
    """Official client's HTTP seam, without hidden retries or redirects.

    httplib2 may resend after BadStatusLine even with execute(num_retries=0).
    HTTPX defaults to zero transport retries. Google-auth still owns OAuth.
    """

    def __init__(self, credentials, client=None):
        import httpx

        self.credentials = credentials
        self.client = client or httpx.Client(
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(30, connect=5),
            limits=httpx.Limits(max_connections=1),
        )

    def request(self, uri, method="GET", body=None, headers=None, **kwargs):
        from urllib.parse import urlsplit
        import httplib2
        from google.auth.transport.requests import Request

        url = urlsplit(uri)
        if (
            url.scheme != "https"
            or url.netloc != "gmail.googleapis.com"
            or not url.path.startswith("/gmail/v1/users/me/")
        ):
            raise MailError("unapproved_google_destination")
        outgoing = dict(headers or {})
        self.credentials.before_request(
            lambda **kw: Request()(**{**kw, "timeout": 30}), method, uri, outgoing
        )
        started = time.monotonic()
        with self.client.stream(
            method, uri, content=body, headers=outgoing
        ) as response:
            if 300 <= response.status_code < 400:
                raise MailError("google_redirect_rejected")
            parts, size = [], 0
            for part in response.iter_bytes():
                size += len(part)
                if size > 12 * 1024 * 1024 or time.monotonic() - started > 60:
                    raise MailError("google_response_budget_exceeded")
                parts.append(part)
            return httplib2.Response(
                {**dict(response.headers), "status": str(response.status_code)}
            ), b"".join(parts)

    def close(self):
        self.client.close()


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "head"}:
            self.hidden += 1
        if tag in {"p", "br", "div", "li"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "head"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def parse_message(row: dict) -> Message:
    raw = row.get("raw", "")
    if not isinstance(raw, str) or len(raw) > RAW_LIMIT * 4 // 3 + 8:
        raise MailError("message_exceeds_size_budget")
    try:
        data = base64.b64decode(
            raw + "=" * (-len(raw) % 4), altchars=b"-_", validate=True
        )
        if not data or len(data) > RAW_LIMIT:
            raise MailError("message_exceeds_size_budget")
        msg = BytesParser(policy=policy.default).parsebytes(data)
        part = msg.get_body(preferencelist=("plain", "html"))
        text = part.get_content() if part else ""
        if not isinstance(text, str):
            text = ""
        if part and part.get_content_type() == "text/html":
            parser = Text()
            parser.feed(text)
            text = " ".join(parser.parts)
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text).strip()
        attachments = sum(
            1
            for p in msg.walk()
            if p.get_content_disposition() == "attachment" or p.get_filename()
        )
        return Message(
            id=row["id"],
            thread_id=row["threadId"],
            received_ms=int(row["internalDate"]),
            sender=str(msg.get("From", ""))[:1000],
            reply_to=str(msg.get("Reply-To", ""))[:1000],
            recipient=str(msg.get("To", ""))[:1000],
            cc=str(msg.get("Cc", ""))[:1000],
            bcc=str(msg.get("Bcc", ""))[:1000],
            subject=str(msg.get("Subject", "(no subject)"))[:500],
            body=text[:8000],
            rfc_id=str(msg.get("Message-ID", ""))[:500],
            labels=row.get("labelIds", []),
            truncated=len(text) > 8000,
            attachment_count=attachments,
        )
    except MailError:
        raise
    except Exception:
        raise MailError("unreadable_message") from None


def parse_full(row):
    """Full Gmail payload: attachment IDs are NEVER fetched or passed to the model."""
    try:
        payload = row["payload"]
        headers = {}
        for h in payload.get("headers", []):
            name = h["name"].lower()
            if name in headers and name in {
                "from",
                "to",
                "cc",
                "bcc",
                "subject",
                "message-id",
                "reply-to",
            }:
                raise MailError("ambiguous_message_headers")
            headers[name] = h["value"]
        plain, html = [], []
        attachments, count, encoded_bytes = 0, 0, 0

        def visit(part, depth=0):
            nonlocal attachments, count, encoded_bytes
            count += 1
            if depth > 20 or count > 200:
                raise MailError("mime_complexity_budget_exceeded")
            ph = {h["name"].lower(): h["value"] for h in part.get("headers", [])}
            mime = part.get("mimeType", "")
            if (
                part.get("filename")
                or ph.get("content-disposition", "").lower().startswith("attachment")
                or mime == "message/rfc822"
            ):
                attachments += 1
                return
            body = part.get("body", {})
            if mime in {"text/plain", "text/html"}:
                if body.get("attachmentId"):
                    raise MailError("body_requires_attachment_fetch_manual_review")
                encoded = body.get("data", "")
                encoded_bytes += len(encoded)
                if encoded_bytes > 1024 * 1024:
                    raise MailError("message_exceeds_size_budget")
                decoded = base64.b64decode(
                    encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True
                )
                header = HeaderMessage()
                header["Content-Type"] = ph.get("content-type", mime)
                text = decoded.decode(
                    header.get_content_charset() or "utf-8", errors="strict"
                )
                (plain if mime == "text/plain" else html).append(text)
            for nested in part.get("parts", []):
                visit(nested, depth + 1)

        visit(payload)
        if plain:
            text = "\n".join(plain)
        else:
            parser = Text()
            for item in html:
                parser.feed(item)
            text = " ".join(parser.parts)
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text).strip()

        def h(name, default=""):
            return str(
                HeaderMessage(policy=policy.default).policy.header_fetch_parse(
                    name, headers.get(name, default)
                )
            )

        return Message(
            id=row["id"],
            thread_id=row["threadId"],
            received_ms=int(row["internalDate"]),
            sender=h("from")[:1000],
            recipient=h("to")[:1000],
            cc=h("cc")[:1000],
            bcc=h("bcc")[:1000],
            reply_to=h("reply-to")[:1000],
            subject=h("subject", "(no subject)")[:500],
            rfc_id=h("message-id")[:500],
            labels=row.get("labelIds", []),
            body=text[:8000],
            truncated=len(text) > 8000
            or any(
                len(headers.get(name, "")) > limit
                for name, limit in (
                    ("from", 1000),
                    ("to", 1000),
                    ("cc", 1000),
                    ("bcc", 1000),
                    ("reply-to", 1000),
                    ("subject", 500),
                    ("message-id", 500),
                )
            ),
            attachment_count=attachments,
        )
    except MailError:
        raise
    except Exception:
        raise MailError("unreadable_message") from None


def authorize(store, cfg, client_path, enable_send=False):
    from google_auth_oauthlib.flow import InstalledAppFlow

    client = read_private(client_path)
    installed = client.get("installed", {})
    # Do not send credentials to endpoints supplied in an arbitrary JSON file.
    if (
        installed.get("auth_uri") != "https://accounts.google.com/o/oauth2/auth"
        or installed.get("token_uri") != "https://oauth2.googleapis.com/token"
    ):
        raise MailError("official_desktop_oauth_client_required")
    scopes = [READ, SEND] if enable_send else [READ]
    flow = InstalledAppFlow.from_client_config(
        client, scopes, autogenerate_code_verifier=True
    )
    creds = flow.run_local_server(
        host="127.0.0.1",
        port=0,
        timeout_seconds=180,
        authorization_prompt_message="Authorize in your local browser; do not share the URL.",
        success_message="Okal authorization received. Return to your terminal.",
        access_type="offline",
        prompt="consent select_account",
    )
    granted = creds.granted_scopes or creds.scopes
    if set(granted or []) != set(scopes):
        raise MailError("unexpected_oauth_scopes")
    info = json.loads(creds.to_json())
    info["scopes"] = list(granted)
    api = Gmail.from_credentials(creds)
    try:
        api.check_account(cfg.account)
    finally:
        api.close()
    # Commit token only after scope and account checks.
    write_private(root(store) / "token.json", info)
    cfg.send_enabled = enable_send
    write_private(root(store) / "config.json", cfg.model_dump())


class Gmail:
    def __init__(self, service, sleep=time.sleep):
        self.service = service
        self.sleep = sleep

    @classmethod
    def from_credentials(cls, creds):
        from googleapiclient.discovery import build

        http = GoogleTransport(creds)
        return cls(
            build(
                "gmail", "v1", http=http, static_discovery=True, cache_discovery=False
            )
        )

    def close(self):
        self.service.close()

    @classmethod
    def open(cls, store, cfg, sending=False):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        info = read_private(root(store) / "token.json")
        scopes = set(info.get("scopes", []))
        if scopes not in ({READ}, {READ, SEND}) or (
            sending and (not cfg.send_enabled or SEND not in scopes)
        ):
            raise MailError("scope_or_send_permission_mismatch")
        if info.get("token_uri") != "https://oauth2.googleapis.com/token":
            raise MailError("invalid_token_endpoint")
        creds = Credentials.from_authorized_user_info(info)
        if not creds.valid:
            try:
                creds.refresh(lambda **kw: Request()(**{**kw, "timeout": 30}))
            except Exception:
                raise MailError("authorization_required") from None
            write_private(root(store) / "token.json", json.loads(creds.to_json()))
        api = cls.from_credentials(creds)
        try:
            api.check_account(cfg.account)
        except Exception:
            api.close()
            raise
        return api

    def call(self, request, write=False):
        for attempt in range(3 if not write else 1):
            try:
                return request.execute(num_retries=0)
            except Exception as exc:
                code = getattr(getattr(exc, "resp", None), "status", None)
                if not write and code in {429, 500, 502, 503, 504} and attempt < 2:
                    self.sleep(2**attempt)
                    continue
                if code == 401:
                    raise MailError("authorization_required") from None
                raise MailError(
                    "provider_write_uncertain" if write else "provider_read_failed"
                ) from None

    def check_account(self, expected):
        actual = self.call(self.service.users().getProfile(userId="me")).get(
            "emailAddress", ""
        )
        if actual.casefold() != expected.casefold():
            raise MailError("wrong_google_account")

    def ids(self, query, limit):
        cursor = None
        seen_cursors, ids = set(), set()
        started = time.monotonic()
        for _ in range(100):
            if time.monotonic() - started > 120:
                raise MailError("listing_time_budget_exceeded")
            page = self.call(
                self.service.users()
                .messages()
                .list(
                    userId="me",
                    q=query,
                    includeSpamTrash=False,
                    maxResults=min(limit + 1, 100),
                    pageToken=cursor,
                )
            )
            ids.update(r["id"] for r in page.get("messages", []))
            if len(ids) > limit:
                raise MailError("message_budget_exceeded_narrow_interval")
            cursor = page.get("nextPageToken")
            if not cursor:
                return sorted(ids)
            if cursor in seen_cursors:
                raise MailError("repeated_page_token")
            seen_cursors.add(cursor)
        raise MailError("page_budget_exceeded")

    def get(self, mid):
        if not re.fullmatch(r"[a-fA-F0-9]{1,64}", mid):
            raise MailError("invalid_message_id")
        row = self.call(
            self.service.users().messages().get(userId="me", id=mid, format="full")
        )
        message = parse_full(row)
        if message.id != mid:
            raise MailError("provider_id_mismatch")
        return message

    def collect(self, start, end, limit):
        query = (
            f"after:{start - 1} before:{end + 1} -in:sent -in:drafts -in:spam -in:trash"
        )
        messages = []
        started = time.monotonic()
        for mid in self.ids(query, limit):
            if time.monotonic() - started > 180:
                raise MailError("read_time_budget_exceeded")
            msg = self.get(mid)
            if start * 1000 <= msg.received_ms < end * 1000 and not set(msg.labels) & {
                "SENT",
                "DRAFT",
                "SPAM",
                "TRASH",
            }:
                messages.append(msg)
        return sorted(messages, key=lambda m: (m.received_ms, m.id))

    def send(self, raw, thread_id=None):
        body = {"raw": base64.urlsafe_b64encode(raw).decode()}
        if thread_id:
            body["threadId"] = thread_id
        return self.call(
            self.service.users().messages().send(userId="me", body=body), write=True
        )
