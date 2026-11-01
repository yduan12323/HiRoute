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
    assert stage.reserve_pair(s,12000-620)
    assert not stage.reserve_pair(s,12000-620+.001)
    s['original_cap_cpu_s']=s['carried_cpu_s']+1000
    assert stage.reserve_pair(s,380)
    assert not stage.reserve_pair(s,380.001)


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
    with patch('psutil.virtual_memory',return_value=SimpleNamespace(available=2*1024**3)),\
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
    s['stage_cap_cpu_s']=180
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
        assert stage.load(tmp_path/'status.json')['stage_charged_cpu_s']==180


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
        assert stage.load(tmp_path/'status.json')['stage_charged_cpu_s']==180+122+120


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
        assert stage.load(tmp_path/'status.json')['stage_charged_cpu_s']==180+86*4
        worker.reset_mock();worker.side_effect=AssertionError('duplicate numerical work')
        stage.execute(SimpleNamespace(output_root=str(tmp_path)))
        assert worker.call_count==0
        assert stage.load(tmp_path/'results.json')==first
        assert stage.load(tmp_path/'status.json')['stage_charged_cpu_s']==180+86*4
