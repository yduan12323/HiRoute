"""Tiny genuine checked families and explicitly protocol-fake receipt factories.

These fixtures never claim a real historical invocation, server run, or final
C01 result. Guard executions are mocked; recovery integration uses genuine
tiny hand certificates and the unchanged physical verifier.
"""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from experiments.time_cut_v2.recorded_real import final_collector as runner
from experiments.time_cut_v2.recorded_real import plan as binding, query_collection as collection
from experiments.time_cut_v2.recorded_real import query_witnesses, runtime, window_receipts as receipts
from tests import test_suffix_query_collection as fixtures
from tests.test_suffix_occurrence_join import attained, primary
from tests.test_suffix_window_plan import population
from tests import test_suffix_query_witnesses as witness_fixtures


def fake_physical(plan, *, change=lambda row: None, finish=lambda coverage: None):
    """Synthetic transport only, deliberately not a certificate verifier."""
    def replay(admitted, registry, requested, emit, **kwargs):
        summary, compact = plan.summary(), []
        for ordinal, request in sorted(requested.items()):
            provenance = dict(population_sha256=summary['population_sha256'],
                registry_sha256=summary['registry_metadata_sha256'],
                physical_request_rows_sha256=summary['physical_request_rows_sha256'])
            row = dict(schema='hiroute-selected-query-model-witness-v1', provisional=True,
                model_ordinal=ordinal, descriptor=deepcopy(request['descriptor']), result=deepcopy(request['result']),
                model_sha256='b'*64, record_sha256='c'*64, provenance=provenance,
                physical_receipt=dict(result=request['result'], physical_witness_verified=True,
                    physical_audit=dict(kind='protocol-fake-approach', J='1000000', Q_total='1', H=1, pi=[])),
                protocol_fake_not_execution_authority=True)
            change(row)
            compact.append(dict(model_ordinal=row['model_ordinal'],
                descriptor_sha256=binding.digest(row['descriptor']), model_sha256=row['model_sha256'],
                record_sha256=row['record_sha256'], result_sha256=binding.digest(row['result']),
                provenance_sha256=binding.digest(row['provenance']), receipt_sha256=binding.digest(row)))
            emit(row)
        coverage = dict(selected_replay_complete=True, selected_models=len(requested), witnesses=compact,
            population_sha256=summary['population_sha256'], registry_sha256=summary['registry_metadata_sha256'],
            physical_request_rows_sha256=summary['physical_request_rows_sha256'],
            physical_request_bytes=summary['physical_request_bytes'], archives=[])
        finish(coverage)
        return coverage
    return replay


