"""The generic runner's boundaries with fake transport and hand proofs only."""
from contextlib import contextmanager, redirect_stdout
from copy import deepcopy
import gzip
import hashlib
import io
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from experiments.time_cut_v2.recorded_real import suffix_window as runner, plan, runtime
from experiments.time_cut_v2.recorded_real import block_archive, window_receipts as receipts
from tests.test_suffix_block_archive import FakeResults, outcomes
from tests.test_suffix_block_certificates import declaration
from tests.test_suffix_window_plan import population, SEEDS
from tests import test_indexed_suffix_population as admitted_fixtures
from tests import test_suffix_window_receipts as receipt_fixtures
from validation.capture5.containers import detach_json
from validation.suffix5.test_convex_checker import hand_record
from validation.suffix5.window_plan import next_window


class RunnerPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def arguments(self, *, later=False):
        argv = []
        for key in receipts.COMMON_PATHS + ('source_policy', 'registry_output', 'registration_return_output'):
            argv += ['--'+key.replace('_', '-'), str(self.root/key)]
        for key in receipts.COMMON_PINS + ('source_policy_sha',):
            argv += ['--'+key.replace('_', '-'), 'a'*(40 if key == 'source_commit' else 64)]
        argv += ['--worker-cpus', '1', '2', '3', '4', '5', '--cpu', '0',
                 '--attempt-dir', str(self.root/'attempt')]
        if later:
            for key in runner.REGISTRY_FIELDS:
                argv += ['--'+key.replace('_', '-'), 'b'*64 if key.endswith('_sha') else str(self.root/key)]
        else:
            for key in runner.SEED_FIELDS[:5]:
                argv += ['--'+key.replace('_', '-'), str(self.root/key)]
        return runner.parser().parse_args(argv)

    def policy(self, args, sources=None, canonical=True):
        value = dict(schema='hiroute-reviewed-window-sources-v1', reviewed_sources=sources or {
            args.source_commit: args.source_sha, receipts.SEED_COMMIT: receipts.SEED_SOURCE})
        data = plan.canonical(value)+b'\n' if canonical else json.dumps(value, indent=2).encode()
        args.source_policy.write_bytes(data)
        args.source_policy_sha = hashlib.sha256(data).hexdigest()
        return value['reviewed_sources']

    def test_fixed_resource_contract_preserves_cumulative_input_cap(self):
        resource = runner.resource_plan([1, 2, 3, 4, 5], 8192)
        self.assertEqual(resource['maximum_input_bytes'], 128*1024**2)
        self.assertEqual(resource['maximum_candidate_passes'], 98304)
        self.assertEqual(resource['maximum_logical_stages'], 40960)
        self.assertEqual(resource['candidate_as_bytes'], 1024**3)
        self.assertEqual(resource['candidate_peak_rss_bytes'], 768*1024**2)
        self.assertEqual(resource['absolute_seconds'], 900)
        self.assertEqual(resource['evidence_charge_bytes'], 512*1024**2)
        self.assertEqual(resource['uncompressed_archive_bytes'], 512*1024**2)
        self.assertEqual(runtime.BATCH_REPLAY.group_rss_bytes, 20*1024**3)
        self.assertEqual(runtime.BATCH_REPLAY.host_reserve_bytes, 16*1024**3)
        self.assertFalse(resource['numerical_cache_enabled'])
        for cpus, models in (([1, 2, 3, 4, True], 1), ([1, 1, 3, 4, 5], 1),
                             ([1, 2, 3, 4, 5], 8193), ([1, 2, 3, 4, 5], True)):
            with self.assertRaises(ValueError):
                runner.resource_plan(cpus, models)

    def test_context_preserves_types_and_optional_null_without_collision(self):
        args = self.arguments()
        context = runner.input_context(args)
        self.assertEqual(context['worker_cpus'], [1, 2, 3, 4, 5])
        self.assertIsNone(context['registry'])
        self.assertEqual(context['capture'], str(args.capture))
        self.assertFalse(set(context) & runner.INPUT_EXCLUSIONS)
        other = deepcopy(args); other.registry = 'None'
        self.assertNotEqual(plan.digest(context), plan.digest(runner.input_context(other)))
        command = runner.worker_command(args, 1000.)
        self.assertEqual(command[command.index('-m')+1], runner.MODULE)
        self.assertNotIn('--registry', command)
        self.assertNotIn('None', command)
        parsed = runner.parser().parse_args(command[4:])
        self.assertEqual(runner.input_context(parsed), context)
        for key in runner.REGISTRY_FIELDS + runner.SEED_FIELDS[5:]:
            self.assertIsNone(getattr(parsed, key))

    def test_command_reconstructs_receipt_context_with_optional_nulls(self):
        for later in (False, True):
            args = self.arguments(later=later)
            request = dict(command=runner.worker_command(args, 1000.), deadline_monotonic=1000.,
                worker_cpus=args.worker_cpus, context=dict(plan_sha256=args.replay_plan_sha,
                source_sha256=args.source_sha, input_sha256=plan.digest(runner.input_context(args)),
                profile_name=runtime.BATCH_REPLAY.name))
            actual = receipts._command(request, 'suffix_window')
            self.assertEqual({key: value for key, value in actual.items() if key != 'deadline'},
                             runner.input_context(args))

    def test_seed_and_registry_admissions_are_exclusive(self):
        initial = self.arguments()
        later = self.arguments(later=True)
        self.assertEqual(runner.admission_mode(initial), 'seed')
        self.assertEqual(runner.admission_mode(later), 'registry')
        self.assertEqual(runner.registry_admission(initial)['successful_return_sha256'], receipts.SEED_RETURN)
        self.assertEqual(runner.registry_admission(later)['registry_sha256'], later.registry_sha)
        initial.registry_sha = 'a'*64
        later.old_archive = Path('/old')
        for args in (initial, later):
            with self.assertRaises(ValueError): runner.admission_mode(args)

    def test_source_policy_requires_current_seed_and_exact_canonical_pin(self):
        args = self.arguments()
        expected = self.policy(args)
        self.assertEqual(runner.source_policy(args), expected)
        for sources in ({args.source_commit: args.source_sha},
                        {receipts.SEED_COMMIT: receipts.SEED_SOURCE},
                        {args.source_commit: 'x'*64, receipts.SEED_COMMIT: receipts.SEED_SOURCE}):
            self.policy(args, sources)
            with self.assertRaises(ValueError): runner.source_policy(args)
        self.policy(args, canonical=False)
        with self.assertRaisesRegex(ValueError, 'canonical'): runner.source_policy(args)
        self.policy(args)
        args.source_policy.write_bytes(args.source_policy.read_bytes()+b' ')
        with self.assertRaises(ValueError): runner.source_policy(args)

    def test_expected_evidence_set_has_exactly_eight_files(self):
        self.assertEqual(runner.EVIDENCE_FILES, {'run-binding.json', 'batch-ledger.json', 'family-summary.json',
            'block-plan.json', 'base-registry.json', 'window-selection.json', 'model-proofs.jsonl.gz', 'window-summary.json'})

    @contextmanager
    def controller_dependencies(self, args, window=None, result=None):
        sources = self.policy(args)
        with patch.object(runner.resource, 'getrlimit', return_value=(1024**3, resource_infinity())), \
             patch.object(runner.resource, 'setrlimit') as limits, \
             patch.object(runner, '_live_checks') as live, \
             patch.object(runner.suffix_census, 'check_sources', return_value={}), \
             patch.object(runner, 'check_invocation_origin', return_value={'observed': 'trusted test invocation'}), \
             patch.object(runner, 'verify_loaded'), \
             patch.object(runner, 'load_registry', return_value=(object(), SimpleNamespace(completed_block_ids=lambda: tuple(SEEDS)))), \
             patch.object(runner, 'plan_window', return_value=window or dict(launch_required=True, window_id='d'*64)), \
             patch.object(runner, 'run_phase', return_value=result or dict(status='failed', reason='fake interruption')) as phase:
            yield SimpleNamespace(limits=limits, live=live, phase=phase, sources=sources)

    def test_controller_uses_existing_group_and_entry_including_admission(self):
        args = self.arguments()
        with self.controller_dependencies(args) as observed:
            result = runner.controller(args)
        self.assertEqual(result['status'], 'unregistered')
        self.assertEqual(observed.limits.call_args.args[1][0], 512*1024**2)
        call = observed.phase.call_args
        self.assertIs(call.kwargs['profile'], runtime.BATCH_REPLAY)
        self.assertEqual(call.kwargs['deadline_monotonic']-call.kwargs['entry_monotonic'], 900)
        self.assertEqual(call.kwargs['entry_monotonic'], runner.ENTRY)
        self.assertEqual(call.kwargs['worker_cpus'], (1, 2, 3, 4, 5))
        self.assertEqual(call.kwargs['context'].input_sha256, plan.digest(runner.input_context(args)))
        self.assertTrue(observed.live.called)
        self.assertFalse(args.registry_output.exists())

    def test_terminal_empty_never_launches_and_never_claims_query_closure(self):
        args = self.arguments(later=True)
        with self.controller_dependencies(args, window=dict(launch_required=False, window_id=None)) as observed:
            result = runner.controller(args)
        observed.phase.assert_not_called()
        self.assertEqual(result['status'], 'terminal_empty')
        for key in runner.FALSE_AUTHORITY: self.assertIs(result[key], False)
        self.assertFalse(args.registry_output.exists())

    def test_deadline_during_admission_prevents_any_launch(self):
        args = self.arguments()
        with self.controller_dependencies(args) as observed, \
             patch.object(runner, '_live_checks', side_effect=TimeoutError('absolute deadline')):
            with self.assertRaises(TimeoutError): runner.controller(args)
        observed.phase.assert_not_called()

    def test_failed_registration_keeps_raw_attempt_and_actual_return(self):
        args = self.arguments()
        actual = dict(status='completed', returned_marker='actual return, not reconstructed')
        with self.controller_dependencies(args, result=actual), \
             patch.object(runner, 'register_completed', side_effect=TimeoutError('registration deadline')):
            result = runner.controller(args)
        self.assertEqual(result['status'], 'registration_failed')
        self.assertEqual(json.loads(runner.runtime_return_path(args).read_bytes()), actual)
        self.assertFalse(args.registration_return_output.exists())
        with self.controller_dependencies(args) as observed:
            with self.assertRaisesRegex(ValueError, 'fresh'): runner.controller(args)
        observed.phase.assert_not_called()
        self.assertEqual(json.loads(runner.runtime_return_path(args).read_bytes()), actual)

    def test_first_postreturn_deadline_failure_returns_actual_receipt_without_claiming_persistence(self):
        args = self.arguments()
        actual = dict(status='completed', acceptance_receipt=dict(returned_monotonic=123.,
            result_sha256='1'*64, decision_sha256='2'*64, manifest_sha256='3'*64))
        returned = False
        archive = args.attempt_dir/'model-proofs.jsonl.gz'
        def completed(*_, **__):
            nonlocal returned
            args.attempt_dir.mkdir()
            archive.write_bytes(b'completed raw proof bytes')
            returned = True
            return actual
        def live(*_, **__):
            if returned: raise TimeoutError('first check after actual return')
        with self.controller_dependencies(args) as observed:
            observed.phase.side_effect = completed
            observed.live.side_effect = live
            result = runner.controller(args)
        self.assertEqual(result['status'], 'registration_failed')
        self.assertIs(result['runtime_result'], actual)
        self.assertFalse(runner.runtime_return_path(args).exists())
        self.assertFalse(args.registration_return_output.exists())
        self.assertFalse(args.registry_output.exists())
        self.assertEqual(archive.read_bytes(), b'completed raw proof bytes')

    def test_late_runtime_return_write_failure_exposes_actual_return_and_keeps_bytes(self):
        args = self.arguments()
        actual = dict(status='completed', acceptance_receipt=dict(returned_monotonic=123.,
            result_sha256='1'*64, decision_sha256='2'*64, manifest_sha256='3'*64))
        write = runner._exclusive_json
        def late_write(*call_args, **call_kwargs):
            write(*call_args, **call_kwargs)
            raise OSError('late sidecar directory sync failure')
        with self.controller_dependencies(args, result=actual), \
             patch.object(runner, '_exclusive_json', side_effect=late_write):
            result = runner.controller(args)
        self.assertEqual(result['status'], 'registration_failed')
        self.assertIs(result['runtime_result'], actual)
        self.assertEqual(json.loads(runner.runtime_return_path(args).read_bytes()), actual)
        self.assertFalse(args.registration_return_output.exists())
        self.assertFalse(args.registry_output.exists())

    def test_old_output_and_nested_attempt_destinations_fail_closed(self):
        for mode in ('old', 'nested', 'alias'):
            args = self.arguments()
            if mode == 'old': args.registry_output.write_bytes(b'previous registry')
            elif mode == 'nested': args.registry_output = args.attempt_dir/'registry'
            else: args.registration_return_output = args.registry_output.parent/'unused'/'..'/args.registry_output.name
            with self.controller_dependencies(args) as observed:
                with self.assertRaises(ValueError): runner.controller(args)
            observed.phase.assert_not_called()
            if mode == 'old':
                self.assertEqual(args.registry_output.read_bytes(), b'previous registry')
                args.registry_output.unlink()

    def test_late_registration_return_is_revoked_but_previous_return_is_preserved(self):
        path = self.root/'return.json'
        calls = []
        def late():
            calls.append(1)
            if len(calls) == 3: raise TimeoutError('late publication')
        with self.assertRaises(TimeoutError):
            runner.retain_return({'status': 'registered'}, path, late, revoke_on_failure=True)
        self.assertFalse(path.exists())
        path.write_bytes(b'previous return')
        with self.assertRaises(FileExistsError):
            runner.retain_return({'status': 'registered'}, path, lambda: None, revoke_on_failure=True)
        self.assertEqual(path.read_bytes(), b'previous return')


