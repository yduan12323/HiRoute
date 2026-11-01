"""Controller contracts using fake workers; never open a real road graph."""
import copy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import run_n64_coverage_stage as stage


@pytest.fixture(autouse=True)
def deterministic_controller_cpu():
    # Accounting tests advance this clock explicitly where live CPU matters.
    with patch.object(stage.time,'process_time',return_value=0):
        yield


def spec():
    return stage.load(ROOT/'configs/n64_coverage_stage.json')


def matrix():
    return stage.load(ROOT/'configs/charging_coverage_dev_matrix.json')


def test_denominator_order_and_only_exact_SOC_reuse():
    s,m=spec(),matrix()
    stage.validate_spec(s,m)
    cohort=stage.cells(m)
    assert len(cohort)==48
    assert sum(c['input_status']=='available' for c in cohort)==44
    assert [c['query_id'] for c in cohort[:5]]==['WD01']*4+['WD02']
    assert [r['method'] for r in stage.reused_rows(cohort[0],s,m)]==list(stage.METHODS)
    assert stage.reused_rows(cohort[2],s,m) is None  # same candidates, different SOC
    changed=copy.deepcopy(m);changed['model']['capacity_kwh']='59'
    with pytest.raises(ValueError,match='model'):
        stage.reused_rows(cohort[0],s,changed)
    changed=copy.deepcopy(m);changed['cells'][0],changed['cells'][1]=changed['cells'][1],changed['cells'][0]
    with pytest.raises(ValueError,match='order'):
        stage.cells(changed)


def test_pair_reservation_includes_cold_and_margin_and_both_ledgers():
    s=spec()
    assert stage.reserve_pair(s,12000-1240)
    assert not stage.reserve_pair(s,12000-1240+.001)
    s['original_cap_cpu_s']=s['carried_cpu_s']+1500
    assert stage.reserve_pair(s,260)
    assert not stage.reserve_pair(s,260.001)


def test_completed_receipt_recovery_and_uncertain_attempt_never_restart(tmp_path):
    d=tmp_path/'attempt';d.mkdir()
    assert stage.terminal_row(d) is None
    stage.pilot.atomic(d/'started.json',{'pid':123})
    with pytest.raises(RuntimeError,match='uncertain attempt'):
        stage.terminal_row(d)
    row={'status':'time_limit','worker_cpu_s':120}
    stage.pilot.atomic(d/'job.row.json',row)
    assert stage.terminal_row(d)==row
    stage.pilot.atomic(d/'final.json',{**row,'stage_charged_cpu_s':121})
    assert stage.terminal_row(d)['stage_charged_cpu_s']==121
    with patch.object(stage.pilot,'main',side_effect=AssertionError('duplicate solve')):
        prepared={'source':{},'configs':{},'inputs':{}}
        c={'query_id':'WD01','initial_energy_kwh':'18','scenario':'schedule','N':64}
        target=tmp_path/'attempts'/stage.cell_id(c)/'scale';target.mkdir(parents=True)
        stage.pilot.atomic(target/'final.json',row)
        assert stage.run_worker(tmp_path,prepared,c,'scale',0)==row


def test_lock_excludes_another_controller(tmp_path):
    with stage.controller_lock(tmp_path):
        with pytest.raises(RuntimeError,match='owns the lock'):
            with stage.controller_lock(tmp_path):
                pass


def test_pilot_preflight_uses_exact_declared_OD_order_instead_of_fixed_four(tmp_path):
    cfg=dict(selection=dict(ods=[{'query_id':q} for q in ('a','b','c')],scenarios=[],candidate_counts=[]),
             resources=dict(numeric_workers=1,numeric_threads=1,host_headroom_bytes=0))
    cp,mp,graph=tmp_path/'config.json',tmp_path/'manifest.json',tmp_path/'graph.tsv'
    stage.pilot.atomic(cp,cfg);graph.touch()
    def manifest(ids):
        stage.pilot.atomic(mp,dict(selection_uses_solver_results=False,config=cfg,
                                  queries=[{'query_id':q} for q in ids]))
    args=SimpleNamespace(config=cp,preflight=mp,graph_tsv=graph)
    # Linux code-only CI has no Darwin monitor dependency. Supply that adapter
    # explicitly rather than requiring psutil merely to mock it.
    with patch.dict(sys.modules,{'psutil':SimpleNamespace(virtual_memory=lambda:SimpleNamespace(available=2*1024**3))}),\
         patch('hiroute.runtime.system_mem_available_bytes',return_value=2*1024**3):
        manifest(['a','b','c']);stage.pilot.preflight(args)
        for bad in (['a','b'],['a','a','c'],['b','a','c']):
            manifest(bad)
            with pytest.raises(ValueError,match='declared OD'):stage.pilot.preflight(args)


