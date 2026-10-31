"""Exact road-provider contract checks; no whole-real-graph path enumeration."""
from fractions import Fraction
import itertools
import random
import unittest

from hiroute.exact.road_index import FrozenLegProvider, IndexedLeg, RoadIndex, NativeRoadIndex


def row(a, b, time, length, identity):
    return dict(source=a, target=b, time_s=str(time), length_m=str(length), edge_id=identity)


def independent_paths(edges, source, target):
    """Finite simple-path oracle only for these tiny test graphs."""
    def visit(node, seen, path):
        if node == target:
            yield path
            return
        for edge in edges:
            if edge["source"] == node and edge["target"] not in seen:
                yield from visit(edge["target"], seen | {edge["target"]}, path + (edge,))
    paths = list(visit(source, {source}, ()))
    if not paths:
        return None
    path = min(paths, key=lambda p: (sum(Fraction(e["time_s"]) for e in p),
                                    (source,) + tuple(e["target"] for e in p),
                                    tuple(e["edge_id"] for e in p)))
    return path


class RoadIndexTests(unittest.TestCase):
    def test_node_then_edge_tie_actual_length_and_directed_relaxation(self):
        edges = [row("o", "z", 2, 1, "direct"),
                 row("o", "a", 1, 100, "parallel-z"),
                 row("o", "a", 1, 200, "parallel-a"),
                 row("a", "z", 1, 100, "end")]
        index = RoadIndex(edges)
        leg = index.selected_leg("o", "z")
        self.assertEqual(tuple(e["edge_id"] for e in leg.edges), ("parallel-a", "end"))
        self.assertEqual(leg.time_s, 2)
        self.assertEqual(leg.length_m, 300)
        self.assertEqual(index.lower_bound("o", "z", "length_m"), 1)
        self.assertIsNone(index.selected_leg("z", "o"))
        self.assertIsNone(index.lower_bound("z", "o", "length_m"))
        self.assertEqual(index.selected_leg("z", "z").time_s, 0)
        self.assertEqual(index.distances_from("o", "time_s")["z"], 2)
        with self.assertRaises(TypeError):
            index.distances_to("z")["o"] = Fraction(99)

    def test_index_matches_independent_tiny_path_oracle(self):
        rng = random.Random(1107)
        nodes = ("a", "b", "c", "d", "e")
        for trial in range(12):
            edges = [row(a, b, rng.randint(1, 4), rng.randint(1, 8), f"{trial}:{a}:{b}")
                     for a, b in itertools.permutations(nodes, 2) if rng.random() < .4]
            index = RoadIndex(edges, distance_cache_size=2, leg_cache_size=3)
            for a, b in itertools.product(nodes, repeat=2):
                expected = independent_paths(edges, a, b)
                actual = index.selected_leg(a, b)
                if expected is None:
                    self.assertIsNone(actual)
                else:
                    self.assertEqual(tuple(e["edge_id"] for e in actual.edges),
                                     tuple(e["edge_id"] for e in expected))
                    self.assertEqual(actual.length_m, sum(Fraction(e["length_m"]) for e in expected))
            self.assertLessEqual(index.metrics()["distance_cache_entries"], 2)
            self.assertLessEqual(index.metrics()["leg_cache_entries"], 3)
            self.assertEqual(index.metrics()["index_builds"], 1)

    def test_reverse_tree_early_stop_resume_and_cache_eviction(self):
        index = RoadIndex([row(str(i), str(i + 1), 1, 2, str(i)) for i in range(30)],
                          distance_cache_size=1, leg_cache_size=0)
        self.assertEqual(index.selected_leg("28", "30").time_s, 2)
        first = index.metrics()["scalar_settled_vertices"]
        self.assertLess(first, 31)
        self.assertEqual(index.selected_leg("0", "30").time_s, 30)
        self.assertEqual(index.metrics()["scalar_settled_vertices"], 31)
        self.assertEqual(index.distances_to("30")["0"], 30)
        self.assertEqual(index.distances_from("0", "length_m")["30"], 60)
        self.assertEqual(index.selected_leg("0", "30").time_s, 30)
        self.assertEqual(index.metrics()["distance_cache_entries"], 1)

    def test_input_validation_and_deadline_callback(self):
        for edges in ([row("a", "b", 0, 1, "x")],
                      [row("a", "b", 1, -1, "x")],
                      [row("a", "b", 1, 1, "x"), row("b", "a", 1, 1, "x")],
                      [row("", "b", 1, 1, "x")]):
            with self.assertRaises(ValueError):
                RoadIndex(edges)
        with self.assertRaises(ValueError):
            RoadIndex([], distance_cache_size=-1)
        index = RoadIndex([row("a", "b", 1, 1, "x")])
        with self.assertRaises(ValueError):
            index.distances_to("b", "energy")
        class Stop(Exception):
            pass
        def check():
            raise Stop
        index.check = check
        with self.assertRaises(Stop):
            index.selected_leg("a", "b")

    def test_frozen_pairs_are_not_rerouted_as_a_graph(self):
        ab = IndexedLeg("a", "b", Fraction(2), Fraction(5), ())
        bc = IndexedLeg("b", "c", Fraction(3), Fraction(7), ())
        provider = FrozenLegProvider({("a", "b"): ab, ("b", "c"): bc})
        self.assertEqual(provider.selected_leg("a", "b").length_m, 5)
        self.assertIsNone(provider.selected_leg("a", "c"))
        self.assertEqual(provider.lower_bound("a", "c", "length_m"), 0)
        self.assertEqual(provider.distances_to("c")["a"], 0)
        with self.assertRaises(ValueError):
            FrozenLegProvider({("a", "b"): ab}, relaxations={("a", "b", "time_s"): -1})
        with self.assertRaises(ValueError):
            FrozenLegProvider({("b", "a"): ab})
        bad = IndexedLeg("a", "b", Fraction(2), Fraction(5), (row("a", "b", 2, 6, "x"),))
        with self.assertRaises(ValueError):
            FrozenLegProvider({("a", "b"): bad})


