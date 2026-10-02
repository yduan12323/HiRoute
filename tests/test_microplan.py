"""Independent tiny directed oracles and compression witnesses."""
import itertools
import numpy as np
import pandas as pd
import pytest
from graph.road_graph import IgraphRoadGraph
from envelope import NumericalTolerance, precompute_detour_distances
from opportunity.models import OpportunityId
from microplan.models import Task, OpportunityArrays, LocalPairs
from microplan.generation import generate_plans
from microplan.compression import pareto_indices, epsilon_cover, random_representatives
from microplan.evaluation import normalize_objectives, regret, utility_family
from microplan.routing import ExactRouter
from _common import read_config


def graph(edges, n=None):
    n = n or max(max(u,v) for u,v,t,d in edges)+1
    nodes = pd.DataFrame({'node_id':np.arange(n),'osm_node_id':np.arange(n)+10,
                          'lat':np.zeros(n),'lon':np.arange(n)/100})
    table = pd.DataFrame(edges,columns=['source','target','travel_time_s','length_m'])
    table['edge_id'] = np.arange(len(edges))
    return IgraphRoadGraph(nodes,table)

@pytest.fixture
def cfg():
    return read_config('configs/microplan.yaml')

@pytest.fixture
def toy(cfg,tmp_path):
    g=graph([(0,1,1,10),(1,2,1,10),(2,3,1,10),(0,2,4,10),
             (2,1,5,10),(1,3,3,10),(3,0,10,10)])
    router=ExactRouter(g,cfg,tmp_path)
    yield g,router
    router.close()


def inputs(g,router,caps=(1,2),risk=(0,0)):
    ds,pl,parents=router.full(0);dd,sl,next_nodes=router.full(3,True)
    nodes=np.array([1,2],dtype=np.int64)
    o=OpportunityArrays(tuple(OpportunityId('node',i+1) for i in range(2)),nodes,np.array(caps),np.array(risk))
    f,fl=router.pairs(nodes[:1],nodes[1:],600)
    r,rl=router.pairs(nodes[1:],nodes[:1],600)
    pairs=LocalPairs(np.array([0]),np.array([1]),np.array([50.]),np.array([10.]),np.array([10.]),f,r,fl,rl)
    return o,pairs,ds,dd,pl,sl,ds[3],pl[3]


def test_exact_single_and_budget(toy,cfg):
    g,r=toy;o,p,ds,dd,pl,sl,t,l=inputs(g,r)
    task=Task('charge',frozenset(['charge']))
    plans=generate_plans(o,p,task,ds,dd,pl,sl,t,l,3,cfg)
    assert len(plans)==1 and plans.total_time_s[0]==3 and plans.second[0]==-1
    assert len(generate_plans(o,p,task,ds,dd,pl,sl,t,l,2.9,cfg))==0


def test_directed_orders_exhaustive_flat_oracle(toy,cfg):
    g,r=toy;o,p,ds,dd,pl,sl,t,l=inputs(g,r)
    task=Task('charge_meal',frozenset(['charge','meal']))
    plans=generate_plans(o,p,task,ds,dd,pl,sl,t,l,10,cfg)
    oracle=[]
    for a,b in itertools.permutations([1,2]):
        cost=g.shortest_path_cost(0,a)+g.shortest_path_cost(a,b)+g.shortest_path_cost(b,3)
        if cost<=10:oracle.append(cost)
    assert sorted(plans.total_time_s.tolist())==sorted(oracle)==[3,9]
    assert np.array_equal(plans.region_mask(np.array([0,1])),[False,False])
    # A: one region preserves optimum. B: crossing regions exclude all bundles.
    assert regret(plans.total_time_s,plans.total_time_s[plans.region_mask(np.array([0,0]))],.01)==(0,0)
    assert regret(plans.total_time_s,plans.total_time_s[plans.region_mask(np.array([0,1]))],.01)[0]==np.inf
    assert len(generate_plans(o,p,task,ds,dd,pl,sl,t,l,8.9,cfg))==1


