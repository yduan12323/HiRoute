"""Tiny independent differential folds; synthetic arithmetic only, no LP/data."""
from copy import deepcopy
from fractions import Fraction
from itertools import permutations, product
import unittest

from validation.suffix5.aggregate_stream import EXCLUSIONS, RANGES, summarize_records
from validation.suffix5.checker import aggregate_records
from validation.suffix5.independent_model import SuffixVerificationError
from validation.suffix5.occurrence_join import join_projection
from validation.suffix5.segment_fold import merge_block_segments


def attained(J='7/3', Q='5/7', pi=None):
    pi = [['a', 'C']] if pi is None else pi
    return dict(status='attained_optimum', J=J, Q_total=Q, H=len(pi),
                site_action_tuple=deepcopy(pi), lex_key=[J, Q, len(pi), deepcopy(pi)])


def primary(J='7/3'):
    return dict(status='primary_unattained', primary_infimum=J)


def secondary(J='7/3', Q='5/7'):
    return dict(status='secondary_unattained', J=J, secondary_infimum=Q)


def fixture(groups, size=3, ids=None):
    ids = list(range(len(groups))) if ids is None else ids
    segments, rows = [], []
    for ident, results in zip(ids, groups):
        start = len(rows)
        rows.extend(dict(result=deepcopy(result)) for result in results)
        segments.append(dict(segment_id=ident, start=start, end=len(rows), model_count=len(results),
                             graph_exclusions=sum(r['status'] == 'graph_unreachable' for r in results)))
    blocks, reports = [], []
    for ident, start in enumerate(range(0, len(rows), size)):
        end = min(len(rows), start+size)
        block = dict(block_id=ident, start=start, end=end, model_count=end-start)
        blocks.append(block)
        parts = []
        for segment in segments:
            lo, hi = max(start, segment['start']), min(end, segment['end'])
            if lo < hi:
                parts.append(dict(segment_id=segment['segment_id'],
                                  aggregate=summarize_records(rows[lo:hi], start=lo)))
        reports.append(dict(schema='suffix5-checked-block-certificates-v1', range=deepcopy(block),
                            complete_certificates=True, verified_models=end-start,
                            unresolved_ordinals=[], unsubmitted_ordinals=[],
                            aggregate=summarize_records(rows[start:end], start=start),
                            segment_summaries=parts, physical_witness_verified=False,
                            query_optimum_certified=False, literal_G8_closed=False))
    plan = dict(schema='suffix5-original-model-block-plan-v1', total_models=len(rows),
                block_size=size, blocks=blocks, segments=segments)
    return plan, reports, rows


def expanded(summary):
    names = ('primary_tied_regimes', 'secondary_tied_regimes', 'winning_regimes')
    return dict(result=summary['result'], audit=dict(
        {name: [i-summary['start'] for lo, hi in summary['audit'][key] for i in range(lo, hi)]
         for name, key in zip(names, RANGES)}, exclusion_counts=summary['audit']['exclusion_counts']))


def incomplete(report, *, unresolved=False):
    changed = deepcopy(report)
    ordinal = changed['range']['start']
    changed.update(complete_certificates=False, aggregate=None, segment_summaries=[])
    changed['verified_models'] -= 1
    changed['unresolved_ordinals' if unresolved else 'unsubmitted_ordinals'] = [ordinal]
    return changed


