"""Finite same-build and public-context gate; imports must come from the wheel."""
import ctypes
from fractions import Fraction
import hashlib
import inspect
import json
import math
import os
from pathlib import Path
import random
import resource
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

import numpy as np
import microplan.routing as routing
from microplan.native_artifact import build_artifact
from timecut5.routing_config import RoutingConfig, ROLES
from timecut5.road_provider import TableFreeRoadSelectedLegProvider, RoadSelectedLegProvider
from timecut5.real_adapter import TableFreeRealProblem, site_catalog_digest
from timecut5.real_legs import RealSite, ImmutableLegTable, SelectedLeg
from timecut5.sparse_seed import SparseSeedCatalog, replay_sparse_seed
from timecut5.feasible_incumbent import canonical, sha, verifier_sources, recover_feasible_incumbent
from timecut5.streaming_seed_diagnostic import StreamingSeedObserver
from timecut5.bounded import _solve_problem
from timecut5.hierarchy import _solve_hierarchical_problem, build_regions

HERE = Path(__file__).resolve().parent


def graph(n, rows):
    arrays = [np.ascontiguousarray([r[i] for r in rows], dtype=np.int64 if i < 2 else np.float64)
              for i in range(4)]
    for array in arrays:
        array.flags.writeable = False
    return SimpleNamespace(node_count=n, edge_count=len(rows), source=arrays[0], target=arrays[1],
                           weights={'travel_time': arrays[2], 'distance': arrays[3]})


def edge_path(g, source, target, labels):
    if math.isinf(float(labels[0][target])) and math.isinf(float(labels[1][target])):
        return None
    result = []
    node = target
    while node != source:
        edge, parent = int(labels[3][node]), int(labels[2][node])
        if not 0 <= edge < g.edge_count or int(g.source[edge]) != parent or int(g.target[edge]) != node:
            raise AssertionError('Invalid predecessor edge')
        result.append(edge)
        node = parent
        if len(result) > g.node_count:
            raise AssertionError('Predecessor cycle')
    return tuple(reversed(result))


class AcceptedRouter:
    def __init__(self, g, library):
        self.g, self.lib = g, library
        self.handle = library.graph_create(g.node_count, g.edge_count, g.source, g.target,
                                          g.weights['travel_time'], g.weights['distance'])
        if not self.handle:
            raise ValueError('Baseline rejected graph')

    def full_edges(self, source, reverse=False):
        n = self.g.node_count
        values = [np.empty(n, dtype=np.float64), np.empty(n, dtype=np.float64),
                  np.empty(n, dtype=np.int64), np.empty(n, dtype=np.int64)]
        self.lib.graph_full_edges(self.handle, source, reverse, *values)
        return values

    def close(self):
        self.lib.graph_free(self.handle)


class TargetRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='hiroute-target-routing-')
        cls.root = Path(cls.temp.name)
        cls.config = {'compiler': str(Path(shutil.which('g++')).resolve()),
                      'compiler_flags': ['-O3', '-std=c++17']}
        cls.artifact = build_artifact(cls.config, cls.root/'candidate-build')
        source = HERE/'accepted_routing.cpp'
        cls.baseline_binary = cls.root/'accepted.so'
        command = [cls.config['compiler'], *cls.config['compiler_flags'], '-shared', '-fPIC',
                   str(source), '-o', str(cls.baseline_binary)]
        def limited():
            resource.setrlimit(resource.RLIMIT_CPU, (20, 25))
        subprocess.run(command, check=True, timeout=30, preexec_fn=limited)
        cls.baseline = ctypes.CDLL(str(cls.baseline_binary))
        integer, pointer = ctypes.c_int64, ctypes.c_void_p
        ints = np.ctypeslib.ndpointer(dtype=np.int64, flags='C_CONTIGUOUS')
        doubles = np.ctypeslib.ndpointer(dtype=np.float64, flags='C_CONTIGUOUS')
        cls.baseline.graph_create.argtypes = [integer, integer, ints, ints, doubles, doubles]
        cls.baseline.graph_create.restype = pointer
        cls.baseline.graph_free.argtypes = [pointer]
        cls.baseline.graph_full_edges.argtypes = [pointer, integer, ctypes.c_int,
                                                 doubles, doubles, ints, ints]
        cls.counter = 0
        output = os.environ.get('HIROUTE_TARGET_TEST_EVIDENCE')
        if output:
            evidence = dict(python=sys.version, module_path=routing.__file__,
                            compiler=cls.config, baseline_command=command,
                            baseline_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                            baseline_binary_sha256=hashlib.sha256(cls.baseline_binary.read_bytes()).hexdigest(),
                            candidate_artifact=cls.artifact.receipt,
                            supported_python=sys.version_info[:2] == (3, 11),
                            real_graph_used=False)
            Path(output).write_text(json.dumps(evidence, sort_keys=True, indent=2)+'\n')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def directory(self):
        type(self).counter += 1
        return self.root/str(self.counter)

    def router(self, g, role='search', mode='full'):
        r = routing.ExactRouter(g, self.config, self.directory(), role=role, mode=mode,
                                artifact=self.artifact)
        self.addCleanup(r.close)
        return r

    def context(self, g, mode='full', role='search', anchors=None, cache_bytes=1000000):
        anchors = anchors or {str(i): i for i in range(g.node_count)}
        c = RoutingConfig(mode).create_context(
            g, self.config, self.directory(), role=role, artifact=self.artifact,
            anchor_nodes=anchors, nodes_sha256=sha(str(g.node_count).encode()),
            edges_sha256=sha(g.source.tobytes()+g.target.tobytes()+
                             g.weights['travel_time'].tobytes()+g.weights['distance'].tobytes()),
            anchor_catalog_sha256=sha(canonical(anchors)), source_cache_max_bytes=cache_bytes)
        self.addCleanup(c.close)
        return c

    def test_installed_origin_same_build_distinct_loads_and_legacy_full(self):
        # CI explicitly requires installed-wheel origin; ordinary pytest uses src.
        expected = (Path(sys.prefix) if os.environ.get('HIROUTE_REQUIRE_INSTALLED_WHEEL') == '1'
                    else Path(__file__).resolve().parents[2] / 'src')
        self.assertTrue(Path(routing.__file__).resolve().is_relative_to(expected.resolve()))
        g = graph(3, [(0, 1, 1, 1), (1, 2, 1, 1)])
        full, target = self.router(g), self.router(g, mode='destination_target')
        self.assertEqual(full.artifact['artifact_identity_sha256'], target.artifact['artifact_identity_sha256'])
        self.assertEqual(full.artifact['artifact_sha256'], target.artifact['artifact_sha256'])
        self.assertNotEqual(Path(full.lib._name), Path(target.lib._name))
        for r in (full, target):
            self.assertEqual(hashlib.sha256(Path(r.lib._name).read_bytes()).hexdigest(), r.artifact['artifact_sha256'])
        legacy = self.router(g, role=None)
        np.testing.assert_array_equal(legacy.full_edges(0)[0], [0, 1, 2])
        costs, lengths = legacy.pairs([0, 1], [2, 2], 10)
        np.testing.assert_array_equal(costs, [2, 1])
        np.testing.assert_array_equal(lengths, [2, 1])
        with self.assertRaises(ValueError):
            legacy.target_edges(0, 2)

    def test_explicit_modes_and_full_only_roles(self):
        self.assertEqual(RoutingConfig().search_mode, 'full')
        self.assertIs(inspect.signature(TableFreeRealProblem).parameters['terminal_target_routing'].default, False)
        g = graph(2, [(0, 1, 1, 1)])
        for role in ROLES:
            mode = RoutingConfig('destination_target').effective_mode(role)
            self.assertEqual(mode, 'destination_target' if role == 'search' else 'full')
            r = self.router(g, role=role, mode=mode)
            if role != 'search':
                with self.assertRaises(ValueError):
                    r.target_edges(0, 1)
                with self.assertRaises(ValueError):
                    self.router(g, role=role, mode='destination_target')
                self.assertEqual(r.target_calls, 0)
        for value in (None, True, 1, '', 'target'):
            with self.assertRaises(ValueError):
                RoutingConfig(value)
        for role in (None, True, 'foreign'):
            with self.assertRaises(ValueError):
                RoutingConfig().effective_mode(role)

    def test_same_build_exact_labels_ties_and_ordered_paths(self):
        cases = [(6, [(0, 1, 1, 4), (0, 1, 1, 4), (0, 2, 1, 2), (2, 1, 0, 2),
                       (1, 3, 0, 0), (3, 1, 0, 0), (3, 4, 1, 1)]),
                 (5, [(0, 1, 9, 1), (0, 2, 1, 1), (2, 1, 1, 0), (1, 3, 0, 0)]),
                 (6, [(0, 1, 2**53, 0), (0, 2, 2**53, 0), (1, 3, 1, 0),
                       (2, 3, 0, 0), (3, 4, math.ulp(0.), math.ulp(0.))]),
                 (4, [(0, 1, 0., -0.), (1, 2, 0., 0.), (2, 0, 0., 0.)]), (3, [])]
        rng = random.Random(8128)
        for _ in range(10):
            n = rng.randrange(2, 7)
            cases.append((n, [(rng.randrange(n), rng.randrange(n), rng.choice([0., .1, 1., 2.]),
                                rng.choice([0., .2, 1.])) for _ in range(rng.randrange(n*n))]))
        for n, rows in cases:
            for edges in (rows, list(reversed(rows))):
                g = graph(n, edges)
                expected, full, target = AcceptedRouter(g, self.baseline), self.router(g), self.router(g, mode='destination_target')
                try:
                    for source in range(n):
                        for reverse in (False, True):
                            for a, b in zip(expected.full_edges(source, reverse), full.full_edges(source, reverse)):
                                self.assertEqual(a.tobytes(), b.tobytes())
                        labels = full.full_edges(source)
                        for destination in range(n):
                            got = target.target_edges(source, destination)
                            self.assertEqual(tuple(x[destination].tobytes() for x in labels), tuple(x[destination].tobytes() for x in got))
                            self.assertEqual(edge_path(g, source, destination, labels), edge_path(g, source, destination, got))
                finally:
                    expected.close(); full.close(); target.close()

    def test_target_cache_isolation_and_complete_source_reuse(self):
        g = graph(4, [(0, 1, 1, 1), (1, 2, 1, 1), (2, 3, 1, 1)])
        p = self.context(g, 'destination_target').provider
        first = p.leg('0', '1', target_only=True)
        self.assertFalse(p._source_labels)
        self.assertEqual((p.source_run_count, p.target_run_count), (0, 1))
        self.assertIs(p.leg('0', '1'), first)
        p.leg('0', '2')
        self.assertEqual((p.source_run_count, p.target_run_count), (1, 1))
        p.leg('0', '3', target_only=True)
        self.assertEqual((p.source_run_count, p.target_run_count, p.source_cache_hits), (1, 1, 1))
        other = self.context(g, 'destination_target').provider
        self.assertFalse(other.legs); self.assertFalse(other._source_labels)
        for value in (None, 0, 1, 'yes'):
            with self.assertRaises(ValueError):
                p.leg('0', '1', target_only=value)
        with self.assertRaises(ValueError):
            self.context(g).provider.leg('0', '1', target_only=True)

    def test_explicit_graph_mutation_and_closed_cache_hits_reject(self):
        g = graph(2, [(0, 1, 1, 1)])
        ctx = self.context(g, 'destination_target')
        ctx.provider.leg('0', '1', target_only=True)
        g.source = g.source.copy()
        with self.assertRaises(ValueError):
            ctx.provider.leg('0', '1', target_only=True)
        good = self.context(graph(2, [(0, 1, 1, 1)]), 'destination_target')
        good.provider.leg('0', '1', target_only=True)
        good.close()
        with self.assertRaises(ValueError):
            good.provider.leg('0', '1', target_only=True)

    def test_explicit_invalid_graphs_and_target_indices_reject(self):
        for rows in ([(0, 1, -1, 1)], [(0, 1, float('nan'), 1)], [(0, 1, 1, float('inf'))], [(0, 2, 1, 1)]):
            with self.assertRaises(ValueError):
                self.router(graph(2, rows))
        g = graph(2, [(0, 1, 1, 1)]); g.source.flags.writeable = True
        with self.assertRaises(ValueError):
            self.router(g)
        r = self.router(graph(2, [(0, 1, 1, 1)]), mode='destination_target')
        for value in (-1, 2, True, 0.0):
            with self.assertRaises(ValueError):
                r.target_edges(0, value)

    def fixture(self, mode='full', role='search', case='nonbest', directory=None):
        directory = directory or self.directory()
        directory.mkdir(parents=True, exist_ok=True)
        positions = [0, 1, 3, 2]
        anchors = {'A': 0, 'B': 1, 'D': 2, 'X': 3}
        rows = [[a, b, abs(positions[a]-positions[b]), abs(positions[a]-positions[b])]
                for a in range(4) for b in range(4) if a != b]
        node_bytes, edge_bytes = canonical(dict(anchors=anchors, node_count=4)), canonical(rows)
        nodes, edges = directory/'nodes.json', directory/'edges.json'
        nodes.write_bytes(node_bytes); edges.write_bytes(edge_bytes)
        ctx = RoutingConfig(mode).create_context(
            graph(4, rows), self.config, self.directory(), role=role, artifact=self.artifact,
            anchor_nodes=anchors, nodes_sha256=sha(node_bytes), edges_sha256=sha(edge_bytes),
            anchor_catalog_sha256=sha(canonical(anchors)), source_cache_max_bytes=0)
        self.addCleanup(ctx.close)
        sites = {'s': RealSite('s', 'B', ('S',) if case == 'equality' else ('C',)),
                 't': RealSite('t', 'X', ('C',))}
        hierarchy = sha(b'fixed synthetic sorted-ID hierarchy')
        catalog = SparseSeedCatalog(ctx.provider, sites, origin_anchor='A', destination_anchor='D',
            nodes_path=nodes, edges_path=edges, site_catalog_sha256=site_catalog_digest(sites),
            hierarchy_sha256=hierarchy, candidate_sha256=sha(canonical(sorted(sites))))
        query = dict(origin='A', destination='D', hierarchy_sha256=hierarchy,
            sparse_domain_sha256=catalog.domain_sha256, H_ref=1, start_time_s=0,
            initial_energy_kwh=2 if case == 'charge_required' else 10, capacity_kwh=20,
            minimum_energy_kwh=0, reserve_kwh=1, consumption_kwh_per_m=1,
            overhead_s=10 if case == 'equality' else 2, lambda_stop_s=0 if case == 'equality' else 1,
            charging_segments=[[0, 20, 1, 0]], schedule=dict(a=0, b=100, D=0) if case == 'equality' else None)
        inputs = dict(query_bytes=canonical(query), catalog=catalog, nodes_path=nodes, edges_path=edges,
                      router_source_path=Path(routing.__file__).with_suffix('.cpp'),
                      approved_verifier_sha256=verifier_sources())
        return ctx, query, catalog, inputs

    def problem(self, ctx, query, catalog):
        return ctx.problem(query, catalog.sites, origin_anchor='A', destination_anchor='D',
                           site_catalog_sha256=catalog.site_catalog_sha256)

    def test_problem_dispatch_only_destination_and_bad_bool(self):
        ctx, query, cat, _ = self.fixture('destination_target')
        problem = self.problem(ctx, query, cat)
        requests = []; original = ctx.provider.leg
        def observed(source, target, **kw):
            requests.append((source, target, kw.get('target_only', False)))
            return original(source, target, **kw)
        ctx.provider.leg = observed
        for pair in (('A', 'B'), ('B', 'D'), ('B', 'A'), ('A', 'D')):
            problem.legs[pair]
        self.assertEqual(requests, [('A', 'B', False), ('B', 'D', True), ('B', 'A', False), ('A', 'D', True)])
        for value in (None, 0, 1, 'yes'):
            with self.assertRaises(ValueError):
                TableFreeRealProblem(query, cat.sites, ctx.provider, origin_anchor='A', destination_anchor='D',
                    site_catalog_sha256=cat.site_catalog_sha256, terminal_target_routing=value)
        full, q, c, _ = self.fixture()
        with self.assertRaises(ValueError):
            TableFreeRealProblem(q, c.sites, full.provider, origin_anchor='A', destination_anchor='D',
                site_catalog_sha256=c.site_catalog_sha256, terminal_target_routing=True)

    def test_flat_hier_finish_order_and_result_parity(self):
        from timecut5.exact_progress import ExactSearchProgress
        for case in ('nonbest', 'charge_required', 'equality'):
            for method in ('flat', 'hier'):
                outcomes = []
                for mode in ('full', 'destination_target'):
                    ctx, query, cat, _ = self.fixture(mode, case=case)
                    problem = self.problem(ctx, query, cat)
                    order = []; advance = problem.advance
                    def observed(pieces, site, effect):
                        order.append((tuple(x.pi for x in pieces), site, effect))
                        return advance(pieces, site, effect)
                    problem.advance = observed
                    observer = ExactSearchProgress(self.directory(), query_sha256=sha(canonical(query)),
                        domain_sha256=cat.domain_sha256, source_sha256=ctx.provider.source_sha256,
                        provider=ctx.provider, interval=.01, max_events=8)
                    result = (_solve_problem(problem, progress_hook=observer) if method == 'flat' else
                        _solve_hierarchical_problem(problem, True, build_regions(cat.sites), progress_hook=observer).bounded)
                    progress = json.loads((observer.path/'progress.json').read_bytes())
                    outcomes.append((result.canonical(), order, ctx.provider.legs, ctx.provider.edge_witnesses,
                                     progress['counters'], progress['timings']['finish']['calls']))
                self.assertEqual(outcomes[0], outcomes[1], (case, method))

    def test_actual_fresh_full_recovery_preserves_key_depth_and_identity(self):
        search, query, cat, _ = self.fixture('destination_target')
        self.problem(search, query, cat).legs['A', 'D']
        self.assertGreater(search.router.target_calls, 0)
        fresh = replay_sparse_seed(query, cat, [('t', 'C')], [1])
        out = self.directory()
        observer = StreamingSeedObserver(query, cat, output_dir=out, provenance={'synthetic': True})
        observer('incumbent', sequence=[('t', 'C')], charges=[1], lex_key=fresh['lex_key'],
                 edge_witnesses=fresh['edge_witnesses'], status='replayed_feasible_incumbent')
        observer.journal.close()
        snapshot = out/'snapshot.json'; expected = sha(snapshot.read_bytes())
        verify, q, other, inputs = self.fixture('destination_target', role='recovery')
        self.assertEqual(query, q)
        self.assertEqual(cat.provider.source_sha256, other.provider.source_sha256)
        self.assertIsNot(search.router, verify.router)
        self.assertIsNot(search.provider, verify.provider)
        receipt = recover_feasible_incumbent(snapshot, expected_checkpoint_sha256=expected, **inputs)
        self.assertEqual(receipt.primary_upper, fresh['lex_key'][0])
        self.assertEqual(receipt.max_depth, fresh['lex_key'][0] // (query['overhead_s']+query['lambda_stop_s']))
        self.assertEqual((verify.router.mode, verify.router.target_calls, verify.provider.target_run_count), ('full', 0, 0))
        self.assertFalse(receipt.exact_optimum_claimed)
        for role, mode in (('search', 'full'), ('search', 'destination_target')):
            bad, _, _, bad_inputs = self.fixture(mode, role=role)
            with self.assertRaises(ValueError):
                recover_feasible_incumbent(snapshot, expected_checkpoint_sha256=expected, **bad_inputs)
            self.assertEqual((bad.router.full_calls, bad.router.target_calls), (0, 0))
        with self.assertRaises(ValueError):
            recover_feasible_incumbent(snapshot, expected_checkpoint_sha256=expected, **inputs)
        changed, _, _, changed_inputs = self.fixture('destination_target', role='recovery')
        changed_inputs['edges_path'].write_bytes(b'changed physical bytes')
        with self.assertRaises(ValueError):
            recover_feasible_incumbent(snapshot, expected_checkpoint_sha256=expected, **changed_inputs)

    def test_durable_replay_factory_rejects_search_context(self):
        from timecut5.durable_incumbent import _independent_replay
        # Use the actual solver witness to avoid inventing its internal fields.
        search, q, cat, _ = self.fixture('destination_target')
        result = _solve_problem(self.problem(search, q, cat))
        witness = result.result.witness
        verify, qv, cv, _ = self.fixture('destination_target', role='durable_verification')
        key = _independent_replay(lambda: self.problem(verify, qv, cv), witness)
        self.assertEqual(key, result.result.key)
        self.assertEqual(verify.router.target_calls, 0)
        bad, qb, cb, _ = self.fixture('destination_target')
        with self.assertRaises(ValueError):
            _independent_replay(lambda: self.problem(bad, qb, cb), witness)
        self.assertEqual(bad.router.target_calls, 0)

    def test_direct_native_call_role_alias_and_count_guards(self):
        g = graph(2, [(0, 1, 1, 1)])
        r = self.router(g, mode='destination_target')
        outputs = [np.empty(2), np.empty(2), np.empty(2, dtype=np.int64), np.empty(2, dtype=np.int64)]
        r.lib.graph_target_edges(r.handle, 0, 1, *outputs)
        self.assertEqual(r.target_calls, 1)
        with self.assertRaises(ValueError):
            r.lib.graph_target_edges(r.handle, 0, 1, outputs[0], outputs[0], *outputs[2:])
        self.assertEqual(r.target_calls, 1)
        verifier = self.router(g, role='verification')
        with self.assertRaises(ValueError):
            verifier.lib.graph_target_edges(verifier.handle, 0, 1, *outputs)
        self.assertEqual(verifier.target_calls, 0)
        with self.assertRaises(ValueError):
            r.lib.graph_full_edges(r.handle+1, 0, False, *outputs)

    def test_artifact_mutation_and_detached_receipt(self):
        import dataclasses
        copied = self.directory(); shutil.copytree(self.artifact.directory, copied)
        bad = dataclasses.replace(self.artifact, directory=copied)
        binary = copied/'routing.so'; binary.chmod(0o600)
        data = bytearray(binary.read_bytes()); data[-1] ^= 1; binary.write_bytes(data)
        with self.assertRaises(ValueError):
            routing.ExactRouter(graph(2, [(0, 1, 1, 1)]), self.config, self.directory(),
                                role='search', mode='destination_target', artifact=bad)
        detached = self.artifact.receipt; detached['artifact_sha256'] = '0'*64
        self.assertNotEqual(detached, self.artifact.receipt)
        missing = self.directory(); shutil.copytree(self.artifact.directory, missing)
        (missing/'receipt.json').unlink()
        with self.assertRaises((ValueError, FileNotFoundError)):
            dataclasses.replace(self.artifact, directory=missing).authenticate()

    def test_table_backed_provider_retains_baseline_contract(self):
        # Distinct legacy table contract: no table-free source-map extension.
        g = graph(2, [(0, 1, 1., 2.)])
        zero = '0' * 64
        legs = {
            ('0', '0'): SelectedLeg('0', '0', True, Fraction(0), Fraction(0),
                                    'identity', 0.0.hex(), 0.0.hex()),
            ('0', '1'): SelectedLeg('0', '1', True, Fraction(1), Fraction(2),
                                    'forward_from_source', 1.0.hex(), 2.0.hex()),
            ('1', '0'): SelectedLeg('1', '0', False, None, None,
                                    'forward_from_source', None, None),
            ('1', '1'): SelectedLeg('1', '1', True, Fraction(0), Fraction(0),
                                    'identity', 0.0.hex(), 0.0.hex()),
        }
        table = ImmutableLegTable(
            ('0', '1'), '0', '1', {}, legs,
            (('data/processed/graphs/slovenia_extended/nodes.parquet', zero),
             ('data/processed/graphs/slovenia_extended/edges.parquet', zero)),
            (), 'synthetic', 'forward_per_source_v1', zero, zero, zero)
        for role, mode in ((None, 'full'), ('search', 'full'),
                           ('search', 'destination_target'), ('verification', 'full')):
            with self.subTest(role=role, mode=mode):
                router = self.router(g, role=role, mode=mode)
                provider = RoadSelectedLegProvider(
                    g, router, table, {'0': 0, '1': 1},
                    nodes_sha256=zero, edges_sha256=zero)
                for pair, expected in legs.items():
                    self.assertEqual(provider.leg(*pair), expected)
                self.assertEqual(provider.edge_witnesses['0', '1'], (0,))
                self.assertEqual(provider.edge_witnesses['1', '0'], None)
                self.assertEqual((provider.source_run_count, router.full_calls,
                                  router.target_calls), (2, 2, 0))
                self.assertFalse(hasattr(provider, 'source_sha256'))
                self.assertEqual(table.source_sha256[0][1], zero)

    def test_legacy_gateways_api_remains_supported(self):
        g = graph(3, [(0, 1, 1, 1), (1, 2, 1, 1), (2, 1, 1, 1), (1, 0, 1, 1)])
        r = self.router(g, role=None)
        forward, reverse = r.full_edges(0), r.full_edges(2, True)
        result = r.gateways([0, 1, 2], forward[0], reverse[0], forward[2], reverse[2], 10., 10.)
        self.assertEqual(result.member_nodes, (0, 1, 2))
        self.assertGreaterEqual(result.local_node_count, 3)

    def test_relocated_installed_resources_and_missing_cpp(self):
        root = self.directory(); root.mkdir()
        import microplan
        original = Path(microplan.__file__).resolve().parent
        copied = root/'microplan'
        shutil.copytree(original, copied, ignore=shutil.ignore_patterns('__pycache__'))
        for filename in ('routing.cpp', 'routing.py', 'native_artifact.py'):
            self.assertEqual((original/filename).read_bytes(), (copied/filename).read_bytes())
        script = """
from pathlib import Path
import json,sys
import microplan.routing as routing
from microplan.native_artifact import build_artifact
root=Path(sys.argv[1])
if not Path(routing.__file__).resolve().is_relative_to(root):raise RuntimeError('Relocated module not loaded')
config=json.loads(sys.argv[2])
try:
 artifact=build_artifact(config,root/'build')
except FileNotFoundError:
 if sys.argv[3]=='missing': print('missing resource rejected');raise SystemExit(0)
 raise
if sys.argv[3]=='missing':raise RuntimeError('Missing native resource accepted')
print(artifact.identity_sha256)
"""
        env = dict(os.environ, PYTHONPATH=str(root), PYTHONDONTWRITEBYTECODE='1')
        command = [sys.executable, '-B', '-c', script, str(root), json.dumps(self.config)]
        result = subprocess.run([*command, 'complete'], env=env, cwd=root, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=45)
        self.assertEqual(result.stdout.strip(), self.artifact.identity_sha256)
        (copied/'routing.cpp').unlink()
        result = subprocess.run([*command, 'missing'], env=env, cwd=root, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=45)
        self.assertEqual(result.stdout.strip(), 'missing resource rejected')


if __name__ == '__main__':
    unittest.main(verbosity=2)
