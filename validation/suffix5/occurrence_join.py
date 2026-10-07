"""Pure arithmetic projection of complete logical segments into one query.

This helper creates no certificate authority. The caller must independently
certify *every* model in every supplied full segment, authenticate the original
query projection and segment identities, and retain all model/task/certificate
proofs, including losing and excluded models. A ``complete_certificates`` flag
is a caller precondition, not a proof checked here. No LP or witness is checked.

The output keeps compact tie runs in original query regime order. Repeated
logical segments contribute again at each original occurrence. Neither partial
segments nor winning-only summaries can establish a complete query aggregate.
"""
from copy import deepcopy

from .aggregate_stream import RANGES, StreamAggregator, finalize_summary
from .checker import _bound_audit
from .independent_model import api, exact_json, require, same


SCHEMA = 'suffix5-original-query-join-v1'


def _natural(value):
    require(type(value) is int and value >= 0, 'join_index_type_or_range')


def _projection(projection):
    exact_json(projection)
    fields = {'query_seq', 'thin_occurrence_sha256', 'ancestry_bundle_sha256',
              'family_ids', 'actions', 'classification', 'recorded_bound',
              'model_slots', 'legal_completion_language_empty', 'ranges'}
    require(type(projection) is dict and set(projection) == fields, 'join_projection_fields')
    _natural(projection['query_seq'])
    _natural(projection['model_slots'])
    require(all(type(projection[key]) is str for key in
                ('thin_occurrence_sha256', 'ancestry_bundle_sha256', 'classification')),
            'join_projection_identity_type')
    families, actions, spans = (projection[key] for key in ('family_ids', 'actions', 'ranges'))
    require(type(families) is list and all(type(value) is str for value in families),
            'join_family_ids_type')
    require(type(actions) is list and all(type(action) is list and len(action) == 2
            and all(type(value) is str for value in action) for action in actions),
            'join_actions_type')
    require(type(spans) is list and len(spans) == len(families)*len(actions),
            'join_family_action_coverage')
    cursor, logical = 0, {}
    for position, span in enumerate(spans):
        require(type(span) is dict and set(span) == {'family_position', 'action_position',
                'segment_id', 'logical_start', 'logical_end', 'query_start', 'query_end'},
                'join_span_fields')
        for value in span.values():
            _natural(value)
        same([span['family_position'], span['action_position']],
             list(divmod(position, len(actions))), 'join_original_family_action_order')
        lo, hi = span['logical_start'], span['logical_end']
        require(lo <= hi and span['query_start'] == cursor
                and span['query_end']-cursor == hi-lo, 'join_gap_overlap_or_length')
        ident = span['segment_id']
        require(ident not in logical or logical[ident] == (lo, hi),
                'join_repeated_segment_span_changed')
        logical[ident] = (lo, hi)
        cursor = span['query_end']
    require(cursor == projection['model_slots'], 'join_model_slot_coverage')
    same(projection['legal_completion_language_empty'], cursor == 0,
         'join_empty_language_mismatch')
    nonempty = sorted((lo, hi) for lo, hi in logical.values() if lo < hi)
    require(all(left[1] <= right[0] for left, right in zip(nonempty, nonempty[1:])),
            'join_foreign_overlapping_segments')
    return logical


@api
def join_projection(projection, complete_segments):
    """Return a complete query summary and its own unchanged checker bound audit.

    ``projection`` is the dictionary emitted by the admitted population's
    ``query_projection``. ``complete_segments`` is a dict keyed by integer
    segment ID; each value has ``segment_id``, ``complete_certificates`` (bool),
    and ``aggregate`` (a full StreamAggregator summary, or None if incomplete).
    Entries for other queries are allowed and ignored. This mapping is an
    arithmetic interface, never a replacement for independently checked proof.

    Missing, incomplete, or partial segment coverage yields ``unresolved`` with
    no aggregate and no bound audit. Malformed or foreign identities/spans raise
    SuffixVerificationError. Empty spans need no model certificates. A complete
    all-excluded query has the checker's vacuous result but retains its nonzero
    model_slots and exclusion counts, unlike a zero-length legal language.
    """
    logical = _projection(projection)
    require(type(complete_segments) is dict, 'join_segments_mapping_type')
    for ident in complete_segments:
        _natural(ident)
    summaries, unresolved = {}, []
    for ident, (lo, hi) in logical.items():
        if lo == hi:
            summaries[ident] = StreamAggregator(lo).summary()
            continue
        entry = complete_segments.get(ident)
        if entry is None:
            unresolved.append(ident)
            continue
        exact_json(entry)
        require(type(entry) is dict and set(entry) ==
                {'segment_id', 'complete_certificates', 'aggregate'}, 'join_segment_fields')
        same(entry['segment_id'], ident, 'join_foreign_segment_id')
        require(type(entry['complete_certificates']) is bool, 'join_complete_flag_type')
        if not entry['complete_certificates'] or entry['aggregate'] is None:
            unresolved.append(ident)
            continue
        summary = entry['aggregate']
        finalize_summary(summary)  # Validate compact audit before translating it.
        if (summary['start'], summary['end']) != (lo, hi):
            unresolved.append(ident)
            continue
        summaries[ident] = summary
    output = dict(schema=SCHEMA, projection=deepcopy(projection),
                  status='unresolved' if unresolved else 'complete',
                  unresolved_segment_ids=unresolved, aggregate=None, bound_audit=None)
    if unresolved:
        return output
    stream = StreamAggregator()
    for span in projection['ranges']:
        translated = deepcopy(summaries[span['segment_id']])
        offset = span['query_start']-span['logical_start']
        translated['start'], translated['end'] = span['query_start'], span['query_end']
        for key in RANGES:
            translated['audit'][key] = [[lo+offset, hi+offset]
                                        for lo, hi in translated['audit'][key]]
        stream.extend_summary(translated)
    combined = stream.summary()
    output['aggregate'] = combined
    output['bound_audit'] = _bound_audit(projection['recorded_bound'], combined['result'])
    return output
