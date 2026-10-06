"""Best-bound-first oracle study. Every saved work count is LOGICAL only."""
import heapq
import math
from collections import Counter
from stopplan4r.evaluation import best_one_stop, plan_key
from .bounds import oracle_bound, can_prune
from .domain import ROLES
from .tree import tree_hash


def search(tree, frame, trip, sites_by_id, travel, ev, curve, schedule, config, epsilon=0.):
    before=tree_hash(tree)
    semantic=frame[frame.role.isin(ROLES)].set_index('site_id',drop=False)
    assert semantic.index.is_unique and semantic.feasible.all()
    regions=tree['regions']; site_ids=tree['site_ids']
    role_ids={r:set(semantic[semantic.role.eq(r)].site_id) for r in ROLES}
    assert set.union(*role_ids.values())==set(semantic.site_id)
    assert sum(map(len,role_ids.values()))==len(semantic)
    incumbent=best_one_stop(trip,[],travel,ev,curve,schedule,config)
    queue=[]; diagnostics=[]; traces=[]; coverage=[]; evaluated=set()
    counters=Counter(dict.fromkeys(['views_created','views_popped','bounds_computed','pruned','refined','leaves'],0))
    perrole={r:Counter() for r in ROLES}
    pruned_floor=math.inf

    def push(region,role):
        counters['views_created']+=1;perrole[role]['views_created']+=1
        ids=[site_ids[i] for i in regions[region]['members'] if site_ids[i] in role_ids[role]]
        if not ids:return
        group=semantic.loc[ids]
        bound=oracle_bound(group,role,trip,ev,curve,schedule,config)
        counters['bounds_computed']+=1;perrole[role]['bounds_computed']+=1
        diagnostics.append(dict(region=region,role=role,depth=regions[region]['depth'],site_count=len(ids),**bound))
        if bound['H1_violation'] or bound['H3_violation'] or bound['perturbation_violation']:
            raise AssertionError(f'B0 theorem violation: {diagnostics[-1]}')
        heapq.heappush(queue,(bound['safe_lower'],region,role,ids))

    def trace():
        u=math.inf if incumbent is None else incumbent.generalized_cost_s
        frontier=queue[0][0] if queue else math.inf
        global_lower=min(u,frontier,pruned_floor)
        traces.append(dict(step=len(traces),logical_sites=len(evaluated),bounds=counters['bounds_computed'],
            popped=counters['views_popped'],incumbent=None if not math.isfinite(u) else u,
            open_lower=None if not math.isfinite(frontier) else frontier,
            G_open=None if not math.isfinite(u-frontier) else u-frontier,
            certified_gap=None if not math.isfinite(u-global_lower) else max(0.,u-global_lower)))

    for role in ROLES:push(0,role)
    trace()
    while queue:
        lb,region,role,ids=heapq.heappop(queue)
        counters['views_popped']+=1;perrole[role]['views_popped']+=1
        if can_prune(lb,math.inf if incumbent is None else incumbent.generalized_cost_s,epsilon):
            counters['pruned']+=1;perrole[role]['pruned']+=1
            pruned_floor=min(pruned_floor,lb)
        elif regions[region]['children']:
            counters['refined']+=1;perrole[role]['refined']+=1
            children=regions[region]['children']
            parts=[{site_ids[i] for i in regions[c]['members']} & role_ids[role] for c in children]
            lost=set(ids)-set.union(*parts); duplicates=len(parts[0]&parts[1])
            coverage.append(dict(region=region,role=role,lost=len(lost),duplicates=duplicates))
            assert not lost and not duplicates and set.union(*parts)==set(ids)
            for child in children:push(child,role)
        else:
            counters['leaves']+=1;perrole[role]['leaves']+=1
            assert not evaluated.intersection(ids)
            evaluated.update(ids);perrole[role]['site_evaluations']+=len(ids)
            candidate=best_one_stop(trip,[sites_by_id[i] for i in ids],travel,ev,curve,schedule,config)
            if candidate is not None and (incumbent is None or plan_key(candidate)<plan_key(incumbent)):
                incumbent=candidate
        trace()
    assert before==tree_hash(tree)
    return incumbent,dict(counters,semantic_flat_sites=len(semantic),logical_site_evaluations=len(evaluated),
        logical_sites_avoided=len(semantic)-len(evaluated),reduction=None if not len(semantic) else 1-len(evaluated)/len(semantic)),diagnostics,traces,coverage,perrole
