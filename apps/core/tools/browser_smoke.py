"""Optional Playwright check against disposable data, not the owner's accounts."""

import argparse
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import urllib.request

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", required=True, help="core venv Python")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        command = [args.python, "-m", "okal_core", "--state-dir", temp]
        subprocess.run(command + ["demo"], check=True, capture_output=True)
        device = json.loads(
            subprocess.check_output(command + ["device-add", "browser-test"])
        )
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        origin = f"http://127.0.0.1:{port}"
        proc = subprocess.Popen(
            command + ["serve", "--port", str(port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for _ in range(100):
                try:
                    with opener.open(origin + "/api/v1/health", timeout=1):
                        break
                except OSError:
                    time.sleep(0.05)
            else:
                raise RuntimeError("core unavailable")
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1365, "height": 1000})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(origin)
                page.locator("#token").fill(device["token"])
                page.locator("#connect").click()
                page.locator(".summary").first.wait_for()
                assert page.locator(".summary").count() == 2
                assert page.locator(".fixture").count() == 2
                assert page.locator("#token").input_value() == ""
                assert page.evaluate("localStorage.length + sessionStorage.length") == 0
                page.screenshot(
                    path=str(args.output_dir / "core-inbox-desktop.png"), full_page=True
                )
                page.set_viewport_size({"width": 390, "height": 844})
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth"
                )
                page.screenshot(
                    path=str(args.output_dir / "core-inbox-mobile.png"), full_page=True
                )
                # Inject data only into this test response, then check DOM XSS and
                # that a revoked token clears the previously displayed summaries.
                page.route(
                    "**/api/v1/summaries?*",
                    lambda route: route.fulfill(
                        json={
                            "items": [
                                {
                                    "title": "<img src=x onerror=alert(1)>",
                                    "body": "<script>window.xss=true</script>",
                                    "data_kind": "fixture",
                                    "created_at": 0,
                                    "workflow": "demo",
                                }
                            ],
                            "next_cursor": None,
                            "fetched_at": 0,
                        }
                    ),
                )
                page.locator("#refresh").click()
                page.get_by_role(
                    "heading", name="<img src=x onerror=alert(1)>"
                ).wait_for()
                assert page.locator(".summary img, .summary script").count() == 0
                assert page.evaluate("window.xss === undefined")
                page.unroute("**/api/v1/summaries?*")
                subprocess.run(
                    command + ["device-revoke", device["id"]],
                    check=True,
                    capture_output=True,
                )
                page.locator("#refresh").click()
                page.locator("#login-panel").wait_for(state="visible")
                assert page.locator(".summary").count() == 0
                assert not errors, errors
                browser.close()
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
    print(
        "Browser smoke passed: desktop, mobile width, no overflow, no token storage, XSS, revocation"
    )


if __name__ == "__main__":
    main()
