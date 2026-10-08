"""Tiny synthetic completed-source receipts; no optimizer or real C01 execution.

The fake source deliberately emits synthetic checked dispositions. These tests
exercise the provenance boundary, not the truth of those dispositions. Genuine
small family/population admission fixtures are used, never fake CheckedBundle.
"""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import os
from pathlib import Path
import tempfile
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from experiments.time_cut_v2.recorded_real import block_archive, domain, plan, runtime
from experiments.time_cut_v2.recorded_real import window_receipts as wr
from experiments.time_cut_v2.recorded_real.lp_stream_jobs import LPStreamJob
from tests import test_indexed_suffix_population as population_fixtures
from tests import test_c01_variant_scope as variant_fixtures
from validation.capture5.containers import detach_json
from validation.suffix5.aggregate_stream import StreamAggregator
from validation.suffix5.independent_convex_model import build_model
from validation.suffix5.window_plan import next_window


def raw(value):
    return plan.canonical(value) + b'\n'


class WindowReceiptTests(unittest.TestCase):
    def setUp(self):
        self.fx = population_fixtures.IndexedPopulationTests()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.root = self.fx.fx.root
        self.number = 0
        self.source = {wr.SEED_COMMIT: wr.SEED_SOURCE, 'f'*40: 'e'*64}
        physical = {'table': 'table.json', 'original_tree': 'tree.json'}
        for role in ('export_manifest', 'resolved_states', 'selection', 'restriction'):
            name = 'physical-'+role+'.json'; (self.root/name).write_bytes(raw({'tiny_fixture': role}))
            physical[role] = name
        input_pins = {role: dict(path=name, **plan.pin(self.root/name)) for role, name in physical.items()}
        manager = patch.object(plan, 'ROOT', self.root)
        manager.start(); self.addCleanup(manager.stop)
        paths = {}
        for key in ('historical_plan', 'replay_plan', 'replay_return', 'logical_return'):
            path = self.root/(key+'.json')
            document = dict(tiny_fixture=key)
            if key in ('historical_plan', 'replay_plan'):
                # Explicit synthetic D1 physical identity, not real C01 input
                # authority. Recovery now independently checks this contract
                # before re-admitting the genuine tiny scheduling population.
                document.update(variant_fixtures.VariantScopeTests().physical())
                document.update(inputs=input_pins, input_sha256=plan.digest(input_pins))
            path.write_bytes(raw(document))
            paths[key] = str(path)
            paths[key+'_sha'] = plan.pin(path)['sha256']
        self.fx.anchors.update(historical_plan_sha256=paths['historical_plan_sha'],
            replay_plan_sha256=paths['replay_plan_sha'], successful_return_sha256=paths['replay_return_sha'],
            manifest_sha256='1'*64, query_index={'sha256': '2'*64})
        self.admitted = self.fx.admit()
        self.population = self.admitted.population.plan()
        self.base = wr.make_registry(self.admitted, [])
        self.base_path = self.root/'registry.json'
        self.registration = wr.write_registry(self.base, self.base_path, deadline=time.monotonic()+30)
        self.registration_path = self.root/'registry-return.json'
        self.registration_path.write_bytes(raw(self.registration))
        self.policy_path = self.root/'source-policy.json'
        self.policy_path.write_bytes(raw(dict(schema='hiroute-reviewed-window-sources-v1', reviewed_sources=self.source)))
        cpus = sorted(os.sched_getaffinity(0))
        if len(cpus) < 6:
            self.skipTest('runtime fixture needs six CPU IDs')
        self.values = dict(paths, replay_attempt=str(self.root/'replay'), logical_attempt=str(self.root/'logical'),
            capture=str(self.root/'capture/capture.json'), replay_manifest_sha='1'*64, replay_result_sha='3'*64,
            replay_decision_sha='4'*64, query_index_sha='2'*64, source_commit='f'*40, source_sha='e'*64,
            logical_report_sha='5'*64, logical_source_sha='6'*64, worker_cpus=cpus[1:6],
            source_policy=str(self.policy_path), source_policy_sha=plan.pin(self.policy_path)['sha256'],
            registry=str(self.base_path), registry_sha=self.registration['registry_sha256'],
            registry_return=str(self.registration_path), registry_return_sha=plan.pin(self.registration_path)['sha256'],
            registry_output=str(self.root/'new-registry.json'), registration_return_output=str(self.root/'new-return.json'))
        for key in wr.WINDOW_OPTIONALS:
            self.values.setdefault(key, None)
        self.cpu = cpus[0]
        window = detach_json(next_window(self.population, [], population_plan_sha256=plan.digest(self.population)))
        blocks = [dict(range=span, descriptors=list(self.admitted.population.block(span['block_id']))) for span in window['blocks']]
        self.selection = dict(schema='hiroute-suffix-window-selection-v1', population=self.admitted.commitment(),
            window_plan=window, blocks=blocks, selection_uses_outcomes=False, numerical_cache_enabled=False,
            maximum_candidate_passes=window['expected_model_count']*12,
            maximum_logical_stages=window['expected_model_count']*5)
        for name in ('Popen', 'run', 'check_output'):
            manager = patch('subprocess.'+name, side_effect=AssertionError('native execution forbidden'))
            manager.start(); self.addCleanup(manager.stop)
        # The population fixture has already independently checked these tiny
        # original inputs. It does not persist fake successful upstream runs.
        manager = patch.object(wr, '_upstream_phases')
        manager.start(); self.addCleanup(manager.stop)

    def fixture(self, mutate_rows=lambda rows: None, mutate_request=lambda request: None,
                mutate_summary=lambda summary: None, mutate_run=lambda run: None, maximum_blocks=None):
        if maximum_blocks is not None:
            self.values['maximum_blocks'] = maximum_blocks
        else:
            self.values.pop('maximum_blocks', None)
        limit = 32 if maximum_blocks is None else maximum_blocks
        window = detach_json(next_window(self.population, self.base.completed_block_ids(),
            population_plan_sha256=plan.digest(self.population), maximum_blocks=limit))
        blocks = [dict(range=span, descriptors=list(self.admitted.population.block(span['block_id'])))
                  for span in window['blocks']]
        models = window['expected_model_count']
        self.selection = dict(schema='hiroute-suffix-window-selection-v1', population=self.admitted.commitment(),
            window_plan=window, blocks=blocks, selection_uses_outcomes=False, numerical_cache_enabled=False,
            maximum_candidate_passes=models*12, maximum_logical_stages=models*5)
        self.number += 1
        attempt = self.root/('window'+str(self.number)); attempt.mkdir()
        evidence = attempt/'evidence'
        resources = dict(name='C01-suffix-window-v1', absolute_seconds=900,
            evidence_charge_bytes=512*1024**2, uncompressed_archive_bytes=512*1024**2,
            maximum_input_bytes=128*1024**2, maximum_blocks=limit, maximum_models=limit*256,
            models=models, block_size=256, persistent_workers=4,
            candidate_as_bytes=1024**3, candidate_peak_rss_bytes=768*1024**2, seconds_per_model=30,
            maximum_passes_per_model=12, maximum_candidate_passes=models*12,
            maximum_logical_stages=models*5,
            numerical_cache_enabled=False, worker_cpus=self.values['worker_cpus'])
        commitment = self.admitted.commitment()
        origin = dict(schema='hiroute-reviewed-controller-origin-v1', checkout_root=str(self.root.resolve()),
            controller_module=wr.MODULE_PREFIX+'suffix_window',
            controller_path=str(self.root/'experiments/time_cut_v2/recorded_real/suffix_window.py'),
            python_executable=sys.executable, executable_realpath=str(Path(sys.executable).resolve()), cwd=str(self.root.resolve()))
        with runtime.BoundedEvidenceWriter(evidence, runtime.BATCH_REPLAY.worker_evidence_bytes,
                                           profile_name=runtime.BATCH_REPLAY.name) as writer:
            writer.write('block-plan.json', domain.chunks(self.population))
            selection_pin = writer.write('window-selection.json', domain.chunks(self.selection))
            base_pin = writer.write('base-registry.json', [self.base_path.read_bytes()])
            context = dict(schema='hiroute-suffix-window-context-v1', source_sha256='e'*64,
                source_bundle_sha256=commitment['source_bundle_sha256'], capture_sha256=commitment['completed_replay']['capture_sha256'],
                block_plan_sha256=commitment['block_plan_sha256'], selection_sha256=selection_pin['sha256'],
                original_query_freeze_sha256=commitment['query_freeze_sha256'], resource_plan_sha256=plan.digest(resources),
                window_id=self.selection['window_plan']['window_id'], base_registry_sha256=base_pin['sha256'],
                source_policy_sha256=self.values['source_policy_sha'])
            run = dict(schema='hiroute-suffix-window-binding-v1', source_commit='f'*40, source_sha256='e'*64,
                invocation_origin=origin,
                completed_replay=commitment['completed_replay'], logical_report_sha256='5'*64, resource_plan=resources,
                base_registry=base_pin, selection=selection_pin, window_id=context['window_id'], registry_admission=dict(
                    kind='registered-window-ledger-v1', registry_sha256=self.values['registry_sha'],
                    registration_return_sha256=self.values['registry_return_sha'], source_policy_sha256=self.values['source_policy_sha']))
            mutate_run(run)
            writer.write('run-binding.json', domain.chunks(run))
            writer.write('family-summary.json', domain.chunks(dict(checked={key: commitment[key] for key in
                ('case_sha256', 'source_bundle_sha256')} | {'bundle_sha256': commitment['source_bundle_sha256']})))
            writer.write('batch-ledger.json', domain.chunks({'tiny_fixture': True}))
            blocks = self.selection['blocks']
            rows = [dict(kind='header', schema='hiroute-suffix-block-proof-archive-v1', source_context=context,
                expected_models=models, blocks=[block['range'] for block in blocks],
                certificate_reuse_enabled=False)]
            reports = []; input_bytes = 0
            for block in blocks:
                aggregate = StreamAggregator(start=block['range']['start'])
                parts, segment, current = [], None, None
                for descriptor in block['descriptors']:
                    ordinal, identity = descriptor['ordinal'], descriptor['logical_identity']
                    model = build_model(self.admitted.ctx, identity['family_id'], identity['word'], identity['arrival_bands'])
                    result = dict(status='closed_infeasible')
                    record = dict(model=model, stages=[], result=result)
                    verification = dict(model_ordinal=ordinal, block_id=block['range']['block_id'],
                        logical_identity_sha256=descriptor['logical_identity_sha256'], model_sha256=plan.digest(model),
                        record_sha256=plan.digest(record), result=result, checked_stage_count=0,
                        independent_certificate_verified=True, physical_witness_verified=False,
                        query_optimum_certified=False, literal_G8_closed=False)
                    job = LPStreamJob(context, block['range']['block_id'], ordinal, plan.digest(model), model)
                    input_bytes += len(job.input_bytes)
                    rows.append(dict(kind='model_certificate', descriptor=descriptor, record=record, verification=verification,
                        candidate_identity=job.header('a'*32)))
                    aggregate.add(ordinal, result)
                    if descriptor['segment_id'] != current:
                        if segment is not None:
                            parts.append(dict(segment_id=current, aggregate=segment.summary()))
                        current, segment = descriptor['segment_id'], StreamAggregator(start=ordinal)
                    segment.add(ordinal, result)
                parts.append(dict(segment_id=current, aggregate=segment.summary()))
                report = dict(schema='suffix5-checked-block-certificates-v1', range=block['range'], complete=True,
                    complete_certificates=True, verified_models=block['range']['model_count'], unresolved_ordinals=[],
                    unsubmitted_ordinals=[], aggregate=aggregate.summary(), segment_summaries=parts,
                    physical_witness_verified=False, physical_witness_not_required=True,
                    query_optimum_certified=False, literal_G8_closed=False)
                reports.append(report); rows.append(dict(kind='block_report', report=report, winner_witness=None))
            transport = dict(status='complete', input_exhausted=True, all_submitted_accounted=True,
                all_processes_reaped=True, submitted_count=models,
                terminal_count=models, protocol_error_count=0, collector_error=None, input_bytes=input_bytes)
            rows.append(dict(kind='footer', schema='hiroute-suffix-block-proof-footer-v1', complete=True,
                verified_models=models, expected_models=models,
                transport=transport, blocks=reports, **wr.FALSE_AUTHORITY))
            mutate_rows(rows)
            encoder = block_archive.ArchiveEncoding()
            proof = writer.write('model-proofs.jsonl.gz', encoder.chunks(rows))
            summary = dict(schema='hiroute-suffix-window-summary-v1', source_context=context, resource_plan=resources,
                invocation_origin=origin,
                population=commitment, selection=selection_pin, base_registry=base_pin, window_id=context['window_id'],
                proof_archive=proof, encoding=encoder.summary(), complete=True, verified_models=models,
                blocks=reports, transport=transport, numerical_wall_seconds=0., registry_admission=run['registry_admission'], **wr.FALSE_AUTHORITY)
            mutate_summary(summary)
            writer.write('window-summary.json', domain.chunks(summary)); manifest = writer.finalize()
        manifest_bytes = (evidence/'__manifest.json').read_bytes()
        manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
        command = [sys.executable, '-B', '-m', wr.MODULE_PREFIX+'suffix_window', '--worker', '--deadline', '110.0']
        for key, value in self.values.items():
            if value is not None:
                command.extend(['--'+key.replace('_', '-'), *([str(x) for x in value] if type(value) is list else [str(value)])])
        request = dict(profile=asdict(runtime.BATCH_REPLAY), context=dict(plan_sha256=self.values['replay_plan_sha'],
            source_sha256='e'*64, input_sha256=plan.digest(self.values), profile_name=runtime.BATCH_REPLAY.name),
            entry_monotonic=100., deadline_monotonic=110., launcher_rss_bytes_at_entry=1,
            command=command, cpu=self.cpu, worker_cpus=self.values['worker_cpus'])
        mutate_request(request)
        report = {key: value for key, value in request.items() if key != 'command'}
        report.update(schema='hiroute-phase-v1', status='provisional', reason='synthetic completed source fixture',
            worker_exit_code=0, descendants_reaped=True, sampled_group_rss_peak_bytes=0, kernel_max_reaped_ru_maxrss_bytes=0,
            supervisor_kernel_peak_rss_bytes=0, supervisor_metadata_charge_bytes_before_report=0,
            worker_charged_bytes=manifest['charged_bytes'], largest_sample_gap_seconds=0., phase_wall_seconds=.1,
            reaped_cpu_seconds=0., supervisor_cpu_seconds=0., verified_manifest_sha256=manifest_sha,
            verified_manifest_size_bytes=len(manifest_bytes), request_sha256=hashlib.sha256(runtime._json(request)).hexdigest())
        result_raw = runtime._json(report)
        ready = dict(schema='hiroute-supervisor-decision-v1', status='ready', report_sha256=hashlib.sha256(result_raw).hexdigest(),
                     report_size_bytes=len(result_raw), manifest_sha256=manifest_sha, manifest_size_bytes=len(manifest_bytes))
        decision = dict(schema='hiroute-phase-decision-v1', status='completed', supervisor_exit_code=0,
            accepted_monotonic=100.2, supervisor_decision_sha256=hashlib.sha256(runtime._json(ready)).hexdigest())
        for name, value in (('request.json', request), ('result.json', report), ('supervisor-decision.json', ready), ('decision.json', decision)):
            (attempt/name).write_bytes(runtime._json(value))
        returned = dict(report, status='completed', phase_wall_seconds=.5, acceptance_receipt=dict(
            schema='hiroute-caller-return-v1', returned_monotonic=100.5, result_sha256=plan.pin(attempt/'result.json')['sha256'],
            decision_sha256=plan.pin(attempt/'decision.json')['sha256'], manifest_sha256=manifest_sha,
            manifest_size_bytes=len(manifest_bytes)))
        path = self.root/('return'+str(self.number)+'.json'); path.write_bytes(raw(returned))
        return SimpleNamespace(window_attempt=attempt, window_return=path, window_return_sha=plan.pin(path)['sha256'],
            window_result_sha=plan.pin(attempt/'result.json')['sha256'], window_decision_sha=plan.pin(attempt/'decision.json')['sha256'],
            window_manifest_sha=manifest_sha)

    def admit(self, args=None, **kwargs):
        return wr.admit_new_completed_window(args or self.fixture(), self.admitted, reviewed_sources=self.source,
                                             deadline=time.monotonic()+30, **kwargs)

    def test_actual_cold_runtime_and_compact_registry_roundtrip(self):
        with patch('validation.suffix5.convex_checker.check_regime', side_effect=AssertionError('no fresh numerical replay')):
            receipt = self.admit()
            registry = wr.make_registry(self.admitted, [receipt])
            self.assertEqual(registry.completed_block_ids(), (0,))
            self.assertEqual(registry.block_reports(), receipt.block_reports())
            scope = wr.scope_from_registry(registry, deadline=time.monotonic()+30)
            self.assertEqual(scope.commitment(), self.admitted.commitment())
            destination = self.root/'registered.json'
            returned = wr.write_registry(registry, destination, deadline=time.monotonic()+30)
            path = self.root/'registration.json'; path.write_bytes(raw(returned))
            loaded = wr.load_scheduling_registry(destination, returned['registry_sha256'], scope,
                registration_return=path, registration_return_sha=plan.pin(path)['sha256'],
                reviewed_sources=self.source, deadline=time.monotonic()+30)
            self.assertEqual(loaded.completed_block_ids(), (0,))
            bootstrapped = wr.scope_from_registered_registry(destination, returned['registry_sha256'],
                registration_return=path, registration_return_sha=plan.pin(path)['sha256'],
                reviewed_sources=self.source, deadline=time.monotonic()+30)
            self.assertEqual(bootstrapped.plan(), scope.plan())
            with self.assertRaisesRegex(ValueError, 'cold reconciliation'):
                loaded.block_reports()
            checked = wr.reconcile_registry(loaded, scope, reviewed_sources=self.source, deadline=time.monotonic()+30)
            self.assertEqual(checked.block_reports(), receipt.block_reports())
        self.assertNotIn('certificate', repr(registry.metadata()['blocks']))
        self.assertLess(len(plan.canonical(registry.metadata())), wr.REGISTRY_LIMIT)
    def test_single_block_limit_cold_binds_actual_request_selection_and_resources(self):
        receipt = self.admit(self.fixture(maximum_blocks=1))
        self.assertEqual([row['range']['block_id'] for row in receipt.block_reports()], [0])
        self.assertEqual(receipt.metadata()['source_commit'], self.values['source_commit'])

    def test_repaired_request_and_outer_hashes_cannot_relabel_default_window_as_single_block(self):
        def alter(request):
            position = request['command'].index('--maximum-blocks')+1
            request['command'][position] = '1'
            values = dict(self.values, maximum_blocks=1)
            request['context']['input_sha256'] = plan.digest(values)
        # fixture() repairs result/decision/return/manifest bindings after this
        # mutation; cold selection still must match the narrowed request.
        args = self.fixture(maximum_blocks=32, mutate_request=alter)
        with self.assertRaisesRegex(ValueError, 'first outstanding catalogue window'):
            self.admit(args)

    def test_factory_boundary_immutable_ownership_and_duplicate_registry(self):
        for cls, args in ((wr.CheckedWindowReceipt, ({}, [])), (wr.CheckedRegistry, ({}, [])), (wr.ReceiptScope, ({}, {}))):
            with self.assertRaises(ValueError): cls(*args)
        receipt = self.admit(); original = receipt.block_reports()
        receipt.block_reports()[0]['aggregate']['end'] = -1
        receipt.metadata()['blocks'][0]['range']['end'] = -1
        self.assertEqual(receipt.block_reports(), original)
        with self.assertRaises(AttributeError): receipt._reports = b'{}'
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            wr.make_registry(self.admitted, [receipt, receipt])

    def test_missing_return_wrong_source_and_wrong_context_reject(self):
        args = self.fixture(); args.window_return.unlink()
        with self.assertRaises(ValueError): self.admit(args)
        args = self.fixture()
        with self.assertRaisesRegex(ValueError, 'allowlist'):
            wr.admit_new_completed_window(args, self.admitted, reviewed_sources={}, deadline=time.monotonic()+30)
        args = self.fixture(mutate_request=lambda value: value['context'].update(input_sha256='0'*64))
        with self.assertRaisesRegex(ValueError, 'command inputs'): self.admit(args)
        args = self.fixture(mutate_request=lambda value: value['command'].__setitem__(3, 'foreign.module'))
        with self.assertRaisesRegex(ValueError, 'module command'): self.admit(args)

    def test_changed_certificate_bytes_and_incomplete_execution_reject(self):
        args = self.fixture()
        path = args.window_attempt/'evidence/model-proofs.jsonl.gz'; path.chmod(0o600); path.write_bytes(path.read_bytes()+b'x')
        with self.assertRaisesRegex(ValueError, 'runtime'): self.admit(args)
        args = self.fixture()
        successful = plan.load(args.window_return); successful['status'] = 'unresolved'
        args.window_return.write_bytes(raw(successful)); args.window_return_sha = plan.pin(args.window_return)['sha256']
        with self.assertRaisesRegex(ValueError, 'successful runtime return'): self.admit(args)

    def test_foreign_duplicate_missing_dispositions_and_altered_segments_reject(self):
        def foreign(rows): rows[1]['descriptor'] = dict(rows[1]['descriptor'], ordinal=999)
        def duplicate(rows): rows.insert(2, deepcopy(rows[1]))
        def gap(rows): rows.pop(1)
        def wrong_record(rows): rows[1]['record']['stages'].append({'changed_certificate': True})
        def segments(rows):
            report = next(row['report'] for row in rows if row['kind'] == 'block_report')
            report['segment_summaries'][0]['aggregate']['end'] -= 1
        for mutation in (foreign, duplicate, gap, wrong_record, segments):
            with self.subTest(mutation=mutation.__name__), self.assertRaises(ValueError):
                self.admit(self.fixture(mutate_rows=mutation))

    def test_deadline_and_callbacks_bound_reads_and_publish(self):
        args = self.fixture()
        with self.assertRaisesRegex(ValueError, 'deadline'):
            wr.admit_new_completed_window(args, self.admitted, reviewed_sources=self.source, deadline=time.monotonic()-1)
        calls = []
        def stop():
            calls.append(1)
            if len(calls) == 10: raise TimeoutError('bounded cancellation')
        with self.assertRaises(TimeoutError): self.admit(args, before=stop)
        self.assertEqual(len(calls), 10)

    def test_missing_full_input_and_missing_registration_return_reject(self):
        args = self.fixture()
        Path(self.values['capture']).unlink()
        with self.assertRaises(ValueError): self.admit(args)
        self.registration_path.unlink()
        with self.assertRaises(ValueError):
            wr.load_scheduling_registry(self.base_path, self.registration['registry_sha256'], self.admitted,
                registration_return=self.registration_path, registration_return_sha=self.values['registry_return_sha'],
                reviewed_sources=self.source, deadline=time.monotonic()+30)

    def test_physical_table_tree_export_selection_and_restriction_are_required(self):
        args = self.fixture()
        original = plan.load(self.values['historical_plan'])
        for role, pin in original['inputs'].items():
            path = self.root/pin['path']; content = path.read_bytes(); path.unlink()
            with self.subTest(role=role), self.assertRaises(ValueError): self.admit(args)
            path.write_bytes(content)

    def test_source_policy_command_and_resource_mismatches_reject(self):
        args = self.fixture(mutate_summary=lambda doc: doc['source_context'].update(source_policy_sha256='0'*64))
        with self.assertRaises(ValueError): self.admit(args)
        args = self.fixture(mutate_summary=lambda doc: doc['resource_plan'].update(maximum_passes_per_model=13))
        with self.assertRaises(ValueError): self.admit(args)
        args = self.fixture(mutate_request=lambda request: request['command'].extend(['--unknown-contract', 'yes']))
        with self.assertRaises(ValueError): self.admit(args)
        args = self.fixture(mutate_request=lambda request: request['command'].__setitem__(0, '/bin/false'))
        with self.assertRaisesRegex(ValueError, 'origin'): self.admit(args)
        args = self.fixture(mutate_run=lambda doc: doc['invocation_origin'].update(cwd='/foreign'))
        with self.assertRaisesRegex(ValueError, 'origin'): self.admit(args)
        args = self.fixture(mutate_rows=lambda rows: rows[-1]['transport'].update(input_bytes=1))
        with self.assertRaisesRegex(ValueError, 'input bytes'): self.admit(args)

    def test_admission_cache_releases_large_decoded_documents(self):
        args = self.fixture()
        deadline = time.monotonic()+30; check = wr._guard(deadline, lambda: None)
        cache = wr._Dependencies(check); spec = wr._spec(args, 'window', 'suffix_window')
        receipt = wr._admit(spec, self.admitted, None, self.source, deadline, check, cache)
        self.assertEqual(cache.decoded, {})
        self.assertTrue(cache.rows)
        self.assertIs(wr._admit(spec, self.admitted, None, self.source, deadline, check, cache), receipt)

    def test_compact_registry_span_segment_and_return_tampering_reject(self):
        receipt = self.admit()
        registry = wr.make_registry(self.admitted, [receipt])
        destination = self.root/'tampered-registry.json'
        returned = wr.write_registry(registry, destination, deadline=time.monotonic()+30)
        return_path = self.root/'tampered-registration.json'; return_path.write_bytes(raw(returned))
        for mode in ('span', 'segment', 'entry', 'return'):
            metadata, retained = registry.metadata(), deepcopy(returned)
            if mode == 'span': metadata['entries'][0]['blocks'][0]['range']['end'] -= 1
            if mode == 'segment': metadata['entries'][0]['blocks'][0]['segments'][0]['end'] -= 1
            if mode == 'entry': metadata['entries'].append(deepcopy(metadata['entries'][0]))
            if mode == 'return': retained['entry_ids'] = []
            destination.write_bytes(raw(metadata))
            # Simulate externally pinned malformed data to exercise structural
            # checks in addition to the ordinary immutable-byte rejection.
            retained['registry_sha256'] = plan.pin(destination)['sha256']
            retained['registry_size_bytes'] = destination.stat().st_size
            return_path.write_bytes(raw(retained))
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                wr.load_scheduling_registry(destination, retained['registry_sha256'], self.admitted,
                    registration_return=return_path, registration_return_sha=plan.pin(return_path)['sha256'],
                    reviewed_sources=self.source, deadline=time.monotonic()+30)


