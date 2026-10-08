"""Genuine tiny D0 mathematics; explicitly mocked execution envelopes only.

No fixture claims a real C01 capture, successful guarded execution, numerical
certificate, or production population. Physical C01 admission stays separate
from the tiny mathematical oracle used here.
"""
from contextlib import contextmanager, redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import sys
import resource
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from experiments.time_cut_v2.recorded_real import domain, plan as binding
from experiments.time_cut_v2.recorded_real import indexed_population as indexed
from experiments.time_cut_v2.recorded_real import population_bootstrap as bootstrap
from experiments.time_cut_v2.recorded_real import model_preview, replay_plan, suffix_census
from experiments.time_cut_v2.recorded_real import suffix_window, window_receipts as receipts
from experiments.time_cut_v2.recorded_real import final_collector, variant_scope
from experiments.time_cut_v2.recorded_real import bootstrap_executor
from experiments.time_cut_v2.recorded_real.logical_models import count_logical_models
from tests import test_c01_variant_scope as variant_fixtures
from tests.test_recovered_real_coalesced import capture
from tests.test_recovered_real_family import prepare
from tests import test_suffix_window_runner as runner_fixtures
from validation.real5_v2.shared_replay_cached import verify_coalesced_trace
from validation.family5.checker import _plain
from validation.capture5.containers import stream_digest


def tiny_population():
    row = json.loads((binding.ROOT/'results/milestone_5_real_leg_contract/mock_solver_cases.json').read_text())[0]
    data = capture(row, False)
    trusted = prepare(row)
    checked = verify_coalesced_trace(data['trace'], data['bundle'], trusted)
    summary = _plain(checked.summary)
    index = dict(schema='hiroute-recorded-query-index-v1', real_input=trusted.source_snapshot(),
        **{k: summary[k] for k in ('bundle_sha256', 'trace_sha256', 'query_freeze_sha256', 'case_sha256')},
        derived_fields=sorted(domain.DERIVED), exact_queries=len(checked.queries),
        empty_action_queries=len(checked.empty_action_queries), empty_action_sha256=stream_digest(checked.empty_action_queries),
        queries=[_plain(q) for q in domain.thin_queries(checked, lambda: None)])
    logical = count_logical_models(index, trusted, summary)['logical_model_plan']
    # A unit-level protocol boundary, not actual cold-execution authority.
    anchors = dict(variant_id=variant_scope.D0, dominance=False,
                   representation=variant_scope.REPRESENTATION)
    admitted = indexed.AdmittedSuffixPopulation(checked.bundle, trusted, index, logical, anchors, _token=indexed._ADMISSION)
    return index, trusted, summary, logical, anchors, admitted


