"""Command-line and Omarchy hotkey entry point."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import sys
from urllib.error import URLError
from urllib.request import urlopen

from .config import VoiceConfig
from .runtime import StateStore
from .service import run_daemon


def send_control(request: dict) -> dict:
    store = StateStore()
    path = store.socket_path
    try:
        mode = path.stat().st_mode
    except FileNotFoundError as exc:
        raise RuntimeError("Okal voice is not running; start okal-voice.service") from exc
    if mode & 0o077:
        raise PermissionError("refusing a control socket accessible by group/other")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(5)
        client.connect(str(path))
        client.sendall((json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8"))
        response = bytearray()
        while not response.endswith(b"\n"):
            chunk = client.recv(65536)
            if not chunk:
                break
            response.extend(chunk)
    return json.loads(response.decode("utf-8"))


def doctor(config: VoiceConfig) -> tuple[int, list[dict]]:
    checks: list[dict] = []

    def add(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    add("Python", sys.version_info >= (3, 12), sys.version.split()[0])
    add("XDG runtime", bool(os.environ.get("XDG_RUNTIME_DIR")), os.environ.get("XDG_RUNTIME_DIR", "missing"))
    for binary in ("pw-record", "pw-play"):
        found = shutil.which(binary)
        add(binary, bool(found), found or "not installed")
    whisper = shutil.which(config.whisper_bin)
    add("whisper.cpp", bool(whisper), whisper or f"missing {config.whisper_bin}")
    add("Whisper model", config.whisper_model.is_file(), str(config.whisper_model))
    try:
        with urlopen(f"{config.ollama_endpoint}/api/tags", timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
        names = {str(item.get("name", "")) for item in payload.get("models", [])}
        present = config.router_model in names or any(name.startswith(f"{config.router_model}:") for name in names)
        add("Ollama", True, config.ollama_endpoint)
        add("Router model", present, config.router_model)
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        add("Ollama", False, str(exc))
        add("Router model", False, config.router_model)
    piper = shutil.which(config.piper_bin)
    espeak = shutil.which(config.espeak_bin)
    tts_ready = bool(
        (piper and (config.piper_ar_model or config.piper_en_model)) or espeak
    )
    add("Local TTS", tts_ready, piper or espeak or "install Piper or espeak-ng")
    return (0 if all(item["ok"] for item in checks) else 1), checks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="okal")
    sub = parser.add_subparsers(dest="area", required=True)
    voice = sub.add_parser("voice", help="local-only voice entry point")
    commands = voice.add_subparsers(dest="command", required=True)
    for name in ("run", "toggle", "cancel", "status", "quit", "doctor"):
        commands.add_parser(name)
    say = commands.add_parser("say")
    say.add_argument("text", nargs="+")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        return run_daemon()
    if args.command == "doctor":
        code, checks = doctor(VoiceConfig.from_env())
        for item in checks:
            print(f"{'PASS' if item['ok'] else 'FAIL'}  {item['name']}: {item['detail']}")
        return code
    request = {"command": args.command}
    if args.command == "say":
        request["text"] = " ".join(args.text)
    try:
        response = send_control(request)
    except (RuntimeError, PermissionError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0 if response.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
