#!/usr/bin/env python3
"""Score real pinned local-model candidates; retain actual outputs as evidence."""
import argparse
import json
import os
from pathlib import Path
import statistics
import time

from okal_core.cognitive.config import AdapterConfig
from okal_core.cognitive.learning import extract, EXTERNAL
from okal_core.cognitive.ledger import SENSITIVE
from okal_core.cognitive.providers import LocalRuntime, install_network_guard


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--state', type=Path, required=True)
    args = parser.parse_args()
    if args.state.exists() or 'okal-core' in args.state.parts:
        raise ValueError('fresh_isolated_state_required')
    os.umask(0o077)
    config = AdapterConfig.read(args.config)
    install_network_guard()
    from okal_core.cognitive.adapter import Mem0Adapter
    runtime = LocalRuntime(config.llm, config.embedding, config.dimensions,
                           embedding_gpu=config.embedding_gpu)
    adapter = Mem0Adapter(args.state, runtime)
    cases = json.loads((Path(__file__).parents[1]/'evals/cognitive-extraction.json').read_text())['cases']
    results, true_positive, returned, expected = [], 0, 0, 0
    try:
        for case in cases:
            started = time.monotonic()
            error = None
            raw_outputs = []
            try:
                actual = extract(adapter.memory, case['message'], case.get('project_id'), diagnostics=raw_outputs.append)
            except Exception as exc:
                actual, error = [], type(exc).__name__
            matched = 0
            for target in case['expected']:
                if any(all(item.get(k)==v for k,v in target.items() if k!='terms')
                       and all(term.casefold() in item['quote'].casefold() for term in target.get('terms', []))
                       for item in actual):
                    matched += 1
            true_positive += matched
            returned += len(actual)
            expected += len(case['expected'])
            result = {'id': case['id'], 'actual': actual, 'expected': case['expected'],
                      'matched': matched, 'error': error, 'seconds': time.monotonic()-started,
                      'raw_model_outputs': raw_outputs,
                      'model_called': not bool(EXTERNAL.search(case['message']) or SENSITIVE.search(case['message']))}
            results.append(result)
            print(json.dumps(result, ensure_ascii=False), flush=True)
    finally:
        adapter.close()
    report = {'llm': config.llm.name, 'llm_digest': config.llm.digest, 'cases': results,
              'precision': true_positive/returned if returned else 0,
              'recall': true_positive/expected if expected else 1,
              'false_memories_in_negative_cases': sum(len(r['actual']) for r in results if not r['expected']),
              'errors': sum(r['error'] is not None for r in results),
              'latency_seconds_p50': statistics.median(r['seconds'] for r in results if r['model_called'])}
    (args.state/'extraction-result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='cases'}, ensure_ascii=False))


if __name__=='__main__':
    main()
