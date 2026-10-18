"""Synthetic proof/guard checks only. No road cohort, installation or holdout."""
from copy import deepcopy
from dataclasses import asdict, replace
from fractions import Fraction as F
from itertools import product
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from timecut5.bounded import Problem, _solve_problem, _replay_problem
from timecut5.hierarchy import _solve_hierarchical_problem, build_regions
from timecut5.post_service_dominance import (VERSION, make_post_service_reducer,
                                           PostServiceDominanceStatistics)
from timecut5.probe import Cut, Event, Interval, State, Witness
from timecut5.pwa import CutPiece, charge_pwa, reduce_frontier_skyline
from timecut5.provenance import Recorder, signature, witness_dict
from timecut5.real_adapter import RealProblem
from timecut5.real_legs import ImmutableLegTable

ROOT = Path(__file__).resolve().parents[1]


def case():
    return dict(H_ref=3, origin='o', destination='z', start_time_s=0,
        initial_energy_kwh=2, capacity_kwh=4, minimum_energy_kwh=0,
        reserve_kwh=0, consumption_kwh_per_m=1, overhead_s=1,
        lambda_stop_s=1, schedule=None, sites={x: ['C', 'S', 'CS'] for x in ('a', 'b', 'x')},
        charging_segments=[[0, 2, 2, 0], [2, 4, 1, 2]],
        edges=[dict(source=a, target=b, time_s=1, length_m=1)
               for a in ('o', 'a', 'b', 'x') for b in ('a', 'b', 'x', 'z') if a != b])


def seed(domain=None, *, slope=0, intercept=0, chi=True, rho=0,
         name='a', state=None, pi=None, tag=None, seen=None):
    domain = domain or Interval(0, 4)
    state = state or State('x', 0, 2)
    pi = pi if pi is not None else ((name, 'C'), ('x', 'C'))
    slope, intercept, rho = F(slope), F(intercept), F(rho)
    tag = tag or name
    def point(energy):
        if not domain.contains(energy):
            raise AssertionError('Callback escaped its inherited predecessor domain')
        if seen is not None:
            seen.append(energy)
        tau = slope*energy + intercept
        def approach(epsilon):
            time = tau if chi else tau + min(F(1), epsilon/2)
            return Witness(time, energy, rho, pi, state,
                           (Event('analytic', tag, time, time, energy, energy),))
        return Cut(tau, chi, energy, rho, pi, state, approach)
    return CutPiece(domain, slope, intercept, chi, rho, pi, state, point)


def policy(problem=None, **kwargs):
    return make_post_service_reducer(problem or Problem(case()), enabled=True,
                                    completed_departure_layers=True, **kwargs)


def canonical(value):
    r = value.canonical()['result']
    if r['status'] == 'attained_optimum':
        return r['status'], r['J'], r['Q_total'], r['H'], tuple(map(tuple, r['site_action_tuple']))
    if r['status'] == 'primary_unattained':
        return r['status'], r['primary_infimum']
    if r['status'] == 'secondary_unattained':
        return r['status'], r['J'], r['secondary_infimum']
    return (r['status'],)


def reference_key(r):
    if r['status'] == 'attained_optimum':
        return r['status'], F(r['J']), F(r['Q_total']), r['H'], tuple(map(tuple, r['site_action_tuple']))
    if r['status'] == 'primary_unattained':
        return r['status'], F(r['primary_infimum'])
    if r['status'] == 'secondary_unattained':
        return r['status'], F(r['J']), F(r['secondary_infimum'])
    return (r['status'],)


def stats_consistent(test, reducer):
    s = reducer.snapshot()
    test.assertIs(type(s), PostServiceDominanceStatistics)
    data = asdict(s)
    test.assertTrue(all(type(v) is int and v >= 0 for k, v in data.items() if k != 'enabled'))
    test.assertEqual(s.calls, s.strong_calls+s.disabled_fallback_calls+
                     s.pre_service_fallback_calls+s.recorded_fallback_calls+s.unsupported_fallback_calls)
    test.assertEqual(s.candidate_visits,
                     s.selected_cells+s.strict_primary_discarded+s.tied_primary_discarded)
    test.assertLessEqual(s.selected_cells-s.parent_run_coalesces, s.output_pieces)


