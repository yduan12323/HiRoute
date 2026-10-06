"""B1-E OFFLINE diagnostics. Frozen B1-D modules are imported read-only."""
import heapq
import math
from types import SimpleNamespace
import numpy as np
from stopplan4r.evaluation import best_one_stop, evaluate_site, scheduled_start_candidates, plan_key
from stopplan4r.models import SearchLabel
from .domain import best
from .deploy import BUCKETS, cost_bound
from .deploy_search import DeployIndex, exact_leaf

AUDIT_TOL=2e-6  # Frozen B1-D cost audit tolerance, also used for E3/E4.
CATEGORIES=('FP1','FP2','FP3','FP4','FP5','FP6','TP')


def flat_baseline(ids,trip,sites,travel,ev,curve,schedule,config):
    """The actual frozen leaf function, without any diagnostic/oracle input."""
    zero=best_one_stop(trip,[],travel,ev,curve,schedule,config)
    counter=SimpleNamespace(evaluator_calls=0)
    plan,semantic,outside,calls=exact_leaf(ids,counter,trip,sites,travel,ev,curve,schedule,config)
    return best(p for p in [zero,plan] if p is not None),dict(
        N_region=0,N_bound=0,N_envelope=len(ids),N_exact=calls,N_semantic=semantic,
        outside_envelope=outside)


