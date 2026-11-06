#!/usr/bin/env python3
"""Real Mem0/Qdrant/vault regression for memories sharing an owner sentence.

Synthetic fixture messages and explicit ledger writes isolate forgetting from
extraction quality. The actual SDK, persistent index and Markdown files are used.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import uuid

from okal_core.cognitive.retrieval import Retrieval
from okal_core.cognitive.service import MemoryWorker
from okal_core.cognitive.vault import Vault
from okal_core.intelligence import Intelligence
from okal_core.mail.private import write_private
from okal_core.store import Conflict, Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    if not args.state.is_absolute() or args.state.exists() or 'okal-core' in args.state.parts:
        parser.error('fresh private synthetic state required')
    os.umask(0o077)
    args.state.mkdir(parents=True, mode=0o700)
    write_private(args.state / 'cognitive.json', json.loads(args.config.read_text()))
    store = Store(args.state)
    chat = Intelligence(store)
    ledger = chat.cognitive
    worker = MemoryWorker(store)
    vault = Vault(ledger)
    cid = chat.create('Synthetic shared-source forgetting')['id']

    def source(message):
        claim = chat.begin(cid, uuid.uuid4().hex, message)
        chat.finish(claim['turn_id'], claim['lease'],
                    {'answer': 'Fixture archive acknowledgement.', 'mode': 'fixture_archive'})
        job = ledger.claim_job()
        assert job['turn_id'] == claim['turn_id']
        ledger.apply_job(job['turn_id'], job['lease'], [])
        return claim['turn_id']

    def drain():
        for _ in range(30):
            worker.tick()
            health = ledger.health()
            if (not health['projections'].get('pending', 0)
                    and health['rebuild']['status'] == 'current'):
                assert not health['projections'].get('failed', 0), health
                return
        raise AssertionError('bounded_projection_drain_failed')

    report = {'synthetic_only': True,
              'source_head': subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True,
                                           text=True, check=True).stdout.strip(),
              'source_clean': not subprocess.run(['git', 'status', '--porcelain'], capture_output=True,
                                               text=True, check=True).stdout.strip(),
              'scope': 'Real SDK/index/vault lifecycle; fixture archive, no model-answer scoring.'}
    try:
        quote = 'Always answer in Egyptian Arabic and keep replies concise.'
        turn = source(quote + ' This independent owner sentence survives.')
        records = [ledger.save(key, quote, kind='instruction', source_turn=turn)
                   for key in ('communication.language', 'communication.style')]
        records.append(ledger.save('copied preference', quote))
        independent = ledger.save('research', 'I prefer offline research.')
        drain()
        stale_hits = worker.adapter.call('search', {'query': quote, 'limit': 16})
        removed_ids = {r['id'] for r in records}
        assert removed_ids <= {r['id'] for r in stale_hits}
        notes = [(vault._locate(r['id'])[0], vault._locate(r['id'])[0].read_text(), r)
                 for r in records]
        inflight = chat.begin(cid, uuid.uuid4().hex, 'What is my speaking style?')
        chat.context(cid, quote, inflight['turn_id'])
        chat.forget(records[1]['id'])
        assert removed_ids.isdisjoint({r['id'] for r in ledger.active(stale_hits)})
        try:
            chat.finish(inflight['turn_id'], inflight['lease'], {'answer': quote, 'mode': 'owner_memory'})
        except Conflict:
            pass
        else:
            raise AssertionError('cached_shared_source_response_not_fenced')
        drain()
        assert removed_ids.isdisjoint({r['id'] for r in worker.adapter.call('search', {'query': quote, 'limit': 16})})
        assert all(not path.exists() for path, _, _ in notes)
        for path, raw, record in notes:
            path.write_text(raw)
            try:
                vault.import_revision(record['id'], record['revision'], hashlib.sha256(quote.encode()).hexdigest())
            except Conflict:
                pass
            else:
                raise AssertionError('rediscovered_shared_source_note_resurrected')
            vault.delete(record['id'])
        ledger.request_rebuild()
        drain()
        chosen, context = Retrieval(ledger).select(cid, quote)
        assert quote not in json.dumps({'records': chosen, 'context': context})
        assert {r['id'] for r in chat.memories()['items']} == {independent['id']}
        assert 'This independent owner sentence survives.' in json.dumps(chat.get(cid))
        assert quote not in json.dumps([ledger.versions(r['id']) for r in records])

        # A partial quote retains authority only if a separate source survives.
        compound = 'I prefer offline references. I prefer concise explanations.'
        first = source(compound)
        whole = ledger.save('compound', compound, source_turn=first)
        research = ledger.save('references', 'I prefer offline references.', source_turn=first)
        partial = ledger.save('reply.detail', 'I prefer concise explanations.', source_turn=first)
        second = source('I prefer offline references.')
        ledger.save('references', research['content'], source_turn=second)
        drain()
        chat.forget(whole['id'])
        drain()
        active = {r['id']: r for r in chat.memories()['items']}
        assert whole['id'] not in active and partial['id'] not in active
        assert active[research['id']]['source_turn'] == second
        assert active[research['id']]['revision'] == 2
        hits = worker.adapter.call('search', {'query': research['content'], 'limit': 16})
        assert research['id'] in {r['id'] for r in ledger.active(hits)}
        assert vault.preview(research['id'])['revision'] == 2
        with store.connect() as db:
            assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert not db.execute('PRAGMA foreign_key_check').fetchall()
            assert db.execute('SELECT COUNT(*) FROM memory_tombstones').fetchone()[0] == 5
        report.update(shared_facets_and_manual_duplicate_forgotten=True,
                      cached_response_fenced=True, stale_vectors_rejected=True,
                      physical_vectors_and_notes_removed=True, stale_note_imports_rejected=True,
                      absent_after_rebuild=True, unrelated_owner_text_preserved=True,
                      partial_quote_without_support_forgotten=True,
                      independently_supported_memory_revised_and_reprojected=True,
                      integrity_check='ok', foreign_key_violations=0, health=ledger.health())
    finally:
        worker.stop()
    (args.state / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
