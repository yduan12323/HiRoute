"""Single-block proposal boundaries; synthetic plans and request transport only."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from experiments.time_cut_v2.recorded_real import suffix_window as runner, runtime, plan
from experiments.time_cut_v2.recorded_real import window_receipts as receipts
from tests.test_suffix_window_plan import population
from tests import test_suffix_window_runner as runner_fixtures
from validation.capture5.containers import detach_json
from validation.family5.checker import digest
from validation.suffix5.window_plan import next_window, check_window_plan


class SingleBlockSelectionTests(unittest.TestCase):
    def test_entire_d0_catalogue_stays_fixed_while_first_block_is_selected(self):
        full = population(844440)
        selected = next_window(full, [], population_plan_sha256=digest(full), maximum_blocks=1)
        self.assertEqual(selected['block_ids'], (0,))
        self.assertEqual(selected['expected_ordinal_ranges'], ((0, 256),))
        self.assertEqual(selected['expected_model_count'], 256)
        self.assertEqual(selected['population']['total_models'], 844440)
        self.assertEqual(selected['population']['total_blocks'], 3299)
        self.assertEqual(selected['operation_budget']['maximum_blocks'], 1)
        self.assertEqual(selected['operation_budget']['maximum_models'], 256)
        self.assertEqual(selected['operation_budget']['absolute_seconds'], 900)
        self.assertFalse(selected['numerical_acceptance'])
        self.assertFalse(selected['literal_G8_closed'])
        check_window_plan(detach_json(selected), full, [],
                          population_plan_sha256=digest(full), maximum_blocks=1)
        with self.assertRaises(ValueError):
            check_window_plan(detach_json(selected), full, [],
                              population_plan_sha256=digest(full), maximum_blocks=2)

    def test_default_selection_identity_and_budget_remain_identical(self):
        full = population(844440)
        implicit = next_window(full, [], population_plan_sha256=digest(full))
        explicit = next_window(full, [], population_plan_sha256=digest(full), maximum_blocks=32)
        self.assertEqual(implicit, explicit)
        self.assertEqual(implicit['block_ids'], tuple(range(32)))
        self.assertEqual(implicit['expected_model_count'], 8192)
        self.assertEqual(implicit['policy'], 'first-32-outstanding-canonical-blocks-v1')

    def test_partial_last_block_and_empty_completion_are_exact(self):
        full = population(600)
        last = next_window(full, [0, 1], population_plan_sha256=digest(full), maximum_blocks=1)
        self.assertEqual(last['block_ids'], (2,))
        self.assertEqual(last['expected_ordinal_ranges'], ((512, 600),))
        self.assertEqual(last['expected_model_count'], 88)
        done = next_window(full, [0, 1, 2], population_plan_sha256=digest(full), maximum_blocks=1)
        self.assertFalse(done['launch_required'])
        self.assertIsNone(done['window_id'])

    def test_invalid_or_increased_caps_stop(self):
        full = population(600)
        for value in (0, -1, 33, True, 1., '1', None):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    next_window(full, [], population_plan_sha256=digest(full), maximum_blocks=value)
                with self.assertRaises(ValueError):
                    runner.resource_plan([1, 2, 3, 4, 5], 0, maximum_blocks=value)
        for value in (0, -1, 33, True, 1., '1'):
            with self.subTest(controller_value=value), self.assertRaises(ValueError):
                runner.block_limit(SimpleNamespace(maximum_blocks=value))

    def test_single_block_preserves_existing_execution_limits(self):
        resource = runner.resource_plan([1, 2, 3, 4, 5], 256, maximum_blocks=1)
        self.assertEqual(resource['maximum_blocks'], 1)
        self.assertEqual(resource['maximum_models'], 256)
        self.assertEqual(resource['absolute_seconds'], 900)
        self.assertEqual(resource['persistent_workers'], 4)
        self.assertEqual(resource['candidate_as_bytes'], 1024**3)
        self.assertEqual(resource['candidate_peak_rss_bytes'], 768*1024**2)
        self.assertEqual(resource['seconds_per_model'], 30)
        self.assertEqual(resource['maximum_passes_per_model'], 12)
        self.assertEqual(resource['maximum_candidate_passes'], 3072)
        self.assertEqual(resource['maximum_logical_stages'], 1280)
        self.assertEqual(resource['evidence_charge_bytes'], 512*1024**2)
        self.assertEqual(runtime.BATCH_REPLAY.group_rss_bytes, 20*1024**3)
        with self.assertRaises(ValueError):
            runner.resource_plan([1, 2, 3, 4, 5], 257, maximum_blocks=1)


class SingleBlockCommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def arguments(self, limit=None, bootstrap=False):
        args = runner_fixtures.RunnerPolicyTests.arguments(self)
        args.maximum_blocks = limit
        if bootstrap:
            for key in runner.SEED_FIELDS:
                setattr(args, key, None)
            args.bootstrap = self.root/'bootstrap.json'
            args.bootstrap_sha = 'b'*64
        return args

    def request(self, args):
        return dict(command=runner.worker_command(args, 1000.), deadline_monotonic=1000.,
            worker_cpus=args.worker_cpus, context=dict(plan_sha256=args.replay_plan_sha,
            source_sha256=args.source_sha, input_sha256=plan.digest(runner.input_context(args)),
            profile_name=runtime.BATCH_REPLAY.name))

    def test_absent_flag_keeps_legacy_command_and_context(self):
        args = self.arguments()
        self.assertNotIn('maximum_blocks', runner.input_context(args))
        self.assertNotIn('--maximum-blocks', runner.worker_command(args, 1000.))
        values = receipts._command(self.request(args), 'suffix_window')
        self.assertNotIn('maximum_blocks', values)
        self.assertEqual(runner.block_limit(args), 32)

    def test_one_block_binds_controller_worker_and_cold_request(self):
        args = self.arguments(1, bootstrap=True)
        self.assertEqual(runner.admission_mode(args), 'bootstrap')
        request = self.request(args)
        parsed = runner.parser().parse_args(request['command'][4:])
        self.assertEqual(runner.block_limit(parsed), 1)
        self.assertEqual(runner.input_context(parsed), runner.input_context(args))
        values = receipts._command(request, 'suffix_window')
        self.assertEqual(values['maximum_blocks'], 1)
        self.assertEqual({k:v for k,v in values.items() if k != 'deadline'}, runner.input_context(args))

    def test_duplicate_removed_or_changed_limit_cannot_admit(self):
        request = self.request(self.arguments(1, bootstrap=True))
        duplicate = deepcopy(request)
        duplicate['command'] += ['--maximum-blocks', '1']
        removed = deepcopy(request)
        pos = removed['command'].index('--maximum-blocks')
        del removed['command'][pos:pos+2]
        changed = deepcopy(request)
        changed['command'][changed['command'].index('--maximum-blocks')+1] = '2'
        for broken in (duplicate, removed, changed):
            with self.assertRaises(ValueError):
                receipts._command(broken, 'suffix_window')

    def test_noncanonical_or_outside_ceiling_request_is_rejected(self):
        request = self.request(self.arguments(1, bootstrap=True))
        for raw in ('0', '-1', '33', 'True', '1.0', '01', '+1', '1e0'):
            broken = deepcopy(request)
            broken['command'][broken['command'].index('--maximum-blocks')+1] = raw
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                receipts._command(broken, 'suffix_window')

    def test_recovery_cli_does_not_gain_bootstrap_or_smaller_window_options(self):
        from experiments.time_cut_v2.recorded_real import suffix_window_recovery as recovery
        options = {option for action in recovery.parser()._actions for option in action.option_strings}
        self.assertNotIn('--maximum-blocks', options)
        self.assertNotIn('--bootstrap', options)

    def test_recovery_rejects_new_executor_mapping_policy(self):
        from experiments.time_cut_v2.recorded_real import suffix_window_recovery as recovery
        from experiments.time_cut_v2.recorded_real import bootstrap_executor
        args = self.arguments()
        value = dict(schema=bootstrap_executor.POLICY_V2,
            reviewed_sources={args.source_commit:args.source_sha, 'c'*40:'c'*64},
            bootstrap_executor_bindings=[dict(schema=bootstrap_executor.BINDING_SCHEMA,
                bootstrap_sha256='b'*64, bootstrap_source_commit='c'*40,
                bootstrap_source_sha256='c'*64, executor_source_commit=args.source_commit,
                executor_source_sha256=args.source_sha, population_sha256='d'*64,
                block_plan_sha256='e'*64, variant_id='C01::HIER::D-off')])
        args.source_policy.write_bytes(plan.canonical(value)+b'\n')
        args.source_policy_sha = plan.pin(args.source_policy)['sha256']
        with self.assertRaisesRegex(ValueError, 'existing version-one'):
            recovery.source_policy(args)


if __name__ == '__main__':
    unittest.main()