class NativeRoadIndexTests(unittest.TestCase):
    """Run when the optional native compiler/header dependency is available.

    This is a normal passing test on minimal installations, while native-capable
    CI and the real pilot execute the exact same assertions below.
    """
    def test_native_contract_when_dependency_available(self):
        import os
        from pathlib import Path
        import shutil
        import tempfile
        compiler = shutil.which('c++') or shutil.which('g++')
        header_roots = [Path('/usr/include'), Path('/usr/local/include'), Path('/opt/homebrew/include')]
        header_roots += [Path(p) for p in os.environ.get('CPLUS_INCLUDE_PATH', '').split(os.pathsep) if p]
        if compiler is None or not any((p / 'boost/multiprecision/cpp_int.hpp').exists() for p in header_roots):
            return
        rng = random.Random(421)
        nodes = ('a', 'b', 'c', 'd', 'e', 'f', 'g')
        edges = [row(a, b, str(Fraction(rng.randint(1, 10), rng.choice((3, 7, 125000000000000000)))),
                     str(Fraction(rng.randint(1, 50), rng.choice((5, 11, 34375000000000000000)))),
                     f'{a}:{b}') for a, b in itertools.permutations(nodes, 2) if rng.random() < .5]
        # Force a node/parallel-edge tie where actual length must not decide.
        edges += [row('o', 'z', 2, 1, 'direct'), row('o', 'a', 1, 200, 'pa'),
                  row('o', 'a', 1, 100, 'pz'), row('a', 'z', 1, 100, 'end')]
        nodes += ('o', 'z')
        reference = RoadIndex(edges)
        with tempfile.TemporaryDirectory() as work:
            tsv = Path(work) / 'graph.tsv'
            tsv.write_text(''.join('\t'.join(str(e[k]) for k in
                ('source', 'target', 'edge_id', 'time_s', 'length_m')) + '\n' for e in edges))
            with NativeRoadIndex(tsv, nodes, cache_directory=work, distance_cache_size=2, leg_cache_size=3) as native:
                for a, b in itertools.product(nodes, repeat=2):
                    expected, actual = reference.selected_leg(a, b), native.selected_leg(a, b)
                    if expected is None:
                        self.assertIsNone(actual)
                    else:
                        self.assertEqual(actual.time_s, expected.time_s)
                        self.assertEqual(actual.length_m, expected.length_m)
                        self.assertEqual(tuple(e['edge_id'] for e in actual.edges),
                                         tuple(e['edge_id'] for e in expected.edges))
                for anchor in nodes:
                    for weight in ('time_s', 'length_m'):
                        self.assertEqual(dict(native.distances_to(anchor, weight)),
                                         {k: v for k, v in reference.distances_to(anchor, weight).items() if k in nodes})
                        self.assertEqual(dict(native.distances_from(anchor, weight)),
                                         {k: v for k, v in reference.distances_from(anchor, weight).items() if k in nodes})
                self.assertEqual(native.metrics()['backend'], 'exact_integer_scaled_cpp')
                self.assertEqual(native.metrics()['index_builds'], 1)
                self.assertLessEqual(native.metrics()['distance_cache_entries'], 2)
                class Stop(Exception):
                    pass
                def check():
                    raise Stop
                native.check = check
                with self.assertRaises(Stop):
                    native.distances_to('z')
                native.check = None
            with self.assertRaises(ValueError):
                native.selected_leg('a', 'z')
            duplicate = Path(work) / 'duplicate.tsv'
            duplicate.write_text('a\tb\tx\t1\t2\nb\tc\tx\t2\t3\n')
            with self.assertRaisesRegex(RuntimeError, 'edge IDs must be unique'):
                NativeRoadIndex(duplicate, ('a', 'b', 'c'), cache_directory=work)
            for malformed in ('010','01/2','1/02'):
                duplicate.write_text('a\tb\tx\t'+malformed+'\t2\n')
                with self.assertRaisesRegex(RuntimeError, 'positive integer or numerator/denominator'):
                    NativeRoadIndex(duplicate, ('a','b'), cache_directory=work)
            # Exercise an interruption *inside* a native search, then retry:
            # aborted scalar workspaces must not silently omit outgoing arcs.
            long_edges = [row(str(i), str(i + 1), str(Fraction(i + 1, 125000000000000000)),
                              str(Fraction(i + 7, 34375000000000000000)), str(i)) for i in range(1000)]
            long_tsv = Path(work) / 'long.tsv'
            long_tsv.write_text(''.join('\t'.join(str(e[k]) for k in
                ('source', 'target', 'edge_id', 'time_s', 'length_m')) + '\n' for e in long_edges))
            with NativeRoadIndex(long_tsv, ('0', '1000'), cache_directory=work) as large:
                calls = 0
                def interrupt():
                    nonlocal calls
                    calls += 1
                    if calls == 3:
                        raise Stop
                large.check = interrupt
                with self.assertRaises(Stop):
                    large.selected_leg('0', '1000')
                large.check = None
                actual = large.selected_leg('0', '1000')
                expected = RoadIndex(long_edges).selected_leg('0', '1000')
                self.assertEqual(actual.time_s, expected.time_s)
                self.assertEqual(actual.length_m, expected.length_m)
                self.assertEqual(tuple(e['edge_id'] for e in actual.edges),
                                 tuple(e['edge_id'] for e in expected.edges))


if __name__ == "__main__":
    unittest.main()
