"""Source-bound original-query planning, pending physical/final collection.

Only a genuine cold-admitted population and a reconciled CheckedRegistry enter
this bridge. Receipt admission remains responsible for the actual successful
reviewed execution and its entire proof dependency graph. This module neither
replays that numerical proof nor creates a CheckedTrace or CheckedBundle.

Storage scales with compact segment summaries, original query bindings and
unique selected descriptors, never the expanded original model occurrences.
Callbacks may stream query rows; all rows remain provisional until the factory
returns. Exceptions (including cancellation) propagate without a completed plan.
"""
from collections import Counter
from copy import deepcopy
import hashlib
import json

from validation.suffix5.block_plan import OrderedModelPopulation
from validation.suffix5.aggregate_stream import RANGES
from validation.suffix5.empty_occurrences import recover_empty_occurrences
from validation.suffix5.occurrence_join import join_projection
from validation.suffix5.segment_fold import merge_block_segments

from . import plan as binding, suffix_census
from .indexed_population import AdmittedSuffixPopulation
from .window_receipts import CheckedRegistry


_PLANNING = object()
MAX_PHYSICAL_REQUESTS = 8192
MAX_PHYSICAL_REQUEST_BYTES = 16 * 1024**2
_PENDING = dict(physical_witness_verified=False, query_optimum_certified=False,
                full_population_complete=False, literal_G8_closed=False)
_REPRESENTATIVE_RUN = dict(attained_optimum=RANGES[2], secondary_unattained=RANGES[1],
                           primary_unattained=RANGES[0])


def _same(actual, expected, why):
    suffix_census.same(actual, expected, 'query collection: '+why)


def _request_digest(requests, before):
    digest = hashlib.sha256(b'[')
    for position, (ordinal, request) in enumerate(sorted(requests.items())):
        before()
        if position:
            digest.update(b',')
        digest.update(binding.canonical(dict(model_ordinal=ordinal, **request)))
    digest.update(b']')
    return digest.hexdigest()


def _source(admitted):
    binding.require(type(admitted) is AdmittedSuffixPopulation and
                    type(admitted.population) is OrderedModelPopulation,
                    'query collection requires genuine admitted population')
    catalogue, commitment = admitted.population.plan(), admitted.commitment()
    _same(binding.digest(catalogue), admitted.population.plan_sha256,
          'population catalogue changed')
    _same(commitment['block_plan_sha256'], admitted.population.plan_sha256,
          'population commitment changed')
    for field, key in (('source_bundle_sha256', 'source_bundle_sha256'),
                       ('case_sha256', 'case_sha256'),
                       ('logical_plan_sha256', 'logical_plan_sha256'),
                       ('total_models', 'unique_logical_models')):
        _same(catalogue[field], commitment[key], 'catalogue source differs: '+field)
    return catalogue, commitment


def _complete_segments(admitted, registry, before):
    catalogue, commitment = _source(admitted)
    binding.require(type(registry) is CheckedRegistry,
                    'query collection requires genuine checked registry')
    metadata = registry.metadata()
    _same(metadata['population'], commitment, 'foreign registry population')
    _same(metadata['catalogue_sha256'], binding.digest(catalogue['blocks']),
          'foreign registry catalogue')
    # This call, not a metadata scheduling/authority flag, is the readiness gate.
    reports = registry.block_reports()
    blocks = catalogue['blocks']
    _same([row['range'] for row in metadata['blocks']], blocks,
          'registry lacks exact full canonical block coverage')
    _same([row['range'] for row in reports], blocks,
          'reports lack exact full canonical block coverage')
    _same(metadata['completed_models'], catalogue['total_models'],
          'registry model total differs')
    for report, compact in zip(reports, metadata['blocks']):
        before()
        binding.require(report['complete_certificates'] is True and
                        report['unresolved_ordinals'] == [] and
                        report['unsubmitted_ordinals'] == [],
                        'query collection requires complete certificate coverage')
        expected = dict(range=report['range'], entry_id=compact['entry_id'],
                        summary_sha256=binding.digest(report),
                        aggregate_sha256=binding.digest(report['aggregate']),
                        segments=[dict(segment_id=row['segment_id'],
                            start=row['aggregate']['start'], end=row['aggregate']['end'],
                            summary_sha256=binding.digest(row))
                            for row in report['segment_summaries']])
        _same(compact, expected, 'report differs from reconciled registry commitment')
    before()
    segments = merge_block_segments(catalogue, reports)
    before()
    binding.require(all(row['complete_certificates'] is True and row['aggregate'] is not None
                        for row in segments.values()),
                    'query collection has unresolved population segments')
    return catalogue, commitment, metadata, segments


