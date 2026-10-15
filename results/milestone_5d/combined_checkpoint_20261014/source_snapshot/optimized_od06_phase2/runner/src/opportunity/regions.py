"""Sparse deterministic region builders; geography is only one decision criterion."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
from typing import Protocol, Sequence, TYPE_CHECKING
import numpy as np
from scipy.spatial import cKDTree
from .models import OpportunityRegion, OpportunityId, DecisionOpportunity, ODContext
from envelope import SafeDetourEnvelope
if TYPE_CHECKING:
    from .sparse import NeighborIndex


def fingerprint(config):
    return hashlib.sha256(json.dumps(config, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class OpportunityRegionBuilder(Protocol):
    def build_regions(self, opportunities: Sequence[DecisionOpportunity], od_context: ODContext,
                      envelope: SafeDetourEnvelope) -> list[OpportunityRegion]: ...


@dataclass(frozen=True)
class NeighborPair:
    first: OpportunityId
    second: OpportunityId
    geographic_m: float
    # Maximum of both directed road distances. inf includes cutoff/unreachability.
    network_m: float


def spatial_pairs(opportunities, radius):
    if not np.isfinite(radius) or radius <= 0:
        raise ValueError('Invalid local radius')
    if not opportunities:
        return []
    xy = np.array([(o.x_m, o.y_m) for o in opportunities])
    pairs = cKDTree(xy).query_pairs(radius, output_type='ndarray')
    return [(int(i), int(j), float(np.linalg.norm(xy[i]-xy[j]))) for i, j in pairs]


def make_regions(opportunities, labels, method, config, instance_id):
    groups = {}
    for o, label in zip(opportunities, labels, strict=True):
        groups.setdefault(int(label), []).append(o)
    regions = []
    fp = fingerprint(config)
    for members in groups.values():
        members.sort(key=lambda o: o.identity)
        ids = tuple(o.identity for o in members)
        # Stable content identity, including OD and builder configuration.
        digest = fingerprint({'members': list(map(str, ids)), 'od': instance_id, 'method': method, 'config': fp})[:20]
        anchor = members[0].opportunity
        regions.append(OpportunityRegion(digest, ids, min(o.progress for o in members), max(o.progress for o in members),
            min(o.detour_cost for o in members), max(o.detour_cost for o in members),
            frozenset().union(*(o.opportunity.capabilities for o in members)), anchor.lat, anchor.lon,
            tuple(sorted({o.opportunity.access_node for o in members})), method, fp))
    return sorted(regions, key=lambda r: r.member_ids)


class GeographicRegionBuilder:
    """Geographic baseline: connected components of a radius graph (DBSCAN min_samples=1)."""
    method = 'geographic baseline'

    def __init__(self, config, pairs=None):
        self.config, self.pairs = dict(config), pairs
        if self.config['local_radius_m'] <= 0:
            raise ValueError('Invalid local radius')

    def build_regions(self, opportunities: Sequence[DecisionOpportunity], od_context: ODContext,
                      envelope: SafeDetourEnvelope) -> list[OpportunityRegion]:
        opportunities = sorted(opportunities, key=lambda o: o.identity)
        if any(not envelope.node_mask[o.opportunity.access_node] for o in opportunities):
            raise ValueError('Region member outside envelope')
        from .sparse import NeighborIndex
        if isinstance(self.pairs, NeighborIndex):
            from scipy.sparse import coo_matrix
            from scipy.sparse.csgraph import connected_components
            pairs = self.pairs.select(opportunities) if self.pairs.identities != tuple(o.identity for o in opportunities) else self.pairs
            mask = pairs.geographic_m <= self.config['local_radius_m']
            matrix = coo_matrix((np.ones(mask.sum()), (pairs.first[mask], pairs.second[mask])),shape=(len(opportunities),len(opportunities))).tocsr()
            labels = connected_components(matrix,directed=False,return_labels=True)[1]
            return make_regions(opportunities,labels,self.method,self.config,od_context.instance_id)
        lookup = {o.identity: i for i, o in enumerate(opportunities)}
        parent = list(range(len(opportunities)))
        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]; i = parent[i]
            return i
        pairs = self.pairs
        if pairs is None:
            pairs = [NeighborPair(opportunities[i].identity, opportunities[j].identity, g, np.inf)
                     for i, j, g in spatial_pairs(opportunities, self.config['local_radius_m'])]
        for p in pairs:
            if p.first in lookup and p.second in lookup and p.geographic_m <= self.config['local_radius_m']:
                a, b = find(lookup[p.first]), find(lookup[p.second])
                if a != b: parent[max(a, b)] = min(a, b)
        return make_regions(opportunities, [find(i) for i in range(len(parent))], self.method,
                            self.config, od_context.instance_id)


class DecisionRegionBuilder:
    """Network-validated sparse agglomeration with whole-region range constraints.

    Union order is geographic distance then OSM identity, independent of input
    order. Whole-region progress/detour ranges prevent threshold-graph chaining.
    Local network connectivity is a spanning-tree guarantee, not an all-pairs
    diameter bound. Complementary capabilities are summarized without weighting.
    """
    method = 'decision-aware'

    def __init__(self, config, pairs, union_kernel=None):
        self.config, self.pairs = dict(config), pairs
        self.union_kernel = union_kernel
        for key in ['progress_tolerance', 'detour_tolerance_s', 'local_radius_m', 'network_radius_m', 'max_geographic_diameter_m']:
            if not np.isfinite(config[key]) or config[key] <= 0:
                raise ValueError(f'Invalid {key}')
        if config['min_cluster_size'] != 1:
            raise ValueError('v1 retains singleton evidence; min_cluster_size must be 1')

    def build_regions(self, opportunities: Sequence[DecisionOpportunity], od_context: ODContext,
                      envelope: SafeDetourEnvelope) -> list[OpportunityRegion]:
        opportunities = sorted(opportunities, key=lambda o: o.identity)
        if od_context.distances.unit != 'seconds':
            raise ValueError('This configured detour tolerance requires seconds')
        if any(not envelope.node_mask[o.opportunity.access_node] for o in opportunities):
            raise ValueError('Region member outside envelope')
        n = len(opportunities)
        from .sparse import NeighborIndex
        if self.union_kernel is not None and isinstance(self.pairs, NeighborIndex):
            pairs = self.pairs.select(opportunities) if self.pairs.identities != tuple(o.identity for o in opportunities) else self.pairs
            mask = (pairs.geographic_m <= self.config['local_radius_m']) & (pairs.network_m <= self.config['network_radius_m'])
            edges = np.column_stack((pairs.first[mask],pairs.second[mask]))
            bounds = np.array([[o.progress,o.detour_cost,o.x_m,o.y_m] for o in opportunities]).reshape(n,4)
            labels = self.union_kernel(bounds,edges,self.config)
            return make_regions(opportunities,labels,self.method,self.config,od_context.instance_id)
        lookup = {o.identity: i for i, o in enumerate(opportunities)}
        parent = list(range(n))
        bounds = np.array([[o.progress, o.detour_cost, o.x_m, o.y_m] for o in opportunities]).reshape(n, 4)
        lower, upper = bounds.copy(), bounds.copy()
        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]; i = parent[i]
            return i
        cfg = self.config
        pairs = (p for p in self.pairs if p.first in lookup and p.second in lookup
                 and p.geographic_m <= cfg['local_radius_m'] and p.network_m <= cfg['network_radius_m'])
        for p in sorted(pairs, key=lambda p: (p.geographic_m, p.first, p.second)):
            a, b = find(lookup[p.first]), find(lookup[p.second])
            if a == b: continue
            lo, hi = np.minimum(lower[a], lower[b]), np.maximum(upper[a], upper[b])
            spread = hi-lo
            if (spread[0] > cfg['progress_tolerance'] or spread[1] > cfg['detour_tolerance_s']
                    or np.linalg.norm(spread[2:]) > cfg['max_geographic_diameter_m']):
                continue
            a, b = min(a, b), max(a, b)
            parent[b] = a; lower[a] = lo; upper[a] = hi
        return make_regions(opportunities, [find(i) for i in range(n)], self.method, cfg, od_context.instance_id)