class PointAndCellTests(unittest.TestCase):
    def test_default_off_and_exact_boolean_admission(self):
        p = Problem(case())
        a, b = seed(rho=2), seed(intercept=1, rho=0, name='b')
        reducer = make_post_service_reducer(p)
        self.assertEqual(tuple(map(signature, reducer((a, b)))),
                         tuple(map(signature, reduce_frontier_skyline((a, b)))))
        self.assertEqual(reducer.snapshot().disabled_fallback_calls, 1)
        self.assertEqual(reducer.snapshot().strong_calls, 0)
        with self.assertRaises(ValueError):
            make_post_service_reducer(p, enabled=True)
        for options in (dict(enabled=1), dict(completed_departure_layers=1)):
            with self.assertRaises(TypeError):
                make_post_service_reducer(p, **options)
        stats_consistent(self, reducer)

    def test_exhaustive_primary_attainment_rho_pi_point_order(self):
        p = Problem(case())
        reducer = policy(p)
        choices = [seed(Interval(1, 1), intercept=t, chi=chi, rho=rho, name=name)
                   for t, chi, rho, name in product((F(0), F(1, 7)), (False, True),
                                                   (F(0), F(1)), ('a', 'b'))]
        for a, b in product(choices, repeat=2):
            expected = min(enumerate((a, b)), key=lambda row:
                (row[1].intercept, not row[1].chi, row[1].rho, row[1].pi, row[0]))[1]
            result, = reducer((a, b))
            self.assertIs(result._point, expected._point)
            for epsilon in (F(1), F(1, 10**60)):
                result.at(F(1)).approach(epsilon)
        stats_consistent(self, reducer)

    def test_strict_primary_may_ignore_worse_rho_and_pi(self):
        for a, b in ((seed(rho=5, name='b'), seed(intercept=1, name='a')),
                     (seed(chi=False, rho=5, name='b'), seed(intercept=1, name='a')),
                     (seed(rho=5, name='b'), seed(chi=False, name='a'))):
            reducer = policy()
            result, = reducer((a, b))
            self.assertIs(result._point, a._point)
            self.assertGreater(reducer.snapshot().strict_primary_discarded, 0)

    def test_tied_primary_needs_rho_then_pi_and_stable_original_parent(self):
        for a, b, winner in ((seed(rho=5), seed(name='b'), 1),
                             (seed(name='b'), seed(name='a'), 1),
                             (seed(tag='first'), seed(tag='second'), 0)):
            result, = policy()((a, b))
            self.assertIs(result._point, (a, b)[winner]._point)

    def test_crossing_knot_uses_exact_secondary_tie_and_original_callback(self):
        a = seed(Interval(0, 2), slope=1, rho=2)
        b = seed(Interval(0, 2), slope=-1, intercept=2, name='b')
        result = policy()((a, b))
        self.assertEqual([p.domain for p in result],
                         [Interval(0, 1, True, False), Interval(1, 2)])
        self.assertIs(result[0]._point, a._point)
        self.assertIs(result[1]._point, b._point)
        self.assertEqual(result[1].at(F(1)).rho, 0)

    def test_same_parent_runs_remove_inactive_crossings_without_filling_holes(self):
        winner = seed(Interval(0, 2))
        loser_a = seed(Interval(0, 2), slope=1, intercept=10)
        loser_b = seed(Interval(0, 2), slope=-1, intercept=12, name='b')
        reducer = policy()
        result, = reducer((winner, loser_a, loser_b))
        self.assertEqual(result.domain, winner.domain)
        self.assertIs(result._point, winner._point)
        self.assertGreater(reducer.snapshot().parent_run_coalesces, 0)
        isolated = seed(Interval(1, 1), intercept=-1, name='b')
        result = policy()((winner, isolated))
        self.assertEqual([p.domain for p in result],
            [Interval(0, 1, True, False), Interval(1, 1), Interval(1, 2, False, True)])
        left, right = seed(Interval(0, 1, False, False)), seed(Interval(1, 2, False, False))
        result = policy()((left, right))
        self.assertEqual([p.domain for p in result], [left.domain, right.domain])
        self.assertFalse(any(p.domain.contains(F(1)) for p in result))

    def test_every_active_callback_validated_even_if_dominated(self):
        good = seed()
        bad = replace(seed(intercept=1), _point=lambda energy: (_ for _ in ()).throw(ValueError('bad inherited cut')))
        with self.assertRaisesRegex(ValueError, 'bad inherited cut'):
            policy()((good, bad))

    def test_parent_restrictions_survive_small_epsilon_future_charge(self):
        p = Problem(case())
        visited = []
        source = seed(Interval(F(1, 4), F(3, 4), False, False),
                      slope=3, seen=visited, tag='restricted')
        selected, = policy(p)((source,))
        self.assertIs(selected._point, source._point)
        output = charge_pwa((selected,), p.curve, p.overhead, 'x')
        for energy in (F(1), F(2), F(3)):
            for piece in output:
                if piece.domain.contains(energy):
                    for epsilon in (F(1), F(1, 10**80)):
                        w = piece.at(energy).approach(epsilon)
                        original = w.events[0]
                        self.assertTrue(source.domain.contains(original.arrival_energy))
                        self.assertEqual(original.site, 'restricted')
                        self.assertGreater(w.events[-1].departure_energy, w.events[-1].arrival_energy)
        self.assertTrue(visited)
        self.assertTrue(all(source.domain.contains(e) for e in visited))

    def test_empty_successful_calls_have_conserved_detached_scalars(self):
        reducer = policy()
        self.assertEqual(reducer(()), ())
        self.assertEqual(reducer.snapshot().strong_calls, 1)
        self.assertEqual(reducer.snapshot().arrangement_cells, 0)
        detached = asdict(reducer.snapshot())
        detached['calls'] = -1
        self.assertEqual(reducer.snapshot().calls, 1)
        stats_consistent(self, reducer)