def test_pilot_persists_supervisor_and_merged_row_before_aggregate_append(tmp_path):
    from hiroute.runtime import SupervisedRun
    cfg=tmp_path/'config.json'
    stage.pilot.atomic(cfg,dict(resources={'new_solve_and_finite_ref_cpu_budget_s':28800,'host_headroom_bytes':0}))
    args=SimpleNamespace(config=cfg,preflight='unused',preflight_only=False,output=tmp_path/'aggregate.jsonl',
        development_cpu_s=100,cold_load_allowance_s=180,graph_tsv=tmp_path/'graph.tsv',native_cache=tmp_path,
        process_memory_gib=8,receipt_directory=str(tmp_path),run_identity={'run':'test'})
    job=dict(N=64,query_id='WD01',scenario='energy_only',method='scale',use_bound=True,solve_limit_s=120,mode='pilot')
    original_atomic=stage.pilot.atomic
    def fake_supervisor(argv,**kw):
        assert kw['cpu_limit_s']==300 and kw['run_identity']=={'run':'test'}
        assert kw['receipt_path'].endswith('.supervisor.json')
        original_atomic(argv[argv.index('--output')+1],dict(status='time_limit',mathematical_status='unknown',worker_cpu_s=7))
        return SupervisedRun(0,False,False,False,123,b'out',b'',9,cpu_peak_s=8)
    def interrupted_append(path,value):
        original_atomic(path,value)
        if str(path).endswith('.row.json'):
            raise InterruptedError('transport disconnected after durable row')
    with patch.object(stage.pilot,'preflight'),patch.object(stage.pilot,'selected_workload',return_value=[job]),\
         patch('hiroute.runtime.run_supervised',side_effect=fake_supervisor),\
         patch.object(stage.pilot,'atomic',side_effect=interrupted_append):
        with pytest.raises(InterruptedError):stage.pilot.supervised_main(args)
    assert not (tmp_path/'aggregate.jsonl').exists()
    assert stage.terminal_row(tmp_path)['new_total_cpu_s']==108
    assert len(list(tmp_path.glob('*.outcome.json')))==1


def test_unknown_is_not_optimal_and_full_key_and_seed_parity_are_checked():
    a=dict(method='flat_bb_strong',status='attained_optimum',key=['1','2',3,['a']],
           feasible_key=['1','2',3,['a']],witness={'physical_verified':True},
           depth_contract={'mode':'unrestricted'},seed_key=['5'])
    b={**a,'method':'scale'}
    stage.validate_row(a);stage.compare_pair([a,b])
    for change,match in (({'witness':None},'physical replay'),({'depth_contract':{'mode':'diagnostic_cap'}},'depth'),
                         ({'status':'worker_error'},'unexpected'),({'failed_phase':'cold_graph_index'},'cold')):
        with pytest.raises(RuntimeError,match=match):stage.validate_row({**a,**change})
    with pytest.raises(RuntimeError,match='full-key'):
        stage.compare_pair([a,{**b,'key':['1','2',3,['b']]}])
    with pytest.raises(RuntimeError,match='seed'):
        stage.compare_pair([a,{**b,'seed_key':['6']}])
    stage.compare_pair([a,{**b,'status':'time_limit','key':None}])
    secondary=[dict(method=method,status='secondary_unattained',primary_value='7',secondary_infimum='2')
               for method in stage.METHODS]
    stage.compare_pair(secondary)
    with pytest.raises(RuntimeError,match='full-key'):
        stage.compare_pair([secondary[0],{**secondary[1],'primary_value':'8'}])


