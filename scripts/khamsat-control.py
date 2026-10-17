#!/usr/bin/env python3
"""Local-only Khamsat control page and scheduled scout/response entry point."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from html import escape
from http.server import BaseHTTPRequestHandler, HTTPServer
import importlib.util
import json
import os
from pathlib import Path
import secrets
from urllib.parse import parse_qs, quote, urlparse


def sibling(name: str, module: str):
    spec = importlib.util.spec_from_file_location(module, Path(__file__).with_name(name))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


scout = sibling("khamsat-request-scout.py", "khamsat_scout_control")
reply = sibling("khamsat-request-reply.py", "khamsat_reply_control")
DRAFTS = scout.STATE / "drafts.json"
HOST = "127.0.0.1"
PORT = 8788
DEFAULT_REPLY = reply.DEFAULT_REPLY | {"scan_interval_minutes": 30}


def private_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default.copy()
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError(f"Private file must be regular and 0600: {path}")
    data = scout.load(path)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def parse_lines(value: str) -> list[str]:
    return [x.strip() for x in value.splitlines() if x.strip()]


def validate_settings(form: dict[str, str]) -> tuple[dict, dict]:
    mode = form.get("authorization", "review")
    if mode not in ("review", "auto"):
        raise ValueError("Choose review or autonomous mode")
    if mode == "auto" and form.get("confirm_auto") != "yes":
        raise ValueError("Confirm autonomous submissions before enabling them")
    keywords = parse_lines(form.get("keywords", ""))
    excludes = parse_lines(form.get("exclude_terms", ""))
    if not keywords or len(keywords) > 30 or any(len(x) > 80 for x in keywords + excludes):
        raise ValueError("Enter 1–30 specific services or job terms, one per line")
    days = int(form.get("max_per_day", "2"))
    interval = int(form.get("scan_interval_minutes", "30"))
    if not 1 <= days <= 5 or not 5 <= interval <= 1440:
        raise ValueError("Daily limit must be 1–5; refresh interval 5–1440 minutes")
    context = form.get("proposal_instructions", "").strip()
    if not context or len(context) > 3000:
        raise ValueError("Proposal instructions must be 1–3000 characters")
    portfolio = form.get("portfolio_url", "").strip()
    field = form.get("reply_selector", "").strip()
    button = form.get("submit_selector", "").strip()
    if mode == "auto" and not all((field, button)):
        raise ValueError("Inspect the live reply field and submit button before auto mode")
    if mode == "auto":
        reply.profile_facts()
    if portfolio:
        uri = urlparse(portfolio)
        if uri.scheme != "https" or not uri.hostname or uri.username or uri.password:
            raise ValueError("Portfolio must be a public HTTPS link")
    if any(len(x) > 200 for x in (field, button)):
        raise ValueError("A setting is too long")
    watch = {"keywords": keywords, "exclude_terms": excludes}
    config = DEFAULT_REPLY | {
        "authorization": mode, "enabled": mode == "auto", "max_per_day": days,
        "scan_interval_minutes": interval,
        "portfolio_url": portfolio, "reply_selector": field, "submit_selector": button,
        "proposal_instructions": context,
        "ollama_model": form.get("ollama_model", DEFAULT_REPLY["ollama_model"]).strip(),
    }
    if not config["ollama_model"] or len(config["ollama_model"]) > 100:
        raise ValueError("Select a local Ollama model")
    return watch, config


def candidates() -> tuple[list[dict], dict]:
    queue = private_json(scout.STATE / "queue.json", {"requests": []})
    receipts = private_json(reply.RECEIPTS, {"requests": {}})
    return queue.get("requests", []), receipts.get("requests", {})


def candidate(rid: str) -> dict:
    if not rid.isascii() or not rid.isdecimal():
        raise ValueError("Invalid request ID")
    rows, _ = candidates()
    found = [x for x in rows if str(x.get("id")) == rid and scout.request_id(x["url"]) == rid]
    if len(found) != 1:
        raise ValueError("Request is not in the scanned queue")
    return found[0]


def preview(rid: str) -> str:
    item = candidate(rid)
    _, receipts = candidates()
    if rid in receipts:
        raise ValueError("Already attempted; inspect the receipt before any retry")
    cfg = reply.instructions(dry_run=True)
    if not scout.matches(item["title"] + " " + item.get("visible_text", ""), cfg):
        raise ValueError("This request does not match your current rules")
    proposal = reply.generate(item, cfg)
    warning = ""
    try:
        reply.valid_reply(proposal, cfg)
    except ValueError as exc:
        warning = str(exc)
    drafts = private_json(DRAFTS, {"requests": {}})
    drafts.setdefault("requests", {})[rid] = {
        "url": item["url"], "text": proposal, "validation_error": warning,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    scout.save(DRAFTS, drafts)
    return warning


def submit_reviewed(rid: str, text: str) -> list[str]:
    cfg = reply.instructions(reviewed=True)
    item = candidate(rid)
    drafts = private_json(DRAFTS, {"requests": {}}).get("requests", {})
    draft = drafts.get(rid)
    if not draft or draft.get("url") != item["url"]:
        raise ValueError("Preview this request before submitting")
    if datetime.fromisoformat(draft["created_at"]) < datetime.now(timezone.utc) - timedelta(hours=24):
        raise ValueError("Preview expired; generate a new one")
    text = text.strip()
    reply.valid_reply(text, cfg)
    results = reply.run(url=item["url"], reply_override=text, reviewed=True)
    if any(result == f'Submitted: {item["url"]}' for result in results):
        try:
            if reply.remember_edit(rid, draft["text"], text):
                results.append("حُفظ تعديلك كأسلوب للمسودات القادمة")
        except (ValueError, OSError, TypeError, KeyError) as exc:
            results.append(f"تم النشر، لكن تعذّر حفظ تعديل الأسلوب: {exc}")
    return results


def tick() -> str:
    watch = scout.settings(scout.CONFIG)
    cfg = private_json(reply.SETTINGS, DEFAULT_REPLY)
    interval = cfg.get("scan_interval_minutes", 30)
    if type(interval) is not int or not 5 <= interval <= 1440:
        raise ValueError("Invalid scan interval")
    queue = private_json(scout.STATE / "queue.json", {})
    checked = queue.get("checked_at")
    if checked:
        last = datetime.fromisoformat(checked)
        if last.tzinfo is None:
            raise ValueError("Queue time needs a timezone")
        if datetime.now(timezone.utc) - last < timedelta(minutes=interval):
            return "Next scan is not due yet"
    scout.scan(scout.STATE, scout.PROFILE, watch, 10)
    if cfg.get("authorization", "review") == "auto" and cfg.get("enabled") is True:
        return "\n".join(reply.run()) or "No new eligible request to submit"
    return "Scanned; review mode kept all responses unsent"


STYLE = """
*{box-sizing:border-box}body{margin:0;background:#08111b;color:#e9f3fa;font:16px system-ui,-apple-system,sans-serif}
main{max-width:1180px;margin:auto;padding:38px 22px 90px}header{display:flex;justify-content:space-between;align-items:center;gap:24px}
h1{font-size:clamp(34px,5vw,60px);margin:6px 0 12px;letter-spacing:-.04em}h2{font-size:22px;margin:0 0 14px}
.eyebrow{color:#68dfcf;text-transform:uppercase;letter-spacing:.18em;font-size:12px;font-weight:750}
.intro{max-width:690px;color:#abc0ca;line-height:1.7}.badge{border:1px solid #3d5967;border-radius:99px;padding:9px 16px;color:#9de7db}
.grid{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(310px,.85fr);gap:18px;margin-top:28px}
.card{background:linear-gradient(145deg,#142430,#101d29);border:1px solid #2d4653;border-radius:20px;padding:24px;box-shadow:0 18px 60px #0004}
.span{grid-column:1/-1}.muted{color:#9ab1be;line-height:1.6}label{display:block;margin:16px 0 7px;font-weight:650}
input,textarea,select{width:100%;background:#0a1722;border:1px solid #45606d;border-radius:10px;color:#f6fcff;padding:11px;font:inherit}
textarea{min-height:96px;resize:vertical}input[type=checkbox]{width:auto;accent-color:#54dcb9}button{background:#57e1ba;color:#0a2025;border:0;border-radius:10px;padding:11px 17px;font:inherit;font-weight:760;cursor:pointer}
button.alt{background:#24404d;color:#d9f5ef}button:focus-visible,a:focus-visible{outline:3px solid #fbca6d;outline-offset:3px}
form.inline{display:inline-block;margin:5px 8px 5px 0}.row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.notice{background:#173c3a;border:1px solid #4dd7bc;border-radius:12px;padding:14px;margin:18px 0;white-space:pre-wrap}
.error{background:#45232c;border-color:#ef8b98}.item{padding:19px 0;border-top:1px solid #304754}.item a{color:#8fe8dd;overflow-wrap:anywhere}
.item small{color:#a2b4c2}.draft{margin-top:10px;min-height:135px}code{color:#b9eecf}footer{color:#93aab6;margin-top:26px}
@media(max-width:800px){header{display:block}.grid{grid-template-columns:1fr}.row{grid-template-columns:1fr}}
"""


def render(token: str, notice: str = "", error: bool = False) -> str:
    watch = private_json(scout.CONFIG, scout.DEFAULT_CONFIG)
    config = DEFAULT_REPLY | private_json(reply.SETTINGS, DEFAULT_REPLY)
    draft_ready = reply.OWNER_PROFILE.is_file() and not reply.OWNER_PROFILE.is_symlink()
    rows, receipts = candidates()
    drafts = private_json(DRAFTS, {"requests": {}}).get("requests", {})
    e = lambda x: escape(str(x), quote=True)
    hidden = f'<input type="hidden" name="csrf" value="{e(token)}">'
    badge = "إرسال تلقائي مفعّل" if config.get("authorization") == "auto" and config.get("enabled") else "المراجعة مطلوبة قبل الإرسال"
    parts = [f'<!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Okal · خمسات</title><style>{STYLE}</style><main>',
             f'<header><div><div class="eyebrow">OKAL / KHAMSAT CONTROL</div><h1>فرص مناسبة. قرار واضح.</h1><p class="intro">راقب طلبات المجتمع، راجع الردود أو فوّض الإرسال ضمن حدودك. الإعدادات وسجل الردود محفوظان على جهازك.</p></div><span class="badge">{e(badge)}</span></header>']
    if notice:
        parts.append(f'<div class="notice {"error" if error else ""}" role="status">{e(notice)}</div>')
    if not draft_ready:
        parts.append('<div class="notice" role="status">لتحضير رد بناءً على خبرتك: راجع ملفك المحلي ~/.config/okal/owner-profile.json وحدد حقائق عمل موثقة فيه. لا يلزم إدخال رابط معرض أعمال أو دليل منفصل. محددات النموذج مطلوبة للإرسال فقط.</div>')
    parts.append('<div class="grid"><section class="card"><h2>قواعد التشغيل</h2><p class="muted">اختر وضع الصلاحية أولًا. في المراجعة لن يضغط Okal إرسال إلا بعد موافقتك على رد بعينه.</p>')
    parts.append(f'<form method="post" action="/settings">{hidden}<label for="auth">الصلاحية</label><select id="auth" name="authorization"><option value="review" {"selected" if config.get("authorization") != "auto" else ""}>Review needed — مراجعة كل رد</option><option value="auto" {"selected" if config.get("authorization") == "auto" else ""}>Allow — إرسال تلقائي للطلبات المطابقة</option></select>')
    parts.append('<label><input type="checkbox" name="confirm_auto" value="yes"> أفوّض الإرسال التلقائي إذا اخترت Allow، مع الحد اليومي والقواعد أدناه</label>')
    fields = [("keywords", "الخدمات والوظائف المستهدفة (سطر لكل كلمة)", "\n".join(watch.get("keywords", []))),
              ("exclude_terms", "استبعاد", "\n".join(watch.get("exclude_terms", []))),
              ("portfolio_url", "رابط معرض الأعمال HTTPS (اختياري)", config.get("portfolio_url", "")),
              ("proposal_instructions", "قالب كتابة الرد (قابل للتعديل)", config.get("proposal_instructions", "")),
              ("reply_selector", "حقل الرد بعد فحص الصفحة", config.get("reply_selector", "")),
              ("submit_selector", "زر الإرسال بعد فحص الصفحة", config.get("submit_selector", "")),
              ("ollama_model", "موديل Ollama المحلي", config.get("ollama_model", ""))]
    for name, label, value in fields:
        parts.append(f'<label for="{name}">{e(label)}</label>')
        if name in ("keywords", "exclude_terms", "proposal_instructions"):
            parts.append(f'<textarea id="{name}" name="{name}">{e(value)}</textarea>')
        else:
            parts.append(f'<input id="{name}" name="{name}" value="{e(value)}">')
    parts.append(f'<div class="row"><div><label for="scan_interval_minutes">تحديث كل (دقيقة)</label><input id="scan_interval_minutes" name="scan_interval_minutes" type="number" min="5" max="1440" value="{e(config.get("scan_interval_minutes", 30))}"></div><div><label for="max_per_day">أقصى ردود في اليوم</label><input id="max_per_day" name="max_per_day" type="number" min="1" max="5" value="{e(config.get("max_per_day", 2))}"></div></div><p><button type="submit">حفظ الإعدادات</button></p></form></section>')
    parts.append(f'<aside class="card"><h2>المراقبة الآن</h2><p class="muted">الصفحة مخصصة لجهازك فقط. سيُفتح متصفحك المرئي عند الفحص، ويقف عند تغيّر تسجيل الدخول أو ظهور CAPTCHA.</p><form method="post" action="/scan" class="inline">{hidden}<button type="submit">افحص الطلبات الآن</button></form><p class="muted">الفحص الدوري يعمل عند تثبيت مؤقّت المستخدم. تغيير المدة يُحفظ هنا ويُحترم في الدورة التالية. الجهاز يجب أن يكون مفتوحًا.</p><p>طلبات بالطابور: <strong>{len(rows)}</strong> · محاولات مسجّلة: <strong>{len(receipts)}</strong></p></aside>')
    parts.append('<section class="card span"><h2>طابور الطلبات</h2><p class="muted">افتح الطلب الأصلي للتأكد من ملاءمته. الرد هنا هو تعليق على طلب مجتمع خمسات.</p>')
    for item in reversed(rows[-60:]):
        try:
            rid = scout.request_id(item["url"])
        except (ValueError, KeyError):
            continue
        if rid in receipts:
            status = receipts[rid].get("status", "attempted")
        else:
            status = "لم يُرسل"
        parts.append(f'<article class="item"><strong>{e(item.get("title", "طلب"))}</strong> · <small>{e(status)}</small><p><a href="{e(item["url"])}" target="_blank" rel="noopener noreferrer">{e(item["url"])}</a></p>')
        if rid not in receipts and config.get("authorization") == "review":
            if draft_ready:
                parts.append(f'<form method="post" action="/preview" class="inline">{hidden}<input type="hidden" name="id" value="{rid}"><button class="alt">جهّز ردًا للمراجعة</button></form>')
            draft = drafts.get(rid)
            if draft and draft.get("url") == item["url"]:
                if draft.get("validation_error"):
                    parts.append(f'<p class="notice error" role="status">المسودة تحتاج تعديل قبل الإرسال: {e(draft["validation_error"])}</p>')
                parts.append(f'<form method="post" action="/submit">{hidden}<input type="hidden" name="id" value="{rid}"><label for="draft-{rid}">راجع النص وعدّله، ثم أرسله لهذا الطلب فقط</label><textarea class="draft" id="draft-{rid}" name="text">{e(draft.get("text", ""))}</textarea><p class="muted">بعد تأكيد نشر ردك، سيتعلم Okal أسلوب تعديلك للمسودات القادمة فقط.</p><p><button type="submit">إرسال الرد الآن</button></p></form>')
        parts.append('</article>')
    if not rows:
        parts.append('<p class="muted">الطابور فارغ. احفظ المجالات ثم اضغط «افحص الطلبات الآن».</p>')
    parts.append('</section></div><footer>Okal · البيانات محلية · لا تعاود إرسال طلب بحالة pending قبل فحصه في الموقع</footer></main></html>')
    return "".join(parts)


def same_page_request(headers) -> bool:
    """Check available browser metadata; the unguessable form token is checked separately.

    Some browsers omit Origin (or send ``null``) for a same-origin HTML form POST,
    especially under a strict Referrer-Policy. Never treat that absence as consent:
    every POST still needs the secret token delivered by the loopback GET page.
    """
    expected = f"http://{HOST}:{PORT}"
    origin = headers.get("Origin")
    if origin not in (None, "", "null", expected):
        return False
    referer = headers.get("Referer")
    if referer:
        parsed = urlparse(referer)
        if f"{parsed.scheme}://{parsed.netloc}" != expected:
            return False
    fetch_site = headers.get("Sec-Fetch-Site")
    return fetch_site in (None, "same-origin", "none")


class Handler(BaseHTTPRequestHandler):
    token = secrets.token_urlsafe(32)

    def security_headers(self, content_type: str):
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")

    def respond(self, content: str, code: int = 200):
        payload = content.encode("utf-8")
        self.send_response(code)
        self.security_headers("text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def allowed(self) -> bool:
        return self.headers.get("Host") == f"{HOST}:{PORT}"

    def do_GET(self):
        if not self.allowed() or self.path != "/":
            self.send_error(404)
            return
        try:
            self.respond(render(self.token))
        except (ValueError, OSError, KeyError, TypeError) as exc:
            self.respond(f"Local settings error: {escape(str(exc))}", 500)

    def do_POST(self):
        if not self.allowed() or self.path not in ("/settings", "/scan", "/preview", "/submit"):
            self.send_error(404)
            return
        if not same_page_request(self.headers):
            self.send_error(403, "Cross-site request blocked")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length < 25000:
                raise ValueError("Invalid form size")
            form = {k: v[0] for k, v in parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True).items()}
            if not secrets.compare_digest(form.get("csrf", ""), self.token):
                self.send_error(403, "Invalid form token")
                return
            if self.path == "/settings":
                watch, config = validate_settings(form)
                scout.save(scout.CONFIG, watch)
                scout.save(reply.SETTINGS, config)
                message = "حُفظت الإعدادات. التفويض: " + config["authorization"]
            elif self.path == "/scan":
                scout.scan(scout.STATE, scout.PROFILE, scout.settings(scout.CONFIG), 10)
                message = "اكتمل الفحص. راجع الطلبات أسفل الصفحة."
            elif self.path == "/preview":
                warning = preview(form.get("id", ""))
                message = ("جهزت مسودة تحتاج تعديلًا قبل الإرسال: " + warning if warning else
                           "جهزت الرد. راجعه أسفل الصفحة قبل الإرسال.")
            else:
                results = submit_reviewed(form.get("id", ""), form.get("text", ""))
                message = "\n".join(results) or "لم يُرسل رد. راجع الطابور."
            self.respond(render(self.token, message))
        except (ValueError, RuntimeError, OSError, ImportError, BlockingIOError, KeyError, TypeError) as exc:
            try:
                self.respond(render(self.token, str(exc), True), 400)
            except Exception:
                self.send_error(400, str(exc))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tick", action="store_true", help="Run one due scan and optional autonomous replies")
    p.add_argument("--port", type=int, default=PORT)
    args = p.parse_args()
    if args.tick:
        print(tick())
        return 0
    if args.port != PORT:
        p.error("Control page uses only fixed loopback port 8788")
    with HTTPServer((HOST, PORT), Handler) as server:
        print(f"Open http://{HOST}:{PORT}/ on this computer", flush=True)
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
