"""Synthetic regression only: no production OD, native binary, or candidate changes."""
import hashlib
import heapq
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = Path(os.environ.get('COVERAGE_SOURCE_ROOT', str(ROOT.parents[1]))).resolve()
sys.path[:0] = [str(ROOT), str(ROOT.parents[1])]
from timecut5.real_legs import RealSite
from timecut5.real_adapter import site_catalog_digest
from timecut5.road_provider import TableFreeRoadSelectedLegProvider
from timecut5.sparse_seed import SparseSeedCatalog, admit_sparse_seed, replay_sparse_seed, SeedInfeasible
from timecut5.deployable import SolveStatus

SHA = '0' * 64

def digest(data):
    return hashlib.sha256(data).hexdigest()

def canonical(data):
    return json.dumps(data, sort_keys=True, separators=(',', ':')).encode()

class Router:
    provenance = {'source_sha256': SHA}
    def __init__(self, graph):
        self.graph = graph
    def full_edges(self, source):
        g = self.graph
        costs = [float('inf')] * g.node_count
        lengths = costs.copy()
        parents = [-1] * g.node_count
        edges = parents.copy()
        costs[source] = lengths[source] = 0.
        queue = [(0., 0., source)]
        while queue:
            cost, length, node = heapq.heappop(queue)
            if (cost, length) != (costs[node], lengths[node]):
                continue
            for edge, (a, b) in enumerate(zip(g.source, g.target)):
                if a != node:
                    continue
                candidate = cost + g.weights['travel_time'][edge], length + g.weights['distance'][edge]
                if candidate < (costs[b], lengths[b]):
                    costs[b], lengths[b] = candidate
                    parents[b], edges[b] = a, edge
                    heapq.heappush(queue, (*candidate, b))
        return costs, lengths, parents, edges

def catalog(root, edges, site_nodes, initial=3, capacity=6, reserve=1, bound=1):
    names = sorted({node for a, b, _ in edges for node in (a, b)})
    anchors = {name: i for i, name in enumerate(names)}
    graph = SimpleNamespace(node_count=len(names), edge_count=len(edges),
        source=[anchors[a] for a, _, _ in edges], target=[anchors[b] for _, b, _ in edges],
        weights={key: [float(w) for _, _, w in edges] for key in ('travel_time', 'distance')})
    nodes_file, edges_file = root / 'nodes.json', root / 'edges.json'
    nodes_file.write_bytes(canonical(names)); edges_file.write_bytes(canonical(edges))
    provider = TableFreeRoadSelectedLegProvider(graph, Router(graph), anchors,
        nodes_sha256=digest(nodes_file.read_bytes()), edges_sha256=digest(edges_file.read_bytes()),
        router_sha256=SHA, anchor_catalog_sha256=digest(canonical(anchors)))
    sites = {sid: RealSite(sid, sid, ('C',)) for sid in site_nodes}
    c = SparseSeedCatalog(provider, sites, origin_anchor='o', destination_anchor='d',
        nodes_path=nodes_file, edges_path=edges_file, site_catalog_sha256=site_catalog_digest(sites),
        hierarchy_sha256=SHA, candidate_sha256=digest(canonical(sorted(sites))))
    q = dict(origin='o', destination='d', hierarchy_sha256=SHA, sparse_domain_sha256=c.domain_sha256,
        H_ref=bound, start_time_s=0, initial_energy_kwh=initial, capacity_kwh=capacity,
        minimum_energy_kwh=0, reserve_kwh=reserve, consumption_kwh_per_m=1,
        overhead_s=1, lambda_stop_s=1, charging_segments=[[0, capacity, 1, 0]], schedule=None)
    return q, c

def reachable_chargers(q, c):
    return [sid for sid, site in c.sites.items()
        if 'C' in site.effects and (leg := c.leg('o', site.anchor_id)).reachable
        and q['initial_energy_kwh'] - leg.energy(q['consumption_kwh_per_m']) >= q['minimum_energy_kwh']]

