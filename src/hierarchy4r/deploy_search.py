"""Online static-superset search. No dependency on H0/B1-O reference records."""
import heapq,json,math,time
from collections import Counter
import numpy as np
from stopplan4r.evaluation import best_one_stop,plan_key
from .domain import flat_actions,effects,best
from .deploy import BUCKETS,alt,cost_bound


class DeployIndex:
    def __init__(self,directory):
        self.directory=directory
        self.summary=np.load(directory/'summaries.npy',mmap_mode='r')
        self.counts=np.load(directory/'counts.npy',mmap_mode='r')
        self.children=np.load(directory/'children.npy',mmap_mode='r')
        self.arrays=[[[np.load(directory/'landmarks'/f'{metric}_{l}_{d}.npy',mmap_mode='r')
                       for l in range(8)] for d in ['out','in']] for metric in ['travel_time','distance']]
        self.site_ids_read=0;self.evaluator_calls=0;self.oracle_reads=0;self.internal_scans=0
        self.phase='idle'

    def points(self,origin,destination):
        return [np.array([[[array[node] for array in direction] for direction in metric]
                          for metric in self.arrays]) for node in [origin,destination]]

    def leaf_ids(self,region,bucket):
        if self.phase!='leaf' or self.children[region,0]>=0:
            self.internal_scans+=1;raise RuntimeError('Internal Site-ID access prohibited')
        ids=json.loads((self.directory/'leaf_buckets'/f'{region}.json').read_text())[BUCKETS[bucket]]
        self.site_ids_read+=len(ids)
        return ids

    def bound(self,region,bucket,points,trip,ev,schedule,config,parent):
        self.phase='bound';before=(self.site_ids_read,self.evaluator_calls,self.oracle_reads)
        s=self.summary[region,bucket];o,z=points
        metrics=(alt(s[0],o[0]),alt(s[0],z[0],True),alt(s[1],o[1]),alt(s[1],z[1],True))
        record=cost_bound(metrics,bucket,trip,ev,schedule,config,parent)
        after=(self.site_ids_read,self.evaluator_calls,self.oracle_reads)
        self.phase='idle'
        return dict(region=region,bucket=BUCKETS[bucket],internal=bool(self.children[region,0]>=0),
            landmark_count=8,summary_rows_read=16,site_ids_read=after[0]-before[0],
            evaluator_calls=after[1]-before[1],oracle_table_reads=after[2]-before[2],**record)


def exact_leaf(ids,index,trip,sites,travel,ev,curve,schedule,config):
    """Every reached candidate incurs an exact envelope check; all work counted.

    Outside-envelope candidates are rejected before objective evaluation and
    recorded separately. Primary work conservatively counts them as well.
    """
    eligible=[];outside=0
    tol=1e-8+trip.mobility_budget_s*1e-10
    for site_id in ids:
        site=sites[site_id]
        first=travel.leg(trip.origin,site.access_node);last=travel.leg(site.access_node,trip.destination)
        if first is not None and last is not None and first.time_s+last.time_s<=trip.mobility_budget_s+tol:
            eligible.append(site)
        else:outside+=1
    index.evaluator_calls+=len(eligible)
    _,plans=flat_actions(trip,eligible,travel,ev,curve,schedule,config)
    semantic=[]
    for site in eligible:
        plan=plans.get(site.site_id)
        if effects(plan,site,schedule):semantic.append(plan)
    return best(semantic),len(semantic),outside,len(eligible)


def deploy_search(index,trip,sites,travel,ev,curve,schedule,config,epsilon=0):
    begin=time.perf_counter();t=time.perf_counter();points=index.points(trip.origin,trip.destination)
    lookup_seconds=time.perf_counter()-t
    index.site_ids_read=index.evaluator_calls=index.oracle_reads=index.internal_scans=0
    incumbent=best_one_stop(trip,[],travel,ev,curve,schedule,config)
    queue=[];records=[];traces=[];leaves=[];stats=Counter();bound_seconds=0.;leaf_seconds=0.
    floor=math.inf
    def create(region,bucket,parent=-math.inf):
        nonlocal bound_seconds
        if not index.counts[region,bucket]:return
        t=time.perf_counter();r=index.bound(region,bucket,points,trip,ev,schedule,config,parent)
        bound_seconds+=time.perf_counter()-t
        r['decision']='infeasible_'+r['infeasible'] if r['infeasible'] else 'open'
        records.append(r);stats['bounds']+=1
        if not r['infeasible']:heapq.heappush(queue,(r['lower'],region,bucket,len(records)-1))
    for bucket in ([0] if schedule is None else [1,2]):create(0,bucket)
    while queue:
        lb,region,bucket,ri=heapq.heappop(queue);r=records[ri];stats['popped']+=1
        u=math.inf if incumbent is None else incumbent.generalized_cost_s
        if math.isfinite(u) and lb>=u-epsilon:
            r['decision']='cost';floor=min(floor,lb)
        elif index.children[region,0]>=0:
            r['decision']='refined'
            for child in index.children[region]:create(int(child),bucket,lb)
        else:
            r['decision']='leaf';index.phase='leaf';t=time.perf_counter()
            ids=index.leaf_ids(region,bucket)
            candidate,nsemantic,outside,calls=exact_leaf(ids,index,trip,sites,travel,ev,curve,schedule,config)
            leaf_seconds+=time.perf_counter()-t;index.phase='idle'
            stats['exact_site_evaluations']+=len(ids);stats['semantic_site_evaluations']+=nsemantic
            stats['objective_site_calls']+=calls;stats['outside_envelope']+=outside
            leaves.append(dict(region=region,bucket=BUCKETS[bucket],candidates=len(ids),semantic=nsemantic,
                false_positives=len(ids)-nsemantic,outside_envelope=outside,objective_site_calls=calls))
            if candidate is not None and (incumbent is None or plan_key(candidate)<plan_key(incumbent)):incumbent=candidate
        u=math.inf if incumbent is None else incumbent.generalized_cost_s
        lower=min(u,queue[0][0] if queue else math.inf,floor)
        traces.append(dict(step=len(traces),exact_site_evaluations=stats['exact_site_evaluations'],
            incumbent=None if not math.isfinite(u) else u,certified_gap=None if not math.isfinite(u-lower) else u-lower))
    total=time.perf_counter()-begin
    return incumbent,dict(stats,lookup_seconds=lookup_seconds,bound_seconds=bound_seconds,
        leaf_seconds=leaf_seconds,refinement_overhead_seconds=max(0.,total-lookup_seconds-bound_seconds-leaf_seconds),
        search_seconds=total,internal_scans=index.internal_scans,oracle_reads=index.oracle_reads),records,traces,leaves