def static_minima(metrics,access,members):
    """Exhaustive OFFLINE metric minima and finite counts; no finite substitutions."""
    minima=np.full((len(members)//3,3,4),np.inf)
    finite=np.zeros(minima.shape,dtype=np.int64)
    for (r,b),ids in members.items():
        if len(ids):
            for k,metric in enumerate(metrics):
                values=metric[access[ids]]
                minima[r,b,k]=values.min()
                finite[r,b,k]=np.isfinite(values).sum()
    return minima,finite


class PerfectStaticIndex(DeployIndex):
    """OFFLINE ONLY: same frozen search/leaf policy, exact static metric input."""
    def __init__(self,directory,minima):
        self.directory=directory
        self.minima=minima
        self.counts=np.load(directory/'counts.npy',mmap_mode='r')
        self.children=np.load(directory/'children.npy',mmap_mode='r')
        self.site_ids_read=self.evaluator_calls=self.oracle_reads=self.internal_scans=0
        self.phase='idle'

    def points(self,origin,destination):
        return None

    def bound(self,region,bucket,points,trip,ev,schedule,config,parent):
        # Deliberately nondeployable: minima were constructed with offline scans.
        result=cost_bound(self.minima[region,bucket],bucket,trip,ev,schedule,config,parent)
        return dict(region=region,bucket=BUCKETS[bucket],internal=bool(self.children[region,0]>=0),
                    diagnostic_only=True,**result)


def normalized_perfect_static(minima,parents,region,bucket,trip,ev,schedule,config,cache):
    key=(region,bucket)
    if key not in cache:
        parent=parents[region]
        lower=-math.inf if parent<0 else normalized_perfect_static(
            minima,parents,parent,bucket,trip,ev,schedule,config,cache)['lower']
        cache[key]=cost_bound(minima[region,bucket],bucket,trip,ev,schedule,config,lower)
    return cache[key]


def decompose(alt,perfect,semantic):
    landmark=perfect-alt
    if semantic is None:
        return dict(G_landmark=landmark,G_residual=None,total_slack=None,identity_error=None)
    residual=semantic-perfect;total=semantic-alt
    return dict(G_landmark=landmark,G_residual=residual,total_slack=total,
                identity_error=total-(landmark+residual))


def terminal_category(site,trip,travel,ev,curve,schedule,config,feasible,role):
    """Classify a paid check OFFLINE, with the required terminal precedence.

    feasible/role are the archived unchanged evaluator result, never used by
    either flat_baseline or deployable search. Rejection physics is independently
    recomputed using the accepted evaluator and schedule-start routine.
    """
    first=travel.leg(trip.origin,site.access_node);last=travel.leg(site.access_node,trip.destination)
    tol=1e-8+trip.mobility_budget_s*1e-10
    if first is None or last is None or first.time_s+last.time_s>trip.mobility_budget_s+tol:
        return 'FP1','exact_envelope'
    root=SearchLabel(trip.origin,0.,trip.initial_energy_kwh,False,0,0.)
    view=evaluate_site(site,root,trip.destination,travel,ev,curve,schedule,config,start_time_s=trip.start_time_s)
    if view is None:
        assert not feasible
        return 'FP5','attachment_or_baseline_unavailable'
    if view.arrival_energy_kwh<ev.minimum_energy_kwh-1e-8:
        assert not feasible
        return 'FP2','execution_floor'
    if not view.energy_feasible:
        assert not feasible
        return 'FP3','capacity_or_noncharger_terminal_reserve'
    if schedule is not None and schedule.hard:
        starts=scheduled_start_candidates(view.arrival_time_s-trip.start_time_s,
            view.charging_duration_s,schedule,config,trip.start_time_s)
        fits=schedule.supports(site) and any(max(schedule.window_start_s-trip.start_time_s-t,
            t-(schedule.window_end_s-trip.start_time_s),0)<=1e-8 for t in starts)
        if not fits:
            assert not feasible
            return 'FP4','hard_schedule'
    if not feasible:
        if first.time_s+last.time_s>trip.mobility_budget_s+1e-7:
            return 'FP5','accepted_evaluator_budget_tolerance'
        raise AssertionError('Undeclared concrete rejection; stop diagnosis')
    return ('TP','semantic') if role else ('FP6','feasible_effect_free')


def pop_order(records,children):
    """Reconstruct frozen heap order from recorded bounds/decisions, without costs."""
    by={(r['region'],r['bucket']):i for i,r in enumerate(records)}
    queue=[];order=[]
    def push(i):
        r=records[i]
        reason=r.get('infeasible')
        if reason is None or (isinstance(reason,float) and math.isnan(reason)):
            heapq.heappush(queue,(r['lower'],r['region'],BUCKETS.index(r['bucket']),i))
    for bucket in BUCKETS:
        if (0,bucket) in by:push(by[0,bucket])
    while queue:
        _,region,bucket,i=heapq.heappop(queue);r=records[i];order.append(r)
        if r['decision']=='refined':
            for child in children[region]:
                key=(int(child),BUCKETS[bucket])
                if key in by:push(by[key])
    return order


def incumbent_diagnosis(records,traces,leaves,children,zero_cost,final_cost):
    order=pop_order(records,children)
    assert len(order)==len(traces)
    leafmap={(r['region'],r['bucket']):r for r in leaves}
    refined=candidates=exact=0;first=None
    for i,(r,t) in enumerate(zip(order,traces)):
        if r['decision']=='refined':refined+=1
        if r['decision']=='leaf':
            leaf=leafmap[r['region'],r['bucket']]
            candidates+=leaf['candidates'];exact+=leaf['objective_site_calls']
        assert candidates==t['exact_site_evaluations']
        u=t['incumbent']
        finite=u is not None and math.isfinite(u)
        if first is None and finite and (zero_cost is None or round(u,7)<round(zero_cost,7)):
            assert r['decision']=='leaf'
            first=dict(pops_to_first_site=i+1,refinements_to_first_site=refined,
                candidates_to_first_site=candidates,exact_to_first_site=exact,first_site_cost=u)
    result=dict(zero_initialized=zero_cost is not None,initial_incumbent_cost=zero_cost,
        first_site_acquired=first is not None,final_optimum_cost=final_cost,
        time_to_first_site_seconds=None,total_pops=len(order),total_refinements=refined,
        first_finite_U_pops=0 if zero_cost is not None else None if first is None else first['pops_to_first_site'])
    keys=['pops_to_first_site','refinements_to_first_site','candidates_to_first_site','exact_to_first_site','first_site_cost']
    result.update(first if first else dict.fromkeys(keys))
    result['fraction_pops_to_first_site']=None if first is None else first['pops_to_first_site']/len(order)
    result['fraction_refinements_to_first_site']=None if first is None or not refined else first['refinements_to_first_site']/refined
    return result
