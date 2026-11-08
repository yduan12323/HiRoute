"""One separately admitted finite+DAG live consumer; no retry or transport."""
import sys,os,json,time
from pathlib import Path
sys.path.insert(0,str(Path.cwd()/'tools'))
from run_grounded_lookup_consumer import Clock,verify_identity,producer_chain,load_verified_table,raw_replay,PINNED,THREAD_VARS,completed_result
from run_shared_leg_pilot import source,load,sha,atomic,ROOT
from shared_pilot_budget import admit

def verify_new_controller(out,ad):
    d=load(out/'budget.json');initial=load(out/'initial-budget.json')
    if sha(out/'initial-budget.json')!=ad['initial_budget_sha256']:raise ValueError('initial accounting changed')
    if sha(out/'historical-budget.json')!=ad['historical_budget_sha256'] or sha(Path(ad['historical_budget_path']))!=ad['historical_budget_sha256']:raise ValueError('historical charges changed')
    if sha(out/'consumer-admission.json')!=d['consumer_admission_sha256']:raise ValueError('admission changed')
    if sha(Path(__file__))!=ad['runner_sha256']:raise ValueError('runner changed')
    for k in ('records','phase_charged_CPU_s','fixed_precharge_CPU_s','carried_research_CPU_s','allocations_CPU_s','cap_CPU_s','original_cap_CPU_s','allowed_real_attempts'):
        if d[k]!=initial[k]:raise ValueError('accounting mismatch '+k)
    admit(initial,'optimization',180,120,120)
    active=d.get('active') or {}
    if (active.get('phase'),active.get('child_CPU_limit'),active.get('wall_limit'),active.get('reserved_CPU_s'))!=('optimization',120,120,180):raise ValueError('controller limits')
    if active.get('pid')!=os.getpid() or active.get('controller_pid')!=os.getppid():raise ValueError('controller PID binding')
    if active.get('controller_sha256')!=ad['controller_sha256'] or sha(ROOT/'tools/shared_pilot_budget.py')!=ad['controller_sha256']:raise ValueError('controller source')
    if any(os.environ.get(v)!='1' for v in THREAD_VARS):raise ValueError('single-worker environment')
    parent=Path(ad['audit_parent']);audit=Path(ad['audit_dir'])
    if not parent.is_dir() or audit.parent!=parent or audit.exists() or sha(parent/'preflight-persistence.txt')!=ad['audit_probe_sha256']:raise ValueError('persistent audit preflight')
    if not ad['finite_lookup'] or not ad['dag_audit'] or ad['holdout'] or (ad['sites'],ad['actions'],ad['pairs'],ad['complete_H'])!=(64,78,4225,20):raise ValueError('domain/encoding contract')
    if ad.get('incumbent_certificate')!='fresh-live-formula-only':raise ValueError('fresh certificate admission required')
    if ad.get('extract_witness') is not True:raise ValueError('extraction admission required')
    return d

def run(out):
    from fractions import Fraction
    from exact_physical_adapter import Encoding,table_relevant_depth,replay
    from import_strict_candidate import verify_candidate
    from unittest.mock import patch
    clock=Clock(out);table=None
    with (out/'optimization.started.json').open('x') as f:json.dump(dict(started_at=time.time(),source=source(),pid=os.getpid()),f)
    result=dict(mode='optimization',status='UNKNOWN',holdout=False,road_selection_certified=False,verification_scope='SEPARATE_POST_RUN_VERIFICATION',original_run_status='UNKNOWN',original_run_completed_in_budget=False)
    try:
        with clock.phase('consumer-and-producer-admission'):
            ad=load(out/'consumer-admission.json');verify_identity(ad);verify_new_controller(out,ad)
            if ad['producer_files']!=PINNED or ad['real_attempts']!=1 or ad['wall_s']!=120:raise ValueError('admission changed')
            root=Path(ad['producer_root']);old,val=producer_chain(root,clock.check)
            origin=Path(ad['origin']);bound=Fraction(ad['bound'])
            for name,expected in ad['sealed_origin_files'].items():
                if sha(origin/name,clock.check)!=expected:raise ValueError('origin evidence changed')
        with clock.phase('full-input-load-and-validation'):
            table,parameters=load_verified_table(root,old,val,clock.check)
            if sha(Path(old['graph_db']),clock.check)!=old['graph_db_sha256']:raise ValueError('raw graph changed')
            pairs=[*old['sample_pairs'],*((p.source,p.target) for p in table.literal_plan_legs(old['upper_witness']['plan'],1))]
            raw_replay(table,old,pairs,clock.check)
            depth,seed=table_relevant_depth(table,parameters,old['upper_witness'])
            if depth!=20 or seed['key'][0]!=bound:raise ValueError('frozen domain/upper changed')
        with clock.phase('complete-model-reconstruction'):
            m=Encoding(table,parameters,depth,bound,clock.check,finite_lookup=True)
            x,y=m.state_copy(clock.check),m.state_copy(clock.check)
        with clock.phase('separate-candidate-verification'):
            comparison=verify_candidate(origin,ad['expected_import'],Path(ad['audit_dir']),m,x,y,table,parameters,old['upper_witness'],clock.check)
            atomic(out/'verification.returned.json',comparison)
        with clock.phase('final-verification'):
            from finalize_candidate_verification import finalize
            def verify_final_inputs():
                producer_chain(root,clock.check)
                for name in ('numeric.json','paths.index.json','paths.bin'):
                    if sha(root/'split-table'/name,clock.check)!=table._path_store.manifest['files'][name]['sha256']:raise ValueError('producer data changed')
                if sha(Path(old['graph_db']),clock.check)!=old['graph_db_sha256']:raise ValueError('raw graph changed')
                for name,expected in ad['sealed_origin_files'].items():
                    if sha(origin/name,clock.check)!=expected:raise ValueError('origin evidence changed')
                verify_identity(ad);clock.check()
            result=finalize(comparison,ad,old,table,parameters,Path(ad['audit_dir']),clock.check,verify_final_inputs)
    except Exception as exc:result.update(status='UNKNOWN',reason=repr(exc))
    finally:
        if table is not None:table._path_store.close()
    if time.monotonic()-clock.start>=120:result.update(status='UNKNOWN',reason='verification deadline')
    result.update(body_wall_s=time.monotonic()-clock.start,body_CPU_s=time.process_time()-clock.cpu)
    atomic(out/'optimization.result.json',result)
    return 0 if result['status']=='COMPLETE' else 75

def main():
    import argparse
    from unittest.mock import patch
    from contextlib import ExitStack
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    # This process must never enter a solver, optimizer, tactic or SMT parser.
    with ExitStack() as stack:
        for name in ('Solver','Optimize','Tactic','parse_smt2_file','parse_smt2_string'):
            stack.enter_context(patch('z3.'+name,side_effect=AssertionError('solver-free verification only')))
        return run(args.output.resolve())

if __name__=='__main__':raise SystemExit(main())