class CoverageRegression(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
    def tearDown(self):
        self.tmp.cleanup()
    def test_n32_prefix_failure_larger_pool_has_verified_trip(self):
        prefix = [f'c{i:02}' for i in range(32)]
        edges = [('o', 'd', 12), ('o', 'bridge', 2), ('bridge', 'd', 4)]
        edges += [edge for sid in prefix for edge in [('o', sid, 10), (sid, 'd', 4)]]
        q32, c32 = catalog(self.root, edges, prefix)
        self.assertEqual(reachable_chargers(q32, c32), [])
        result = admit_sparse_seed(q32, c32)
        self.assertEqual(result['status'], 'incumbent_search_failed')
        self.assertNotIn('max_depth', result)
        q33, c33 = catalog(self.root, edges, prefix + ['bridge'])
        self.assertEqual(reachable_chargers(q33, c33), ['bridge'])
        self.assertNotEqual(c32.domain_sha256, c33.domain_sha256)
        result = admit_sparse_seed(q33, c33)
        self.assertEqual(result['status'], 'verified')
        self.assertEqual(result['sequence'], (('bridge', 'C'),))
        self.assertEqual(replay_sparse_seed(q33, c33, result['sequence'], result['charges'])['lex_key'], result['lex_key'])
    def test_first_reachable_charger_does_not_establish_whole_trip(self):
        q, c = catalog(self.root, [('o', 'd', 20), ('o', 'bridge', 2), ('bridge', 'd', 10)], ['bridge'])
        self.assertEqual(reachable_chargers(q, c), ['bridge'])
        self.assertEqual(admit_sparse_seed(q, c)['status'], 'incumbent_search_failed')
        with self.assertRaisesRegex(SeedInfeasible, 'Terminal reserve infeasible'):
            replay_sparse_seed(q, c, (('bridge', 'C'),), (5,))
    def test_heuristic_failure_even_with_full_fixture_pool_and_feasible_trip(self):
        # Nine mandatory charging stops; the heuristic beam stops at depth eight.
        sites = [f'c{i}' for i in range(9)]
        chain = ['o'] + sites + ['d']
        edges = [(a, b, 2) for a, b in zip(chain, chain[1:])]
        q, c = catalog(self.root, edges, sites, initial=2, capacity=3, reserve=0, bound=9)
        self.assertEqual(reachable_chargers(q, c), ['c0'])
        self.assertEqual(admit_sparse_seed(q, c)['status'], 'incumbent_search_failed')
        replay = replay_sparse_seed(q, c, tuple((sid, 'C') for sid in sites), (2,) * 9)
        self.assertEqual(replay['lex_key'][:3], (56, 18, 9))
    def test_routing_failure_is_not_relabelled_as_infeasibility(self):
        q, c = catalog(self.root, [('o', 'd', 20), ('o', 'bridge', 2), ('bridge', 'd', 4)], ['bridge'])
        def fail(_source):
            raise RuntimeError('synthetic source routing failure')
        c.provider.router.full_edges = fail
        with self.assertRaisesRegex(RuntimeError, 'synthetic source routing failure'):
            admit_sparse_seed(q, c)

    def test_failure_status_is_separate_from_domain_scoped_infeasibility(self):
        self.assertNotEqual(SolveStatus.INCUMBENT_SEARCH_FAILED, SolveStatus.INFEASIBLE_WITHIN_DECLARED_DOMAIN)
        self.assertEqual(SolveStatus.INCUMBENT_SEARCH_FAILED.value, 'incumbent_search_failed')
        self.assertEqual(SolveStatus.INFEASIBLE_WITHIN_DECLARED_DOMAIN.value, 'infeasible_within_declared_domain')

if __name__ == '__main__':
    started = time.process_time()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(CoverageRegression)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = dict(tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                  cpu_seconds=time.process_time()-started, synthetic_only=True,
                  production_code_modified=False, frozen_selection_modified=False, real_od_runs=0)
    (ROOT / os.environ.get('COVERAGE_REPORT', 'TEST_RESULTS.json')).write_text(json.dumps(report, indent=2) + '\n')
    sys.exit(not result.wasSuccessful())
