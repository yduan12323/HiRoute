"""Proof fixtures for the optional shared pending-activity relaxation."""
from fractions import Fraction as F
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tests'))
import test_scale_bounds as baseline_bounds
import test_scale_search as baseline_search
from hiroute.contracts import ProblemSnapshot
from hiroute.exact import scale
from hiroute.exact.interval import Interval
from hiroute.exact.pipeline import execute_exact_plan, DriveStep, StopStep, initial_piece
from hiroute.exact.pwa import AffineCutPiece
from hiroute.exact.road_index import RoadIndex
from hiroute.exact.scale_bounds import (pending_activity_possible,
    pending_service_travel_bound, service_summary, singleton_region)


class PendingActivityScreenTests(unittest.TestCase):
    def piece(self, domain=Interval(0, 2), slope=1, intercept=3, attained=True, remaining=1):
        return AffineCutPiece(domain, F(slope), F(intercept), attained,
                              state_key=('a', remaining, 0))

    def test_equality_open_infima_unions_and_negative_slope(self):
        for slope, domain, intercept in ((1, Interval(0, 2, False, False), 3),
                                         (-1, Interval(0, 2, False, False), 5)):
            for attained in (False, True):
                p = self.piece(domain, slope, intercept, attained)
                self.assertTrue(pending_activity_possible((p,), latest_arrival=5,
                                                         service_travel_time=2))
                self.assertFalse(pending_activity_possible((p,), latest_arrival=F(499, 100),
                                                          service_travel_time=2))
                self.assertEqual(p.domain, domain)
                self.assertEqual(p.attained, attained)
        late = self.piece(intercept=20)
        early = self.piece(intercept=1)
        self.assertTrue(pending_activity_possible((late, early), latest_arrival=3,
                                                  service_travel_time=2))
        self.assertFalse(pending_activity_possible((late,), latest_arrival=3,
                                                   service_travel_time=None))
        self.assertTrue(pending_activity_possible((self.piece(remaining=0),),
            latest_arrival=-100, service_travel_time=None))
        self.assertFalse(pending_activity_possible((), latest_arrival=10, service_travel_time=0))

    def test_directed_region_coverage_against_every_represented_service_path(self):
        fixture = baseline_bounds.SummaryRegionTests(); fixture.setUp()
        service = service_summary(fixture.capabilities, fixture.features)
        services = [s for s in fixture.sites if set(fixture.capabilities[s]) & {'S', 'CS'}]
        self.assertEqual(service.count, len(services))  # CS+S counted once.
        for region in fixture.walk(fixture.root):
            for effect, mask in region.effect_masks.items():
                for anchor in fixture.nodes[:-1]:
                    bound = pending_service_travel_bound(fixture.features[anchor], service,
                        region.summaries[effect], effect, 1)
                    for index, first in enumerate(fixture.sites):
                        if not mask & (1 << index): continue
                        inbound = fixture.metrics[0][anchor, first]
                        if inbound is None: continue
                        if effect in ('S', 'CS'):
                            self.assertLessEqual(bound, inbound)
                        else:
                            for last in services:
                                onward = fixture.metrics[0][first, last]
                                if onward is not None:
                                    self.assertLessEqual(bound, inbound+1+onward)
                    if region.site is not None:
                        singleton = singleton_region(region.site, fixture.capabilities[region.site],
                                                     fixture.features[region.site])
                        self.assertEqual(bound, pending_service_travel_bound(
                            fixture.features[anchor], service, singleton.summaries[effect], effect, 1))
        fixture.test_refinement_is_complete_and_disjoint_for_every_effect()

    def test_internal_query_has_no_candidate_or_tree_access(self):
        fixture = baseline_bounds.SummaryRegionTests(); fixture.setUp()
        service = service_summary(fixture.capabilities, fixture.features)
        summary = fixture.root.summaries['C']
        class ExtremaOnly:
            def __getattr__(self, name):
                if name in ('min_from_origin_time', 'min_to_destination_time',
                            'max_to_destination_time'):
                    return getattr(summary, name)
                raise AssertionError('query inspected '+name)
        self.assertGreaterEqual(pending_service_travel_bound(fixture.features['a'], service,
                                                            ExtremaOnly(), 'C', 1), 0)
        self.assertIsNone(service_summary({'a': ('C',)}, {'a': fixture.features['a']}))

    def test_core_window_is_exact_but_c_does_not_precheck_future_service(self):
        root = initial_piece(Interval(2, 2), anchor='o', remaining_schedule=1, rho=-2)
        c = (DriveStep('c', F(2), F(1)),
             StopStep('C', 'c', F(1), ((F(0), F(5), F(1), F(0)),)))
        charged = execute_exact_plan((root,), c)
        self.assertTrue(charged)  # The physical C prefix is valid.
        served = execute_exact_plan(charged, (DriveStep('s', F(4), F(1)),
            StopStep('S', 's', F(1), a=F(0), b=F(3), duration=F(1))))
        self.assertEqual(served, ())  # Core only rejects when service is attempted.

    def nonredundant_source(self):
        e = baseline_search.edge
        return baseline_search.raw(initial_energy_kwh='5', capacity_kwh='5',
            candidate_order=['c', 's'], site_capabilities={'c': ['C'], 's': ['S']},
            charging_curve=[['0', '5', '1', '0']], depth_limit=2,
            schedule={'a': '0', 'b': '3', 'D': '1'}, initial_remaining_schedule=1,
            directed_edges=[e('o', 'c', 2), e('c', 'z', 1), e('c', 's', 4),
                            e('o', 's', 1), e('s', 'z', 20)])

    def test_nonredundant_pre_route_rejection_both_methods_and_bound_ablation(self):
        snapshot = ProblemSnapshot.from_dict(self.nonredundant_source())
        expected = baseline_search.solve_snapshot(snapshot, baseline_search.old_config())
        for method in baseline_search.METHODS:
            old = scale.solve_scale(snapshot, method=method)
            new = scale.solve_scale(snapshot, method=method, pending_activity_screen=True)
            off = scale.solve_scale(snapshot, method=method, pending_activity_screen=True, use_bound=False)
            for r in (old, new, off):
                self.assertEqual(baseline_search.semantics(r), baseline_search.semantics(expected))
                self.assertEqual(baseline_search.verify_scale_witness(snapshot, r)['independent_key'], r['key'])
            self.assertEqual(old['seed']['key'], new['seed']['key'])
            self.assertGreater(new['metrics']['pending_activity_pruned_actions'], 0)
            self.assertLess(new['metrics']['transitions'], old['metrics']['transitions'])
            self.assertLess(new['metrics']['leaf_routes'], old['metrics']['leaf_routes'])
            self.assertEqual(off['metrics']['pending_activity_pruned_actions'], 0)
            self.assertEqual(off['metrics']['pending_activity_late_empty_actions'], 0)

    def test_exact_selected_inbound_can_reject_after_weak_static_landmarks(self):
        snapshot = ProblemSnapshot.from_dict(self.nonredundant_source())
        class ZeroLandmarks(RoadIndex):
            # Explicitly weaker safe zero features isolate the post-route hook;
            # no production provider or selected-leg semantics is changed.
            def distances_from(self, source, weight):
                return dict.fromkeys(('o', 'c', 's', 'z'), F(0))
            distances_to = distances_from
        for method in baseline_search.METHODS:
            with patch.object(scale, 'deterministic_seed', return_value=(None, 0)), \
                 patch('hiroute.exact.scale_bounds.completion_bound', return_value=F(0)):
                r = scale.solve_scale(snapshot, method=method, provider=ZeroLandmarks(snapshot.directed_edges),
                                      pending_activity_screen=True)
            self.assertEqual(r['status'], 'attained_optimum')
            self.assertGreater(r['metrics']['pending_activity_late_empty_actions'], 0)
            self.assertEqual(baseline_search.verify_scale_witness(snapshot, r)['independent_key'], r['key'])

    def test_full_key_unattainment_energy_temporal_and_time_translation(self):
        cases = json.loads((ROOT/'tests/fixtures/milestone_5_reference/frozen_cases_v2.json').read_text())
        sources = [baseline_search.frozen_snapshot(cases[i]) for i in (5, 6, 7, 8, 14)]
        for shift in (-50, 0, 100):
            source = self.nonredundant_source()
            source['departure_time_s'] = str(shift)
            source['schedule'] = {'a': str(shift), 'b': str(3+shift), 'D': '1'}
            sources.append(source)
        for source in sources:
            snapshot = ProblemSnapshot.from_dict(source)
            expected = baseline_search.solve_snapshot(snapshot, baseline_search.old_config())
            for method in baseline_search.METHODS:
                r = scale.solve_scale(snapshot, method=method, pending_activity_screen=True,
                    inbound_energy_bound=True, eager_incumbent_pruning=True)
                self.assertEqual(baseline_search.semantics(r), baseline_search.semantics(expected))
                if r['status'] == 'attained_optimum':
                    self.assertEqual(baseline_search.verify_scale_witness(snapshot, r)['independent_key'], r['key'])

    def test_completed_service_future_charging_and_same_site_cs_are_retained(self):
        e = baseline_search.edge
        source = baseline_search.raw(initial_energy_kwh='1', capacity_kwh='2', depth_limit=2,
            candidate_order=['s', 'c'], site_capabilities={'s': ['S', 'CS'], 'c': ['C']},
            charging_curve=[['0', '2', '1', '0']], schedule={'a': '0', 'b': '2', 'D': '1'},
            initial_remaining_schedule=1, directed_edges=[e('o', 's'), e('s', 'c', length=2),
                                                         e('c', 'z', length=2)])
        snapshot = ProblemSnapshot.from_dict(source)
        for method in baseline_search.METHODS:
            off = scale.solve_scale(snapshot, method=method)
            on = scale.solve_scale(snapshot, method=method, pending_activity_screen=True)
            self.assertEqual(baseline_search.semantics(on), baseline_search.semantics(off))
            self.assertEqual(on['status'], 'attained_optimum')
            self.assertEqual(on['plan'], (('s', 'CS'), ('c', 'C')))
            self.assertEqual(baseline_search.verify_scale_witness(snapshot, on)['independent_key'], on['key'])

    def test_independent_finite_ref_on_the_same_tiny_domain(self):
        source = self.nonredundant_source()
        independent, _ = baseline_search.snapshot_case(source)
        ref = baseline_search.solve_case(independent, keep_evidence=False)['result']
        self.assertEqual(ref['status'], 'attained_optimum')
        snapshot = ProblemSnapshot.from_dict(source)
        for method in baseline_search.METHODS:
            r = scale.solve_scale(snapshot, method=method, pending_activity_screen=True)
            self.assertEqual(r['key'], ref['lex_key'])

    def test_flag_contract_rejected_before_index(self):
        snapshot = ProblemSnapshot.from_dict(baseline_search.raw())
        with patch('hiroute.exact.road_index.RoadIndex', side_effect=AssertionError('constructed index')):
            for flag in (None, 0, 1, 'true', 1.5):
                with self.assertRaisesRegex(ValueError, 'pending_activity_screen'):
                    scale.solve_scale(snapshot, pending_activity_screen=flag)

    def test_live_diagnostics_survive_a_late_external_resource_exception(self):
        snapshot=ProblemSnapshot.from_dict(baseline_search.raw())
        class LateLimit(RoadIndex):
            def metrics(self):raise scale.ResourceLimit('time_limit')
        for method in baseline_search.METHODS:
            diagnostics={}
            with self.assertRaises(scale.ResourceLimit):
                scale.solve_scale(snapshot,method=method,provider=LateLimit(snapshot.directed_edges),
                                  diagnostics=diagnostics)
            self.assertGreater(diagnostics['metrics']['terminal_attempts'],0)
            self.assertIn('search',diagnostics['seconds'])
            self.assertNotIn('key',diagnostics)


if __name__ == '__main__':
    unittest.main()
