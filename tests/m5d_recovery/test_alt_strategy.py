"""Synthetic-only indexed/recomputed ALT equivalence and timing isolation."""
import ast
from dataclasses import replace
from fractions import Fraction
import hashlib
import inspect
import json
from pathlib import Path
import sys
import textwrap
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixture_source import Router
from timecut5.deployable import LandmarkDistances
from timecut5.hierarchy import Region, _solve_hierarchical_problem
from timecut5.real_adapter import TableFreeRealProblem, site_catalog_digest
from timecut5.real_legs import RealSite
from timecut5.road_provider import TableFreeRegionBoundProvider, TableFreeRoadSelectedLegProvider


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def context(strategy='indexed', *, collect=False, empty=False):
    # Asymmetric core, one-way reachable U, one-way incoming V, isolated X.
    names = ('A', 'B', 'D', 'U', 'V', 'X')
    anchors = {name: i for i, name in enumerate(names)}
    edges = [(0, 1, 3.), (1, 0, 8.), (1, 2, 4.), (2, 0, 5.),
             (0, 3, 9.), (4, 0, 17.)]
    graph = SimpleNamespace(node_count=len(names), edge_count=len(edges),
        source=np.array([a for a, _, _ in edges]),
        target=np.array([b for _, b, _ in edges]),
        weights={k: np.array([w for _, _, w in edges]) for k in ('travel_time', 'distance')})
    router = Router(graph)
    legs = TableFreeRoadSelectedLegProvider(graph, router, anchors,
        nodes_sha256='a'*64, edges_sha256='b'*64,
        router_sha256=router.provenance['source_sha256'], anchor_catalog_sha256=digest(anchors),
        source_cache_max_bytes=0)
    sites = {} if empty else {
        'b': RealSite('b', 'B', ('C', 'S', 'CS')),
        'alias': RealSite('alias', 'B', ('C',)),
        'destination': RealSite('destination', 'D', ('C', 'S')),
        'u': RealSite('u', 'U', ('S',)),
        'v': RealSite('v', 'V', ('CS',)),
        'x': RealSite('x', 'X', ('C',))}
    members = tuple(sites)
    root = Region(0, ()) if empty else Region(0, members, (
        Region(1, members, (Region(2, ()), Region(3, members[:3]), Region(4, members[3:]))),))
    bound = TableFreeRegionBoundProvider(legs, sites, root,
        destination_anchor='D', landmark_anchor='A',
        site_catalog_sha256=site_catalog_digest(sites), router_factory=Router,
        alt_strategy=strategy, collect_alt_member_reads=collect)
    query = dict(H_ref=1, start_time_s=0, initial_energy_kwh=5,
        capacity_kwh=20, minimum_energy_kwh=0, reserve_kwh=1,
        consumption_kwh_per_m=1, overhead_s=1, lambda_stop_s=1,
        charging_segments=[[0, 20, 1, 0]], schedule=dict(a=0, b=100, D=2))
    if empty:
        return context(strategy, collect=collect)[0], bound, root
    problem = TableFreeRealProblem(query, sites, legs, origin_anchor='A',
        destination_anchor='D', site_catalog_sha256=site_catalog_digest(sites))
    return problem, bound, root


class ReadSpy(dict):
    def __getitem__(self, key):
        self.reads += 1
        return super().__getitem__(key)


