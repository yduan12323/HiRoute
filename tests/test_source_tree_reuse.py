"""Exact source-time reuse: no real graph enumeration or performance oracle."""
from __future__ import annotations
import itertools,json,os,random,shutil,sys,tempfile,unittest
from fractions import Fraction
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from test_scale_road_index import row,independent_paths
from test_scale_search import frozen_snapshot,semantics
from hiroute.contracts import ProblemSnapshot
from hiroute.exact import scale
from hiroute.exact.road_index import NativeRoadIndex,RoadIndex


def export(path,edges):
    path.write_text(''.join('\t'.join(str(e[k]) for k in
        ('source','target','edge_id','time_s','length_m'))+'\n' for e in edges))


class SourceTreeReuseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        roots=[Path('/usr/include'),Path('/usr/local/include'),Path('/opt/homebrew/include')]
        roots += [Path(p) for p in os.environ.get('CPLUS_INCLUDE_PATH','').split(os.pathsep) if p]
        cls.available=bool(shutil.which('c++')) and any((p/'boost/multiprecision/cpp_int.hpp').exists() for p in roots)
        if not cls.available and os.environ.get('HIROUTE_REQUIRE_NATIVE_ROADS')=='1':
            raise RuntimeError('Source-tree CI requires C++17 and Boost headers')

    def test_invalid_mode_boolean_and_cache_contracts_fail_before_loading(self):
        with tempfile.TemporaryDirectory() as work:
            for values in (dict(source_tree_reuse=1),dict(source_tree_reuse=None),
                           dict(source_tree_reuse=True),
                           *(dict(source_tree_reuse=True,pair_query_mode='landmark_astar',
                                  distance_cache_size=n) for n in (0,1,3))):
                with self.subTest(values=values),self.assertRaisesRegex(ValueError,'source_tree_reuse'):
                    NativeRoadIndex('missing.tsv',(),cache_directory=work,**values)

    def test_lazy_work_trigger_two_slot_eviction_and_rebuild(self):
        if not self.available:return
        names=tuple(str(i) for i in range(8))
        edges=[row(a,b,1,1,a+':'+b) for a,b in itertools.permutations(names,2)]
        with tempfile.TemporaryDirectory() as work:
            path=Path(work)/'g.tsv';export(path,edges)
            with NativeRoadIndex(path,names,cache_directory=work,pair_query_mode='landmark_astar',
                                 source_tree_reuse=True,leg_cache_size=0) as native:
                native.prepare_landmarks('0','7')
                for source in ('1','2'):
                    before=native.metrics()['source_tree_builds']
                    native.selected_leg(source,'6');native.selected_leg(source,'6')
                    self.assertEqual(native.metrics()['source_tree_builds'],before)
                    self.assertEqual(native.selected_leg(source,'6').time_s,1)
                    self.assertEqual(native.metrics()['source_tree_builds'],before+1)
                native.selected_leg('1','6')  # LRU source 2, not source 1
                before=native.metrics()['source_tree_cache_hits']
                for _ in range(3):native.selected_leg('3','6')
                m=native.metrics()
                self.assertEqual(m['source_tree_builds'],3)
                self.assertEqual(m['source_tree_evictions'],1)
                self.assertEqual(m['source_tree_cache_entries'],2)
                self.assertEqual(m['distance_cache_entries'],2)
                native.selected_leg('1','6')
                self.assertEqual(native.metrics()['source_tree_cache_hits'],before+1)
                for _ in range(3):native.selected_leg('2','6')
                m=native.metrics()
                self.assertEqual(m['source_tree_builds'],4)
                self.assertEqual(m['source_tree_build_settled_vertices'],4*len(names))
                self.assertEqual(m['source_tree_build_relaxed_edges'],4*len(edges))
                self.assertLessEqual(m['source_tree_cache_entries'],2)
                # Ordinary scalar queries share the same slots and may evict a source.
                native.distances_to('0','length_m')
                self.assertEqual(native.metrics()['distance_cache_entries'],2)
                self.assertEqual(native.selected_leg('1','6').time_s,1)
            with NativeRoadIndex(path,names,cache_directory=work,pair_query_mode='landmark_astar',
                                 leg_cache_size=0) as legacy:
                legacy.prepare_landmarks('0','7')
                for _ in range(8):legacy.selected_leg('1','6')
                self.assertEqual(legacy.metrics()['source_tree_builds'],0)
                self.assertEqual(legacy.metrics()['source_tree_work_sources'],0)

    def test_exact_equality_contour_actual_length_and_random_directed_oracle(self):
        if not self.available:return
        rng=random.Random(9401);promotions=0
        with tempfile.TemporaryDirectory() as work:
            path=Path(work)/'g.tsv'
            # Source gets the first numeric ID and can settle before the tied
            # canonical intermediate. Equality must remain after promotion.
            edges=[row('0','z',2,1,'direct'),row('0','a',1,200,'pa'),
                   row('0','a',1,100,'pz'),row('a','z',1,100,'az'),
                   row('O','0',100,1,'O0'),row('O','a',1,1,'Oa'),row('z','D',1,1,'zD')]
            export(path,edges)
            with NativeRoadIndex(path,('0','z','a','O','D'),cache_directory=work,
                    pair_query_mode='landmark_astar',source_tree_reuse=True,leg_cache_size=0) as native:
                native.prepare_landmarks('O','D')
                for _ in range(8):
                    leg=native.selected_leg('0','z')
                    self.assertEqual(tuple(e['edge_id'] for e in leg.edges),('pa','az'))
                    self.assertEqual((leg.time_s,leg.length_m),(2,300))
                self.assertGreater(native.metrics()['source_tree_builds'],0)
            names=('0','a','z','é','中','Ω','u','v')
            for trial in range(12):
                inner=names[:6]
                edges=[row(a,b,Fraction(rng.randint(1,4),3),Fraction(rng.randint(1,12),7),f'{i}')
                       for i,(a,b) in enumerate(itertools.permutations(inner,2)) if rng.random()<.3]
                edges += [row(a,b,1,1,'chain'+str(i)) for i,(a,b) in enumerate(zip(inner,inner[1:]))]
                edges += [row('u','v',1,1,'other'),row('0','a',1,100,'parallel')]
                expected={(a,b):independent_paths(edges,a,b) for a,b in itertools.product(names,repeat=2)}
                export(path,edges)
                with NativeRoadIndex(path,names,cache_directory=work,pair_query_mode='landmark_astar',
                                     source_tree_reuse=True,leg_cache_size=0) as native:
                    native.prepare_landmarks('0','Ω')
                    for _ in range(3):
                        for (a,b),oracle in expected.items():
                            actual=native.selected_leg(a,b)
                            if oracle is None:self.assertIsNone(actual,(trial,a,b))
                            else:
                                self.assertEqual(tuple(e['edge_id'] for e in actual.edges),tuple(e['edge_id'] for e in oracle),(trial,a,b))
                                self.assertEqual(actual.time_s,sum(Fraction(e['time_s']) for e in oracle))
                                self.assertEqual(actual.length_m,sum(Fraction(e['length_m']) for e in oracle))
                    promotions+=native.metrics()['source_tree_builds']
                    self.assertLessEqual(native.metrics()['distance_cache_entries'],2)
            self.assertGreater(promotions,0)

    def test_interrupted_promotion_discards_partial_trees_and_work(self):
        if not self.available:return
        names=tuple(str(i) for i in range(300))
        edges=[row(a,b,1,1,a+':'+b) for a,b in itertools.permutations(names,2)]
        with tempfile.TemporaryDirectory() as work:
            path=Path(work)/'g.tsv';export(path,edges)
            with NativeRoadIndex(path,names,cache_directory=work,pair_query_mode='landmark_astar',
                                 source_tree_reuse=True,leg_cache_size=0) as native:
                native.prepare_landmarks('0','299')
                native.selected_leg('1','298');native.selected_leg('1','298')
                class Stop(Exception):pass
                calls=0
                def interrupt():
                    nonlocal calls
                    calls+=1
                    if calls==4:raise Stop
                native.check=interrupt
                with self.assertRaises(Stop):native.selected_leg('1','298')
                native.check=None;m=native.metrics()
                self.assertEqual(m['source_tree_build_attempts'],1)
                self.assertEqual(m['source_tree_builds'],0)
                self.assertGreater(m['source_tree_build_settled_vertices'],0)
                self.assertLess(m['source_tree_build_settled_vertices'],len(names))
                self.assertEqual(m['distance_cache_entries'],0)
                self.assertEqual(m['source_tree_work_sources'],0)
                native.prepare_landmarks('0','299')
                self.assertEqual(native.selected_leg('1','298').time_s,1)
                self.assertEqual(native.metrics()['source_tree_builds'],0)
                native.selected_leg('1','298');native.selected_leg('1','298')
                self.assertEqual(native.metrics()['source_tree_builds'],1)
                calls=0
                def during_dag():
                    nonlocal calls
                    calls+=1
                    if calls==3:raise Stop
                native.check=during_dag
                with self.assertRaises(Stop):native.selected_leg('1','298')
                native.check=None
                self.assertEqual(native.metrics()['distance_cache_entries'],0)
                native.prepare_landmarks('0','299')
                self.assertEqual(native.selected_leg('1','298').edges[0]['edge_id'],'1:298')

    def test_full_key_seed_and_unattainment_parity_on_finite_common_domains(self):
        if not self.available:return
        cases=json.loads((ROOT/'tests/fixtures/milestone_5_reference/frozen_cases_v2.json').read_text())
        with tempfile.TemporaryDirectory() as work:
            path=Path(work)/'g.tsv'
            for index in (5,6,7,8,14):
                snap=ProblemSnapshot.from_dict(frozen_snapshot(cases[index]))
                export(path,snap.directed_edges)
                names={snap.origin,snap.destination,*snap.candidate_order}
                for method in ('flat_bb_strong','scale'):
                    expected=scale.solve_scale(snap,method=method,seed_beam_pruning=True)
                    with NativeRoadIndex(path,names,cache_directory=work,pair_query_mode='landmark_astar',
                                         source_tree_reuse=True,leg_cache_size=0) as native:
                        native.prepare_landmarks(snap.origin,snap.destination)
                        actual=scale.solve_scale(snap,method=method,provider=native,seed_beam_pruning=True)
                        self.assertEqual(semantics(actual),semantics(expected),(index,method))
                        self.assertEqual(None if actual['seed'] is None else actual['seed']['key'],
                                         None if expected['seed'] is None else expected['seed']['key'])
                        self.assertEqual(actual['depth_contract'],expected['depth_contract'])


if __name__=='__main__':unittest.main()