class RetainedSeedDependencyTests(unittest.TestCase):
    """Reuse three genuine hand certificates and two missing historical models."""
    def setUp(self):
        from tests.test_suffix_block_resume import BlockResumeTests
        self.fixture = BlockResumeTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        receipt = self.fixture.receipt()
        cold_path = self.root/'cold-replay.json'; cold_path.write_bytes(raw(receipt.summary()))
        self.context = dict(self.fixture.old_context,
            schema='hiroute-suffix-block-resume-context-v1', source_sha256='e'*64,
            previous_source_context=self.fixture.old_context)
        for key, value in (('SEED_MODELS', 5), ('SEED_RETAINED_MODELS', 3),
                           ('SEED_COLD', plan.pin(cold_path)['sha256'])):
            manager = patch.object(wr, key, value); manager.start(); self.addCleanup(manager.stop)

    def retained(self):
        check = wr._guard(time.monotonic()+30, lambda: None)
        return wr._retained(vars(self.fixture.args), {}, self.root, self.fixture.selection,
                            self.context, wr._Dependencies(check), check)

    def test_retained_references_bind_full_old_archive_and_cold_receipt(self):
        retained = self.retained()
        self.assertEqual(sorted(retained), [0, 346112, 648960])
        self.assertTrue(all(row['kind'] == 'retained_certificate_reference' for row in retained.values()))
        for field in ('old_archive', 'old_summary', 'old_selection'):
            path = getattr(self.fixture.args, field)
            original = path.read_bytes(); path.unlink()
            with self.subTest(missing=field), self.assertRaises(ValueError): self.retained()
            path.write_bytes(original)

    def test_changed_old_certificate_bytes_and_foreign_cold_reference_reject(self):
        path = self.fixture.args.old_archive
        original = path.read_bytes(); path.write_bytes(original[:-1]+bytes([original[-1] ^ 1]))
        with self.assertRaises(ValueError): self.retained()
        path.write_bytes(original)
        cold_path = self.root/'cold-replay.json'
        cold = plan.load(cold_path); cold['certificate_refs'][0]['archive_row_sha256'] = '0'*64
        cold_path.write_bytes(raw(cold))
        with patch.object(wr, 'SEED_COLD', plan.pin(cold_path)['sha256']), self.assertRaises(ValueError):
            self.retained()