def test_budget_stop_keeps_all_cells_and_resume_charges_once(tmp_path):
    s,m=spec(),matrix()
    # Tiny test-only stage allowance: no worker can start. Reuse/unavailable
    # classification still happens after the budget stop in frozen order.
    s['stage_cap_cpu_s']=300
    prepared=dict(spec=s,source={},matrix_sha256='matrix',configs={})
    stage.pilot.atomic(tmp_path/'preparation.json',prepared)
    def fake_load(path):
        if Path(path)==ROOT/s['matrix']:return m
        return original_load(path)
    original_load=stage.load
    with patch.object(stage,'validate_spec'),patch.object(stage,'source_identity',return_value={}),\
         patch.object(stage,'digest',return_value='matrix'),patch.object(stage,'load',side_effect=fake_load),\
         patch.object(stage,'run_worker',side_effect=AssertionError('unreserved solve')):
        stage.execute(SimpleNamespace(output_root=str(tmp_path)))
        first=stage.load(tmp_path/'results.json')
        assert len(first['rows'])==96
        assert sum(r['status']=='not_run_cpu_budget' for r in first['rows'])==86
        assert sum(r['status']=='input_domain_unavailable' for r in first['rows'])==8
        assert sum(r['execution']=='reused' for r in first['rows'])==2
        stage.execute(SimpleNamespace(output_root=str(tmp_path)))
        assert stage.load(tmp_path/'results.json')==first
        assert stage.load(tmp_path/'status.json')['worker_and_development_cpu_s']==300
        assert stage.load(tmp_path/'status.json')['stage_charged_cpu_s']==302  # cumulative terminal CPU pad


def test_partial_pair_resume_finishes_only_missing_method_and_accounts_saved_CPU(tmp_path):
    s,m=spec(),matrix(); cohort=stage.cells(m)
    # Restrict the mock loop, not the production denominator policy. First fresh
    # pair Strong has already finished; Scale must run once, with both charged.
    c=cohort[1]
    prepared=dict(spec=s,source={},matrix_sha256='matrix',configs={})
    stage.pilot.atomic(tmp_path/'preparation.json',prepared)
    d=tmp_path/'attempts'/stage.cell_id(c)/'flat_bb_strong';d.mkdir(parents=True)
    a=dict(method='flat_bb_strong',status='time_limit',worker_cpu_s=120,supervisor_cpu_s=121)
    stage.pilot.atomic(d/'job.row.json',a)
    original_load=stage.load
    def fake_load(path):return m if Path(path)==ROOT/s['matrix'] else original_load(path)
    b=dict(method='scale',status='time_limit',worker_cpu_s=118,supervisor_cpu_s=119)
    with patch.object(stage,'validate_spec'),patch.object(stage,'source_identity',return_value={}),\
         patch.object(stage,'digest',return_value='matrix'),patch.object(stage,'load',side_effect=fake_load),\
         patch.object(stage,'cells',return_value=[c]+cohort[2:]),\
         patch.object(stage,'reused_rows',return_value=None),\
         patch.object(stage,'reserve_pair',return_value=False),\
         patch.object(stage,'run_worker',return_value=b) as run:
        # Ensure the fake worker mimics its durable method directory.
        def fake_worker(out,p,cell,method,total):
            target=out/'attempts'/stage.cell_id(cell)/method;target.mkdir(parents=True)
            return copy.deepcopy(b)
        run.side_effect=fake_worker
        with pytest.raises(RuntimeError,match='denominator lost'):
            stage.execute(SimpleNamespace(output_root=str(tmp_path)))
        assert run.call_count==1 and run.call_args.args[3]=='scale'
        assert stage.load(tmp_path/'status.json')['stage_charged_cpu_s']==300+122+120


def test_complete_mock_stage_resume_does_not_reexecute_or_double_charge(tmp_path):
    s,m=spec(),matrix();original_load=stage.load
    prepared=dict(spec=s,source={},matrix_sha256='matrix',configs={})
    stage.pilot.atomic(tmp_path/'preparation.json',prepared)
    def fake_load(path):return m if Path(path)==ROOT/s['matrix'] else original_load(path)
    def fake_worker(out,p,cell,method,total):
        target=out/'attempts'/stage.cell_id(cell)/method;target.mkdir(parents=True)
        return dict(method=method,status='infeasible',mathematical_status='infeasible',
                    worker_cpu_s=2.5,supervisor_cpu_s=3,depth_contract={'mode':'unrestricted'})
    with patch.object(stage,'source_identity',return_value={}),\
         patch.object(stage,'digest',return_value='matrix'),patch.object(stage,'load',side_effect=fake_load),\
         patch.object(stage,'run_worker',side_effect=fake_worker) as worker:
        stage.execute(SimpleNamespace(output_root=str(tmp_path)))
        assert worker.call_count==86
        first=stage.load(tmp_path/'results.json')
        assert len(first['rows'])==96
        assert stage.load(tmp_path/'status.json')['stage_charged_cpu_s']==300+86*4
        raw_before={str(p):p.read_bytes() for p in tmp_path.glob('attempts/*/*/final.json')}
        worker.reset_mock();worker.side_effect=AssertionError('duplicate numerical work')
        stage.execute(SimpleNamespace(output_root=str(tmp_path)))
        assert worker.call_count==0
        def science(value):
            return [{k:v for k,v in row.items() if not k.startswith('accounting_')} for row in value['rows']]
        assert science(stage.load(tmp_path/'results.json'))==science(first)
        assert {str(p):p.read_bytes() for p in tmp_path.glob('attempts/*/*/final.json')}==raw_before
        assert stage.load(tmp_path/'status.json')['worker_and_development_cpu_s']==300+86*4
        assert stage.load(tmp_path/'status.json')['stage_charged_cpu_s']==302+86*4


