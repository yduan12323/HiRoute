"""Tiny metadata linkage tests; historical flags never verify a model."""
from copy import deepcopy
import json
from pathlib import Path
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from experiments.time_cut_v2.recorded_real import plan, recovery_plan as recovery
from experiments.time_cut_v2.recorded_real import window_receipts as receipts
from experiments.time_cut_v2.recorded_real import suffix_window_recovery as runner
from tests import test_suffix_window_receipts as fixtures
raw = fixtures.raw


class RecoveryPlanTests(unittest.TestCase):
    def setUp(self):
        self.fx = fixtures.WindowReceiptTests()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.root = self.fx.root

    def pin(self, path):
        return dict(path=str(path), **plan.pin(path))

    def document(self, **mutations):
        args = self.fx.fixture(**mutations)
        attempt = args.window_attempt
        # Explicit fake failure metadata. No historical read_phase_result is
        # called, and the deliberately synthetic certificate is never trusted.
        for path in (attempt/'result.json', attempt/'decision.json', args.window_return):
            value = json.loads(path.read_bytes())
            value['status'] = 'unresolved'
            value.pop('acceptance_receipt', None)
            path.write_bytes(raw(value))
        evidence = attempt/'evidence'
        artifacts = dict(request=self.pin(attempt/'request.json'), run_binding=self.pin(evidence/'run-binding.json'),
            selection=self.pin(evidence/'window-selection.json'), base_registry=self.pin(evidence/'base-registry.json'),
            source_policy=self.pin(self.fx.policy_path), archive=self.pin(evidence/'model-proofs.jsonl.gz'),
            summary=self.pin(evidence/'window-summary.json'), manifest=self.pin(evidence/'__manifest.json'),
            result=self.pin(attempt/'result.json'), decision=self.pin(attempt/'decision.json'),
            actual_return=self.pin(args.window_return), recovery_plan=None, cold_replay=None)
        return dict(schema=recovery.SCHEMA, historical_attempt_status='failed',
            original_selection=artifacts['selection'], base_registry=self.pin(self.fx.base_path),
            predecessors=[dict(module='experiments.time_cut_v2.recorded_real.suffix_window', source_commit='f'*40,
                source_sha256='e'*64, attempt=str(attempt), archive_mode='finalized',
                source_context=json.loads((evidence/'window-summary.json').read_bytes())['source_context'], artifacts=artifacts)])

    def load(self, value, canonical=True):
        path = self.root/'recovery-plan.json'
        path.write_bytes(raw(value) if canonical else json.dumps(value, indent=2).encode())
        return recovery.load(path, plan.pin(path)['sha256'], deadline=time.monotonic()+30)

    def admit(self, value):
        value = self.load(value)
        with patch.object(receipts, 'read_phase_result', side_effect=AssertionError('no failed-run success admission')):
            return recovery.admit(value, self.fx.admitted, self.fx.base,
                                  reviewed_sources=self.fx.source, deadline=time.monotonic()+30)

    def test_independently_linked_plan_is_detached_and_has_no_certificate_authority(self):
        value = self.document()
        admitted = self.admit(value)
        self.assertEqual(admitted.selection(), self.fx.selection)
        self.assertEqual(admitted.document()['historical_attempt_status'], 'failed')
        self.assertFalse(hasattr(admitted, 'certificates'))
        value['predecessors'][0]['source_context']['source_sha256'] = '0'*64
        self.assertEqual(admitted.history()[0]['source_context']['source_sha256'], 'e'*64)
        with self.assertRaisesRegex(ValueError, 'independent'):
            recovery.AdmittedRecoveryPlan({}, {}, [], [])

    def test_plan_canonical_pin_explicit_absences_and_cumulative_caps(self):
        value = self.document()
        with self.assertRaisesRegex(ValueError, 'canonical'):
            self.load(value, canonical=False)
        bad = deepcopy(value); del bad['predecessors'][0]['artifacts']['summary']
        with self.assertRaisesRegex(ValueError, 'absences'):
            self.load(bad)
        bad = deepcopy(value); bad['predecessors'][0]['artifacts']['archive']['size_bytes'] = 512*1024**2+1
        with self.assertRaisesRegex(ValueError, 'bounded'):
            self.load(bad)
        bad = deepcopy(value); bad['predecessors'][0]['source_commit'] = 'f'*12
        with self.assertRaisesRegex(ValueError, 'full predecessor'):
            self.load(bad)

    def test_summary_claims_and_absence_never_supply_old_runtime_authority(self):
        value = self.document(mutate_summary=lambda row: row.update(complete=True, verified_models=987654,
            query_optimum_certified=True, full_population_complete=True, literal_G8_closed=True))
        admitted = self.admit(value)
        self.assertEqual(admitted.document()['historical_attempt_status'], 'failed')
        for key in ('summary', 'manifest', 'result', 'decision', 'actual_return'):
            value['predecessors'][0]['artifacts'][key] = None
        self.assertEqual(self.admit(value).selection(), self.fx.selection)

    def test_successful_old_return_is_never_accepted(self):
        value = self.document()
        pin = value['predecessors'][0]['artifacts']['actual_return']
        path = Path(pin['path']); body = json.loads(path.read_bytes()); body['status'] = 'completed'
        path.write_bytes(raw(body)); pin.update(plan.pin(path))
        with self.assertRaisesRegex(ValueError, 'successful runtime'):
            self.admit(value)

    def test_completed_decision_without_successful_actual_return_is_only_linked_metadata(self):
        for missing_return in (True, False):
            with self.subTest(missing_return=missing_return):
                value = self.document()
                artifacts = value['predecessors'][0]['artifacts']
                # Runtime publishes this decision before the final checks and
                # actual return; an interrupted launcher can leave it intact.
                pin = artifacts['decision']; path = Path(pin['path'])
                body = json.loads(path.read_bytes()); body['status'] = 'completed'
                path.write_bytes(raw(body)); pin.update(plan.pin(path))
                if missing_return:
                    artifacts['actual_return'] = None
                admitted = self.admit(value)
                self.assertEqual(admitted.document()['historical_attempt_status'], 'failed')
                self.assertFalse(hasattr(admitted, 'certificates'))
                self.assertEqual(admitted.selection(), self.fx.selection)

    def test_completed_result_flag_also_grants_no_runtime_authority(self):
        value = self.document()
        artifacts = value['predecessors'][0]['artifacts']
        pin = artifacts['result']; path = Path(pin['path'])
        body = json.loads(path.read_bytes()); body['status'] = 'completed'
        path.write_bytes(raw(body)); pin.update(plan.pin(path))
        artifacts['actual_return'] = None
        admitted = self.admit(value)
        self.assertEqual(admitted.document()['historical_attempt_status'], 'failed')
        self.assertFalse(hasattr(admitted, 'certificates'))

    def test_repaired_manifest_hash_cannot_substitute_foreign_evidence(self):
        value = self.document()
        pin = value['predecessors'][0]['artifacts']['manifest']
        path = Path(pin['path']); body = json.loads(path.read_bytes())
        next(row for row in body['files'] if row['path'] == 'model-proofs.jsonl.gz')['sha256'] = '0'*64
        path.chmod(0o600); path.write_bytes(raw(body)); pin.update(plan.pin(path))
        with self.assertRaisesRegex(ValueError, 'manifest linkage'):
            self.admit(value)

    def test_repaired_source_selection_and_origin_fail_independent_links(self):
        for mutation, pattern in ((lambda run: run.update(source_commit='0'*40), 'source binding'),
            (lambda run: run['invocation_origin'].update(controller_module=recovery.MODULE), 'origin')):
            with self.subTest(pattern=pattern):
                with self.assertRaisesRegex(ValueError, pattern):
                    self.admit(self.document(mutate_run=mutation))
        value = self.document()
        pin = value['original_selection']; path = Path(pin['path'])
        body = json.loads(path.read_bytes()); body['window_plan']['window_id'] = '0'*64
        path.chmod(0o600); path.write_bytes(raw(body)); pin.update(plan.pin(path))
        with self.assertRaisesRegex(ValueError, 'selection contract'):
            self.admit(value)

    def test_interrupted_prefix_is_explicit_and_finalization_checked_cold(self):
        value = self.document()
        value['predecessors'][0]['archive_mode'] = 'interrupted-prefix'
        admitted = self.admit(value)
        cold = dict(history=[dict(admitted.history()[0], gzip_eof=False, trailing_partial_row_bytes=13)])
        admitted.validate_cold_history(cold)
        cold['history'][0]['gzip_eof'] = True
        with self.assertRaisesRegex(ValueError, 'finalization'):
            admitted.validate_cold_history(cold)

    def test_writer_partial_location_does_not_decide_gzip_finalization(self):
        from experiments.time_cut_v2.recorded_real.archive_reader import ArchiveReader
        value = self.document()
        row = value['predecessors'][0]
        original = Path(row['artifacts']['archive']['path'])
        partial = original.parent/'__partial/0007.part'; partial.parent.mkdir(exist_ok=True)
        original.rename(partial)
        # Metadata completed after archive publication is explicitly absent.
        for key in ('summary', 'manifest', 'result', 'decision', 'actual_return'):
            row['artifacts'][key] = None
        row['archive_mode'] = 'interrupted-prefix'
        row['artifacts']['archive']['path'] = str(partial)
        admitted = self.admit(value)
        self.assertEqual(admitted.document()['predecessors'][0]['artifacts']['archive']['path'], str(partial))
        # The stream was completely written before publication was interrupted.
        # Authenticate the actual canonical rows and gzip trailer at its
        # retained path; this does not verify the synthetic model dispositions.
        pin = row['artifacts']['archive']
        reader = ArchiveReader(partial, compressed_sha256=pin['sha256'], compressed_bytes=pin['size_bytes'])
        list(reader)
        self.assertTrue(reader.summary['gzip_eof'])
        cold = dict(history=[dict(admitted.history()[0], gzip_eof=reader.summary['gzip_eof'],
            trailing_partial_row_bytes=reader.summary['trailing_partial_row_bytes'])])
        with self.assertRaisesRegex(ValueError, 'finalization'):
            admitted.validate_cold_history(cold)
        row['archive_mode'] = 'finalized'
        finalized = self.admit(value)
        finalized.validate_cold_history(cold)
        self.assertEqual(finalized.document()['historical_attempt_status'], 'failed')
        self.assertFalse(hasattr(finalized, 'certificates'))
        self.assertTrue(partial.is_file())
        self.assertFalse(original.exists())

    def test_changed_bytes_and_deadline_fail_before_admission(self):
        value = self.document()
        path = Path(value['predecessors'][0]['artifacts']['archive']['path'])
        path.chmod(0o600); path.write_bytes(path.read_bytes()+b'x')
        with self.assertRaisesRegex(ValueError, 'size cap/pin'):
            self.admit(value)
        with self.assertRaisesRegex(ValueError, 'deadline'):
            recovery.admit(value, self.fx.admitted, self.fx.base, reviewed_sources=self.fx.source,
                           deadline=time.monotonic()-1.)

    def test_repeated_recovery_can_use_same_source_but_must_pin_exact_ancestry(self):
        value = self.document()
        first = self.admit(value)
        attempt = self.root/'recovery-ancestor'; evidence = attempt/'evidence'; evidence.mkdir(parents=True)
        def write(path, body):
            path.write_bytes(raw(body)); return self.pin(path)
        external_plan = write(self.root/'ancestor-plan.json', value)
        copied_plan = write(evidence/'recovery-plan.json', value)
        cold = dict(candidate_models=0, history=[dict(first.history()[0], gzip_eof=True, trailing_partial_row_bytes=0)])
        cold_pin = write(evidence/'cold-replay.json', cold)
        selection = write(evidence/'window-selection.json', first.selection())
        base = write(evidence/'base-registry.json', self.fx.base.metadata())
        args = SimpleNamespace(**self.fx.values, worker=False, deadline=None, cpu=None, attempt_dir=None,
            recovery_plan=Path(external_plan['path']), recovery_plan_sha=external_plan['sha256'])
        request = json.loads(Path(value['predecessors'][0]['artifacts']['request']['path']).read_bytes())
        request['command'] = runner.worker_command(args, request['deadline_monotonic'])
        request['context']['input_sha256'] = plan.digest(runner.input_context(args))
        request_pin = write(attempt/'request.json', request)
        resources = runner.resource_plan(args.worker_cpus, first.selection()['window_plan']['expected_model_count'], 0)
        context = dict(first.history()[0]['source_context'], schema='hiroute-suffix-window-recovery-context-v1',
            resource_plan_sha256=plan.digest(resources), recovery_plan_sha256=copied_plan['sha256'],
            cold_replay_sha256=cold_pin['sha256'], history_sha256=plan.digest(cold['history']),
            previous_archive=first.history()[0]['archive'],
            previous_source_context_sha256=plan.digest(first.history()[0]['source_context']))
        old_run = json.loads(Path(value['predecessors'][0]['artifacts']['run_binding']['path']).read_bytes())
        old_run.update(schema='hiroute-suffix-window-recovery-binding-v1', resource_plan=resources,
            source_context=context, recovery_plan=recovery._relative(copied_plan, 'recovery-plan.json'),
            cold_replay=recovery._relative(cold_pin, 'cold-replay.json'))
        old_run['invocation_origin'].update(controller_module=runner.MODULE,
            controller_path=str(self.root/'experiments/time_cut_v2/recorded_real/suffix_window_recovery.py'))
        run_pin = write(evidence/'run-binding.json', old_run)
        archive = evidence/'recovery-model-proofs.jsonl.gz'; archive.write_bytes(b'fake interrupted bytes')
        artifacts = dict.fromkeys(recovery.FILES)
        artifacts.update(request=request_pin, run_binding=run_pin, selection=selection, base_registry=base,
            source_policy=value['predecessors'][0]['artifacts']['source_policy'], archive=self.pin(archive),
            recovery_plan=copied_plan, cold_replay=cold_pin)
        value['predecessors'].append(dict(module=runner.MODULE, source_commit='f'*40, source_sha256='e'*64,
            attempt=str(attempt), archive_mode='interrupted-prefix', source_context=context, artifacts=artifacts))
        repeated = self.admit(value)
        self.assertEqual(len(repeated.history()), 2)
        self.assertEqual(repeated.history()[0]['source_context']['source_sha256'],
                         repeated.history()[1]['source_context']['source_sha256'])
        changed = json.loads(Path(copied_plan['path']).read_bytes())
        changed['predecessors'][0]['archive_mode'] = 'interrupted-prefix'
        copied_plan.update(write(Path(copied_plan['path']), changed))
        with self.assertRaisesRegex(ValueError, 'ancestry changed'):
            self.admit(value)


if __name__ == '__main__':
    unittest.main()
