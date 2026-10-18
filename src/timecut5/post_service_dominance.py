"""Default-OFF total cut order for trusted, static post-service departures.

This is an explicit solver reducer hook, not a replacement for historical
product-order reduction/certificates. CutPiece cannot authenticate its query
lineage or physical phase: callers must supply completed departure layers from
the exact live admitted problem. Unsupported subclasses are intentionally out
of scope. Native table-free use reuses an existing same-problem runtime guard.
"""
from dataclasses import dataclass, replace
from fractions import Fraction as F
from types import MappingProxyType

from .bounded import Leg, Problem
from .probe import ChargingCurve, Interval, State
from .pwa import CutPiece, _arrangement, reduce_frontier_skyline
from .real_adapter import RealProblem, RealLegPrimitive, TableFreeRealProblem
from . import provenance as prov


VERSION = 'post-service-total-cut-order-v1'
_CLASSES = (Problem, RealProblem, TableFreeRealProblem)
_METHOD_NAMES = ('advance', 'finish', 'initial_piece', 'site_anchor', '_configure_query')
_METHODS = {cls: {name: getattr(cls, name) for name in _METHOD_NAMES}
            for cls in _CLASSES}
_QUANTITIES = ('start', 'initial', 'capacity', 'floor', 'reserve', 'overhead', 'penalty', 'rate')
_FIELDS = ('origin', 'destination', *_QUANTITIES, 'bound', 'sites', 'schedule', 'initial_remaining')
_CURVE_AT = ChargingCurve.at


def _freeze(value):
    """Bounded, type-sensitive semantic snapshot; no graph scan or routing."""
    if value is None or type(value) in (str, int, bool):
        return type(value).__name__, value
    if type(value) is F:
        return 'Fraction', str(value)
    if type(value) in (list, tuple):
        return type(value).__name__, tuple(_freeze(x) for x in value)
    if type(value) is dict and all(type(k) is str for k in value):
        return 'dict', tuple((k, _freeze(value[k])) for k in sorted(value))
    raise TypeError('Plain exact physical model values required')


def _model(problem):
    cls = type(problem)
    if cls not in _CLASSES:
        raise TypeError('Exact built-in Problem, RealProblem or TableFreeRealProblem required')
    for name, method in _METHODS[cls].items():
        if name in vars(problem) or getattr(cls, name) is not method:
            raise ValueError('Built-in physical transition method was replaced')
    if (any(type(getattr(problem, name)) is not F for name in _QUANTITIES) or
            type(problem.bound) is not int or type(problem.initial_remaining) is not int or
            type(problem.origin) is not str or type(problem.destination) is not str or
            type(problem.sites) is not dict):
        raise TypeError('Exact live physical query types required')
    if problem.curve is not None and type(problem.curve) is not ChargingCurve:
        raise TypeError('Exact built-in ChargingCurve required')
    if problem.curve is not None and ('at' in vars(problem.curve) or ChargingCurve.at is not _CURVE_AT):
        raise ValueError('Built-in static charging primitive was replaced')
    reference = Problem.__new__(Problem)
    Problem._configure_query(reference, problem.case)
    if (any(getattr(reference, key) != getattr(problem, key) for key in _FIELDS) or
            reference.curve != problem.curve):
        raise ValueError('Live physical model differs from its actual query')
    anchors = dict(problem.site_anchors)
    if (set(anchors) != set(problem.sites) or
            any(type(x) is not str for x in anchors.values()) or
            any(type(sid) is not str or type(effects) is not tuple or
                any(type(effect) is not str for effect in effects)
                for sid, effects in problem.sites.items())):
        raise ValueError('Physical Site/anchor catalog differs')
    return _freeze(dict(case=problem.case, live={key: getattr(problem, key) for key in _FIELDS},
        site_anchors=anchors, curve=None if problem.curve is None else problem.curve.segments))


def _static_legs(problem):
    expected = Leg if type(problem) is Problem else RealLegPrimitive
    if (type(problem) is Problem and type(problem.legs) is not dict or
            type(problem) is RealProblem and type(problem.legs) is not MappingProxyType):
        raise TypeError('Static selected-leg mapping required; on-demand RealProblem is unsupported')
    result = []
    for pair, leg in sorted(problem.legs.items()):
        if (type(pair) is not tuple or len(pair) != 2 or any(type(x) is not str for x in pair) or
                type(leg) is not expected or type(leg.time) is not F or type(leg.energy) is not F or
                leg.time < 0 or leg.energy < 0):
            raise ValueError('Exact static selected-leg constants required')
        result.append((pair, leg))
    return tuple(result)