def test_task_and_multicapability_concurrency(toy,cfg):
    g,r=toy;o,p,ds,dd,pl,sl,t,l=inputs(g,r,caps=(3,2))
    task=Task('charge_meal',frozenset(['charge','meal']))
    plans=generate_plans(o,p,task,ds,dd,pl,sl,t,l,10,cfg,dwell_scenario='structural_concurrency')
    single=np.flatnonzero(plans.second<0)
    assert len(single)==1 and plans.concurrency[single[0]]==2
    assert plans.objectives[single[0],3]==2700
    assert np.any(plans.concurrency==1)  # potential, not certified concurrency
    assert len(generate_plans(o,p,Task('sleep',frozenset(['sleep'])),ds,dd,pl,sl,t,l,10,cfg))==0


def test_conservative_access_and_sequential_dwell(toy,cfg):
    g,r=toy;o,p,ds,dd,pl,sl,t,l=inputs(g,r,risk=(0,1))
    task=Task('compound',frozenset(['charge','meal']))
    assert len(generate_plans(o,p,task,ds,dd,pl,sl,t,l,10,cfg,access_scenario='conservative'))==0
    cfg['concurrency']['potential_network_distance_m']=5
    plans=generate_plans(o,p,task,ds,dd,pl,sl,t,l,10,cfg,dwell_scenario='structural_concurrency')
    assert (plans.concurrency==0).all() and (plans.objectives[:,3]==4500).all()


def test_exact_pareto_preserves_ties_and_matches_exhaustive():
    rng=np.random.default_rng(42)
    z=rng.integers(0,10,(200,5)).astype(float)
    z=np.vstack([z,z[0]])
    oracle=[i for i in range(len(z)) if not np.any(np.all(z<=z[i],axis=1)&np.any(z<z[i],axis=1))]
    assert pareto_indices(z).tolist()==oracle
    assert pareto_indices(np.array([[1,2],[1,2],[2,2]])).tolist()==[0,1]


def test_additive_cover_conditional_bound_and_determinism():
    z=np.array([[0,.1,1,0,0],[.1,0,1,0,0],[.2,.2,1,0,0]])
    eps=np.array([.11,.11,0,0,0])
    kept,witness=epsilon_cover(z,eps)
    assert kept.tolist()==[0]
    assert np.all(z[witness]<=z+eps)
    theta=np.array([.2]*5)
    assert np.all((z[witness]-z)@theta<=theta@eps+1e-12)
    assert np.array_equal(kept,epsilon_cover(z,eps)[0])


def test_random_baseline_loses_strong_candidate():
    z=np.array([[0.,0.,1,0,0],[2.,2.,2,0,0]])
    frontier=pareto_indices(z);retained,_=epsilon_cover(z[frontier],np.zeros(5))
    assert frontier[retained].tolist()==[0]
    random=random_representatives(2,1,0)
    assert random.tolist()==[1] and (z[random].sum()>z[frontier[retained]].sum())


def test_normalization_weights_and_topk(cfg):
    z=np.array([[600,10000,2,28800,1]])
    assert np.array_equal(normalize_objectives(z,cfg['normalization_scales']),np.ones((1,5)))
    names,w=utility_family(cfg['evaluation'],cfg['seed'])
    assert len(names)==16 and (w>0).all() and np.allclose(w.sum(axis=1),1)
    for k in [1,3,5]:
        assert regret([1,2],[1.2,3,4],.01,k)[0]==pytest.approx(.2)
    assert regret([],[],.01)==(None,None)


def test_native_routing_against_independent_igraph(toy):
    g,r=toy
    for root in range(g.node_count):
        for reverse in [False,True]:
            costs,lengths,parents=r.full(root,reverse)
            assert np.allclose(costs,g.single_source_distances(root,direction='in' if reverse else 'out'))
    costs,lengths=r.pairs([1,2],[2,1],2)
    assert costs[0]==1 and lengths[0]==10 and np.isinf(costs[1])

