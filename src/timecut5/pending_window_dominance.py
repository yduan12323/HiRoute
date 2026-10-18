"""Default-OFF late-primary dominance at trusted pending-service departures.

This is an explicitly selected solver reducer, not a replacement for historical
product-order certificates. At one exact energy and full State(anchor,1,k), a
strict-primary-worse cut can ignore rho/pi only when every actual prefix clock
is strictly above a-h. Admission and fallback reuse the existing live physical
post-service reducer. Metadata alone does not authenticate lineage or phase.
"""
from dataclasses import dataclass, replace

from . import provenance as prov
from .post_service_dominance import make_post_service_reducer, _joined
from .probe import Interval
from .pwa import _arrangement, _cells, _same_state_energy_skyline


VERSION = 'pending-window-late-primary-order-v1'


@dataclass(frozen=True)
class PendingWindowDominanceStatistics:
    enabled: bool
    post_service_enabled: bool
    calls: int
    input_pieces: int
    output_pieces: int
    strong_calls: int
    disabled_fallback_calls: int
    recorded_fallback_calls: int
    phase_fallback_calls: int
    unsupported_fallback_calls: int
    arrangement_cells: int
    selected_cells: int
    candidate_visits: int
    product_discarded: int
    late_primary_discarded: int
    kept_candidate_visits: int
    threshold_roots: int
    added_threshold_knots: int
    parent_run_coalesces: int


def _pending_arrangement(pieces, threshold):
    """Historical arrangement plus every affine tau=a-h root, exactly."""
    original = _arrangement(pieces)
    if not original:
        return (), 0, 0
    knots = {cell.lo for cell in original} | {cell.hi for cell in original}
    roots = set()
    for piece in pieces:
        if piece.slope:
            energy = (threshold-piece.intercept)/piece.slope
            if piece.domain.lo <= energy <= piece.domain.hi:
                roots.add(energy)
    added = len(roots-knots)
    knots.update(roots)
    return _cells(Interval(min(knots), max(knots)), knots), len(roots), added


class _PendingWindowReducer:
    def __init__(self, problem, enabled, post_service_enabled, departure_contract, runtime):
        self._enabled = enabled
        self._post_service_enabled = post_service_enabled
        self._counts = {name: 0 for name in PendingWindowDominanceStatistics.__dataclass_fields__
                        if name not in ('enabled', 'post_service_enabled')}
        # An enabled existing reducer supplies the unchanged model/runtime guard.
        # Its r=0 optimization is used only when explicitly selected below.
        admitted = make_post_service_reducer(problem, enabled=enabled or post_service_enabled,
            completed_departure_layers=departure_contract, runtime=runtime)
        self._guard = admitted
        self._fallback_reducer = (admitted if post_service_enabled else
                                 make_post_service_reducer(problem))

    def snapshot(self):
        """New-feature counts only; detached immutable scalar values."""
        return PendingWindowDominanceStatistics(enabled=self._enabled,
            post_service_enabled=self._post_service_enabled, **self._counts)

    def post_service_snapshot(self):
        """Unchanged old counters, only for calls actually delegated to fallback."""
        return self._fallback_reducer.snapshot()

    def _commit(self, pieces, result, path, counts=None):
        self._counts['calls'] += 1
        self._counts['input_pieces'] += len(pieces)
        self._counts['output_pieces'] += len(result)
        self._counts[path] += 1
        for name, value in (counts or {}).items():
            self._counts[name] += value
        return result

    def _fallback(self, pieces, path):
        result = self._fallback_reducer(pieces)
        return self._commit(pieces, result, path)

    def __call__(self, pieces):
        pieces = tuple(pieces)
        if not self._enabled:
            return self._fallback(pieces, 'disabled_fallback_calls')
        # Never relabel or strip recorded families to enable stronger deletion.
        if prov._active.get() is not None or any(getattr(p, '_family', None) is not None for p in pieces):
            return self._fallback(pieces, 'recorded_fallback_calls')
        supported = self._guard._check(pieces)
        if not pieces or pieces[0].state.remaining_schedule != 1:
            return self._fallback(pieces, 'phase_fallback_calls')
        if not supported:
            return self._fallback(pieces, 'unsupported_fallback_calls')
        problem = self._guard._problem
        threshold = problem.schedule[0]-problem.overhead
        cells, roots, added = _pending_arrangement(pieces, threshold)
        counts = dict(arrangement_cells=0, selected_cells=0, candidate_visits=0,
            product_discarded=0, late_primary_discarded=0, kept_candidate_visits=0,
            threshold_roots=roots, added_threshold_knots=added, parent_run_coalesces=0)
        runs = []
        for cell in cells:
            counts['arrangement_cells'] += 1
            energy = (cell.lo+cell.hi)/2
            active = [p for p in pieces if p.domain.contains(energy)]
            cuts = tuple(p.at(energy) for p in active)  # Validate every callback.
            if not cuts:
                continue
            counts['selected_cells'] += 1
            counts['candidate_visits'] += len(cuts)
            primary = min((c.tau, not c.chi) for c in cuts)
            skyline_ids = {id(c) for c in _same_state_energy_skyline(cuts)}
            for parent, cut in zip(active, cuts):
                if id(cut) not in skyline_ids:
                    counts['product_discarded'] += 1
                    continue
                late = cut.tau > threshold or cut.tau == threshold and not cut.chi
                if late and (cut.tau, not cut.chi) > primary:
                    counts['late_primary_discarded'] += 1
                    continue
                counts['kept_candidate_visits'] += 1
                # Only an identical original parent and connected exact domain
                # may join. Another parent's intervening run interrupts joining.
                joined = _joined(runs[-1][1], cell) if runs and runs[-1][0] is parent else None
                if joined is not None:
                    runs[-1] = parent, joined
                    counts['parent_run_coalesces'] += 1
                else:
                    runs.append((parent, cell))
        result = tuple(replace(parent, domain=domain) for parent, domain in runs)
        return self._commit(pieces, result, 'strong_calls', counts)


def make_pending_window_reducer(problem, *, enabled=False, post_service_enabled=False,
                                completed_departure_layers=False, runtime=None):
    """Select new pending-window and existing post-service features explicitly.

    Both flags default OFF, preserving the historical skyline. Enabling either
    requires the existing same-live-problem completed-departure admission and,
    for TableFreeRealProblem, its admitted RemainingChargeRuntimeV1. The r=0,
    disabled, recorded and unsupported cases delegate to the explicitly selected
    old reducer. snapshot() and post_service_snapshot() keep counter meanings
    separate. Use only existing completed-next-layer full-State solver hooks.
    """
    if type(enabled) is not bool or type(post_service_enabled) is not bool:
        raise TypeError('Explicit exact boolean switches required')
    return _PendingWindowReducer(problem, enabled, post_service_enabled,
                                 completed_departure_layers, runtime)
