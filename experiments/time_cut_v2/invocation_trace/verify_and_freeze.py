"""Independently certify complete pilot traces and freeze exact node queries.

No reference/production optimizer is imported or launched. Counts are a
conservative combinatorial inventory for the declared charge-only pilot.
"""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from validation.trace5 import verify_trace
from validation.family5.checker import require,wire_equal,digest,canonical as json_canonical


def save(path,value):path.write_text(json.dumps(value,sort_keys=True,indent=2)+'\n')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def regime_inventory(queries):
    rows=[]
    for q in queries:
        case=q['trusted_case']
        require(case['schedule'] is None and len(case['charging_segments'])==1,'count formula requires one-segment charge-only pilot')
        require(all(effects==['C'] for effects in case['sites'].values()),'count formula requires genuine C-only Sites')
        width=sum(site!=case['destination'] for site in case['sites'])
        remaining=q['H_remaining'];first=len(q['actions']);pieces=len(q['cuts'])
        require(type(remaining) is int and remaining>=1,'invalid query suffix depth')
        # Mandatory first Region/action choice; all later Sites, including repeats.
        # One affine charge regime per suffix action because the curve has one segment.
        words=first*sum(width**extra for extra in range(remaining))
        rows.append(dict(query_seq=q['query_seq'],prefix_piece_count=pieces,H_remaining=remaining,
                         mandatory_first_actions=first,explicit_suffix_words=words,
                         affine_regime_upper_bound=pieces*words,
                         independently_graph_excluded=q['classification']=='unreachable',
                         numerical_status='not_started'))
    return rows


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--runs',default='runs_initial');p.add_argument('--verify-only',action='store_true');a=p.parse_args()
    case_path=a.root/'pilot_case.json';case=json.loads(case_path.read_text());freeze=json.loads((a.root/'PILOT_FREEZE.json').read_text())
    require(sha(case_path)==freeze['case_sha256'],'frozen pilot case hash mismatch')
    out=a.root/'certified_queries';out.mkdir(exist_ok=True)
    reports=[];all_inventory=[]
    for mode in ('D0','D1'):
        source=a.root/a.runs/(mode+'.json');payload=json.loads(source.read_text())
        require(wire_equal(payload['case'],case),'trace has foreign case')
        require(payload['source_case_sha256']==freeze['case_sha256'],'source case byte hash mismatch')
        checked=verify_trace(payload['trace'],payload['bundle'],case)
        canonical=json.loads(json_canonical(checked.summary['canonical']))['result']
        expected=freeze['expected']
        require(wire_equal({k:canonical[k] for k in expected},expected),'predeclared pilot key mismatch')
        queries=checked.export_queries();inventory=regime_inventory(queries)
        path=out/(mode+'.exact_queries.json')
        if a.verify_only:require(wire_equal(json.loads(path.read_text()),queries),'exact query freeze differs')
        else:save(path,queries)
        row=dict(mode=mode,source_sha256=sha(source),query_file_sha256=sha(path),
                 query_population_sha256=digest(queries),trace_check=json.loads(json_canonical(checked.summary)),
                 regime_inventory=inventory,numerical_suffix_optimization_run=False)
        if not a.verify_only:save(out/(mode+'.report.json'),row)
        reports.append(row);all_inventory.extend(inventory)
        print(json.dumps(dict(mode=mode,events=checked.summary['events'],invocations=checked.summary['invocations'],
                              exact_queries=len(queries),empty_action_queries=checked.summary['empty_action_queries'],
                              affine_regime_upper_bound=sum(x['affine_regime_upper_bound'] for x in inventory))),flush=True)
    manifest=dict(schema='family5-exact-query-preregistration-v1',pilot_freeze_sha256=sha(a.root/'PILOT_FREEZE.json'),
                  source_case_sha256=sha(case_path),modes=[{k:r[k] for k in ('mode','source_sha256','query_file_sha256','query_population_sha256')} for r in reports],
                  exact_node_queries=len(all_inventory),graph_excluded_node_queries=sum(x['independently_graph_excluded'] for x in all_inventory),
                  affine_regime_upper_bound_before_exclusions=sum(x['affine_regime_upper_bound'] for x in all_inventory),
                  numerical_suffix_optimization_run=False,literal_G8_closed=False)
    target=out/'QUERY_FREEZE.json'
    if a.verify_only:require(wire_equal(json.loads(target.read_text()),manifest),'query manifest differs')
    else:save(target,manifest)

if __name__=='__main__':main()
