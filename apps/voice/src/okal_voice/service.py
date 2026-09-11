"""Local daemon orchestrating capture, inference, routing, and display state."""

from __future__ import annotations

import json
import socketserver
import threading
import time
import uuid
from pathlib import Path
from typing import Protocol

from .capture import CaptureError, PipeWireCapture
from .config import VoiceConfig
from .contracts import RouteDecision, VoicePhase, VoiceSnapshot
from .providers import LocalTts, OllamaRouter, ProviderError, build_stt
from .runtime import StateStore


class Stt(Protocol):
    def transcribe(self, audio_path: Path) -> tuple[str, str]: ...


class Router(Protocol):
    def route(self, transcript: str) -> RouteDecision: ...


class Tts(Protocol):
    def speak(self, text: str, language: str) -> str: ...


class VoiceService:
    def __init__(self, config: VoiceConfig | None = None, store: StateStore | None = None, *, capture=None, stt: Stt | None = None, router: Router | None = None, tts: Tts | None = None):
        self.config = config or VoiceConfig.from_env()
        self.store = store or StateStore()
        self.capture = capture or PipeWireCapture(self.store, sample_rate=self.config.sample_rate)
        self.stt = stt or build_stt(self.config)
        self.router = router or OllamaRouter(self.config)
        self.tts = tts or LocalTts(self.config)
        self.phase = VoicePhase.IDLE
        self.session_id = ""
        self._lock = threading.RLock()
        self._cancel = threading.Event()
        self._pipeline: threading.Thread | None = None
        self._publish(VoicePhase.IDLE)

    def handle(self, request: dict) -> dict:
        command = request.get("command")
        if command == "toggle":
            return self.toggle()
        if command == "cancel":
            return self.cancel()
        if command == "status":
            return {"ok": True, "state": self.store.read().as_dict()}
        if command == "say":
            return self.say(str(request.get("text", "")).strip())
        if command == "quit":
            self.cancel()
            return {"ok": True, "message": "stopping", "stop": True}
        return {"ok": False, "error": "unknown control command"}

    def toggle(self) -> dict:
        with self._lock:
            if self.phase is VoicePhase.IDLE:
                self.session_id = uuid.uuid4().hex
                self._cancel.clear()
                try:
                    self.capture.start()
                except CaptureError as exc:
                    self._publish(VoicePhase.ERROR, text=str(exc))
                    return {"ok": False, "error": str(exc)}
                self._publish(VoicePhase.LISTENING, text="Listening — اضغط مرة أخرى للإرسال")
                return {"ok": True, "phase": self.phase.value}
            if self.phase is VoicePhase.LISTENING:
                try:
                    audio_path, duration = self.capture.stop()
                except CaptureError as exc:
                    self._publish(VoicePhase.ERROR, text=str(exc))
                    return {"ok": False, "error": str(exc)}
                if duration < self.config.min_audio_seconds:
                    audio_path.unlink(missing_ok=True)
                    self._publish(VoicePhase.BLOCKED, text="No speech captured — لم يتم تسجيل كلام كافٍ")
                    return {"ok": False, "error": "audio is too short"}
                self._start_pipeline(audio_path)
                return {"ok": True, "phase": VoicePhase.TRANSCRIBING.value}
            return self.cancel()

    def say(self, text: str) -> dict:
        text = " ".join(text.strip().split())
        if not text:
            self._publish(VoicePhase.BLOCKED, text="Empty request — الطلب فارغ")
            return {"ok": False, "error": "text is required"}
        with self._lock:
            if self.phase is not VoicePhase.IDLE:
                return {"ok": False, "error": "voice session is busy"}
            self.session_id = uuid.uuid4().hex
            self._cancel.clear()
            self._start_routing(text, "unknown")
            return {"ok": True, "phase": VoicePhase.ROUTING.value}

    def cancel(self) -> dict:
        with self._lock:
            self._cancel.set()
            if self.capture.active:
                self.capture.cancel()
            self._publish(VoicePhase.IDLE, text="Cancelled — تم الإلغاء")
            return {"ok": True, "phase": self.phase.value}

    def _start_pipeline(self, audio_path: Path) -> None:
        self._publish(VoicePhase.TRANSCRIBING, text="Transcribing locally — جاري فهم كلامك")

        def work() -> None:
            try:
                transcript, language = self.stt.transcribe(audio_path)
                if self._cancel.is_set():
                    return
                self._route_and_speak(transcript, language)
            except ProviderError as exc:
                self._publish(VoicePhase.ERROR, text=str(exc))
            finally:
                audio_path.unlink(missing_ok=True)

        self._pipeline = threading.Thread(target=work, daemon=True, name="okal-voice-pipeline")
        self._pipeline.start()

    def _start_routing(self, text: str, language: str) -> None:
        self._publish(VoicePhase.ROUTING, text=text, language=language)

        def work() -> None:
            try:
                self._route_and_speak(text, language)
            except ProviderError as exc:
                self._publish(VoicePhase.ERROR, text=str(exc))

        self._pipeline = threading.Thread(target=work, daemon=True, name="okal-voice-router")
        self._pipeline.start()

    def _route_and_speak(self, transcript: str, detected_language: str) -> None:
        self._publish(VoicePhase.ROUTING, text=transcript, language=detected_language)
        decision = self.router.route(transcript)
        if self._cancel.is_set():
            return
        self.store.append_route({
            "schema_version": "okal.voice.route.v1",
            "session_id": self.session_id,
            "transcript": transcript,
            "decision": decision.as_dict(),
            "created_at": time.time(),
            "authority": "classification-only",
        })
        display = decision.reply or decision.summary
        if decision.route.value == "blocked":
            self._publish(VoicePhase.BLOCKED, text=display, language=decision.language, route=decision.route.value)
            return
        self._publish(VoicePhase.SPEAKING, text=display, language=decision.language, route=decision.route.value)
        try:
            self.tts.speak(display, decision.language)
        except ProviderError as exc:
            self._publish(VoicePhase.ERROR, text=f"{display} — TTS unavailable: {exc}", language=decision.language, route=decision.route.value)
            return
        if not self._cancel.is_set():
            self._publish(VoicePhase.IDLE, text=display, language=decision.language, route=decision.route.value)

    def _publish(self, phase: VoicePhase, *, text: str = "", language: str = "unknown", route: str = "") -> None:
        with self._lock:
            self.phase = phase
            self.store.publish(VoiceSnapshot.new(phase, session_id=self.session_id, text=text, language=language, route=route))


class _ControlHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        try:
            request = json.loads(self.rfile.readline(65536).decode("utf-8"))
            if not isinstance(request, dict):
                raise ValueError("request must be an object")
            response = self.server.voice_service.handle(request)  # type: ignore[attr-defined]
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            response = {"ok": False, "error": f"invalid control request: {exc}"}
        self.wfile.write((json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8"))
        if response.get("stop"):
            threading.Thread(target=self.server.shutdown, daemon=True).start()


class _ControlServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    allow_reuse_address = False


def run_daemon(service: VoiceService | None = None) -> int:
    service = service or VoiceService()
    socket_path = service.store.socket_path
    socket_path.unlink(missing_ok=True)
    server = _ControlServer(str(socket_path), _ControlHandler)
    server.voice_service = service  # type: ignore[attr-defined]
    socket_path.chmod(0o600)
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        service.cancel()
        server.server_close()
        socket_path.unlink(missing_ok=True)
    return 0