def _query(admitted, segments, position, sequence, population_sha, requests, request_budget, before):
    before()
    projection = admitted.query_projection(sequence)
    joined = join_projection(projection, segments)  # Includes unchanged _bound_audit, once.
    binding.require(joined['status'] == 'complete', 'query collection has unresolved query')
    result = joined['aggregate']['result']
    ordinal = regime = descriptor_sha = None
    if result['status'] != 'empty_restricted_family':
        runs = joined['aggregate']['audit'][_REPRESENTATIVE_RUN[result['status']]]
        binding.require(bool(runs), 'query collection missing representative tie range')
        regime = runs[0][0]
        span = next((span for span in projection['ranges']
                     if span['query_start'] <= regime < span['query_end']), None)
        binding.require(span is not None, 'query collection representative outside projection')
        ordinal = span['logical_start']+regime-span['query_start']
        if ordinal not in requests:
            binding.require(len(requests) < MAX_PHYSICAL_REQUESTS,
                            'query collection unique physical request count cap')
            before()
            rows = list(admitted.population.descriptors(ordinal, ordinal+1))
            binding.require(len(rows) == 1 and rows[0]['ordinal'] == ordinal and
                            rows[0]['segment_id'] == span['segment_id'],
                            'query collection representative descriptor differs')
            descriptor = rows[0]
            _same(binding.digest(descriptor['logical_identity']),
                  descriptor['logical_identity_sha256'], 'descriptor identity hash differs')
            request = dict(descriptor=descriptor, result=deepcopy(result))
            size = len(binding.canonical(dict(model_ordinal=ordinal, **request)))
            total_bytes = request_budget['bytes']+size+bool(requests)
            binding.require(total_bytes <= MAX_PHYSICAL_REQUEST_BYTES,
                            'query collection physical request byte cap')
            requests[ordinal] = request
            request_budget['bytes'] = total_bytes
        request = requests[ordinal]
        _same(request['result'], result, 'one physical model has conflicting query results')
        binding.require(request['descriptor']['segment_id'] == span['segment_id'],
                        'query collection repeated descriptor segment differs')
        descriptor_sha = binding.digest(request['descriptor'])
    query_binding = dict(schema='hiroute-original-query-physical-binding-v1',
                        population_sha256=population_sha, query_index_position=position,
                        query_seq=sequence, projection_sha256=binding.digest(projection),
                        result_sha256=binding.digest(result), query_regime=regime,
                        model_ordinal=ordinal, descriptor_sha256=descriptor_sha)
    query_binding['binding_id'] = binding.digest(query_binding)
    return dict(schema='hiroute-original-query-collection-row-v1',
                status='pending_final_collection' if ordinal is None else
                       'pending_physical_witness_and_final_collection',
                query_binding=query_binding, joined=joined,
                physical_witness_required=ordinal is not None, **_PENDING)


class EmptyOccurrencePartition:
    """Count/hash/identity partition recovered from this plan's admitted pins.

    It is not execution or certificate authority and cannot be passed in as a
    substitute for calling the recovery method on the original pinned trace.
    """
    __slots__ = ('_report',)

    def __init__(self, report, *, _token=None):
        binding.require(_token is _PLANNING, 'query collection recovery factory required')
        object.__setattr__(self, '_report', binding.canonical(report))

    def __setattr__(self, *_):
        raise AttributeError('immutable empty occurrence partition')

    def report(self) -> dict:
        return json.loads(self._report)


class QueryCollectionPlan:
    """Completed planning only; every physical/final acceptance remains pending."""
    __slots__ = ('_admitted', '_segments', '_bindings', '_requests', '_summary')

    def __init__(self, admitted, segments, bindings, requests, summary, *, _token=None):
        binding.require(_token is _PLANNING, 'query collection planning factory required')
        object.__setattr__(self, '_admitted', admitted)
        object.__setattr__(self, '_segments', binding.canonical(list(segments.values())))
        object.__setattr__(self, '_bindings', tuple(binding.canonical(row) for row in bindings))
        object.__setattr__(self, '_requests', tuple((ordinal, binding.canonical(request))
                                                  for ordinal, request in sorted(requests.items())))
        object.__setattr__(self, '_summary', binding.canonical(summary))

    def __setattr__(self, *_):
        raise AttributeError('immutable query collection plan')

    def summary(self) -> dict:
        return json.loads(self._summary)

    def query_bindings(self) -> list[dict]:
        return [json.loads(row) for row in self._bindings]

    def physical_requests(self) -> dict[int, dict]:
        """Unique ordinal -> exact admitted descriptor and expected query result."""
        return {ordinal: json.loads(request) for ordinal, request in self._requests}

    def physical_request_rows(self) -> list[dict]:
        """Persistence form: an ordered array retaining exact integer ordinals."""
        return [dict(model_ordinal=ordinal, **json.loads(request))
                for ordinal, request in self._requests]

    def _check_source(self):
        _, commitment = _source(self._admitted)
        _same(binding.digest(commitment), self.summary()['population_sha256'],
              'admitted source changed after planning')

    def iter_queries(self, *, before=lambda: None):
        """Re-emit detached provisional rows in original index order, compactly."""
        binding.require(callable(before), 'query collection checkpoint must be callable')
        before()
        self._check_source()
        segments = {row['segment_id']: row for row in json.loads(self._segments)}
        requests = self.physical_requests()
        request_budget = dict(bytes=self.summary()['physical_request_bytes'])
        population_sha = self.summary()['population_sha256']
        for raw in self._bindings:
            expected = json.loads(raw)
            row = _query(self._admitted, segments, expected['query_index_position'],
                         expected['query_seq'], population_sha, requests, request_budget, before)
            _same(row['query_binding'], expected, 'original query changed after planning')
            yield row
        before()

    def recover_empty_partition(self, trace, *, before=lambda: None) -> EmptyOccurrencePartition:
        """Recover freshly, using admitted trace/index pins; never accept a report.

        The final runtime supplies the trace from the authenticated original
        capture. Do not pre-hash it here: the cleared recovery bridge performs
        its own cancellable trace hash, partition checks, empty hash and audits.
        """
        binding.require(callable(before), 'query collection checkpoint must be callable')
        before()
        self._check_source()
        summary = self.summary()
        recovered = recover_empty_occurrences(trace, self._admitted.query_ids(),
            trace_sha256=summary['original_trace_sha256'],
            exact_queries=summary['queries'],
            empty_action_queries=summary['empty_action_queries'],
            empty_action_sha256=summary['empty_action_sha256'], before=before)
        partition = EmptyOccurrencePartition(dict(population_sha256=summary['population_sha256'],
            query_collection_rows_sha256=summary['query_collection_rows_sha256'],
            status='pending_final_collection', recovered=recovered, **_PENDING), _token=_PLANNING)
        before()
        return partition