@pytest.mark.parametrize('case',['motorway_exit','asymmetric','river','multiple_exits'])
def test_directed_topological_gateways(case,cfg,tmp_path):
    if case=='motorway_exit':
        edges=[(0,1,1,10),(1,5,1,10),(1,2,1,1),(2,3,1,1),
               (3,2,1,1),(2,1,1,1)]
        members=[3];radius=1.1;destination=5
    elif case=='asymmetric':
        edges=[(0,1,1,10),(1,2,1,1),(2,3,1,1),(3,4,1,1),(4,5,1,10)]
        members=[3];radius=1.1;destination=5
    elif case=='river':
        edges=[(0,1,1,10),(1,2,1,1),(2,3,1,1),(3,7,1,10),
               (0,4,1,10),(4,5,1,1),(5,6,1,1),(6,7,1,10)]
        members=[2,5];radius=.1;destination=7
    else:
        edges=[(0,1,1,10),(1,3,1,1),(0,2,1,10),(2,3,1,1),
               (3,4,1,1),(4,6,1,10),(3,5,1,1),(5,6,1,10)]
        members=[3];radius=1.1;destination=6
    g=graph(edges);r=ExactRouter(g,cfg,tmp_path)
    ds,_,parents=r.full(0);dd,_,next_nodes=r.full(destination,True)
    result=r.gateways(members,ds,dd,parents,next_nodes,20,radius)
    ingress={x.node for x in result.gateways if x.ingress};egress={x.node for x in result.gateways if x.egress}
    if case=='motorway_exit':
        assert ingress==egress=={2}
        assert result.member_ingress==(2,) and result.member_egress==(2,)
    elif case=='asymmetric':
        assert 2 in ingress and 4 in egress
        assert result.member_ingress==(2,) and result.member_egress==(4,)
        if case=='asymmetric':assert 4 not in ingress and 2 not in egress
    elif case=='river':
        assert ingress==egress=={2,5} and result.unreachable_member_count==1
    else:
        assert ingress=={1,2} and egress=={4,5}
    assert result.local_node_count>=len(members)
    r.close()


def test_finite_cross_region_regret_with_single_alternative(toy,cfg):
    g,r=toy;o,p,ds,dd,pl,sl,t,l=inputs(g,r,caps=(1,3))
    plans=generate_plans(o,p,Task('both',frozenset(['charge','meal'])),ds,dd,pl,sl,t,l,10,cfg)
    # The pair and multicap single are equally fast, but pair normalization can
    # favor a cheaper-distance alternative only if it truly exists in the graph.
    assert plans.region_mask(np.array([0,1])).sum()==1
    # Independent objective witness isolates nonzero structural exclusion loss.
    assert regret([1,2],[2],.01)[0]==1


def test_native_grouped_pareto_matches_reference(cfg,tmp_path):
    from microplan.compression import load_grouped_pareto,grouped_epsilon_cover
    native=load_grouped_pareto(cfg,tmp_path)
    rng=np.random.default_rng(93)
    for size in [0,1,50,500]:
        z=rng.integers(0,5,(size,5)).astype(float);groups=rng.integers(0,8,size)
        expected=[]
        for group in np.unique(groups):
            ids=np.flatnonzero(groups==group);expected.extend(ids[pareto_indices(z[ids])])
        assert native(z,groups).tolist()==sorted(expected)
        kept,witness=grouped_epsilon_cover(z,groups,np.ones(5))
        assert np.all(z[witness]<=z+1) and np.array_equal(groups[witness],groups)


def test_cross_region_bundle_finite_regret(cfg,tmp_path):
    g=graph([(0,1,1,10),(1,2,1,10),(2,4,1,10),(0,3,5,50),(3,4,5,50),
             (2,1,4,10),(1,4,2,20),(0,2,2,20)])
    router=ExactRouter(g,cfg,tmp_path)
    ds,pl,_=router.full(0);dd,sl,_=router.full(4,True)
    o=OpportunityArrays(tuple(OpportunityId('node',i) for i in [1,2,3]),np.array([1,2,3]),np.array([1,2,3]),np.zeros(3))
    ft,fl=router.pairs([1],[2],600);rt,rl=router.pairs([2],[1],600)
    pairs=LocalPairs(np.array([0]),np.array([1]),np.array([50.]),np.array([10.]),np.array([10.]),ft,rt,fl,rl)
    plans=generate_plans(o,pairs,Task('both',frozenset(['charge','meal'])),ds,dd,pl,sl,ds[4],pl[4],11,cfg)
    region=plans.region_mask(np.array([0,1,2]))
    assert min(plans.total_time_s)==3 and min(plans.total_time_s[region])==10
    assert regret(plans.total_time_s,plans.total_time_s[region],.01)[0]==7
    router.close()
