"""Mock-reviewed immutable-leg adapters; real acceptance is an external gate.

No graph shortest paths are computed here. Public callers must obtain table
and restriction objects from their hash-verified loader/restriction factories.
The independent REF adapter is separately implemented outside timecut5.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction as R
import hashlib
import json
from collections.abc import Mapping as AbstractMapping
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


class _OnDemandRealLegs(AbstractMapping):
    def __init__(self, table, rate, cache):
        self.table, self.rate, self.cache = table, rate, cache

    def __getitem__(self, pair):
        leg = self.cache.leg(*pair)
        if not leg.reachable:
            raise KeyError(pair)
        return RealLegPrimitive(leg.time, leg.energy(self.rate), leg.actual_length,
                                *pair, self.table.payload_sha256)

    def __iter__(self):
        return (pair for pair, leg in self.table.legs.items() if leg.reachable)

    def __len__(self):
        return sum(leg.reachable for leg in self.table.legs.values())


class _TableFreeRealLegs(AbstractMapping):
    """Exact selected-leg lookup; iteration exposes cached pairs only."""
    def __init__(self, provider, rate, terminal_target=None):
        self.provider, self.rate = provider, rate
        self.terminal_target = terminal_target

    def __getitem__(self, pair):
        source, target = pair
        leg = self.provider.leg(source, target,
            target_only=self.terminal_target is not None and target == self.terminal_target)
        if not leg.reachable:
            raise KeyError(pair)
        return RealLegPrimitive(leg.time, leg.energy(self.rate), leg.actual_length,
                                source, target, self.provider.source_sha256["anchors"])

    def __iter__(self):
        return (pair for pair, leg in self.provider.legs.items() if leg.reachable)

    def __len__(self):
        return sum(leg.reachable for leg in self.provider.legs.values())


def site_catalog_digest(sites: Mapping) -> str:
    rows = [(sid, site.anchor_id, list(site.effects))
            for sid, site in sorted(sites.items())]
    return hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()


class TableFreeRealProblem(Problem):
    """Accepted physical transitions fed by source-bound native selected legs.

    This adapter opens no ordered-leg table. Seed and bound admission remain
    separate obligations of the caller before an exact result can be claimed.
    """
    def __init__(self, query: Mapping, sites: Mapping, provider, *,
                 origin_anchor: str, destination_anchor: str,
                 site_catalog_sha256: str,
                 terminal_target_routing: bool = False):
        from .road_provider import TableFreeRoadSelectedLegProvider
        if not isinstance(provider, TableFreeRoadSelectedLegProvider):
            raise ValueError("Table-free native selected-leg provider required")
        if (origin_anchor not in provider.anchor_nodes or
                destination_anchor not in provider.anchor_nodes or
                "edges" in query or "leg_payload_sha256" in query):
            raise ValueError("Table-free query conflicts with selected-road source")
        site_rows = dict(sites)
        if not site_rows or any(
                sid != site.site_id or site.anchor_id not in provider.anchor_nodes or
                not site.effects or not set(site.effects) <= {"C", "S", "CS"}
                for sid, site in site_rows.items()):
            raise ValueError("Invalid table-free Site catalog")
        if site_catalog_digest(site_rows) != site_catalog_sha256:
            raise ValueError("Table-free Site catalog bytes differ from binding")
        declared = {sid: list(site.effects) for sid, site in site_rows.items()}
        for key, expected in (("origin", origin_anchor), ("destination", destination_anchor),
                              ("sites", declared)):
            if key in query and query[key] != expected:
                raise ValueError(f"Query conflicts with table-free {key}")
        configured = dict(query, origin=origin_anchor,
                          destination=destination_anchor, sites=declared)
        self._configure_query(configured)
        self.site_anchors = MappingProxyType({sid: site.anchor_id
                                              for sid, site in site_rows.items()})
        if type(terminal_target_routing) is not bool:
            raise ValueError("Terminal target routing requires an explicit boolean")
        if terminal_target_routing and (
                not callable(getattr(provider.router, "target_edges", None)) or
                getattr(provider.router, "role", None) != "search" or
                getattr(provider.router, "mode", None) != "destination_target"):
            raise ValueError("Explicit search-only destination-target router required")
        self.routing_role = getattr(provider.router, "role", None)
        self._terminal_energy_screen = None
        self.terminal_target_routing = terminal_target_routing
        self.legs = _TableFreeRealLegs(provider, self.rate,
            destination_anchor if terminal_target_routing else None)
        self.provider = provider
        self.site_catalog_sha256 = site_catalog_sha256

    def finish(self, pieces):
        # Screening changes only impossible immediate finishes, never expansion.
        # Independent full replay ignores even an accidentally attached screen.
        if (self.routing_role == 'search' and self._terminal_energy_screen is not None
                and self._terminal_energy_screen.reject(self, pieces)):
            return ()
        return super().finish(pieces)

    def onward_time_lower_bound(self, anchor: str) -> R:
        if anchor not in self.provider.anchor_nodes:
            raise ValueError("Unknown physical anchor")
        return R(0)


class RealProblem(Problem):
    """Physical query over immutable accepted direct legs, never a graph."""
    def __init__(self, query: Mapping, table: ImmutableLegTable, *, leg_cache=None):
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
        if leg_cache is None:
            self.legs=MappingProxyType({pair:RealLegPrimitive(leg.time,leg.energy(self.rate),leg.actual_length,
                                                          *pair,table.payload_sha256)
                                       for pair,leg in table.legs.items() if leg.reachable})
        else:
            from .deployable import SelectedLegCache
            if not isinstance(leg_cache, SelectedLegCache):
                raise ValueError("On-demand real legs require a validated selected-leg cache")
            self.legs=_OnDemandRealLegs(table,self.rate,leg_cache)

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
