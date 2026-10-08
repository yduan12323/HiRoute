"""Tiny genuine families plus protocol-fake receipt metadata; no LP/server.

Factory tokens below deliberately bypass receipt execution admission to test
the collection protocol. Their synthetic dispositions are NOT evidence of a
successful verifier execution or a physical certificate. No CheckedTrace or
CheckedBundle is fabricated; tiny captures receive genuine structural checks.
"""
from copy import deepcopy
import hashlib
import json
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from experiments.time_cut_v2.recorded_real import plan, indexed_population as admission
from experiments.time_cut_v2.recorded_real import query_collection as collection
from experiments.time_cut_v2.recorded_real import window_receipts as receipts
from experiments.time_cut_v2.recorded_real.logical_models import count_logical_models
from tests import test_indexed_suffix_population as population_fixtures
from tests import test_logical_suffix_models as logical_fixtures
from tests.test_suffix_occurrence_join import attained, primary, secondary, expanded
from validation.suffix5.aggregate_stream import RANGES, summarize_records
from validation.suffix5.block_plan import OrderedModelPopulation
from validation.suffix5.checker import _bound_audit, aggregate_records


def protocol_registry(admitted, results):
    """Explicitly fake execution envelope, with genuine catalogue/range bindings."""
    catalogue = admitted.population.plan()
    rows = [dict(result=deepcopy(result)) for result in results]
    reports = []
    for span in catalogue['blocks']:
        lo, hi = span['start'], span['end']
        fragments = []
        for segment in catalogue['segments']:
            left, right = max(lo, segment['start']), min(hi, segment['end'])
            if left < right:
                fragments.append(dict(segment_id=segment['segment_id'],
                    aggregate=summarize_records(rows[left:right], start=left)))
        reports.append(dict(schema='suffix5-checked-block-certificates-v1', range=deepcopy(span),
            complete_certificates=True, verified_models=hi-lo, unresolved_ordinals=[],
            unsubmitted_ordinals=[], aggregate=summarize_records(rows[lo:hi], start=lo),
            segment_summaries=fragments, physical_witness_verified=False,
            query_optimum_certified=False, literal_G8_closed=False))
    if not reports:
        return receipts.make_registry(admitted, [])
    entry = dict(protocol_fake_not_execution_authority=True, entry_id='f'*64,
                 population_sha256=plan.digest(admitted.commitment()))
    entry['blocks'] = [receipts._compact_report(report, entry['entry_id']) for report in reports]
    receipt = receipts.CheckedWindowReceipt(entry, reports, _token=receipts._ADMISSION)
    return receipts.make_registry(admitted, [receipt])


def replace_registry(registry, *, metadata=None, reports=None):
    """Only for protocol rejection tests; never claim real receipt admission."""
    metadata = registry.metadata() if metadata is None else metadata
    if reports is None:
        return receipts.CheckedRegistry(metadata, registry._receipts, _token=receipts._ADMISSION)
    receipt = receipts.CheckedWindowReceipt(metadata['entries'][0], reports, _token=receipts._ADMISSION)
    return receipts.CheckedRegistry(metadata, [receipt], _token=receipts._ADMISSION)


