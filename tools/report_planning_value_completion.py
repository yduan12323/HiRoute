"""Post-terminal join preserving six historical policy rows and two new rows."""
import argparse
from collections import Counter
import copy
from pathlib import Path

import report_planning_value_dev as prior_report
import run_planning_value_completion as completion

stage = completion.stage
ROOT = stage.ROOT


def validate_previous(previous,original,raw_rows):
    rows=previous['rows'];full=original['definition']['rows']
    def identity(r):return tuple(r[k] for k in ('query_id','initial_energy_kwh','scenario','N','policy'))
    if (previous['query_denominator']!=4 or previous['policy_row_denominator']!=8 or
            len(rows)!=8 or [identity(r) for r in rows]!=[identity(r) for r in full] or
            previous['numerical_source']!=original['source']):
        raise ValueError('historical policy frame/source mismatch')
    fields=('query_id','initial_energy_kwh','scenario','N','policy','status','key',
            'feasible_key','witness','policy_info','query_loaded_total_s')
    if len(raw_rows)!=8 or any(a.get(k)!=b.get(k) for a,b in zip(rows[:6],raw_rows[:6]) for k in fields):
        raise ValueError('historical summary differs from raw policy receipts')
    if any(a['original_candidate_domain_sha256']!=b['original_candidate_domain_sha256']
           for a,b in zip(rows,full)):
        raise ValueError('historical policy domain mismatch')


def combine_rows(previous, fresh, previous_source):
    if len(previous)!=8 or len(fresh)!=2:
        raise ValueError('completion denominator changed')
    if ([stage.row_id(r) for r in fresh] != [stage.row_id(r) for r in previous[-2:]] or
            any(r['status']!='budget_unrun' for r in previous[-2:])):
        raise ValueError('only the historical budget-unrun suffix may be completed')
    preserved = copy.deepcopy(previous[:6])
    for row in preserved:
        row['numerical_source'] = copy.deepcopy(previous_source)
    return preserved+copy.deepcopy(fresh)


def terminal_evidence(row,root):
    directory=root/'attempts'/stage.row_id(row)
    if row['status']=='budget_unrun':
        if directory.exists():
            raise ValueError('unrun slot has a possible prior start')
        return {}
    stage.validate_policy_row(row)
    receipt=directory/'final.json'
    if stage.load(receipt)!=row:
        raise ValueError('new terminal receipt mismatch')
    evidence=dict(terminal_receipt_sha256=stage.digest(receipt))
    checkpoints=list(directory.rglob('*.incumbent.json'))
    if row.get('feasible_key') is not None:
        if len(checkpoints)!=1 or prior_report.key(stage.load(checkpoints[0])['key']) != prior_report.key(row['feasible_key']):
            raise ValueError('new actual witness checkpoint missing/mismatched')
        evidence['raw_witness_checkpoint_sha256']=stage.digest(checkpoints[0])
    elif checkpoints:
        raise ValueError('unreported new feasible checkpoint')
    return evidence


def fresh_summary(row,prepared,reference,evidence):
    cfg = stage.load(prepared['configs']['48|'+row['policy']]['config'])
    if (reference['candidate_domain_sha256'] != row['original_candidate_domain_sha256'] or
            reference['implementation'] != cfg['implementation']):
        raise ValueError('joint domain/profile mismatch')
    if row.get('direct_selected_time_s') is not None and any(row[k]!=reference[k]
            for k in ('direct_selected_time_s','direct_selected_length_m')):
        raise ValueError('joint direct selected-leg mismatch')
    fields = ('query_id','initial_energy_kwh','scenario','N','policy','status',
        'mathematical_status','key','feasible_key','primary_infimum','secondary_infimum',
        'witness','policy_info','query_loaded_total_s','cold_index_wall_s','worker_cpu_s',
        'supervisor_cpu_s','stage_worker_charged_cpu_s','process_group_peak_rss_bytes',
        'query_extra_peak_bytes','host_available_min_bytes','depth_contract','seed_key')
    result = {k:row.get(k) for k in fields}
    result.update(policy_outcome=prior_report.policy_status(row),
        numerical_source=prepared['source'],
        original_candidate_domain_sha256=row['original_candidate_domain_sha256'],
        joint_reference={k:reference.get(k) for k in ('status','mathematical_status','key',
            'feasible_key','witness','raw_checkpoint_sha256','candidate_domain_sha256','numerical_source')},
        comparison=prior_report.compare(row,reference))
    result.update(evidence)
    return result


