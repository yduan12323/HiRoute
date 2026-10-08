"""Pure range arithmetic from checked block reports to logical segments.

The caller must independently admit the population and certify every model in
each report marked complete, including losing and excluded models. Neither a
flag nor this fold authenticates certificates, sources, descriptors or witnesses.
This is the same explicit certificate precondition as ``join_projection``.
Only structural coverage and the exact summary algebra are checked here.
"""
from .aggregate_stream import StreamAggregator, finalize_summary
from .independent_model import api, exact_json, require, same


def _natural(value):
    require(type(value) is int and value >= 0, 'segment_fold_index_type_or_range')


def _population(plan):
    exact_json(plan)
    require(type(plan) is dict, 'segment_fold_plan_type')
    same(plan['schema'], 'suffix5-original-model-block-plan-v1', 'segment_fold_plan_schema')
    total, size = plan['total_models'], plan['block_size']
    _natural(total)
    _natural(size)
    require(size > 0, 'segment_fold_block_size')
    blocks, segments = plan['blocks'], plan['segments']
    require(type(blocks) is list and type(segments) is list, 'segment_fold_plan_lists')
    require(len(blocks) == (total+size-1)//size, 'segment_fold_block_count')
    for ident, block in enumerate(blocks):
        start, end = ident*size, min(total, (ident+1)*size)
        same(block, dict(block_id=ident, start=start, end=end, model_count=end-start),
             'segment_fold_canonical_block_range')
    cursor, seen = 0, set()
    for segment in segments:
        require(type(segment) is dict, 'segment_fold_segment_type')
        for key in ('segment_id', 'start', 'end', 'model_count'):
            _natural(segment[key])
        ident, start, end = (segment[key] for key in ('segment_id', 'start', 'end'))
        require(ident not in seen, 'segment_fold_duplicate_segment_id')
        seen.add(ident)
        require(start == cursor and start <= end <= total
                and segment['model_count'] == end-start, 'segment_fold_segment_gap_overlap_or_count')
        if 'graph_exclusions' in segment:
            _natural(segment['graph_exclusions'])
            require(segment['graph_exclusions'] <= end-start, 'segment_fold_graph_exclusion_count')
        cursor = end
    require(cursor == total, 'segment_fold_population_coverage')
    return blocks, segments


def _report(report, blocks):
    exact_json(report)
    require(type(report) is dict, 'segment_fold_report_type')
    same(report['schema'], 'suffix5-checked-block-certificates-v1', 'segment_fold_report_schema')
    span = report['range']
    require(type(span) is dict, 'segment_fold_report_range_type')
    ident = span['block_id']
    _natural(ident)
    require(ident < len(blocks), 'segment_fold_foreign_block_id')
    same(span, blocks[ident], 'segment_fold_report_range_changed')
    require(type(report['complete_certificates']) is bool, 'segment_fold_complete_flag_type')
    _natural(report['verified_models'])
    pending = set()
    for key in ('unresolved_ordinals', 'unsubmitted_ordinals'):
        values = report[key]
        require(type(values) is list, 'segment_fold_pending_ordinals_type')
        previous = span['start']-1
        for ordinal in values:
            _natural(ordinal)
            require(previous < ordinal < span['end'] and ordinal >= span['start']
                    and ordinal not in pending, 'segment_fold_pending_ordinal_duplicate_or_foreign')
            pending.add(ordinal)
            previous = ordinal
    require(report['verified_models']+len(pending) == span['model_count'],
            'segment_fold_verified_model_count')
    require(type(report['segment_summaries']) is list, 'segment_fold_fragments_type')
    same(report['complete_certificates'], not pending, 'segment_fold_inconsistent_completeness')
    if pending:
        require(report['aggregate'] is None and not report['segment_summaries'],
                'segment_fold_incomplete_report_has_aggregate')
    return ident


@api
def merge_block_segments(population_plan, block_reports):
    """Return the integer-keyed segment mapping consumed by ``join_projection``.

    Inputs are an admitted ``OrderedModelPopulation.plan()`` and a list of
    ``BlockCertificates.summary()`` reports, in any arrival order. The caller
    explicitly supplies independently certified reports; this function cannot
    establish that precondition. Ancillary plan/report metadata is not authority
    and is ignored. If present, declared segment graph-exclusion counts must
    agree with completed segment summaries.

    Missing or incomplete blocks leave affected nonempty segments unresolved:
    ``complete_certificates=False, aggregate=None``. Empty canonical segments
    need no proofs. A malformed report, duplicate/foreign block, changed range,
    or fragment gap/overlap is rejected, even if other coverage is missing.
    Every complete block's whole summary must equal its ordered fragment fold,
    including exact result, exclusion counts and all compact tie runs.

    Space depends on block/segment counts and tie runs, never expanded model IDs.
    Returned summaries are detached from the inputs; segment IDs are preserved.
    """
    blocks, segments = _population(population_plan)
    require(type(block_reports) is list, 'segment_fold_reports_type')
    reports = {}
    for report in block_reports:
        ident = _report(report, blocks)
        require(ident not in reports, 'segment_fold_duplicate_block_id')
        reports[ident] = report
    streams = {segment['segment_id']: StreamAggregator(segment['start']) for segment in segments}
    position = 0
    for ident in sorted(reports):
        report, span = reports[ident], blocks[ident]
        if not report['complete_certificates']:
            continue
        while position < len(segments) and segments[position]['end'] <= span['start']:
            position += 1
        expected, index = [], position
        while index < len(segments) and segments[index]['start'] < span['end']:
            segment = segments[index]
            lo, hi = max(span['start'], segment['start']), min(span['end'], segment['end'])
            if lo < hi:
                expected.append((segment['segment_id'], lo, hi))
            index += 1
        fragments = report['segment_summaries']
        require(len(fragments) == len(expected), 'segment_fold_fragment_count')
        whole = StreamAggregator(span['start'])
        for fragment, (segment_id, lo, hi) in zip(fragments, expected):
            require(type(fragment) is dict and set(fragment) == {'segment_id', 'aggregate'},
                    'segment_fold_fragment_fields')
            same(fragment['segment_id'], segment_id, 'segment_fold_foreign_or_reordered_fragment')
            summary = fragment['aggregate']
            finalize_summary(summary)
            same([summary['start'], summary['end']], [lo, hi], 'segment_fold_fragment_intersection')
            whole.extend_summary(summary)
            stream = streams[segment_id]
            if stream is not None and stream.end == lo:
                stream.extend_summary(summary)
            else:
                # A missing earlier block cannot be filled by a later fragment.
                streams[segment_id] = None
        finalize_summary(report['aggregate'])
        same(report['aggregate'], whole.summary(), 'segment_fold_whole_block_mismatch')
    output = {}
    for segment in segments:
        ident = segment['segment_id']
        stream = streams[ident]
        complete = stream is not None and stream.end == segment['end']
        summary = stream.summary() if complete else None
        if complete and 'graph_exclusions' in segment:
            same(summary['audit']['exclusion_counts']['graph_unreachable'], segment['graph_exclusions'],
                 'segment_fold_graph_exclusions_mismatch')
        output[ident] = dict(segment_id=ident, complete_certificates=complete, aggregate=summary)
    return output
