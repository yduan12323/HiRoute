import math
from types import SimpleNamespace
import numpy as np
import pandas as pd
import pytest
from scipy.sparse.csgraph import shortest_path
from hierarchy4r.deploy import select_landmarks,alt,cost_bound,bucket_flags,reduction,micro_reduction
from hierarchy4r.deploy_search import exact_leaf,DeployIndex
from stopplan4r.models import EVModel,PlannerConfig,ScheduledStop,Trip


def test_landmarks_unique_repeatable_scc_only():
    nodes=pd.DataFrame(dict(lon=[0.]*10,lat=[0.]*10,osm_node_id=list(reversed(range(10)))))
    scc=np.arange(1,9)
    a=select_landmarks(nodes,scc)
    assert a==select_landmarks(nodes,scc) and len(set(a))==8 and set(a)==set(scc)
    assert a==list(reversed(scc))
    with pytest.raises(ValueError):select_landmarks(nodes,np.arange(7))


@pytest.mark.parametrize('metric_scale',[1.,1000.])
@pytest.mark.parametrize('members',[[1],[1,2],[1,1,2],[1,4]])
def test_directed_alt_independent_exact_minima(metric_scale,members):
    graph=np.array([[0,2,9,8,0],[4,0,3,9,0],[7,1,0,2,0],[3,4,5,0,0],[0,0,0,0,0]],float)*metric_scale
    d=shortest_path(graph,directed=True)
    # Hand-computable paths: 0->1->2, 0->1->2->3 and 2->3->0.
    assert d[0,2]==5*metric_scale and d[0,3]==7*metric_scale and d[2,0]==5*metric_scale
    landmarks=[0,2,3]
    s=np.array([[d[l,members].min(),d[l,members].max(),d[members,l].min(),d[members,l].max()] for l in landmarks])
    with np.errstate(invalid='raise'):
        for point in range(5):
            p=np.array([d[landmarks,point],d[point,landmarks]])
            assert alt(s,p)<=d[point,members].min()+1e-8
            assert alt(s,p,True)<=d[members,point].min()+1e-8
    if 4 in members:assert np.isinf(s[:,1]).all() and np.isinf(s[:,3]).all()


def test_no_inf_subtraction_and_zero_fallback():
    with np.errstate(invalid='raise'):
        assert alt(np.full((8,4),np.inf),np.full((2,8),np.inf))==0


@pytest.mark.parametrize('bounds,bucket,energy,schedule,reason',[
    ((600,600,0,0),0,18,None,'envelope'),
    ((0,0,1e6,0),0,18,None,'inbound_energy'),
    ((0,0,0,1e6),0,18,None,'outbound_energy'),
    ((0,0,50000,80000),1,18,ScheduledStop(0,1000),'noncharger_energy'),
    ((900,0,0,0),2,45.6,ScheduledStop(0,1000),'schedule')])
def test_safe_infeasibility(bounds,bucket,energy,schedule,reason):
    r=cost_bound(bounds,bucket,Trip(0,1,energy,mobility_budget_s=1000),EVModel(),schedule,PlannerConfig())
    assert r['infeasible']==reason


@pytest.mark.parametrize('bucket',[0,1,2])
def test_cost_formulas_and_parent_monotonicity(bucket):
    sched=None if bucket==0 else ScheduledStop(800,1800)
    r=cost_bound((100,200,10000,100000),bucket,Trip(0,1,45.6,mobility_budget_s=2000),EVModel(),sched,PlannerConfig())
    assert r['raw_cost']==(1200 if bucket==0 else 4300)
    assert r['lower']<r['raw_cost'] and r['infeasible'] is None
    child=cost_bound((100,200,10000,100000),bucket,Trip(0,1,45.6,mobility_budget_s=2000),EVModel(),sched,PlannerConfig(),r['raw_cost']+1)
    assert child['lower']==r['raw_cost']+1