class ALTStrategyTests(unittest.TestCase):
    def test_all_sources_regions_effects_and_masks_match(self):
        p, indexed, root = context()
        _, scan, _ = context('recompute')
        self.assertEqual(indexed.landmark_certificate, scan.landmark_certificate)
        self.assertEqual(indexed._actions, scan._actions)
        self.assertEqual(indexed._action_masks, scan._action_masks)
        self.assertEqual(indexed._member_hash, scan._member_hash)
        self.assertEqual(scan._summary, {})
        self.assertIsNone(scan.alt_member_reads)
        for rid, region in indexed._regions.items():
            other = scan._regions[rid]
            for source in p.provider.anchor_nodes:
                if region.members:
                    self.assertEqual(indexed._incoming(source, region), scan._incoming(source, other))
                else:
                    for provider, candidate in ((indexed, region), (scan, other)):
                        with self.assertRaises(KeyError):
                            provider._incoming(source, candidate)
            for remaining in (0, 1):
                for effect in ('C', 'S', 'CS'):
                    piece = p.initial_piece()
                    piece = replace(piece, state=replace(piece.state, remaining_schedule=remaining))
                    self.assertEqual(indexed.bound(p, (piece,), region, effect),
                                     scan.bound(p, (piece,), other, effect))
                    self.assertEqual(indexed.action_mask(region, effect, remaining),
                                     scan.action_mask(other, effect, remaining))
                    if not region.children:
                        self.assertEqual(indexed.leaf_actions(region, effect, remaining),
                                         scan.leaf_actions(other, effect, remaining))
            self.assertEqual(indexed.bound(p, (p.initial_piece(),), region, 'C'),
                             scan.bound(p, (p.initial_piece(),), other, 'C'))
        self.assertNotIn(('destination', 'C'), scan._action_bits)
        self.assertNotEqual(scan.action_bit(('b', 'C')), scan.action_bit(('alias', 'C')))
        for key in ('online_queries', 'online_internal_member_accesses',
                    'online_leaf_action_reads', 'online_mask_word_work'):
            self.assertEqual(getattr(indexed, key), getattr(scan, key))

    def test_directed_infinite_terms_are_skipped_independently(self):
        _, indexed, _ = context()
        _, scan, _ = context('recompute')
        # X is disconnected in both directions. Mixing X with finite members
        # makes max-to infinite, but must retain the finite forward term.
        for b in (indexed, scan):
            self.assertEqual(b._incoming('A', b._regions[4]), Fraction(8))
            self.assertEqual(b._incoming('X', b._regions[4]), Fraction(0))
            self.assertEqual(b._incoming('V', b._regions[3]), Fraction(9))

    def test_recompute_setup_never_reads_landmark_members_or_builds_summary(self):
        _, original, _ = context()
        distance = original.landmarks[0]
        forward, reverse = ReadSpy(distance.from_landmark), ReadSpy(distance.to_landmark)
        forward.reads = reverse.reads = 0
        labels = LandmarkDistances(forward, reverse)
        with patch('timecut5.road_landmark.certify_integer_landmark',
                   return_value=(labels, original.landmark_certificate)), \
             patch('timecut5.deployable.RegionLandmarkSummary',
                   side_effect=AssertionError('setup built ALT summary')):
            _, scan, root = context('recompute')
        self.assertEqual((forward.reads, reverse.reads), (0, 0))
        scan._incoming('A', root)
        self.assertEqual((forward.reads, reverse.reads), (len(root.members)+1, len(root.members)+1))
        self.assertEqual(scan._summary, {})
        # Repeating the query does not memoize the extrema.
        scan._incoming('A', root)
        self.assertEqual((forward.reads, reverse.reads), (2*(len(root.members)+1),)*2)

    def test_disabled_counter_has_no_per_read_branch_or_counter_access(self):
        _, scan, root = context('recompute')
        self.assertEqual(scan._incoming.__func__, scan._incoming_recomputed.__func__)
        tree = ast.parse(textwrap.dedent(inspect.getsource(scan._incoming_recomputed)))
        self.assertFalse(any(isinstance(n, ast.Attribute) and n.attr == 'alt_member_reads'
                             for n in ast.walk(tree)))
        generators = [n for n in ast.walk(tree) if isinstance(n, ast.GeneratorExp)]
        self.assertEqual(len(generators), 2)
        self.assertTrue(all(not g.ifs for n in generators for g in n.generators))
        scan._incoming('A', root)
        self.assertIsNone(scan.alt_member_reads)
        _, counted, counted_root = context('recompute', collect=True)
        counted._incoming('A', counted_root)
        self.assertEqual(counted.alt_member_reads, 2*len(counted_root.members))
        _, indexed, indexed_root = context(collect=True)
        indexed._incoming('A', indexed_root)
        self.assertEqual(indexed.alt_member_reads, 0)

    def test_full_result_and_traversal_equivalence(self):
        outputs = []
        for strategy in ('indexed', 'recompute'):
            p, b, root = context(strategy)
            trace = []
            advance, bound = p.advance, b.bound
            def observed_advance(pieces, site, effect):
                trace.append(('advance', tuple(x.pi for x in pieces), site, effect))
                return advance(pieces, site, effect)
            def observed_bound(problem, pieces, region, effect):
                value = bound(problem, pieces, region, effect)
                trace.append(('bound', region.identifier, effect, value))
                return value
            p.advance, b.bound = observed_advance, observed_bound
            result = _solve_hierarchical_problem(p, True, root, bound_provider=b)
            outputs.append((result, trace, p.provider.edge_witnesses,
                            p.provider.source_run_count, dict(p.provider.legs)))
        self.assertEqual(outputs[0], outputs[1])
        self.assertTrue(outputs[0][1])

    def test_empty_tree_and_invalid_identity(self):
        for mode in ('indexed', 'recompute'):
            p, b, root = context(mode, empty=True)
            self.assertEqual(b.bound(p, (p.initial_piece(),), root, 'C'), (None, 0))
            self.assertEqual(b.bound(p, (), root, 'S'), (None, 0))
            self.assertEqual(b.leaf_actions(root, 'C', 1), ())
            with self.assertRaisesRegex(ValueError, 'Region identity'):
                b.action_mask(Region(root.identifier, root.members), 'C', 1)
            _, b, root = context(mode)
            with self.assertRaisesRegex(ValueError, 'Internal Region'):
                b.leaf_actions(root, 'C', 1)
            self.assertEqual(b.online_internal_member_accesses, 1)

    def test_partial_scan_failure_invalidates_diagnostic_metric(self):
        _, counted, root = context('recompute', collect=True)
        counted._incoming('A', root)
        distance = counted.landmarks[0]
        class FailingReads(dict):
            def __getitem__(self, key):
                if key == 'U':
                    raise RuntimeError('partial scan failure')
                return super().__getitem__(key)
        counted.landmarks = (LandmarkDistances(FailingReads(distance.from_landmark),
                                               distance.to_landmark),)
        with self.assertRaisesRegex(RuntimeError, 'partial scan'):
            counted._incoming('A', root)
        self.assertIsNone(counted.alt_member_reads)
        counted.landmarks = (distance,)
        counted._incoming('A', root)
        self.assertIsNone(counted.alt_member_reads)

    def test_singleton_bounds_preserve_multieffect_schedule_rules(self):
        p, indexed, _ = context()
        _, scan, _ = context('recompute')
        for remaining in (0, 1):
            piece = p.initial_piece()
            piece = replace(piece, state=replace(piece.state, remaining_schedule=remaining))
            for site, effect in indexed._action_bits:
                self.assertEqual(indexed.singleton_bound(p, (piece,), site, effect),
                                 scan.singleton_bound(p, (piece,), site, effect))

    def test_both_strategies_reject_invalid_tree_partitions(self):
        p, b, root = context()
        invalid = (Region(0, root.members + (root.members[0],)),
                   Region(0, root.members, (Region(1, root.members[:1]),)),
                   Region(0, root.members, (Region(0, root.members),)))
        for mode in ('indexed', 'recompute'):
            for candidate in invalid:
                with self.subTest(mode=mode, candidate=candidate):
                    with self.assertRaises(ValueError):
                        TableFreeRegionBoundProvider(p.provider, b.sites, candidate,
                            destination_anchor='D', landmark_anchor='A',
                            site_catalog_sha256=site_catalog_digest(b.sites),
                            router_factory=Router, alt_strategy=mode)

    def test_invalid_options_fail_closed(self):
        with self.assertRaisesRegex(ValueError, 'ALT strategy'):
            context('scan_masks_too')
        with self.assertRaisesRegex(ValueError, 'boolean'):
            context(collect=1)


if __name__ == '__main__':
    unittest.main()
