"""Fresh Chromium contexts; exact-origin egress with DNS pinned per invocation."""

import base64
import ipaddress
import json
import re
import shutil
import socket
import sys
import signal
import tempfile
from urllib.parse import urlsplit

from .contracts import Denied
from .process import run

BLOCKED_PORTS = {8766, 8876, 11434}


def origin(url):
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise Denied("invalid_browser_url")
    host = parsed.hostname or ""
    if not re.fullmatch(r"[a-zA-Z0-9.-]+", host):
        raise Denied("invalid_browser_host")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if port in BLOCKED_PORTS:
        raise Denied("core_and_model_ports_are_not_browser_targets")
    return (
        parsed.scheme
        + "://"
        + host.lower()
        + (":" + str(port) if port not in {80, 443} else "")
    )


def network(origins):
    rules = []
    for allowed in origins:
        if origin(allowed) != allowed or urlsplit(allowed).path not in {"", "/"}:
            raise Denied("exact_origin_required")
        parsed = urlsplit(allowed)
        host = parsed.hostname
        addresses = {
            r[4][0]
            for r in socket.getaddrinfo(
                host, parsed.port or 443, type=socket.SOCK_STREAM
            )
        }
        if not addresses:
            raise Denied("browser_dns_unavailable")
        for value in addresses:
            ip = ipaddress.ip_address(value)
            # Explicit numeric loopback origins support owner test/dev servers;
            # private DNS names and link-local/metadata networks are rejected.
            if not ip.is_global and not (host == "127.0.0.1" and ip.is_loopback):
                raise Denied("private_network_browser_destination_denied")
        address = sorted(addresses)[0]
        if ":" in address:
            address = "[" + address + "]"
        rules.append("MAP " + host + " " + address)
    return ",".join(rules) + ",MAP * ~NOTFOUND"


def browse(ctx, args, interactive=False):
    if origin(args.url) not in ctx.policy.browser_origins:
        raise Denied("browser_origin_not_granted")
    payload = {
        "url": args.url,
        "origins": ctx.policy.browser_origins,
        "rules": network(ctx.policy.browser_origins),
        "operations": args.operations if interactive else [],
        "interactive": interactive,
    }
    raw = run(
        [sys.executable, "-m", "okal_core.computer.browser"],
        ctx.check,
        timeout=40,
        input_data=json.dumps(payload).encode(),
    )
    data = json.loads(raw)
    if data.get("error"):
        raise ValueError(data["error"])
    if data.get("download"):
        content = base64.b64decode(data.pop("download"), validate=True)
        if not args.download_to:
            raise ValueError("download_destination_required")
        created = ctx.files.write(args.download_to, content)
        data["download_file"] = created
    return data


def main():
    # This worker gets explicit synthetic/browser input only, not the private
    # core database/config. It never attaches to an owner's existing profile.
    from playwright.sync_api import sync_playwright

    payload = json.loads(sys.stdin.buffer.read(65537))
    origins = set(payload["origins"])
    count = 0
    with (
        tempfile.TemporaryDirectory(prefix="okal-browser-") as directory,
        sync_playwright() as p,
    ):
        executable = shutil.which("chromium")
        if not executable:
            raise ValueError("chromium_unavailable")
        browser = p.chromium.launch(
            executable_path=executable,
            headless=True,
            chromium_sandbox=True,
            args=[
                "--host-resolver-rules=" + payload["rules"],
                "--disable-background-networking",
            ],
        )
        try:
            context = browser.new_context(
                accept_downloads=True, service_workers="block"
            )
            context.set_default_timeout(10000)

            def route(request_route):
                nonlocal count
                request = request_route.request
                count += 1
                try:
                    approved = origin(request.url) in origins and count <= 80
                    approved = approved and (
                        payload["interactive"] or request.method == "GET"
                    )
                except ValueError:
                    approved = False
                if approved:
                    request_route.continue_()
                else:
                    request_route.abort()

            context.route("**/*", route)
            context.route_web_socket("**/*", lambda ws: ws.close())
            page = context.new_page()
            page.on("dialog", lambda dialog: dialog.dismiss())
            response = page.goto(
                payload["url"], wait_until="domcontentloaded", timeout=15000
            )
            if response is None or response.status >= 400:
                raise ValueError("browser_navigation_failed")
            download = None
            for operation in payload["operations"]:
                target = page.locator(operation["selector"])
                if operation["action"] == "fill":
                    field = target.evaluate(
                        "(el)=>({type:el.type,name:el.name,autocomplete:el.autocomplete})"
                    )
                    if any(
                        re.search(
                            "password|token|secret|one-time|credit|cc-", str(v), re.I
                        )
                        for v in field.values()
                    ):
                        raise Denied(
                            "credentials_and_financial_fields_require_owner_native_flow"
                        )
                    target.fill(operation["value"])
                elif operation["action"] == "click":
                    target.click()
                elif operation["action"] == "download":
                    with page.expect_download(timeout=10000) as pending:
                        target.click()
                    file = directory + "/download"
                    pending.value.save_as(file)
                    with open(file, "rb") as stream:
                        content = stream.read(65537)
                    if len(content) > 65536:
                        raise ValueError("browser_download_limit_64kib")
                    download = base64.b64encode(content).decode()
            if origin(page.url) not in origins:
                raise Denied("ungranted_redirect")
            body = page.locator("body").inner_text(timeout=5000)
            links = page.locator("a[href]").evaluate_all(
                "(els)=>els.slice(0,30).map(e=>({text:e.textContent.slice(0,100),url:e.href}))"
            )
            print(
                json.dumps(
                    dict(
                        url=page.url,
                        title=page.title()[:200],
                        text=body[:12000],
                        links=links,
                        limited=len(body) > 12000,
                        download=download,
                    ),
                    ensure_ascii=False,
                )
            )
            context.close()
        finally:
            browser.close()


if __name__ == "__main__":

    def interrupted(signum, frame):
        raise KeyboardInterrupt()

    signal.signal(signal.SIGTERM, interrupted)
    try:
        main()
    except Exception as exc:
        code = (
            "owner_authentication_or_native_financial_flow_required"
            if str(exc) == "credentials_and_financial_fields_require_owner_native_flow"
            else "browser_navigation_or_interaction_failed"
        )
        print(json.dumps({"error": code}))
