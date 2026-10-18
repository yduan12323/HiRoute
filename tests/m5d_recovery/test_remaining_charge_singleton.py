"""Explicit FLAT bound-family adapter: unit and tiny native checks only."""
from fractions import Fraction as F
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from experiments.remaining_charge_gate_v1.singleton import (
    POLICY_SCHEMA, RemainingChargeSingletonBound)
from experiments.remaining_charge_gate_v1.run import RemainingChargeRegionBound
from timecut5.remaining_charge_runtime import (RemainingChargeBoundResultV1 as Result,
                                               admit_remaining_charge_runtime)
from timecut5.bounded import Problem, _solve_problem, _replay_problem
from timecut5.hierarchy import _solve_hierarchical_problem, build_regions

# Explicit sibling fixtures for standalone installed-wheel invocation. Never
# add src/: production imports above must continue to resolve from the wheel.
_FIXTURE_ROOT = str(Path(__file__).resolve().parents[1])
if _FIXTURE_ROOT not in sys.path:
    sys.path.append(_FIXTURE_ROOT)
from terminal_energy import test_dyadic_time_alt as native_fixture
from terminal_energy import test_energy as graph_fixture


def wrapper(lower=F(3), prefix=F(4), whole=F(5)):
    problem = SimpleNamespace(bound=3)
    original = Mock()
    original.singleton_bound.return_value = lower
    runtime = Mock(binding_sha256='a'*64)
    runtime.evaluate_group.return_value = Result('active', prefix, 'a'*64)
    runtime.whole_route_lower_bound.return_value = Result('active', whole, 'a'*64)
    bound = RemainingChargeSingletonBound(original, problem, runtime=runtime)
    pieces = (SimpleNamespace(state=SimpleNamespace(stop_count=1)),)
    return bound, problem, pieces


