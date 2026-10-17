"""Typed structural microplans; evaluation weights never enter construction."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
import numpy as np
from opportunity.models import OpportunityId

AccessRisk = Literal['low_access_risk', 'uncertain_access']

@dataclass(frozen=True)
class Task:
    name: str
    required_capabilities: frozenset[str]
    primary: bool = True

@dataclass(frozen=True)
class Gateway:
    node: int
    ingress: bool
    egress: bool
    boundary_edge_count: int

@dataclass(frozen=True)
class RegionGateways:
    gateways: tuple[Gateway, ...]
    member_nodes: tuple[int, ...]
    member_ingress: tuple[int | None, ...]
    member_egress: tuple[int | None, ...]
    local_node_count: int
    local_edge_count: int
    unreachable_member_count: int
    local_build_seconds: float
    interface_seconds: float

@dataclass(frozen=True)
class MicroPlan:
    opportunity_ids: tuple[OpportunityId, ...]
    required_capabilities: frozenset[str]
    ingress_gateway: int | None
    egress_gateway: int | None
    visit_order: tuple[OpportunityId, ...]
    total_route_time_s: float
    total_route_distance_m: float
    detour_time_s: float
    detour_distance_m: float
    stop_count: int
    dwell_time_s: float
    capabilities_satisfied: frozenset[str]
    exact_feasible: bool
    access_risk: AccessRisk
    concurrency: str
    feasibility_fingerprint: str

@dataclass(frozen=True)
class OpportunityArrays:
    identities: tuple[OpportunityId, ...]
    access_nodes: np.ndarray
    capability_masks: np.ndarray
    risk: np.ndarray

@dataclass(frozen=True)
class LocalPairs:
    first: np.ndarray
    second: np.ndarray
    geographic_m: np.ndarray
    # Each ordered direction has separately validated distance and exact time.
    distance_forward_m: np.ndarray
    distance_reverse_m: np.ndarray
    time_forward_s: np.ndarray
    time_reverse_s: np.ndarray
    fastest_length_forward_m: np.ndarray
    fastest_length_reverse_m: np.ndarray

@dataclass(frozen=True)
class PlanBatch:
    """Compact typed columnar representation, IDs index frozen OpportunityArrays.

    second=-1 denotes a single object. Rows are ordered by first/second identity
    index. Distances are lengths of actual lexicographically fastest paths.
    """
    first: np.ndarray
    second: np.ndarray
    total_time_s: np.ndarray
    total_distance_m: np.ndarray
    objectives: np.ndarray
    concurrency: np.ndarray

    def __len__(self):
        return len(self.first)

    def subset(self, indices):
        return PlanBatch(*(a[indices] for a in (self.first, self.second, self.total_time_s,
                            self.total_distance_m, self.objectives, self.concurrency)))

    def region_mask(self, labels):
        return (self.second < 0) | (labels[self.first] == labels[np.maximum(self.second, 0)])


def materialize_plan(batch: PlanBatch, index: int, opportunities: OpportunityArrays,
                     task: Task, fingerprint: str, ingress_gateway=None, egress_gateway=None) -> MicroPlan:
    """Reconstruct a typed plan on demand; bulk storage remains compact columns."""
    first,second=int(batch.first[index]),int(batch.second[index])
    order=(opportunities.identities[first],) if second<0 else (opportunities.identities[first],opportunities.identities[second])
    z=batch.objectives[index]
    return MicroPlan(order,task.required_capabilities,ingress_gateway,egress_gateway,order,
        float(batch.total_time_s[index]),float(batch.total_distance_m[index]),float(z[0]),float(z[1]),
        int(z[2]),float(z[3]),task.required_capabilities,True,
        'low_access_risk' if z[4]==0 else 'uncertain_access',
        {0:'sequential',1:'potential_concurrency',2:'concurrent-compatible'}[int(batch.concurrency[index])],fingerprint)
