"""User-agnostic activity evidence and route-attached decision representations."""
from __future__ import annotations
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Literal, Sequence
import numpy as np
from envelope import DetourDistances, NumericalTolerance


@dataclass(frozen=True, order=True)
class OpportunityId:
    osm_type: Literal['node', 'way', 'relation']
    osm_id: int

    def __post_init__(self):
        if self.osm_type not in ('node', 'way', 'relation') or self.osm_id <= 0:
            raise ValueError('Invalid OSM identity')

    def __str__(self):
        return f'{self.osm_type}/{self.osm_id}'


@dataclass(frozen=True)
class Provenance:
    source_datasets: tuple[str, ...]
    snapshot_timestamp: str
    geometry_method: str


@dataclass(frozen=True)
class Opportunity:
    identity: OpportunityId
    lat: float
    lon: float
    capabilities: frozenset[str]
    subtype: str | None
    original_tags: Mapping[str, str]
    provenance: Provenance
    access_node: int | None = None
    access_osm_node_id: int | None = None
    access_distance_m: float | None = None
    attachment_status: str = 'unattached'

    def __post_init__(self):
        if not np.isfinite([self.lat, self.lon]).all() or not -90 <= self.lat <= 90 or not -180 <= self.lon <= 180:
            raise ValueError('Invalid opportunity coordinates')
        object.__setattr__(self, 'original_tags', MappingProxyType(dict(self.original_tags)))
        object.__setattr__(self, 'capabilities', frozenset(self.capabilities))


@dataclass(frozen=True)
class DecisionOpportunity:
    opportunity: Opportunity
    through_cost: float
    detour_cost: float
    detour_ratio: float
    progress: float
    x_m: float
    y_m: float

    @property
    def identity(self) -> OpportunityId:
        return self.opportunity.identity


@dataclass(frozen=True)
class ODContext:
    instance_id: int
    distances: DetourDistances


@dataclass(frozen=True)
class OpportunityRegion:
    region_id: str
    member_ids: tuple[OpportunityId, ...]
    progress_min: float
    progress_max: float
    detour_min: float
    detour_max: float
    capabilities: frozenset[str]
    anchor_lat: float
    anchor_lon: float
    access_nodes: tuple[int, ...]
    construction_method: str
    config_fingerprint: str
    # Anchor is a member location, never asserted to be a gateway.
    topology_reference: str = 'frozen_extended_graph; member access nodes'


def decision_features(opportunities: Sequence[Opportunity], distances: DetourDistances, xy) -> list[DecisionOpportunity]:
    if distances.baseline_cost <= 0:
        raise ValueError('Normalized progress requires a positive baseline cost')
    result = []
    for o, (x, y) in zip(opportunities, xy, strict=True):
        if o.attachment_status != 'attached' or o.access_node is None:
            continue
        v = o.access_node
        if not 0 <= v < len(distances.node_lower_bounds):
            raise ValueError('Access node outside graph')
        h = float(distances.node_lower_bounds[v])
        if not np.isfinite(h):
            continue
        r = float(distances.forward_distances[v] / h)
        if not 0 <= r <= 1:
            raise ValueError('Invalid route progress')
        result.append(DecisionOpportunity(o, h, h - distances.baseline_cost,
                                          h / distances.baseline_cost, r, float(x), float(y)))
    return result


def eligible_opportunities(features: Sequence[DecisionOpportunity], budget: float,
                           tolerance: NumericalTolerance = NumericalTolerance()) -> list[DecisionOpportunity]:
    if not np.isfinite(budget) or budget < 0:
        raise ValueError('Invalid budget')
    return [o for o in features if o.through_cost <= budget + tolerance.allowance(budget)]