class QueryCollectionTests(unittest.TestCase):
    def setUp(self):
        self.fx = population_fixtures.IndexedPopulationTests()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.admitted = self.fx.admit()
        # Smaller source-parameter blocks deliberately cross logical segments.
        self.admitted.population = OrderedModelPopulation(self.fx.ctx, self.fx.trusted,
                                                         self.fx.logical, block_size=7)
        self.catalogue = self.admitted.population.plan()
        self.results = [attained(str(ordinal+1)) for ordinal in range(self.catalogue['total_models'])]
        self.registry = protocol_registry(self.admitted, self.results)
        for name in ('Popen', 'run', 'check_output'):
            manager = patch('subprocess.'+name, side_effect=AssertionError('native execution forbidden'))
            manager.start()
            self.addCleanup(manager.stop)
        manager = patch('validation.suffix5.calibration.verify_model',
                        side_effect=AssertionError('planning cannot check physical witnesses'))
        manager.start()
        self.addCleanup(manager.stop)

    def run_plan(self, results=None, admitted=None):
        admitted = self.admitted if admitted is None else admitted
        results = self.results if results is None else results
        registry = protocol_registry(admitted, results)
        output = []
        result = collection.plan_query_collection(admitted, registry, on_query=output.append)
        return result, output

    def assert_reference(self, admitted, rows, results):
        self.assertEqual([row['joined']['projection']['query_seq'] for row in rows], list(admitted.query_ids()))
        for row in rows:
            joined = row['joined']
            projection = joined['projection']
            originals = [dict(result=results[ordinal]) for span in projection['ranges']
                         for ordinal in range(span['logical_start'], span['logical_end'])]
            self.assertEqual(expanded(joined['aggregate']), aggregate_records(originals, with_audit=True))
            self.assertEqual(joined['bound_audit'], _bound_audit(projection['recorded_bound'],
                                                              joined['aggregate']['result']))

    def test_source_totals_original_query_order_and_cross_block_representative(self):
        result, rows = self.run_plan()
        self.assert_reference(self.admitted, rows, self.results)
        summary = result.summary()
        self.assertEqual(summary['queries'], len(self.admitted.query_ids()))
        self.assertEqual(summary['unique_logical_models'], self.catalogue['total_models'])
        self.assertEqual(summary['original_model_occurrences'],
                         self.admitted.commitment()['original_model_occurrences'])
        self.assertEqual(summary['complete_blocks'], len(self.catalogue['blocks']))
        self.assertEqual(summary['query_collection_rows_sha256'], hashlib.sha256(
            b''.join(plan.canonical(row)+b'\n' for row in rows)).hexdigest())
        self.assertEqual(list(result.iter_queries()), rows)
        # Query 12 uses segment B, whose first winner is inside a block won by A.
        row = next(row for row in rows if row['joined']['projection']['query_seq'] == 12)
        self.assertEqual(row['query_binding']['model_ordinal'], 10)
        report = self.registry.block_reports()[1]
        self.assertEqual(report['aggregate']['audit'][RANGES[2]][0][0], 7)
        self.assertNotEqual(row['query_binding']['model_ordinal'], 7)
        self.assertEqual(row['query_binding']['query_regime'], 0)

    def test_exact_single_ordinal_descriptor_binding_and_physical_deduplication(self):
        with patch.object(self.admitted.population, 'descriptors',
                          wraps=self.admitted.population.descriptors) as descriptors:
            result, rows = self.run_plan()
        requests, bindings = result.physical_requests(), result.query_bindings()
        self.assertGreater(sum(row['physical_witness_required'] for row in rows), len(requests))
        self.assertEqual(descriptors.call_count, len(requests))
        self.assertTrue(all(call.args[1] == call.args[0]+1 for call in descriptors.call_args_list))
        self.assertEqual(len({row['binding_id'] for row in bindings}), len(rows))
        for row in rows:
            joined, query_binding = row['joined'], row['query_binding']
            request = requests[query_binding['model_ordinal']]
            self.assertEqual(request['descriptor'], next(self.admitted.population.descriptors(
                query_binding['model_ordinal'], query_binding['model_ordinal']+1)))
            self.assertEqual(query_binding['descriptor_sha256'], plan.digest(request['descriptor']))
            self.assertEqual(query_binding['result_sha256'], plan.digest(joined['aggregate']['result']))
            self.assertEqual(query_binding['projection_sha256'], plan.digest(joined['projection']))
            self.assertEqual(request['result'], joined['aggregate']['result'])
        persisted = json.loads(plan.canonical(result.physical_request_rows()))
        self.assertTrue(all(type(row['model_ordinal']) is int for row in persisted))
        self.assertEqual([row['model_ordinal'] for row in persisted], sorted(requests))
        self.assertEqual({row['model_ordinal']: {key: row[key] for key in ('descriptor', 'result')}
                          for row in persisted}, requests)
        self.assertEqual(plan.digest(persisted), result.summary()['physical_request_rows_sha256'])
        self.assertEqual(len(plan.canonical(persisted)), result.summary()['physical_request_bytes'])

    def test_unique_request_count_and_exact_persistence_byte_caps(self):
        with patch.object(collection, 'MAX_PHYSICAL_REQUESTS', 1), \
             self.assertRaisesRegex(ValueError, 'request count cap'):
            self.run_plan()
        with patch.object(collection, 'MAX_PHYSICAL_REQUEST_BYTES', 2), \
             self.assertRaisesRegex(ValueError, 'request byte cap'):
            self.run_plan()
        result, expected = self.run_plan()
        size = result.summary()['physical_request_bytes']
        with patch.object(collection, 'MAX_PHYSICAL_REQUEST_BYTES', size):
            accepted, rows = self.run_plan()
            self.assertEqual(rows, expected)
            self.assertEqual(accepted.summary()['physical_request_bytes'], size)
        with patch.object(collection, 'MAX_PHYSICAL_REQUEST_BYTES', size-1), \
             self.assertRaisesRegex(ValueError, 'request byte cap'):
            self.run_plan()
        # Query count is not the unique-request cap. Repeated bindings sharing
        # ordinal zero and empty queries all still receive their bound audits.
        results = [dict(status='closed_infeasible') for _ in self.results]
        results[0] = attained()
        with patch.object(collection, 'MAX_PHYSICAL_REQUESTS', 1):
            result, rows = self.run_plan(results)
        self.assertEqual(result.summary()['unique_physical_requests'], 1)
        self.assertGreater(result.summary()['physical_query_bindings'], 1)
        self.assertEqual(len(rows), len(self.admitted.query_ids()))

    def test_attained_and_both_nonattainment_choose_first_correct_tie_run(self):
        for candidate, range_name in ((attained(), RANGES[2]), (secondary(), RANGES[1]),
                                      (primary(), RANGES[0])):
            results = [attained('100') for _ in self.results]
            results[2] = deepcopy(candidate)
            results[4] = deepcopy(candidate)
            result, rows = self.run_plan(results)
            self.assert_reference(self.admitted, rows, results)
            row = rows[0]
            self.assertEqual(row['joined']['aggregate']['audit'][range_name], [[2, 3], [4, 5]])
            self.assertEqual(row['query_binding']['query_regime'], 2)
            self.assertEqual(row['query_binding']['model_ordinal'], 2)
            self.assertEqual(result.physical_requests()[2]['result'], candidate)

    def test_original_repeated_family_action_bindings_and_ties_are_not_deduplicated(self):
        # This is a protocol variation of original occurrence metadata; it is
        # deliberately not presented as a completed real structural execution.
        index, logical = deepcopy(self.fx.index), deepcopy(self.fx.logical)
        row, link = index['queries'][0], logical['occurrence_bindings'][0]
        old_count = link['model_slots']
        row['family_ids'] *= 2
        row['actions'] = list(reversed(row['actions']))*2
        link['family_groups'] *= 2
        link['first_actions'] = deepcopy(row['actions'])
        link['model_slots'] *= 4
        link['thin_occurrence_sha256'] = plan.digest(row)
        logical['original_occurrence_model_slots'] += 3*old_count
        admitted = self.fx.admit(index, logical)
        results = [attained() for _ in range(admitted.population.plan()['total_models'])]
        result, rows = self.run_plan(results, admitted)
        self.assert_reference(admitted, rows, results)
        first = rows[0]
        self.assertEqual(len(first['joined']['projection']['ranges']), 8)
        self.assertEqual(first['joined']['aggregate']['audit'][RANGES[2]], [[0, old_count*4]])
        self.assertEqual(first['query_binding']['model_ordinal'], 10)
        self.assertEqual(result.summary()['original_model_occurrences'],
                         logical['original_occurrence_model_slots'])

    def test_bound_audit_runs_once_per_query_and_keeps_violated_or_missing_findings(self):
        index, logical = deepcopy(self.fx.index), deepcopy(self.fx.logical)
        for position, bound in ((0, None), (1, '1000000')):
            index['queries'][position]['bound'] = bound
            logical['occurrence_bindings'][position]['thin_occurrence_sha256'] = plan.digest(index['queries'][position])
        admitted = self.fx.admit(index, logical)
        with patch('validation.suffix5.occurrence_join._bound_audit', wraps=_bound_audit) as audit:
            result, rows = self.run_plan(admitted=admitted)
        self.assertEqual(audit.call_count, len(admitted.query_ids()))
        self.assertEqual([call.args for call in audit.call_args_list],
                         [(row['joined']['projection']['recorded_bound'], row['joined']['aggregate']['result'])
                          for row in rows])
        self.assertEqual(rows[0]['joined']['bound_audit']['bound_status'], 'missing_bound_for_nonempty_family')
        self.assertEqual(rows[1]['joined']['bound_audit']['bound_status'], 'violated')
        self.assertTrue(result.summary()['planning_complete'])
        self.assertLess(float(rows[1]['joined']['bound_audit']['bound_gap']), 0)

    def test_no_physical_authority_and_detached_outputs(self):
        result, rows = self.run_plan()
        for row in [result.summary(), *rows]:
            for field in ('physical_witness_verified', 'query_optimum_certified',
                          'full_population_complete', 'literal_G8_closed'):
                self.assertIs(row[field], False)
            self.assertTrue(row['status'].startswith('pending_'))
        request = result.physical_requests()
        request[next(iter(request))]['descriptor']['ordinal'] = -1
        result.query_bindings()[0]['binding_id'] = 'changed'
        result.summary()['queries'] = -1
        self.assertEqual(list(result.iter_queries()), rows)
        with self.assertRaises(AttributeError):
            result._summary = b'{}'

    def test_scheduling_only_foreign_and_subclass_inputs_reject_before_output(self):
        scheduling = receipts.CheckedRegistry(self.registry.metadata(), (), _token=receipts._ADMISSION)
        output = []
        with self.assertRaisesRegex(ValueError, 'cold reconciliation'):
            collection.plan_query_collection(self.admitted, scheduling, on_query=output.append)
        self.assertEqual(output, [])
        class PopulationSubclass(admission.AdmittedSuffixPopulation):
            pass
        class RegistrySubclass(receipts.CheckedRegistry):
            pass
        impostor = object.__new__(PopulationSubclass)
        for population, registry in (({}, self.registry), (impostor, self.registry),
                                     (self.admitted, {}), (self.admitted, object.__new__(RegistrySubclass))):
            with self.assertRaises(ValueError):
                collection.plan_query_collection(population, registry)
        for field in ('population', 'catalogue_sha256'):
            metadata = self.registry.metadata()
            if field == 'population':
                metadata[field]['case_sha256'] = '0'*64
            else:
                metadata[field] = '0'*64
            with self.assertRaisesRegex(ValueError, 'foreign registry'):
                collection.plan_query_collection(self.admitted, replace_registry(self.registry, metadata=metadata))

    def test_missing_duplicate_foreign_unresolved_or_uncommitted_reports_fail_closed(self):
        original = self.registry.block_reports()
        changed = []
        changed.append(original[:-1])
        changed.append(original+[original[0]])
        bad = deepcopy(original)
        bad[0]['range']['block_id'] = 999
        changed.append(bad)
        bad = deepcopy(original)
        bad[0].update(complete_certificates=False, unresolved_ordinals=[0], aggregate=None, segment_summaries=[])
        changed.append(bad)
        bad = deepcopy(original)
        bad[0]['verified_models'] -= 1
        changed.append(bad)
        for reports in changed:
            output = []
            with self.subTest(reports=reports[0]['range']), self.assertRaises(ValueError):
                collection.plan_query_collection(self.admitted,
                    replace_registry(self.registry, reports=reports), on_query=output.append)
            self.assertEqual(output, [])
        missing = receipts.make_registry(self.admitted, [])
        with self.assertRaisesRegex(ValueError, 'full canonical block coverage'):
            collection.plan_query_collection(self.admitted, missing)

    def test_fold_rechecks_summary_algebra_even_when_protocol_hashes_match(self):
        reports = self.registry.block_reports()
        reports[0]['segment_summaries'][0]['aggregate']['result'] = attained('999')
        metadata = self.registry.metadata()
        compact = receipts._compact_report(reports[0], metadata['blocks'][0]['entry_id'])
        metadata['blocks'][0] = compact
        metadata['entries'][0]['blocks'][0] = compact
        with self.assertRaises(ValueError):
            collection.plan_query_collection(self.admitted,
                replace_registry(self.registry, metadata=metadata, reports=reports))

    def test_stream_callback_mutation_and_cancellation_do_not_return_a_completed_plan(self):
        def mutate(row):
            row['query_binding']['model_ordinal'] = -1
            row['joined']['projection']['actions'].clear()
        clean, expected = self.run_plan()
        result = collection.plan_query_collection(self.admitted, self.registry, on_query=mutate)
        self.assertEqual(result.summary(), clean.summary())
        self.assertEqual(list(result.iter_queries()), expected)
        output = []
        class Cancelled(Exception):
            pass
        def cancel(row):
            output.append(row)
            raise Cancelled('stream interrupted')
        with patch.object(collection, 'QueryCollectionPlan', wraps=collection.QueryCollectionPlan) as factory:
            with self.assertRaises(Cancelled):
                collection.plan_query_collection(self.admitted, self.registry, on_query=cancel)
            factory.assert_not_called()
        self.assertEqual(len(output), 1)
        self.assertFalse(output[0]['query_optimum_certified'])
        def checkpoint():
            if len(output) == len(self.admitted.query_ids()):
                raise Cancelled('cancelled after final streamed query')
        output.clear()
        with self.assertRaises(Cancelled):
            collection.plan_query_collection(self.admitted, self.registry, on_query=output.append,
                                             before=checkpoint)
        self.assertEqual(len(output), len(self.admitted.query_ids()))

    def test_empty_recovery_requires_unchanged_original_v2_trace_and_returns_bound_partition(self):
        result, _ = self.run_plan()
        trace = plan.load(self.fx.fx.root/'capture/capture.json')['trace']
        self.assertEqual(trace['schema'], 'family5-hier-trace-v2')
        original = deepcopy(trace)
        with patch('validation.suffix5.checker._bound_audit', wraps=_bound_audit) as audit:
            partition = result.recover_empty_partition(trace)
        self.assertIs(type(partition), collection.EmptyOccurrencePartition)
        report = partition.report()
        recovered = report['recovered']
        self.assertEqual(report['population_sha256'], result.summary()['population_sha256'])
        self.assertEqual(recovered['empty_action_queries'], self.admitted.commitment()['empty_action_queries'])
        self.assertEqual(recovered['query_ids'], [event['seq'] for event in trace['events']
                                                if event['kind'] == 'query'])
        self.assertEqual(audit.call_count, recovered['empty_action_queries'])
        self.assertFalse(recovered['execution_authority'])
        self.assertFalse(recovered['certificate_authority'])
        self.assertEqual(trace, original)
        self.assertFalse(result.summary()['empty_partition_recovered'])
        with self.assertRaises(ValueError):
            result.recover_empty_partition(recovered)  # A returned report is not the source trace.
        bad = dict(schema='family5-hier-trace-v1', events=deepcopy(trace['events']))
        with self.assertRaisesRegex(ValueError, 'trace_digest_mismatch'):
            result.recover_empty_partition(bad)
        bad = deepcopy(trace)
        bad['events'][-1]['payload']['changed'] = True
        with self.assertRaisesRegex(ValueError, 'trace_digest_mismatch'):
            result.recover_empty_partition(bad)

    def test_empty_recovery_passes_only_admitted_pins_to_bridge(self):
        result, _ = self.run_plan()
        trace = plan.load(self.fx.fx.root/'capture/capture.json')['trace']
        # Protocol wiring only, explicitly not a successful v2 recovery claim.
        bridge_return = dict(protocol_fake_not_execution_authority=True,
                             execution_authority=False, certificate_authority=False)
        with patch.object(collection, 'recover_empty_occurrences', return_value=bridge_return) as bridge:
            partition = result.recover_empty_partition(trace)
        self.assertIs(type(partition), collection.EmptyOccurrencePartition)
        self.assertEqual(bridge.call_args.args, (trace, self.admitted.query_ids()))
        self.assertEqual({key: value for key, value in bridge.call_args.kwargs.items() if key != 'before'},
            dict(trace_sha256=self.fx.index['trace_sha256'], exact_queries=len(self.admitted.query_ids()),
                 empty_action_queries=self.fx.index['empty_action_queries'],
                 empty_action_sha256=self.fx.index['empty_action_sha256']))
        report = partition.report()
        self.assertEqual(report['population_sha256'], result.summary()['population_sha256'])
        self.assertEqual(report['recovered'], bridge_return)
        self.assertFalse(report['physical_witness_verified'])
        report['recovered']['execution_authority'] = True
        self.assertFalse(partition.report()['recovered']['execution_authority'])


