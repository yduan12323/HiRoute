"""Explicit exact interval sweep for the unchanged lower-envelope arrangement.

This is an operator selector, not a new frontier reducer or pruning rule.
The historical selector remains the default and handles all recorded calls.
"""
from contextvars import ContextVar
from dataclasses import dataclass
import heapq
from itertools import combinations

from .probe import Interval
from . import provenance as prov


_active = ContextVar("timecut5_envelope_sweep", default=None)


@dataclass(frozen=True)
class EnvelopeSweepStatistics:
    enabled: bool
    calls: int
    completed_calls: int
    input_pieces: int
    arrangement_cells: int
    selected_cells: int
    pair_tests: int
    relation_intervals: int
    event_updates: int
    heap_pushes: int
    heap_pops: int
    baseline_parent_visits: int
    recorded_fallback_calls: int
    max_input_pieces: int
    max_arrangement_cells: int


class EnvelopeSweep:
    """Single-use, context-local opt-in; exact booleans and scalar counters.

    Distinct nested contexts restore their predecessors, including on errors.
    Child tasks inherit Python context variables; use distinct contexts when
    separate accounting is wanted. No-context calls retain historical behavior.
    """
    def __init__(self, *, enabled=False):
        if type(enabled) is not bool:
            raise ValueError("Envelope sweep requires an exact boolean")
        self._enabled = enabled
        self._used = False
        self._token = None
        self._counts = {name: 0 for name in EnvelopeSweepStatistics.__dataclass_fields__
                        if name != "enabled"}

    @property
    def enabled(self):
        return self._enabled

    def snapshot(self):
        return EnvelopeSweepStatistics(enabled=self.enabled, **self._counts)

    def __enter__(self):
        if self._used:
            raise ValueError("Envelope sweep context is single-use")
        self._used = True
        self._token = _active.set(self)
        return self

    def __exit__(self, *exception):
        _active.reset(self._token)
        self._token = None

    def _begin(self, size, cells, *, recorded=False):
        counts = self._counts
        counts["calls"] += 1
        counts["input_pieces"] += size
        counts["arrangement_cells"] += cells
        counts["max_input_pieces"] = max(counts["max_input_pieces"], size)
        counts["max_arrangement_cells"] = max(counts["max_arrangement_cells"], cells)
        counts["recorded_fallback_calls"] += int(recorded)

    def _baseline(self, size, cells, selected):
        self._counts["completed_calls"] += 1
        self._counts["selected_cells"] += selected
        self._counts["baseline_parent_visits"] += size*cells


def _better_interval(overlap, slope, intercept, owns_tie):
    """Clip overlap to slope*energy+intercept < 0, or <= 0 at owned ties."""
    if slope == 0:
        return overlap if intercept < 0 or intercept == 0 and owns_tie else None
    lo, hi = overlap.lo, overlap.hi
    lc, rc = overlap.left_closed, overlap.right_closed
    root = -intercept / slope
    if slope > 0:
        if root < hi:
            hi, rc = root, owns_tie
        elif root == hi:
            rc = rc and owns_tie
    else:
        if root > lo:
            lo, lc = root, owns_tie
        elif root == lo:
            lc = lc and owns_tie
    return (Interval(lo, hi, lc, rc)
            if lo < hi or lo == hi and lc and rc else None)


def _add_interval(events, interval, support, target):
    """Before singleton: closed starts/open ends; after: the converse."""
    if interval is None:
        return
    events.setdefault(interval.lo, [[], []])[0 if interval.left_closed else 1].append(
        (support, target, 1))
    events.setdefault(interval.hi, [[], []])[1 if interval.right_closed else 0].append(
        (support, target, -1))


def select_envelope(pieces, cells, policy):
    """Select identical original parents on the supplied historical cells.

    Pair relations are active only where both parent domains contain energy.
    Their total-order minimum is the unique active zero-indegree parent.
    All events at one endpoint phase are applied before selecting a winner.
    """
    counts = policy._counts
    events = {}
    for i, piece in enumerate(pieces):
        _add_interval(events, piece.domain, True, i)
    for i, j in combinations(range(len(pieces)), 2):
        counts["pair_tests"] += 1
        left, right = pieces[i], pieces[j]
        overlap = left.domain.intersect(right.domain)
        if overlap is None:
            continue
        slope, intercept = left.slope-right.slope, left.intercept-right.intercept
        owns_tie = (not left.chi, i) < (not right.chi, j)
        for delta_m, delta_b, tie, target in ((slope, intercept, owns_tie, j),
                                             (-slope, -intercept, not owns_tie, i)):
            interval = _better_interval(overlap, delta_m, delta_b, tie)
            if interval is not None:
                counts["relation_intervals"] += 1
                _add_interval(events, interval, False, target)
    # Missing events would invalidate a sweep. This is an invariant failure,
    # never a zero/unreachable relaxation or a reason to drop a cell.
    knots = {cell.lo for cell in cells if cell.lo == cell.hi}
    if not set(events) <= knots:
        raise AssertionError("Envelope event is absent from the original arrangement")
    active = [False]*len(pieces)
    better = [0]*len(pieces)
    versions = [0]*len(pieces)
    heap = []
    active_count = 0

    def apply(actions):
        nonlocal active_count
        dirty = set()
        for support, target, delta in actions:
            counts["event_updates"] += 1
            dirty.add(target)
            if support:
                if active[target] != (delta == -1):
                    raise AssertionError("Invalid envelope support event")
                active[target] = delta == 1
                active_count += delta
            else:
                better[target] += delta
        for target in dirty:
            if better[target] < 0:
                raise AssertionError("Negative better-parent count")
            versions[target] += 1
            if active[target] and better[target] == 0:
                heapq.heappush(heap, (target, versions[target]))
                counts["heap_pushes"] += 1

    def winner():
        while heap:
            target, version = heap[0]
            if active[target] and better[target] == 0 and versions[target] == version:
                return target
            heapq.heappop(heap)
            counts["heap_pops"] += 1
        if active_count:
            raise AssertionError("Active envelope has no exact minimum")
        return None

    first_parent = {}
    for i, piece in enumerate(pieces):
        first_parent.setdefault(id(piece), i)
    choices = []
    for cell in cells:
        singleton = cell.lo == cell.hi
        actions = events.get(cell.lo, ((), ())) if singleton else ((), ())
        if singleton:
            apply(actions[0])
        index = winner()
        if index is not None:
            choices.append((first_parent[id(pieces[index])], cell))
        if singleton:
            apply(actions[1])
    if active_count or any(better):
        raise AssertionError("Envelope sweep did not drain its finite intervals")
    result = prov.select_many(pieces, choices, "union")
    prov.batch("union", pieces, result)
    counts["selected_cells"] += len(result)
    counts["completed_calls"] += 1
    return result