class GuardAndFallbackTests(unittest.TestCase):
    def test_unsupported_subclass_and_changed_method_query_bound_or_owner_reject(self):
        class Extension(Problem):
            pass
        with self.assertRaises(TypeError):
            policy(Extension(case()))
        for change in ('bound', 'query', 'owner', 'leg', 'method'):
            p = Problem(case())
            reducer = policy(p)
            if change == 'bound':
                p.bound += 1
            elif change == 'query':
                p.case['overhead_s'] = 2
            elif change == 'owner':
                p.site_anchors = dict(p.site_anchors)
            elif change == 'leg':
                pair = next(iter(p.legs))
                p.legs[pair] = replace(p.legs[pair], time=p.legs[pair].time+1)
            else:
                p.advance = lambda *args: ()
            with self.subTest(change=change), self.assertRaises((ValueError, TypeError)):
                reducer((seed(),))
            self.assertEqual(reducer.snapshot().calls, 0)

    def test_mixed_states_bad_phase_energy_types_and_service_history_reject(self):
        good = seed()
        bad_chi = seed()
        object.__setattr__(bad_chi, 'chi', 1)
        invalid = [seed(state=State('a', 0, 2)),
                   seed(Interval(0, 5)),
                   seed(pi=(('missing', 'C'), ('x', 'C'))),
                   seed(pi=(('a', 'S'), ('x', 'C'))),
                   bad_chi]
        for bad in invalid:
            with self.subTest(bad=bad), self.assertRaises((ValueError, TypeError)):
                policy()((bad,))
        with self.assertRaises(ValueError):
            policy()((good, seed(state=State('a', 0, 2))))
        d = Interval(0, 4)
        object.__setattr__(d, 'left_closed', 1)
        with self.assertRaises(ValueError):
            policy()((seed(d),))

    def test_pre_service_fallback_preserves_waiting_tradeoff(self):
        source = case()
        source.update(schedule=dict(a=10, b=20, D=1))
        p = Problem(source)
        state = State('x', 1, 2)
        a, b = seed(rho=2, state=state), seed(intercept=1, state=state, name='b')
        reducer = policy(p)
        self.assertEqual(tuple(map(signature, reducer((a, b)))),
                         tuple(map(signature, reduce_frontier_skyline((a, b)))))
        self.assertEqual(reducer.snapshot().pre_service_fallback_calls, 1)
        self.assertEqual(reducer.snapshot().strong_calls, 0)
        stats_consistent(self, reducer)

    def test_active_recorder_uses_historical_certificate_without_relabeling(self):
        from validation.family5 import verify_bundle
        source = json.loads((ROOT/'tests/fixtures/milestone_5_reference/frozen_cases_v2.json').read_text())[0]
        p = Problem(source)
        reducer = policy(p)
        with Recorder() as recorder:
            solved = _solve_problem(p, True, reducer=reducer)
            bundle = recorder.export()
        checked = verify_bundle(bundle, source)
        self.assertTrue(checked.summary['verified'])
        self.assertIsNotNone(solved.result.key)
        self.assertGreater(reducer.snapshot().recorded_fallback_calls, 0)
        self.assertEqual(reducer.snapshot().strong_calls, 0)
        stats_consistent(self, reducer)

    def test_known_family_outside_recorder_is_never_stripped(self):
        p = Problem(case())
        reducer = policy(p)
        with Recorder():
            pieces = p.advance((p.initial_piece(),), 'x', 'C')
        with self.assertRaisesRegex(ValueError, 'Recorder context'):
            reducer(pieces)
        self.assertTrue(all(piece._family is not None for piece in pieces))


