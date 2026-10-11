#!/usr/bin/env python3
"""Independent byte/event binding check for the retained B node audit."""
import collections
import gzip
import hashlib
import json
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE / 'ab_evidence_tree/results/milestone_5_acceptance_b64/acceptance_populations'
AUDIT = BASE / 'bound_audit'
REPORT = HERE / 'b64_g8_node_reaudit_20261011_independent.json'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def load(path):
    return json.loads(path.read_text())

rows = load(REPORT)['nodes']
assert len(rows) == 1551
by_trace = collections.defaultdict(list)
for row in rows:
    by_trace[row['case_id'], row['dominance']].append(row)
trace_hashes = {}
trace_report_hashes = {}
ref_hashes = {}
aggregate = load(AUDIT / 'aggregate_relaxation_v1/certificates.json')
lp_by_key = {(n['case_id'], n['dominance'], n['trace_event'], n['trace_sha256']): n for n in aggregate['nodes']}
assert len(lp_by_key) == 20
checked = collections.Counter()
for (cid, dom), subset in by_trace.items():
    path = AUDIT / 'production_trace_v1/runs' / cid / f'D{int(dom)}.jsonl.gz'
    digest = sha(path)
    trace_hashes[str(path.relative_to(BASE))] = digest
    trace_report = load(path.parent / 'report.json')
    trace_report_hashes[str((path.parent / 'report.json').relative_to(BASE))] = sha(path.parent / 'report.json')
    entry = next(r for r in trace_report if r['dominance'] == dom)
    assert entry['complete_output_equivalence'] and entry['trace_sha256'] == digest
    with gzip.open(path, 'rt') as handle:
        events = {e['index']: e['event'] for e in map(json.loads, handle) if e['kind'] == 'event'}
    expected = {i for i,e in events.items() if e['kind'] in ('region_decision','unreachable')}
    assert expected == {r['trace_event'] for r in subset}
    for row in subset:
        assert row['trace_sha256'] == digest
        event = events[row['trace_event']]
        assert row['prefix'] == event['prefix'] and row['actions'] == event['actions']
        assert row['region'] == event['region'] and row['lower_bound'] == event['lower_bound']
        provenance = row['reference_provenance']
        if 'path' in provenance:
            ref_path = BASE / provenance['path']
            assert sha(ref_path) == provenance['sha256']
            ref_hashes[provenance['path']] = provenance['sha256']
        status = row['status']
        if status == 'certified_by_independent_aggregate_superset_LP':
            key = cid, dom, row['trace_event'], digest
            proof = lp_by_key[key]
            assert proof['prefix'] == event['prefix'] and proof['actions'] == event['actions']
            assert Fraction(event['lower_bound']) <= Fraction(proof['relaxation']['independent_lower_bound'])
            assert Fraction(proof['relaxation']['independent_lower_bound']) == Fraction(row['reference_lower_bound'])
        elif status in ('certified_by_global_infimum', 'certified_by_prefix_superset_infimum'):
            assert Fraction(event['lower_bound']) <= Fraction(row['reference_lower_bound'])
        checked[status] += 1

assert sum(checked.values()) == 1551
assert len(trace_hashes) == 128
assert len(ref_hashes) == 64
assert checked == {'certified_by_independent_aggregate_superset_LP':20,
                   'certified_by_global_infimum':444,
                   'certified_empty_by_global_infeasibility':627,
                   'certified_empty_by_independent_reachability':144,
                   'certified_by_prefix_superset_infimum':314,
                   'certified_empty_by_prefix_superset':2}
output = {
  'schema':'hiroute-b-node-evidence-byte-event-review-v1',
  'scope':'Read-only check of 1551 audit rows against 128 complete production traces, trace reports, 64 REF reports, and 20 stored LP rows.',
  'replayed_auditor_sha256':sha(AUDIT / 'aggregate_g8_v3.py'),
  'reaudit_sha256':sha(REPORT),
  'population_sha256':sha(BASE / 'stage_b/cases.json'),
  'aggregate_certificate_sha256':sha(AUDIT / 'aggregate_relaxation_v1/certificates.json'),
  'aggregate_source_sha256':sha(AUDIT / 'aggregate_relaxation_v1/certify_relaxation.py'),
  'aggregate_freeze_sha256':sha(AUDIT / 'aggregate_relaxation_v1/freeze_manifest.json'),
  'checker_freeze_sha256':sha(AUDIT / 'v2/instrumentation_freeze.json'),
  'transition_manifest_sha256':sha(BASE / 'evaluation_v2/transition_manifest.json'),
  'trace_hashes':trace_hashes,
  'trace_report_hashes':trace_report_hashes,
  'reference_hashes':ref_hashes,
  'status_counts':dict(checked),
  'limitations':[
    'The 20 aggregate LP duals are replayed by aggregate_g8_v3.py, including regenerated graph and relaxation certificates; this script independently checks their event and inequality binding.',
    'For 52 final streamed REF reports, the raw v2 regime streams are absent from the recovered tree, so their fully_replayed report fields cannot be independently rechecked from raw regime bytes here.',
    'The original frozen REF records likewise have raw_certificate_replay=false in the auditor.',
    'No exact inherited-mask node optimum or complete exact node emptiness classification is established.'
  ]
}
out=HERE/'b_node_evidence_review_20261011.json'
out.write_text(json.dumps(output,indent=2,sort_keys=True)+'\n')
print(json.dumps({'report':str(out),'sha256':sha(out),'counts':dict(checked),'traces':len(trace_hashes),'refs':len(ref_hashes)},sort_keys=True))
