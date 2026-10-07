"""Streaming arithmetic over *already independently checked* suffix results.

This helper grants no certificate authority.  It neither checks LP witnesses nor
proves language coverage: callers must check each regime and bind its ordered ID
to the intended finite language.  A summary covers exactly ``[start, end)`` and
retains canonical half-open runs of tied IDs, never the records or expanded IDs.
Space is proportional to the number of tie runs (which can still be linear).
"""
from copy import deepcopy

from .independent_model import api, exact_json, rational, require, same


SCHEMA = 'suffix5-stream-aggregate-v1'
EXCLUSIONS = ('graph_unreachable', 'closed_infeasible', 'strict_infeasible')
RANGES = ('primary_tied_regime_ranges', 'secondary_tied_regime_ranges',
          'winning_regime_ranges')


def _parse_result(row, *, summary=False):
    """Independent implementation of the result algebra, without checker calls."""
    exact_json(row)
    require(type(row) is dict, 'stream_result_type')
    fields = {name: {'status'} for name in EXCLUSIONS}
    fields.update(
        primary_unattained={'status', 'primary_infimum'},
        secondary_unattained={'status', 'J', 'secondary_infimum'},
        attained_optimum={'status', 'J', 'Q_total', 'H', 'site_action_tuple', 'lex_key'})
    if summary:
        fields = {name: keys for name, keys in fields.items() if name not in EXCLUSIONS}
        fields['empty_restricted_family'] = {'status'}
    status = row.get('status')
    require(type(status) is str and status in fields and set(row) == fields[status],
            'stream_result_fields')
    if status in (*EXCLUSIONS, 'empty_restricted_family'):
        return None, None, None
    J = rational(row['primary_infimum'] if status == 'primary_unattained' else row['J'])
    if status == 'primary_unattained':
        return J, None, None
    Q = rational(row['secondary_infimum'] if status == 'secondary_unattained' else row['Q_total'])
    if status == 'secondary_unattained':
        return J, Q, None
    H, pi = row['H'], row['site_action_tuple']
    require(type(H) is int and H >= 0 and type(pi) is list and len(pi) == H,
            'stream_H_or_pi_type')
    require(all(type(pair) is list and len(pair) == 2 and type(pair[0]) is str
                and type(pair[1]) is str and pair[1] in ('C', 'S', 'CS') for pair in pi),
            'stream_pi_action')
    same(row['lex_key'], [str(J), str(Q), H, pi], 'stream_lex_key')
    return J, Q, (H, tuple(map(tuple, pi)))


def _index(value):
    require(type(value) is int and value >= 0, 'stream_index_type_or_range')


def _append(target, incoming):
    """Append disjoint ordered runs, coalescing the single possible seam."""
    if not incoming:
        return
    first = 0
    if target and target[-1][1] == incoming[0][0]:
        target[-1][1] = incoming[0][1]
        first = 1
    target.extend(pair[:] for pair in incoming[first:])


def _subset(inner, outer):
    cursor = 0
    for lo, hi in inner:
        while cursor < len(outer) and outer[cursor][1] <= lo:
            cursor += 1
        if cursor == len(outer) or not outer[cursor][0] <= lo < hi <= outer[cursor][1]:
            return False
    return True


def _validate_summary(summary):
    exact_json(summary)
    require(type(summary) is dict and set(summary) == {'schema', 'start', 'end', 'result', 'audit'},
            'stream_summary_fields')
    same(summary['schema'], SCHEMA, 'stream_summary_schema')
    start, end = summary['start'], summary['end']
    _index(start)
    _index(end)
    require(start <= end, 'stream_reversed_interval')
    parsed = _parse_result(summary['result'], summary=True)
    audit = summary['audit']
    require(type(audit) is dict and set(audit) == {*RANGES, 'exclusion_counts'},
            'stream_audit_fields')
    counts = audit['exclusion_counts']
    require(type(counts) is dict and set(counts) == set(EXCLUSIONS)
            and all(type(count) is int and count >= 0 for count in counts.values()),
            'stream_exclusion_counts')
    candidates = end-start-sum(counts.values())
    require(candidates >= 0, 'stream_exclusion_count_overflow')
    lengths = []
    for name in RANGES:
        runs = audit[name]
        require(type(runs) is list, 'stream_ranges_type')
        previous = None
        length = 0
        for pair in runs:
            require(type(pair) is list and len(pair) == 2, 'stream_range_pair')
            lo, hi = pair
            _index(lo)
            _index(hi)
            require(start <= lo < hi <= end, 'stream_range_bounds')
            require(previous is None or previous < lo, 'stream_ranges_not_canonical')
            previous = hi
            length += hi-lo
        lengths.append(length)
    primary, secondary, winners = (audit[name] for name in RANGES)
    require(_subset(secondary, primary) and _subset(winners, secondary), 'stream_tie_subset')
    J, Q, key = parsed
    require(bool(candidates) == (J is not None) and lengths[0] <= candidates,
            'stream_candidate_count_mismatch')
    require(bool(primary) == (J is not None) and bool(secondary) == (Q is not None)
            and bool(winners) == (key is not None), 'stream_result_tie_mismatch')
    return parsed