def test_live_controller_CPU_blocks_admission_before_worker(tmp_path):
    s,m=spec(),matrix();s['stage_cap_cpu_s']=1700
    prepared=dict(spec=s,source={},matrix_sha256='matrix',configs={})
    stage.pilot.atomic(tmp_path/'preparation.json',prepared)
    original_load,original_reuse=stage.load,stage.reused_rows
    def fake_load(path):return m if Path(path)==ROOT/s['matrix'] else original_load(path)
    clock=[0]
    def reuse(*args):
        result=original_reuse(*args)
        if result is not None:clock[0]=250
        return result
    with patch.object(stage,'validate_spec'),patch.object(stage,'source_identity',return_value={}),\
         patch.object(stage,'digest',return_value='matrix'),patch.object(stage,'load',side_effect=fake_load),\
         patch.object(stage,'reused_rows',side_effect=reuse),\
         patch.object(stage.time,'process_time',side_effect=lambda:clock[0]),\
         patch.object(stage,'run_worker',side_effect=AssertionError('controller CPU omitted')):
        stage.execute(SimpleNamespace(output_root=str(tmp_path)))
        status=stage.load(tmp_path/'status.json')
        assert status['stage_charged_cpu_s']==550
        assert status['total_controller_cpu_s']==250
        assert status['state']=='budget_stopped'


def test_prior_controller_CPU_persists_across_repeated_resumes(tmp_path):
    s,m=spec(),matrix();s['stage_cap_cpu_s']=1650
    prepared=dict(spec=s,source={},matrix_sha256='matrix',configs={})
    stage.pilot.atomic(tmp_path/'preparation.json',prepared)
    stage.pilot.atomic(tmp_path/'accounting-resume.json',dict(spec=s,execution_source={},revision_id='001',controller_cpu_carried_s=200))
    original_load=stage.load
    def fake_load(path):return m if Path(path)==ROOT/s['matrix'] else original_load(path)
    with patch.object(stage,'validate_spec'),patch.object(stage,'source_identity',return_value={}),\
         patch.object(stage,'digest',return_value='matrix'),patch.object(stage,'load',side_effect=fake_load),\
         patch.object(stage,'run_worker',side_effect=AssertionError('prior controller forgotten')):
        stage.execute(SimpleNamespace(output_root=str(tmp_path)))
        assert stage.load(tmp_path/'status.json')['stage_charged_cpu_s']==500
        stage.execute(SimpleNamespace(output_root=str(tmp_path)))
        assert stage.load(tmp_path/'status.json')['stage_charged_cpu_s']==502
        assert stage.load(tmp_path/'status.json')['total_controller_cpu_s']==202


def test_persistent_pause_hook_stops_only_before_fresh_pair(tmp_path):
    s,m=spec(),matrix();original_load=stage.load
    stage.pilot.atomic(tmp_path/'preparation.json',dict(spec=s,source={},matrix_sha256='matrix',configs={}))
    stage.pilot.atomic(tmp_path/'pause-request.json',{'reason':'operator budget inspection'})
    def fake_load(path):return m if Path(path)==ROOT/s['matrix'] else original_load(path)
    with patch.object(stage,'source_identity',return_value={}),patch.object(stage,'digest',return_value='matrix'),\
         patch.object(stage,'load',side_effect=fake_load),\
         patch.object(stage,'run_worker',side_effect=AssertionError('ignored admission pause')):
        stage.execute(SimpleNamespace(output_root=str(tmp_path)))
        assert stage.load(tmp_path/'status.json')['state']=='paused_requested'
        assert len(stage.load(tmp_path/'results.json')['denominator_cells'])==48
        assert len(stage.load(tmp_path/'results.json')['rows'])==2


