"""Representation compression/coherence and partition evolution, never utility."""
from collections import Counter
import numpy as np

COMBINATIONS = [('charge','meal'), ('charge','parking'), ('meal','parking'), ('sleep','charge'), ('services','meal')]


def region_statistics(regions, features, pairs, network_radius_m):
    lookup = {o.identity: o for o in features}
    membership = {i: r.region_id for r in regions for i in r.member_ids}
    local_by_region = {}
    from .sparse import NeighborIndex
    fast_counts = None
    if isinstance(pairs, NeighborIndex):
        from scipy.sparse import coo_matrix
        from scipy.sparse.csgraph import connected_components
        region_lookup = {r.region_id: i for i,r in enumerate(regions)}
        group = np.array([region_lookup.get(membership.get(i),-1) for i in pairs.identities],dtype=np.int64)
        local_mask = (group[pairs.first] >= 0) & (group[pairs.first] == group[pairs.second])
        valid_mask = local_mask & (pairs.network_m <= network_radius_m)
        matrix = coo_matrix((np.ones(valid_mask.sum()),(pairs.first[valid_mask],pairs.second[valid_mask])),shape=(len(group),len(group))).tocsr()
        labels = connected_components(matrix,directed=False,return_labels=True)[1]
        counts = np.bincount(group[pairs.first[local_mask]],minlength=len(regions))
        valid_counts = np.bincount(group[pairs.first[valid_mask]],minlength=len(regions))
        max_network = np.zeros(len(regions))
        np.maximum.at(max_network,group[pairs.first[valid_mask]],pairs.network_m[valid_mask])
        components = np.zeros(len(regions),dtype=int)
        if len(group):
            good = group >= 0
            combinations = np.unique(np.column_stack((group[good],labels[good])),axis=0)
            components = np.bincount(combinations[:,0],minlength=len(regions))
        fast_counts = (region_lookup,counts,valid_counts,max_network,components)
    for p in (() if fast_counts is not None else pairs):
        region_id = membership.get(p.first)
        if region_id is not None and region_id == membership.get(p.second):
            local_by_region.setdefault(region_id, []).append(p)
    rows = []
    for region in regions:
        members = [lookup[i] for i in region.member_ids]
        progress = np.array([o.progress for o in members]); detour = np.array([o.detour_cost for o in members])
        xy = np.array([(o.x_m, o.y_m) for o in members])
        spatial_span = float(np.linalg.norm(np.ptp(xy, axis=0)))
        ids = set(region.member_ids)
        # Local candidate-edge connectivity; no all-pairs network claim.
        local = local_by_region.get(region.region_id, [])
        validated = [p for p in local if p.network_m <= network_radius_m]
        parent = {i: i for i in ids}
        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i
        for p in validated:
            a, b = find(p.first), find(p.second)
            if a != b: parent[max(a,b)] = min(a,b)
        components = len({find(i) for i in ids})
        local_count, valid_count = len(local),len(validated)
        edge_max = max((p.network_m for p in validated), default=0.)
        if fast_counts is not None:
            lookup_region,counts,valid_counts,max_network,component_counts = fast_counts
            index = lookup_region[region.region_id]
            components = int(component_counts[index])
            local_count,valid_count = int(counts[index]),int(valid_counts[index])
            edge_max = float(max_network[index])
        row = {'region_id': region.region_id, 'member_count': len(members),
               'capabilities': sorted(region.capabilities), 'capability_count': len(region.capabilities),
               'access_nodes': list(region.access_nodes), 'anchor_lat': region.anchor_lat, 'anchor_lon': region.anchor_lon,
               'progress_spread': float(np.ptp(progress)), 'progress_variance': float(np.var(progress)),
               'detour_spread_s': float(np.ptp(detour)), 'detour_variance_s2': float(np.var(detour)),
               'geographic_bbox_diagonal_m': spatial_span,
               'local_network_components': components, 'local_candidate_pair_count': local_count,
               'local_network_valid_fraction': valid_count/local_count if local_count else None,
               'validated_network_edge_max_m': edge_max,
               'construction_method': region.construction_method, 'config_fingerprint': region.config_fingerprint}
        for a,b in COMBINATIONS: row[f'{a}+{b}'] = a in region.capabilities and b in region.capabilities
        rows.append(row)
    n, k = len(features), len(regions)
    def mean(key): return float(np.mean([r[key] for r in rows])) if rows else 0.
    def weighted(key): return sum(r[key]*r['member_count'] for r in rows)/n if n else 0.
    summary = {'eligible_opportunities': n, 'region_count': k, 'compression_ratio': 1-k/n if n else None,
               'mean_members': n/k if k else 0., 'median_members': float(np.median([r['member_count'] for r in rows])) if k else 0.,
               'singleton_fraction': sum(r['member_count']==1 for r in rows)/k if k else None,
               'mean_capability_count': mean('capability_count'), 'mean_progress_spread': mean('progress_spread'),
               'mean_detour_spread_s': mean('detour_spread_s'), 'weighted_progress_variance': weighted('progress_variance'),
               'weighted_detour_variance_s2': weighted('detour_variance_s2'),
               'mean_geographic_bbox_diagonal_m': mean('geographic_bbox_diagonal_m'),
               'network_disconnected_region_fraction': sum(r['local_network_components']>1 for r in rows)/k if k else None,
               'maximum_geographic_bbox_diagonal_m': max((r['geographic_bbox_diagonal_m'] for r in rows), default=0.)}
    for a,b in COMBINATIONS: summary[f'{a}+{b}_regions'] = sum(r[f'{a}+{b}'] for r in rows)
    return rows, summary


def expansion_stability(previous, current):
    a = {i: r.region_id for r in previous for i in r.member_ids}
    b = {i: r.region_id for r in current for i in r.member_ids}
    common = a.keys() & b.keys()
    contingency = Counter((a[i],b[i]) for i in common)
    ca, cb = Counter(a[i] for i in common), Counter(b[i] for i in common)
    choose = lambda v: sum(n*(n-1)/2 for n in v)
    n = len(common)
    total = n*(n-1)/2
    expected = choose(ca.values())*choose(cb.values())/total if total else 0.
    max_index = (choose(ca.values())+choose(cb.values()))/2
    ari = (choose(contingency.values())-expected)/(max_index-expected) if max_index != expected else (1. if n else None)
    full_b = Counter(b.values())
    best = {x: 0. for x in ca}
    for (x,y), intersection in contingency.items():
        best[x] = max(best[x], intersection/(ca[x]+full_b[y]-intersection))
    old_degrees = Counter(x for x, _ in contingency)
    new_degrees = Counter(y for _, y in contingency)
    splits = sum(degree > 1 for degree in old_degrees.values())
    merges = sum(degree > 1 for degree in new_degrees.values())
    return {'common_member_count': n, 'new_opportunity_count': len(b)-n, 'removed_opportunity_count': len(a)-n,
            'adjusted_rand_common': ari, 'mean_best_full_member_jaccard': float(np.mean(list(best.values()))) if best else None,
            'new_regions_without_old_members': sum(r.region_id not in cb for r in current),
            'split_old_regions': splits, 'merged_current_regions': merges}
