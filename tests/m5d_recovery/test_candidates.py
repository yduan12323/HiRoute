"""Tiny recovered-catalog regressions; no real graph, routing or search."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
from portable_candidate.test_portable_policy import fixture
from experiments.mechanism_recovery_v1 import candidates as c
from timecut5.real_legs import RealSite, TIE_POLICY
from timecut5.real_adapter import site_catalog_digest
from timecut5.sparse_seed import sparse_domain_digest
from timecut5.portable_candidate_policy import canonical, digest
import pandas as pd


class CandidateRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.f = f = fixture()
        # Deliberately nonlexical baseline order: it is an execution input.
        f['baseline_sites'].reverse()
        q = f['query']
        q.update(case_id=c.CASE_ID, hierarchy_sha256=digest(b'original tree'))
        self.sites = {r['site_id']: RealSite(r['site_id'], r['anchor_id'], tuple(r['effects']))
                      for r in f['baseline_sites']}
        self.sources = f['bindings']['source_sha256']
        anchors = {a: int(a[5:]) for a in [q['origin']] + [r['anchor_id'] for r in f['baseline_sites']] + [q['destination']]}
        self.sources.update(anchors=digest(canonical(anchors)), tie_policy=digest(TIE_POLICY.encode()))
        q['sparse_domain_sha256'] = sparse_domain_digest(
            self.sources, site_catalog_digest(self.sites), digest(canonical(sorted(self.sites))),
            q['hierarchy_sha256'], q['origin'], q['destination'])
        self.write('hierarchy.json', b'original tree')
        self.write('stop_sites.parquet', b'synthetic metadata; parquet reader mocked')
        self.write('geographic_screen_v5_grid14.json', canonical(dict(fixed_grid_candidates=[
            dict(site_id='origin', lat=0, lon=0), dict(site_id='destination', lat=0, lon=2)])))
        self.write('fixed_12od_candidate_slate.json', canonical(dict(od=[dict(
            od_id='OD07', origin_site='origin', destination_site='destination',
            origin_anchor=0, destination_anchor=4)])))
        self.write('pools.json', canonical(dict(
            site_catalog_sha256=c._hash_file(self.root / 'stop_sites.parquet'),
            geographic_sha256=c._hash_file(self.root / 'geographic_screen_v5_grid14.json'),
            slate_sha256=c._hash_file(self.root / 'fixed_12od_candidate_slate.json'),
            pools=[dict(od_id='OD07', sites=f['baseline_sites'], radius_m=1000,
                        eligible_capable_site_count=8)])))
        frozen = dict(query=q, candidate_site_ids=list(self.sites),
                      anchor_catalog_sha256=self.sources['anchors'],
                      sparse_domain_sha256=q['sparse_domain_sha256'],
                      candidate_sha256=digest(canonical(sorted(self.sites))),
                      site_catalog_sha256=site_catalog_digest(self.sites),
                      query_sha256=digest(canonical(q)))
        self.write('queries.json', canonical(dict(queries=[dict(query_id=c.CASE_ID,
                                          bindings={'128': frozen})], source_sha256=dict(
            graph_nodes=self.sources['nodes'], graph_edges=self.sources['edges'],
            router_cpp=self.sources['router'], hierarchy=q['hierarchy_sha256'],
            pools=c._hash_file(self.root / 'pools.json')))))
        self.bindings = {p.name: dict(size=p.stat().st_size, sha256=c._hash_file(p))
                         for p in self.root.iterdir()}
        for key, name in [('nodes', 'nodes.parquet'), ('edges', 'edges.parquet')]:
            self.bindings[name] = dict(size=0, sha256=self.sources[key])
        rows = {r['site_id']: r for r in f['baseline_sites'] + f['eligible_charging_sites']}
        self.frame = pd.DataFrame([dict(site_id=r['site_id'], access_node=r['access_node'],
            lat=0, lon=1, transport_capabilities=['charge'] if 'C' in r['effects'] else [],
            meal_count=int('S' in r['effects'])) for r in rows.values()] + [
                dict(site_id='excluded_endpoint', access_node=4, lat=0, lon=1,
                     transport_capabilities=['charge'], meal_count=0),
                dict(site_id='excluded_outside', access_node=2, lat=2, lon=1,
                     transport_capabilities=['charge'], meal_count=0)])
        self.addCleanup(patch.stopall)
        patch.object(c, 'RECOVERED_SHA256', {n: self.bindings[n]['sha256'] for n in c.RECOVERED_SHA256}).start()
        patch.object(c, 'EXPECTED_COUNTS', dict(baseline=2, eligible_chargers=7,
            unique_eligible_anchors=5, added=4, total=6)).start()
        patch('pandas.read_parquet', return_value=self.frame).start()

    def write(self, name, data):
        (self.root / name).write_bytes(data)

    def repair(self):
        return c.repair_od07(self.root, self.bindings, self.f['graph'], self.f['router'],
                            self.f['query'], self.sites, self.sources)

    def test_all_floor_pass_sites_preserve_order_query_and_hierarchy_identity(self):
        original = copy.deepcopy(self.f['query'])
        q, sites, receipt = self.repair()
        expected_added = ['colocated', 'reserve_fail_a', 'reserve_fail_b', 'zero_distance']
        self.assertEqual(list(sites), list(self.sites) + expected_added)
        self.assertEqual(receipt['proposal']['added_ids'], expected_added)
        self.assertEqual(receipt['insertion_order_sha256'], digest(canonical(list(sites))))
        self.assertNotEqual(receipt['insertion_order_sha256'], receipt['candidate_set_sha256'])
        self.assertFalse(receipt['historical_149_insertion_order_authenticated'])
        self.assertEqual(receipt['proposal']['counts']['added_floor_pass_reserve_fail'], 2)
        self.assertEqual(q['hierarchy_sha256'], original['hierarchy_sha256'])
        self.assertEqual({k: v for k, v in q.items() if k != 'sparse_domain_sha256'},
                         {k: v for k, v in original.items() if k != 'sparse_domain_sha256'})
        self.assertEqual(self.f['query'], original)
        for sid, site in self.sites.items():
            self.assertEqual(sites[sid], site)
        self.assertEqual(receipt['proposal']['counts']['eligible_chargers'], 7)
        self.assertFalse(receipt['launchable'])
        self.assertFalse(receipt['runtime_admission_complete'])
        self.assertEqual(self.f['router'].calls, [0])

    def test_source_hash_rejected_before_router(self):
        self.write('stop_sites.parquet', b'tampered')
        with self.assertRaisesRegex(ValueError, 'input identity'):
            self.repair()
        self.assertEqual(self.f['router'].calls, [])

    def test_self_consistent_replaced_source_still_rejected_by_pin(self):
        self.write('stop_sites.parquet', b'replacement')
        self.bindings['stop_sites.parquet'] = dict(size=11, sha256=digest(b'replacement'))
        with self.assertRaisesRegex(ValueError, 'pinned source'):
            self.repair()
        self.assertEqual(self.f['router'].calls, [])

    def test_changed_baseline_order_rejected_before_router(self):
        self.sites = dict(reversed(list(self.sites.items())))
        with self.assertRaisesRegex(ValueError, 'candidate order'):
            self.repair()
        self.assertEqual(self.f['router'].calls, [])

    def test_original_eligibility_failure_rejected_before_router(self):
        self.frame.loc[self.frame.site_id == 'base_charge', 'lat'] = 3
        with self.assertRaisesRegex(ValueError, 'eligibility changed'):
            self.repair()
        self.assertEqual(self.f['router'].calls, [])

    def test_cap_overflow_rejects_complete_union_without_truncation(self):
        with patch.object(c, 'CAP', 5), self.assertRaisesRegex(ValueError, 'candidate_cap_overflow'):
            self.repair()
        self.assertEqual(self.f['router'].calls, [0])

    def test_expected_149_is_validation_not_truncation_rule(self):
        with patch.dict(c.EXPECTED_COUNTS, total=5), self.assertRaisesRegex(ValueError, 'validation target'):
            self.repair()
        self.assertEqual(self.f['router'].calls, [0])

    def test_original_provider_domain_rejected_before_router(self):
        self.sources['unexpected_policy'] = 'a' * 64
        with self.assertRaisesRegex(ValueError, 'provider/domain identity'):
            self.repair()
        self.assertEqual(self.f['router'].calls, [])

    def test_new_native_source_rebinds_only_domain_and_records_both_identities(self):
        original = copy.deepcopy(self.f['query'])
        self.sources['router'] = '8' * 64
        self.f['router'].provenance['source_sha256'] = '8' * 64
        q, sites, receipt = self.repair()
        self.assertEqual(receipt['historical_baseline_query'], original)
        rebound = receipt['runtime_baseline_query']
        self.assertNotEqual(rebound['sparse_domain_sha256'], original['sparse_domain_sha256'])
        self.assertEqual(dict(rebound, sparse_domain_sha256=original['sparse_domain_sha256']), original)
        self.assertEqual(receipt['historical_provider_sources']['router'], 'a' * 64)
        self.assertEqual(receipt['runtime_provider_sources']['router'], '8' * 64)
        self.assertEqual(receipt['runtime_native_provenance']['source_sha256'], '8' * 64)
        self.assertEqual(receipt['baseline_rebinding_fields'], ['sparse_domain_sha256'])

    def test_current_native_source_mismatch_fails_before_route(self):
        self.sources['router'] = '8' * 64
        with self.assertRaisesRegex(ValueError, 'current provider/domain'):
            self.repair()
        self.assertEqual(self.f['router'].calls, [])

    def test_historical_domain_mismatch_fails_before_route(self):
        path = self.root / 'queries.json'
        document = json.loads(path.read_bytes())
        document['source_sha256']['router_cpp'] = '8' * 64
        path.write_bytes(canonical(document))
        self.bindings['queries.json'] = dict(size=path.stat().st_size, sha256=c._hash_file(path))
        with self.assertRaisesRegex(ValueError, 'historical provider/domain'):
            self.repair()
        self.assertEqual(self.f['router'].calls, [])

    def test_query_semantics_drift_rejected_before_router(self):
        self.f['query']['reserve_kwh'] = '0'
        with self.assertRaisesRegex(ValueError, 'original query'):
            self.repair()
        self.assertEqual(self.f['router'].calls, [])


if __name__ == '__main__':
    unittest.main()