def plan_query_collection(admitted, registry, *, on_query=None, before=lambda: None) -> QueryCollectionPlan:
    """Plan every original indexed query, or raise without a completed plan.

    ``before`` supplies the caller's resource/cancellation checkpoint at source,
    block, query, descriptor, callback and return boundaries. Existing pure fold
    and join operations retain their own compact-summary memory behavior. No
    per-model array is created. ``on_query`` rows are provisional, detached and
    carry no physical proof; retain the successful returned plan to seal a stream.
    """
    binding.require(callable(before) and (on_query is None or callable(on_query)),
                    'query collection callbacks must be callable')
    before()
    catalogue, commitment, metadata, segments = _complete_segments(admitted, registry, before)
    population_sha = binding.digest(commitment)
    requests, bindings, statuses, bounds = {}, [], Counter(), Counter()
    request_budget = dict(bytes=2)  # Canonical persistence array's opening/closing brackets.
    occurrences = zero_languages = excluded_languages = 0
    stream_hash = hashlib.sha256()
    sequences = admitted.query_ids()
    _same(len(sequences), commitment['queries'], 'original query count changed')
    for position, sequence in enumerate(sequences):
        row = _query(admitted, segments, position, sequence, population_sha, requests, request_budget, before)
        joined = row['joined']
        slots = joined['projection']['model_slots']
        status = joined['aggregate']['result']['status']
        occurrences += slots
        statuses[status] += 1
        bounds[joined['bound_audit']['bound_status']] += 1
        zero_languages += slots == 0
        excluded_languages += slots > 0 and status == 'empty_restricted_family'
        bindings.append(deepcopy(row['query_binding']))
        stream_hash.update(binding.canonical(row)+b'\n')
        if on_query is not None:
            on_query(row)
        before()
    _same(occurrences, commitment['original_model_occurrences'],
          'original model occurrence total changed')
    _same(binding.digest(admitted.commitment()), population_sha,
          'admitted source changed during planning')
    summary = dict(schema='hiroute-original-query-collection-plan-v1',
        status='pending_physical_witnesses_and_final_collection' if requests else
               'pending_final_collection', planning_complete=True,
        population_sha256=population_sha, registry_metadata_sha256=binding.digest(metadata),
        block_plan_sha256=commitment['block_plan_sha256'], catalogue_sha256=metadata['catalogue_sha256'],
        original_query_freeze_sha256=commitment['query_freeze_sha256'],
        original_trace_sha256=admitted._index['trace_sha256'],
        completed_replay=deepcopy(commitment['completed_replay']),
        queries=len(bindings), original_model_occurrences=occurrences,
        unique_logical_models=catalogue['total_models'], complete_blocks=len(catalogue['blocks']),
        segments=len(segments), zero_length_queries=zero_languages,
        all_excluded_nonempty_queries=excluded_languages,
        result_counts=dict(statuses), bound_status_counts=dict(bounds),
        physical_query_bindings=sum(row['model_ordinal'] is not None for row in bindings),
        unique_physical_requests=len(requests),
        physical_request_bytes=request_budget['bytes'],
        physical_request_rows_sha256=_request_digest(requests, before),
        query_bindings_sha256=binding.digest(bindings),
        query_collection_rows_sha256=stream_hash.hexdigest(),
        query_collection_rows_encoding='canonical-json-lines-v1',
        empty_action_queries=commitment['empty_action_queries'],
        empty_action_sha256=commitment['empty_action_sha256'],
        empty_partition_recovered=False, **_PENDING)
    result = QueryCollectionPlan(admitted, segments, bindings, requests, summary, _token=_PLANNING)
    before()
    return result
