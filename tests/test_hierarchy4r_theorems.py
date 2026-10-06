"""Independent concrete-evaluator checks and theorem/search boundary fixtures."""
import copy
import math
import numpy as np
import pandas as pd
import pytest
from hierarchy4r.bounds import oracle_bound, directed_time_check, can_prune, SAFE_TAU
from hierarchy4r.domain import flat_actions, effects
from hierarchy4r.search import search
from hierarchy4r.tree import validate_tree, tree_hash
from stopplan4r.models import (StopSite, LocalSupport, EVModel, PiecewiseChargingCurve,
                              PlannerConfig, ScheduledStop, Trip, TravelLeg)
from stopplan4r.evaluation import plan_key


def world(energy=18., scheduled=False, lengths=None, times=None):
    ev=EVModel();curve=PiecewiseChargingCurve();config=PlannerConfig()
    schedule=ScheduledStop(500,2000) if scheduled else None
    sites=[StopSite(f'4r:node/{i}', 'node', i,0,0,i,frozenset({'charge'}),LocalSupport(meal_count=1)) for i in range(1,5)]
    lengths=lengths or [(40000,160000),(20000,200000),(60000,100000),(10000,180000)]
    times=times or [(400,1600),(200,2000),(600,1000),(100,1800)]
    class Travel:
        def leg(self,a,b):
            if (a,b)==(0,5):return TravelLeg(1600,160000)
            i=b-1 if a==0 else a-1;j=0 if a==0 else 1
            return TravelLeg(times[i][j],lengths[i][j])
    trip=Trip(0,5,energy,mobility_budget_s=10000)
    travel=Travel()
    legacy,plans=flat_actions(trip,sites,travel,ev,curve,schedule,config)
    rows=[]
    for site in sites:
        p=plans.get(site.site_id)
        if not p:continue
        e=p.stops[0];i=site.access_node-1
        rows.append(dict(site_id=site.site_id,role=effects(p,site,schedule),feasible=True,
            tm=times[i][0],tp=times[i][1],lm=lengths[i][0],lp=lengths[i][1],
            arrival_energy=e.arrival_energy_kwh,required_energy=6+lengths[i][1]*.00016,
            charge_s=e.charging_duration_s,cost=p.generalized_cost_s))
    tree=dict(site_ids=[s.site_id for s in sites],regions=[
        dict(parent=-1,depth=0,children=[1,2],members=[0,1,2,3]),
        dict(parent=0,depth=1,children=[],members=[0,1]),
        dict(parent=0,depth=1,children=[],members=[2,3])])
    return tree,pd.DataFrame(rows),trip,{s.site_id:s for s in sites},travel,ev,curve,schedule,config,legacy


@pytest.mark.parametrize('energy,scheduled',[(18,False),(18,True),(45.6,True)])
def test_b0_against_independent_accepted_concrete_evaluator(energy,scheduled):
    tree,f,trip,sites,travel,ev,curve,sched,cfg,legacy=world(energy,scheduled)
    for role,g in f.groupby('role'):
        if not role:continue
        b=oracle_bound(g,role,trip,ev,curve,sched,cfg)
        assert not b['H1_violation'] and not b['H3_violation'] and not b['perturbation_violation']
        assert b['lower']<=g.cost.min()+2e-6
        if b['certified']:assert g.cost.max()-b['lower']<=b['gap_bound']+2e-6


@pytest.mark.parametrize('epsilon',[0,30,60,120])
def test_exact_and_epsilon_search_preserves_actions_and_static_tree(epsilon):
    args=world(); tree=args[0];original=copy.deepcopy(tree)
    incumbent,metrics,diag,trace,coverage,_=search(*args[:-1],epsilon=epsilon)
    assert incumbent.generalized_cost_s-args[-1].generalized_cost_s<=epsilon+1e-7
    if epsilon==0:assert plan_key(incumbent)==plan_key(args[-1])
    assert all(r['lost']==r['duplicates']==0 for r in coverage)
    assert tree==original
    assert metrics['logical_site_evaluations']<=metrics['semantic_flat_sites']


