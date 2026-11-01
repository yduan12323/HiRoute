"""Join historical joint values only after durable policy terminal receipts."""
import argparse
from collections import Counter
from fractions import Fraction as F
import json
from pathlib import Path
from types import SimpleNamespace

import run_planning_value_dev as stage
from planning_value_policy import verify_policy_witness
from real_scale_inputs import bind_snapshot
from run_real_scale_pilot import aliases, atomic

ROOT=Path(__file__).resolve().parents[1]


def key(value):
    return (F(value[0]),F(value[1]),value[2],tuple(tuple(p) for p in value[3]))


def cell(row):
    return row['query_id'],row['initial_energy_kwh'],row['scenario'],row['N']


def compare(policy_row,joint):
    actual=policy_row.get('feasible_key')
    reference=joint.get('feasible_key')
    result=dict(policy_mathematical_status=policy_row['status'],
                joint_mathematical_status=joint['status'],
                comparison_type='no_pair_of_verified_feasible_values')
    if actual is None or reference is None:return result
    if (policy_row.get('witness',{}).get('original_joint_model_verified') is not True or
            joint.get('witness',{}).get('physical_verified') is not True):
        raise ValueError('unverified feasible value')
    attained=joint['status']=='attained_optimum'
    if attained and key(actual)<key(joint['key']):
        result.update(comparison_type='verification_error',
                      error='restricted feasible full key beats an attained joint optimum')
        return result
    result.update(comparison_type='feasible_plan_gap_to_attained_joint_optimum' if attained else
                  'observed_feasible_plans_only_UNKNOWN_joint',
                  delta_J_s=F(actual[0])-F(reference[0]),
                  delta_charge_kwh=F(actual[1])-F(reference[1]),
                  delta_stops=actual[2]-reference[2])
    for metric in ('elapsed_time_s','driving_time_s','total_distance_m','positive_charge_count',
                   'charging_duration_s','charging_activity_overlap_s'):
        a,b=policy_row['witness'].get(metric),joint['witness'].get(metric)
        result['delta_'+metric]=None if a is None or b is None else F(a)-F(b)
    return result


def policy_status(row):
    status=row['status']
    if status=='attained_optimum':return 'attained_policy_optimum'
    if status=='infeasible':return 'policy_infeasible_proved'
    if status in ('primary_unattained','secondary_unattained'):return status+'_policy'
    if status=='time_limit':return 'time_limit_feasible_only' if row.get('feasible_key') else 'time_limit_no_feasible'
    return status


def historical_metrics(reference,prepared,definition,historical_stage):
    if reference.get('feasible_key') is None:return reference
    directory=Path(historical_stage)/'attempts'/stage.common.cell_id(reference)/'scale'
    candidates=[]
    for path in directory.rglob('*.incumbent.json'):
        record=stage.load(path)
        if key(record['key'])==key(reference['feasible_key']):candidates.append((path,record))
    if len(candidates)!=1:
        raise ValueError('historical feasible plan raw checkpoint unavailable/ambiguous')
    path,record=candidates[0]
    cfg=prepared['configs'][reference['initial_energy_kwh']+'|'+definition['policies'][0]]
    config,manifest=stage.load(cfg['config']),stage.load(cfg['preflight'])
    query=next(q for q in manifest['queries'] if q['query_id']==reference['query_id'])
    # Binding only needs the already observed exact direct time for the frozen
    # schedule recipe. This provider never searches a road or optimizes a plan.
    provider=SimpleNamespace(selected_leg=lambda *_:SimpleNamespace(time_s=F(reference['direct_selected_time_s'])))
    original=bind_snapshot(config,query,64,'schedule',provider)
    verified=verify_policy_witness(original,original,record,site_to_road=aliases(query,64,'schedule'),
                                  direct_length_m=reference['direct_selected_length_m'])
    verified.pop('policy_verified',None)
    verified['historical_original_model_replayed']=True
    reference={**reference,'witness':verified,'raw_checkpoint_sha256':stage.digest(path)}
    return reference


