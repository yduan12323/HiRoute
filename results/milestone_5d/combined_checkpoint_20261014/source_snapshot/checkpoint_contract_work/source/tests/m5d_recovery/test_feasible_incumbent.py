"""Small graph fixtures only; no production data, native binary, or optimizer."""
import copy
from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path
import resource
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT), str(ROOT.parents[1])]
from timecut5 import feasible_incumbent as f, sparse_seed, deployable
from timecut5.streaming_seed_diagnostic import StreamingSeedObserver
helpers = {'__name__': 'fixture_helpers', '__file__': str(ROOT/'fixture_helpers.py')}
with patch.object(sys, 'argv', ['fixture', 'disabled']):
    exec((ROOT/'fixture_helpers.py').read_text().split('results=[]')[0], helpers)

helpers['SHA'] = f.sha((ROOT/'fixture_helpers.py').read_bytes())
helpers['Router'].provenance = {'source_sha256': helpers['SHA']}

class Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.query, cat, _ = helpers['fixture'](6, self.root)
        candidates = deployable.constructive_seed_candidates(self.query, cat)
        for seq, charges in reversed(candidates):
            try:
                replay = sparse_seed.replay_sparse_seed(self.query, cat, seq, charges)
                break
            except sparse_seed.SeedInfeasible:
                pass
        observer = StreamingSeedObserver(self.query, cat, output_dir=self.root/'diagnostic', provenance={'fixture': 6})
        observer('incumbent', sequence=seq, charges=charges, lex_key=replay['lex_key'],
                 edge_witnesses=replay['edge_witnesses'], status='replayed_feasible_incumbent')
        observer.journal.close()
        self.path = self.root/'diagnostic'/'snapshot.json'
        self.snapshot = json.loads(self.path.read_bytes())
        self.approved = f.verifier_sources()

    def arguments(self):
        q, cat, _ = helpers['fixture'](6, self.root)
        return dict(checkpoint_path=self.path, expected_checkpoint_sha256=f.sha(self.path.read_bytes()),
            query_bytes=f.canonical(self.query), catalog=cat, nodes_path=self.root/'nodes.fixture',
            edges_path=self.root/'edges.fixture', router_source_path=ROOT/'fixture_helpers.py',
            approved_verifier_sha256=self.approved)

    def rewrite(self, modify):
        snap = copy.deepcopy(self.snapshot); modify(snap)
        self.path.write_bytes(f.canonical(snap))

    def test_partial_stream_is_separate_frozen_feasible_receipt(self):
        receipt = f.recover_feasible_incumbent(**self.arguments())
        self.assertFalse(self.snapshot['generation_complete'])
        self.assertEqual(receipt.status, 'feasible_incumbent_available')
        self.assertFalse(receipt.heuristic_minimum_claimed)
        self.assertFalse(receipt.exact_optimum_claimed)
        self.assertFalse(receipt.exact_solver_admitted)
        self.assertNotIsInstance(receipt, deployable.SeedDepthCertificate)
        self.assertEqual(receipt.max_depth, receipt.primary_upper // 2)
        self.assertEqual(receipt.witness_sha256, f.sha(receipt.witness_bytes))
        with self.assertRaises(FrozenInstanceError): receipt.max_depth = 1
        self.assertEqual(f.reverify_feasible_incumbent(receipt, **self.arguments()), receipt)

    def test_tampered_bounds_are_recomputed_at_boundary(self):
        receipt = f.recover_feasible_incumbent(**self.arguments())
        for fake in (replace(receipt, max_depth=receipt.max_depth+1),
                     replace(receipt, primary_upper=receipt.primary_upper+1),
                     replace(receipt, witness_bytes=b'forged')):
            with self.assertRaises(ValueError): f.reverify_feasible_incumbent(fake, **self.arguments())

    def test_stale_query_and_source_bindings_rejected(self):
        for field, value in [('canonical_query_sha256','0'*64), ('domain_sha256','0'*64),
                             ('source_sha256',{}), ('graph_node_count',99)]:
            self.rewrite(lambda s: s.update({field:value}))
            with self.assertRaises(ValueError): f.recover_feasible_incumbent(**self.arguments())

    def test_missing_incumbent_and_malformed_witness_rejected(self):
        mutations = [lambda s:s.update(provisional_incumbent=None),
            lambda s:s['provisional_incumbent'].pop('charges'),
            lambda s:s['provisional_incumbent'].update(edge_witnesses=[]),
            lambda s:s['provisional_incumbent'].update(charges=[True]),
            lambda s:s['provisional_incumbent'].update(edge_witnesses=[[True]]),
            lambda s:s['provisional_incumbent'].update(sequence=[['missing','C']])]
        for mutate in mutations:
            self.rewrite(mutate)
            with self.assertRaises((ValueError, KeyError)): f.recover_feasible_incumbent(**self.arguments())

    def test_checkpoint_digest_corruption_and_truncation(self):
        args = self.arguments(); self.path.write_bytes(b'{')
        with self.assertRaises(ValueError): f.recover_feasible_incumbent(**args)
        args['expected_checkpoint_sha256'] = f.sha(b'{')
        with self.assertRaises(ValueError): f.recover_feasible_incumbent(**args)

    def test_no_journal_or_tmp_recovery_and_complete_snapshot_survives_tmp(self):
        tmp = self.path.with_suffix('.tmp'); tmp.write_bytes(b'{')
        args = self.arguments(); f.recover_feasible_incumbent(**args)
        args = self.arguments(); args['checkpoint_path'] = tmp
        with self.assertRaises(ValueError): f.recover_feasible_incumbent(**args)

    def test_duplicate_json_and_false_optimum_rejected(self):
        args = self.arguments()
        self.path.write_bytes(b'{"schema":1,"schema":2}')
        args['expected_checkpoint_sha256'] = f.sha(self.path.read_bytes())
        with self.assertRaises(ValueError): f.recover_feasible_incumbent(**args)
        self.rewrite(lambda s:s.update(exact_optimum_claimed=True))
        with self.assertRaises(ValueError): f.recover_feasible_incumbent(**self.arguments())

    def test_cached_provider_is_rejected(self):
        args = self.arguments(); args['catalog'].provider.leg('0','4')
        with self.assertRaises(ValueError): f.recover_feasible_incumbent(**args)

    def test_graph_bytes_and_approved_code_are_rechecked(self):
        args = self.arguments(); (self.root/'edges.fixture').write_bytes(b'changed')
        with self.assertRaises(ValueError): f.recover_feasible_incumbent(**args)
        args = self.arguments(); args['approved_verifier_sha256'] = {}
        with self.assertRaises(ValueError): f.recover_feasible_incumbent(**args)

    def test_witness_key_and_edge_disagreement_rejected(self):
        for mutate in [lambda s:s['provisional_incumbent']['lex_key'].__setitem__(0,'99999'),
                       lambda s:s['provisional_incumbent']['edge_witnesses'][0].append(999)]:
            self.rewrite(mutate)
            with self.assertRaises(ValueError): f.recover_feasible_incumbent(**self.arguments())

    def test_mutable_catalog_and_query_cannot_change_proof(self):
        args = self.arguments(); args['catalog'].sites.pop('1')
        with self.assertRaises(ValueError): f.recover_feasible_incumbent(**args)
        args = self.arguments(); q = dict(self.query, initial_energy_kwh=0)
        args['query_bytes'] = f.canonical(q)
        with self.assertRaises(ValueError): f.recover_feasible_incumbent(**args)

    def test_invalid_depth_assumptions_fail_closed(self):
        for overhead, penalty in [(0,1),(1,-1)]:
            args = self.arguments()
            query = dict(self.query, overhead_s=overhead, lambda_stop_s=penalty)
            args['query_bytes'] = f.canonical(query)
            self.rewrite(lambda snap: snap.update(canonical_query_sha256=f.sha(f.canonical(query))))
            args['expected_checkpoint_sha256'] = f.sha(self.path.read_bytes())
            with self.assertRaises(ValueError): f.recover_feasible_incumbent(**args)

    def test_native_failure_propagates_without_receipt(self):
        args = self.arguments(); args['catalog'].provider.router.fail = True
        with self.assertRaisesRegex(RuntimeError, 'fixture native failure'):
            f.recover_feasible_incumbent(**args)

    def test_old_completed_seed_api_unchanged(self):
        q, cat, _ = helpers['fixture'](6, self.root)
        seed = sparse_seed.admit_sparse_seed(q,cat)
        self.assertEqual(seed['status'],'verified')
        self.assertNotIn('feasible_incumbent_available',seed.values())

if __name__ == '__main__':
    resource.setrlimit(resource.RLIMIT_CPU, (60,60))
    started = time.process_time()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    report = dict(tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                  cpu_seconds=time.process_time()-started, real_od_runs=0, exact_solver_runs=0)
    (ROOT/'TEST_RESULTS.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(not result.wasSuccessful())
