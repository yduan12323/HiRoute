"""Combined opt-in policy; finite native graphs, no real-road launches."""
from dataclasses import replace
from fractions import Fraction as F
import math
import unittest

from . import test_energy as fixture
from timecut5 import terminal_energy as energy
from timecut5.bounded import _solve_problem
from timecut5.durable_incumbent import _independent_replay
from timecut5.hierarchy import _solve_hierarchical_problem, build_regions
from timecut5.probe import Interval
from timecut5.routing_config import (RoutingConfig, TerminalEnergyConfig, ROLES,
                                    require_full_verifier)


class CombinedTargetEnergyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.EnergyTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        fixture.EnergyTests.tearDownClass.__func__(cls)

    directory = fixture.EnergyTests.directory
    problem = fixture.EnergyTests.problem
    observer = fixture.EnergyTests.observer

    def context(self, *, mode='destination_target', enabled=True, role='search',
                g=None, anchors=None, cache_bytes=1000000, obs=None,
                unsupported='reject'):
        g = g or fixture.graph(4, [(a, b, abs(a-b), abs(a-b))
                                  for a in range(4) for b in range(4) if a != b])
        anchors = anchors or dict(A=0, B=1, D=3, X=2)
        config = RoutingConfig(mode, TerminalEnergyConfig(unsupported=unsupported)
                               if enabled else None)
        context = config.create_context(g, self.config, self.directory(), role=role,
            artifact=self.router_artifact,
            energy_artifact=self.energy_artifact if enabled else None,
            observation=obs, anchor_nodes=anchors, nodes_sha256=fixture.digest(g.node_count),
            edges_sha256=fixture.digest('synthetic edges'),
            anchor_catalog_sha256=fixture.digest(anchors),
            source_cache_max_bytes=cache_bytes)
        self.addCleanup(context.close)
        return context

    def test_only_search_activates_combined_policy_and_identity_records_mode(self):
        full, target = self.context(mode='full'), self.context()
        self.assertEqual(full.provider.source_sha256, target.provider.source_sha256)
        for context in (full, target):
            screen = self.problem(context)._terminal_energy_screen
            self.assertEqual(screen.receipt['original_native']['routing_mode'], context.router.mode)
            self.assertEqual(screen.receipt['routing_history']['original_native']['routing_mode'], context.router.mode)
        for role in ROLES:
            if role == 'search':
                continue
            context = self.context(role=role)
            self.assertEqual(context.router.mode, 'full')
            self.assertIsNone(context._energy_kernel)
            self.assertIsNone(self.problem(context)._terminal_energy_screen)
            self.assertFalse(hasattr(context.provider, '_terminal_energy_route_guard'))
            self.assertEqual(context.provider.source_sha256, target.provider.source_sha256)
            with self.assertRaises(ValueError):
                context.provider.leg('A', 'D', target_only=True)
            self.assertEqual(context.router.target_calls, 0)

    def test_final_labels_paths_and_energy_bound_match_full_routing(self):
        cases = [
            (6, [(0,1,1,4), (0,1,1,4), (0,2,1,2), (2,1,0,2),
                 (1,3,0,0), (3,1,0,0), (3,5,1,1)]),
            (5, [(0,1,9,1), (0,2,1,1), (2,1,1,0), (1,4,0,0)]),
            (6, [(0,1,2**53,0), (0,2,2**53,0), (1,3,1,0),
                 (2,3,0,0), (3,5,math.ulp(0.),math.ulp(0.))]),
            (4, [(0,1,0.,-0.), (1,2,0.,0.), (2,0,0.,0.)]),
            (4, [(0,1,1.,2**53), (1,2,1.,1.5), (2,3,1.,1.5)]),
            (4, []),
        ]
        for count, rows in cases:
            for order in (rows, list(reversed(rows))):
                with self.subTest(count=count, rows=order):
                    graph = fixture.graph(count, order)
                    anchors = dict(A=0, B=1, X=2, D=count-1)
                    full = self.context(mode='full', g=graph, anchors=anchors, cache_bytes=0)
                    target = self.context(g=graph, anchors=anchors, cache_bytes=0)
                    screen = self.problem(target)._terminal_energy_screen
                    self.problem(full)
                    for anchor in anchors:
                        expected = full.provider.leg(anchor, 'D')
                        actual = target.provider.leg(anchor, 'D', target_only=True)
                        self.assertEqual(expected, actual)
                        self.assertEqual(full.provider.edge_witnesses[anchor, 'D'],
                                         target.provider.edge_witnesses[anchor, 'D'])
                        if actual.reachable:
                            self.assertLessEqual(screen._lower[anchor], actual.energy(F(1)))
                    self.assertFalse(target.provider._source_labels)
                    self.assertEqual(target.provider.source_run_count, 0)
                    self.assertEqual(target.provider.target_run_count, len(anchors))
                    full.close(); target.close()

    def test_flat_hier_keys_action_order_and_fresh_full_replay(self):
        for method in ('flat', 'hier'):
            outcomes = []
            for mode in ('full', 'destination_target'):
                for enabled in (False, True):
                    context = self.context(mode=mode, enabled=enabled, cache_bytes=0)
                    problem = self.problem(context)
                    order, advance = [], problem.advance
                    def record(pieces, site, effect):
                        order.append((pieces[0].state.anchor, site, effect))
                        return advance(pieces, site, effect)
                    problem.advance = record
                    solved = (_solve_problem(problem) if method == 'flat' else
                              _solve_hierarchical_problem(problem, True, build_regions(problem.sites)).bounded)
                    result = solved.result
                    self.assertIsNotNone(result.witness)
                    verification = self.context(mode=mode, enabled=enabled, role='durable_verification')
                    verified_problem = self.problem(verification)
                    self.assertEqual(context.provider.source_sha256, verification.provider.source_sha256)
                    self.assertEqual(_independent_replay(lambda: verified_problem, result.witness), result.key)
                    self.assertEqual(verification.router.target_calls, 0)
                    self.assertEqual(verification.provider.target_run_count, 0)
                    outcomes.append((result.status, result.key, result.witness.pi, order))
                    if mode == 'destination_target':
                        self.assertGreater(context.provider.target_run_count, 0)
                    context.close(); verification.close()
            self.assertTrue(all(value == outcomes[0] for value in outcomes))

    def test_partial_labels_isolated_but_complete_cache_can_serve_target(self):
        context = self.context()
        self.problem(context)
        provider = context.provider
        selected = provider.leg('A', 'D', target_only=True)
        self.assertFalse(provider._source_labels)
        self.assertEqual((provider.source_run_count, provider.target_run_count), (0, 1))
        self.assertIs(provider.leg('A', 'D'), selected)
        provider.leg('A', 'B')
        self.assertEqual((provider.source_run_count, provider.target_run_count), (1, 1))
        provider.leg('A', 'X', target_only=True)
        self.assertEqual((provider.source_run_count, provider.target_run_count), (1, 1))
        for arrays, _ in provider._source_labels.values():
            self.assertTrue(all(array.flags.owndata and not array.flags.writeable for array in arrays))
        self.assertEqual(provider._terminal_energy_route_guard.pending, 0)

    def test_screen_rejects_only_immediate_finish_and_preserves_closed_equality(self):
        context = self.context(cache_bytes=0)
        problem = self.problem(context)
        screen = problem._terminal_energy_screen
        initial = problem.initial_piece()
        before = context.provider.target_run_count
        self.assertEqual(problem.finish((initial,)), ())
        self.assertEqual(context.provider.target_run_count, before)
        self.assertTrue(problem.advance((initial,), 's', 'C'))
        threshold = problem.reserve + screen._lower['A']
        closed = replace(initial, domain=Interval(threshold, threshold))
        opened = replace(initial, domain=Interval(F(0), threshold, True, False))
        self.assertFalse(screen.reject(problem, (closed,)))
        self.assertTrue(screen.reject(problem, (opened,)))

    def test_target_cache_hits_and_misses_keep_floating_environment_guard(self):
        for cache_hit in (False, True):
            context = self.context()
            self.problem(context)
            if cache_hit:
                context.provider.leg('A', 'D', target_only=True)
            old = self.flags.test_get_round()
            try:
                self.flags.test_set_round(self.flags.test_downward())
                with self.assertRaises(energy.UnsupportedEnvironment):
                    context.provider.leg('A', 'D', target_only=True)
            finally:
                self.flags.test_set_round(old)
            self.assertEqual(context.provider.target_run_count, int(cache_hit))

    def test_prior_target_history_cannot_be_adopted_or_used_as_full_verifier(self):
        context = self.context()
        provider = context.provider
        provider.router.target_edges(0, 3)
        del provider._terminal_energy_route_guard
        with self.assertRaisesRegex(ValueError, 'prior selected-routing'):
            energy.RoutingHistoryGuard(provider, context._energy_kernel, 'reject')
        other = self.context()
        self.problem(other)
        other.provider.leg('A', 'D', target_only=True)
        with self.assertRaisesRegex(ValueError, 'full-only'):
            require_full_verifier(other.provider, fresh=True)
        verification = self.context(role='recovery')
        require_full_verifier(verification.provider, fresh=True)
        self.assertEqual(other.provider.source_sha256, verification.provider.source_sha256)

    def test_mode_mutation_fails_before_cached_return(self):
        context = self.context()
        self.problem(context)
        context.provider.leg('A', 'D', target_only=True)
        context.router._mode = 'full'
        try:
            with self.assertRaisesRegex(ValueError, 'binding'):
                context.provider.leg('A', 'D', target_only=True)
        finally:
            context.router._mode = 'destination_target'

    def test_combined_evidence_publishes_checked_mode_and_clean_closure(self):
        observer = self.observer()
        context = self.context(obs=observer)
        screen = self.problem(context)._terminal_energy_screen
        context.provider.leg('A', 'D', target_only=True)
        self.assertEqual(screen.receipt['original_native']['routing_mode'], 'destination_target')
        self.assertEqual(screen.receipt['routing_history']['pending_operations'], 0)
        context.close()
        observer.complete(context)
        self.assertTrue(observer.final_complete)


if __name__ == '__main__':
    unittest.main()
