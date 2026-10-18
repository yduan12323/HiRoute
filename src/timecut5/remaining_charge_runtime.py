"""Explicit v1 admission for conditional remaining-charge objective bounds.

This module has no solver hook, pruning decision, upper bound or depth cutoff.
The caller must supply trusted solver-produced frontiers from this exact live
problem. CutPiece does not authenticate query lineage: admitting the physical
model and road potentials does NOT certify arbitrary caller-created clocks.
Combine a returned complete primary bound with existing bounds by max. Any
future pruning must use strict > and retain the original Hmax/domain.
"""
from dataclasses import dataclass
from fractions import Fraction as F
import json

from .bounded import Problem
from .probe import ChargingCurve, Interval, State
from .pwa import CutPiece
from .real_adapter import TableFreeRealProblem, _TableFreeRealLegs, site_catalog_digest
from .real_legs import RealSite
from .remaining_charge_bound import (remaining_charge_primary_lower_bound,
                                     complete_route_primary_lower_bound)
from . import remaining_charge_bound
from .road_provider import TableFreeRegionBoundProvider
from .terminal_energy import (TerminalEnergyScreen, RoutingHistoryGuard,
                              canonical, digest, hash_id, file_digest)


@dataclass(frozen=True)
class SuffixPotentialV1:
    """Versioned accessor result; None is an explicit disabled relaxation."""
    quantity: str
    status: str
    lower_bound: F | None
    binding_sha256: str

    def __post_init__(self):
        if self.quantity not in ('energy', 'time'):
            raise ValueError('Unknown suffix potential quantity')
        _result_value(self.status, self.lower_bound, ('disabled_unsupported',))
        if self.lower_bound is not None and self.lower_bound < 0:
            raise ValueError('Suffix potential must be nonnegative')
        hash_id(self.binding_sha256)


def _result_value(status, value, disabled):
    if status == 'active':
        if type(value) is not F:
            raise TypeError('Active bound must be an exact Fraction')
    elif status not in disabled or value is not None:
        raise ValueError('Disabled bound requires a known status and None')


@dataclass(frozen=True)
class RemainingChargeBoundResultV1:
    """Conditional primary objective infimum, not a feasibility certificate."""
    status: str
    primary_lower_bound: F | None
    binding_sha256: str

    def __post_init__(self):
        _result_value(self.status, self.primary_lower_bound,
                      ('disabled_unsupported', 'inactive_no_charging_curve'))
        hash_id(self.binding_sha256)


def _typed(value):
    """Unambiguous exact snapshots, including rational input representation."""
    if value is None or type(value) in (bool, int, str):
        return [type(value).__name__, value]
    if type(value) is F:
        return ['Fraction', str(value)]
    if type(value) in (list, tuple):
        return [type(value).__name__, [_typed(item) for item in value]]
    if type(value) is dict and all(type(key) is str for key in value):
        return ['dict', [[key, _typed(value[key])] for key in sorted(value)]]
    raise TypeError('Exact query/runtime snapshot requires plain exact values')


_RATIONAL_FIELDS = ('start', 'initial', 'capacity', 'floor', 'reserve',
                    'overhead', 'penalty', 'rate')
_QUERY_FIELDS = ('origin', 'destination', *_RATIONAL_FIELDS, 'bound', 'sites',
                'schedule', 'initial_remaining')
_ADMISSION = object()