class RecoveryAssemblyTests(unittest.TestCase):
    """Full tiny collector pipeline, with protocol-only registry provenance."""
    def setUp(self):
        self.fx = witness_fixtures.RecoveryWitnessTests(); self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)

    def collect(self, **options):
        admitted, registry, _ = self.fx.fixture(**options)
        plan = collection.plan_query_collection(admitted, registry)
        partition = plan.recover_empty_partition(witness_fixtures.hand_query_trace(admitted._index['queries']))
        writer = runtime.BoundedEvidenceWriter(self.fx.root/'output', 16*1024**2, profile_name='test')
        self.addCleanup(writer.close)
        physical = runner.stream_physical(plan, admitted, registry, writer,
                                          deadline=time.monotonic()+30, before=lambda: None)
        queries = []
        report = runner.emit_queries(plan, partition, physical, queries.append)
        return plan, physical, queries, report, writer

    def test_recovered_selected_segment_loser_and_empty_partition_complete(self):
        plan, physical, queries, report, writer = self.collect(interrupted=(0, 1))
        self.assertEqual(set(physical['receipts']), {0, 3})
        self.assertEqual(report['total_query_events'], 3)
        self.assertEqual([row['query_seq'] for row in queries], [0, 1, 2])
        nonempty = {row['query_seq'] for row in queries if row['occurrence_kind'] == 'nonempty_actions'}
        empty = {row['query_seq'] for row in queries if row['occurrence_kind'] == 'empty_actions'}
        self.assertEqual((nonempty, empty), ({0, 1}, {2}))
        self.assertTrue(nonempty.isdisjoint(empty))
        self.assertEqual(len(nonempty)+len(empty), report['total_query_events'])
        rows = [json.loads(line) for line in (writer.root/'physical-witnesses.jsonl').read_bytes().splitlines()]
        loser = next(row for row in rows if row['model_ordinal'] == 0)
        self.assertEqual(loser['result']['status'], 'secondary_unattained')
        self.assertTrue(loser['physical_receipt']['physical_witness_verified'])
        self.assertEqual(len(loser['provenance']['source_rows']), 2)
        self.assertEqual(loser['provenance']['physical_request_rows_sha256'],
                         plan.summary()['physical_request_rows_sha256'])
        self.assertTrue(report['complete'])
        self.assertTrue(all(report[key] is False for key in runner.FALSE_AUTHORITY))

    def test_exact_only_intermediate_selected_leaf_still_has_fresh_physical_check(self):
        _, _, _, report, writer = self.collect(exact_only=True, complete_history=True)
        rows = [json.loads(line) for line in (writer.root/'physical-witnesses.jsonl').read_bytes().splitlines()]
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row['physical_receipt']['physical_witness_verified'] for row in rows))
        self.assertTrue(all(len(row['provenance']['source_rows']) == 2 for row in rows))
        self.assertTrue(report['complete'])

    def test_late_recovery_ancestor_corruption_prevents_sealing(self):
        admitted, registry, _ = self.fx.fixture()
        plan = collection.plan_query_collection(admitted, registry)
        pin = registry.metadata()['entries'][0]['dependencies'][1]
        path = Path(pin['path']); content = bytearray(path.read_bytes())
        content[-8] ^= 1; path.write_bytes(content)
        writer = runtime.BoundedEvidenceWriter(self.fx.root/'output', 16*1024**2, profile_name='test')
        self.addCleanup(writer.close)
        with self.assertRaises(ValueError):
            runner.stream_physical(plan, admitted, registry, writer,
                                   deadline=time.monotonic()+30, before=lambda: None)
        self.assertFalse((writer.root/'physical-witnesses.jsonl').exists())
        with self.assertRaises(ValueError): writer.finalize()


