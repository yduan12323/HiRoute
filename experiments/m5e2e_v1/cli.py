"""Explicit DEV stage entrypoint; no implicit expansion, retries or holdout."""
import argparse
import json
from pathlib import Path
import sys
from .common import load, write_new, file_hash, source_identity, environment_admission, installation_identity

STAGES = ('preflight', 'prepare', 'freeze', 'solve', 'verify', 'summarize')


def plan():
    return dict(schema='hiroute.m5e2e.plan.v1', stages=list(STAGES),
        case_ids=['E01','E02','E03'], max_candidates=4, H_ref=3,
        domain='real_map_microdomain_v1', exposure='DEV_E2E',
        methods=['REF','FLAT','HIER'], clean_builds=['A','B'],
        original_bridge='separate explicit binding; at most one unchanged N8 case',
        merge=False, holdout=False, automatic_retries=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage', choices=STAGES)
    p.add_argument('--plan', action='store_true')
    p.add_argument('--source', required=True, type=Path)
    p.add_argument('--config', required=True, type=Path)
    p.add_argument('--raw-cache', required=True, type=Path)
    p.add_argument('--run-root', required=True, type=Path)
    p.add_argument('--budget-root', required=True, type=Path)
    p.add_argument('--osmium', type=Path)
    p.add_argument('--compiler', type=Path)
    p.add_argument('--compare-run', type=Path)
    args = p.parse_args()
    if args.plan:
        print(json.dumps(plan(), indent=2)); return 0
    source = source_identity(args.source)
    config = load(args.config)
    root = args.run_root.resolve()
    if root.is_relative_to(args.source.resolve()):
        raise ValueError('Generated outputs must be outside source checkout')
    if args.stage == 'preflight':
        root.mkdir(parents=True, exist_ok=False)
        environment = environment_admission()
        from .prepare import preflight
        inputs = preflight(config, args.raw_cache)
        try:
            installation=installation_identity(source)
        except (OSError,ValueError,ImportError) as exc:
            installation=dict(error=str(exc))
        ready = 'error' not in installation and environment['status']=='READY' and inputs.get('status') in ('READY','NEEDS_ACQUISITION') and not source['dirty']
        receipt = dict(schema='hiroute.m5e2e.preflight.v1',
            status='READY' if ready else 'BLOCKED_INPUT_OR_ENVIRONMENT',
            source=source, installation=installation, config_sha256=file_hash(args.config), environment=environment,
            inputs=inputs, planned=plan(), numerical_workers_started=0)
        write_new(root/'preflight.json', receipt)
        print(json.dumps(receipt, indent=2)); return 0 if ready else 2
    preflight_receipt = load(root/'preflight.json')
    if (preflight_receipt['config_sha256']!=file_hash(args.config) or
            preflight_receipt['source']['commit']!=source['commit'] or source['dirty']):
        raise ValueError('Source/config changed after preflight')
    if args.stage == 'summarize':
        return summarize(root, args.compare_run)
    if preflight_receipt['status'] != 'READY':
        raise RuntimeError('NOT_RUN_DEPENDENCY: preflight was not admitted')
    if installation_identity(source)!=preflight_receipt['installation']:
        raise ValueError('Installed source/dependencies changed after preflight')
    if environment_admission()['status'] != 'READY':
        raise RuntimeError('BLOCKED_INPUT_OR_ENVIRONMENT: current environment unsafe')
    if args.stage in ('prepare','freeze'):
        from .budget import execute
        cpu, wall = ((7200,5400) if args.stage=='prepare' else (600,600))
        if args.stage=='freeze':
            previous=load(root/'prepare-invocation/receipt.json')
            cpu=min(cpu,7200-previous['accounted_owned_cpu_seconds'])
            wall=min(wall,5400-previous['wall_seconds'])
            if min(cpu,wall)<=0:raise RuntimeError('Preprocessing and freeze combined allowance exhausted')
        command=[sys.executable,'-m','experiments.m5e2e_v1.pipeline_worker',args.stage,
                 '--source',str(args.source.resolve()),'--config',str(args.config.resolve()),
                 '--raw-cache',str(args.raw_cache.resolve()),'--run-root',str(root)]
        if args.osmium: command += ['--osmium',str(args.osmium.resolve())]
        if args.compiler: command += ['--compiler',str(args.compiler.resolve())]
        receipt=execute(command,budget_root=args.budget_root,output_dir=root/(args.stage+'-invocation'),
            phase=args.stage,cpu_seconds=cpu,wall_seconds=wall,
            memory_bytes=min(config['resources'].get('preprocess_memory_bytes', 5*1024**3),38*1024**3),
            preprocessing=True)
        return 0 if receipt['status']=='SUCCESS' else 2
    if args.stage == 'solve':
        return solve(root,args.budget_root)
    if args.stage == 'verify':
        return verify(root,args.budget_root)


def cases(root):
    return load(root/'freeze-invocation/artifacts/cases.json')['cases']


def solve(root,budget):
    from .budget import execute
    rows=[]
    for case in cases(root):
        for method in ('REF','FLAT','HIER'):
            row=dict(case_id=case['case_id'],method=method)
            if case['status']!='READY':
                row.update(operation_status='NOT_RUN_DEPENDENCY',reason=case.get('reason',case['status']))
            else:
                directory=root/'methods'/case['case_id']/method
                receipt=execute([sys.executable,'-m','experiments.m5e2e_v1.worker',
                    '--case',case['case_path'],'--method',method],budget_root=budget,
                    output_dir=directory,phase=case['case_id']+'/'+method)
                row.update(operation_status=receipt['status'],supervisor=str(directory/'receipt.json'))
                if receipt['status']=='SUCCESS':
                    row['result_path']=str(directory/'artifacts/result.json')
            rows.append(row)
    write_new(root/'method_slots.json',dict(slots=rows))
    return 0


def verify(root,budget):
    from .budget import execute
    from .solve import compare_receipts
    slots=load(root/'method_slots.json')['slots']; results=[]
    for case in cases(root):
        rows=[r for r in slots if r['case_id']==case['case_id']]
        result=dict(case_id=case['case_id'],status='NOT_RUN_DEPENDENCY')
        if len(rows)==3 and all(r.get('result_path') for r in rows):
            receipts=[load(r['result_path']) for r in rows]
            result.update(compare_receipts(receipts))
            ref=next(r for r in receipts if r['method']=='REF')
            if ref.get('ref_completed'):
                directory=root/'checks'/case['case_id']
                check=execute([sys.executable,'-m','experiments.m5e2e_v1.worker','--case',case['case_path'],
                    '--method','CHECK','--ref-evidence',ref['reference_evidence_path']],
                    budget_root=budget,output_dir=directory,phase=case['case_id']+'/cold_check')
                result['cold_check_verified']=check['status']=='SUCCESS'
        if case['status']=='READY':
            directory=root/'road-checks'/case['case_id']
            road=execute([sys.executable,'-m','experiments.m5e2e_v1.worker','--case',case['case_path'],
                '--method','ROAD_CHECK','--prepared',str(root/'prepare-invocation/artifacts/prepared.json')],
                budget_root=budget,output_dir=directory,phase=case['case_id']+'/graph_replay')
            result['road_check_verified']=road['status']=='SUCCESS'
        results.append(result)
    write_new(root/'comparisons.json',dict(cases=results))
    return 0


def summarize(root,other):
    preflight=load(root/'preflight.json')
    # Gates not established are never inferred from absent artifacts.
    result=dict(delivery_status='PARTIAL',clean_e2e_status='BLOCKED' if preflight['status']!='READY' else 'PARTIAL',
        original_shandong_ref_status='UNKNOWN',
        original_bridge_execution='NOT_RUN_ENVIRONMENT',
        original_bridge_reason='Memory safety admission failed; no bridge attempted. Current original artifact binding not independently revalidated.',
        historical_m5d_disposition='M5D_LIMITED_BY_DATA_OR_SCALE',historical_accounting_repaired=False,
        full_shandong_batch_confirmed=False,final_holdout_completed=False,project_completed=False,
        reproduction_scope='NOT_RUN',gates={g:'NOT_ESTABLISHED' for g in ('E0','E1','E2','E3','E4','E5','E6','E7')})
    result['gates']['E0']=preflight['status']
    if (root/'comparisons.json').exists():
        result['comparisons']=load(root/'comparisons.json')
        rows=result['comparisons']['cases']
        result['gates']['E2']='PASS' if len(rows)==3 and all(r.get('reference_match') is True for r in rows) else 'PARTIAL'
        result['gates']['E3']='PASS' if any((r.get('actual_positive_charge_count') or 0)>=2 for r in rows if r.get('reference_match')) and any(r.get('schedule_covered') for r in rows if r.get('reference_match')) else 'COVERAGE_LIMITED'
        result['gates']['E5']='CHECKS_PASSED_ACCOUNTING_REVIEW_REQUIRED' if all(r.get('cold_check_verified') for r in rows) and any(r.get('road_check_verified') for r in rows) else 'ACCOUNTING_OR_EVIDENCE_INCOMPLETE'
    if other:
        from .reproduction import compare_builds
        result['reproduction']=compare_builds(root,other.resolve())
        result['gates']['E4']=result['reproduction']['status']
        result['reproduction_scope']=result['reproduction'].get('reproduction_scope','NOT_RUN')
    write_new(root/'acceptance.json',result)
    print(json.dumps(result,indent=2)); return 0


if __name__ == '__main__':
    raise SystemExit(main())