class UpstreamProofGraphTests(unittest.TestCase):
    @staticmethod
    def json_sha(value):
        return hashlib.sha256(runtime._json(value)).hexdigest()

    def history(self, root, prefix, profile, names):
        attempt = root/prefix; attempt.mkdir()
        with runtime.BoundedEvidenceWriter(attempt/'evidence', profile.worker_evidence_bytes,
                                           profile_name=profile.name) as writer:
            files = {name: writer.write(name, [raw({'tiny_upstream_fixture': name})]) for name in names}
            manifest = writer.finalize()
        manifest_raw = (attempt/'evidence/__manifest.json').read_bytes()
        cpus = sorted(os.sched_getaffinity(0))
        context = dict(plan_sha256='e'*64, source_sha256='f'*64, input_sha256='d'*64, profile_name=profile.name)
        request = dict(profile=asdict(profile), context=context, entry_monotonic=100., deadline_monotonic=110.,
                       launcher_rss_bytes_at_entry=1, command=['/usr/bin/python3', '-c', 'synthetic fixture'])
        if profile == runtime.BATCH_REPLAY:
            request.update(cpu=cpus[0], worker_cpus=cpus[1:6])
        report = {key: value for key, value in request.items() if key != 'command'}
        report.update(schema='hiroute-phase-v1', status='provisional', reason='tiny upstream fixture',
            worker_exit_code=0, descendants_reaped=True, sampled_group_rss_peak_bytes=0, kernel_max_reaped_ru_maxrss_bytes=0,
            supervisor_kernel_peak_rss_bytes=0, supervisor_metadata_charge_bytes_before_report=0,
            worker_charged_bytes=manifest['charged_bytes'], largest_sample_gap_seconds=0., phase_wall_seconds=.1,
            reaped_cpu_seconds=0., supervisor_cpu_seconds=0., verified_manifest_sha256=hashlib.sha256(manifest_raw).hexdigest(),
            verified_manifest_size_bytes=len(manifest_raw), request_sha256=self.json_sha(request))
        ready = dict(schema='hiroute-supervisor-decision-v1', status='ready', report_sha256=self.json_sha(report),
            report_size_bytes=len(runtime._json(report)), manifest_sha256=report['verified_manifest_sha256'],
            manifest_size_bytes=len(manifest_raw))
        decision = dict(schema='hiroute-phase-decision-v1', status='completed', supervisor_exit_code=0,
                        accepted_monotonic=100.2, supervisor_decision_sha256=self.json_sha(ready))
        for name, value in (('request.json', request), ('result.json', report), ('supervisor-decision.json', ready), ('decision.json', decision)):
            (attempt/name).write_bytes(runtime._json(value))
        returned = dict(report, status='completed', phase_wall_seconds=.5, acceptance_receipt=dict(
            schema='hiroute-caller-return-v1', returned_monotonic=100.5, result_sha256=self.json_sha(report),
            decision_sha256=self.json_sha(decision), manifest_sha256=report['verified_manifest_sha256'],
            manifest_size_bytes=len(manifest_raw)))
        return_path = root/(prefix+'-return.json'); return_path.write_bytes(raw(returned))
        return dict(attempt=str(attempt), returned=str(return_path), returned_sha=plan.pin(return_path)['sha256'],
            result_sha=self.json_sha(report), decision_sha=self.json_sha(decision), manifest_sha=report['verified_manifest_sha256'],
            files=files)

    def test_each_upstream_phase_is_authenticated_once_and_every_proof_remains_required(self):
        if len(os.sched_getaffinity(0)) < 6: self.skipTest('six CPU IDs required')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            replay = self.history(root, 'replay', runtime.BATCH_REPLAY,
                                  ['query-index.json', 'structural-summary.json', 'parallel-summary.json', 'retained-proof.json'])
            logical = self.history(root, 'logical', runtime.REPLAY, ['suffix-census.json'])
            values = dict(replay_plan_sha='e'*64, logical_source_sha='f'*64,
                logical_report_sha=logical['files']['suffix-census.json']['sha256'],
                replay_manifest_sha=replay['manifest_sha'], replay_result_sha=replay['result_sha'],
                replay_decision_sha=replay['decision_sha'], query_index_sha=replay['files']['query-index.json']['sha256'])
            for name, result in (('replay', replay), ('logical', logical)):
                values.update({name+'_attempt': result['attempt'], name+'_return': result['returned'],
                               name+'_return_sha': result['returned_sha']})
            commitment = dict(completed_replay={field: replay['files'][name] for field, name in
                (('query_index', 'query-index.json'), ('structural_summary', 'structural-summary.json'),
                 ('parallel_summary', 'parallel-summary.json'))})
            deadline = time.monotonic()+30; check = wr._guard(deadline, lambda: None); cache = wr._Dependencies(check)
            with patch.object(wr, 'read_phase_result', wraps=runtime.read_phase_result) as read_phase:
                wr._upstream_phases(values, commitment, cache, deadline)
                first = set(cache.used); cache.used = set()
                wr._upstream_phases(values, commitment, cache, deadline)
                self.assertEqual(read_phase.call_count, 2)
                self.assertEqual(cache.used, first)
            self.assertIn((str(root/'replay/evidence/retained-proof.json'),
                           replay['files']['retained-proof.json']['sha256']), cache.used)
            missing = root/'replay/evidence/retained-proof.json'
            missing.parent.chmod(0o700); missing.unlink()
            with self.assertRaisesRegex(ValueError, 'upstream replay'):
                wr._upstream_phases(values, commitment, wr._Dependencies(check), deadline)


if __name__ == '__main__':
    unittest.main()
