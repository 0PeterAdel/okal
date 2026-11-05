"""Private stdin/stdout RPC client; no network listener or credentials.

The Core runtime never imports Mem0. Calls are bounded and serialized, and a
busy extraction cannot make a chat wait for a vector lookup.
"""
import json
import os
from pathlib import Path
import select
import subprocess
import threading
import time
import uuid

from .config import AdapterConfig


class AdapterUnavailable(ValueError):
    pass


class AdapterClient:
    def __init__(self, state_directory: Path):
        self.directory = state_directory
        self.config_path = self.directory / 'cognitive.json'
        self.process = None
        self.lock = threading.Lock()

    def _start(self):
        if self.process is not None and self.process.poll() is None:
            return
        self._stop()
        config = AdapterConfig.read(self.config_path)
        source = Path(__file__).resolve().parents[2]
        environment = {
            'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'PYTHONPATH': str(source),
            'PYTHONNOUSERSITE': '1', 'MEM0_TELEMETRY': 'False', 'DO_NOT_TRACK': '1',
            'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1',
            'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'OTEL_SDK_DISABLED': 'true',
        }
        self.process = subprocess.Popen([
            str(config.python), '-m', 'okal_core.cognitive.worker_process',
            '--config', str(self.config_path), '--directory', str(self.directory / 'cognitive')],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            cwd=self.directory, env=environment, shell=False, bufsize=0, close_fds=True)

    def call(self, method, payload, *, timeout=90, opportunistic=False):
        if method not in {'project', 'delete', 'search', 'extract', 'ping'}:
            raise ValueError('unknown_memory_operation')
        if not self.lock.acquire(timeout=0 if opportunistic else 1):
            raise AdapterUnavailable('memory_adapter_busy')
        try:
            self._start()
            process = self.process
            request_id = uuid.uuid4().hex
            raw = json.dumps({'id': request_id, 'method': method, 'payload': payload}, ensure_ascii=False).encode() + b'\n'
            if len(raw) > 32_000:
                raise ValueError('memory_request_budget')
            process.stdin.write(raw)
            process.stdin.flush()
            deadline = time.monotonic() + timeout
            result = bytearray()
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not select.select([process.stdout], [], [], remaining)[0]:
                    raise AdapterUnavailable('memory_adapter_timeout')
                chunk = os.read(process.stdout.fileno(), 4096)
                if not chunk:
                    raise AdapterUnavailable('memory_adapter_stopped')
                result.extend(chunk)
                if len(result) > 32_000:
                    raise AdapterUnavailable('memory_response_budget')
                if b'\n' in result:
                    if not result.endswith(b'\n') or result.count(b'\n') != 1:
                        raise AdapterUnavailable('memory_protocol_error')
                    response = json.loads(result)
                    if response.get('id') != request_id or not response.get('ok'):
                        raise AdapterUnavailable('memory_operation_failed')
                    return response['result']
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self._stop()
            if isinstance(exc, AdapterUnavailable):
                raise
            raise AdapterUnavailable('memory_adapter_unavailable') from None
        finally:
            self.lock.release()

    def _stop(self):
        if self.process is not None:
            process, self.process = self.process, None
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
            for stream in (process.stdin, process.stdout):
                if stream:
                    stream.close()

    def close(self):
        with self.lock:
            self._stop()
