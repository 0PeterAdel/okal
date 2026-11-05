#!/usr/bin/env python3
"""Real local Mem0/Qdrant acceptance and embedding comparison on synthetic data.

Run in requirements-memory.lock's environment, never against owner state.
The result JSON contains measured outcomes, model pins and actual rankings.
"""
import argparse
import json
import math
import os
from pathlib import Path
import statistics
import time
import uuid

from okal_core.cognitive.providers import LocalRuntime, ModelPin, install_network_guard

DOCUMENTS = [
    'أنا بفضل إنك ترد عليا بالمصري وباختصار وتدخل في الموضوع على طول.',
    'We selected SQLite for the Orion garden project because it works offline.',
    'The Orion satellite project uses PostgreSQL for concurrent telemetry writers.',
    'For the garden project, the next task is testing irrigation sensors.',
    'For the satellite project, the next task is calibrating the radio antenna.',
    'Please use English for technical documentation.',
    'My long-term goal is to learn Arabic calligraphy.',
    'آخر قرار لمشروع الحديقة هو استخدام ري بالتنقيط لتوفير المياه.',
    'We postponed the satellite launch until September.',
    'My favorite editor is Vim because I prefer keyboard navigation.',
    'في المحادثة دي خلصنا التصميم ولسه اختبار الاسترجاع بعد إعادة التشغيل.',
    'The reading club meets on Tuesday evenings.',
]
QUERIES = [
    ('How do I prefer you to speak to me?', 0),
    ('Do I want long introductions?', 0),
    ('إيه سبب اختيار قاعدة البيانات للحديقة؟', 1),
    ('Why did the garden use a local database?', 1),
    ('Which database stores satellite telemetry?', 2),
    ('قاعدة بيانات القمر الصناعي إيه؟', 2),
    ('What is pending for the garden?', 3),
    ('هنعمل إيه بعد كده في مشروع الحديقة؟', 3),
    ('What is pending for the satellite?', 4),
    ('المهمة الجاية للقمر الصناعي إيه؟', 4),
    ('Which language should technical docs use?', 5),
    ('لغة التوثيق التقني اللي بفضلها إيه؟', 5),
    ('What art do I want to study?', 6),
    ('أنا عايز أتعلم إيه على المدى الطويل؟', 6),
    ('What irrigation method did we decide on?', 7),
    ('Why are we using drip irrigation?', 7),
    ('When was the satellite launch moved to?', 8),
    ('أي محرر نصوص بفضله وليه؟', 9),
    ('What remains unfinished in this conversation?', 10),
    ('What evening does the reading club meet?', 11),
]


def cosine(left, right):
    return sum(a*b for a,b in zip(left,right)) / (
        math.sqrt(sum(a*a for a in left))*math.sqrt(sum(b*b for b in right)))


def percentile(values, quantile):
    return sorted(values)[max(0, math.ceil(len(values)*quantile)-1)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--embedding', required=True)
    parser.add_argument('--embedding-digest', required=True)
    parser.add_argument('--dimensions', type=int, required=True)
    parser.add_argument('--llm', required=True)
    parser.add_argument('--llm-digest', required=True)
    parser.add_argument('--gpu', action='store_true')
    args = parser.parse_args()
    if 'okal-core' in args.state.parts or args.state.exists():
        raise ValueError('fresh_isolated_synthetic_state_required')
    os.umask(0o077)
    args.state.mkdir(mode=0o700, parents=True)
    install_network_guard()
    runtime = LocalRuntime(ModelPin(args.llm, args.llm_digest),
        ModelPin(args.embedding, args.embedding_digest), args.dimensions,
        embedding_gpu=args.gpu)
    report = {'embedding': args.embedding, 'digest': args.embedding_digest,
              'dimensions': args.dimensions, 'embedding_gpu': args.gpu,
              'corpus': len(DOCUMENTS), 'queries': len(QUERIES), 'rankings': []}
    started = time.monotonic()
    vectors = runtime.embed(DOCUMENTS)
    report['index_seconds'] = time.monotonic()-started
    latencies = []
    for query, expected in QUERIES:
        started = time.monotonic()
        vector = runtime.embed([query], 'search')[0]
        ranked = sorted(range(len(vectors)), key=lambda i: cosine(vector,vectors[i]), reverse=True)
        latencies.append(time.monotonic()-started)
        report['rankings'].append({'query': query, 'expected': expected, 'actual': ranked[:3]})
    report['recall_at_1'] = sum(r['actual'][0]==r['expected'] for r in report['rankings'])/len(QUERIES)
    report['recall_at_3'] = sum(r['expected'] in r['actual'] for r in report['rankings'])/len(QUERIES)
    report['query_seconds_p50'] = statistics.median(latencies)
    report['query_seconds_p95'] = percentile(latencies,.95)
    from okal_core.cognitive.adapter import Mem0Adapter
    adapter = Mem0Adapter(args.state/'adapter', runtime)
    memory_id = uuid.uuid4().hex
    try:
        # Real CRUD, metadata tracing, persistent reopen and lifecycle ownership.
        record = {'id': memory_id, 'revision': 1, 'scope': 'owner', 'content': DOCUMENTS[0]}
        first = adapter.project(record)
        again = adapter.project(record)
        assert first['vector_id'] == again['vector_id'], 'non_idempotent_projection'
        hits = adapter.search(QUERIES[0][0])
        assert any(h['id']==memory_id and h['revision']==1 for h in hits), 'semantic_retrieval_failed'
        record.update(revision=2, content='I now prefer detailed English explanations.')
        updated = adapter.project(record)
        assert first['vector_id'] == updated['vector_id'], 'update_replaced_identity'
        assert any(h['id']==memory_id and h['revision']==2 for h in adapter.search('preferred speaking style')), 'update_not_visible'
        other_runtime = LocalRuntime(ModelPin(args.llm,args.llm_digest), ModelPin(args.embedding,args.embedding_digest),args.dimensions)
        try:
            Mem0Adapter(args.state/'adapter', other_runtime)
        except ValueError as exc:
            assert str(exc) == 'memory_adapter_already_running'
        else:
            raise AssertionError('exclusive_owner_lock_missing')
        finally:
            other_runtime.close()
        report['crud_before_reopen'] = 'passed'
    finally:
        adapter.close()
    runtime = LocalRuntime(ModelPin(args.llm,args.llm_digest), ModelPin(args.embedding,args.embedding_digest),args.dimensions, embedding_gpu=args.gpu)
    adapter = Mem0Adapter(args.state/'adapter', runtime)
    try:
        assert any(h['id']==memory_id and h['revision']==2 for h in adapter.search('English explanations')), 'persistence_failed'
        adapter.delete(memory_id)
        adapter.delete(memory_id)
        assert not adapter.search('English explanations'), 'deletion_failed'
        report['reopen_delete'] = 'passed'
    finally:
        adapter.close()
    import socket
    for destination in [('example.com',443), ('127.0.0.1',8766)]:
        try:
            socket.create_connection(destination, timeout=1)
        except PermissionError:
            pass
        else:
            raise AssertionError('network_guard_failed')
    report['forbidden_network'] = 'passed'
    result = args.state/'result.json'
    result.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='rankings'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
