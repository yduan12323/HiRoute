"""Small source-bound graphs only; no historical timing or large-road claims."""
from dataclasses import replace
from fractions import Fraction as R
from itertools import product
import hashlib
import inspect
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from timecut5.bounded import _solve_problem
from timecut5.coalesced_solver import (table_free_problem,
    solve_bounded_table_free, solve_hierarchical_table_free)
from timecut5.coalesce import CoalescedDispatch, VERSION
from timecut5.hierarchy import build_regions
from timecut5.real_adapter import TableFreeRealProblem, site_catalog_digest
from timecut5.real_legs import RealSite
from timecut5.road_provider import TableFreeRoadSelectedLegProvider, TableFreeRegionBoundProvider
from timecut5.sparse_seed import SparseSeedCatalog, replay_sparse_seed
from timecut5.probe import Interval, State
from timecut5.probe import Cut, Event, Witness
from timecut5.pwa import CutPiece
from timecut5.live_replay import ExactLayerReplay, LayerCheckpointStop


def seed(domain, slope=R(1), intercept=R(30), chi=True):
    state = State('x', 1, 0)
    def point(energy):
        if not domain.contains(energy):
            raise AssertionError('Escaped original parent guard')
        tau = slope * energy + intercept
        def approach(epsilon):
            time = tau if chi else tau + epsilon / 2
            return Witness(time, energy, R(0), (), state,
                           (Event('analytic', 'parent', time, time, energy, energy),))
        return Cut(tau, chi, energy, R(0), (), state, approach)
    return CutPiece(domain, slope, intercept, chi, R(0), (), state, point)


def equivalent(test, before, after):
    # Every endpoint and intervening open cell, using symbolic affine metadata.
    knots = sorted({x for p in (*before, *after) for x in (p.domain.lo, p.domain.hi)})
    energies = knots + [(a+b)/2 for a, b in zip(knots, knots[1:])]
    for energy in energies:
        signature = lambda pieces: {(p.slope, p.intercept, p.chi, p.rho, p.pi, p.state)
                                    for p in pieces if p.domain.contains(energy)}
        test.assertEqual(signature(before), signature(after))
        for piece in after:
            if piece.domain.contains(energy):
                for epsilon in (R(1), R(1, 10**30)):
                    cut = piece.at(energy)
                    witness = cut.approach(epsilon)
                    test.assertEqual(witness.energy, energy)
                    test.assertGreaterEqual(witness.time, cut.tau)
                    test.assertLess(witness.time, cut.tau + epsilon)


class LineRouter:
    """Independent hand-calculated native labels for O -> A -> D."""
    provenance = {'source_sha256': 'a' * 64}
    def __init__(self, time_scale=1):
        self.time_scale = time_scale

    def full_edges(self, source):
        distances = np.array([float(i-source) if i >= source else np.inf for i in range(3)])
        parents = np.array([i-1 if i > source else -1 for i in range(3)])
        return distances * self.time_scale, distances.copy(), parents, parents.copy()