class RemainingChargeSingletonTests(unittest.TestCase):
    def test_explicit_exact_max_next_stop_and_no_implicit_forwarding(self):
        bound, problem, pieces = wrapper()
        self.assertEqual(bound.singleton_bound(problem, pieces, 's', 'CS'), F(5))
        bound.original.singleton_bound.assert_called_once_with(problem, pieces, 's', 'CS')
        bound.runtime.evaluate_group.assert_called_once_with(pieces)
        bound.runtime.whole_route_lower_bound.assert_called_once_with(2)
        self.assertFalse(hasattr(bound, 'bound'))
        self.assertFalse(hasattr(bound, 'action_mask'))
        self.assertEqual(problem.bound, 3)
        self.assertFalse(F(5) > F(5))  # caller must retain primary equality

    def test_none_off_and_empty_original_none_preserve_order(self):
        bound, problem, pieces = wrapper(lower=None)
        self.assertIsNone(bound.singleton_bound(problem, (), 's', 'S'))
        bound.runtime.evaluate_group.assert_not_called()
        bound.runtime.whole_route_lower_bound.assert_not_called()
        self.assertEqual(bound.statistics_snapshot()['original_none'], 1)
        bound, problem, pieces = wrapper()
        bound.runtime = None
        self.assertIs(bound.singleton_bound(problem, pieces, 's', 'C'),
                      bound.original.singleton_bound.return_value)
        self.assertFalse(bound.statistics_snapshot()['runtime_enabled'])

    def test_known_disabled_status_on_either_term_keeps_original(self):
        for status in ('disabled_unsupported', 'inactive_no_charging_curve'):
            for term in ('evaluate_group', 'whole_route_lower_bound'):
                with self.subTest(status=status, term=term):
                    bound, problem, pieces = wrapper()
                    getattr(bound.runtime, term).return_value = Result(status, None, 'a'*64)
                    for _ in range(2):
                        self.assertEqual(bound.singleton_bound(problem, pieces, 's', 'C'), F(3))
                    self.assertEqual(bound.runtime.evaluate_group.call_count, 2)
                    self.assertEqual(bound.runtime.whole_route_lower_bound.call_count, 2)
                    self.assertEqual(bound.statistics_snapshot()['disabled_calls'], 2)

    def test_owner_depth_and_runtime_errors_fail_closed(self):
        bound, problem, pieces = wrapper()
        with self.assertRaisesRegex(ValueError, 'owner'):
            bound.singleton_bound(object(), pieces, 's', 'C')
        bound.original.singleton_bound.assert_not_called()
        with self.assertRaisesRegex(ValueError, 'Nonempty'):
            bound.singleton_bound(problem, (), 's', 'C')
        problem.bound = 1
        with self.assertRaisesRegex(ValueError, 'Hmax'):
            bound.singleton_bound(problem, pieces, 's', 'C')
        problem.bound = 3
        bound.runtime.evaluate_group.side_effect = ValueError('native drift')
        with self.assertRaisesRegex(ValueError, 'native drift'):
            bound.singleton_bound(problem, pieces, 's', 'C')

    def test_malformed_result_and_binding_raise_even_if_other_term_disabled(self):
        malformed = [
            SimpleNamespace(status='active', primary_lower_bound=F(4), binding_sha256='b'*64),
            SimpleNamespace(status='active', primary_lower_bound=4, binding_sha256='a'*64),
            SimpleNamespace(status='active', primary_lower_bound=4., binding_sha256='a'*64),
            SimpleNamespace(status='unreachable', primary_lower_bound=None, binding_sha256='a'*64),
            SimpleNamespace(status='disabled_unsupported', primary_lower_bound=F(0), binding_sha256='a'*64),
        ]
        for value in malformed:
            for bad, other in (('evaluate_group', 'whole_route_lower_bound'),
                               ('whole_route_lower_bound', 'evaluate_group')):
                with self.subTest(value=value, bad=bad):
                    bound, problem, pieces = wrapper()
                    getattr(bound.runtime, bad).return_value = value
                    getattr(bound.runtime, other).return_value = Result('disabled_unsupported', None, 'a'*64)
                    with self.assertRaises((ValueError, TypeError)):
                        bound.singleton_bound(problem, pieces, 's', 'C')
        bound, problem, pieces = wrapper(lower=3.)
        with self.assertRaisesRegex(TypeError, 'original'):
            bound.singleton_bound(problem, pieces, 's', 'C')

    def test_detached_constant_field_statistics_and_original_errors(self):
        bound, problem, pieces = wrapper()
        before = bound.statistics_snapshot()
        bound.singleton_bound(problem, pieces, 's', 'C')
        after = bound.statistics_snapshot()
        self.assertEqual(before['calls'], 0)
        self.assertEqual(after, dict(schema=POLICY_SCHEMA, runtime_enabled=True, calls=1,
            original_none=0, active_calls=1, disabled_calls=0, strengthened_calls=1))
        after['calls'] = 999
        self.assertEqual(bound.statistics_snapshot()['calls'], 1)
        bound.original.singleton_bound.side_effect = ValueError('unknown action')
        with self.assertRaisesRegex(ValueError, 'unknown action'):
            bound.singleton_bound(problem, pieces, 'missing', 'C')
        self.assertEqual(bound.statistics_snapshot()['calls'], 2)
        self.assertEqual(bound.statistics_snapshot()['active_calls'], 1)

    def test_open_primary_infimum_preserves_terminal_semantics(self):
        # Synthetic adapter seam: a zero certified relaxation cannot change
        # open charging support or convert its infimum into an attained key.
        case = dict(origin='A', destination='D', start_time_s=0, initial_energy_kwh=2,
            capacity_kwh=10, minimum_energy_kwh=0, reserve_kwh=0, overhead_s=1,
            lambda_stop_s=1, consumption_kwh_per_m=1, H_ref=1, sites={'s':['CS']},
            charging_segments=[[0,10,1,0]], schedule=dict(a=0,b=100,D=0),
            edges=[dict(source='A',target='s',time_s=1,length_m=1),
                   dict(source='s',target='D',time_s=1,length_m=1)])
        p = Problem(case)
        base = _solve_problem(p).result
        original = Mock(); original.singleton_bound.return_value = F(0)
        runtime = Mock(binding_sha256='a'*64)
        runtime.evaluate_group.return_value = runtime.whole_route_lower_bound.return_value = Result('active', F(0), 'a'*64)
        bound = RemainingChargeSingletonBound(original, p, runtime=runtime)
        flat = _solve_problem(p, singleton_bound=bound.singleton_bound).result
        hier = _solve_hierarchical_problem(p, True, build_regions(p.sites)).bounded.result
        for result in (base, flat, hier):
            self.assertEqual(result.status, 'infimum_unattained')
            self.assertEqual(result.primary_infimum, F(4))
            self.assertIsNone(result.key)
            self.assertIsNone(result.witness)


class RemainingChargeSingletonNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        native_fixture.DyadicTimeALTTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        native_fixture.DyadicTimeALTTests.tearDownClass.__func__(cls)

    directory = native_fixture.DyadicTimeALTTests.directory
    context = native_fixture.DyadicTimeALTTests.context
    problem = native_fixture.DyadicTimeALTTests.problem
    landmark_router = native_fixture.DyadicTimeALTTests.landmark_router
    make = native_fixture.DyadicTimeALTTests.make

    def test_q0_q10_full_keys_match_exhaustive_flat_and_hier(self):
        keys = []
        for q in (0, 10):
            with self.subTest(q=q):
                _, p, original, root = self.make(q=q, mode='destination_target')
                runtime = admit_remaining_charge_runtime(p,
                    energy_screen=p._terminal_energy_screen, travel_provider=original)
                bound = RemainingChargeSingletonBound(original, p, runtime=runtime)
                exhaustive = _solve_problem(p).result
                key = exhaustive.key
                flat = _solve_problem(p, verified_primary_upper=key[0],
                                      singleton_bound=bound.singleton_bound).result
                region = RemainingChargeRegionBound(original, p, runtime=runtime)
                hier = _solve_hierarchical_problem(p, True, root,
                    verified_primary_upper=key[0], bound_provider=region).bounded.result
                for result in (exhaustive, flat, hier):
                    self.assertEqual(result.status, 'attained_optimum')
                    self.assertEqual(result.key, key)
                    self.assertEqual(_replay_problem(p, result.witness), key)
                self.assertGreater(bound.statistics_snapshot()['active_calls'], 0)
                self.assertEqual(p.bound, 1)
                keys.append(key)
        self.assertEqual(keys[0], keys[1])

    def test_exact_equality_keeps_extensions_in_actual_flat_engine(self):
        _, p, original, _ = self.make(q=10)
        expected = _solve_problem(p).result
        # The exact known optimum is a valid lower bound in this tiny fixture.
        runtime = Mock(binding_sha256='a'*64)
        runtime.evaluate_group.return_value = runtime.whole_route_lower_bound.return_value = Result('active', expected.key[0], 'a'*64)
        bound = RemainingChargeSingletonBound(original, p, runtime=runtime)
        actual = _solve_problem(p, verified_primary_upper=expected.key[0],
                                singleton_bound=bound.singleton_bound)
        self.assertGreater(actual.attempted_extensions, 0)
        self.assertEqual(actual.result.key, expected.key)

    def test_infinite_alt_labels_are_not_none_and_native_drift_raises(self):
        graph = graph_fixture.graph(4, [(0,3,.5,1.)])
        _, p, original, _ = self.make(q=10, graph=graph)
        runtime = admit_remaining_charge_runtime(p,
            energy_screen=p._terminal_energy_screen, travel_provider=original)
        bound = RemainingChargeSingletonBound(original, p, runtime=runtime)
        pieces = (p.initial_piece(),)
        self.assertIsInstance(bound.singleton_bound(p, pieces, 's', 'C'), F)
        self.assertFalse(p.advance(pieces, 's', 'C'))  # routing decides feasibility
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            bound.singleton_bound(p, pieces, 'missing', 'C')
        p.rate += 1
        with self.assertRaises(ValueError):
            bound.singleton_bound(p, pieces, 's', 'C')


if __name__ == '__main__':
    unittest.main()
