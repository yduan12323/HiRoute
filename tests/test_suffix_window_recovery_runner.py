"""The recovery controller/transport seams use tiny fake results only."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import time
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from experiments.time_cut_v2.recorded_real import suffix_window_recovery as runner
from experiments.time_cut_v2.recorded_real import suffix_window, recovery_plan, plan, runtime
from tests import test_suffix_window_runner as fixtures


class RecoveryRunnerTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.RunnerPolicyTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root

    def arguments(self):
        args = self.fixture.arguments(later=True)
        args.recovery_plan = self.root/'recovery-plan.json'
        args.recovery_plan_sha = '9'*64
        return args

    @contextmanager
    def controller_dependencies(self, args, result=None):
        self.fixture.policy(args)
        history = SimpleNamespace(selection=lambda: dict(window_plan=dict(window_id='d'*64, launch_required=True)),
                                  document=lambda: dict(fake=True))
        with patch.object(runner.resource, 'getrlimit', return_value=(1024**3, resource.RLIM_INFINITY)), \
             patch.object(runner.resource, 'setrlimit') as limits, \
             patch.object(runner, '_live_checks') as live, \
             patch.object(runner.suffix_census, 'check_sources', return_value={}) as sources, \
             patch.object(runner, 'check_invocation_origin', return_value={'observed': 'trusted invocation'}), \
             patch.object(runner, 'verify_loaded'), \
             patch.object(runner, 'load_registry', return_value=(object(), object())), \
             patch.object(runner, 'load_recovery', return_value=history), \
             patch.object(runner, 'run_phase', return_value=result or dict(status='failed', reason='tiny failure')) as phase:
            yield SimpleNamespace(limits=limits, live=live, phase=phase, sources=sources)

    def test_new_command_contract_preserves_old_optional_null_digest(self):
        old = self.fixture.arguments(later=True)
        old_context = suffix_window.input_context(old)
        args = self.arguments()
        argv = runner.worker_command(args, 1000.)
        request = dict(command=argv, deadline_monotonic=1000., worker_cpus=args.worker_cpus,
            context=dict(plan_sha256=args.replay_plan_sha, source_sha256=args.source_sha,
                input_sha256=plan.digest(runner.input_context(args)), profile_name=runtime.BATCH_REPLAY.name))
        actual = recovery_plan.command(request)
        self.assertEqual({k: v for k, v in actual.items() if k != 'deadline'}, runner.input_context(args))
        self.assertEqual(suffix_window.input_context(old), old_context)
        self.assertNotIn('recovery_plan', old_context)
        self.assertIsNone(actual['seed_attempt'])
        request['command'].extend(['--recovery-plan-sha', '0'*64])
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            recovery_plan.command(request)

    def test_bounded_candidate_resource_contract_includes_zero(self):
        for count in (0, 3, 8192):
            value = runner.resource_plan([1, 2, 3, 4, 5], 8192, count)
            self.assertEqual(value['models'], 8192)
            self.assertEqual(value['candidate_models'], count)
            self.assertEqual(value['retained_models'], 8192-count)
            self.assertEqual(value['maximum_candidate_passes'], count*12)
            self.assertEqual(value['maximum_logical_stages'], count*5)
            self.assertEqual(value['absolute_seconds'], 900)
            self.assertEqual(value['maximum_input_bytes'], 128*1024**2)
            self.assertEqual(value['candidate_as_bytes'], 1024**3)
            self.assertFalse(value['numerical_cache_enabled'])
        for candidate in (True, -1, 8193):
            with self.assertRaises(ValueError): runner.resource_plan([1, 2, 3, 4, 5], 8192, candidate)

    def test_zero_retry_never_constructs_jobs_or_candidate_workers(self):
        args = self.arguments(); args.deadline = time.monotonic()+60
        session = SimpleNamespace(summary=lambda: dict(candidate_models=0), candidate_jobs=Mock())
        core = ModuleType('experiments.time_cut_v2.recorded_real.window_recovery_core')
        core.publish_proofs = Mock(return_value={'tiny': 'exact-only proof'})
        with patch.dict(sys.modules, {core.__name__: core}), \
             patch('experiments.time_cut_v2.recorded_real.lp_stream_jobs.stream_results') as stream:
            result = runner.execute_recovery(session, {}, object(), args, lambda: None)
        stream.assert_not_called(); session.candidate_jobs.assert_not_called()
        self.assertEqual(result, {'tiny': 'exact-only proof'})
        self.assertIsNone(core.publish_proofs.call_args.kwargs['outcomes'])

    def test_complement_job_iterator_passed_directly_under_fixed_limits(self):
        args = self.arguments(); args.deadline = time.monotonic()+60
        jobs = iter([dict(ordinal=7)])
        session = SimpleNamespace(summary=lambda: dict(candidate_models=1), candidate_jobs=Mock(return_value=jobs))
        core = ModuleType('experiments.time_cut_v2.recorded_real.window_recovery_core')
        core.publish_proofs = Mock(return_value={'tiny': 'new proof'})
        with patch.dict(sys.modules, {core.__name__: core}), patch.object(os, 'sched_setaffinity'), \
             patch('experiments.time_cut_v2.recorded_real.lp_stream_jobs.stream_results') as stream:
            runner.execute_recovery(session, {'source': 'current'}, object(), args, lambda: None)
        self.assertIs(stream.call_args.args[0], jobs)
        self.assertEqual(stream.call_args.kwargs['max_jobs'], 1)
        self.assertEqual(stream.call_args.kwargs['max_input_bytes'], 128*1024**2)
        self.assertEqual(stream.call_args.kwargs['deadline_monotonic'], args.deadline-10)
        self.assertEqual(session.candidate_jobs.call_args.args, ({'source': 'current'},))

    def test_failed_actual_return_is_retained_and_not_registered(self):
        args = self.arguments(); actual = dict(status='unresolved', reason='tiny fresh failure', marker=['actual'])
        with self.controller_dependencies(args, actual) as observed, patch.object(runner, 'register_completed') as register:
            result = runner.controller(args)
        self.assertIs(result['runtime_result'], actual)
        self.assertEqual(json.loads(runner.runtime_return_path(args).read_bytes()), actual)
        self.assertEqual(result['status'], 'unregistered')
        register.assert_not_called()
        self.assertFalse(args.registry_output.exists())
        call = observed.phase.call_args
        self.assertIs(call.kwargs['profile'], runtime.BATCH_REPLAY)
        self.assertEqual(call.kwargs['deadline_monotonic']-call.kwargs['entry_monotonic'], 900)
        self.assertEqual(call.kwargs['entry_monotonic'], runner.ENTRY)
        self.assertEqual(call.kwargs['context'].input_sha256, plan.digest(runner.input_context(args)))
        self.assertEqual(observed.limits.call_args.args[1][0], 512*1024**2)

    def test_existing_attempt_or_external_output_never_overwritten(self):
        args = self.arguments(); path = runner.runtime_return_path(args); path.write_text('older evidence')
        with self.controller_dependencies(args) as observed:
            with self.assertRaisesRegex(ValueError, 'fresh'): runner.controller(args)
        observed.phase.assert_not_called()
        self.assertEqual(path.read_text(), 'older evidence')
        path.unlink(); args.registry_output = args.attempt_dir/'registry.json'
        with self.controller_dependencies(args) as observed:
            with self.assertRaisesRegex(ValueError, 'outside'): runner.controller(args)
        observed.phase.assert_not_called()

    def test_deadline_in_plan_admission_prevents_launch(self):
        args = self.arguments()
        with self.controller_dependencies(args) as observed, \
             patch.object(runner, 'load_recovery', side_effect=TimeoutError('total absolute deadline')):
            with self.assertRaises(TimeoutError): runner.controller(args)
        observed.phase.assert_not_called()

    def test_metadata_change_after_actual_success_preserves_raw_and_return(self):
        args = self.arguments(); actual = dict(status='completed', marker='actual success')
        with self.controller_dependencies(args, actual) as observed, patch.object(runner, 'register_completed') as register:
            observed.sources.side_effect = [{}, ValueError('source changed after completion')]
            result = runner.controller(args)
        self.assertEqual(result['status'], 'registration_failed')
        self.assertIs(result['runtime_result'], actual)
        self.assertEqual(json.loads(runner.runtime_return_path(args).read_bytes()), actual)
        register.assert_not_called(); self.assertFalse(args.registry_output.exists())

    def test_first_postreturn_deadline_does_not_invent_persisted_receipt(self):
        args = self.arguments(); actual = dict(status='completed', marker='returned but expired')
        returned = False
        def phase(*args, **kwargs):
            nonlocal returned
            returned = True
            return actual
        def check(*args, **kwargs):
            if returned: raise TimeoutError('total deadline after return')
        with self.controller_dependencies(args) as observed:
            observed.phase.side_effect = phase; observed.live.side_effect = check
            result = runner.controller(args)
        self.assertIs(result['runtime_result'], actual)
        self.assertFalse(runner.runtime_return_path(args).exists())
        self.assertFalse(args.registration_return_output.exists())

    def test_import_is_inert_and_origin_requires_reviewed_checkout(self):
        script = ('import sys; from experiments.time_cut_v2.recorded_real import suffix_window_recovery as r; '
            'assert not any(x == "validation" or x.startswith(("validation.", "timecut5")) '
            'or x.split(".")[0] in ("numpy", "scipy", "sympy") for x in sys.modules); '
            'assert r.check_invocation_origin()["controller_module"] == r.MODULE')
        completed = subprocess.run([sys.executable, '-B', '-c', script], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        with patch.object(Path, 'cwd', return_value=self.root):
            with self.assertRaisesRegex(ValueError, 'checkout cwd'): runner.check_invocation_origin()


if __name__ == '__main__':
    unittest.main()