class TestTableFreeCoalescing(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.nodes = Path(self.directory.name) / 'nodes'
        self.edges = Path(self.directory.name) / 'edges'
        self.nodes.write_bytes(b'tiny O A D nodes')
        self.edges.write_bytes(b'tiny O A D edges')
        self.graph = SimpleNamespace(node_count=3, edge_count=2,
            source=np.array([0, 1]), target=np.array([1, 2]),
            weights={'travel_time': np.array([1., 1.]), 'distance': np.array([1., 1.])})
        self.sites = {sid: RealSite(sid, 'A', ('C',)) for sid in ('a', 'z')}
        self.query = dict(H_ref=2, start_time_s=0, initial_energy_kwh=1,
            capacity_kwh=4, minimum_energy_kwh=0, reserve_kwh=0,
            consumption_kwh_per_m=1, overhead_s=1, lambda_stop_s=0,
            schedule=None, charging_segments=[[0, 2, 1, 0], [2, 4, 2, -2]])

    def provider(self):
        anchors = {'O': 0, 'A': 1, 'D': 2}
        digest = hashlib.sha256(json.dumps(anchors, sort_keys=True,
            separators=(',', ':')).encode()).hexdigest()
        return TableFreeRoadSelectedLegProvider(self.graph, LineRouter(self.graph.weights['travel_time'][0]), anchors,
            nodes_sha256=hashlib.sha256(self.nodes.read_bytes()).hexdigest(),
            edges_sha256=hashlib.sha256(self.edges.read_bytes()).hexdigest(),
            router_sha256='a' * 64, anchor_catalog_sha256=digest)

    def binding(self):
        return dict(origin_anchor='O', destination_anchor='D',
                    site_catalog_sha256=site_catalog_digest(self.sites))

    def replay(self, witness, search_provider):
        provider = self.provider()
        self.assertIsNot(provider, search_provider)
        self.assertFalse(provider.legs)
        catalog = SparseSeedCatalog(provider, self.sites, **self.binding(),
            nodes_path=self.nodes, edges_path=self.edges, hierarchy_sha256='e' * 64,
            candidate_sha256=hashlib.sha256(json.dumps(sorted(self.sites),
                separators=(',', ':')).encode()).hexdigest())
        query = dict(self.query, origin='O', destination='D',
            sparse_domain_sha256=catalog.domain_sha256, hierarchy_sha256='e' * 64)
        charges = tuple(e.departure_energy-e.arrival_energy for e in witness.events
                        if e.effect in ('C', 'CS'))
        return replay_sparse_seed(query, catalog, witness.pi, charges)['lex_key']

    def matrix(self, expected_status, component=None):
        signatures = []
        for hier, coalescing, dominance in product((False, True), repeat=3):
            with self.subTest(hier=hier, coalescing=coalescing, dominance=dominance):
                provider = self.provider()
                args = (self.query, self.sites, provider)
                solver = solve_hierarchical_table_free if hier else solve_bounded_table_free
                if hier:
                    args += (build_regions(self.sites),)
                outcome = solver(*args, **self.binding(), coalescing=coalescing,
                                 dominance=dominance)
                bounded = outcome.inner.bounded if hier else outcome.inner
                result = bounded.result
                signatures.append((result.status, result.primary_infimum,
                    result.secondary_infimum, result.unattained_component, result.key))
                self.assertEqual(result.status, expected_status)
                self.assertEqual(result.unattained_component, component)
                self.assertEqual(outcome.canonical().get('representation_version'),
                                 VERSION if coalescing else None)
                self.assertEqual(outcome.statistics.calls > 0, coalescing)
                self.assertLessEqual(outcome.statistics.output_pieces, outcome.statistics.input_pieces)
                if hier:
                    self.assertEqual((outcome.inner.missing_actions, outcome.inner.duplicate_actions), (0, 0))
                if result.witness:
                    self.assertEqual(self.replay(result.witness, provider), result.key)
                else:
                    self.assertIsNone(result.key)
        self.assertTrue(all(value == signatures[0] for value in signatures))
        return signatures[0]

    def test_attained_full_key_and_equal_primary_action_tie(self):
        result = self.matrix('attained_optimum')
        self.assertEqual(result[-1], (R(4), R(1), 1, (('a', 'C'),)))

    def test_primary_unattained_strict_charge(self):
        self.sites = {'a': RealSite('a', 'A', ('CS',))}
        self.query.update(initial_energy_kwh=2, schedule=dict(a=0, b=20, D=0))
        result = self.matrix('infimum_unattained', 'J')
        self.assertEqual(result[1], 3)

    def test_secondary_unattained_schedule_plateau(self):
        self.sites = {'a': RealSite('a', 'A', ('CS',))}
        self.query.update(initial_energy_kwh=2, schedule=dict(a=10, b=20, D=1))
        result = self.matrix('infimum_unattained', 'Q')
        self.assertEqual(result[1:3], (R(12), R(0)))

    def test_attained_plateau_minimizes_secondary_charge(self):
        self.sites = {sid: RealSite(sid, 'A', ('CS',)) for sid in ('a', 'z')}
        self.query.update(schedule=dict(a=10, b=20, D=1))
        result = self.matrix('attained_optimum')
        self.assertEqual(result[-1], (R(12), R(1), 1, (('a', 'CS'),)))

    def test_infeasible_is_not_an_unattained_result(self):
        self.query.update(initial_energy_kwh=0)
        self.matrix('infeasible')

    def test_defaults_do_not_invoke_coalescing_and_preserve_adapter(self):
        for function in (table_free_problem, solve_bounded_table_free, solve_hierarchical_table_free):
            self.assertIs(inspect.signature(function).parameters['coalescing'].default, False)
        with patch('timecut5.coalesced_solver.coalesce_pieces', side_effect=AssertionError('enabled')):
            problem = table_free_problem(self.query, self.sites, self.provider(), **self.binding())
            self.assertIs(type(problem), TableFreeRealProblem)
            expected = _solve_problem(problem).result.key
            actual = solve_bounded_table_free(self.query, self.sites, self.provider(), **self.binding())
            self.assertEqual(actual.inner.result.key, expected)
        with self.assertRaises(TypeError):
            table_free_problem(self.query, self.sites, self.provider(), **self.binding(), coalescing=1)

    def test_exact_guarded_domains_through_table_free_adapter(self):
        problem = table_free_problem(self.query, self.sites, self.provider(),
                                    **self.binding(), coalescing=True)
        for right, left in product((False, True), repeat=2):
            original = (seed(Interval(0, 1, True, right)), seed(Interval(1, 2, left, True)))
            merged = problem.compact(original)
            self.assertEqual(len(merged), 1 if right or left else 2)
            equivalent(self, original, merged)
        original = (seed(Interval(0, 1, False, False), chi=False),
                    seed(Interval(1, 2), chi=False))
        merged = problem.compact(original)
        self.assertIsInstance(merged[0]._point, CoalescedDispatch)
        self.assertIs(merged[0]._point.select(R(1)).piece, original[1])
        with self.assertRaises(ValueError):
            merged[0].at(R(0))
        equivalent(self, original, merged)
        for change in (dict(rho=R(1)), dict(pi=(('a', 'C'),), state=State('x', 1, 1)), dict(chi=True),
                       dict(slope=R(2)), dict(intercept=R(31)),
                       dict(state=State('different', 1, 0))):
            changed = replace(original[1], **change)
            self.assertEqual(len(problem.compact((original[0], changed))), 2)

    def test_known_lineage_is_rejected_before_physical_transition(self):
        problem = table_free_problem(self.query, self.sites, self.provider(),
                                    **self.binding(), coalescing=True)
        piece = problem.initial_piece()
        object.__setattr__(piece, '_family', object())
        with self.assertRaisesRegex(ValueError, 'before processing'):
            problem.advance((piece,), 'a', 'C')
        self.assertFalse(problem.provider.legs)

    def test_checkpoint_resume_and_independent_incumbent_replay(self):
        external = {name: 'b' * 64 for name in
            ('graph_nodes', 'graph_edges', 'router', 'anchors', 'sites', 'query',
             'hierarchy', 'landmark', 'seed', 'policy', 'runtime')}
        for hier, coalescing in product((False, True), repeat=2):
            mode = 'hier' if hier else 'flat'
            saved = []
            def solve(hook):
                provider = self.provider()
                def save(witness, key):
                    # A callback can atomically persist only the replayed plan.
                    self.assertEqual(self.replay(witness, provider), key)
                    saved.append((witness, key))
                solver = solve_hierarchical_table_free if hier else solve_bounded_table_free
                args = (self.query, self.sites, provider)
                if hier:
                    args += (build_regions(self.sites),)
                return solver(*args, **self.binding(), coalescing=coalescing,
                              checkpoint_hook=hook, incumbent_hook=save)
            original = solve(None)
            saved.clear()
            stopped = ExactLayerReplay(mode=mode, domain_sha256='d' * 64,
                external_source_sha256=external, stop_after_depth=1)
            with self.assertRaises(LayerCheckpointStop) as interrupted:
                solve(stopped)
            self.assertTrue(saved, 'Budget stop must retain a replayable incumbent')
            restored = ExactLayerReplay(mode=mode, domain_sha256='d' * 64,
                external_source_sha256=external,
                previous_checkpoint=interrupted.exception.checkpoint_bytes)
            resumed = solve(restored)
            self.assertEqual(restored.replayed_restore_layers, 2)
            self.assertEqual(original.canonical(), resumed.canonical())
            self.assertEqual(min(key for _, key in saved), (R(4), R(1), 1, (('a', 'C'),)))

    def test_cropped_physical_parents_replay_after_coalescing(self):
        problem = table_free_problem(self.query, self.sites, self.provider(),
                                    **self.binding(), coalescing=True)
        first = problem.advance((problem.initial_piece(),), 'a', 'C')
        splits = []
        for piece in first:
            for window in (Interval(0, 1, False, False), Interval(1, 1),
                           Interval(1, 4, False, True)):
                domain = piece.domain.intersect(window)
                if domain is not None:
                    splits.append(replace(piece, domain=domain))
        merged = problem.compact(splits)
        self.assertLess(len(merged), len(splits))
        for piece in problem.finish(merged):
            for energy in (piece.domain.lo, (piece.domain.lo+piece.domain.hi)/2, piece.domain.hi):
                if piece.domain.contains(energy):
                    witness = piece.at(energy).approach(R(1, 10**12))
                    self.replay(witness, problem.provider)
                    first_charge = next(event for event in witness.events if event.effect == 'C')
                    self.assertTrue(any(p.domain.contains(first_charge.departure_energy) for p in splits))

    def test_combined_bound_hooks_with_strictly_positive_onward_alt(self):
        self.graph.weights['travel_time'][:] = 2
        class ConservativeLineRouter:
            provenance = {'source_sha256': 'f' * 64}
            def full(self, root, reverse=False):
                assert root == 0
                values = np.array([0., np.inf, np.inf] if reverse else [0., 1., 2.])
                return values, values.copy(), np.array([-1, -1, -1])
            def close(self):
                pass
        for hier, coalescing, dominance, onward in product((False, True), repeat=4):
            with self.subTest(hier=hier, coalescing=coalescing, dominance=dominance, onward=onward):
                provider = self.provider()
                root = build_regions(self.sites)
                bounds = TableFreeRegionBoundProvider(provider, self.sites, root,
                    destination_anchor='D', landmark_anchor='O',
                    site_catalog_sha256=site_catalog_digest(self.sites),
                    router_factory=lambda _: ConservativeLineRouter(), onward_alt=onward)
                captured = []
                def incumbent(witness, key):
                    self.assertEqual(self.replay(witness, provider), key)
                    captured.append(key)
                options = dict(self.binding(), dominance=dominance, coalescing=coalescing,
                               verified_primary_upper=R(6), incumbent_hook=incumbent)
                if hier:
                    output = solve_hierarchical_table_free(self.query, self.sites, provider,
                        root, **options, bound_provider=bounds).inner.bounded
                else:
                    output = solve_bounded_table_free(self.query, self.sites, provider,
                        **options, singleton_bound=bounds.singleton_bound).inner
                self.assertEqual(output.result.key, (R(6), R(1), 1, (('a', 'C'),)))
                self.assertTrue(captured)
                self.assertEqual(bounds.online_internal_member_accesses, 0)
