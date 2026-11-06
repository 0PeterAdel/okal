#!/usr/bin/env python3
"""Read-only provenance audit of a finished synthetic real-model benchmark.

Preserves the original report. Keyword matches count as recall only when a
relevant ledger revision or an actually supplied archive excerpt supports them.
No gold data is sent to an inference provider. Run after the writer has exited.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3

from evaluate_cognitive_memory import has_concepts


def audit(directory):
    manifest=json.loads((directory/'manifest.json').read_text())
    raw=json.loads((directory/'report.json').read_text())
    if raw.get('incomplete') or not manifest.get('archive_assistant_mode','').startswith('fixture_archive;'):
        raise ValueError('completed_synthetic_benchmark_required')
    answers=[json.loads(line) for line in (directory/'answers.jsonl').read_text().splitlines()]
    rows=[]
    with sqlite3.connect((directory/'core.sqlite3').as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        for answer in answers:
            concepts=answer['expected_concepts']
            ledger_support=[]
            for source in answer['sources']:
                row=db.execute('SELECT snapshot FROM memory_versions WHERE memory_id=? AND revision=?',
                               (source['id'],source['revision'])).fetchone()
                record=json.loads(row['snapshot']) if row and row['snapshot'] else None
                if (source['id'] in answer['relevant_ledger_ids'] and record
                        and has_concepts(record['content'],concepts)):
                    ledger_support.append({'id':source['id'],'revision':source['revision']})
            # Resolve only the actual persisted response, never an unrelated
            # archive hit that happens to contain the expected answer.
            persisted=[]
            for row in db.execute('SELECT response FROM chat_turns WHERE user_text=? AND response IS NOT NULL',
                                  (answer['question'],)):
                response=json.loads(row['response'])
                if (response.get('answer')==answer['actual_answer']
                        and response.get('context_sources',[])==answer['sources']):
                    persisted.append(response)
            archive_support=[]
            # If repeated identical outputs had different archive context,
            # accept only support common to every matching persisted response.
            common=None
            for response in persisted:
                supported=set()
                for source in response.get('archive_sources',[]):
                    row=db.execute('SELECT user_text FROM chat_turns WHERE id=?',(source['turn_id'],)).fetchone()
                    if row and has_concepts(row['user_text'][:500],concepts):
                        supported.add(source['turn_id'])
                common=supported if common is None else common & supported
            archive_support=sorted(common or ())
            supported=bool(ledger_support or archive_support)
            rows.append({'id':answer['id'],'family':answer['family'],'raw_passed':answer['passed'],
                'provenance_supported':supported,'audited_passed':bool(answer['passed'] and supported),
                'ledger_support':ledger_support,'archive_support':archive_support,
                'persisted_response_found':bool(persisted),
                'language_adherence':answer['language_adherence']})
    thresholds={'preference':.90,'project':.85,'conversation':.90}
    families={}
    for name,threshold in thresholds.items():
        subset=[row for row in rows if row['family']==name]
        count=sum(row['audited_passed'] for row in subset)
        families[name]={'answered':len(subset),'passed':count,'recall':count/len(subset) if subset else 0,
                        'threshold':threshold,'gate_passed':bool(subset) and count/len(subset)>=threshold}
    language=[row['language_adherence'] for row in rows if row['language_adherence'] is not None]
    components={}
    for path in directory.rglob('*'):
        if path.is_file() and path.name!='answer-audit.json':
            group=path.relative_to(directory).parts[0]
            components[group]=components.get(group,0)+path.stat().st_size
    result={'source_head':manifest['source_head'],'source_clean':manifest['source_clean'],
        'raw_report_sha256':hashlib.sha256((directory/'report.json').read_bytes()).hexdigest(),
        'scoring':'Raw answer concepts plus support in actual sent ledger revisions or archive excerpts. HISTORY/checkpoints are deliberately not credited because their trimmed contents were not journalled.',
        'families':families,'answer_count':len(rows),
        'unsupported_raw_passes':[r['id'] for r in rows if r['raw_passed'] and not r['provenance_supported']],
        'missing_persisted_responses':[r['id'] for r in rows if not r['persisted_response_found']],
        'reply_language_adherence':{'scored':len(language),'passed':sum(language),
                                    'ratio':sum(language)/len(language) if language else None},
        'final_disk_bytes_excluding_this_audit':sum(components.values()),'disk_components':components,
        'quality_gates_passed':all(f['gate_passed'] for f in families.values()),
        'rows':rows}
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',type=Path,required=True)
    args=parser.parse_args()
    if not args.state.is_absolute() or 'okal-core' in args.state.parts:
        parser.error('absolute isolated synthetic benchmark state required')
    result=audit(args.state)
    (args.state/'answer-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},ensure_ascii=False,indent=2))
    return 0 if result['quality_gates_passed'] and not result['missing_persisted_responses'] else 2


if __name__=='__main__':
    raise SystemExit(main())