def resource_infinity():
    return runner.resource.RLIM_INFINITY


class RunnerOriginTests(unittest.TestCase):
    def test_origin_observes_live_checkout_module_and_interpreter(self):
        observed = runner.check_invocation_origin()
        self.assertEqual(observed['schema'], 'hiroute-reviewed-controller-origin-v1')
        self.assertEqual(observed['cwd'], str(plan.ROOT.resolve()))
        self.assertEqual(observed['checkout_root'], observed['cwd'])
        self.assertEqual(observed['controller_module'], runner.MODULE)
        self.assertEqual(observed['controller_path'], str(Path(runner.__file__).resolve()))
        self.assertEqual(observed['python_executable'], runner.sys.executable)
        self.assertEqual(observed['executable_realpath'], str(Path(runner.sys.executable).resolve()))

    def test_wrong_cwd_module_resolution_or_interpreter_rejects(self):
        cases = [patch.object(runner.Path, 'cwd', return_value=Path('/tmp')),
                 patch.object(runner, '__file__', '/tmp/unreviewed.py'),
                 patch.object(runner.importlib.util, 'find_spec', return_value=SimpleNamespace(origin='/tmp/unreviewed.py')),
                 patch.object(runner.sys, 'executable', '/usr/bin/true')]
        for case in cases:
            with case, self.assertRaises(ValueError): runner.check_invocation_origin()

    def test_loaded_controller_shadow_and_changed_source_pin_rejects(self):
        module = runner.sys.modules['experiments.time_cut_v2.recorded_real.runtime']
        with patch.object(module, '__file__', '/tmp/shadow/runtime.py'), self.assertRaisesRegex(ValueError, 'foreign loaded'):
            runner.check_invocation_origin()
        sources = runner.suffix_census.source_inventory(plan.ROOT)
        runner.check_invocation_origin(sources)
        relative = Path(module.__file__).resolve().relative_to(plan.ROOT).as_posix()
        sources[relative] = dict(sources[relative], sha256='0'*64)
        with self.assertRaisesRegex(ValueError, 'source bytes changed'):
            runner.check_invocation_origin(sources)


