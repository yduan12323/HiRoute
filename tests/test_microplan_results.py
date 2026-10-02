"""Acceptance on complete frozen M4B evidence, with no previous-result writes."""
import json
import numpy as np
import pandas as pd
import pytest
from _common import ROOT,sha256,read_config

@pytest.fixture(scope='module')
def results(request):
    root=ROOT/'results/milestone_4b'
    if not (root/'acceptance.json').exists() and not request.config.getoption('--require-microplan-results'):
        pytest.skip('Complete M4B acceptance not yet recorded')
    if not (root/'benchmark.json').exists():
        pytest.fail('M4B benchmark is required')
    return root


def test_all_od_budget_task_scenarios_and_counts(results):
    table=pd.read_parquet(results/'candidate_counts.parquet')
    assert set(table.instance_id)==set(range(30))
    assert set(table.ratio)=={1.,1.05,1.1,1.2,1.4,1.6,2.}
    assert table.groupby(['instance_id','ratio','task','access_scenario','dwell_scenario','method']).size().eq(1).all()
    assert len(table)==30*7*8*2*2*12
    assert (table.candidate_count<=table.flat_count).all()
    assert set(table.query('ratio==2 and boundary_risk').instance_id)=={0,1,4,9,10,16,19,22,23}
    assert not table[table.ratio.isin([1.05,1.1,1.2,1.4])].boundary_risk.any()


def test_exact_pareto_cover_bounds_and_topk(results):
    table=pd.read_parquet(results/'stage_regret.parquet')
    finite=np.isfinite(table.pareto_loss)
    assert np.allclose(table.loc[finite,'pareto_loss'],0,atol=1e-10)
    cfg=read_config('configs/microplan.yaml')
    weights=pd.read_parquet(results/'utility_weights.parquet').set_index('theta_id')
    for cover,eps in cfg['epsilon_covers'].items():
        bound=weights.to_numpy()@np.array(eps)
        expected=table.theta_id.map(dict(zip(weights.index,bound))).to_numpy()
        valid=np.isfinite(table[cover+'_cover_loss'])
        assert np.all(table.loc[valid,cover+'_cover_loss']<=expected[valid]+1e-10)
    top=pd.read_parquet(results/'topk_regret.parquet',columns=['instance_id','ratio','task','access_scenario','dwell_scenario','method','theta_id','k','absolute_regret'])
    pivot=top.pivot(index=['instance_id','ratio','task','access_scenario','dwell_scenario','method','theta_id'],columns='k',values='absolute_regret')
    assert np.allclose(pivot[1],pivot[3],equal_nan=True) and np.allclose(pivot[1],pivot[5],equal_nan=True)
    covers=pd.read_parquet(results/'epsilon_cover_stats.parquet')
    assert covers.componentwise_cover_verified.all()
    assert (covers.retained_count<=covers.pareto_count).all()


def test_saved_flat_plans_identity_budget_capability_and_reproducibility(results):
    benchmark=json.loads((results/'benchmark.json').read_text())
    catalogue=pd.read_parquet(results/'opportunity_index.parquet')
    cfg=read_config('configs/microplan.yaml')
    assert len(benchmark['candidate_partition_files'])==30*8
    od_table=pd.read_parquet(ROOT/'results/milestone_3a/od_remapping.parquet').set_index('instance_id')
    for relative,record in benchmark['candidate_partition_files'].items():
        assert sha256(results/relative)==record['sha256']
        od=int(relative.split('od_')[1][:2]);task=relative.split('od_')[1][3:-8]
        plans=pd.read_parquet(results/relative)
        assert len(plans)==record['row_count']
        assert np.isfinite(plans.total_route_time_s).all() and np.isfinite(plans.total_route_distance_m).all()
        budget=2*float(od_table.loc[od].ext_baseline_time_s)
        assert (plans.total_route_time_s<=budget+1e-8+budget*1e-10).all()
        assert ((plans.first_index>=0)&(plans.first_index<len(catalogue))).all()
        assert ((plans.second_index>=-1)&(plans.second_index<len(catalogue))).all()
        assert (plans.first_index!=plans.second_index).all()
        # Deterministic stable visit order and task evidence, sampled across every
        # partition; exhaustive construction/property tests run on toy graphs.
        sample=plans.iloc[np.linspace(0,max(len(plans)-1,0),min(len(plans),25),dtype=int)]
        for row in sample.itertuples():
            caps=set(catalogue.iloc[row.first_index].capabilities)
            if row.second_index>=0:caps.update(catalogue.iloc[row.second_index].capabilities)
            assert set(cfg['tasks'][task]['required_capabilities'])<=caps
    for name,digest in benchmark['result_files'].items():assert sha256(results/name)==digest
    for name,digest in benchmark['analysis_files'].items():assert sha256(results/name)==digest


def test_protected_files_and_gateway_semantics(results):
    before=json.loads((results/'preservation_before.json').read_text())
    for p,digest in before['preserved_files'].items():assert sha256(ROOT/p)==digest,p
    gateway=pd.read_parquet(results/'gateways.parquet')
    assert (gateway.ingress|gateway.egress).all() and (gateway.boundary_edge_count>0).all()
    assert set(gateway.instance_id)==set(range(30))
    stats=pd.read_parquet(results/'region_gateway_stats.parquet')
    assert (stats.local_node_count>=stats.member_access_nodes).all()
    assert (stats.routing_computations_avoided==0).all()
    failure=pd.read_parquet(results/'failure_analysis.parquet')
    assert not failure.gateway_pruning_applied.any()