class EmptyLanguageCollectionTests(unittest.TestCase):
    def admit_case(self, number):
        fixture = logical_fixtures.LogicalModels()
        index, trusted, summary, checked = fixture.inputs(fixture.rows()[number])
        logical = count_logical_models(index, trusted, summary)['logical_model_plan']
        # Genuine independent family/trace, injected only at cold protocol boundary.
        with patch.object(admission.suffix_census, 'completed_inputs',
                          return_value=(index, trusted, {}, {'capture_sha256': 'a'*64})), \
             patch.object(admission.model_preview, 'logical_input', return_value=logical):
            admitted = admission.admit_population(None, SimpleNamespace(), checked.bundle, time.monotonic()+10)
        return admitted

    def test_zero_length_segments_are_distinct_from_all_excluded_nonempty_queries(self):
        admitted = self.admit_case(0)
        descriptors = list(admitted.population.descriptors())
        results = [dict(status='graph_unreachable' if row['logical_identity']['arrival_bands'] is None
                        else 'closed_infeasible') for row in descriptors]
        output = []
        result = collection.plan_query_collection(admitted, protocol_registry(admitted, results),
                                                  on_query=output.append)
        self.assertGreater(result.summary()['zero_length_queries'], 0)
        self.assertGreater(result.summary()['all_excluded_nonempty_queries'], 0)
        self.assertEqual(result.physical_requests(), {})
        for row in output:
            self.assertEqual(row['joined']['aggregate']['result'], dict(status='empty_restricted_family'))
            self.assertFalse(row['physical_witness_required'])
            self.assertIsNone(row['query_binding']['model_ordinal'])
            self.assertIsNone(row['query_binding']['descriptor_sha256'])
            self.assertEqual(row['joined']['projection']['legal_completion_language_empty'],
                             row['joined']['aggregate']['end'] == 0)
        QueryCollectionTests.assert_reference(self, admitted, output, results)

    def test_entire_empty_population_requires_no_blocks_or_model_descriptors(self):
        admitted = self.admit_case(4)
        with patch.object(admitted.population, 'descriptors', side_effect=AssertionError('no models')):
            result = collection.plan_query_collection(admitted, receipts.make_registry(admitted, []))
        self.assertEqual(result.summary()['unique_logical_models'], 0)
        self.assertEqual(result.summary()['queries'], 0)
        self.assertEqual(result.summary()['complete_blocks'], 0)
        self.assertEqual(result.physical_requests(), {})


if __name__ == '__main__':
    unittest.main()
