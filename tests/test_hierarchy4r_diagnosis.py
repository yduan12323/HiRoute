from dataclasses import replace
from pathlib import Path
import json
import numpy as np
import pytest
from scipy.sparse.csgraph import shortest_path
from hierarchy4r import deploy_search as frozen
from hierarchy4r.diagnosis import (flat_baseline,static_minima,PerfectStaticIndex,
    normalized_perfect_static,decompose,terminal_category,CATEGORIES,AUDIT_TOL)
from hierarchy4r.deploy import cost_bound
from hierarchy4r.domain import effects
from stopplan4r.models import ScheduledStop,TravelLeg
from stopplan4r.evaluation import plan_key
from test_hierarchy4r_domain import fixture


def test_flat_uses_identical_frozen_leaf():
    assert flat_baseline.__globals__['exact_leaf'] is frozen.exact_leaf
    site,_,_,args=fixture(8)
    p,w=flat_baseline([site.site_id],args[0],{site.site_id:site},*args[2:])
    assert p.stops[0].site_id==site.site_id and w['N_exact']==w['N_semantic']==1


def test_directed_static_minima_and_unreachable_counts():
    d=shortest_path(np.array([[0,2,10,0],[4,0,3,0],[1,9,0,0],[0,0,0,0.]]),directed=True)
    members={(0,0):np.array([0,1]),(0,1):np.array([2]),(0,2):np.array([],int)}
    minima,finite=static_minima([d[0],d[:,0],d[0]*100,d[:,0]*100],np.array([1,2,3]),members)
    assert np.array_equal(minima[0,0],[2,1,200,100])
    assert np.isinf(minima[0,1:]).all() and finite[0,0,0]==2 and finite[0,1,0]==0


@pytest.mark.parametrize('bucket,energy',[(0,8),(1,45.6),(2,8),(2,45.6)])
def test_perfect_static_cost_order_and_admissibility(bucket,energy):
    sched=None if bucket==0 else ScheduledStop(0,1000)
    site,_,plans,args=fixture(energy,sched,charger=bucket!=1)
    ps=cost_bound((100,100,10000,10000),bucket,args[0],args[3],sched,args[-1])
    alt=cost_bound((0,50,0,5000),bucket,args[0],args[3],sched,args[-1])
    j=plans[site.site_id].generalized_cost_s
    assert alt['lower']<=ps['lower']<=j
    gaps=decompose(alt['lower'],ps['lower'],j)
    assert abs(gaps['identity_error'])<=AUDIT_TOL
    assert gaps['G_landmark']>=0 and gaps['G_residual']>=0


def test_parent_normalization_and_missing_semantic_target():
    site,_,_,args=fixture(8)
    minima=np.array([[[100,100,10000,10000]]*3,[[150,150,10000,10000]]*3])
    cache={}
    child=normalized_perfect_static(minima,[-1,0],1,0,args[0],args[3],None,args[-1],cache)
    assert child['lower']>=cache[0,0]['lower']
    assert decompose(100,110,None)['G_residual'] is None


@pytest.mark.parametrize('energy,schedule,charger,budget,expected',[
    (.1,ScheduledStop(0,1),False,100,'FP1'),
    (.1,ScheduledStop(0,1),False,300,'FP2'),
    (8,ScheduledStop(0,1),False,300,'FP3'),
    (45.6,ScheduledStop(0,1),False,300,'FP4'),
    (45.6,None,True,300,'FP6'),
    (8,None,True,300,'TP')])
def test_terminal_precedence_and_no_effect(energy,schedule,charger,budget,expected):
    site,_,plans,args=fixture(energy,schedule,charger)
    trip=replace(args[0],mobility_budget_s=budget)
    p=plans.get(site.site_id)
    cat,_=terminal_category(site,trip,*args[2:],p is not None,effects(p,site,schedule))
    assert cat==expected and sum(cat==c for c in CATEGORIES)==1


def test_other_reject_preserves_two_frozen_budget_tolerances():
    site,_,_,args=fixture()
    class Travel:
        def leg(self,a,b):return TravelLeg(1000000,1)
    trip=replace(args[0],mobility_budget_s=2000000-1e-5)
    cat,reason=terminal_category(site,trip,Travel(),*args[3:],False,'')
    assert cat=='FP5' and reason=='accepted_evaluator_budget_tolerance'


def test_perfect_static_replay_same_optimum_and_exact_leaf(tmp_path):
    site,_,plans,args=fixture(8)
    np.save(tmp_path/'counts.npy',np.array([[1,0,0]]))
    np.save(tmp_path/'children.npy',np.array([[-1,-1]]))
    (tmp_path/'leaf_buckets').mkdir()
    (tmp_path/'leaf_buckets/0.json').write_text(json.dumps(dict(Ccap=[site.site_id],S0cap=[],SCcap=[])))
    index=PerfectStaticIndex(tmp_path,np.array([[[100,100,10000,10000]]*3]))
    p,stats,_,_,leaves=frozen.deploy_search(index,args[0],{site.site_id:site},*args[2:])
    assert plan_key(p)==plan_key(plans[site.site_id])
    assert sum(l['candidates'] for l in leaves)==stats['exact_site_evaluations']==1


def test_frozen_modules_and_all_protected_evidence_unchanged():
    from _common import sha256
    root=Path(__file__).resolve().parents[1]
    manifest=json.loads((root/'results/milestone_4r_b1e/preservation_before.json').read_text())
    for p,h in manifest['files'].items():assert sha256(root/p)==h,p