class SegmentFoldTests(unittest.TestCase):
    def assert_reference(self, plan, reports, rows):
        saved = deepcopy((plan, reports))
        folded = merge_block_segments(plan, reports)
        self.assertEqual(list(folded), [s['segment_id'] for s in plan['segments']])
        for segment in plan['segments']:
            entry = folded[segment['segment_id']]
            self.assertEqual(set(entry), {'segment_id', 'complete_certificates', 'aggregate'})
            self.assertEqual(entry['segment_id'], segment['segment_id'])
            self.assertIs(entry['complete_certificates'], True)
            summary = entry['aggregate']
            self.assertEqual((summary['start'], summary['end']), (segment['start'], segment['end']))
            self.assertEqual(expanded(summary), aggregate_records(rows[segment['start']:segment['end']],
                                                                 with_audit=True))
        self.assertEqual((plan, reports), saved)
        return folded

    def test_crossed_boundaries_empty_segments_short_tail_and_preserved_ids(self):
        groups = [[], [attained(), primary()], [], [secondary(), attained(), primary(), attained()],
                  [], [dict(status=s) for s in EXCLUSIONS], []]
        for size in (1, 2, 4, 20):
            plan, reports, rows = fixture(groups, size, ids=[18, 6, 23, 2, 45, 11, 30])
            self.assert_reference(plan, list(reversed(reports)), rows)
        plan, reports, rows = fixture(groups, 4)
        self.assertEqual(plan['blocks'][-1]['model_count'], 1)
        self.assert_reference(plan, reports, rows)
        for groups in ([], [[], [], []]):
            plan, reports, rows = fixture(groups)
            self.assert_reference(plan, reports, rows)

    def test_primary_and_secondary_nonattainment_survive_block_seams(self):
        groups = [[attained('3', '0'), primary(), secondary('5/2', '-100'), primary()],
                  [attained(Q='1', pi=[]), secondary(Q='2/3'), primary(),
                   secondary(Q='2/3'), attained(Q='3/4')]]
        plan, reports, rows = fixture(groups, 3)
        folded = self.assert_reference(plan, reports, rows)
        self.assertEqual(folded[0]['aggregate']['result'], primary())
        self.assertEqual(folded[1]['aggregate']['result'], secondary(Q='2/3'))
        self.assertEqual(folded[0]['aggregate']['audit'][RANGES[0]], [[1, 2], [3, 4]])
        self.assertEqual(folded[1]['aggregate']['audit'][RANGES[2]], [])

    def test_J_Q_H_pi_ties_first_winner_and_all_exclusions(self):
        winner = attained(pi=[['a', 'CS']])
        groups = [[attained('3', '-100'), attained(pi=[['0', 'C'], ['0', 'C']]),
                   attained(pi=[['z', 'C']]), winner, winner,
                   dict(status='strict_infeasible'), attained(pi=[['a', 'S']]), winner,
                   primary(), secondary()], [dict(status=s) for s in EXCLUSIONS], []]
        for size in (1, 2, 3, 4, 7, 20):
            folded = self.assert_reference(*fixture(groups, size))
            self.assertEqual(folded[0]['aggregate']['result'], winner)
            self.assertEqual(folded[0]['aggregate']['audit'][RANGES[2]], [[3, 5], [7, 8]])
            self.assertEqual(folded[1]['aggregate']['result'], dict(status='empty_restricted_family'))
            self.assertEqual(folded[1]['aggregate']['audit']['exclusion_counts'], dict.fromkeys(EXCLUSIONS, 1))
            self.assertEqual(folded[2]['aggregate']['audit']['exclusion_counts'], dict.fromkeys(EXCLUSIONS, 0))

    def test_exact_fractions_and_attained_equal_faces(self):
        tiny, J, Q = Fraction(1, 10**80), Fraction(1, 3), Fraction(2, 7)
        groups = [[attained(str(J+tiny), '-100'), primary(str(J)),
                   attained(str(J), str(Q+tiny), []), secondary(str(J), str(Q)),
                   attained(str(J), str(Q)), primary(str(J))]]
        folded = self.assert_reference(*fixture(groups, 2))
        self.assertEqual(folded[0]['aggregate']['result'], attained(str(J), str(Q)))

    def test_tiny_exhaustive_partition_and_arrival_permutations(self):
        choices = [*(dict(status=s) for s in EXCLUSIONS), primary('1'), secondary('1', '2'),
                   attained('1', '2'), attained('2', '0')]
        for sequence in product(choices, repeat=3):
            for split in (1, 2):
                for size in (1, 2, 3):
                    plan, reports, rows = fixture([sequence[:split], [], sequence[split:]], size)
                    for arrival in permutations(reports):
                        folded = merge_block_segments(plan, list(arrival))
                        for segment in plan['segments']:
                            self.assertEqual(expanded(folded[segment['segment_id']]['aggregate']),
                                             aggregate_records(rows[segment['start']:segment['end']], with_audit=True))

    def test_missing_prefix_middle_tail_or_incomplete_blocks_stay_unresolved(self):
        plan, reports, _ = fixture([[], [attained()]*7, [primary()], []], 2)
        for block_id in range(len(reports)):
            for replacement in (None, incomplete(reports[block_id]), incomplete(reports[block_id], unresolved=True)):
                changed = deepcopy(reports)
                if replacement is None:
                    changed.pop(block_id)
                else:
                    changed[block_id] = replacement
                folded = merge_block_segments(plan, changed)
                for segment in plan['segments']:
                    block = plan['blocks'][block_id]
                    affected = segment['start'] < block['end'] and block['start'] < segment['end']
                    if segment['start'] == segment['end']:
                        affected = False
                    self.assertIs(folded[segment['segment_id']]['complete_certificates'], not affected)
                    if affected:
                        self.assertIsNone(folded[segment['segment_id']]['aggregate'])
        missing = merge_block_segments(plan, [])
        self.assertEqual([i for i, value in missing.items() if value['complete_certificates']], [0, 3])

    def test_duplicate_foreign_changed_or_wrongly_typed_blocks_reject(self):
        plan, reports, _ = fixture([[attained()]*3, [primary()]*2], 2)
        bads = [reports+[deepcopy(reports[0])]]
        for path, value in [(('range', 'block_id'), 99), (('range', 'block_id'), True),
                            (('range', 'start'), 1), (('range', 'end'), 99),
                            (('range', 'model_count'), True), (('complete_certificates',), 1),
                            (('verified_models',), True), (('verified_models',), 1),
                            (('schema',), 'wrong')]:
            changed = deepcopy(reports)
            target = changed[0]
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            bads.append(changed)
        for bad in bads:
            with self.subTest(reports=bad), self.assertRaises(SuffixVerificationError):
                merge_block_segments(plan, bad)

    def test_missing_duplicate_foreign_reordered_and_wrong_intersection_fragments_reject(self):
        plan, reports, _ = fixture([[attained()], [primary()], [secondary()]], 3)
        mutations = [lambda r: r['segment_summaries'].pop(),
                     lambda r: r['segment_summaries'].append(deepcopy(r['segment_summaries'][0])),
                     lambda r: r['segment_summaries'].reverse(),
                     lambda r: r['segment_summaries'][0].update(segment_id=99),
                     lambda r: r['segment_summaries'][0].update(segment_id=True),
                     lambda r: r['segment_summaries'][0]['aggregate'].update(end=2),
                     lambda r: r['segment_summaries'][1].update(aggregate=summarize_records([], start=1)),
                     lambda r: r['segment_summaries'][1].update(aggregate=summarize_records([dict(result=primary())], start=2))]
        for mutate in mutations:
            changed = deepcopy(reports)
            mutate(changed[0])
            with self.subTest(reports=changed), self.assertRaises(SuffixVerificationError):
                merge_block_segments(plan, changed)

    def test_whole_block_result_exclusion_or_tie_disagreement_rejects(self):
        plan, reports, _ = fixture([[attained(), attained(), dict(status='closed_infeasible')]], 3)
        alternate_rows = [[attained('8/3'), attained('8/3'), dict(status='closed_infeasible')],
                          [attained(), attained(), dict(status='strict_infeasible')],
                          [primary(), attained(), dict(status='closed_infeasible')],
                          [attained(), attained(), attained()]]
        for rows in alternate_rows:
            changed = deepcopy(reports)
            changed[0]['aggregate'] = summarize_records([dict(result=r) for r in rows])
            with self.assertRaisesRegex(SuffixVerificationError, 'whole_block_mismatch'):
                merge_block_segments(plan, changed)

    def test_malformed_summary_types_counts_and_tie_metadata_reject(self):
        plan, reports, _ = fixture([[attained(), attained(), primary()]], 3)
        mutations = [lambda s: s.update(start=True), lambda s: s.update(end='3'),
                     lambda s: s.update(result=[]), lambda s: s.update(audit=None),
                     lambda s: s['audit']['exclusion_counts'].update(graph_unreachable=True),
                     lambda s: s['audit']['exclusion_counts'].update(graph_unreachable=4),
                     lambda s: s['audit'].update(primary_tied_regime_ranges=[[0, 2], [1, 3]]),
                     lambda s: s['audit'].update(primary_tied_regime_ranges=[[0, 1], [1, 3]]),
                     lambda s: s['audit'].update(primary_tied_regime_ranges=[]),
                     lambda s: s['audit'].update(winning_regime_ranges=[[2, 3]])]
        for whole in (True, False):
            for mutate in mutations:
                changed = deepcopy(reports)
                summary = changed[0]['aggregate'] if whole else changed[0]['segment_summaries'][0]['aggregate']
                mutate(summary)
                with self.subTest(whole=whole, summary=summary), self.assertRaises(SuffixVerificationError):
                    merge_block_segments(plan, changed)
            for value in (None, [], (), 1, 'summary'):
                changed = deepcopy(reports)
                target = changed[0] if whole else changed[0]['segment_summaries'][0]
                target['aggregate'] = value
                with self.assertRaises(SuffixVerificationError):
                    merge_block_segments(plan, changed)

    def test_inconsistent_pending_dispositions_reject(self):
        plan, reports, _ = fixture([[attained()]*3], 3)
        mutations = [lambda r: r.update(complete_certificates=False),
                     lambda r: r.update(unresolved_ordinals=[0], verified_models=2),
                     lambda r: r.update(unresolved_ordinals=[True], verified_models=2),
                     lambda r: r.update(unresolved_ordinals=[3], verified_models=2),
                     lambda r: r.update(unsubmitted_ordinals=[0, 0], verified_models=1),
                     lambda r: r.update(unsubmitted_ordinals=[1, 0], verified_models=1),
                     lambda r: r.update(unresolved_ordinals=[0], unsubmitted_ordinals=[0], verified_models=1),
                     lambda r: r.update(complete_certificates=False, unresolved_ordinals=[0], verified_models=2)]
        for mutate in mutations:
            changed = deepcopy(reports)
            mutate(changed[0])
            with self.assertRaises(SuffixVerificationError):
                merge_block_segments(plan, changed)

    def test_plan_gap_overlap_counts_duplicate_ids_and_graph_exclusions_reject(self):
        plan, reports, _ = fixture([[attained()], [], [dict(status='graph_unreachable')]], 1)
        mutations = [lambda p: p.update(block_size=True), lambda p: p.update(block_size=0),
                     lambda p: p.update(total_models=3), lambda p: p['blocks'].pop(),
                     lambda p: p['blocks'].reverse(), lambda p: p['segments'].pop(),
                     lambda p: p['segments'][2].update(segment_id=0),
                     lambda p: p['segments'][2].update(segment_id=True),
                     lambda p: p['segments'][2].update(start=0, model_count=2),
                     lambda p: p['segments'][2].update(start=2, model_count=0),
                     lambda p: p['segments'][2].update(model_count=2),
                     lambda p: p['segments'][2].update(graph_exclusions=0),
                     lambda p: p['segments'][2].update(graph_exclusions=True),
                     lambda p: p['segments'][1].update(graph_exclusions=1)]
        for mutate in mutations:
            changed = deepcopy(plan)
            mutate(changed)
            with self.subTest(plan=changed), self.assertRaises(SuffixVerificationError):
                merge_block_segments(changed, reports)

    def test_compact_billion_model_spans_and_detached_output(self):
        plan, reports, _ = fixture([[attained()]], 1)
        count = 10**9
        plan.update(total_models=count, block_size=count)
        plan['blocks'][0].update(end=count, model_count=count)
        plan['segments'][0].update(end=count, model_count=count)
        reports[0]['range'].update(end=count, model_count=count)
        reports[0]['verified_models'] = count
        for summary in (reports[0]['aggregate'], reports[0]['segment_summaries'][0]['aggregate']):
            summary['end'] = count
            for key in RANGES:
                summary['audit'][key] = [[0, count]]
        saved = deepcopy((plan, reports))
        folded = merge_block_segments(plan, reports)
        for key in RANGES:
            self.assertEqual(folded[0]['aggregate']['audit'][key], [[0, count]])
        folded[0]['aggregate']['audit'][RANGES[0]][0][1] = 1
        folded[0]['aggregate']['result']['site_action_tuple'][0][0] = 'changed'
        self.assertEqual((plan, reports), saved)
        self.assertEqual(merge_block_segments(plan, reports)[0]['aggregate']['end'], count)

    def test_output_directly_joins_repeated_segments_and_missing_stays_unresolved(self):
        plan, reports, rows = fixture([[attained(), primary()], [secondary(), attained()]], 3)
        spans, offset = [], 0
        for position, ident in enumerate((1, 0, 1)):
            segment = plan['segments'][ident]
            spans.append(dict(family_position=0, action_position=position, segment_id=ident,
                              logical_start=segment['start'], logical_end=segment['end'],
                              query_start=offset, query_end=offset+segment['model_count']))
            offset += segment['model_count']
        projection = dict(query_seq=8, thin_occurrence_sha256='a'*64, ancestry_bundle_sha256='b'*64,
                          family_ids=['f'], actions=[['a', 'C'], ['b', 'C'], ['c', 'C']],
                          classification='synthetic', recorded_bound='7/3', model_slots=offset,
                          legal_completion_language_empty=False, ranges=spans)
        joined = join_projection(projection, merge_block_segments(plan, reports))
        self.assertEqual(joined['status'], 'complete')
        self.assertEqual(expanded(joined['aggregate']), aggregate_records(rows[2:]+rows[:2]+rows[2:], with_audit=True))
        joined = join_projection(projection, merge_block_segments(plan, reports[:1]))
        self.assertEqual(joined['status'], 'unresolved')
        self.assertIsNone(joined['aggregate'])
        self.assertIsNone(joined['bound_audit'])


if __name__ == '__main__':
    unittest.main()
