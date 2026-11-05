"""Pinned local providers for the isolated Mem0 process.

Deliberately implements Mem0's provider interface without importing Mem0 here.
No default models, environment proxy settings, tool calls, redirects or pulls.
"""
from dataclasses import dataclass
import json
import math
import re
import socket
import sys
from typing import Any

import httpx

BASE_URL = 'http://127.0.0.1:11434'
MAX_RESPONSE = 1_048_576


@dataclass(frozen=True)
class ModelPin:
    name: str
    digest: str

    def __post_init__(self):
        if (not re.fullmatch(r'[a-zA-Z0-9_.:/-]{1,100}', self.name)
                or not re.fullmatch(r'[a-f0-9]{64}', self.digest)):
            raise ValueError('invalid_local_model_pin')


class LocalRuntime:
    def __init__(self, llm: ModelPin, embedder: ModelPin, dimensions: int,
                 *, embedding_gpu: bool = False):
        if type(dimensions) is not int or not 64 <= dimensions <= 4096:
            raise ValueError('invalid_embedding_dimensions')
        if embedder.name.split(':')[0] not in {'bge-m3', 'nomic-embed-text-v2-moe'}:
            raise ValueError('unreviewed_embedding_model')
        self.llm, self.embedder, self.dimensions = llm, embedder, dimensions
        self.embedding_gpu = embedding_gpu
        self.client = httpx.Client(base_url=BASE_URL, trust_env=False,
                                   follow_redirects=False,
                                   timeout=httpx.Timeout(60, connect=3))

    def close(self):
        self.client.close()

    def request(self, path: str, payload: dict | None = None) -> dict:
        if path not in {'/api/tags', '/api/chat', '/api/embed'}:
            raise ValueError('local_inference_endpoint_denied')
        if payload is not None and len(json.dumps(payload).encode()) > 32_000:
            raise ValueError('local_inference_input_budget')
        with self.client.stream('GET' if payload is None else 'POST', path,
                                json=payload) as response:
            response.raise_for_status()
            raw = bytearray()
            for chunk in response.iter_bytes():
                raw.extend(chunk)
                if len(raw) > MAX_RESPONSE:
                    raise ValueError('local_inference_response_budget')
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError('invalid_local_inference_response')
        return result

    def verify(self, pin: ModelPin):
        tags = self.request('/api/tags').get('models', [])
        name = pin.name if ':' in pin.name else pin.name + ':latest'
        if not any(m.get('name') == name and m.get('digest') == pin.digest
                   and m.get('details', {}).get('format') == 'gguf'
                   for m in tags if isinstance(m, dict)):
            raise ValueError('local_model_missing_or_digest_changed')

    def generate(self, messages: list[dict], schema: dict | str = 'json') -> str:
        if not messages or len(messages) > 12 or any(
                m.get('role') not in {'system', 'user', 'assistant'}
                or not isinstance(m.get('content'), str) for m in messages):
            raise ValueError('invalid_memory_messages')
        self.verify(self.llm)
        result = self.request('/api/chat', {
            'model': self.llm.name, 'messages': messages, 'stream': False,
            'think': False, 'format': schema, 'keep_alive': 0,
            'options': {'temperature': 0, 'num_ctx': 4096, 'num_predict': 1000},
        })
        content = result.get('message', {}).get('content')
        if not result.get('done') or not isinstance(content, str) or len(content) > 6000:
            raise ValueError('incomplete_memory_extraction')
        return content

    def embed(self, texts: list[str], action: str = 'add') -> list[list[float]]:
        if (not 1 <= len(texts) <= 16 or any(not isinstance(t, str)
                or not t.strip() or len(t) > 1400 for t in texts)):
            raise ValueError('embedding_input_budget')
        self.verify(self.embedder)
        prefix = ''
        if self.embedder.name.startswith('nomic-embed-text-v2-moe'):
            prefix = 'search_query: ' if action == 'search' else 'search_document: '
        result = self.request('/api/embed', {
            'model': self.embedder.name, 'input': [prefix + t for t in texts],
            'truncate': False, 'keep_alive': 0,
            'options': {'num_gpu': 99 if self.embedding_gpu else 0},
        })
        vectors = result.get('embeddings')
        if (not isinstance(vectors, list) or len(vectors) != len(texts)
                or any(not isinstance(v, list) or len(v) != self.dimensions
                       or any(type(n) not in (int, float) or not math.isfinite(n)
                              for n in v) for v in vectors)):
            raise ValueError('embedding_dimension_or_value_mismatch_reindex_required')
        return vectors


_runtime: LocalRuntime | None = None


def configure(runtime: LocalRuntime):
    global _runtime
    _runtime = runtime


def runtime() -> LocalRuntime:
    if _runtime is None:
        raise ValueError('explicit_local_memory_configuration_required')
    return _runtime


class PinnedLLM:
    def __init__(self, config: Any):
        if config.model != runtime().llm.name or config.ollama_base_url != BASE_URL:
            raise ValueError('unreviewed_memory_llm')
        self.config = config

    def generate_response(self, messages, response_format=None, tools=None,
                          tool_choice='auto', **kwargs):
        if tools:
            raise ValueError('memory_model_has_no_tools')
        schema = kwargs.get('schema', 'json')
        return runtime().generate(messages, schema)


class PinnedEmbedding:
    def __init__(self, config: Any):
        if (config.model != runtime().embedder.name
                or config.embedding_dims != runtime().dimensions
                or config.ollama_base_url != BASE_URL):
            raise ValueError('unreviewed_memory_embedder')
        self.config = config

    def embed(self, text, memory_action='add'):
        return runtime().embed([text], memory_action)[0]

    def embed_batch(self, texts, memory_action='add'):
        return runtime().embed(texts, memory_action)


def install_network_guard():
    """Defense in depth for the dedicated process, not an OS sandbox claim.

    Install before importing third-party intelligence packages. No DNS, external
    connections, subprocesses, or listeners are needed by embedded Qdrant.
    """
    def audit(event, args):
        if event == 'socket.connect':
            sock, address = args
            if (sock.family != socket.AF_INET
                    or address != ('127.0.0.1', 11434)):
                raise PermissionError('memory_network_destination_denied')
        elif event == 'socket.getaddrinfo':
            if args[0] != '127.0.0.1' or args[1] != 11434:
                raise PermissionError('memory_dns_denied')
        elif event in {'socket.bind', 'subprocess.Popen', 'os.system', 'os.exec', 'os.posix_spawn'}:
            raise PermissionError('memory_process_operation_denied')
    sys.addaudithook(audit)