class D0MathematicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tiny_population()

    def test_independent_count_catalogue_matches_genuine_checked_bundle(self):
        index, trusted, _, logical, anchors, admitted = self.fixture
        # Neither descriptors nor matrices are needed for bootstrap counting.
        with patch('validation.suffix5.independent_convex_model.build_models', side_effect=RuntimeError('no matrices')):
            catalogue, commitment = bootstrap.population_from_count(index, trusted, logical, anchors)
        self.assertEqual(catalogue, admitted.population.plan())
        self.assertEqual(commitment, admitted.commitment())
        self.assertTrue(variant_scope.is_d0_population(commitment))
        self.assertNotEqual(commitment['unique_logical_models'], 695712)
        self.assertGreater(commitment['queries'], 0)
        self.assertGreater(commitment['empty_action_queries'], 0)
        self.assertEqual(commitment['queries']+commitment['empty_action_queries'],
                         self.fixture[2]['exact_node_queries']+self.fixture[2]['empty_action_queries'])

    def test_changed_language_totals_or_physical_sources_reject(self):
        index, trusted, _, logical, anchors, _ = self.fixture
        for field, value in [('unique_logical_model_slots', logical['unique_logical_model_slots']+1),
                             ('unique_families', True), ('source_bundle_sha256', '0'*64)]:
            bad = deepcopy(logical); bad[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                bootstrap.population_from_count(index, trusted, bad, anchors)
        for field, value in [('case_sha256', '0'*64), ('exact_queries', True)]:
            bad = deepcopy(index); bad[field] = value
            with self.assertRaises(ValueError): bootstrap.population_from_count(bad, trusted, logical, anchors)

    def test_independent_window_uses_own_counts_and_empty_registry(self):
        admitted = self.fixture[-1]
        scope = receipts.ReceiptScope(admitted.population.plan(), admitted.commitment(), _token=receipts._ADMISSION)
        registry = receipts.make_registry(scope, [])
        window = suffix_window.plan_window(scope, registry)
        self.assertEqual(window['expected_model_count'], admitted.commitment()['unique_logical_models'])
        self.assertEqual(registry.metadata()['completed_models'], 0)
        self.assertEqual(registry.metadata()['entries'], [])
        self.assertEqual(window['operation_budget']['maximum_models'], 8192)
        self.assertEqual(window['operation_budget']['absolute_seconds'], 900)
        with self.assertRaisesRegex(ValueError, 'full canonical block coverage'):
            final_collector.require_complete_registry(scope, registry)

    def test_foreign_registry_identity_and_d1_small_population_reject(self):
        admitted = self.fixture[-1]
        scope = receipts.ReceiptScope(admitted.population.plan(), admitted.commitment(), _token=receipts._ADMISSION)
        registry = receipts.make_registry(scope, [])
        legacy = deepcopy(admitted.commitment())
        for key in ('variant_id', 'dominance', 'representation', 'population_freeze_sha256'):
            legacy.pop(key)
        legacy['completed_replay'] = {}
        other = receipts.ReceiptScope(scope.plan(), legacy, _token=receipts._ADMISSION)
        with self.assertRaises(ValueError): suffix_window.plan_window(other, registry)
        # Same numerical totals do not allow distinct D0 query freezes to mix.
        foreign = deepcopy(scope.commitment()); foreign['query_freeze_sha256'] = '0'*64
        foreign['population_freeze_sha256'] = binding.digest({k:v for k,v in foreign.items() if k!='population_freeze_sha256'})
        other = receipts.ReceiptScope(scope.plan(), foreign, _token=receipts._ADMISSION)
        with self.assertRaises(ValueError): suffix_window.plan_window(other, registry)

    def test_cooperative_deadline_failure_stops_count(self):
        def expired(): raise ValueError('expired')
        with self.assertRaisesRegex(ValueError, 'expired'):
            bootstrap.catalogue_from_count(self.fixture[1], self.fixture[3], expired)


class BootstrapProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tiny_population()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.args = SimpleNamespace(**{k: self.root/k for k in receipts.COMMON_PATHS},
                                   **{k: 'a'*(40 if k=='source_commit' else 64) for k in receipts.COMMON_PINS})
        self.physical = variant_fixtures.VariantScopeTests().physical(True)
        self.physical['source_commit'] = self.args.source_commit
        self.policy = {self.args.source_commit: self.args.source_sha}
        self.returned = {}
        self.requests = {}
        for prefix, module in [('replay', 'parallel_replay'), ('logical', 'suffix_census')]:
            path = getattr(self.args, prefix+'_attempt'); path.mkdir()
            value = dict(command=[sys.executable, '-B', '-m', receipts.MODULE_PREFIX+module, '--worker',
                                  '--deadline', '280.0'], entry_monotonic=100.0, deadline_monotonic=280.0)
            self.requests[prefix] = value
            self.write(path/'request.json', value)
            returned = dict(status='completed', protocol_fake_not_execution_authority=True, prefix=prefix)
            self.returned[prefix] = returned
            returned.update(entry_monotonic=100.0, deadline_monotonic=280.0)
            sha = self.write(getattr(self.args, prefix+'_return'), returned)
            setattr(self.args, prefix+'_return_sha', sha)
        report = self.args.logical_attempt/'evidence/suffix-census.json'
        report.parent.mkdir()
        self.args.logical_report_sha = self.write(report, dict(census_source_commit=self.args.source_commit))

    def write(self, path, value):
        raw = binding.canonical(value)+b'\n'; path.write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()

    @contextmanager
    def execution_boundary(self, *, fail=False):
        index, trusted, summary, logical, anchors, _ = self.fixture
        def fake_phase(path, *, successful_return, **kwargs):
            prefix = 'replay' if Path(path)==self.args.replay_attempt else 'logical'
            self.assertEqual(successful_return, self.returned[prefix])
            return dict(successful_return, status='failed' if fail else 'completed',
                        request_sha256=binding.pin(Path(path)/'request.json')['sha256'])
        with patch.object(replay_plan, 'historical_plan', return_value=self.physical), \
             patch.object(suffix_census, 'completed_inputs', return_value=(index, trusted, dict(checked=summary), anchors)), \
             patch.object(model_preview, 'logical_input', return_value=logical), \
             patch.object(receipts, 'read_phase_result', side_effect=fake_phase) as phase, \
             patch.object(receipts, '_inputs') as closure:
            yield phase, closure

    def authenticate(self):
        return bootstrap.authenticate_inputs(self.args, self.policy, time.monotonic()+20)

    def test_both_actual_return_objects_worker_modules_and_closure_are_required(self):
        with self.execution_boundary() as (phase, closure):
            result = self.authenticate()
        self.assertEqual(phase.call_count, 2)
        self.assertEqual(closure.call_count, 1)
        self.assertEqual(result['population'], self.fixture[-1].commitment())
        self.assertFalse(result['numerical_acceptance'])

    def test_completed_count_with_181_to_1800_second_budget_is_rejected_before_count_decode(self):
        for seconds in (181.0, 900.0, 1800.0):
            request = self.requests['logical']; request['deadline_monotonic'] = 100.0+seconds
            request['command'][-1] = repr(request['deadline_monotonic'])
            self.returned['logical']['deadline_monotonic'] = request['deadline_monotonic']
            self.write(self.args.logical_attempt/'request.json', request)
            self.args.logical_return_sha = self.write(self.args.logical_return, self.returned['logical'])
            with self.subTest(seconds=seconds), self.execution_boundary(), \
                 patch.object(model_preview, 'logical_input') as count, \
                 self.assertRaisesRegex(ValueError, '180-second budget'):
                self.authenticate()
            count.assert_not_called()

    def test_actual_request_entry_and_deadline_must_match_successful_return(self):
        for field in ('entry_monotonic', 'deadline_monotonic'):
            request = deepcopy(self.requests['logical']); request[field] += 1.0
            self.write(self.args.logical_attempt/'request.json', request)
            with self.subTest(field=field), self.execution_boundary(), \
                 self.assertRaisesRegex(ValueError, 'request/return time binding'):
                self.authenticate()

    def test_worker_deadline_missing_changed_duplicate_attached_or_abbreviated_rejects(self):
        original = self.requests['logical']['command']
        commands = [original[:-2], original[:-1], original[:-1]+['281.0'],
                    original+['--deadline','281.0'], original+['--deadline=281.0'],
                    original+['--d','281.0'], original[:-2]+['--deadline=280.0'],
                    original[:-1]+['nan'], original[:-1]+['invalid']]
        for command in commands:
            request = deepcopy(self.requests['logical']); request['command'] = command
            self.write(self.args.logical_attempt/'request.json', request)
            with self.subTest(command=command), self.execution_boundary(), self.assertRaises(ValueError):
                self.authenticate()

    def test_exact_180_and_shorter_count_budgets_are_accepted_as_protocol_metadata(self):
        for seconds in (0.5, 179.0, 180.0):
            request = deepcopy(self.requests['logical']); request['deadline_monotonic'] = 100.0+seconds
            request['command'][-1] = repr(request['deadline_monotonic'])
            accepted = dict(entry_monotonic=request['entry_monotonic'],deadline_monotonic=request['deadline_monotonic'])
            bootstrap.check_count_budget(request, accepted)

    def test_nonfinite_boolean_time_alias_and_nonpositive_budget_reject(self):
        for field, value in [('entry_monotonic', True), ('deadline_monotonic', 280),
                             ('deadline_monotonic', float('inf')), ('entry_monotonic', float('nan')),
                             ('deadline_monotonic', 100.0), ('deadline_monotonic', 99.0)]:
            request = deepcopy(self.requests['logical']); request[field] = value
            accepted = {key: request[key] for key in ('entry_monotonic','deadline_monotonic')}
            with self.subTest(field=field,value=value), self.assertRaises(ValueError):
                bootstrap.check_count_budget(request, accepted)

    def test_missing_changed_or_failed_upstream_return_rejects(self):
        with self.execution_boundary(fail=True), self.assertRaises(ValueError): self.authenticate()
        self.args.replay_return.write_bytes(b'{}\n')
        with self.execution_boundary(), self.assertRaises(ValueError): self.authenticate()
        self.args.replay_return.unlink()
        with self.execution_boundary(), self.assertRaises((ValueError, OSError)): self.authenticate()

    def test_unreviewed_checkpoint_d1_and_forged_worker_reject(self):
        with self.execution_boundary():
            for bad in ({}, {self.args.source_commit: 'b'*64}):
                with self.assertRaises(ValueError):
                    bootstrap.authenticate_inputs(self.args, bad, time.monotonic()+20)
            self.args.logical_source_sha = 'b'*64
            with self.assertRaises(ValueError): self.authenticate()
            self.args.logical_source_sha = self.args.source_sha
            self.physical.update(schema=variant_scope.D1_PLAN_SCHEMA, dominance=True)
            self.physical.pop('variant_id')
            with self.assertRaisesRegex(ValueError, 'D0-only'): self.authenticate()
        self.physical = variant_fixtures.VariantScopeTests().physical(True); self.physical['source_commit'] = self.args.source_commit
        self.requests['replay']['command'][3] = receipts.MODULE_PREFIX+'model_preview'
        self.write(self.args.replay_attempt/'request.json', self.requests['replay'])
        with self.execution_boundary(), self.assertRaisesRegex(ValueError, 'worker required'): self.authenticate()

    def test_repaired_outer_hash_cannot_change_counts_catalogue_or_identity(self):
        with self.execution_boundary(): expected = self.authenticate()
        self.args.bootstrap = self.root/'bootstrap.json'
        for mutation in ('count', 'catalogue', 'identity', 'extra'):
            value = deepcopy(expected)
            if mutation=='count': value['population']['queries'] += 1
            elif mutation=='catalogue': value['catalogue']['blocks'][0]['end'] += 1
            elif mutation=='identity': value['population']['dominance'] = True
            else: value['execution_accepted'] = True
            self.args.bootstrap_sha = self.write(self.args.bootstrap, value)
            with patch.object(bootstrap, 'authenticate_inputs', return_value=expected), \
                 self.assertRaisesRegex(ValueError, 'authenticated replay/count population'):
                bootstrap.admit_bootstrap(self.args, self.policy, deadline=time.monotonic()+20)

    def test_exact_bootstrap_mints_only_empty_scheduling_registry_and_compares_fresh_population(self):
        with self.execution_boundary(): expected = self.authenticate()
        self.args.bootstrap = self.root/'bootstrap.json'; self.args.bootstrap_sha = self.write(self.args.bootstrap, expected)
        with patch.object(bootstrap, 'authenticate_inputs', return_value=expected):
            scope, registry = bootstrap.admit_bootstrap(self.args, self.policy, deadline=time.monotonic()+20,
                                                      admitted=self.fixture[-1])
        self.assertIs(type(scope), receipts.ReceiptScope)
        self.assertIs(type(registry), receipts.CheckedRegistry)
        self.assertEqual(registry.completed_block_ids(), ())
        self.assertFalse(registry.metadata()['fresh_numerical_replay'])
        with patch.object(bootstrap, 'authenticate_inputs', return_value=expected), self.assertRaises(ValueError):
            bootstrap.admit_bootstrap(self.args, self.policy, deadline=time.monotonic()+20,
                admitted=SimpleNamespace(population=SimpleNamespace(plan=lambda: {}), commitment=lambda: {}))

    def test_unmocked_runtime_reader_rejects_protocol_fake_return(self):
        # The synthetic envelope above is never accepted by real cold admission.
        with self.assertRaises((ValueError, OSError, KeyError)):
            model_preview.logical_input(self.args, self.fixture[4], self.fixture[0], self.fixture[1],
                                        dict(checked=self.fixture[2]), time.monotonic()+20, lambda: None)

    def executor_transition(self):
        # Actual execution is mocked exactly as in the existing protocol tests.
        # The independently checked tiny population remains genuine mathematics.
        with self.execution_boundary():
            expected = self.authenticate()
        self.args.bootstrap = self.root/'bootstrap.json'
        self.args.bootstrap_sha = self.write(self.args.bootstrap, expected)
        original_commit, original_sha = self.args.source_commit, self.args.source_sha
        self.args.source_commit, self.args.source_sha = 'e'*40, 'd'*64
        self.policy = {original_commit: original_sha, self.args.source_commit: self.args.source_sha}
        self.args.source_policy = self.root/'executor-policy.json'
        row = dict(schema=bootstrap_executor.BINDING_SCHEMA, bootstrap_sha256=self.args.bootstrap_sha,
            bootstrap_source_commit=original_commit, bootstrap_source_sha256=original_sha,
            executor_source_commit=self.args.source_commit, executor_source_sha256=self.args.source_sha,
            population_sha256=binding.digest(expected['population']),
            block_plan_sha256=expected['population']['block_plan_sha256'], variant_id=variant_scope.D0)
        policy = dict(schema=bootstrap_executor.POLICY_V2, reviewed_sources=self.policy,
                      bootstrap_executor_bindings=[row])
        self.args.source_policy_sha = self.write(self.args.source_policy, policy)
        return expected, policy

    def admit_transition(self):
        return bootstrap.admit_bootstrap(self.args, self.policy, deadline=time.monotonic()+20)

    def test_reviewed_executor_transition_authenticates_original_checkpoint_and_preserves_population(self):
        expected, _ = self.executor_transition()
        with self.execution_boundary() as (phase, closure), \
             patch.object(bootstrap, 'authenticate_inputs', wraps=bootstrap.authenticate_inputs) as authenticate:
            scope, registry = self.admit_transition()
        self.assertEqual(phase.call_count, 2)
        self.assertEqual(closure.call_count, 1)
        self.assertEqual(authenticate.call_args.args[0].source_commit, expected['source_commit'])
        self.assertEqual(self.args.source_commit, 'e'*40)
        self.assertEqual(scope.plan(), expected['catalogue'])
        self.assertEqual(scope.commitment(), expected['population'])
        self.assertEqual(registry.completed_block_ids(), ())
        self.assertFalse(registry.metadata()['fresh_numerical_replay'])
        self.assertEqual(binding.pin(self.args.bootstrap)['sha256'], self.args.bootstrap_sha)

    def test_new_executor_allowlist_alone_or_missing_policy_cannot_admit(self):
        _, policy = self.executor_transition()
        old = dict(schema=bootstrap_executor.POLICY_V1, reviewed_sources=self.policy)
        self.args.source_policy_sha = self.write(self.args.source_policy, old)
        with self.execution_boundary(), self.assertRaisesRegex(ValueError, 'version-two'):
            self.admit_transition()
        self.args.source_policy.unlink()
        with self.execution_boundary(), self.assertRaises((ValueError, OSError)):
            self.admit_transition()
        policy['bootstrap_executor_bindings'] = []
        self.args.source_policy_sha = self.write(self.args.source_policy, policy)
        with self.execution_boundary(), self.assertRaises(ValueError):
            self.admit_transition()

    def test_repaired_policy_hash_cannot_change_mapping_source_variant_or_population(self):
        _, policy = self.executor_transition()
        mutations = [('bootstrap_sha256', '0'*64), ('bootstrap_source_commit', '0'*40),
            ('bootstrap_source_sha256', '0'*64), ('executor_source_commit', '0'*40),
            ('executor_source_sha256', '0'*64), ('population_sha256', '0'*64),
            ('block_plan_sha256', '0'*64), ('variant_id', 'C01::HIER::D-on'),
            ('schema', 'unreviewed-binding'), ('allow_any_executor', True)]
        for key, value in mutations:
            bad = deepcopy(policy); bad['bootstrap_executor_bindings'][0][key] = value
            self.args.source_policy_sha = self.write(self.args.source_policy, bad)
            with self.subTest(key=key), self.execution_boundary() as (phase, _), self.assertRaises(ValueError):
                self.admit_transition()
            # A repaired policy never substitutes for historical cold admission.
            self.assertEqual(phase.call_count, 2)

    def test_duplicate_ambiguous_or_unreviewed_policy_sources_reject(self):
        _, policy = self.executor_transition()
        duplicate = deepcopy(policy)
        duplicate['bootstrap_executor_bindings'].append(deepcopy(duplicate['bootstrap_executor_bindings'][0]))
        extra = deepcopy(policy); extra['reviewed_sources']['f'*40] = 'f'*64
        for bad in (duplicate, extra):
            self.args.source_policy_sha = self.write(self.args.source_policy, bad)
            with self.execution_boundary(), self.assertRaises(ValueError): self.admit_transition()

    def test_repaired_bootstrap_and_policy_hashes_cannot_change_original_population(self):
        expected, policy = self.executor_transition()
        for mutation in ('population', 'catalogue', 'history_source', 'inputs', 'variant'):
            bad = deepcopy(expected)
            if mutation == 'population':
                bad['population']['queries'] += 1
                freeze = {k:v for k,v in bad['population'].items() if k != 'population_freeze_sha256'}
                bad['population']['population_freeze_sha256'] = binding.digest(freeze)
            elif mutation == 'catalogue': bad['catalogue']['blocks'][0]['end'] += 1
            elif mutation == 'history_source': bad['source_commit'] = self.args.source_commit
            elif mutation == 'inputs': bad['inputs']['logical_return_sha'] = '0'*64
            else: bad['population']['dominance'] = True
            self.args.bootstrap_sha = self.write(self.args.bootstrap, bad)
            updated = deepcopy(policy); row = updated['bootstrap_executor_bindings'][0]
            row['bootstrap_sha256'] = self.args.bootstrap_sha
            row['population_sha256'] = binding.digest(bad['population'])
            self.args.source_policy_sha = self.write(self.args.source_policy, updated)
            with self.subTest(mutation=mutation), self.execution_boundary(), self.assertRaises(ValueError):
                self.admit_transition()

    def test_executor_policy_shape_and_binding_count_are_strict(self):
        _, policy = self.executor_transition()
        invalid = []
        for rows in (None, {}, (), [], [deepcopy(policy['bootstrap_executor_bindings'][0])]*17):
            bad = deepcopy(policy); bad['bootstrap_executor_bindings'] = rows
            invalid.append(bad)
        for field, value in (('schema', 'allow-any-source'), ('reviewed_sources', []),
                             ('allow_any_executor', True)):
            bad = deepcopy(policy); bad[field] = value
            invalid.append(bad)
        bad = deepcopy(policy)
        bad['bootstrap_executor_bindings'][0]['executor_source_sha256'] = True
        invalid.append(bad)
        for bad in invalid:
            with self.subTest(policy=bad), self.assertRaises(ValueError):
                bootstrap_executor.policy_sources(bad)

    def test_executor_policy_pin_requires_exact_canonical_bytes(self):
        _, policy = self.executor_transition()
        for payload in (binding.canonical(policy), binding.canonical(policy)+b'\n\n',
                        json.dumps(policy, indent=2).encode()+b'\n'):
            with self.subTest(payload=payload[:40]), self.assertRaisesRegex(ValueError, 'canonical JSON'):
                bootstrap_executor.validate_pinned_policy(policy, hashlib.sha256(payload).hexdigest())

    def test_changed_caller_input_or_unreviewed_executor_rejects(self):
        self.executor_transition()
        original = self.args.query_index_sha
        self.args.query_index_sha = '0'*64
        with self.execution_boundary(), self.assertRaises(ValueError): self.admit_transition()
        self.args.query_index_sha = original
        self.args.source_sha = '0'*64
        with self.execution_boundary(), self.assertRaisesRegex(ValueError, 'executor outside'):
            self.admit_transition()

    def test_d1_seed_worker_or_d1_physical_plan_cannot_enter_executor_transition(self):
        self.executor_transition()
        self.requests['replay']['command'][3] = receipts.MODULE_PREFIX+'block_resume'
        self.write(self.args.replay_attempt/'request.json', self.requests['replay'])
        with self.execution_boundary(), self.assertRaisesRegex(ValueError, 'worker required'):
            self.admit_transition()
        self.requests['replay']['command'][3] = receipts.MODULE_PREFIX+'parallel_replay'
        self.write(self.args.replay_attempt/'request.json', self.requests['replay'])
        self.physical.update(schema=variant_scope.D1_PLAN_SCHEMA, dominance=True)
        self.physical.pop('variant_id')
        with self.execution_boundary(), self.assertRaisesRegex(ValueError, 'D0-only'):
            self.admit_transition()

    def test_mapping_never_hides_changed_actual_count_deadline_or_return(self):
        self.executor_transition()
        request = self.requests['logical']; request['deadline_monotonic'] = 281.0
        request['command'][-1] = '281.0'
        self.returned['logical']['deadline_monotonic'] = 281.0
        self.write(self.args.logical_attempt/'request.json', request)
        self.args.logical_return_sha = self.write(self.args.logical_return, self.returned['logical'])
        with self.execution_boundary(), self.assertRaisesRegex(ValueError, '180-second budget'):
            self.admit_transition()

    @contextmanager
    def preparation_boundary(self, limits):
        # Only CLI orchestration is injected; no successful phase is claimed.
        self.args.output = self.root/'prepared.json'
        with patch('argparse.ArgumentParser.parse_args', return_value=self.args), \
             patch.object(resource, 'getrlimit', return_value=limits), \
             patch.object(resource, 'setrlimit') as memory, \
             patch.object(sys, 'meta_path', list(sys.meta_path)), \
             patch.object(suffix_census, 'check_sources') as source, \
             patch.object(suffix_window, 'source_policy', return_value=self.policy), \
             patch.object(bootstrap, 'authenticate_inputs', return_value=dict(protocol_fake_not_execution_authority=True)), \
             redirect_stdout(io.StringIO()):
            yield memory, source

    def test_preparation_cannot_raise_inherited_memory_limits(self):
        for limits, expected in (((resource.RLIM_INFINITY, resource.RLIM_INFINITY), 2*1024**3),
                                  ((512*1024**2, resource.RLIM_INFINITY), 512*1024**2),
                                  ((512*1024**2, 1024**3), 512*1024**2)):
            with self.subTest(limits=limits), self.preparation_boundary(limits) as (memory, _):
                bootstrap.main()
                memory.assert_called_once_with(resource.RLIMIT_AS, (expected, limits[1]))
            self.args.output.unlink()

    def test_source_change_before_publication_stops_without_final_bootstrap(self):
        with self.preparation_boundary((resource.RLIM_INFINITY, resource.RLIM_INFINITY)) as (_, source):
            source.side_effect = [None, ValueError('owner source changed')]
            with self.assertRaisesRegex(ValueError, 'owner source changed'): bootstrap.main()
        self.assertFalse(self.args.output.exists())
        self.assertTrue(self.args.output.with_name(self.args.output.name+'.partial').exists())


class D0CommandTests(unittest.TestCase):
    def setUp(self):
        self.fx = runner_fixtures.RunnerPolicyTests(); self.fx.setUp(); self.addCleanup(self.fx.doCleanups)
        self.args = self.fx.arguments()
        for key in suffix_window.SEED_FIELDS+suffix_window.REGISTRY_FIELDS: setattr(self.args, key, None)
        self.args.bootstrap = self.fx.root/'bootstrap.json'; self.args.bootstrap_sha = 'b'*64

    def test_bootstrap_options_bind_exact_worker_and_cold_receipt_context(self):
        args = self.args
        self.assertEqual(suffix_window.admission_mode(args), 'bootstrap')
        context = suffix_window.input_context(args)
        request = dict(command=suffix_window.worker_command(args, 1000.), deadline_monotonic=1000.,
            worker_cpus=args.worker_cpus, context=dict(plan_sha256=args.replay_plan_sha,
            source_sha256=args.source_sha, input_sha256=binding.digest(context), profile_name=suffix_window.BATCH_REPLAY.name))
        values = receipts._command(request, 'suffix_window')
        self.assertEqual({k:v for k,v in values.items() if k!='deadline'}, context)
        self.assertEqual(suffix_window.registry_admission(args)['kind'], 'd0-replay-count-bootstrap-v1')
        broken = deepcopy(request); broken['command'].pop(broken['command'].index('--bootstrap-sha')+1)
        broken['command'].remove('--bootstrap-sha')
        with self.assertRaises(ValueError): receipts._command(broken, 'suffix_window')

    def test_partial_bootstrap_mixed_seed_and_d0_using_d1_seed_reject(self):
        args = self.args; args.bootstrap_sha = None
        with self.assertRaises(ValueError): suffix_window.admission_mode(args)
        args.bootstrap_sha = 'b'*64; args.old_archive = self.fx.root/'old'
        with self.assertRaises(ValueError): suffix_window.admission_mode(args)
        args = self.fx.arguments()
        args.historical_plan_sha = self.write_plan(args.historical_plan, True)
        with self.assertRaisesRegex(ValueError, 'historical D1 seed'):
            suffix_window.load_registry(args, {}, deadline=time.monotonic()+20, before=lambda: None)

    def write_plan(self, path, d0):
        raw = binding.canonical(variant_fixtures.VariantScopeTests().physical(d0))+b'\n'; path.write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()

    def test_only_explicit_d0_can_omit_d1_seed_source(self):
        args = self.args
        self.fx.policy(args, {args.source_commit: args.source_sha})
        args.historical_plan_sha = self.write_plan(args.historical_plan, True)
        self.assertEqual(suffix_window.source_policy(args), {args.source_commit: args.source_sha})
        args.historical_plan_sha = self.write_plan(args.historical_plan, False)
        with self.assertRaisesRegex(ValueError, 'seed source'): suffix_window.source_policy(args)


if __name__ == '__main__':
    unittest.main()
