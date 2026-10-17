"""Synthetic certified onward ALT; unittest assertions also execute under -OO."""
from dataclasses import replace
from fractions import Fraction as R
from pathlib import Path
import itertools
import math
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_alt_strategy import context, ReadSpy
from fixture_source import Router
from timecut5.bounded import _solve_problem
from timecut5.deployable import LandmarkDistances
from timecut5.hierarchy import Region, _solve_hierarchical_problem
from timecut5.real_adapter import site_catalog_digest
from timecut5.road_provider import TableFreeRegionBoundProvider


def enabled(strategy='indexed', *, collect=False, empty=False, onward=True):
    p, old, root = context(strategy, collect=collect, empty=empty)
    b = TableFreeRegionBoundProvider(old.leg_provider, old.sites, root,
        destination_anchor='D', landmark_anchor='A',
        site_catalog_sha256=site_catalog_digest(old.sites), router_factory=Router,
        alt_strategy=strategy, collect_alt_member_reads=collect, onward_alt=onward)
    return p, b, root


class OnwardALTTests(unittest.TestCase):
    def test_default_is_unchanged_and_option_is_explicit_boolean(self):
        p, old, root = context()
        _, off, other = enabled(onward=False)
        self.assertFalse(old.onward_alt)
        self.assertEqual(old._onward_summary, {})
        for rid, r in old._regions.items():
            for effect in ('C', 'S', 'CS'):
                self.assertEqual(old.bound(p, (p.initial_piece(),), r, effect),
                                 off.bound(p, (p.initial_piece(),), off._regions[rid], effect))
        with self.assertRaisesRegex(ValueError, 'boolean'):
            enabled(onward=1)

    def test_directed_singletons_same_anchor_aliases_and_nonfinite_terms(self):
        for strategy in ('indexed', 'recompute'):
            p, b, _ = enabled(strategy)
            d = b.landmarks[0]
            # A->B conservative 2, B->D 3; the reverse potential gives B->D=3.
            self.assertEqual(b._onward_from_extrema(d.from_landmark['B'], d.to_landmark['B']), 3)
            self.assertEqual(b._onward_from_extrema(d.from_landmark['D'], d.to_landmark['D']), 0)
            self.assertEqual(b._onward_from_extrema(math.inf, math.inf), 0)
            self.assertEqual(b._onward_from_extrema(math.inf, 10), 6)
            self.assertEqual(b._onward_from_extrema(2, math.inf), 3)
            piece = replace(p.initial_piece(), state=replace(p.initial_piece().state, anchor='B'))
            self.assertEqual(b.singleton_bound(p, (piece,), 'b', 'C'),
                             b.singleton_bound(p, (piece,), 'alias', 'C'))
            self.assertEqual(b.singleton_bound(p, (piece,), 'b', 'C'),
                             p.overhead + p.penalty + 3)

    def test_stronger_after_service_wait_and_independent_region_minima(self):
        p, b, root = enabled()
        _, old, _ = context()
        for effect in ('C', 'S', 'CS'):
            p.schedule = (R(50), R(100), R(7))
            piece = p.initial_piece()
            self.assertEqual(b.singleton_bound(p, (piece,), 'b', effect),
                             old.singleton_bound(p, (piece,), 'b', effect) + 3)
        # Complete root includes destination and unreachable Sites: zero remains safe.
        self.assertEqual(b._outgoing(root), 0)
        for effect in ('S', 'CS'):
            piece = replace(p.initial_piece(), state=replace(p.initial_piece().state, remaining_schedule=0))
            self.assertIsNone(b.singleton_bound(p, (piece,), 'b', effect))

    def test_indexed_recomputed_equivalent_and_member_count_is_four_passes(self):
        p, indexed, root = enabled(collect=True)
        _, scan, _ = enabled('recompute', collect=True)
        self.assertEqual(scan._onward_summary, {})
        for rid, region in indexed._regions.items():
            for effect in ('C', 'S', 'CS'):
                self.assertEqual(indexed.bound(p, (p.initial_piece(),), region, effect),
                                 scan.bound(p, (p.initial_piece(),), scan._regions[rid], effect))
        _, counted, r = enabled('recompute', collect=True)
        counted.bound(p, (p.initial_piece(),), r, 'C')
        self.assertEqual(counted.alt_member_reads, 4 * len(r.members))
        self.assertEqual(indexed.alt_member_reads, 0)

    def test_indexed_online_no_members_recompute_no_setup_summary(self):
        p, b, root = enabled()
        d = b.landmarks[0]
        f, t = ReadSpy(d.from_landmark), ReadSpy(d.to_landmark)
        f.reads = t.reads = 0
        with patch('timecut5.road_landmark.certify_integer_landmark',
                   return_value=(LandmarkDistances(f, t), b.landmark_certificate)):
            _, scan, r = enabled('recompute')
        self.assertEqual((f.reads, t.reads), (0, 0))
        scan._outgoing(r)
        self.assertEqual((f.reads, t.reads), (len(r.members)+1, len(r.members)+1))
        # For indexed, only destination lookups occur online.
        b.landmarks = (LandmarkDistances(f, t),)
        f.reads = t.reads = 0
        b._outgoing(root)
        self.assertEqual((f.reads, t.reads), (1, 1))

    def test_empty_invalid_identity_and_source_binding_fail_closed(self):
        for strategy in ('indexed', 'recompute'):
            p, b, r = enabled(strategy, empty=True)
            self.assertEqual(b.bound(p, (p.initial_piece(),), r, 'C'), (None, 0))
            self.assertEqual(b.bound(p, (), r, 'C'), (None, 0))
            with self.assertRaises(KeyError):
                b._outgoing(r)
            p, b, r = enabled(strategy)
            with self.assertRaisesRegex(ValueError, 'Region identity'):
                b._outgoing(Region(r.identifier, r.members))
            for field, bad in [('destination', 'B'), ('site_catalog_sha256', '0'*64)]:
                prior = getattr(p, field)
                setattr(p, field, bad)
                with self.assertRaisesRegex(ValueError, 'binding'):
                    b.singleton_bound(p, (p.initial_piece(),), 'b', 'C')
                setattr(p, field, prior)
            p.provider.source_sha256['edges'] = '0'*64
            with self.assertRaisesRegex(ValueError, 'binding'):
                b.bound(p, (p.initial_piece(),), r, 'C')

    def test_all_short_anchor_walks_are_lower_bounded_even_with_intermediate_sites(self):
        p, b, root = enabled()
        d = b.landmarks[0]
        anchors = tuple(p.provider.anchor_nodes)
        for source in anchors:
            lower = b._onward_from_extrema(d.from_landmark[source], d.to_landmark[source])
            for count in range(3):
                for middle in itertools.product(anchors, repeat=count):
                    walk = (source, *middle, 'D')
                    legs = [p.provider.leg(a, z) for a, z in zip(walk, walk[1:])]
                    if all(leg.reachable for leg in legs):
                        self.assertLessEqual(lower, sum(leg.time for leg in legs))

    def test_failed_outgoing_recompute_invalidates_member_counter(self):
        _, b, root = enabled('recompute', collect=True)
        distance = b.landmarks[0]
        class FailingReads(dict):
            def __getitem__(self, key):
                if key == 'U':
                    raise RuntimeError('partial outgoing read')
                return super().__getitem__(key)
        b.landmarks = (LandmarkDistances(FailingReads(distance.from_landmark),
                                        distance.to_landmark),)
        with self.assertRaisesRegex(RuntimeError, 'partial outgoing'):
            b._outgoing(root)
        self.assertIsNone(b.alt_member_reads)

    def test_nonmetric_selected_lengths_and_fractional_times(self):
        import numpy as np
        from types import SimpleNamespace
        from fixture_source import sha, canonical
        from timecut5.real_legs import RealSite
        from timecut5.road_provider import TableFreeRoadSelectedLegProvider
        # B->D fastest leg is long; B->C->D is slower but much shorter.
        anchors = dict(A=0, B=1, C=2, D=3)
        edges = [(0,1,2.25,1.), (1,3,1.25,100.), (1,2,.75,1.),
                 (2,3,.75,1.), (3,0,2.25,1.)]
        g = SimpleNamespace(node_count=4, edge_count=len(edges),
            source=np.array([x[0] for x in edges]), target=np.array([x[1] for x in edges]),
            weights={name: np.array([x[i] for x in edges])
                     for name, i in [('travel_time',2), ('distance',3)]})
        router = Router(g)
        legs = TableFreeRoadSelectedLegProvider(g, router, anchors,
            nodes_sha256='a'*64, edges_sha256='b'*64,
            router_sha256=router.provenance['source_sha256'], anchor_catalog_sha256=sha(canonical(anchors)))
        sites = {'b': RealSite('b', 'B', ('C',))}
        root = Region(0, ('b',))
        b = TableFreeRegionBoundProvider(legs, sites, root, destination_anchor='D', landmark_anchor='A',
            site_catalog_sha256=site_catalog_digest(sites), router_factory=Router, onward_alt=True)
        direct, first, second = (legs.leg(a, z) for a,z in [('B','D'), ('B','C'), ('C','D')])
        self.assertGreater(direct.actual_length, first.actual_length + second.actual_length)
        self.assertLess(direct.time, first.time + second.time)
        self.assertLessEqual(b._outgoing(root), direct.time)
        self.assertLessEqual(b._outgoing(root), first.time + second.time)

    def test_sub_ulp_native_accumulation_is_not_assumed_exact(self):
        import numpy as np
        from types import SimpleNamespace
        from fixture_source import sha, canonical
        from timecut5.real_legs import RealSite
        from timecut5.road_provider import TableFreeRoadSelectedLegProvider
        anchors = dict(A=0, B=1, C=2, D=3)
        weights = np.array([float(2**52), .5, .5])
        g = SimpleNamespace(node_count=4, edge_count=3,
            source=np.array([0,1,2]), target=np.array([1,2,3]),
            weights={'travel_time': weights, 'distance': np.ones(3)})
        router = Router(g)
        legs = TableFreeRoadSelectedLegProvider(g, router, anchors,
            nodes_sha256='a'*64, edges_sha256='b'*64,
            router_sha256=router.provenance['source_sha256'], anchor_catalog_sha256=sha(canonical(anchors)))
        sites = {'a': RealSite('a', 'A', ('C',))}
        root = Region(0, ('a',))
        b = TableFreeRegionBoundProvider(legs, sites, root, destination_anchor='D', landmark_anchor='A',
            site_catalog_sha256=site_catalog_digest(sites), router_factory=Router, onward_alt=True)
        native = legs.leg('A', 'D').time
        exact_edges = sum(R(float(w)) for w in weights)
        self.assertLess(native, exact_edges)  # Two half-ULP increments disappeared.
        self.assertEqual(b._outgoing(root), R(2**52 - 1))
        self.assertLessEqual(b._outgoing(root), native)
        # A split into selected legs starts each native accumulation afresh.
        self.assertLessEqual(b._outgoing(root), legs.leg('A','B').time + legs.leg('B','D').time)

    def test_equal_primary_bounds_remain_live_in_both_engines(self):
        # A proven global optimum is a valid (possibly tight) candidate lower
        # bound. Inject equality at the provider boundary to test strict >.
        p, b, root = enabled()
        optimum = _solve_problem(p, singleton_bound=b.singleton_bound).result.key[0]
        for mode in ('flat', 'hier'):
            p, b, root = enabled()
            seen = []
            advance = p.advance
            def observed(*args):
                seen.append(args[1:])
                return advance(*args)
            p.advance = observed
            if mode == 'flat':
                result = _solve_problem(p, verified_primary_upper=optimum,
                    singleton_bound=lambda *args: optimum)
            else:
                original = b.bound
                def equal_bound(*args):
                    value, scans = original(*args)
                    return (None if value is None else optimum), scans
                b.bound = equal_bound
                hierarchical = _solve_hierarchical_problem(p, True, root,
                    bound_provider=b, verified_primary_upper=optimum)
                self.assertGreater(hierarchical.equality_nodes_retained, 0)
                result = hierarchical.bounded
            self.assertTrue(seen)
            self.assertEqual(result.result.key[0], optimum)

    def test_flat_hier_results_identical_for_both_strategies_and_toggle(self):
        keys = []
        for strategy, onward, mode in itertools.product(('indexed', 'recompute'), (False, True), ('flat', 'hier')):
            p, b, root = enabled(strategy, onward=onward)
            result = (_solve_problem(p, singleton_bound=b.singleton_bound) if mode == 'flat'
                      else _solve_hierarchical_problem(p, True, root, bound_provider=b).bounded)
            keys.append(result.result.key)
        self.assertTrue(all(key == keys[0] for key in keys))


if __name__ == '__main__':
    unittest.main()
