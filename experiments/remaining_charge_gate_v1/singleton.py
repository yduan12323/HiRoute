"""Explicit experiment-only FLAT adapter for the certified bound family.

Nothing installs this adapter automatically. Callers pass ``singleton_bound``
to FLAT explicitly and admit the runtime against that same live problem. The
frontier must be trusted solver-produced pieces from that problem; runtime
admission does not authenticate arbitrary caller-created clocks.

This adapter makes no feasibility, pruning, attainment, or depth decision.
The engine retains its original Hmax and strict ``lower > upper`` comparison.
"""
from fractions import Fraction as F


POLICY_SCHEMA = 'hiroute.remaining_charge_singleton.v1'


class RemainingChargeSingletonBound:
    """Max the original singleton bound with the same two HIER relaxations.

    Original ``None`` is authoritative and returned before evaluating added
    bounds. Missing finite ALT terms are not interpreted here as unreachable.
    Explicit unsupported/inactive runtime status disables only this addition;
    malformed values, ownership changes and integrity errors fail closed.
    """

    def __init__(self, original, problem, *, runtime=None):
        self.original = original
        self.problem = problem
        self.runtime = runtime
        self._counters = dict(calls=0, original_none=0, active_calls=0,
                              disabled_calls=0, strengthened_calls=0)

    def singleton_bound(self, problem, pieces, site, effect):
        if problem is not self.problem:
            raise ValueError('Remaining-charge singleton problem owner changed')
        self._counters['calls'] += 1
        lower = self.original.singleton_bound(problem, pieces, site, effect)
        if lower is None:
            self._counters['original_none'] += 1
            return None
        if self.runtime is None:
            return lower
        if type(lower) is not F:
            raise TypeError('Exact original singleton lower bound required')
        if not pieces:
            raise ValueError('Nonempty trusted frontier required for singleton bound')
        next_stops = pieces[0].state.stop_count + 1
        if next_stops > problem.bound:
            raise ValueError('Next action exceeds unchanged declared Hmax')
        prefix = self.runtime.evaluate_group(pieces)
        whole = self.runtime.whole_route_lower_bound(next_stops)
        values = [lower]
        for result in (prefix, whole):
            if result.binding_sha256 != self.runtime.binding_sha256:
                raise ValueError('Remaining-charge runtime result binding differs')
            if result.status == 'active':
                if type(result.primary_lower_bound) is not F:
                    raise TypeError('Exact active lower bound required')
                values.append(result.primary_lower_bound)
            elif (result.status not in ('disabled_unsupported', 'inactive_no_charging_curve')
                  or result.primary_lower_bound is not None):
                raise ValueError('Unknown remaining-charge disabled result')
        if prefix.status != 'active' or whole.status != 'active':
            self._counters['disabled_calls'] += 1
            return lower
        self._counters['active_calls'] += 1
        combined = max(values)
        self._counters['strengthened_calls'] += combined > lower
        return combined

    def statistics_snapshot(self):
        """Detached constant-field counts of calls, never actual prune counts.

        Calls are counted on entry, so an exception/censored invocation need
        not appear in a completed category. No trace or callback is retained.
        """
        return dict(schema=POLICY_SCHEMA, runtime_enabled=self.runtime is not None,
                    **self._counters)