class SolverDifferentialTests(unittest.TestCase):
    def test_all_eighteen_frozen_cases_both_engines_full_key_and_replay(self):
        cases = json.loads((ROOT/'tests/fixtures/milestone_5_reference/frozen_cases_v2.json').read_text())
        from validation.reference5 import solve_case
        # Independent exhaustive reference is evaluated fresh, never loaded from
        # a published solver-output cache. Inputs carry hand-arithmetic checks.
        statuses = set()
        pre = strong = 0
        for source in cases:
            reference = solve_case(source, keep_evidence=False)
            self.assertEqual(source['case_id'], reference['case_id'])
            self.assertTrue(reference['all_regimes_certified'])
            for hier in (False, True):
                answers = []
                for enabled in (False, True):
                    p = Problem(source)
                    reducer = make_post_service_reducer(p, enabled=enabled, completed_departure_layers=True)
                    solved = (_solve_hierarchical_problem(p, True, build_regions(p.sites), reducer=reducer).bounded
                              if hier else _solve_problem(p, True, reducer=reducer))
                    answers.append(canonical(solved))
                    statuses.add(solved.canonical()['result']['status'])
                    self.assertEqual(canonical(solved), reference_key(reference['result']))
                    if solved.result.witness is not None:
                        self.assertEqual(_replay_problem(p, solved.result.witness), solved.result.key)
                    pre += reducer.snapshot().pre_service_fallback_calls
                    strong += reducer.snapshot().strong_calls
                    stats_consistent(self, reducer)
                self.assertEqual(answers[0], answers[1], (source['case_id'], hier))
        self.assertEqual(len(statuses), 4)
        self.assertGreater(pre, 0)
        self.assertGreater(strong, 0)

    def test_independent_continuous_exhaustive_two_charge_future_completions(self):
        from collections import defaultdict
        from validation.family5 import independent_oracle_v2 as oracle
        source = case()
        source['H_ref'] = 4  # Two declared prefix stops plus two future C stops.
        p = Problem(source)
        fronts = [
            [seed(rho=2), seed(intercept=1, name='b')],
            [seed(chi=False, rho=2), seed(intercept=1, name='b')],
            [seed(rho=2), seed(chi=False, name='b')],
            [seed(slope=1, rho=2), seed(slope=-1, intercept=4, name='b')],
            [seed(Interval(1, 2, False, True)), seed(Interval(2, 2), name='b')],
            [seed(chi=False), seed(Interval(1, 1), rho=1, name='b')],
        ]
        def convert(piece):
            return oracle.Piece(piece.domain.lo, piece.domain.hi,
                piece.domain.left_closed, piece.domain.right_closed,
                piece.slope, piece.intercept, piece.chi, piece.rho, piece.pi,
                (piece.state.anchor, piece.state.remaining_schedule, piece.state.stop_count))
        def complete(front, enabled):
            layer = list(map(convert, front))
            terminal = []
            reducer = policy(p)
            for depth in range(3):
                if enabled:
                    by_state = defaultdict(list)
                    for q in layer:
                        by_state[q.state].append(seed(Interval(q.lo, q.hi, q.lc, q.rc),
                            slope=q.m, intercept=q.b, chi=q.chi, rho=q.rho,
                            pi=q.pi, state=State(*q.state)))
                    layer = [convert(q) for group in by_state.values() for q in reducer(group)]
                following = []
                for q in layer:
                    anchor = q.state[0]
                    leg = p.legs[anchor, p.destination]
                    terminal.extend(oracle.transform([q], 'D', dict(site=p.destination,
                        duration=leg.time, consumption=leg.energy, floor=p.reserve)))
                    if depth < 2:
                        for site in ('a', 'b'):
                            leg = p.legs[anchor, site]
                            incoming = oracle.transform([q], 'D', dict(site=site,
                                duration=leg.time, consumption=leg.energy, floor=p.floor))
                            following.extend(oracle.transform(incoming, 'C',
                                dict(site=site, h=p.overhead, curve=p.curve.segments)))
                layer = following
            return oracle.terminal_expected(terminal, p.penalty, p.reserve)
        statuses = set()
        for front in fronts:
            expected = complete(front, False)
            self.assertEqual(complete(front, True), expected)
            statuses.add((expected['status'], expected.get('unattained_component')))
        self.assertIn(('infimum_unattained', 'J'), statuses)
        self.assertIn(('infimum_unattained', 'Q'), statuses)

    def test_all_five_real_mock_alias_cases_full_key_and_fresh_replay(self):
        rows = json.loads((ROOT/'tests/fixtures/milestone_5_real_leg_contract/mock_solver_cases.json').read_text())
        for row in rows:
            data = json.dumps(row['table'], sort_keys=True, separators=(',', ':')).encode()
            table = ImmutableLegTable.from_bytes(data, row['table_sha256'])
            for hier in (False, True):
                answers = []
                for enabled in (False, True):
                    p = RealProblem(row['query'], table)
                    reducer = make_post_service_reducer(p, enabled=enabled, completed_departure_layers=True)
                    solved = (_solve_hierarchical_problem(p, True, build_regions(p.sites), reducer=reducer).bounded
                              if hier else _solve_problem(p, True, reducer=reducer))
                    answers.append(canonical(solved))
                    if solved.result.witness is not None:
                        self.assertEqual(_replay_problem(RealProblem(row['query'], table), solved.result.witness), solved.result.key)
                    stats_consistent(self, reducer)
                self.assertEqual(answers[0], answers[1], (row['case_id'], hier))

    def test_raw_site_id_cannot_masquerade_as_physical_anchor(self):
        row = json.loads((ROOT/'tests/fixtures/milestone_5_real_leg_contract/mock_solver_cases.json').read_text())[0]
        data = json.dumps(row['table'], sort_keys=True, separators=(',', ':')).encode()
        p = RealProblem(row['query'], ImmutableLegTable.from_bytes(data, row['table_sha256']))
        pieces = p.advance((p.initial_piece(),), 'B', 'S')
        self.assertTrue(pieces)
        self.assertEqual(pieces[0].state.anchor, 'road:x')
        bad = tuple(replace(piece, state=State('B', 0, 1)) for piece in pieces)
        with self.assertRaisesRegex(ValueError, 'physical departure anchor'):
            policy(p)(bad)


class NativeAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.terminal_energy import test_energy as fixture
        fixture.EnergyTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        from tests.terminal_energy import test_energy as fixture
        fixture.EnergyTests.tearDownClass.__func__(cls)

    def directory(self):
        from tests.terminal_energy import test_energy as fixture
        return fixture.EnergyTests.directory(self)

    def context(self, *args, **kwargs):
        from tests.terminal_energy import test_combined_target_energy as fixture
        return fixture.CombinedTargetEnergyTests.context(self, *args, **kwargs)

    def make(self, **kwargs):
        from tests.terminal_energy.test_remaining_charge_runtime import RemainingChargeRuntimeTests
        return RemainingChargeRuntimeTests.make(self, **kwargs)

    def test_native_same_problem_runtime_required_and_supported_modes_match(self):
        for mode in ('full', 'destination_target'):
            _, p, _, runtime = self.make(mode=mode)
            with self.assertRaisesRegex(ValueError, 'Same live admitted'):
                policy(p)
            _, other, _, other_runtime = self.make(mode=mode)
            with self.assertRaisesRegex(ValueError, 'Same live admitted'):
                policy(p, runtime=other_runtime)
            answers = []
            for hier in (False, True):
                reducer = policy(p, runtime=runtime)
                solved = (_solve_hierarchical_problem(p, True, build_regions(p.sites), reducer=reducer).bounded
                          if hier else _solve_problem(p, True, reducer=reducer))
                answers.append(canonical(solved))
                self.assertGreater(reducer.snapshot().strong_calls, 0)
                self.assertEqual(p.bound, runtime.original_hmax)
                stats_consistent(self, reducer)
                if solved.result.witness is not None:
                    from timecut5.routing_config import require_full_verifier
                    fresh_context = self.context(mode='full', role='verification', g=p.provider.graph)
                    require_full_verifier(fresh_context.provider, fresh=True)
                    from timecut5.real_adapter import site_catalog_digest
                    from timecut5.real_legs import RealSite
                    sites = {sid: RealSite(sid, p.site_anchors[sid], effects) for sid, effects in p.sites.items()}
                    fresh = fresh_context.problem(p.case, sites, origin_anchor=p.origin,
                        destination_anchor=p.destination, site_catalog_sha256=site_catalog_digest(sites))
                    self.assertIsNot(fresh.provider, p.provider)
                    self.assertEqual(_replay_problem(fresh, solved.result.witness), solved.result.key)
            self.assertEqual(answers[0], answers[1])

    def test_native_unsupported_falls_back_and_changed_owner_rejects(self):
        _, p, _, runtime = self.make()
        reducer = policy(p, runtime=runtime)
        initial = (p.initial_piece(),)
        with patch.object(runtime, '_check', return_value=('disabled_unsupported', None, None)):
            self.assertEqual(tuple(map(signature, reducer(initial))),
                             tuple(map(signature, reduce_frontier_skyline(initial))))
        self.assertEqual(reducer.snapshot().unsupported_fallback_calls, 1)
        stats_consistent(self, reducer)
        old = p.provider
        p.provider = object()
        try:
            with self.assertRaises((ValueError, AttributeError)):
                reducer(initial)
        finally:
            p.provider = old


if __name__ == '__main__':
    unittest.main()