class RunnerSelectionTests(unittest.TestCase):
    def setUp(self):
        self.fx = admitted_fixtures.IndexedPopulationTests()
        self.fx.setUp(); self.addCleanup(self.fx.doCleanups)
        self.admitted = self.fx.admit()
        self.registry = receipts.make_registry(self.admitted, [])

    def test_freeze_uses_original_descriptors_before_model_construction(self):
        population = self.admitted.population.plan()
        window = detach_json(next_window(population, (), population_plan_sha256=plan.digest(population)))
        with patch.object(runner, 'plan_window', return_value=window), \
             patch('validation.suffix5.convex_model.build_model', side_effect=AssertionError('premature matrix')):
            selected = runner.freeze_selection(self.admitted, self.registry)
        self.assertEqual(selected['window_plan'], window)
        self.assertEqual([block['range'] for block in selected['blocks']], window['blocks'])
        for block in selected['blocks']:
            self.admitted.population.check_block_descriptors(block['range']['block_id'], block['descriptors'])
        self.assertEqual(selected['maximum_candidate_passes'], window['expected_model_count']*12)
        self.assertEqual(selected['maximum_logical_stages'], window['expected_model_count']*5)
        with self.assertRaisesRegex(ValueError, 'fresh genuine'):
            runner.freeze_selection(SimpleNamespace(population=self.admitted.population), self.registry)

    def test_registry_and_population_dicts_cannot_supply_scheduling_authority(self):
        with self.assertRaisesRegex(ValueError, 'typed checked'):
            runner.plan_window(self.admitted, self.registry.metadata())
        with self.assertRaisesRegex(ValueError, 'authenticated original'):
            runner.plan_window(SimpleNamespace(), self.registry)

    def test_next_8192_window_preserves_original_ids_and_short_tail(self):
        # Synthetic full-size catalogue and typed test scope; no real proofs or
        # numerical authority are claimed by this structural selection fixture.
        catalog = population()
        commitment = dict(block_plan_sha256=plan.digest(catalog), source_bundle_sha256='a'*64,
            case_sha256='b'*64, logical_plan_sha256='c'*64, unique_logical_models=695712,
            original_model_occurrences=7652832)
        scope = receipts.ReceiptScope(catalog, commitment, _token=receipts._ADMISSION)
        synthetic = dict(population=commitment, blocks=[dict(range=catalog['blocks'][i]) for i in SEEDS])
        registry = receipts.CheckedRegistry(synthetic, (), _token=receipts._ADMISSION)
        selected = runner.plan_window(scope, registry)
        self.assertEqual(selected['block_ids'], list(range(1, 33)))
        self.assertEqual(selected['expected_model_count'], 8192)
        self.assertEqual(selected['expected_ordinal_ranges'], [[i*256, (i+1)*256] for i in range(1, 33)])
        later = dict(population=commitment, blocks=[dict(range=catalog['blocks'][i]) for i in range(2717)])
        final = runner.plan_window(scope, receipts.CheckedRegistry(later, (), _token=receipts._ADMISSION))
        self.assertEqual(final['block_ids'], [2717])
        self.assertEqual(final['expected_model_count'], 160)
        self.assertEqual(final['expected_ordinal_ranges'], [[695552, 695712]])


class RunnerProofTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ctx, self.record = hand_record('C', 1, True)
        self.context = dict(schema='hiroute-suffix-window-context-v1', window_id='f'*64)
        self.selection = dict(blocks=declaration([self.record]))

    def publish(self, stream, before=lambda: None):
        with runtime.BoundedEvidenceWriter(self.root/'proofs', runtime.BATCH_REPLAY.worker_evidence_bytes,
            profile_name=runtime.BATCH_REPLAY.name) as raw, redirect_stdout(io.StringIO()) as progress:
            result = runner.publish_proofs(self.ctx, self.selection, self.context,
                block_archive.QuotaWriter(raw, before), stream, deadline=time.monotonic()+30, before=before)
            raw.finalize()
        return result, progress.getvalue()

    def test_hand_proof_is_full_archive_and_progress_is_provisional(self):
        proof, progress = self.publish(FakeResults(outcomes([self.record], self.context)))
        rows = [json.loads(row) for row in gzip.decompress((self.root/'proofs/model-proofs.jsonl.gz').read_bytes()).splitlines()]
        self.assertTrue(proof['footer']['complete'])
        self.assertEqual(next(row['record'] for row in rows if row['kind'] == 'model_certificate'), self.record)
        self.assertEqual(json.loads(progress)['acceptance'], False)
        self.assertEqual(rows[0]['source_context'], self.context)
        self.assertTrue(proof['encoding']['complete'])
        self.assertEqual(proof['footer']['verified_models'], 1)
        for key in runner.FALSE_AUTHORITY: self.assertIs(proof['footer'][key], False)

    def test_unresolved_and_dirty_transport_never_publish_success(self):
        stream = FakeResults(outcomes([self.record], self.context))
        stream.summary['all_processes_reaped'] = False
        proof, _ = self.publish(stream)
        self.assertFalse(proof['footer']['complete'])

    def test_late_exact_exit_does_not_publish_footer_or_stale_receipt(self):
        @contextmanager
        def late(_):
            yield
            raise TimeoutError('late exact check')
        with patch('validation.suffix5.calibration.verification_deadline', late), self.assertRaises(TimeoutError):
            self.publish(FakeResults(outcomes([self.record], self.context)))
        self.assertFalse((self.root/'proofs/__manifest.json').exists())


class RunnerRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.fx = receipt_fixtures.WindowReceiptTests()
        self.fx.setUp(); self.addCleanup(self.fx.doCleanups)
        self.completed = self.fx.fixture()
        self.result = json.loads(self.completed.window_return.read_bytes())
        self.args = SimpleNamespace(attempt_dir=self.completed.window_attempt,
            registry_output=Path(self.fx.values['registry_output']),
            registration_return_output=Path(self.fx.values['registration_return_output']))
        self.archive = self.args.attempt_dir/'evidence/model-proofs.jsonl.gz'
        self.archive_bytes = self.archive.read_bytes()

    def register(self, **options):
        return runner.register_completed(self.args, self.fx.admitted, self.fx.base, self.result,
            self.fx.source, deadline=time.monotonic()+30, before=lambda: None, **options)

    def test_actual_return_and_actual_registration_survive_restart(self):
        registered = self.register()
        self.assertEqual(registered['status'], 'registered')
        self.assertEqual(json.loads(runner.runtime_return_path(self.args).read_bytes()), self.result)
        actual = json.loads(self.args.registration_return_output.read_bytes())
        loaded = receipts.load_scheduling_registry(self.args.registry_output,
            registered['registry']['sha256'], self.fx.admitted,
            registration_return=self.args.registration_return_output,
            registration_return_sha=registered['registration_return']['sha256'],
            reviewed_sources=self.fx.source, deadline=time.monotonic()+30)
        self.assertEqual(loaded.completed_block_ids(), (0,))
        self.assertEqual(actual['registry_sha256'], registered['registry']['sha256'])
        self.assertEqual(self.archive.read_bytes(), self.archive_bytes)
        with self.assertRaises(FileExistsError): self.register()
        self.assertEqual(self.archive.read_bytes(), self.archive_bytes)

    def test_invalid_completed_proof_preserves_raw_and_has_no_registry_authority(self):
        self.archive.chmod(0o600)
        self.archive.write_bytes(self.archive_bytes+b'tampered')
        with self.assertRaises(ValueError): self.register()
        self.assertEqual(json.loads(runner.runtime_return_path(self.args).read_bytes()), self.result)
        self.assertFalse(self.args.registry_output.exists())
        self.assertFalse(self.args.registration_return_output.exists())
        self.assertEqual(self.archive.read_bytes(), self.archive_bytes+b'tampered')

    def test_source_or_deadline_failure_at_final_publish_revokes_only_new_return(self):
        calls = []
        def fail_late():
            calls.append(1)
            if len(calls) == 4: raise TimeoutError('late registration publication')
        with self.assertRaises(TimeoutError): self.register(final_check=fail_late)
        self.assertEqual(json.loads(runner.runtime_return_path(self.args).read_bytes()), self.result)
        self.assertTrue(self.args.registry_output.exists())
        self.assertFalse(self.args.registration_return_output.exists())
        self.assertEqual(self.archive.read_bytes(), self.archive_bytes)


if __name__ == '__main__':
    unittest.main()
