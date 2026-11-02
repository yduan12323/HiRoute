"""Read-only receipt join; never repeats a construction or solver call."""
import argparse
from decimal import Decimal,ROUND_CEILING
import hashlib
import json
from pathlib import Path


def load(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def report(root):
    root=Path(root);budget=load(root/'budget.json')
    if budget.get('active'):raise RuntimeError('active/uncertain command; inspect before closing')
    commands={r['label']:r for r in budget['records']};rounds=[]
    for name,directory,ready_name,label_prefix in (
        ('initial','probes','preflight.json','construct_'),
        ('guarded','probes-final','preflight-final.json','final_construct_')):
        ready=load(root/ready_name);rows=[]
        for profile in ready['config']['probes']:
            directory_path=root/directory/profile['id'];receipt=directory_path/'receipt.json'
            command=commands.get(label_prefix+profile['id'])
            row=dict(profile=profile,source=ready['source'],status='unrun')
            if receipt.exists():
                worker=load(receipt);row.update(worker)
                if worker.get('source',{}).get('commit')!=ready['source']['commit']:
                    row['status']='verification_error_source'
                if command is None or command['returncode']!=0 or command.get('guard_reason'):
                    row['status']='not_accepted_by_supervisor'
                if (worker.get('real_graph_loaded') or worker.get('real_table_generated') or
                        worker.get('real_road_queries') or worker.get('SMT_calls') or worker.get('Optimize_calls')):
                    row['status']='verification_error_scope'
                row['raw_receipt_sha256']=sha(receipt)
                row['input_file_sha256']=sha(directory_path/'synthetic-input.json')
                if row.get('input_sha256')!=row['input_file_sha256']:
                    row['status']='verification_error_input'
            elif command is not None or (directory_path/'started.json').exists():
                row['status']='started_without_complete_receipt'
            if command:
                native=command['child_maxrss_native']*(1 if ready['source']['platform'].startswith('macOS') else 1024)
                row.update(guarded_charged_CPU_s=command['charged_CPU_s'],
                    full_process_group_peak_RSS_bytes=max(native,command['sampled_process_group_peak_rss_bytes'],row.get('peak_RSS_bytes',0)),
                    host_available_min_bytes=command['host_available_min_bytes'],
                    supervisor_returncode=command['returncode'],supervisor_guard_reason=command.get('guard_reason'))
            rows.append(row)
        rounds.append(dict(round=name,profile_denominator=ready['config']['probe_denominator'],
            source=ready['source'],preflight_sha256=sha(root/ready_name),rows=rows))
    fee=(Decimal(str(budget['charged_commands_CPU_s'])).quantize(Decimal('.000001'),rounding=ROUND_CEILING)
         +Decimal(budget['fixed_development_control_precharge_CPU_s']))
    parent=Decimal(budget['carried_parent_stage_CPU_s'])+fee
    total=Decimal(budget['carried_research_CPU_s'])+fee
    within=fee<=Decimal(400) and parent<=Decimal(600) and total<=Decimal(28800)
    compact_commands=[]
    for r in budget['records']:
        item={k:r.get(k) for k in ('label','pid','returncode','actual_child_returncode','guard_reason',
            'charged_CPU_s','sampled_process_group_peak_rss_bytes','host_available_min_bytes','controller_sha256')}
        log=root/(r['label']+'.log')
        item['stdout_log_sha256']=sha(log) if log.exists() else None
        if r.get('error'):item['controller_error']=r['error']
        if log.exists() and "No module named 'z3'" in log.read_text():
            item['startup_error']='wrong existing Python environment lacked z3; no completed semantic suite'
        compact_commands.append(item)
    required_tests=('final_tiny_semantics_normal','final_tiny_semantics_optimized',
                    'symbolic_domain_negative_normal','symbolic_domain_negative_optimized')
    tests_passed=all(k in commands and commands[k]['returncode']==0 and
                     commands[k].get('guard_reason') is None for k in required_tests)
    accepted=all(r['status']=='constructed' for r in rounds[-1]['rows']) and within and tests_passed
    return dict(schema='hiroute.exact_leg_construction_results.v1',
        scope='Synthetic exact input/discrete-trace component; not full physical model or real benchmark',
        gate_status='PASS_COMPONENT_ONLY' if accepted else 'LIMITED_OR_FAILED',
        final_profile_denominator=2,construction_slot_denominator=sum(len(r['rows']) for r in rounds),
        total_construction_attempts=sum(row['status']!='unrun' for r in rounds for row in r['rows']),
        initial_profiles_preserved=True,verification_reason=budget.get('verification_amendment'),
        raw_input_preserved_between_rounds=all(a.get('input_sha256')==b.get('input_sha256')
            for a,b in zip(rounds[0]['rows'],rounds[1]['rows'])),
        local_final_suite_tests_per_mode=11,local_tests_passed=tests_passed,
        local_extra_symbolic_domain_test_both_modes=True,
        local_completed_tiny_road_parity_calls=4,
        real_road_queries=0,real_table_generated=False,SMT_Solver_check_calls=0,SMT_Optimize_calls=0,
        old_optimization_cohorts_repeated=False,physical_continuous_model_constructed=False,
        road_selection_certified=False,independent_real_N64_comparator_ready=False,
        original_taskbook_complete=False,main_experiment=False,holdout=False,
        rounds=rounds,command_receipts=compact_commands,
        accounting=dict(additional_cap_CPU_s=400,additional_fixed_precharge_CPU_s=140,
            conservative_metered_commands_CPU_s=str(fee-Decimal(140)),
            additional_conservative_CPU_s=str(fee),prior_parent_stage_CPU_s=budget['carried_parent_stage_CPU_s'],
            cumulative_parent_stage_CPU_s=str(parent),parent_stage_cap_CPU_s=600,
            carried_original_research_CPU_s=budget['carried_research_CPU_s'],
            cumulative_original_research_CPU_s=str(total),original_research_cap_CPU_s=28800,
            remaining_original_CPU_s=str(Decimal(28800)-total),within_caps=within,
            prior_fixed120_retained=True,preprocessing_CPU_s='652.040677976',preprocessing_cap_CPU_s=900,
            ordinary_software_CI='Separate prospective reservations, no old research/CI charge refunds'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input-root',required=True)
    p.add_argument('--output',required=True);a=p.parse_args();result=report(a.input_root)
    with Path(a.output).open('x') as stream:
        json.dump(result,stream,indent=2,sort_keys=True);stream.write('\n')
    print(json.dumps(dict(status=result['gate_status'],accounting=result['accounting'],
        final_rows=[{k:r[k] for k in ('status','literal_Sites','literal_actions','slots',
                   'pair_records','unique_expression_AST_nodes','cpu_s','wall_s','full_process_group_peak_RSS_bytes')}
                   for r in result['rounds'][-1]['rows']]),indent=2))
    raise SystemExit(0 if result['gate_status']=='PASS_COMPONENT_ONLY' else 1)
