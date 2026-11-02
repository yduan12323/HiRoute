"""Read-only complete15-row gate/receipt join; no routing or certificate generation."""
import argparse
from collections import Counter
from decimal import Decimal,ROUND_CEILING
import hashlib
import json
from pathlib import Path

from road_certificate_fixtures import IDS


def load(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def expected(name):
    if name.startswith('zero_time_'):return 'unsupported'
    return 'verified' if name.startswith('valid_') or name in ('string_node_tuple','deep_tuple_ties') else 'rejected'


def report(root):
    root=Path(root);budget=load(root/'budget.json');r=load(root/'gate'/'results.json')
    if budget.get('active'):raise ValueError('uncertain active command')
    if r.get('case_denominator')!=15 or [row.get('case') for row in r.get('rows',[])]!=list(IDS):
        raise ValueError('frozen15-cell actual coverage mismatch')
    if any(r.get(k) is not False for k in ('real_table_generation','real_scale_optimization','holdout','production_oracle')):
        raise ValueError('scope mismatch')
    if r.get('source',{}).get('dirty') is not False or r.get('source_consistency_error'):raise ValueError('within-run source mismatch')
    labels=[v['label'] for v in budget['records']]
    if len(set(labels))!=len(labels):raise ValueError('duplicate command history label')
    commands={v['label']:v for v in budget['records']}
    if any(name.startswith('frozen_certificate_gate') and name!='frozen_certificate_gate' for name in labels):
        raise ValueError('unexpected formal gate history')
    if any(p.is_dir() and p.name not in IDS for p in (root/'gate').iterdir()):
        raise ValueError('unexpected gate case directory')
    required=('saved_input_checker_normal','saved_input_checker_optimized','final_receipt_normal','final_receipt_optimized','frozen_certificate_gate')
    tested=all(name in commands and commands[name]['returncode']==0 and not commands[name].get('guard_reason') for name in required)
    tested=tested and commands.get('frozen_certificate_gate',{}).get('pid') is not None
    rows=[]
    for row in r['rows']:
        row=dict(row);name=row['case'];folder=root/'gate'/name;hashes=row.get('input_sha256',{})
        if row.get('status')!='verified':
            rows.append(row);continue
        if row.get('expected')!=expected(name) or row.get('actual',{}).get('status')!=expected(name):row['status']='decision_mismatch'
        if not hashes or 'graph.json' not in hashes:row['status']='missing_input_manifest'
        else:
            if set(hashes)!={p.name for p in folder.iterdir() if p.is_file()}:row['status']='input_file_coverage_drift'
            for file,digest in hashes.items():
                path=folder/file
                if not path.exists() or sha(path)!=digest:row['status']='input_hash_drift'
        actual=row.get('actual',{})
        if actual.get('status')=='verified':
            table=load(folder/'table.json');aliases={s:v['anchor'] for s,v in table['sites'].items()}
            S=sorted({table['origin_anchor'],*aliases.values()});T=sorted({table['destination_anchor'],*aliases.values()})
            pairs={(p['source'],p['target']) for p in table['pairs']}
            sources=actual.get('source_receipts',[])
            if (pairs!={(s,t) for s in S for t in T} or len(table['pairs'])!=len(S)*len(T) or
                actual.get('checked_pairs')!=len(pairs) or actual.get('literal_sites')!=len(table['candidate_order']) or
                actual.get('physical_sources')!=len(S) or actual.get('physical_targets')!=len(T) or
                [v['source'] for v in sources]!=S or actual.get('owns_exact_inputs') is not True or
                actual.get('graph_sha256')!=hashes.get('graph.json') or actual.get('table_sha256')!=hashes.get('table.json')):
                row['status']='whole_table_coverage_or_identity_drift'
            filenames=[f'source-{i:04}.json' for i in range(len(S))]
            if sorted(k for k in hashes if k.startswith('source-'))!=filenames:row['status']='source_file_coverage_drift'
            for i,value in enumerate(sources):
                if value.get('checked_pairs')!=len(T) or value.get('certificate_sha256')!=hashes.get(f'source-{i:04}.json'):
                    row['status']='source_receipt_drift'
        rows.append(row)
    micro=Decimal('.000001')
    metered=max(Decimal(str(budget['charged_commands_CPU_s'])).quantize(micro,rounding=ROUND_CEILING),
        sum((Decimal(str(x.get('charged_CPU_s',0))).quantize(micro,rounding=ROUND_CEILING) for x in budget['records']),Decimal(0)))
    fee=metered+Decimal(220);original=Decimal(budget['carried_research_CPU_s'])+fee
    passed=tested and fee<=600 and original<=28800 and all(row.get('status')=='verified' for row in rows)
    counts=Counter(row.get('actual',{}).get('status','unrun') for row in rows)
    return dict(schema='hiroute.road_certificate_delivery.v1',gate_status='PASS_TINY_CERTIFICATE_CHECKER' if passed else 'LIMITED_OR_FAILED',
        scope='15 fixed synthetic certificate decisions, not real input certification or EV optimization',
        source=r['source'],config_sha256=r['config_sha256'],case_denominator=15,rows=rows,decision_counts=dict(counts),
        accepted_case_pair_checks=sum(v.get('actual',{}).get('checked_pairs',0) for v in rows),
        accepted_case_source_certificates=sum(v.get('actual',{}).get('physical_sources',0) for v in rows),
        original_worker_receipt_sha256=sha(root/'gate'/'results.json'),
        tests_per_mode=16,normal_and_optimized_passed=tested,real_table_generation=False,real_scale_optimization=False,holdout=False,
        original_taskbook_complete=False,
        commands=[{**{k:v.get(k) for k in ('label','pid','returncode','guard_reason','charged_CPU_s','controller_sha256')},
                   'log_sha256':sha(root/(v['label']+'.log')) if (root/(v['label']+'.log')).exists() else None} for v in budget['records']],
        accounting=dict(stage_cap_CPU_s=600,fixed_precharge_CPU_s=220,metered_CPU_s=str(metered),stage_CPU_s=str(fee),
            carried_original_CPU_s=budget['carried_research_CPU_s'],original_CPU_s=str(original),original_cap_CPU_s=28800,
            original_remaining_CPU_s=str(Decimal(28800)-original),preprocessing_CPU_s='652.040677976',preprocessing_cap_CPU_s=900,
            software_CI='Separately prospectively reserved; previous charges retained'))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    result=report(a.root)
    with Path(a.output).open('x') as stream:json.dump(result,stream,indent=2,sort_keys=True);stream.write('\n')
    print(json.dumps(dict(status=result['gate_status'],decisions=result['decision_counts'],accounting=result['accounting']),indent=2))
    raise SystemExit(0 if result['gate_status']=='PASS_TINY_CERTIFICATE_CHECKER' else 1)