class StreamAggregator:
    """Accumulate increasing, gap-free regime IDs without retaining input rows.

    ``add(id, result)`` accepts only one of the six checked regime statuses.
    Failed input validation leaves the accumulator unchanged.  ``summary()``
    returns detached JSON data suitable for ``merge_summaries``.
    """

    @api
    def __init__(self, start=0):
        _index(start)
        self.start = self.end = start
        self._J = self._Q = self._key = None
        self._result = dict(status='empty_restricted_family')
        self._ranges = [[], [], []]
        self._counts = {name: 0 for name in EXCLUSIONS}

    def _consume(self, parsed, result, ranges):
        J, Q, key = parsed
        if J is None or (self._J is not None and J > self._J):
            return
        if self._J is None or J < self._J:
            self._J, self._Q, self._key = J, None, None
            self._result = dict(status='primary_unattained', primary_infimum=str(J))
            self._ranges = [[], [], []]
        _append(self._ranges[0], ranges[0])
        if Q is None or (self._Q is not None and Q > self._Q):
            return
        if self._Q is None or Q < self._Q:
            self._Q, self._key = Q, None
            self._result = dict(status='secondary_unattained', J=str(J), secondary_infimum=str(Q))
            self._ranges[1:] = [[], []]
        _append(self._ranges[1], ranges[1])
        if key is None or (self._key is not None and key > self._key):
            return
        if self._key is None or key < self._key:
            self._key = key
            self._result = deepcopy(result)
            self._ranges[2] = []
        _append(self._ranges[2], ranges[2])

    @api
    def add(self, regime_id, result):
        _index(regime_id)
        require(regime_id == self.end, 'stream_noncontiguous_regime_id')
        parsed = _parse_result(result)
        run = [[regime_id, regime_id+1]]
        self._consume(parsed, result, [run if value is not None else [] for value in parsed])
        if result['status'] in EXCLUSIONS:
            self._counts[result['status']] += 1
        self.end += 1

    @api
    def extend_summary(self, summary):
        """Merge an adjacent summary; validate its structure, not its authority."""
        parsed = _validate_summary(summary)
        require(self.end == summary['start'], 'stream_nonadjacent_summary')
        audit = summary['audit']
        self._consume(parsed, summary['result'], [audit[name] for name in RANGES])
        for name in EXCLUSIONS:
            self._counts[name] += audit['exclusion_counts'][name]
        self.end = summary['end']

    def summary(self):
        return dict(schema=SCHEMA, start=self.start, end=self.end,
                    result=deepcopy(self._result),
                    audit=dict(zip(RANGES, deepcopy(self._ranges)),
                               exclusion_counts=self._counts.copy()))


@api
def summarize_records(records, *, start=0):
    """Consume old-style record dictionaries once, assigning IDs from ``start``.

    Other record fields are ignored; this function does not verify them.  Use
    ``StreamAggregator.add`` when the source already carries explicit IDs.
    Empty input remains distinguishable from all-excluded input by ``end-start``
    and the exclusion counts, although both have the reference's empty result.
    """
    stream = StreamAggregator(start)
    for record in records:
        require(type(record) is dict and 'result' in record, 'stream_record_result_missing')
        stream.add(stream.end, record['result'])
    return stream.summary()


@api
def merge_summaries(left, right):
    """Return a fresh summary for adjacent intervals; merge is associative."""
    _validate_summary(left)
    stream = StreamAggregator(left['start'])
    stream.extend_summary(left)
    stream.extend_summary(right)
    return stream.summary()


@api
def finalize_summary(summary, *, with_audit=False):
    """Return the reference result and, optionally, compact range-based audit."""
    require(type(with_audit) is bool, 'with_audit_type')
    _validate_summary(summary)
    result = deepcopy(summary['result'])
    return dict(result=result, audit=deepcopy(summary['audit'])) if with_audit else result


@api
def bound_audit(bound, summary):
    """Report the exact bound gap, preserving counterexamples and nonattainment."""
    result = finalize_summary(summary)
    if result['status'] == 'empty_restricted_family':
        return dict(bound_valid=True, bound_status='vacuous_empty_restricted_family',
                    bound_gap=None, recorded_bound=bound, primary_infimum=None)
    infimum = result['primary_infimum'] if result['status'] == 'primary_unattained' else result['J']
    if bound is None:
        return dict(bound_valid=False, bound_status='missing_bound_for_nonempty_family',
                    bound_gap=None, recorded_bound=None, primary_infimum=infimum)
    gap = rational(infimum)-rational(bound)
    return dict(bound_valid=gap >= 0, bound_status='satisfied' if gap >= 0 else 'violated',
                bound_gap=str(gap), recorded_bound=bound, primary_infimum=infimum)
