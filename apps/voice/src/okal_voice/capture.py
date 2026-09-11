"""Explicit PipeWire capture; no recorder exists while voice is idle."""

from __future__ import annotations

import array
import os
import subprocess
import tempfile
import threading
import wave
from pathlib import Path

from .runtime import StateStore


class CaptureError(RuntimeError):
    pass


class PipeWireCapture:
    def __init__(self, store: StateStore, *, sample_rate: int = 16000):
        self.store = store
        self.sample_rate = sample_rate
        self._process: subprocess.Popen[bytes] | None = None
        self._reader: threading.Thread | None = None
        self._raw_path: Path | None = None
        self._frames = 0
        self._lock = threading.Lock()

    @property
    def active(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(self) -> None:
        with self._lock:
            if self.active:
                raise CaptureError("capture is already active")
            descriptor, name = tempfile.mkstemp(prefix="okal-voice-", suffix=".pcm", dir=self.store.root)
            os.close(descriptor)
            Path(name).chmod(0o600)
            self._raw_path = Path(name)
            self._frames = 0
            command = [
                "pw-record",
                "--raw",
                "--rate",
                str(self.sample_rate),
                "--channels",
                "1",
                "--format",
                "s16",
                "-",
            ]
            try:
                self._process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
            except OSError as exc:
                self._raw_path.unlink(missing_ok=True)
                self._raw_path = None
                raise CaptureError(f"could not start pw-record: {exc}") from exc
            self._reader = threading.Thread(target=self._drain, daemon=True, name="okal-audio-capture")
            self._reader.start()

    def _drain(self) -> None:
        process, path = self._process, self._raw_path
        if process is None or process.stdout is None or path is None:
            return
        with path.open("ab", buffering=0) as output:
            while chunk := process.stdout.read(3200):
                output.write(chunk)
                self._frames += len(chunk) // 2
                samples = array.array("h")
                samples.frombytes(chunk[: len(chunk) - (len(chunk) % 2)])
                if samples:
                    mean_square = sum(sample * sample for sample in samples) / len(samples)
                    self.store.write_level(min((mean_square**0.5) / 9000.0, 1.0))
        self.store.write_level(0)

    def stop(self) -> tuple[Path, float]:
        with self._lock:
            if not self.active or self._process is None or self._raw_path is None:
                raise CaptureError("capture is not active")
            self._process.terminate()
            try:
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=2)
            if self._reader is not None:
                self._reader.join(timeout=2)
            raw_path = self._raw_path
            wav_path = raw_path.with_suffix(".wav")
            raw = raw_path.read_bytes()
            with wave.open(str(wav_path), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(self.sample_rate)
                handle.writeframes(raw)
            wav_path.chmod(0o600)
            raw_path.unlink(missing_ok=True)
            duration = self._frames / self.sample_rate
            self._clear()
            return wav_path, duration

    def cancel(self) -> None:
        with self._lock:
            process = self._process
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
            if self._reader is not None:
                self._reader.join(timeout=2)
            if self._raw_path is not None:
                self._raw_path.unlink(missing_ok=True)
            self.store.write_level(0)
            self._clear()

    def _clear(self) -> None:
        self._process = None
        self._reader = None
        self._raw_path = None
        self._frames = 0