@dataclass(frozen=True)
class PostServiceDominanceStatistics:
    enabled: bool
    calls: int
    input_pieces: int
    output_pieces: int
    strong_calls: int
    disabled_fallback_calls: int
    pre_service_fallback_calls: int
    recorded_fallback_calls: int
    unsupported_fallback_calls: int
    arrangement_cells: int
    selected_cells: int
    candidate_visits: int
    strict_primary_discarded: int
    tied_primary_discarded: int
    parent_run_coalesces: int


def _joined(left, right):
    """Exact ordered interval union, preserving a genuinely omitted knot."""
    if left.hi < right.lo or left.hi == right.lo and not (left.right_closed or right.left_closed):
        return None
    hi = max(left.hi, right.hi)
    rc = (left.right_closed if left.hi > right.hi else right.right_closed
          if right.hi > left.hi else left.right_closed or right.right_closed)
    return Interval(left.lo, hi, left.left_closed, rc)


class _PostServiceReducer:
    def __init__(self, problem, enabled, departure_contract, runtime):
        self._enabled = enabled
        self._problem = problem
        self._counts = {key: 0 for key in PostServiceDominanceStatistics.__dataclass_fields__
                        if key != 'enabled'}
        self._model = self._owners = self._legs = self._runtime = None
        if not enabled:
            return
        if not departure_contract:
            raise ValueError('Explicit trusted completed-departure-layer contract required')
        self._model = _model(problem)
        self._owners = (problem.legs, problem.curve, problem.site_anchors)
        if type(problem) is TableFreeRealProblem:
            from .remaining_charge_runtime import RemainingChargeRuntimeV1
            if type(runtime) is not RemainingChargeRuntimeV1 or runtime._problem is not problem:
                raise ValueError('Same live admitted RemainingChargeRuntimeV1 required for table-free use')
            self._runtime = runtime
            self._runtime_binding = runtime.binding_sha256
            self._native_owners = (problem.provider, problem.provider.graph, problem.provider.router,
                                   problem._terminal_energy_screen)
            runtime._check(problem.origin)
        else:
            if runtime is not None:
                raise ValueError('Native runtime is only supported with TableFreeRealProblem')
            self._legs = _static_legs(problem)

    def snapshot(self):
        """Completed successful call counts; detached immutable scalar values."""
        return PostServiceDominanceStatistics(enabled=self._enabled, **self._counts)

    def _commit(self, pieces, result, path, counts=None):
        self._counts['calls'] += 1
        self._counts['input_pieces'] += len(pieces)
        self._counts['output_pieces'] += len(result)
        self._counts[path] += 1
        for key, value in (counts or {}).items():
            self._counts[key] += value
        return result

    def _fallback(self, pieces, path):
        return self._commit(pieces, reduce_frontier_skyline(pieces), path)

    def _check(self, pieces):
        p = self._problem
        if (_model(p) != self._model or any(a is not b for a, b in zip(
                (p.legs, p.curve, p.site_anchors), self._owners))):
            raise ValueError('Admitted live physical model, bound or owner changed')
        if self._runtime is None:
            if _static_legs(p) != self._legs:
                raise ValueError('Admitted static selected legs changed')
        else:
            if p.provider is not self._native_owners[0]:
                raise ValueError('Admitted native provider owner changed')
            owners = (p.provider, p.provider.graph, p.provider.router, p._terminal_energy_screen)
            if (any(a is not b for a, b in zip(owners, self._native_owners)) or
                    self._runtime._problem is not p or self._runtime.binding_sha256 != self._runtime_binding):
                raise ValueError('Admitted native problem/runtime owner changed')
        if not pieces:
            anchor = p.origin
        else:
            if type(pieces[0]) is not CutPiece:
                raise TypeError('Exact CutPiece required')
            state = pieces[0].state
            if type(state) is not State or type(state.anchor) is not str:
                raise TypeError('Exact physical State required')
            anchor = state.anchor
            if state.stop_count > p.bound or state.remaining_schedule > p.initial_remaining:
                raise ValueError('Departure state exceeds the original query or Hmax')
            for piece in pieces:
                if type(piece) is not CutPiece or type(piece.state) is not State or piece.state != state:
                    raise ValueError('Only one complete physical departure state may be reduced')
                d = piece.domain
                if (type(d) is not Interval or type(d.left_closed) is not bool or type(d.right_closed) is not bool or
                        any(type(x) is not F for x in (d.lo, d.hi, piece.slope, piece.intercept, piece.rho)) or
                        type(piece.chi) is not bool or not p.floor <= d.lo <= d.hi <= p.capacity or
                        d.lo == d.hi and not (d.left_closed and d.right_closed)):
                    raise ValueError('Exact cut metadata and physical energy domain required')
                if (type(piece.pi) is not tuple or len(piece.pi) != state.stop_count or
                        any(type(row) is not tuple or len(row) != 2 or
                            any(type(x) is not str for x in row) or
                            row[1] not in p.sites.get(row[0], ()) for row in piece.pi)):
                    raise ValueError('Valid exact Site/effect prefix required')
                services = sum(effect in ('S', 'CS') for _, effect in piece.pi)
                if services != p.initial_remaining - state.remaining_schedule:
                    raise ValueError('Prefix service history disagrees with its physical state')
                if state.stop_count:
                    if p.site_anchor(piece.pi[-1][0]) != anchor or anchor == p.destination:
                        raise ValueError('Completed physical departure anchor required; retag raw Site arrivals first')
                elif (anchor != p.origin or state.remaining_schedule != p.initial_remaining or
                        d != Interval(p.initial, p.initial) or piece.rho != -p.initial or
                        piece.slope*p.initial + piece.intercept != p.start or not piece.chi):
                    raise ValueError('Zero-stop state must be the unchanged initial departure')
        if self._runtime is not None:
            status, _, _ = self._runtime._check(anchor)
            return status == 'active'
        return True

    def __call__(self, pieces):
        pieces = tuple(pieces)
        if not self._enabled:
            return self._fallback(pieces, 'disabled_fallback_calls')
        # Historical product-order certificates keep their original meaning.
        if prov._active.get() is not None or any(getattr(p, '_family', None) is not None for p in pieces):
            return self._fallback(pieces, 'recorded_fallback_calls')
        supported = self._check(pieces)
        if pieces and pieces[0].state.remaining_schedule != 0:
            return self._fallback(pieces, 'pre_service_fallback_calls')
        if not supported:
            return self._fallback(pieces, 'unsupported_fallback_calls')
        counts = dict(arrangement_cells=0, selected_cells=0, candidate_visits=0,
                      strict_primary_discarded=0, tied_primary_discarded=0, parent_run_coalesces=0)
        runs = []
        for cell in _arrangement(pieces):
            counts['arrangement_cells'] += 1
            e = (cell.lo + cell.hi) / 2
            active = [p for p in pieces if p.domain.contains(e)]
            cuts = [p.at(e) for p in active]  # Validate every active inherited callback.
            if not cuts:
                continue
            counts['selected_cells'] += 1
            counts['candidate_visits'] += len(cuts)
            keys = [(cut.tau, not cut.chi, cut.rho, cut.pi, index)
                    for index, cut in enumerate(cuts)]
            winner = min(range(len(cuts)), key=keys.__getitem__)
            for index, key in enumerate(keys):
                if index != winner:
                    counter = 'strict_primary_discarded' if keys[winner][:2] < key[:2] else 'tied_primary_discarded'
                    counts[counter] += 1
            parent = active[winner]
            joined = _joined(runs[-1][1], cell) if runs and runs[-1][0] is parent else None
            if joined is not None:
                runs[-1] = parent, joined
                counts['parent_run_coalesces'] += 1
            else:
                runs.append((parent, cell))
        result = tuple(replace(parent, domain=domain) for parent, domain in runs)
        return self._commit(pieces, result, 'strong_calls', counts)


def make_post_service_reducer(problem, *, enabled=False, completed_departure_layers=False, runtime=None):
    """Bind an optional reducer to one live built-in static physical problem.

    Set completed_departure_layers=True only at the existing same-State,
    completed-next-layer reducer hooks in bounded.py/hierarchy.py. This is a
    trusted ownership/phase contract, not metadata-based lineage authentication.
    Native table-free enabling additionally requires the existing same-problem
    RemainingChargeRuntimeV1. Disabled/recorded/pre-service paths use skyline.
    No stop bound, pruning comparison, solver default or certificate changes.
    """
    if type(enabled) is not bool or type(completed_departure_layers) is not bool:
        raise TypeError('Explicit exact boolean switches required')
    return _PostServiceReducer(problem, enabled, completed_departure_layers, runtime)
