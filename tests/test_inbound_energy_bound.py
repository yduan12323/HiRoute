"""Inbound-energy relaxation admissibility, coverage and full-key regressions."""
from fractions import Fraction as F
from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
import test_scale_bounds as baseline_bounds
import test_scale_search as baseline_search
from hiroute.exact.interval import Interval
from hiroute.exact.pwa import AffineCutPiece
from hiroute.exact.scale_bounds import completion_bound,region_travel_lower_bounds
from hiroute.exact.road_index import RoadIndex
from hiroute.contracts import ProblemSnapshot
from hiroute.exact import scale

class InboundEnergyBoundTests(unittest.TestCase):
    def bound(self,pieces,threshold,**changes):
        options=dict(start_time=0,travel_time=7,drive_energy=0,reserve=0,
            overhead=1,stop_penalty=2,charge_slope=0,service_duration=0,
            inbound_energy=threshold)
        options.update(changes)
        return completion_bound(pieces,**options)

    def piece(self,domain,slope=1,intercept=0,remaining=0,attained=True):
        return AffineCutPiece(domain,F(slope),F(intercept),attained,
                              state_key=('a',remaining,0))

    def test_clipped_minimum_and_charge_service_kink(self):
        p=self.piece(Interval(0,10),remaining=1)
        self.assertEqual(self.bound((p,),0,drive_energy=7,reserve=1,
            charge_slope=2,service_duration=4),20)
        self.assertEqual(self.bound((p,),7,drive_energy=7,reserve=1,
            charge_slope=2,service_duration=4),21)
        self.assertEqual(self.bound((p,),10,drive_energy=7,reserve=1,
            charge_slope=2,service_duration=4),24)
        self.assertIsNone(self.bound((p,),11))

    def test_union_negative_slope_strict_exclusion_and_endpoint_limits(self):
        low=self.piece(Interval(0,4))
        high=self.piece(Interval(6,8),slope=-1,intercept=20)
        self.assertEqual(self.bound((low,high),5),22)
        self.assertIsNone(self.bound((low,),5))
        for closed in (False,True):
            p=self.piece(Interval(0,4,False,closed),attained=False)
            self.assertEqual(self.bound((p,),4),14)
            self.assertIs(p.attained,False)
            self.assertEqual(p.domain.right_closed,closed)
            self.assertEqual(p.domain.lo,0)
            self.assertEqual(p.domain.hi,4)

    def test_relative_time_translation_and_nonnegative_contract(self):
        original=self.piece(Interval(2,8),slope=-1,intercept=20,remaining=1)
        for shift in (-100,200):
            moved=self.piece(original.domain,slope=-1,intercept=20+shift,remaining=1)
            self.assertEqual(self.bound((original,),5,service_duration=4),
                             self.bound((moved,),5,start_time=shift,service_duration=4))
        with self.assertRaises(ValueError):self.bound((),-1)

    def test_directed_region_inbound_lower_bound_and_singleton_information(self):
        fixture=baseline_bounds.SummaryRegionTests();fixture.setUp()
        for region in fixture.walk(fixture.root):
            for effect,mask in region.effect_masks.items():
                for anchor in fixture.nodes[:-1]:
                    travel,remaining=region_travel_lower_bounds(region,effect,fixture.features[anchor])
                    inbound=remaining-region.summaries[effect].min_to_destination_distance
                    self.assertGreaterEqual(inbound,0)
                    for index,site in enumerate(fixture.sites):
                        d=fixture.metrics[1][anchor,site]
                        if mask & (1<<index) and d is not None:
                            self.assertLessEqual(inbound,d)
        fixture.test_refinement_is_complete_and_disjoint_for_every_effect()
        fixture.test_singleton_and_region_share_information()

    def test_no_seed_energy_empty_screen_keeps_capacity_equality_and_full_key(self):
        edge=baseline_search.edge
        source=baseline_search.raw(initial_energy_kwh='2',capacity_kwh='2',depth_limit=2,
            candidate_order=['a','b','far'],site_capabilities={s:['C'] for s in ('a','b','far')},
            charging_curve=[['0','2','1','0']],directed_edges=[edge('o','a',length=2),
            edge('a','b',length=2),edge('b','z',length=2),edge('o','far',length=10),edge('far','z')])
        snapshot=ProblemSnapshot.from_dict(source)
        class Trace(RoadIndex):
            def __init__(self):super().__init__(snapshot.directed_edges);self.requests=[]
            def selected_leg(self,a,b):self.requests.append((a,b));return super().selected_leg(a,b)
        from unittest.mock import patch
        for method in baseline_search.METHODS:
            provider=Trace()
            with patch.object(scale,'deterministic_seed',return_value=(None,0)):
                r=scale.solve_scale(snapshot,method=method,provider=provider,inbound_energy_bound=True)
            self.assertEqual(r['status'],'attained_optimum')
            self.assertEqual(r['key'],(11,4,2,(('a','C'),('b','C'))))
            self.assertFalse(any(b=='far' for a,b in provider.requests))
            self.assertIn(('o','a'),provider.requests)
            self.assertIn(('a','b'),provider.requests)


    def test_full_key_unattainment_service_translation_and_replay_parity(self):
        import json
        cases=json.loads((ROOT/'tests/fixtures/milestone_5_reference/frozen_cases_v2.json').read_text())
        sources=[baseline_search.frozen_snapshot(cases[i]) for i in (5,6,7,8,14)]
        e=baseline_search.edge
        sources.append(baseline_search.raw(initial_energy_kwh='1',capacity_kwh='6',
            minimum_energy_kwh='0',destination_reserve_kwh='4',depth_limit=1,
            candidate_order=['a'],site_capabilities={'a':['C']},
            charging_curve=[['0','6','1','0']],directed_edges=[e('o','a'),e('a','z')]))
        for shift in (-50,0,100):
            sources.append(baseline_search.raw(initial_energy_kwh='1',capacity_kwh='5',
                departure_time_s=str(shift),stop_penalty_s='0',candidate_order=['a'],
                site_capabilities={'a':['C','S','CS']},charging_curve=[['0','5','1','0']],
                depth_limit=1,schedule={'a':str(10+shift),'b':str(20+shift),'D':'3'},
                initial_remaining_schedule=1,directed_edges=[e('o','a'),e('a','z')]))
        for source in sources:
            snapshot=ProblemSnapshot.from_dict(source)
            expected=baseline_search.solve_snapshot(snapshot,baseline_search.old_config())
            for method in baseline_search.METHODS:
                actual=scale.solve_scale(snapshot,method=method,inbound_energy_bound=True)
                self.assertEqual(baseline_search.semantics(actual),baseline_search.semantics(expected))
                if actual['status']=='attained_optimum':
                    checked=baseline_search.verify_scale_witness(snapshot,actual)
                    self.assertEqual(checked['independent_key'],actual['key'])

    def test_exhaustive_tiny_physical_continuation_admissibility(self):
        import itertools
        from hiroute.exact.pipeline import initial_piece,DriveStep,StopStep,execute_exact_plan
        from hiroute.exact.terminal import terminal_optimize
        distance={('o','a'):2,('o','b'):4,('a','a'):0,('b','b'):0,
            ('a','b'):2,('b','a'):1,('a','z'):5,('b','z'):3}
        checked_total=0
        for pending,energy,first in itertools.product((0,1),(2,3,6),('a','b')):
            root=initial_piece(Interval(energy,energy),anchor='o',remaining_schedule=pending,rho=-energy)
            remaining=distance['o',first]+distance[first,'z']
            bound=self.bound((root,),distance['o',first],travel_time=remaining,
                drive_energy=remaining,reserve=1,charge_slope=2,service_duration=4)
            for count in (1,2,3):
                for tail in itertools.product(('a','b'),repeat=count-1):
                    sites=(first,)+tail
                    for effects in itertools.product(('C','S','CS'),repeat=count):
                        if sum(x in ('S','CS') for x in effects)!=pending:continue
                        steps=[];anchor='o'
                        for site,effect in zip(sites,effects):
                            d=distance[anchor,site]
                            steps.extend((DriveStep(site,F(d),F(d),F(0)),
                                StopStep(effect,site,F(1),((F(0),F(6),F(2),F(0)),),F(0),F(100),F(4))))
                            anchor=site
                        d=distance[anchor,'z'];steps.append(DriveStep('z',F(d),F(d),F(0)))
                        terminal=terminal_optimize(execute_exact_plan((root,),steps),'z',1,0,2)
                        value=(terminal.primary_infimum if terminal.status=='primary_unattained'
                               else terminal.primary_value)
                        if value is not None:
                            checked_total+=1
                            self.assertIsNotNone(bound)
                            self.assertLessEqual(bound,value)
            if energy<distance['o',first]:self.assertIsNone(bound)
        self.assertGreater(checked_total,0)


    def test_invalid_boolean_contract_is_rejected_before_index_loading(self):
        from unittest.mock import patch
        snapshot=ProblemSnapshot.from_dict(baseline_search.raw())
        with patch('hiroute.exact.road_index.RoadIndex',side_effect=AssertionError('loaded invalid input')):
            for flag in (None,0,1,'true',1.5):
                with self.assertRaisesRegex(ValueError,'inbound_energy_bound'):
                    scale.solve_scale(snapshot,inbound_energy_bound=flag)

    def test_relevant_depth_and_strict_incumbent_equality_are_preserved(self):
        edge=baseline_search.edge
        sites=[f'c{i}' for i in range(6)];nodes=['o']+sites+['z']
        sources=[baseline_search.raw(initial_energy_kwh='2',capacity_kwh='2',
            stop_overhead_s='10',stop_penalty_s='10',candidate_order=sites,
            site_capabilities={s:['C'] for s in sites},charging_curve=[['0','2','1','0']],
            depth_mode='unrestricted',depth_limit=0,
            directed_edges=[edge(a,b,length=2) for a,b in zip(nodes,nodes[1:])]),
            baseline_search.raw(initial_energy_kwh='1',capacity_kwh='5',stop_penalty_s='0',
            candidate_order=['a','b'],site_capabilities={'a':['C'],'b':['C']},depth_limit=1,
            charging_curve=[['0','5','1','0']],directed_edges=[edge('o','a'),
                edge('a','z',length=3),edge('o','b',time=2),edge('b','z',time=2)])]
        for index,source in enumerate(sources):
            snapshot=ProblemSnapshot.from_dict(source)
            for method in baseline_search.METHODS:
                control=scale.solve_scale(snapshot,method=method,inbound_energy_bound=False)
                actual=scale.solve_scale(snapshot,method=method,inbound_energy_bound=True)
                self.assertEqual(baseline_search.semantics(actual),baseline_search.semantics(control))
                self.assertEqual(actual['depth_contract'],control['depth_contract'])
                if index==0:
                    self.assertEqual(actual['key'][:3],(139,12,6))
                    self.assertGreaterEqual(actual['metrics']['max_depth'],6)
                else:
                    self.assertEqual(actual['key'],(6,1,1,(('b','C'),)))
                    self.assertGreater(actual['metrics']['equality_retained'],0)


    def test_selected_fastest_length_rejects_late_without_claiming_avoided_route(self):
        from unittest.mock import patch
        edge=baseline_search.edge
        source=baseline_search.raw(initial_energy_kwh='2',capacity_kwh='2',depth_limit=1,
            candidate_order=['a'],site_capabilities={'a':['C']},charging_curve=[['0','2','1','0']],
            directed_edges=[edge('o','a',time=1,length=10),edge('o','x',time=2,length=1),
                edge('x','a',time=2,length=1),edge('a','z')])
        snapshot=ProblemSnapshot.from_dict(source)
        for method in baseline_search.METHODS:
            results=[]
            for enabled,use_bound in ((False,True),(True,True),(True,False)):
                with patch.object(scale,'deterministic_seed',return_value=(None,0)):
                    r=scale.solve_scale(snapshot,method=method,inbound_energy_bound=enabled,
                                        use_bound=use_bound)
                results.append(r)
            self.assertEqual([baseline_search.semantics(x) for x in results],
                             [baseline_search.semantics(results[0])]*3)
            old,refined,ablation=results
            self.assertEqual(refined['metrics']['inbound_energy_late_empty_actions'],1)
            self.assertEqual(refined['metrics']['inbound_energy_pruned_actions'],0)
            self.assertEqual(refined['metrics']['leaf_routes'],old['metrics']['leaf_routes'])
            for key in ('inbound_energy_pruned_regions','inbound_energy_pruned_actions',
                        'inbound_energy_late_empty_actions'):
                self.assertEqual(old['metrics'][key],0)
                self.assertEqual(ablation['metrics'][key],0)

    def test_summary_query_needs_only_static_extrema(self):
        fixture=baseline_bounds.SummaryRegionTests();fixture.setUp()
        class NoTraversal:
            summaries=fixture.root.summaries
            def __getattr__(self,name):
                raise AssertionError('summary query traversed '+name)
        for effect in fixture.root.summaries:
            travel,remaining=region_travel_lower_bounds(NoTraversal(),effect,fixture.features['o'])
            inbound=remaining-NoTraversal.summaries[effect].min_to_destination_distance
            p=self.piece(Interval(0,20))
            self.assertIsNotNone(self.bound((p,),inbound,travel_time=travel,drive_energy=remaining))


    def test_positive_arrival_floor_and_independent_tiny_reference(self):
        from unittest.mock import patch
        from hiroute_ref.cli import snapshot_case
        from hiroute_ref.solver import solve_case
        edge=baseline_search.edge
        source=baseline_search.raw(initial_energy_kwh='4',capacity_kwh='4',
            minimum_energy_kwh='2',destination_reserve_kwh='2',depth_limit=1,
            candidate_order=['a','far'],site_capabilities={'a':['C'],'far':['C']},
            charging_curve=[['0','4','1','0']],directed_edges=[edge('o','a',length=2),
                edge('a','z',length=2),edge('o','far',length=3),edge('far','z',length=2)])
        snapshot=ProblemSnapshot.from_dict(source)
        independent,_=snapshot_case(source)
        ref=solve_case(independent,keep_evidence=False)['result']
        self.assertEqual(ref['status'],'attained_optimum')
        class Trace(RoadIndex):
            def __init__(self):super().__init__(snapshot.directed_edges);self.requests=[]
            def selected_leg(self,a,b):self.requests.append((a,b));return super().selected_leg(a,b)
        for method in baseline_search.METHODS:
            provider=Trace()
            with patch.object(scale,'deterministic_seed',return_value=(None,0)):
                actual=scale.solve_scale(snapshot,method=method,provider=provider,inbound_energy_bound=True)
            self.assertEqual(actual['key'],ref['lex_key'])
            self.assertNotIn(('o','far'),provider.requests)
            self.assertIn(('o','a'),provider.requests)
            self.assertGreater(actual['metrics']['inbound_energy_pruned_actions'],0)

if __name__=='__main__':unittest.main()