def _model_payload(problem):
    """Check current values against the actual query, not just a query hash."""
    if type(problem) is not TableFreeRealProblem:
        raise TypeError('Exact TableFreeRealProblem required')
    if any(type(getattr(problem, key)) is not F for key in _RATIONAL_FIELDS):
        raise TypeError('Live physical quantities must be exact Fractions')
    if (type(problem.bound) is not int or type(problem.initial_remaining) is not int or
            type(problem.origin) is not str or type(problem.destination) is not str or
            type(problem.sites) is not dict or
            any(type(sid) is not str or type(effects) is not tuple or
                any(type(effect) is not str for effect in effects)
                for sid, effects in problem.sites.items()) or
            problem.schedule is not None and (type(problem.schedule) is not tuple or
                any(type(value) is not F for value in problem.schedule))):
        raise TypeError('Unexpected live physical query field types')
    if problem.curve is not None and type(problem.curve) is not ChargingCurve:
        raise TypeError('Exact shared ChargingCurve required')
    if problem.curve is not None and (type(problem.curve.segments) is not tuple or
            any(type(row) is not tuple or len(row) != 4 or
                any(type(value) is not F for value in row) for row in problem.curve.segments)):
        raise TypeError('Exact shared charging segment quantities required')
    reference = Problem.__new__(Problem)
    reference._configure_query(problem.case)
    if (any(getattr(reference, key) != getattr(problem, key) for key in _QUERY_FIELDS) or
            reference.curve != problem.curve):
        raise ValueError('Live physical query differs from its actual case')
    if (set(problem.site_anchors) != set(problem.sites) or
            any(type(anchor) is not str or anchor not in problem.provider.anchor_nodes
                for anchor in problem.site_anchors.values()) or
            problem.origin not in problem.provider.anchor_nodes or
            problem.destination not in problem.provider.anchor_nodes):
        raise ValueError('Physical anchor/Site domain differs')
    sites = {sid: RealSite(sid, problem.site_anchors[sid], effects)
             for sid, effects in problem.sites.items()}
    if site_catalog_digest(sites) != problem.site_catalog_sha256:
        raise ValueError('Actual Site/effect catalog differs from its binding')
    if (type(problem.terminal_target_routing) is not bool or
            problem.routing_role != 'search' or
            problem.provider.router.mode not in ('full', 'destination_target') or
            problem.terminal_target_routing != (problem.provider.router.mode == 'destination_target') or
            type(problem.legs) is not _TableFreeRealLegs or
            problem.legs.provider is not problem.provider or problem.legs.rate != problem.rate or
            type(problem.legs.rate) is not F or
            problem.legs.terminal_target != (problem.destination if problem.terminal_target_routing else None)):
        raise ValueError('Live selected-leg adapter/search policy differs')
    values = {key: getattr(problem, key) for key in _QUERY_FIELDS}
    values.update(site_anchors=dict(problem.site_anchors),
        site_catalog_sha256=problem.site_catalog_sha256,
        curve_segments=None if problem.curve is None else problem.curve.segments,
        terminal_target_routing=problem.terminal_target_routing,
        routing_role=problem.routing_role)
    return dict(case=_typed(problem.case), runtime=_typed(values))


