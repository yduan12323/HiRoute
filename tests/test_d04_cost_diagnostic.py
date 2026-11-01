"""Diagnostic hooks preserve results, clocks, cutoff equality and resource checks."""
import json
from pathlib import Path
from types import SimpleNamespace
import time
import unittest
import sys
from hiroute.contracts import ProblemSnapshot
from hiroute.exact import scale,scale_bounds,road_index

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from d04_cost_diagnostic import CostProfile,MeasuredProvider,instrument,domain_digest,source_reuse_analysis,summarize_run


def snapshot():
    raw=json.loads((ROOT/'tests/r0/c01_zero_stop_snapshot.json').read_text())
    raw.update(initial_energy_kwh='2',capacity_kwh='2',depth_limit=2,
        candidate_order=['a','b','c'],site_capabilities={s:['C'] for s in 'abc'},
        charging_curve=[['0','2','1','0']],directed_edges=[
            dict(source=a,target=b,time_s=str(t),length_m=str(l),edge_id=str(i))
            for i,(a,b,t,l) in enumerate([('o','a',1,2),('a','b',1,2),('b','z',1,2),
                                          ('o','c',1,3),('c','z',1,3)])])
    return ProblemSnapshot.from_dict(raw)


class DiagnosticTests(unittest.TestCase):
    def test_summary_does_not_invent_a_profile_after_an_early_stop(self):
        import tempfile
        with tempfile.TemporaryDirectory() as work:
            root=Path(work)
            (root/'diagnostic-result.jsonl').write_text(json.dumps(dict(status='not_run_cpu_budget'))+'\n')
            (root/'preparation.json').write_text('{}')
            summary=summarize_run(root)
            self.assertFalse(summary['profile_available'])
            self.assertEqual(summary['row']['status'],'not_run_cpu_budget')
            self.assertNotIn('source_reuse',summary)
            workers=root/'diagnostic-result-workers';workers.mkdir()
            (root/'diagnostic-result.jsonl').write_text(json.dumps(dict(status='host_headroom_limit'))+'\n')
            (workers/'query.cost.json').write_text('{}')
            (workers/'query.cost-events.json').write_text('[]')
            summary=summarize_run(root)
            self.assertEqual(summary['row']['status'],'host_headroom_limit')
            self.assertIn('source_reuse_unavailable_reason',summary)
            self.assertNotIn('source_reuse',summary)

    def test_offline_source_reuse_proxy_charges_builds_and_respects_lru(self):
        events=[dict(kind='search_leaf',source=s,target=str(i),settled_vertices=1,
                     relaxed_edges=w,astar_s=1,path_edges=1,error=None)
                for i,(s,w) in enumerate([('a',6),('a',5),('a',3),('b',11),
                                          ('a',4),('c',11),('b',6),('b',5)])]
        result=source_reuse_analysis(events,100,10)
        self.assertFalse(result['algorithm_executed'])
        self.assertIsNone(result['runtime_saving_estimate'])
        one,two=result['sketches']
        self.assertEqual((one['forward_tree_builds'],one['covered_later_pairs']),(4,1))
        self.assertEqual((two['forward_tree_builds'],two['covered_later_pairs']),(4,2))
        self.assertEqual(two['full_tree_edges_upper_work'],40)
        self.assertEqual(two['observed_covered_relaxed_edges'],7)
        self.assertEqual(two['canonical_path_vertices_lower_work'],4)

    def test_profile_parity_flow_accounting_and_patch_restoration(self):
        snap=snapshot();original=scale.solve_scale;original_bound=scale_bounds.completion_bound
        original_native=road_index.NativeRoadIndex
        for method in ('flat_bb_strong','scale'):
            expected=scale.solve_scale(snap,method=method,seed_beam_pruning=True)
            profile=CostProfile();profile.window_start=time.monotonic()
            provider=MeasuredProvider(road_index.RoadIndex(snap.directed_edges),profile)
            callbacks=[]
            with instrument(profile):
                actual=scale.solve_scale(snap,method=method,provider=provider,seed_beam_pruning=True,
                                         on_incumbent=lambda r:callbacks.append(r['key']))
            profile.window_end=time.monotonic()
            self.assertEqual((actual['status'],actual['key'],actual['seed']['key']),
                             (expected['status'],expected['key'],expected['seed']['key']))
            self.assertEqual(actual['metrics'],expected['metrics'])
            self.assertTrue(callbacks)
            summary=profile.summary();outcomes=summary['leaf_outcomes']
            count=lambda key:outcomes.get(key,{}).get('requests',0)
            self.assertEqual(summary['by_kind']['search_leaf']['requests'],actual['metrics']['leaf_routes'])
            self.assertEqual(count('empty_family'),actual['metrics']['empty_prefixes'])
            self.assertEqual(count('empty_family')+count('nonempty_child'),actual['metrics']['transitions'])
            self.assertEqual(count('selected')+count('interrupted'),0)
            self.assertEqual(summary['calls'].get('association_mismatch',0),0)
            self.assertGreaterEqual(summary['residual_other_s'],-1e-6)
            self.assertTrue(all(t>=0 for t in summary['exclusive_seconds'].values()))
        self.assertIs(scale.solve_scale,original)
        self.assertIs(scale_bounds.completion_bound,original_bound)
        self.assertIs(road_index.NativeRoadIndex,original_native)
        with self.assertRaisesRegex(RuntimeError,'probe'):
            with instrument(CostProfile()):raise RuntimeError('probe')
        self.assertIs(scale.solve_scale,original)

    def test_equality_cache_and_resource_exception_are_not_misclassified(self):
        profile=CostProfile();event=dict(source='a',target='b',outcome='selected')
        profile.last_leaf=event;profile.ub=5
        profile.mark_bound(5)
        self.assertEqual(event['outcome'],'selected')
        profile.mark_bound(6)
        self.assertEqual(event['outcome'],'late_bound_prune')
        provider=road_index.RoadIndex(snapshot().directed_edges)
        wrapped=MeasuredProvider(provider,profile)
        self.assertIs(wrapped.selected_leg('o','a'),wrapped.selected_leg('o','a'))
        self.assertFalse(profile.events[-2]['cache_hit'])
        self.assertTrue(profile.events[-1]['cache_hit'])
        def stop():raise scale.ResourceLimit('time_limit')
        wrapped.check=stop
        self.assertIs(provider.check,stop)
        with self.assertRaises(scale.ResourceLimit):wrapped.selected_leg('a','b')
        self.assertEqual(profile.events[-1]['outcome'],'interrupted')
        self.assertEqual(profile.events[-1]['error'],'ResourceLimit')
        self.assertEqual(CostProfile(clock=lambda:0).summary()['measurement_window_s'],0)

    def test_domain_identity_covers_selected_inputs(self):
        q=dict(endpoints={'origin':'o','destination':'z'},
               scenario_candidate_domains={'energy_only':{'1':[dict(site_id='a',access_node='x')]}})
        first=domain_digest(q,1,'energy_only')
        q['scenario_candidate_domains']['energy_only']['1'][0]['access_node']='y'
        self.assertNotEqual(first,domain_digest(q,1,'energy_only'))

    def test_native_profile_preserves_exact_result_and_check_callback(self):
        import os,shutil,tempfile
        roots=[Path('/usr/include'),Path('/usr/local/include'),Path('/opt/homebrew/include')]
        roots += [Path(p) for p in os.environ.get('CPLUS_INCLUDE_PATH','').split(os.pathsep) if p]
        if not shutil.which('c++') or not any((p/'boost/multiprecision/cpp_int.hpp').exists() for p in roots):
            if os.environ.get('HIROUTE_REQUIRE_NATIVE_ROADS')=='1':self.fail('native profile dependency missing')
            return
        snap=snapshot();expected=scale.solve_scale(snap,seed_beam_pruning=True)
        with tempfile.TemporaryDirectory() as work:
            tsv=Path(work)/'road.tsv'
            tsv.write_text(''.join('\t'.join(str(e[k]) for k in
                ('source','target','edge_id','time_s','length_m'))+'\n' for e in snap.directed_edges))
            native=road_index.NativeRoadIndex(tsv,('o','z','a','b','c'),cache_directory=work,
                                             pair_query_mode='landmark_astar')
            profile=CostProfile();profile.window_start=time.monotonic()
            provider=MeasuredProvider(native,profile)
            try:
                provider.prepare_landmarks('o','z')
                with instrument(profile):
                    actual=scale.solve_scale(snap,provider=provider,seed_beam_pruning=True)
                self.assertEqual(actual['key'],expected['key'])
                self.assertEqual(actual['seed']['key'],expected['seed']['key'])
                self.assertEqual(actual['metrics'],expected['metrics'])
                self.assertGreater(profile.summary()['routing']['settled_vertices'],0)
                def stop():raise scale.ResourceLimit('time_limit')
                provider.check=stop
                with self.assertRaises(scale.ResourceLimit):provider.selected_leg('o','a')
                self.assertEqual(profile.events[-1]['outcome'],'interrupted')
            finally:provider.close()


if __name__=='__main__':unittest.main()
