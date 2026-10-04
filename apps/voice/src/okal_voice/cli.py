"""Command-line and Omarchy hotkey entry point."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shlex
import shutil
import socket
import sys
import sysconfig
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from .config import VoiceConfig
from .runtime import StateStore
from .service import run_daemon


def load_voice_environment(path: Path | None = None) -> None:
    """Use the service settings for direct CLI checks, without executing the file."""
    path = path or Path.home() / ".config/okal/voice.env"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        try:
            tokens = shlex.split(raw, comments=True)
        except ValueError:
            continue
        if len(tokens) != 1 or "=" not in tokens[0]:
            continue
        key, value = tokens[0].split("=", 1)
        if key.startswith("OKAL_") and key.replace("_", "").isalnum():
            os.environ.setdefault(key, value)


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
    if config.stt_backend == "whisper.cpp":
        whisper = shutil.which(config.whisper_bin)
        add("whisper.cpp", bool(whisper), whisper or f"missing {config.whisper_bin}")
        add("Whisper model", config.whisper_model.is_file(), str(config.whisper_model))
    elif config.stt_backend == "faster-whisper":
        installed = importlib.util.find_spec("faster_whisper") is not None
        add("faster-whisper", installed, "installed" if installed else "run setup-local-voice-stack.sh")
        if config.stt_model_dir:
            ready = all((config.stt_model_dir / name).is_file() for name in ("model.bin", "config.json"))
            add("STT model", ready, str(config.stt_model_dir))
        else:
            add("STT model", True, f"{config.stt_model} (cache verified on first use)")
        if config.stt_device == "cuda":
            packages = Path(sysconfig.get_path("purelib"))
            ready = (packages / "nvidia/cublas/lib/libcublas.so.12").is_file() and (packages / "nvidia/cudnn/lib/libcudnn.so.9").is_file()
            add("CUDA libraries", ready, "CUDA 12 cuBLAS and cuDNN 9" if ready else "run pip install '.[cuda]' in the voice environment")
    else:
        add("STT backend", True, f"{config.stt_backend} (model verified on first use)")
    try:
        with urlopen(f"{config.ollama_endpoint}/api/tags", timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
        names = {str(item.get("name", "")) for item in payload.get("models", [])}
        present = config.router_model in names or any(name.startswith(f"{config.router_model}:") for name in names)
        add("Ollama", True, config.ollama_endpoint)
        add("Router model", present, config.router_model)
        if config.conversation_model:
            chat_present = config.conversation_model in names or any(
                name.startswith(f"{config.conversation_model}:") for name in names
            )
            add("Conversation model", chat_present, config.conversation_model)
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        add("Ollama", False, str(exc))
        add("Router model", False, config.router_model)
        if config.conversation_model:
            add("Conversation model", False, config.conversation_model)
    if config.voicetut_enabled:
        from .tts_lab import SPEAKERS, check_cache

        interpreter = config.voicetut_python
        python_ready = bool(interpreter and interpreter.is_file() and os.access(interpreter, os.X_OK))
        add("VoiceTut Python", python_ready, str(interpreter or "set OKAL_VOICETUT_PYTHON"))
        if config.voicetut_speaker in SPEAKERS:
            _, missing = check_cache((config.voicetut_speaker,))
            add("VoiceTut cache", not missing, ", ".join(missing) if missing else config.voicetut_speaker)
        else:
            add("VoiceTut cache", False, f"unsupported speaker: {config.voicetut_speaker}")
    piper = shutil.which(config.piper_bin)
    espeak = shutil.which(config.espeak_bin)
    silma_ready = bool(config.silma_enabled and config.silma_ref_audio and config.silma_ref_audio.is_file()
                       and config.silma_ref_text and importlib.util.find_spec("silma_tts"))
    piper_ready = bool(piper and any(model and model.is_file() for model in
                                     (config.piper_ar_model, config.piper_en_model)))
    add("Local TTS", bool(config.voicetut_enabled or silma_ready or piper_ready or espeak),
        "VoiceTut" if config.voicetut_enabled else ("SILMA" if silma_ready else ("Piper" if piper_ready else (espeak or "configure SILMA reference or install a local fallback"))))
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
    load_voice_environment()
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