class RemainingChargeRuntimeV1:
    """Live same-problem admission, with explicit trusted-frontier boundary.

    Validation is O(anchors + Sites + curve segments + pieces), with no graph
    scan, routing, cache admission, or source-cache policy change per call.
    This is intentionally opt-in and is not registered with any search loop.
    """
    def __init__(self, token, problem, energy_screen, travel_provider):
        if token is not _ADMISSION:
            raise ValueError('Use admit_remaining_charge_runtime')
        if type(energy_screen) is not TerminalEnergyScreen:
            raise TypeError('Authenticated TerminalEnergyScreen required')
        if travel_provider is not None and type(travel_provider) is not TableFreeRegionBoundProvider:
            raise TypeError('Exact TableFreeRegionBoundProvider or None required')
        model = _model_payload(problem)
        if (problem._terminal_energy_screen is not energy_screen or
                problem.provider is not energy_screen.provider or
                type(energy_screen.history) is not RoutingHistoryGuard or
                travel_provider is not None and travel_provider.leg_provider is not problem.provider):
            raise ValueError('Same live physical problem and guarded provider required')
        self._problem, self._screen, self._travel = problem, energy_screen, travel_provider
        self._owners = (problem.provider, problem.provider.graph, problem.provider.router,
                        energy_screen.history, energy_screen.kernel, problem.legs, problem.curve)
        self._model_bytes = canonical(model)
        self._original_hmax = problem.bound
        self._alpha = None if problem.curve is None else min(row[2] for row in problem.curve.segments)
        # Admission authenticates pinned artifacts once; subsequent accessor
        # checks preserve the existing mapped-native/FP/cache-history guards.
        native = problem.provider.router.verify_artifact()
        kernel = energy_screen.kernel.artifact.authenticate()
        e, t = self._potentials(problem.origin)
        self._potential_bindings = (e.binding_sha256, None if t is None else t.binding_sha256)
        self._binding_bytes = canonical(dict(schema='hiroute.remaining_charge_runtime.v1',
            model=model, global_min_charge_seconds_per_kwh=None if self._alpha is None else str(self._alpha),
            original_hmax=self._original_hmax, potential_bindings=list(self._potential_bindings),
            provider_sources=problem.provider.source_sha256,
            graph_sha256=digest(problem.provider.graph.identity_bytes),
            native_artifact_sha256=native['artifact_identity_sha256'],
            energy_artifact_sha256=kernel['artifact_identity_sha256'],
            routing_mode=problem.provider.router.mode,
            routing_history=energy_screen.history.native,
            cache_policy=list(energy_screen.history.cache_policy),
            runtime_source_sha256=file_digest(__file__),
            inequality_source_sha256=file_digest(remaining_charge_bound.__file__),
            energy_contract='signed per-leg beta-weighted potentials telescope across native label resets',
            travel_relaxation='certified_integer_ALT' if t is not None else 'explicit_zero',
            frontier_contract='trusted_live_solver_frontier_same_problem_not_authenticated_by_CutPiece'))
        self._binding_sha256 = digest(self._binding_bytes)

    @property
    def binding(self):
        """Detached readable receipt, not authority to restore a live runtime."""
        return json.loads(self._binding_bytes)

    @property
    def binding_sha256(self):
        return self._binding_sha256

    @property
    def original_hmax(self):
        return self._original_hmax

    def _potentials(self, anchor):
        e = self._screen.certified_suffix_energy_v1(self._problem, anchor)
        t = None if self._travel is None else self._travel.certified_suffix_time_v1(self._problem, anchor)
        return e, t

    def _check(self, anchor):
        p, screen = self._problem, self._screen
        owners = (p.provider, p.provider.graph, p.provider.router, screen.history,
                  screen.kernel, p.legs, p.curve)
        if (any(actual is not original for actual, original in zip(owners, self._owners)) or
                p._terminal_energy_screen is not screen or canonical(_model_payload(p)) != self._model_bytes):
            raise ValueError('Admitted runtime owner/query/curve changed')
        e, t = self._potentials(anchor)
        if (e.binding_sha256, None if t is None else t.binding_sha256) != self._potential_bindings:
            raise ValueError('Admitted suffix potential binding changed')
        if e.status != 'active' or t is not None and t.status != 'active':
            return 'disabled_unsupported', None, None
        if self._alpha is None:
            return 'inactive_no_charging_curve', None, None
        return 'active', e.lower_bound, F(0) if t is None else t.lower_bound

    def _result(self, status, value=None):
        return RemainingChargeBoundResultV1(status, value, self.binding_sha256)

    def evaluate_group(self, pieces):
        """Bound trusted same-problem prefix pieces; never authenticate clocks."""
        pieces = tuple(pieces)
        if not pieces:
            raise ValueError('Nonempty trusted same-state frontier required')
        if type(pieces[0]) is not CutPiece:
            raise TypeError('Exact CutPiece required')
        state = pieces[0].state
        if type(state) is not State or type(state.anchor) is not str:
            raise TypeError('Exact physical State required')
        for piece in pieces:
            if (type(piece) is not CutPiece or type(piece.state) is not State or
                    piece.state != state or type(piece.domain) is not Interval):
                raise ValueError('No mixed-state or nonphysical frontier')
            if (any(type(value) is not F for value in
                    (piece.domain.lo, piece.domain.hi, piece.slope, piece.intercept)) or
                    type(piece.domain.left_closed) is not bool or type(piece.domain.right_closed) is not bool):
                raise TypeError('Exact frontier quantities and interval flags required')
            if (piece.domain.lo < self._problem.floor or piece.domain.hi > self._problem.capacity or
                    piece.domain.lo > piece.domain.hi or piece.domain.lo == piece.domain.hi and
                    not (piece.domain.left_closed and piece.domain.right_closed)):
                raise ValueError('Frontier energy outside the physical domain')
        if (state.stop_count > self.original_hmax or
                state.remaining_schedule > self._problem.initial_remaining):
            raise ValueError('Frontier discrete state outside original query domain')
        status, energy, travel = self._check(state.anchor)
        if status != 'active':
            return self._result(status)
        p = self._problem
        lower = remaining_charge_primary_lower_bound(pieces,
            remaining_energy_lower=energy, remaining_time_lower=travel,
            terminal_reserve=p.reserve, min_charge_seconds_per_kwh=self._alpha,
            start_time=p.start, stop_penalty=p.penalty)
        return self._result(status, lower)

    def whole_route_lower_bound(self, total_stops):
        """Conditional fixed-H bound; preserve Hmax and make no cutoff claim."""
        if type(total_stops) is not int or not 0 <= total_stops <= self.original_hmax:
            raise ValueError('Total stops must be within the original Hmax')
        p = self._problem
        status, energy, travel = self._check(p.origin)
        if status != 'active':
            return self._result(status)
        lower = complete_route_primary_lower_bound(total_stops=total_stops,
            initial_energy=p.initial, origin_energy_lower=energy, origin_time_lower=travel,
            terminal_reserve=p.reserve, min_charge_seconds_per_kwh=self._alpha,
            stop_overhead=p.overhead, stop_penalty=p.penalty)
        return self._result(status, lower)


def admit_remaining_charge_runtime(problem, *, energy_screen, travel_provider=None):
    """Explicitly admit v1 physical/potential bindings, without enabling search."""
    return RemainingChargeRuntimeV1(_ADMISSION, problem, energy_screen, travel_provider)
