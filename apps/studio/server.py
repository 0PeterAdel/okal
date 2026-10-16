"""Okal Studio: loopback-only display and narrow voice control bridge.

The browser never receives direct access to the voice socket or arbitrary files.
All files and routes served here are explicitly allowlisted.
"""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import mimetypes
import os
from pathlib import Path
import re
import secrets
import socket
import stat
import threading
import webbrowser
from urllib.parse import urlsplit


HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
SCHEMA = "okal.studio.canvas.v1"
PHASES = {"idle", "listening", "transcribing", "reviewing", "routing",
          "speaking", "blocked", "error"}
KINDS = {"text", "chart", "gallery", "steps"}
MEDIA_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}\.(?:png|jpg|jpeg|webp)$", re.I)
ASSET_NAME = re.compile(r"^/assets/[a-z0-9][a-z0-9_-]*\.svg$")
STATIC_FILES = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css",
                "/assets/noor.svg": "assets/noor.svg",
                "/assets/terrain.svg": "assets/terrain.svg",
                "/assets/atlas.svg": "assets/atlas.svg"}
MAX_CANVAS = 128 * 1024


def runtime_root() -> Path | None:
    override = os.environ.get("OKAL_STUDIO_RUNTIME_DIR")
    base = override or os.environ.get("XDG_RUNTIME_DIR")
    return Path(base) / "okal" if base else None


def clean_text(value: object, limit: int = 160) -> str:
    return value[:limit] if isinstance(value, str) else ""


def safe_canvas(payload: object) -> dict | None:
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA:
        return None
    kind = payload.get("kind")
    if not isinstance(kind, str) or kind not in KINDS:
        return None
    result = {
        "schema_version": SCHEMA,
        "kind": kind,
        "title": clean_text(payload.get("title"), 120),
        "subtitle": clean_text(payload.get("subtitle"), 240),
        "source": clean_text(payload.get("source"), 120),
    }
    if kind == "text":
        result["body"] = clean_text(payload.get("body"), 8000)
        result["highlights"] = [clean_text(s, 200) for s in payload.get("highlights", [])[:6]
                                if isinstance(s, str)] if isinstance(payload.get("highlights"), list) else []
    elif kind == "chart":
        result["unit"] = clean_text(payload.get("unit"), 30)
        series = payload.get("series")
        if not isinstance(series, list):
            return None
        result["series"] = [
            {"label": clean_text(row.get("label"), 60), "value": round(row["value"], 2)}
            for row in series[:12]
            if isinstance(row, dict) and type(row.get("value")) in (int, float)
            and math.isfinite(row["value"]) and 0 <= row["value"] <= 100
        ]
    elif kind == "steps":
        steps = payload.get("steps")
        if not isinstance(steps, list):
            return None
        result["steps"] = [
            {"title": clean_text(s.get("title"), 90), "detail": clean_text(s.get("detail"), 300),
             "state": s.get("state") if s.get("state") in ("done", "active", "waiting") else "waiting"}
            for s in steps[:8] if isinstance(s, dict)
        ]
    else:
        images = payload.get("images")
        if not isinstance(images, list):
            return None
        result["images"] = []
        for entry in images[:8]:
            if not isinstance(entry, dict):
                continue
            src = entry.get("src")
            if (isinstance(src, str) and
                    (ASSET_NAME.fullmatch(src) and src in STATIC_FILES or
                     src.startswith("/media/") and MEDIA_NAME.fullmatch(src[7:]))):
                result["images"].append({"src": src, "alt": clean_text(entry.get("alt"), 160),
                                         "caption": clean_text(entry.get("caption"), 160)})
    return result


def read_canvas() -> dict | None:
    root = runtime_root()
    if not root:
        return None
    path = root / "studio" / "canvas.json"
    try:
        if path.stat().st_size > MAX_CANVAS:
            return None
        return safe_canvas(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, UnicodeError):
        return None


def read_voice() -> dict:
    root = runtime_root()
    idle = {"available": False, "phase": "idle", "text": "", "language": "unknown",
            "route": "", "session_id": "", "level": 0}
    if not root:
        return idle
    folder = root / "voice"
    try:
        socket_info = (folder / "control.sock").stat()
        idle["available"] = stat.S_ISSOCK(socket_info.st_mode) and socket_info.st_uid == os.getuid()
    except OSError:
        pass
    try:
        payload = json.loads((folder / "state.json").read_text(encoding="utf-8"))
        idle.update({
            "phase": payload.get("phase") if isinstance(payload.get("phase"), str)
                     and payload.get("phase") in PHASES else "idle",
            "text": clean_text(payload.get("text"), 2500),
            "language": clean_text(payload.get("language"), 12),
            "route": clean_text(payload.get("route"), 30),
            "session_id": clean_text(payload.get("session_id"), 80),
        })
    except (OSError, ValueError, UnicodeError, AttributeError, TypeError):
        pass
    try:
        idle["level"] = max(0.0, min(1.0, float((folder / "level").read_text())))
    except (OSError, ValueError):
        pass
    return idle