def report(input_root,historical_stage,output_root):
    root=Path(input_root);out=Path(output_root);out.mkdir(parents=True,exist_ok=True)
    status=stage.load(root/'status.json');prepared=stage.load(root/'preparation.json')
    if status['state'] not in ('complete','budget_stopped'):
        raise RuntimeError('no historical controls before terminal policy stage')
    rows=stage.load(root/'results.json')['rows'];definition=prepared['definition']
    if len(rows)!=8 or [stage.row_id(r) for r in rows]!=[stage.row_id(r) for r in definition['rows']]:
        raise ValueError('policy denominator/order changed')
    for row in rows:
        if row['status']=='budget_unrun':continue
        stage.validate_policy_row(row)
        receipt=root/'attempts'/stage.row_id(row)/'final.json'
        if not receipt.is_file() or stage.load(receipt)!=row:
            raise ValueError('missing/mismatched durable policy terminal receipt')
    # This is the first read of joint-control contents in the execution flow.
    join=definition['joint_report_join_only'];path=ROOT/join['file']
    if stage.digest(path)!=join['sha256']:raise ValueError('frozen joint report changed')
    historical=stage.load(path)
    if historical['preparation']['input_sha256']!=prepared['input_sha256']:
        raise ValueError('historical graph/catalog/bindings mismatch')
    expected={cell(r) for r in rows}
    controls=[r for r in historical['rows'] if r['method']==join['method'] and cell(r) in expected]
    if len(controls)!=4 or {cell(r) for r in controls}!=expected:
        raise ValueError('historical joint controls unavailable/duplicated')
    controls={cell(r):historical_metrics(r,prepared,definition,historical_stage) for r in controls}
    result_rows=[]
    for row in rows:
        control=controls[cell(row)]
        cfg=stage.load(prepared['configs'][row['initial_energy_kwh']+'|'+row['policy']]['config'])
        if (control['candidate_domain_sha256']!=row['original_candidate_domain_sha256'] or
                control['implementation']!=cfg['implementation']):
            raise ValueError('historical domain/profile mismatch')
        if row.get('direct_selected_time_s') is not None and any(
                row[k]!=control[k] for k in ('direct_selected_time_s','direct_selected_length_m')):
            raise ValueError('historical selected direct leg mismatch')
        # Keep resource and mathematical statuses separate from actual values.
        summary={k:row.get(k) for k in ('query_id','initial_energy_kwh','scenario','N','policy','status',
            'mathematical_status','key','feasible_key','primary_infimum','secondary_infimum',
            'witness','policy_info','query_loaded_total_s','cold_index_wall_s','worker_cpu_s',
            'supervisor_cpu_s','stage_worker_charged_cpu_s','process_group_peak_rss_bytes',
            'query_extra_peak_bytes','host_available_min_bytes','depth_contract','seed_key')}
        summary.update(policy_outcome=policy_status(row),
            original_candidate_domain_sha256=row['original_candidate_domain_sha256'],
            joint_reference={k:control.get(k) for k in ('status','mathematical_status','key','feasible_key',
                'witness','raw_checkpoint_sha256','candidate_domain_sha256','numerical_source')},
            comparison=compare(row,control))
        if row['status']!='budget_unrun':
            directory=root/'attempts'/stage.row_id(row)
            summary['terminal_receipt_sha256']=stage.digest(directory/'final.json')
            checkpoints=list(directory.rglob('*.incumbent.json'))
            if row.get('feasible_key') is not None:
                if len(checkpoints)!=1 or key(stage.load(checkpoints[0])['key'])!=key(row['feasible_key']):
                    raise ValueError('missing/mismatched actual policy witness checkpoint')
                summary['raw_witness_checkpoint_sha256']=stage.digest(checkpoints[0])
            elif checkpoints:
                raise ValueError('unreported feasible checkpoint')
        result_rows.append(summary)
    final_stage=status['worker_cpu_charged_s']+stage.common.closed_controller_cost(status)
    spec=prepared['spec'];inclusive=spec['nonstage_precharge_cpu_s']+final_stage
    if final_stage>2100 or inclusive>3000 or spec['carried_cpu_s']+inclusive>28800:
        raise ValueError('inclusive final cap exceeded')
    errors=[stage.row_id(r) for r in result_rows if r['comparison']['comparison_type']=='verification_error']
    result=dict(schema='hiroute.planning_value_dev_results.v1',scope='Four selected DEV contrasts; not main experiment or holdout',
        numerical_source=prepared['source'],base_main='0f486300d931558d072ce05a6fcc4c42d4b70027',
        dependency_environment=prepared.get('dependency_environment'),
        query_denominator=4,policy_row_denominator=8,all_policy_slots_retained=True,
        policy_summary={p:dict(Counter(r['policy_outcome'] for r in result_rows if r['policy']==p))
                        for p in definition['policies']},
        accounting=dict(raw_terminal_status=status,stage_final_conservative_cpu_s=final_stage,
            gate_inclusive_conservative_cpu_s=inclusive,gate_cap_cpu_s=3000,
            original_total_conservative_cpu_s=spec['carried_cpu_s']+inclusive,
            preprocessing_cpu_s=652.040677976,future_main_CI_reserved_cpu_s=180,
            prior_failed_setup_cpu_s=prepared.get('prior_failed_setup_cpu_s',0)),
        historical_joint_report_sha256=join['sha256'],joint_controls_read_after_policy_terminal_receipts=True,
        historical_timings_not_speedup_controls=True,counterexamples=errors,rows=result_rows)
    if prepared.get('prior_failed_setup_root'):
        predecessor=Path(prepared['prior_failed_setup_root'])
        result['setup_failures']=dict(predecessor_source=stage.load(predecessor/'preparation.json')['source'],
            raw_terminal_status=stage.load(predecessor/'status.json'),
            archived_prelaunch_status=stage.load(predecessor/'prelaunch-failed-status.json'),
            errors=['process-inventory permission denied before worker launch',
                    'existing Boost header path omitted; native compilation failed before graph load/query'],
            failed_cold_workers=1,prelaunch_controller_failures=1,prior_loaded_queries=0,
            prior_conservative_charged_cpu_s=prepared['prior_failed_setup_cpu_s'],solver_repeats=0)
    atomic(out/'planning_value_dev_results.json',result)
    print(json.dumps(dict(summary=result['policy_summary'],accounting=result['accounting'],counterexamples=errors)))
    return not errors


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-root',required=True)
    parser.add_argument('--historical-stage',required=True)
    parser.add_argument('--output-root',required=True)
    args=parser.parse_args()
    raise SystemExit(0 if report(args.input_root,args.historical_stage,args.output_root) else 1)