def test_accounting_compatibility_does_not_allow_numerical_change_or_lost_CPU():
    assert stage.numerical_paths_unchanged(['tools/run_n64_coverage_stage.py','configs/n64_coverage_stage.json','docs/REAL_SCALE_RESEARCH.md'])
    for path in ('src/hiroute/exact/scale.py','tools/run_real_scale_pilot.py','tools/real_scale_inputs.py','reference/src/hiroute_ref/solver.py'):
        assert not stage.numerical_paths_unchanged([path])
    assert stage.closed_controller_cost({'controller_cpu_s':12.2})==15
    assert stage.closed_controller_cost({'controller_cpu_s':3,'total_controller_cpu_s':100.2})==103
    with pytest.raises(ValueError):stage.closed_controller_cost({'controller_cpu_s':float('nan')})


@pytest.mark.parametrize('defect',[None,'numerical_source','uncertain_receipt','partial_pair'])
def test_reconcile_inspects_closed_pair_and_preserves_original_records(tmp_path,defect):
    s=spec();old=copy.deepcopy(s)
    old['development_and_reporting_precharge_cpu_s']=180;old['pair_reservation_cpu_s']=620
    for key in ('controller_reservation_cpu_s','accounting_revision_additional_precharge_cpu_s'):old.pop(key)
    old_source=dict(commit='old',python='same',platform='same',executable='same')
    new_source={**old_source,'commit':'new'}
    stage.pilot.atomic(tmp_path/'preparation.json',dict(spec=old,source=old_source))
    stage.pilot.atomic(tmp_path/'status.json',dict(state='paused',controller_pid=999,
        controller_cpu_s=3.2,stage_charged_cpu_s=204))
    stage.pilot.atomic(tmp_path/'results.json',{'rows':[]})
    pair=tmp_path/'attempts'/'closed-pair'
    originals={}
    for i,method in enumerate(stage.METHODS):
        if defect=='partial_pair' and i:continue
        d=pair/method;d.mkdir(parents=True)
        stage.pilot.atomic(d/'started.json',{'method':method})
        stage.pilot.atomic(d/'final.json',dict(method=method,status='time_limit',
            mathematical_status='unknown',worker_cpu_s=10,supervisor_cpu_s=11))
        stage.pilot.atomic(d/'job.supervisor.json',dict(status='running' if defect=='uncertain_receipt' else 'completed',
            finished_at=None if defect=='uncertain_receipt' else '2026-11-01T12:00:00Z',pid=123+i))
        originals[d/'final.json']=(d/'final.json').read_bytes()
    gate=tmp_path/'attempts'/'future-pair'
    pause=dict(schema='hiroute.stage.admission_pause.v1',gate_path=str(gate))
    stage.pilot.atomic(gate,pause);stage.pilot.atomic(tmp_path/'admission-pause.json',pause)
    prepared_bytes=(tmp_path/'preparation.json').read_bytes()
    changes='src/hiroute/exact/scale.py\n' if defect=='numerical_source' else 'tools/run_n64_coverage_stage.py\n'
    with patch.object(stage,'source_identity',return_value=new_source),\
         patch.object(stage,'active_pid',return_value=False),\
         patch.object(stage.subprocess,'check_output',return_value=changes):
        args=SimpleNamespace(output_root=str(tmp_path),config=ROOT/'configs/n64_coverage_stage.json')
        if defect:
            with pytest.raises((RuntimeError,ValueError)):stage.reconcile(args)
            assert gate.is_file() and not (tmp_path/'accounting-resume.json').exists()
        else:
            stage.reconcile(args)
            revision=stage.load(tmp_path/'accounting-resume.json')
            assert revision['numerical_source']==old_source and revision['execution_source']==new_source
            assert revision['controller_cpu_carried_s']==6
            assert revision['no_active_workers'] and revision['no_uncertain_attempts']
            assert not gate.exists() and Path(revision['gate_archive']).is_file()
            assert stage.load(revision['previous_raw_status'])['stage_charged_cpu_s']==204
    assert (tmp_path/'preparation.json').read_bytes()==prepared_bytes
    assert {p:p.read_bytes() for p in originals}==originals
