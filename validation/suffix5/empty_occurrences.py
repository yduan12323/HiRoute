"""Pure recovery of the historical trace's omitted empty-action occurrences.

The old replay retained these rows separately from its nonempty node-query
index. Recover exactly ``dict(query_seq=event['seq'], **event['payload'])``;
never synthesize a family, ancestry, CheckedTrace, or CheckedBundle.

Hash agreement here creates no execution or certificate authority. The final
caller must establish a trusted completed structural replay and immutable
capture/index pins independently, then supply that capture's trace, the index's
complete ordered nonempty query IDs, and its count/hash commitments. Neither a
claimed replay flag nor self-generated hashes can satisfy that trust boundary.
Inputs must remain unchanged during the call. Returned empty rows are detached.
Both the original v1 trace and the exact coalesced v2 header are supported;
the full original object, including the v2 representation, is hashed unchanged.
"""
import hashlib

from validation.capture5.containers import canonical_chunks
from . import checker
from .independent_model import api, require


_QUERY_FIELDS = {'group_id', 'region_id', 'effect', 'actions', 'bound',
                 'classification', 'queue_serial'}
_CHECKPOINT = 128


def _digest(value, before):
    """Exact containers.stream_digest bytes, with bounded chunk checkpoints."""
    digest = hashlib.sha256()
    for position, chunk in enumerate(canonical_chunks(value)):
        if position % _CHECKPOINT == 0:
            before()
        digest.update(chunk)
    before()
    return digest.hexdigest()


def _count(value, name):
    require(type(value) is int and value >= 0, name + '_type')


def _sha(value, name):
    require(type(value) is str and len(value) == 64
            and all(c in '0123456789abcdef' for c in value), name + '_type')


@api
def recover_empty_occurrences(trace, nonempty_query_ids, *, trace_sha256,
                              exact_queries, empty_action_queries,
                              empty_action_sha256, before=lambda: None):
    """Bind the complete historical query partition to independent replay pins.

    ``before`` is called at most 128 events, index IDs, actions, audit rows, or
    canonical chunks apart; each canonical chunk is at most 64 KiB. Exceptions
    abort extraction. These checkpoints impose no population-size limit.
    """
    require(callable(before), 'empty_occurrence_checkpoint_type')
    before()
    _count(exact_queries, 'exact_queries')
    _count(empty_action_queries, 'empty_action_queries')
    _sha(trace_sha256, 'trace_sha256')
    _sha(empty_action_sha256, 'empty_action_sha256')
    require(type(nonempty_query_ids) in (list, tuple), 'nonempty_query_ids_type')
    require(len(nonempty_query_ids) == exact_queries, 'nonempty_query_count')
    indexed_ids = set()
    previous = -1
    for position, seq in enumerate(nonempty_query_ids):
        if position % _CHECKPOINT == 0:
            before()
        _count(seq, 'nonempty_query_seq')
        require(seq > previous, 'nonempty_query_identity_or_order')
        indexed_ids.add(seq)
        previous = seq

    require(type(trace) is dict, 'trace_fields')
    if trace.get('schema') == 'family5-hier-trace-v2':
        require(set(trace) == {'schema', 'representation', 'events'}, 'trace_fields')
        require(type(trace['representation']) is str
                and trace['representation'] == 'exact-adjacent-cut-coalescing-v1',
                'trace_representation')
    else:
        require(set(trace) == {'schema', 'events'}, 'trace_fields')
        require(trace['schema'] == 'family5-hier-trace-v1', 'trace_schema')
    require(type(trace['events']) is list, 'trace_events_type')
    require(_digest(trace, before) == trace_sha256, 'historical_trace_digest_mismatch')
    rows, query_ids = [], []
    nonempty_position = 0
    for position, event in enumerate(trace['events']):
        if position % _CHECKPOINT == 0:
            before()
        require(type(event) is dict and set(event) == {'seq', 'kind', 'payload'}, 'event_fields')
        seq = event['seq']
        require(type(seq) is int and seq == position, 'event_sequence_identity_or_order')
        require(type(event['kind']) is str and type(event['payload']) is dict, 'event_types')
        if event['kind'] != 'query':
            continue
        query_ids.append(seq)
        payload = event['payload']
        require(set(payload) == _QUERY_FIELDS, 'query_payload_fields')
        _count(payload['group_id'], 'query_group_id')
        _count(payload['region_id'], 'query_region_id')
        require(type(payload['effect']) is str and payload['effect'] in ('C', 'S', 'CS'), 'query_effect')
        actions = payload['actions']
        require(type(actions) is list, 'query_actions_type')
        classification = payload['classification']
        require(type(classification) is str, 'query_classification_type')
        if not actions:
            require(classification == 'empty_actions', 'empty_query_classification')
            require(payload['bound'] is None and payload['queue_serial'] is None,
                    'empty_query_bound_or_queue_serial')
            require(seq not in indexed_ids, 'empty_nonempty_query_overlap')
            # All other accepted payload fields are immutable scalar leaves.
            rows.append(dict(query_seq=seq, **dict(payload, actions=[])))
        else:
            require(classification in ('queued', 'unreachable'), 'nonempty_query_classification')
            for action_position, action in enumerate(actions):
                if action_position % _CHECKPOINT == 0:
                    before()
                require(type(action) is list and len(action) == 2
                        and type(action[0]) is str and type(action[1]) is str
                        and action[1] == payload['effect'], 'query_action_type_or_effect')
            if classification == 'queued':
                require(type(payload['bound']) is str and type(payload['queue_serial']) is int
                        and payload['queue_serial'] > 0, 'queued_query_bound_or_queue_serial')
            else:
                require(payload['bound'] is None and payload['queue_serial'] is None,
                        'unreachable_query_bound_or_queue_serial')
            require(nonempty_position < len(nonempty_query_ids)
                    and seq == nonempty_query_ids[nonempty_position], 'nonempty_query_identity_or_order')
            nonempty_position += 1
    require(nonempty_position == exact_queries, 'nonempty_query_count')
    require(len(rows) == empty_action_queries, 'empty_query_count')
    require(len(query_ids) == exact_queries + empty_action_queries, 'total_query_event_count')
    require(_digest(rows, before) == empty_action_sha256, 'historical_empty_digest_mismatch')
    audits = []
    for position, row in enumerate(rows):
        if position % _CHECKPOINT == 0:
            before()
        result = {'status': 'empty_restricted_family'}
        audits.append(dict(query_seq=row['query_seq'], result=result,
                           audit=checker._bound_audit(row['bound'], result)))
    before()
    return dict(schema='family5-historical-empty-occurrences-v1',
                trace_sha256=trace_sha256, exact_queries=exact_queries,
                empty_action_queries=len(rows), empty_action_sha256=empty_action_sha256,
                total_query_events=len(query_ids), query_ids=query_ids, rows=rows, audits=audits,
                execution_authority=False, certificate_authority=False)