def test_empty_role_and_zero_seed():
    args=world(45.6,False)
    inc,metrics,*_=search(*args[:-1])
    assert inc.stop_count==0 and metrics['semantic_flat_sites']==0
    assert metrics['logical_site_evaluations']==0


def test_refinement_not_infeasibility_when_margin_inconclusive():
    args=world(45.6,True)
    f=args[1];b=oracle_bound(f,'S',args[2],args[5],args[6],args[7],args[8])
    # Independent minima combine short incoming and outgoing legs; summed
    # oscillations may exceed no-charge slack despite each Site being feasible.
    assert not b['certified']
    inc,metrics,*_=search(*args[:-1])
    assert inc is not None and metrics['refined']>0


def test_boundary_pruning_and_persistence():
    assert not can_prune(100-SAFE_TAU,100,0)
    assert can_prune(101-SAFE_TAU,100,0)
    assert can_prune(101-SAFE_TAU,90,0)
    assert not can_prune(70-SAFE_TAU,100,30)
    assert can_prune(71-SAFE_TAU,100,30)
    assert not can_prune(math.inf,math.inf,0)


def test_directed_diameter_and_unreachable_pair():
    from scipy.sparse.csgraph import shortest_path
    graph=np.array([[0,4,20,50],[8,0,3,20],[20,6,0,4],[9,20,7,0]],float)
    d=shortest_path(graph,directed=True)
    ids=[1,2]
    r=directed_time_check(d[0,ids],d[ids,3],d[np.ix_(ids,ids)])
    assert r['passed'] and r['diameter']==6
    r=directed_time_check([2,4],[8,3],[[0,math.inf],[1,0]])
    assert math.isinf(r['diameter']) and r['passed']


@pytest.mark.parametrize('boundary',['arrival','capacity','deadline'])
def test_exact_certificate_margin_boundaries(boundary):
    # Exactly representable endpoint products isolate mathematical equality
    # from decimal roundoff; the primary 0.16 model is tested above.
    ev=EVModel(consumption_kwh_km=0.125);curve=PiecewiseChargingCurve();cfg=PlannerConfig(overhead_s=0,lambda_stop_s=0)
    trip=Trip(0,3,30.)
    sched=ScheduledStop(0,200,10)
    lm=[128000,240000] if boundary=='arrival' else [16000,32000]
    lp=[192000,432000] if boundary=='capacity' else [256000,288000]
    rows=[]
    for i in range(2):
        arr=30-lm[i]*.000125;req=6+lp[i]*.000125
        c=curve.duration_s(arr,max(arr,req),60)
        t=100+100*i
        rows.append(dict(role='CS',tm=t,tp=100,lm=lm[i],lp=lp[i],arrival_energy=arr,
            required_energy=req,charge_s=c,cost=max(t+c,t+10)+100))
    b=oracle_bound(pd.DataFrame(rows),'CS',trip,ev,curve,sched,cfg)
    assert b['certified'] and not b['H3_violation']
    if boundary=='arrival':assert abs(b['margin_arrival']-.000125*b['omega_lm'])<1e-12
    if boundary=='capacity':assert abs(b['margin_capacity']-.000125*b['omega_lp'])<1e-12
    if boundary=='deadline':assert b['margin_deadline']==b['omega_tm']


def test_piecewise_crossing_independent_integral():
    c=PiecewiseChargingCurve()
    assert c.duration_s(25,55,60)==pytest.approx(5*36+18*60+7*120)
    # Both endpoints move across different curve bands.
    delta=c.duration_s(25,55,60)-c.duration_s(32,45,60)
    assert delta<=3600*((32-25)+(55-45))/30


def test_static_coverage_and_mutation_detection():
    tree=world()[0];assert validate_tree(tree)
    assert tree_hash(tree)==tree_hash(copy.deepcopy(tree))
    tree['regions'][2]['members'].append(0)
    with pytest.raises(AssertionError):validate_tree(tree)


def test_empty_view_has_no_certificate():
    args=world()
    with pytest.raises(ValueError,match='Empty'):
        oracle_bound(args[1].iloc[:0],'C',args[2],args[5],args[6],args[7],args[8])