def voice_command(command: str, text: str = "") -> dict:
    if command not in ("toggle", "cancel", "ask"):
        return {"ok": False, "error": "Unsupported voice command"}
    root = runtime_root()
    if not root:
        return {"ok": False, "error": "Okal voice is unavailable"}
    path = root / "voice" / "control.sock"
    try:
        info = path.stat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
            raise OSError("unsafe voice socket")
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(4)
            client.connect(str(path))
            request = json.dumps({"command": command, "text": text}, ensure_ascii=False) + "\n"
            client.sendall(request.encode("utf-8"))
            response = bytearray()
            while len(response) < 65536:
                piece = client.recv(4096)
                if not piece or b"\n" in piece:
                    response.extend(piece)
                    break
                response.extend(piece)
        value = json.loads(response.decode("utf-8").splitlines()[0])
        return value if isinstance(value, dict) else {"ok": False, "error": "Invalid voice response"}
    except (OSError, ValueError, IndexError) as exc:
        return {"ok": False, "error": "Okal voice is unavailable: " + str(exc)}


class StudioServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int]):
        super().__init__(address, StudioHandler)
        self.csrf = secrets.token_urlsafe(32)


class StudioHandler(BaseHTTPRequestHandler):
    server: StudioServer

    def log_message(self, format: str, *args: object) -> None:
        print("studio:", format % args)

    def _headers(self, code: int, content_type: str, length: int) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; "
                         "style-src 'self'; img-src 'self'; connect-src 'self'; "
                         "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
        self.end_headers()

    def _send(self, code: int, content: bytes, content_type: str) -> None:
        self._headers(code, content_type, len(content))
        self.wfile.write(content)

    def _json(self, code: int, value: dict) -> None:
        self._send(code, json.dumps(value, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _allowed_host(self) -> bool:
        return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

    def do_GET(self) -> None:
        if not self._allowed_host():
            return self._json(403, {"ok": False, "error": "Invalid host"})
        path = urlsplit(self.path).path
        if path == "/api/state":
            return self._json(200, {"voice": read_voice(), "canvas": read_canvas()})
        if path.startswith("/media/") and MEDIA_NAME.fullmatch(path[7:]):
            media = Path.home() / ".local/share/okal/studio/media" / path[7:]
            try:
                if media.is_symlink() or not media.is_file() or media.stat().st_size > 12 * 1024 * 1024:
                    raise OSError("media unavailable")
                return self._send(200, media.read_bytes(),
                                  mimetypes.guess_type(media.name)[0] or "application/octet-stream")
            except OSError:
                return self._json(404, {"ok": False, "error": "Media unavailable"})
        file_name = STATIC_FILES.get(path)
        if not file_name:
            return self._json(404, {"ok": False, "error": "Not found"})
        content = (STATIC / file_name).read_bytes()
        if path == "/":
            content = content.replace(b"__OKAL_CSRF__", self.server.csrf.encode("ascii"))
        content_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
        return self._send(200, content, content_type + ("; charset=utf-8" if content_type.startswith("text/") else ""))

    def do_POST(self) -> None:
        if not self._allowed_host():
            return self._json(403, {"ok": False, "error": "Invalid host"})
        origin = f"http://127.0.0.1:{self.server.server_port}"
        if (self.path != "/api/voice" or self.headers.get("Origin") != origin or
                self.headers.get("X-Okal-CSRF") != self.server.csrf):
            return self._json(403, {"ok": False, "error": "Request not allowed"})
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            return self._json(415, {"ok": False, "error": "JSON required"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4096:
                raise ValueError("Invalid request size")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("Expected an object")
            command = payload.get("command")
            text = payload.get("text", "")
            if command not in ("ask", "toggle", "cancel") or not isinstance(text, str) or len(text) > 2000:
                raise ValueError("Unsupported command or text length")
        except (ValueError, UnicodeError):
            return self._json(400, {"ok": False, "error": "Invalid request"})
        response = voice_command(command, text)
        return self._json(200 if response.get("ok") else 503, response)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Okal Studio local browser UI")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true", help="Do not launch the default browser")
    args = parser.parse_args(argv)
    if not 1024 <= args.port <= 65535:
        parser.error("port must be between 1024 and 65535")
    server = StudioServer(("127.0.0.1", args.port))
    address = f"http://127.0.0.1:{server.server_port}"
    print(f"Okal Studio: {address} (local only)")
    if not args.no_open:
        threading.Timer(0.4, lambda: webbrowser.open(address)).start()
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