def report(input_root,historical_stage,output_root):
    root=Path(input_root)
    status=stage.load(root/'status.json')
    if status['state'] not in ('complete','budget_stopped'):
        raise RuntimeError('no historical controls before terminal completion receipts')
    prepared=stage.load(root/'preparation.json')
    spec=prepared['spec']
    original,prior=completion.predecessor(prepared['predecessor']['root'],spec)
    if prior!=prepared['predecessor']:
        raise ValueError('predecessor changed since preflight')
    rows=stage.load(root/'results.json')['rows']
    if len(rows)!=2 or [stage.row_id(r) for r in rows]!=[stage.row_id(r) for r in prepared['definition']['rows']]:
        raise ValueError('completion pair/order changed')
    evidence={stage.row_id(r):terminal_evidence(r,root) for r in rows}
    # No joint or published policy-control content is read before the new
    # terminal status above. Workers never receive either report or any key.
    summary_path=ROOT/'docs/planning_value_dev_results.json'
    if stage.digest(summary_path)!=spec['prior_summary_sha256']:
        raise ValueError('published predecessor summary changed')
    previous=stage.load(summary_path)
    validate_previous(previous,original,stage.load(Path(prior['root'])/'results.json')['rows'])
    full=original['definition']
    join=full['joint_report_join_only']
    path=ROOT/join['file']
    if stage.digest(path)!=join['sha256']:
        raise ValueError('historical joint input changed')
    joint=stage.load(path)
    if joint['preparation']['input_sha256']!=prepared['input_sha256']:
        raise ValueError('historical graph/catalog/bindings mismatch')
    controls=[r for r in joint['rows'] if r['method']==join['method'] and
        (r['query_id'],r['initial_energy_kwh'],r['scenario'],r['N'])==('WD07','48','schedule',64)]
    if len(controls)!=1:
        raise ValueError('missing/duplicate WD07 historical control')
    reference=prior_report.historical_metrics(controls[0],prepared,full,historical_stage)
    fresh=[fresh_summary(r,prepared,reference,evidence[stage.row_id(r)]) for r in rows]
    combined=combine_rows(previous['rows'],fresh,previous['numerical_source'])
    final_stage=status['worker_cpu_charged_s']+stage.common.closed_controller_cost(status)
    inclusive=spec['nonstage_precharge_cpu_s']+final_stage
    total=spec['carried_cpu_s']+inclusive
    if final_stage>spec['stage_cap_cpu_s'] or inclusive>spec['gate_cap_cpu_s'] or total>spec['original_cap_cpu_s']:
        raise ValueError('completion inclusive research budget exceeded')
    errors=[stage.row_id(r) for r in combined if r['comparison']['comparison_type']=='verification_error']
    result=dict(schema='hiroute.planning_value_completion_results.v1',
        scope='Four existing selected DEV cells completed prospectively; not main experiment or holdout',
        query_denominator=4,policy_row_denominator=8,fresh_policy_slots=2,
        attempted_fresh_policy_rows=sum(r['status']!='budget_unrun' for r in rows),reused_policy_rows=6,
        predecessor_summary_sha256=spec['prior_summary_sha256'],
        predecessor_budget_unrun_records=copy.deepcopy(previous['rows'][-2:]),
        predecessor=prior,completion_numerical_source=prepared['source'],
        reporting_source=stage.common.source_identity(),
        input_sha256=prepared['input_sha256'],historical_joint_report_sha256=join['sha256'],
        joint_controls_read_after_terminal_stage=True,
        started_slots_have_terminal_receipts_and_unrun_slots_have_no_start=True,new_joint_solves=0,
        historical_timings_not_speedup_controls=True,holdout=False,main_experiment=False,
        policy_summary={p:dict(Counter(r['policy_outcome'] for r in combined if r['policy']==p))
                        for p in full['policies']},
        accounting=dict(carried_conservative_CPU_s=spec['carried_cpu_s'],
            nonstage_precharged_CPU_s=spec['nonstage_precharge_cpu_s'],
            new_stage_final_conservative_CPU_s=final_stage,new_gate_conservative_CPU_s=inclusive,
            new_gate_cap_CPU_s=spec['gate_cap_cpu_s'],original_conservative_total_CPU_s=total,
            original_cap_CPU_s=spec['original_cap_cpu_s'],raw_terminal_status=status,
            preprocessing_CPU_s=652.040677976,ordinary_software_CI='separate prospective records; old CI reservations not refunded'),
        counterexamples=errors,rows=combined)
    out=Path(output_root);out.mkdir(parents=True,exist_ok=True)
    stage.pilot.atomic(out/'planning_value_completion_results.json',result)
    print(dict(policy_summary=result['policy_summary'],accounting=result['accounting'],counterexamples=errors))
    return not errors


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-root',required=True)
    parser.add_argument('--historical-stage',required=True)
    parser.add_argument('--output-root',required=True)
    args=parser.parse_args()
    raise SystemExit(0 if report(args.input_root,args.historical_stage,args.output_root) else 1)
