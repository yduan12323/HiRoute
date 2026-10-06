"""Bounded tiny-fixture HIER over exact next-action partitions.

This does not load or claim integration with the frozen real Site hierarchy.
It shares physical/PWA transitions with FLAT; the independent REF remains
separate. Member scans are counted, so pruning is not a scalability claim.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from fractions import Fraction as R
import heapq
from typing import Mapping

from . import invocation_trace as trace
from . import provenance
from .bounded import BoundedResult, Problem, _groups, _replay_problem
from .probe import Witness, terminal
from .pwa import CutPiece, reduce_frontier


@dataclass(frozen=True)
class Region:
    identifier: int
    members: tuple[str, ...]
    children: tuple[Region, ...] = ()


def build_regions(sites, leaf_size: int = 1) -> Region:
    if type(leaf_size) is not int or leaf_size < 1:
        raise ValueError("Positive integer leaf size required")
    members = tuple(sorted(set(sites)))

    def build(members, identifier):
        if len(members) <= leaf_size:
            return Region(identifier, members)
        mid = len(members) // 2
        return Region(identifier, members, (build(members[:mid], 2 * identifier + 1),
                                            build(members[mid:], 2 * identifier + 2)))

    return build(members, 0)


def actions(problem: Problem, region: Region, effect: str, remaining: int):
    if effect in ("S", "CS") and not remaining:
        return ()
    return tuple((site, effect) for site in region.members
                 if problem.site_anchor(site) != problem.destination and effect in problem.sites[site])


def region_bound(problem: Problem, pieces: tuple[CutPiece, ...], region: Region,
                 effect: str) -> tuple[R | None, int]:
    """Admissible directed time bound; strict-charge duration relaxed to zero."""
    if not pieces:
        return None, 0
    state = pieces[0].state
    candidates = actions(problem, region, effect, state.remaining_schedule)
    reachable = [(problem.legs.get((state.anchor, problem.site_anchor(site))),
                  problem.onward_time_lower_bound(problem.site_anchor(site))) for site, _ in candidates]
    reachable = [(incoming, outgoing) for incoming, outgoing in reachable if incoming is not None and outgoing is not None]
    if not reachable:
        return None, len(candidates)
    lower_time = min(p.slope * p.domain.affine_infimum(p.slope)[0] + p.intercept for p in pieces)
    incoming = min(leg.time for leg, _ in reachable)
    outgoing = min(time for _, time in reachable)
    time = lower_time + incoming + problem.overhead
    if effect in ("S", "CS"):
        a, _, duration = problem.schedule
        time = max(a, time) + duration
    value = time + outgoing - problem.start + problem.penalty * (state.stop_count + 1)
    return value, len(candidates)


@dataclass(frozen=True)
class HierarchyResult:
    bounded: BoundedResult
    region_nodes: int
    leaf_actions: int
    bound_member_scans: int
    pruned_regions: int
    equality_nodes_retained: int
    coverage_groups: int
    missing_actions: int
    duplicate_actions: int
    incumbent_source: str
    pruning_audit: tuple[dict, ...]

    def canonical(self):
        return self.bounded.canonical()


def solve_hierarchical(case: Mapping, dominance: bool = True, leaf_size: int = 1,
                       incumbent: Witness | None = None) -> HierarchyResult:
    """Own-search incumbent by default; never obtains the FLAT optimum as a seed."""
    problem = Problem(case)
    root = build_regions(problem.sites, leaf_size)
    return _solve_hierarchical_problem(problem,dominance,root,incumbent)


def _solve_hierarchical_problem(problem: Problem, dominance: bool, root: Region,
                                incumbent: Witness | None = None, *, reducer=None) -> HierarchyResult:
    reducer = reduce_frontier if reducer is None else reducer
    trace.start_run(problem,dominance,root,incumbent)
    incumbent_key = None
    incumbent_witness = None
    source = "none"
    if incumbent is not None:
        if incumbent.state.stop_count > problem.bound:
            raise ValueError("External incumbent lies outside H_ref")
        incumbent_key = _replay_problem(problem, incumbent)
        incumbent_witness = incumbent
        source = "externally_supplied_verified"

    def update_incumbent(pieces,group_id,source_stage):
        nonlocal incumbent_key, incumbent_witness, source
        for piece in pieces:
            # This is one feasible candidate, not a charge quantum or an
            # optimization surrogate. The exact terminal frontier is retained.
            energy = piece.domain.approach_optimizer(piece.slope, R(1))
            witness = piece.at(energy).approach(R(1))
            key = _replay_problem(problem, witness)
            improved=incumbent_key is None or key < incumbent_key
            trace.emit('candidate',group_id=group_id,source=source_stage,
                       family_id=trace.family_id(piece),energy=energy,
                       witness=provenance.witness_dict(witness),key=key,improved=improved)
            if improved:
                incumbent_key = key
                incumbent_witness = witness
                if source != "externally_supplied_verified":
                    source = "own_search"

    initial=trace.invoke("initial",(),{},lambda:(problem.initial_piece(),))
    layer = (initial,)
    terminals = []
    attempted, feasible, maximum = 0, 1, 1
    nodes = leaf_actions = scans = pruned = equality = coverage_groups = 0
    audit = []
    for depth in range(problem.bound + 1):
        group_ids=trace.start_layer(depth,layer)
        for group_id,group in zip(group_ids,layer):
            finished=trace.invoke('finish',group,dict(group_id=group_id,source='layer',advance_id=None),
                                  lambda group=group:problem.finish(group))
            terminals.extend(finished)
            update_incumbent(finished,group_id,'layer')
        if depth == problem.bound:
            trace.emit('layer_end',depth=depth,reason='stop_bound',next_groups=[])
            break
        next_pieces = []
        for group_id,group in zip(group_ids,layer):
            state = group[0].state
            if state.anchor == problem.destination:
                trace.emit('skip_terminal',group_id=group_id)
                continue
            trace.emit('expansion_start',group_id=group_id)
            expected = {a for effect in ("C", "S", "CS")
                        for a in actions(problem, root, effect, state.remaining_schedule)}
            covered = set()
            queue = []
            sequence_number = 0
            query_ids = {}

            def cover(action_set):
                if covered.intersection(action_set):
                    raise AssertionError("Hierarchy covers a next action more than once")
                covered.update(action_set)

            def enqueue(region, effect):
                nonlocal scans, sequence_number
                action_set = actions(problem, region, effect, state.remaining_schedule)
                if not action_set:
                    trace.emit('query',group_id=group_id,region_id=region.identifier,effect=effect,
                               actions=action_set,bound=None,classification='empty_actions',queue_serial=None)
                    return
                bound, paid = region_bound(problem, group, region, effect)
                scans += paid
                if bound is None:
                    trace.emit('query',group_id=group_id,region_id=region.identifier,effect=effect,
                               actions=action_set,bound=None,classification='unreachable',queue_serial=None)
                    cover(action_set)
                    audit.append(dict(reason="unreachable", region=region.identifier,
                                      effect=effect, prefix=group[0].pi, actions=action_set))
                    return
                sequence_number += 1
                query_ids[sequence_number]=trace.emit('query',group_id=group_id,
                    region_id=region.identifier,effect=effect,actions=action_set,bound=bound,
                    classification='queued',queue_serial=sequence_number)
                heapq.heappush(queue, (bound, effect, region.identifier, sequence_number, region))

            for effect in ("C", "S", "CS"):
                enqueue(root, effect)
            while queue:
                bound, effect, _, popped_serial, region = heapq.heappop(queue)
                nodes += 1
                decision=('prune' if incumbent_key is not None and bound>incumbent_key[0] else
                          'split' if region.children else 'leaf')
                trace.emit('pop',group_id=group_id,query_seq=query_ids[popped_serial],
                           decision=decision,incumbent_key=incumbent_key)
                action_set = actions(problem, region, effect, state.remaining_schedule)
                if incumbent_key is not None and bound > incumbent_key[0]:
                    pruned += 1
                    cover(action_set)
                    audit.append(dict(reason="strict_primary", lower_bound=bound,
                                      incumbent_key=incumbent_key, incumbent_witness=incumbent_witness,
                                      region=region.identifier, region_members=region.members,
                                      state=state, effect=effect, prefix=group[0].pi, actions=action_set,
                                      current_frontier=tuple((p.domain.lo,p.domain.hi,p.domain.left_closed,
                                          p.domain.right_closed,p.slope,p.intercept,p.chi,p.rho,p.pi)
                                          for p in group)))
                    continue
                if incumbent_key is not None and bound == incumbent_key[0]:
                    equality += 1
                if region.children:
                    child_actions = [a for child in region.children
                                     for a in actions(problem, child, effect, state.remaining_schedule)]
                    if len(child_actions) != len(set(child_actions)) or set(child_actions) != set(action_set):
                        raise AssertionError("Children are not an exact disjoint action partition")
                    for child in region.children:
                        enqueue(child, effect)
                else:
                    for site, effect in action_set:
                        cover(((site, effect),))
                        leaf_actions += 1
                        attempted += 1
                        output=trace.invoke('advance',group,dict(group_id=group_id,site=site,effect=effect),
                                            lambda:problem.advance(group,site,effect))
                        advance_id=trace.last_invocation()
                        if output:
                            feasible += 1
                            next_pieces.extend(output)
                            finished=trace.invoke('finish',output,
                                dict(group_id=group_id,source='leaf',advance_id=advance_id),
                                lambda:problem.finish(output))
                            update_incumbent(finished,group_id,'leaf')
            if covered != expected:
                raise AssertionError("Hierarchy lost a statically legal next action")
            trace.emit('expansion_end',group_id=group_id,covered_actions=sorted(covered))
            coverage_groups += 1
        if dominance:
            by_state = defaultdict(list)
            for p in next_pieces:
                by_state[p.state].append(p)
            next_pieces = [p for state,values in by_state.items() for p in trace.invoke(
                'reduce',values,dict(depth=depth,state=[state.anchor,state.remaining_schedule,state.stop_count]),
                lambda values=values:reducer(values))]
        maximum = max(maximum, len(next_pieces))
        layer = _groups(next_pieces)
        trace.emit('layer_end',depth=depth,reason='continue' if layer else 'empty',
                   next_groups=[trace.family_ids(group) for group in layer])
        if not layer:
            break
    result = terminal(terminals, problem.destination, problem.reserve, problem.start, problem.penalty)
    if result.witness is not None:
        _replay_problem(problem, result.witness)
    bounded = BoundedResult(result, problem.bound, dominance, attempted, feasible, len(terminals), maximum)
    trace.emit('run_end',canonical=bounded.canonical(),terminal_families=trace.family_ids(terminals),
               terminal_witness=provenance.witness_dict(result.witness) if result.witness else None,
               terminal_family_id=trace.last_witness_family(result.witness))
    return HierarchyResult(bounded, nodes, leaf_actions, scans, pruned, equality,
                           coverage_groups, 0, 0, source, tuple(audit))