class AssemblyTests(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.QueryCollectionTests()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.trace = binding.load(self.fx.fx.fx.root/'capture/capture.json')['trace']
        self.counter = 0

    def planned(self, results=None):
        plan, rows = self.fx.run_plan(results)
        return plan, plan.recover_empty_partition(self.trace), rows

    def writer(self):
        self.counter += 1
        writer = runtime.BoundedEvidenceWriter(self.root/str(self.counter), 16*1024**2, profile_name='test')
        self.addCleanup(writer.close)
        return writer

    def physical(self, plan, **kwargs):
        writer = self.writer()
        with patch.object(query_witnesses, 'replay_selected_witnesses', fake_physical(plan, **kwargs)):
            result = runner.stream_physical(plan, self.fx.admitted, self.fx.registry, writer,
                                           deadline=time.monotonic()+20, before=lambda: None)
        return result, writer

    def test_exact_mixed_order_count_bindings_ties_and_receipt_pointers(self):
        plan, partition, original = self.planned()
        physical, writer = self.physical(plan)
        rows = []
        result = runner.emit_queries(plan, partition, physical, rows.append)
        self.assertEqual([row['query_seq'] for row in rows], partition.report()['recovered']['query_ids'])
        self.assertEqual(result['total_query_events'], len(rows))
        nonempty = [row for row in rows if row['occurrence_kind'] == 'nonempty_actions']
        self.assertEqual([row['joined'] for row in nonempty], [row['joined'] for row in original])
        self.assertEqual([row['query_binding'] for row in nonempty], plan.query_bindings())
        self.assertEqual(result['original_model_occurrences'], plan.summary()['original_model_occurrences'])
        self.assertEqual(result['query_collection_rows_sha256'], plan.summary()['query_collection_rows_sha256'])
        raw = (writer.root/'physical-witnesses.jsonl').read_bytes()
        for row in nonempty:
            receipt = row['physical_receipt']
            if receipt is None:
                continue
            pointer = receipt['pointer']
            part = raw[pointer['byte_offset']:pointer['byte_offset']+pointer['size_bytes']]
            self.assertEqual(hashlib.sha256(part).hexdigest(), pointer['row_sha256'])
            self.assertEqual(binding.digest(json.loads(part)), pointer['receipt_sha256'])
            self.assertEqual(json.loads(part)['model_ordinal'], row['query_binding']['model_ordinal'])
        self.assertTrue(result['complete'])
        for flag in runner.FALSE_AUTHORITY:
            self.assertFalse(result[flag])

    def test_counterexample_and_missing_bound_are_complete_findings(self):
        for factory in (attained, primary):
            values = [factory('-100000') for _ in self.fx.results]
            plan, partition, _ = self.planned(values)
            physical, _ = self.physical(plan)
            rows = []
            result = runner.emit_queries(plan, partition, physical, rows.append)
            self.assertTrue(result['complete'])
            self.assertGreater(result['bound_counterexample_queries'], 0)
            self.assertFalse(result['single_C01_case_accepted'])
            violated = next(row for row in rows if row['bound_counterexample'])
            self.assertTrue(violated['bound_audit']['bound_gap'].startswith('-'))
            self.assertEqual(violated['physical_receipt']['physical_point']['J'], '1000000')
            self.assertFalse(violated['point_level_counterexample_claimed'])
        # Preserve a genuine admitted query's missing recorded bound by using
        # the fixture's existing protocol-boundary admission, not a fake family.
        bad_index = deepcopy(self.fx.fx.index)
        bad_index['queries'][0]['bound'] = None
        logical = deepcopy(self.fx.fx.logical)
        logical['occurrence_bindings'][0]['thin_occurrence_sha256'] = binding.digest(bad_index['queries'][0])
        admitted = self.fx.fx.admit(index=bad_index, logical=logical)
        values = [attained() for _ in admitted.population.descriptors()]
        plan, _ = self.fx.run_plan(values, admitted=admitted)
        partition = plan.recover_empty_partition(self.trace)
        physical, _ = self.physical(plan)
        result = runner.emit_queries(plan, partition, physical, lambda _: None)
        self.assertGreater(result['missing_bound_queries'], 0)
        self.assertTrue(result['complete'])
        self.assertFalse(result['single_C01_case_accepted'])

    def test_physical_hash_bytes_and_completed_compact_map_are_exact(self):
        plan, _, _ = self.planned()
        for key in ('physical_request_rows_sha256', 'physical_request_bytes', 'selected_models', 'witnesses'):
            def finish(value, key=key):
                value[key] = [] if key == 'witnesses' else 'wrong'
            writer = self.writer()
            with patch.object(query_witnesses, 'replay_selected_witnesses', fake_physical(plan, finish=finish)), \
                 self.assertRaises(ValueError):
                runner.stream_physical(plan, self.fx.admitted, self.fx.registry, writer,
                                       deadline=time.monotonic()+20, before=lambda: None)
            self.assertFalse((writer.root/'physical-witnesses.jsonl').exists())
            with self.assertRaises(ValueError): writer.finalize()

    def test_actual_request_array_hash_and_bytes_must_match_plan(self):
        plan, _, _ = self.planned()
        for field, value in (('physical_request_rows_sha256', '0'*64), ('physical_request_bytes', 1)):
            original = plan.summary(); changed = dict(original, **{field: value})
            with patch.object(collection.QueryCollectionPlan, 'summary', return_value=changed), \
                 self.assertRaises(ValueError): self.physical(plan)

    def test_zero_languages_and_all_excluded_languages_stay_distinct(self):
        admitted = fixtures.EmptyLanguageCollectionTests().admit_case(0)
        descriptors = list(admitted.population.descriptors())
        values = [dict(status='graph_unreachable' if row['logical_identity']['arrival_bands'] is None
                       else 'closed_infeasible') for row in descriptors]
        registry = fixtures.protocol_registry(admitted, values)
        plan = collection.plan_query_collection(admitted, registry)
        source = fixtures.logical_fixtures.LogicalModels()
        trace = fixtures.logical_fixtures.capture(source.rows()[0], True)['trace']
        partition = plan.recover_empty_partition(trace)
        physical, _ = self.physical(plan)
        rows = []
        summary = runner.emit_queries(plan, partition, physical, rows.append)
        self.assertGreater(summary['zero_length_queries'], 0)
        self.assertGreater(summary['all_excluded_nonempty_queries'], 0)
        self.assertEqual(summary['unique_physical_requests'], 0)
        self.assertTrue(summary['complete'])

    def test_foreign_duplicate_wrong_descriptor_and_wrong_result_receipts_reject(self):
        plan, _, _ = self.planned()
        first = min(plan.physical_requests())
        mutations = [lambda row: row.update(model_ordinal=999999),
                     lambda row: row.update(model_ordinal=first),
                     lambda row: row['descriptor'].update(ordinal=-1),
                     lambda row: row.update(result=attained('999'))]
        for position, change in enumerate(mutations):
            with self.subTest(position=position), self.assertRaises(ValueError): self.physical(plan, change=change)

    def test_late_physical_failure_never_seals_file(self):
        plan, _, _ = self.planned()
        def late(_): raise TimeoutError('last archive bytes failed')
        writer = self.writer()
        with patch.object(query_witnesses, 'replay_selected_witnesses', fake_physical(plan, finish=late)), \
             self.assertRaises(TimeoutError):
            runner.stream_physical(plan, self.fx.admitted, self.fx.registry, writer,
                                   deadline=time.monotonic()+20, before=lambda: None)
        self.assertFalse((writer.root/'physical-witnesses.jsonl').exists())

    def test_missing_or_foreign_physical_map_rejects_query_collection(self):
        plan, partition, _ = self.planned()
        physical, _ = self.physical(plan)
        for mode in ('missing', 'foreign', 'wrong-binding'):
            bad = deepcopy(physical); ordinal = min(bad['receipts'])
            if mode == 'missing': del bad['receipts'][ordinal]
            elif mode == 'foreign': bad['receipts'][999999] = bad['receipts'][ordinal]
            else: bad['receipts'][ordinal]['result_sha256'] = '0'*64
            with self.assertRaises(ValueError): runner.emit_queries(plan, partition, bad, lambda _: None)

    def test_missing_duplicate_foreign_and_reordered_query_ids_reject(self):
        plan, partition, _ = self.planned()
        physical, _ = self.physical(plan)
        for mode in ('missing', 'duplicate', 'foreign', 'reorder'):
            report = partition.report(); ids = report['recovered']['query_ids']
            if mode == 'missing': ids.pop()
            elif mode == 'duplicate': ids[1] = ids[0]
            elif mode == 'foreign': ids[0] = 999999
            else: ids[0], ids[1] = ids[1], ids[0]
            bad = collection.EmptyOccurrencePartition(report, _token=collection._PLANNING)
            with self.assertRaises(ValueError): runner.emit_queries(plan, bad, physical, lambda _: None)

    def test_reemitted_rows_and_binding_digest_are_checked(self):
        plan, partition, rows = self.planned()
        physical, _ = self.physical(plan)
        altered = deepcopy(rows); altered[0]['joined']['aggregate']['audit']['extra'] = True
        with patch.object(collection.QueryCollectionPlan, 'iter_queries', return_value=iter(altered)), \
             self.assertRaisesRegex(ValueError, 'query-row digest'):
            runner.emit_queries(plan, partition, physical, lambda _: None)
        altered = deepcopy(rows); altered[1]['query_binding'] = altered[0]['query_binding']
        with patch.object(collection.QueryCollectionPlan, 'iter_queries', return_value=iter(altered)), \
             self.assertRaises(ValueError): runner.emit_queries(plan, partition, physical, lambda _: None)

    def test_cancellation_during_query_stream_poisoned_and_unpublished(self):
        plan, partition, _ = self.planned()
        physical, _ = self.physical(plan)
        writer = self.writer()
        def producer(sink):
            def emit(row):
                for part in runner.checked_chunks(runner.domain.chunks(row), lambda: None): sink(part)
                raise TimeoutError('late query cancellation')
            runner.emit_queries(plan, partition, physical, emit)
        with self.assertRaises(TimeoutError): writer.write_from_callback('query-results.jsonl', producer)
        self.assertFalse((writer.root/'query-results.jsonl').exists())
        with self.assertRaises(ValueError): writer.finalize()


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def args(self):
        argv = []
        for name in receipts.COMMON_PATHS + ('source_policy', 'registry', 'registry_return',
                                             'runtime_return_output', 'collector_output'):
            argv.extend(('--'+name.replace('_', '-'), str(self.root/name)))
        for name in receipts.COMMON_PINS + ('source_policy_sha', 'registry_sha', 'registry_return_sha'):
            argv.extend(('--'+name.replace('_', '-'), 'a'*(40 if name == 'source_commit' else 64)))
        argv.extend(('--worker-cpus', '1', '2', '3', '4', '5', '--cpu', '0', '--attempt-dir', str(self.root/'attempt')))
        return runner.parser().parse_args(argv)

    @contextmanager
    def dependencies(self, result=None):
        with patch.object(runner.resource, 'getrlimit', return_value=(1024**3, resource.RLIM_INFINITY)), \
             patch.object(runner.resource, 'setrlimit') as limits, \
             patch.object(runner, '_live_checks') as live, \
             patch.object(runner, 'check_invocation_origin', return_value={'controller_module': runner.MODULE}), \
             patch.object(runner.suffix_census, 'check_sources', return_value={}) as source, \
             patch.object(runner.suffix_window, 'source_policy', return_value={}), \
             patch.object(runner, 'load_registry', return_value=(object(), object())) as registry, \
             patch.object(runner, 'retained_snapshot', return_value={}), \
             patch.object(runner, 'check_case'), \
             patch.object(runner, 'run_phase', return_value=result or {'status': 'failed'}) as phase, \
             patch.object(runner, 'read_phase_result', return_value={'status': 'completed'}) as cold:
            yield SimpleNamespace(limits=limits, live=live, source=source, registry=registry, phase=phase, cold=cold)

    def fake_completed(self, args):
        def launch(*_, **__):
            args.attempt_dir.mkdir()
            for name in ('request.json', 'result.json', 'supervisor-decision.json', 'decision.json'):
                (args.attempt_dir/name).write_bytes(b'{}\n')
            writer = runtime.BoundedEvidenceWriter(args.attempt_dir/'evidence',
                runtime.FINAL_COLLECTOR.worker_evidence_bytes, profile_name=runtime.FINAL_COLLECTOR.name)
            for name in sorted(runner.EVIDENCE_FILES):
                doc = dict(schema='hiroute-final-collector-summary-v1', complete=True,
                    resource_plan=runner.resource_plan(args.worker_cpus), single_C01_case_bound_status='counterexample',
                    single_C01_case_bound_valid=False, single_C01_case_accepted=False, **runner.FALSE_AUTHORITY)
                writer.write(name, runner.domain.chunks(doc))
            writer.finalize()
            return dict(status='completed', actual_not_reconstructed='fixture marker',
                verified_manifest_sha256=binding.pin(args.attempt_dir/'evidence/__manifest.json')['sha256'])
        return launch

    def test_profile_entry_deadline_and_explicit_module_wiring(self):
        args = self.args()
        with self.dependencies() as dep: result = runner.controller(args)
        self.assertEqual(result['status'], 'unaccepted')
        self.assertEqual(dep.limits.call_args.args[1][0], 512*1024**2)
        call = dep.phase.call_args
        self.assertIs(call.kwargs['profile'], runtime.FINAL_COLLECTOR)
        self.assertEqual(call.kwargs['deadline_monotonic']-call.kwargs['entry_monotonic'], 3600)
        self.assertEqual(call.kwargs['worker_cpus'], (1, 2, 3, 4, 5))
        self.assertEqual(call.args[0][3], runner.MODULE)
        parsed = runner.parser().parse_args(call.args[0][4:])
        self.assertEqual(runner.input_context(parsed), runner.input_context(args))

    def test_incomplete_registry_blocks_launch(self):
        args = self.args()
        with self.dependencies() as dep:
            dep.registry.side_effect = ValueError('final registry lacks full canonical block coverage')
            with self.assertRaisesRegex(ValueError, 'full canonical'): runner.controller(args)
        dep.phase.assert_not_called()

    def test_full_registry_gate_checks_actual_canonical_ranges_and_counts(self):
        catalogue = population()
        commitment = dict(block_plan_sha256=binding.digest(catalogue),
            source_bundle_sha256=catalogue['source_bundle_sha256'], case_sha256=catalogue['case_sha256'],
            logical_plan_sha256=catalogue['logical_plan_sha256'], unique_logical_models=695712,
            queries=12172, original_model_occurrences=7652832, empty_action_queries=9666)
        scope = receipts.ReceiptScope(catalogue, commitment, _token=receipts._ADMISSION)
        # Explicit fake receipt metadata; this tests only preflight coverage.
        metadata = dict(population=commitment, blocks=[dict(range=row) for row in catalogue['blocks']],
                        completed_models=695712, entries=[])
        registry = receipts.CheckedRegistry(metadata, (), _token=receipts._ADMISSION)
        self.assertEqual(runner.require_complete_registry(scope, registry), commitment)
        for mutation in ('missing', 'duplicate', 'reordered', 'count'):
            bad = deepcopy(metadata)
            if mutation == 'missing': bad['blocks'].pop()
            elif mutation == 'duplicate': bad['blocks'][1] = bad['blocks'][0]
            elif mutation == 'reordered': bad['blocks'].reverse()
            else: bad['completed_models'] -= 1
            changed = receipts.CheckedRegistry(bad, (), _token=receipts._ADMISSION)
            with self.assertRaises(ValueError): runner.require_complete_registry(scope, changed)

    def test_actual_return_retained_and_case_counterexample_is_completed(self):
        args = self.args()
        with self.dependencies() as dep:
            dep.phase.side_effect = self.fake_completed(args)
            result = runner.controller(args)
        self.assertEqual(result['status'], 'collected')
        self.assertEqual(json.loads(args.runtime_return_output.read_bytes())['actual_not_reconstructed'], 'fixture marker')
        self.assertFalse(result['single_C01_case_accepted'])
        self.assertEqual(json.loads(args.collector_output.read_bytes())['status'], 'collected')
        self.assertEqual(dep.cold.call_args.kwargs['successful_return'],
                         json.loads(args.runtime_return_output.read_bytes()))

    def test_first_postreturn_timeout_preserves_actual_object_without_faking_file(self):
        args = self.args(); actual = {'status': 'completed', 'actual': 'unpersisted'}
        returned = False
        def launch(*_, **__):
            nonlocal returned
            returned = True
            return actual
        def live(*_, **__):
            if returned: raise TimeoutError('postreturn deadline')
        with self.dependencies() as dep:
            dep.phase.side_effect = launch; dep.live.side_effect = live
            result = runner.controller(args)
        self.assertEqual(result['status'], 'collection_acceptance_failed')
        self.assertIs(result['runtime_result'], actual)
        self.assertFalse(args.runtime_return_output.exists())
        self.assertFalse(args.collector_output.exists())

    def test_late_source_or_evidence_change_never_accepts(self):
        for kind in ('source', 'evidence', 'actual-return', 'decision', 'journal', 'new-rejection'):
            args = self.args()
            args.attempt_dir = self.root/('attempt-'+kind)
            args.runtime_return_output = self.root/('return-'+kind)
            args.collector_output = self.root/('accept-'+kind)
            with self.dependencies() as dep:
                dep.phase.side_effect = self.fake_completed(args)
                if kind == 'source':
                    def source(*_):
                        if args.runtime_return_output.exists(): raise ValueError('late source changed')
                        return {}
                    dep.source.side_effect = source
                else:
                    def cold(*_, **__):
                        path = {'actual-return': args.runtime_return_output,
                            'decision': args.attempt_dir/'decision.json',
                            'journal': args.attempt_dir/'evidence/__journal.jsonl',
                            'new-rejection': args.attempt_dir/'rejection.json'}.get(kind,
                                args.attempt_dir/'evidence/query-results.jsonl')
                        path.write_bytes(b'changed')
                        return {'status': 'completed'}
                    dep.cold.side_effect = cold
                result = runner.controller(args)
            self.assertEqual(result['status'], 'collection_acceptance_failed')
            self.assertTrue(args.runtime_return_output.exists())
            self.assertFalse(args.collector_output.exists())

    def test_late_acceptance_mutation_is_revoked(self):
        args = self.args()
        write = runner.suffix_window._exclusive_json
        def changed(path, *a, **kw):
            write(path, *a, **kw)
            if path == args.collector_output:
                path.write_bytes(b'{}\n')
        with self.dependencies() as dep, patch.object(runner.suffix_window, '_exclusive_json', side_effect=changed):
            dep.phase.side_effect = self.fake_completed(args)
            result = runner.controller(args)
        self.assertEqual(result['status'], 'collection_acceptance_failed')
        self.assertFalse(args.collector_output.exists())
        self.assertTrue(args.runtime_return_output.exists())

    def test_return_publication_failure_preserves_actual_object_and_bytes(self):
        args = self.args(); actual = {'status': 'completed', 'actual': 'keep me'}
        write = runner.suffix_window._exclusive_json
        def late(*a, **kw):
            write(*a, **kw)
            raise OSError('late publication sync')
        with self.dependencies(actual), patch.object(runner.suffix_window, '_exclusive_json', side_effect=late):
            result = runner.controller(args)
        self.assertIs(result['runtime_result'], actual)
        self.assertEqual(json.loads(args.runtime_return_output.read_bytes()), actual)
        self.assertFalse(args.collector_output.exists())

    def test_identity_checks_reject_changed_same_size_file_and_symlink_parent(self):
        parent = self.root/'parent'; parent.mkdir(); path = parent/'data'; path.write_bytes(b'abc')
        snapshot = {str(path): runner.file_identity(path)}
        path.write_bytes(b'def')
        with self.assertRaises(ValueError): runner.check_snapshot(snapshot, lambda: None)
        snapshot = {str(path): runner.file_identity(path)}
        moved = self.root/'moved'; parent.rename(moved); parent.symlink_to(moved, target_is_directory=True)
        with self.assertRaises(ValueError): runner.check_snapshot(snapshot, lambda: None)

    def test_origin_is_explicit_and_import_has_no_math_or_optimizer(self):
        origin = runner.check_invocation_origin()
        self.assertEqual(origin['controller_module'], runner.MODULE)
        self.assertTrue(origin['controller_path'].endswith('/final_collector.py'))
        with patch.object(runner, '__file__', runner.suffix_window.__file__), self.assertRaises(ValueError):
            runner.check_invocation_origin()
        command = "from experiments.time_cut_v2.recorded_real import final_collector as r; import sys; " \
                  "print([n for n in sys.modules if n == 'validation' or n.startswith(('validation.', 'timecut5')) " \
                  "or n.split('.')[0] in ('numpy', 'scipy', 'sympy')]); sys.meta_path.insert(0, r.suffix_census.NoOptimization()); " \
                  "import scipy"
        result = subprocess.run([sys.executable, '-B', '-c', command], cwd=binding.ROOT,
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.stdout.strip(), '[]')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('forbids producer/optimizer scipy', result.stderr)

class HistoricalContinuityTests(unittest.TestCase):
    """Filesystem metadata fixtures only, never historical execution proof."""

    def fixture(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        values = {}
        for name in receipts.COMMON_PATHS + ('registry', 'registry_return', 'source_policy'):
            path = root/name
            if name.endswith('_attempt'):
                path.mkdir()
            else:
                path.write_bytes(b'{}\n')
            values[name] = path
        args = SimpleNamespace(**values)
        old = root/'old-window'; old.mkdir()
        attempts = (args.replay_attempt, args.logical_attempt, old)
        for attempt in attempts:
            (attempt/'evidence').mkdir()
            (attempt/'request.json').write_bytes(b'{}\n')
            (attempt/'spool').write_bytes(b'log')
            (attempt/'evidence'/'__journal.jsonl').write_bytes(b'journal')
        proof = old/'evidence'/'proof'; proof.write_bytes(b'proof')
        entry = dict(attempt=str(old), dependencies=[dict(path=str(proof))])
        registry = SimpleNamespace(metadata=lambda: dict(entries=[entry]))
        return args, registry, attempts

    def test_complete_historical_trees_and_directory_identities_are_retained(self):
        args, registry, attempts = self.fixture()
        snapshot = runner.retained_snapshot(args, registry, lambda: None)
        for attempt in attempts:
            for path in (attempt, attempt/'evidence', attempt/'request.json',
                         attempt/'spool', attempt/'evidence'/'__journal.jsonl'):
                self.assertIn(str(path.absolute()), snapshot)
                self.assertEqual(len(snapshot[str(path.absolute())]), 7)
        runner.check_snapshot(snapshot, lambda: None)

    def test_old_journals_controls_and_spools_reject_mutation(self):
        for number in range(3):
            for relative in ('request.json', 'spool', 'evidence/__journal.jsonl'):
                with self.subTest(attempt=number, relative=relative):
                    args, registry, attempts = self.fixture()
                    snapshot = runner.retained_snapshot(args, registry, lambda: None)
                    (attempts[number]/relative).write_bytes(b'changed')
                    with self.assertRaises(ValueError):
                        runner.check_snapshot(snapshot, lambda: None)

    def test_unlisted_additions_and_removals_change_tracked_directories(self):
        for mutation in ('add-root', 'add-nested', 'remove'):
            args, registry, attempts = self.fixture()
            snapshot = runner.retained_snapshot(args, registry, lambda: None)
            old = attempts[-1]
            if mutation == 'add-root':
                (old/'rejection.json').write_bytes(b'{}\n')
            elif mutation == 'add-nested':
                (old/'evidence'/'foreign').write_bytes(b'new')
            else:
                (old/'spool').unlink()
            with self.subTest(mutation=mutation), self.assertRaises((ValueError, OSError)):
                runner.check_snapshot(snapshot, lambda: None)

    def test_same_size_write_with_restored_mtime_rejects(self):
        args, registry, attempts = self.fixture()
        path = attempts[-1]/'spool'
        snapshot = runner.retained_snapshot(args, registry, lambda: None)
        original = path.stat()
        path.write_bytes(b'new')
        os.utime(path, ns=(original.st_atime_ns, original.st_mtime_ns))
        with self.assertRaises(ValueError):
            runner.check_snapshot(snapshot, lambda: None)

    def test_old_directory_substitution_and_symlink_parent_reject(self):
        for symlink in (False, True):
            args, registry, attempts = self.fixture()
            old = attempts[-1]
            snapshot = runner.retained_snapshot(args, registry, lambda: None)
            moved = old.with_name('moved'); old.rename(moved)
            if symlink:
                old.symlink_to(moved, target_is_directory=True)
            else:
                old.mkdir()
            with self.subTest(symlink=symlink), self.assertRaises((ValueError, OSError)):
                runner.check_snapshot(snapshot, lambda: None)

    def test_shared_historical_attempt_inventory_is_taken_once(self):
        args, registry, attempts = self.fixture()
        entry = registry.metadata()['entries'][0]
        repeated = SimpleNamespace(metadata=lambda: dict(entries=[entry, entry]))
        with patch.object(runner, 'attempt_snapshot', wraps=runner.attempt_snapshot) as inventory:
            snapshot = runner.retained_snapshot(args, repeated, lambda: None)
        self.assertEqual(inventory.call_count, len(attempts))
        runner.check_snapshot(snapshot, lambda: None)


if __name__ == '__main__':
    unittest.main()
