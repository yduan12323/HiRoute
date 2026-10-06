"""Mock-reviewed immutable-leg adapters; real acceptance is an external gate.

No graph shortest paths are computed here. Public callers must obtain table
and restriction objects from their hash-verified loader/restriction factories.
The independent REF adapter is separately implemented outside timecut5.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction as R
from types import MappingProxyType
from typing import Mapping

from .bounded import Problem,_evaluate_sequence_problem,_replay_problem,_solve_problem
from .hierarchy import Region,_solve_hierarchical_problem
from .probe import Witness
from .real_legs import ImmutableLegTable,RestrictedTree,SCHEMA,NUMERICS


@dataclass(frozen=True)
class RealLegPrimitive:
    time: R
    energy: R
    actual_length: R
    source_anchor: str
    target_anchor: str
    table_sha256: str


class RealProblem(Problem):
    """Physical query over immutable accepted direct legs, never a graph."""
    def __init__(self, query: Mapping, table: ImmutableLegTable):
        if not isinstance(table,ImmutableLegTable):
            raise TypeError("A validated immutable leg table is required")
        if "edges" in query:
            raise ValueError("Real leg primitives must not be passed as graph edges")
        sites={sid:list(site.effects) for sid,site in table.sites.items()}
        for key,expected in (("origin",table.origin_anchor),("destination",table.destination_anchor),
                             ("sites",sites),("leg_payload_sha256",table.payload_sha256),
                             ("selection_certificate_sha256",table.selection_certificate_sha256),
                             ("hierarchy_sha256",table.hierarchy_sha256)):
            if key in query and query[key]!=expected:
                raise ValueError(f"Query conflicts with immutable {key}")
        configured=dict(query,origin=table.origin_anchor,destination=table.destination_anchor,sites=sites)
        self._configure_query(configured)
        self.table=table
        self.site_anchors=MappingProxyType({sid:site.anchor_id for sid,site in table.sites.items()})
        self.legs=MappingProxyType({pair:RealLegPrimitive(leg.time,leg.energy(self.rate),leg.actual_length,
                                                      *pair,table.payload_sha256)
                                   for pair,leg in table.legs.items() if leg.reachable})

    def onward_time_lower_bound(self, anchor: str) -> R:
        if anchor not in self.table.anchors:
            raise ValueError("Unknown physical anchor")
        return R(0)


def original_region_view(table: ImmutableLegTable, restriction: RestrictedTree) -> Region:
    """Validate exact action coverage and preserve every original Region ID."""
    if not isinstance(restriction,RestrictedTree) or restriction.original_sha256!=table.hierarchy_sha256:
        raise ValueError("Restriction does not identify the table's frozen original tree")
    sites=set(table.sites)
    if set(restriction.selected_site_ids)!=sites or len(restriction.selected_site_ids)!=len(sites):
        raise ValueError("Restriction and physical Site universe differ")
    rows=restriction.regions
    if not rows or tuple(r.region_id for r in rows)!=tuple(range(len(rows))) or rows[0].parent_id!=-1:
        raise ValueError("Original Region array identities/root are invalid")
    for row in rows:
        if len(set(row.site_ids))!=len(row.site_ids) or not set(row.site_ids)<=sites:
            raise ValueError("Invalid restricted Site membership")
    if set(rows[0].site_ids)!=sites:
        raise ValueError("Original root omits a physical action Site")
    seen=set()
    def visit(index):
        if type(index) is not int or not 0<=index<len(rows) or index in seen:
            raise ValueError("Invalid/cyclic Region topology")
        seen.add(index);row=rows[index]
        if len(set(row.child_ids))!=len(row.child_ids):
            raise ValueError("Duplicate child Region")
        child_nodes=[];covered=set()
        for child in row.child_ids:
            if type(child) is not int or not 0<=child<len(rows) or rows[child].parent_id!=index:
                raise ValueError("Invalid original Region parent link")
            members=set(rows[child].site_ids)
            if covered.intersection(members):
                raise ValueError("Overlapping child action partitions")
            covered.update(members);child_nodes.append(visit(child))
        if row.child_ids and covered!=set(row.site_ids):
            raise ValueError("Child Region action coverage is incomplete")
        return Region(row.region_id,row.site_ids,tuple(child_nodes))
    root=visit(0)
    if len(seen)!=len(rows):
        raise ValueError("Original Region view contains disconnected nodes")
    return root


@dataclass(frozen=True)
class RealResult:
    inner: object
    table_sha256: str
    selection_sha256: str
    hierarchy_sha256: str | None

    def canonical(self):
        result=self.inner.canonical()
        result.update(routing_contract=SCHEMA,numerical_contract=NUMERICS,
                      leg_payload_sha256=self.table_sha256,
                      selection_certificate_sha256=self.selection_sha256,
                      hierarchy_sha256=self.hierarchy_sha256,
                      physical_state_identity="road_anchor",
                      witness_replay_scope="immutable_selected_leg_constants_and_semantic_events")
        return result


def solve_bounded_real(query, table: ImmutableLegTable, restriction: RestrictedTree | None = None,
                       dominance: bool = True) -> RealResult:
    if restriction is not None:original_region_view(table,restriction)
    result=_solve_problem(RealProblem(query,table),dominance)
    return RealResult(result,table.payload_sha256,table.selection_certificate_sha256,
                      restriction.original_sha256 if restriction is not None else None)


def solve_hierarchical_real(query, table: ImmutableLegTable, restriction: RestrictedTree,
                            dominance: bool = True, incumbent: Witness | None = None) -> RealResult:
    root=original_region_view(table,restriction)
    result=_solve_hierarchical_problem(RealProblem(query,table),dominance,root,incumbent)
    return RealResult(result,table.payload_sha256,table.selection_certificate_sha256,restriction.original_sha256)


def evaluate_real_sequence(query,table: ImmutableLegTable,sequence):
    problem=RealProblem(query,table)
    result=_evaluate_sequence_problem(problem,tuple(sequence))
    if result.witness is not None:_replay_problem(problem,result.witness)
    return result


def replay_real_witness(query,table: ImmutableLegTable,witness: Witness):
    return _replay_problem(RealProblem(query,table),witness)