def test_bucket_coverage_and_false_positives():
    from test_hierarchy4r_domain import fixture
    site,_,plans,args=fixture()
    assert bucket_flags(site)==(True,False,True)
    index=SimpleNamespace(evaluator_calls=0)
    p,n,_,calls=exact_leaf([site.site_id],index,args[0],{site.site_id:site},*args[2:])
    assert p is None and n==0 and calls==1  # Charger adds no energy.
    site,_,plans,args=fixture(schedule=ScheduledStop(0,1000))
    p,n,_,_=exact_leaf([site.site_id],index,args[0],{site.site_id:site},*args[2:])
    assert p is not None and n==1 and p.stops[0].charged_kwh==0  # SCcap -> S.
    site,_,_,_=fixture(charger=False)
    assert bucket_flags(site)==(False,True,False)


def test_d5_internal_ids_prohibited():
    index=DeployIndex.__new__(DeployIndex);index.phase='bound';index.internal_scans=0
    index.children=np.array([[1,2],[-1,-1],[-1,-1]])
    with pytest.raises(RuntimeError):index.leaf_ids(0,0)
    assert index.internal_scans==1


def test_na_and_micro_accounting():
    assert reduction(0,0) is None and reduction(12,10)==pytest.approx(-.2)
    assert micro_reduction([0,2],[0,10])==.8
    assert micro_reduction([0],[0]) is None


def test_empty_bucket_creates_no_bound_or_leaf():
    from hierarchy4r.deploy_search import deploy_search
    from test_hierarchy4r_domain import fixture
    site,_,_,args=fixture()
    class EmptyIndex:
        counts=np.zeros((1,3),int)
        def points(self,*args):return None
        def bound(self,*args):raise AssertionError('Empty bucket evaluated')
        def leaf_ids(self,*args):raise AssertionError('Empty bucket enumerated')
    p,stats,records,traces,leaves=deploy_search(EmptyIndex(),args[0],{site.site_id:site},*args[2:])
    assert p is not None and not p.stops
    assert records==traces==leaves==[]


@pytest.mark.parametrize('bucket,energy',[(0,8),(1,45.6),(2,8),(2,45.6)])
def test_cost_bounds_against_unchanged_concrete_evaluator(bucket,energy):
    from test_hierarchy4r_domain import fixture
    sched=None if bucket==0 else ScheduledStop(0,1000)
    site,_,plans,args=fixture(energy,sched,charger=bucket!=1)
    bound=cost_bound((100,100,10000,10000),bucket,args[0],args[3],sched,args[-1])
    assert bound['infeasible'] is None
    assert bound['lower']<=plans[site.site_id].generalized_cost_s
    if bucket!=1 and energy==8:
        assert bound['q_lower']==pytest.approx(1.2)
        assert bound['charging_lower']==pytest.approx(43.2)


def test_exact_leaf_preserves_deterministic_site_tie():
    from dataclasses import replace
    from test_hierarchy4r_domain import fixture
    from stopplan4r.evaluation import plan_key
    site,_,_,args=fixture(8)
    second=replace(site,site_id='4r:node/2',osm_id=2)
    sites={s.site_id:s for s in [site,second]}
    index=SimpleNamespace(evaluator_calls=0)
    p,n,_,_=exact_leaf(list(sites),index,args[0],sites,*args[2:])
    reverse,_,_,_=exact_leaf(list(reversed(sites)),index,args[0],sites,*args[2:])
    assert n==2 and p.stops[0].site_id==site.site_id
    assert plan_key(p)==plan_key(reverse)


def test_unavailable_landmarks_do_not_restrict_site_feasibility(tmp_path):
    import json
    from hierarchy4r.deploy_search import deploy_search
    from test_hierarchy4r_domain import fixture
    site,_,_,args=fixture(8)
    index=DeployIndex.__new__(DeployIndex)
    index.summary=np.full((1,3,2,8,4),np.inf)
    index.counts=np.array([[1,0,0]])
    index.children=np.array([[-1,-1]])
    index.points=lambda *unused:[np.full((2,2,8),np.inf)]*2
    index.directory=tmp_path
    (tmp_path/'leaf_buckets').mkdir()
    (tmp_path/'leaf_buckets/0.json').write_text(json.dumps(dict(Ccap=[site.site_id],S0cap=[],SCcap=[])))
    p,stats,records,_,_=deploy_search(index,args[0],{site.site_id:site},*args[2:])
    assert p.stops[0].site_id==site.site_id and stats['exact_site_evaluations']==1
    assert all(records[0][k]==0 for k in ['tm','tp','dm','dp','site_ids_read','evaluator_calls','oracle_table_reads'])
