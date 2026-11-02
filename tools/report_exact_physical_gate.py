"""Join frozen eight-cell receipts without solving or constructing a model."""
import argparse
from decimal import Decimal,ROUND_CEILING
import hashlib
import json
from pathlib import Path

IDS=('empty_prefix_terminal','alias_positive_charge','repeated_C_S_C','CS_overlap',
     'directed_unreachable','equality_attained','primary_unattained','secondary_unattained')
def load(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def report(root):
    root=Path(root);ready=load(root/'admission.json');budget=load(root/'budget.json')
    if budget.get('active'):raise ValueError('uncertain active worker')
    if (ready.get('state')!='prepared' or ready.get('case_denominator')!=8 or ready.get('case_ids')!=list(IDS) or
        [r.get('case') for r in ready.get('cells',[])]!=list(IDS)):
        raise ValueError('frozen eight-cell coverage')
    records=budget['records'];labels=[r['label'] for r in records]
    if len(set(labels))!=len(labels):raise ValueError('duplicate command history label')
    folder=root/'cases'
    if folder.exists() and any(p.is_dir() and p.name not in IDS for p in folder.iterdir()):raise ValueError('unexpected cell directory')
    if any(r['label'].startswith('gate_') and r.get('pid') is not None and
           not any(r['label'].startswith('gate_'+name) for name in IDS) for r in records):
        raise ValueError('unexpected numerical cell history')
    rows=[]
    for expected in ready['cells']:
        name=expected['case'];path=folder/name;receipt=path/'receipt.json'
        row=dict(case=name,status='unrun',prepared=expected)
        attempts=[r for r in records if r['label'].startswith('gate_'+name) and r.get('pid') is not None]
        row['numerical_worker_attempts']=len(attempts)
        if receipt.exists():
            worker=load(receipt);row.update(worker)
            if (worker.get('source')!=ready['source'] or worker.get('config_sha256')!=ready['config_sha256'] or
                worker.get('case')!=name or worker.get('derived_depth')!=expected['derived_depth']):row['status']='invalid_identity_or_depth'
            if len(attempts)!=1 or attempts[0]['returncode']!=0 or attempts[0].get('guard_reason'):row['status']='not_accepted_by_supervisor'
            if sha(path/'tiny-table.json')!=expected['table_sha256']:row['status']='input_drift'
            if hashlib.sha256(json.dumps(load(path/'input.json'),sort_keys=True,separators=(',',':')).encode()).hexdigest()!=expected['fixture_sha256']:
                row['status']='physical_input_drift'
            fixture=load(path/'input.json');semantic_keys=('status','key','primary_infimum','primary_value','secondary_infimum')
            actual={k:worker.get('result',{}).get(k) for k in semantic_keys if k in worker.get('result',{})}
            if (worker.get('expected')!=fixture.get('expected') or worker.get('actual')!=actual or
                worker.get('actual')!=worker.get('expected') or worker.get('production_optimizer_called') is not False or
                worker.get('real_road_generation') is not False or worker.get('real_scale_solve') is not False or worker.get('holdout') is not False):
                row['status']='scope_or_semantic_mismatch'
            checks=load(path/'SMT'/'checks.json')
            files=list((path/'SMT').glob('*.smt2'))
            if len(checks)!=len(files) or any(r.get('status')!='completed' or r.get('result') not in ('sat','unsat') for r in checks):
                row['status']='incomplete_SMT_audit'
            for i,check in enumerate(checks,1):
                file=path/'SMT'/f"{i:04}-{check['kind']}.smt2"
                if (not file.exists() or hashlib.sha256(file.read_bytes().removesuffix(b'\n(check-sat)\n')).hexdigest()!=check['sha256']):
                    row['status']='SMT_artifact_drift'
            row.update(raw_receipt_sha256=sha(receipt),SMT_check_count=len(checks),
                SMT_artifact_files=len(files),SMT_checks_sha256=sha(path/'SMT'/'checks.json'))
            if attempts:
                command=attempts[0];row.update(supervised_CPU_s=command['charged_CPU_s'],
                    sampled_process_group_peak_RSS_bytes=command['sampled_process_group_peak_rss_bytes'],
                    host_available_min_bytes=command['host_available_min_bytes'])
        elif attempts or (path/'started.json').exists():row['status']='started_without_terminal_receipt'
        rows.append(row)
    micro=Decimal('.000001')
    metered=max(Decimal(str(budget['charged_commands_CPU_s'])).quantize(micro,rounding=ROUND_CEILING),
        sum((Decimal(str(r.get('charged_CPU_s',0))).quantize(micro,rounding=ROUND_CEILING) for r in records),Decimal(0)))
    fee=metered+Decimal(300)
    original=Decimal(budget['carried_research_CPU_s'])+fee
    required=('admission_semantics_normal','admission_semantics_optimized','frozen_tiny_preparation',
              'final_report_semantics_normal','final_report_semantics_optimized',
              'terminal_status_regressions_normal','terminal_status_regressions_optimized')
    tested=all(any(r['label']==name and r['returncode']==0 and not r.get('guard_reason') for r in records) for name in required)
    passed=all(r['status']=='verified' for r in rows) and tested and fee<=900 and original<=28800
    commands=[]
    for r in records:
        row={k:r.get(k) for k in ('label','pid','returncode','guard_reason','charged_CPU_s','controller_sha256','error')}
        log=root/(r['label']+'.log');row['log_sha256']=sha(log) if log.exists() else None;commands.append(row)
    return dict(schema='hiroute.exact_physical_results.v1',gate_status='PASS_TINY_CONDITIONAL_MODEL' if passed else 'LIMITED_OR_FAILED',
        scope='Eight synthetic analytic fixtures, conditional exact supplied-table model; no real-scale or holdout claim',
        case_denominator=8,rows=rows,gate_source=ready['source'],admission_sha256=sha(root/'admission.json'),
        final_tests_per_mode=15,normal_and_optimized_passed=tested,
        gate_SMT_checks=sum(r.get('SMT_check_count',0) for r in rows),
        focused_unit_SMT_calls='Additional actual tiny SMT calls in focused regression processes; per-call count not instrumented there; complete process CPU charged',
        old_optimization_cohorts_repeated=False,production_optimizer_oracle=False,
        real_road_generation=False,real_scale_solve=False,holdout=False,original_taskbook_complete=False,
        separate_seed_replay_count=sum(bool(r.get('separate_seed_replay')) for r in rows),
        separate_final_replay_count=sum(bool(r.get('separate_final_replay')) for r in rows),
        controller_correction=budget.get('controller_correction'),commands=commands,
        accounting=dict(stage_cap_CPU_s=900,fixed_precharge_CPU_s=300,metered_commands_CPU_s=str(fee-300),
            stage_conservative_CPU_s=str(fee),carried_original_research_CPU_s=budget['carried_research_CPU_s'],
            original_conservative_CPU_s=str(original),original_cap_CPU_s=28800,
            original_remaining_CPU_s=str(Decimal(28800)-original),preprocessing_CPU_s='652.040677976',preprocessing_cap_CPU_s=900,
            software_CI='Separate prospective reservations; all previous research and CI charges retained'))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    r=report(a.root)
    with Path(a.output).open('x') as stream:json.dump(r,stream,indent=2,sort_keys=True);stream.write('\n')
    print(json.dumps(dict(status=r['gate_status'],SMT_checks=r['gate_SMT_checks'],accounting=r['accounting'],
        rows=[dict(case=x['case'],status=x['status'],actual=x.get('actual'),checks=x.get('SMT_check_count')) for x in r['rows']]),indent=2))
    raise SystemExit(0 if r['gate_status']=='PASS_TINY_CONDITIONAL_MODEL' else 1)
