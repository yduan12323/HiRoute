"""Small source-loaded graphs only; no real OD or production experiment."""
import hashlib
import json
from fractions import Fraction as F
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixture_source import fixture
from timecut5 import deployable, sparse_seed
from timecut5.real_adapter import site_catalog_digest
from timecut5.real_legs import RealSite


class FirstSequentialFeasibleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def fixture(self, name='source', *, full_sites=False):
        q, old, paths = fixture(self.root / name)
        sites = {'s': RealSite('s', 'B', ('C', 'S', 'CS')),
                 't': RealSite('t', 'X', ('C', 'S', 'CS'))}
        if full_sites:
            sites.update({f'z{i:03}': RealSite(f'z{i:03}', 'X', ('C', 'S', 'CS'))
                          for i in range(147)})
        c = sparse_seed.SparseSeedCatalog(old.provider, sites,
            origin_anchor=old.origin_anchor, destination_anchor=old.destination_anchor,
            nodes_path=paths['nodes_path'], edges_path=paths['edges_path'],
            site_catalog_sha256=site_catalog_digest(sites),
            hierarchy_sha256=old.hierarchy_sha256,
            candidate_sha256=hashlib.sha256(json.dumps(sorted(sites), separators=(',', ':')).encode()).hexdigest())
        q.update(sparse_domain_sha256=c.domain_sha256,
                 schedule={'a': 0, 'b': 100, 'D': 4})
        return q, c

    def test_first_replay_stops_before_eager_trap_and_callback_is_complete(self):
        q, c = self.fixture()
        proposal = ((('s', 'CS'),), ('1/3',))
        events = []
        def stream(*args):
            yield proposal
            raise AssertionError('must never advance after first feasible proposal')
        def observe(event, **snapshot):
            events.append((event, dict(snapshot)))
            # Deep nested mutation cannot corrupt the returned provenance.
            snapshot['provenance']['query']['schedule']['b'] = -1
        with patch.object(deployable, 'iter_constructive_seed_candidates', stream), \
             patch.object(deployable, 'constructive_seed_candidates', side_effect=AssertionError('eager')):
            result = sparse_seed.first_sequential_feasible(q, c, observer=observe)
        self.assertEqual(result['status'], 'first_feasible')
        self.assertEqual(result['proposal_count'], 1)
        self.assertEqual(result['proposal_ordinal'], 0)
        self.assertFalse(result['generation_complete'])
        self.assertFalse(result['exact_optimum_claimed'])
        self.assertFalse(result['finite_stream_minimum_claimed'])
        self.assertFalse(result['fresh_provider_verified'])
        self.assertEqual(result['sequence'], proposal[0])
        self.assertEqual(result['charges'], (F(1, 3),))
        # Arrival 1 + overhead 2 + charge 1/3 + service 4 + drive 2 + stop 1.
        self.assertEqual(result['lex_key'], (F(31, 3), F(1, 3), 1, proposal[0]))
        self.assertEqual(events[0][0], 'first_feasible')
        for key in ('sequence', 'charges', 'lex_key', 'edge_witnesses', 'domain_sha256'):
            self.assertEqual(events[0][1][key], result[key])
        self.assertEqual(result['provenance']['query']['schedule']['b'], 100)
        self.assertEqual(result['provenance']['source_sha256'], c.provider.source_sha256)

    def test_concurrent_feasible_sequential_window_rejection_continues(self):
        q, c = self.fixture()
        q['schedule']['b'] = 3
        proposals = [((('s', 'CS'),), (F(1),)), ((('s', 'S'),), ())]
        sparse_seed.replay_sparse_seed(q, c, *proposals[0])
        with self.assertRaisesRegex(sparse_seed.SeedInfeasible, 'Schedule'):
            sparse_seed.replay_sparse_seed(q, c, *proposals[0], sequential_no_overlap=True)
        with patch.object(deployable, 'iter_constructive_seed_candidates', return_value=iter(proposals)):
            result = sparse_seed.first_sequential_feasible(q, c)
        self.assertEqual(result['proposal_ordinal'], 1)
        self.assertEqual(result['proposal_count'], 2)
        self.assertEqual(result['sequence'], proposals[1][0])

    def test_strict_positive_charge_and_unattained_stream_are_unknown(self):
        q, c = self.fixture()
        proposals = [((('s', 'CS'),), (F(0),)), ((('s', 'CS'),), (F(-1),))]
        with patch.object(deployable, 'iter_constructive_seed_candidates', return_value=iter(proposals)):
            result = sparse_seed.first_sequential_feasible(q, c)
        self.assertEqual(result['status'], 'unknown')
        self.assertTrue(result['generation_complete'])
        self.assertEqual(result['accepted_count'], 0)
        with patch.object(deployable, 'iter_constructive_seed_candidates', return_value=iter(())):
            self.assertEqual(sparse_seed.first_sequential_feasible(q, c)['status'], 'unknown')

    def test_invalid_stream_source_and_callback_failures_propagate(self):
        q, c = self.fixture()
        def broken(*args):
            raise RuntimeError('invalid stream remains an error, not infeasible')
            yield
        with patch.object(deployable, 'iter_constructive_seed_candidates', broken):
            with self.assertRaisesRegex(RuntimeError, 'invalid stream'):
                sparse_seed.first_sequential_feasible(q, c)
        for amount in (True, 0.5):
            with patch.object(deployable, 'iter_constructive_seed_candidates',
                              return_value=iter([((("s", "CS"),), (amount,))])):
                with self.assertRaises(ValueError):
                    sparse_seed.first_sequential_feasible(q, c)
        with patch.object(c.provider, 'leg', side_effect=RuntimeError('source failure')):
            with self.assertRaisesRegex(RuntimeError, 'source failure'):
                sparse_seed.first_sequential_feasible(q, c)
        def fail(*args, **kwargs):
            raise OSError('persistence failure')
        with self.assertRaisesRegex(OSError, 'persistence failure'):
            sparse_seed.first_sequential_feasible(q, c, observer=fail)

    def test_full_catalog_real_stream_and_fresh_provider_recovery(self):
        q, c = self.fixture(full_sites=True)
        snapshots = []
        result = sparse_seed.first_sequential_feasible(q, c,
            observer=lambda event, **data: snapshots.append(data))
        self.assertEqual(result['provenance']['site_count'], 149)
        self.assertEqual(result['provenance']['generator_cs_clock'], 'concurrent')
        # Simulate durable JSON round trip, then reload original source bytes
        # into an independent provider, without reusing any selected-leg cache.
        saved = json.loads(json.dumps(snapshots[0], default=str))
        fresh_query, fresh = self.fixture('fresh', full_sites=True)
        self.assertIsNot(c.provider, fresh.provider)
        self.assertEqual(fresh.provider.source_run_count, 0)
        self.assertEqual(saved['domain_sha256'], fresh.domain_sha256)
        replay = sparse_seed.replay_sparse_seed(saved['provenance']['query'], fresh,
            saved['sequence'], saved['charges'], sequential_no_overlap=True)
        self.assertEqual(replay['lex_key'], result['lex_key'])
        self.assertEqual(replay['edge_witnesses'], result['edge_witnesses'])
        self.assertGreater(fresh.provider.source_run_count, 0)
        self.assertEqual(fresh_query, saved['provenance']['query'])

    def test_optional_physical_events_are_exact_and_default_schema_unchanged(self):
        q, c = self.fixture()
        proposal = ((('s', 'CS'),), (F(1, 3),))
        plain = sparse_seed.replay_sparse_seed(q, c, *proposal)
        self.assertEqual(set(plain), {'lex_key', 'edge_witnesses', 'domain_sha256', 'source_run_count'})
        concurrent = sparse_seed.replay_sparse_seed(q, c, *proposal, include_events=True)
        sequential = sparse_seed.replay_sparse_seed(q, c, *proposal,
            sequential_no_overlap=True, include_events=True)
        self.assertEqual(concurrent['distance_m'], F(3))
        self.assertEqual(sequential['distance_m'], F(3))
        self.assertEqual(concurrent['elapsed_s'], F(9))
        self.assertEqual(sequential['elapsed_s'], F(28, 3))
        self.assertEqual(concurrent['overlap_s'], F(1, 3))
        self.assertEqual(sequential['overlap_s'], F(0))
        event = sequential['events'][0]
        self.assertEqual(event['arrival'], F(1))
        self.assertEqual(event['release'], F(3))  # Parking overhead exactly once.
        self.assertEqual(event['charge_start'], F(3))
        self.assertEqual(event['charge_done'], F(10, 3))
        self.assertEqual(event['service_start'], F(10, 3))
        self.assertEqual(event['service_done'], F(22, 3))
        self.assertEqual(event['departure'], F(22, 3))
        self.assertEqual(event['window_margin_s'], F(290, 3))
        self.assertEqual(sequential['terminal_energy_kwh'], F(22, 3))
        q['start_time_s'] = 10
        shifted = sparse_seed.replay_sparse_seed(q, c, *proposal,
            sequential_no_overlap=True, include_events=True)
        self.assertEqual(shifted['elapsed_s'], sequential['elapsed_s'])
        self.assertEqual(shifted['arrival_time_s'], sequential['arrival_time_s'] + 10)

    def test_real_generator_first_feasible_matches_original_order(self):
        q, c = self.fixture()
        expected = None
        for ordinal, proposal in enumerate(deployable.iter_constructive_seed_candidates(q, c)):
            try:
                replay = sparse_seed.replay_sparse_seed(q, c, *proposal, sequential_no_overlap=True)
            except sparse_seed.SeedInfeasible:
                continue
            expected = ordinal, proposal, replay
            break
        self.assertIsNotNone(expected)
        result = sparse_seed.first_sequential_feasible(q, c)
        self.assertEqual(result['proposal_ordinal'], expected[0])
        self.assertEqual((result['sequence'], result['charges']), expected[1])
        self.assertEqual(result['lex_key'], expected[2]['lex_key'])


if __name__ == '__main__':
    unittest.main()
