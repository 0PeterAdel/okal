"""Dedicated Mem0 environment entry point. No authoritative database access."""
import argparse
from contextlib import redirect_stdout
import json
import logging
import os
from pathlib import Path
import sys

from .config import AdapterConfig
from .providers import LocalRuntime, install_network_guard


def dispatch(adapter, method, payload):
    from .learning import extract
    if not isinstance(payload, dict):
        raise ValueError('invalid_memory_payload')
    if method == 'ping' and not payload:
        return {'local': True, 'engine': 'mem0', 'index': 'qdrant'}
    if method == 'search' and set(payload) == {'query', 'limit'}:
        return adapter.search(payload['query'], payload['limit'])
    if method == 'project' and set(payload) == {'record'}:
        return adapter.project(payload['record'])
    if method == 'delete' and set(payload) == {'id'}:
        return adapter.delete(payload['id'])
    if method == 'extract' and set(payload) == {'message', 'project_id', 'existing'}:
        return extract(adapter.memory, payload['message'], payload['project_id'], payload['existing'])
    raise ValueError('invalid_memory_operation')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    config = AdapterConfig.read(args.config)
    install_network_guard()
    from .adapter import Mem0Adapter
    runtime = LocalRuntime(config.llm, config.embedding, config.dimensions,
                           embedding_gpu=config.embedding_gpu)
    logging.disable(logging.CRITICAL)
    with redirect_stdout(sys.stderr):
        adapter = Mem0Adapter(args.directory, runtime)
    try:
        while True:
            line = sys.stdin.buffer.readline(32_001)
            if not line:
                return
            if len(line) > 32_000 or not line.endswith(b'\n'):
                return 2
            request_id = None
            try:
                request = json.loads(line)
                if not isinstance(request, dict) or set(request) != {'id', 'method', 'payload'}:
                    raise ValueError('invalid_request')
                from ..intelligence import identifier
                request_id = identifier(request['id'])
                with redirect_stdout(sys.stderr):
                    result = dispatch(adapter, request['method'], request['payload'])
                response = {'id': request_id, 'ok': True, 'result': result}
            except Exception:
                # Never print owner content or third-party exception text.
                response = {'id': request_id, 'ok': False, 'error': 'memory_operation_failed'}
            raw = json.dumps(response, ensure_ascii=False)
            if len(raw.encode()) > 32_000:
                return 2
            sys.stdout.write(raw + '\n')
            sys.stdout.flush()
    finally:
        adapter.close()


if __name__ == '__main__':
    sys.exit(main())
