"""Strict incumbent enqueue pruning: semantics, ordering and resource regressions."""
from pathlib import Path
import json,sys,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
import test_scale_search as helpers
from hiroute.contracts import ProblemSnapshot
from hiroute.exact import scale,scale_bounds

class EnqueuePruningTests(unittest.TestCase):
    def source(self):
        sites=[f'c{i}' for i in range(4)]
        return helpers.raw(candidate_order=sites,site_capabilities={s:['C'] for s in sites},
            charging_curve=[['0','10','1','0']],depth_limit=1,
            directed_edges=[helpers.edge('o','z',time=20)]+[
                e for s in sites for e in (helpers.edge('o',s,time=100),helpers.edge(s,'z',time=100))])

    def test_existing_attained_upper_bound_rejects_strict_losers_before_heap(self):
        snap=ProblemSnapshot.from_dict(self.source())
        for method in helpers.METHODS:
            out=[]
            for eager in (False,True):
                with patch.object(scale,'deterministic_seed',return_value=(None,0)):
                    out.append(scale.solve_scale(snap,method=method,inbound_energy_bound=True,
                                                 eager_incumbent_pruning=eager))
            old,new=out
            self.assertEqual(helpers.semantics(new),helpers.semantics(old))
            self.assertEqual(new['key'],(20,0,0,()))
            self.assertGreater(new['metrics']['enqueue_pruned_nodes'],0)
            self.assertEqual(new['metrics']['pruned_regions'],0)
            self.assertEqual(new['metrics']['leaf_routes'],old['metrics']['leaf_routes'])
            self.assertLessEqual(new['metrics']['peak_open'],old['metrics']['peak_open'])
            self.accounting(old);self.accounting(new)

    def test_equal_primary_and_unattained_faces_keep_full_key_semantics(self):
        cases=json.loads((ROOT/'tests/fixtures/milestone_5_reference/frozen_cases_v2.json').read_text())
        sources=[helpers.frozen_snapshot(cases[i]) for i in (5,6,7,8,14)]
        e=helpers.edge
        sources.append(helpers.raw(initial_energy_kwh='1',capacity_kwh='5',stop_penalty_s='0',
            candidate_order=['a','b'],site_capabilities={'a':['C'],'b':['C']},depth_limit=1,
            charging_curve=[['0','5','1','0']],directed_edges=[e('o','a'),e('a','z',length=3),
                e('o','b',time=2),e('b','z',time=2)]))
        for src in sources:
            snap=ProblemSnapshot.from_dict(src)
            for method in helpers.METHODS:
                old=scale.solve_scale(snap,method=method,inbound_energy_bound=True)
                new=scale.solve_scale(snap,method=method,inbound_energy_bound=True,
                                      eager_incumbent_pruning=True)
                self.assertEqual(helpers.semantics(new),helpers.semantics(old))
                self.assertEqual(new['depth_contract'],old['depth_contract'])

    def test_final_rejection_cannot_hide_a_crossed_resource_deadline(self):
        snap=ProblemSnapshot.from_dict(self.source())
        original=scale_bounds.completion_bound
        for method in helpers.METHODS:
            clock={'now':0}
            def delayed(*a,**kw):
                value=original(*a,**kw);clock['now']=2;return value
            with patch.object(scale,'deterministic_seed',return_value=(None,0)),patch.object(
                    scale_bounds,'completion_bound',side_effect=delayed):
                row=scale.solve_scale(snap,method=method,time_limit_s=1,
                    _clock=lambda:clock['now'],inbound_energy_bound=True,eager_incumbent_pruning=True)
            self.assertEqual(row['status'],'time_limit')
            self.assertEqual(row['mathematical_status'],'unknown')
            self.assertEqual(row['incumbent']['key'],(20,0,0,()))
            self.assertEqual(row['open_remaining'],0)
            self.accounting(row)


    def accounting(self,row):
        m=row['metrics']
        self.assertEqual(m['enqueue_attempts'],m['heap_pushes']+m['enqueue_pruned_nodes'])
        self.assertEqual(m['enqueue_pruned_nodes'],m['enqueue_pruned_regions']+m['enqueue_pruned_states'])
        self.assertEqual(m['heap_pushes']-m['heap_pops'],row['open_remaining'])

    def test_boolean_contract_fails_before_index_loading(self):
        snap=ProblemSnapshot.from_dict(self.source())
        with patch('hiroute.exact.road_index.RoadIndex',side_effect=AssertionError('invalid flag loaded index')):
            for value in (None,0,1,'true',1.5):
                with self.assertRaisesRegex(ValueError,'eager_incumbent_pruning'):
                    scale.solve_scale(snap,eager_incumbent_pruning=value)

    def test_pop_pruning_still_handles_later_improved_incumbent_and_order(self):
        e=helpers.edge
        source=helpers.raw(initial_energy_kwh='1',capacity_kwh='5',depth_limit=1,
            candidate_order=['a','b','c','d'],site_capabilities={s:['C'] for s in ('a','b','c','d')},
            charging_curve=[['0','5','1','0']],directed_edges=[e('o','a'),e('a','z',length=4),
                e('o','b',time=2),e('b','z',time=2),e('o','c',time=3),e('c','z',time=2),
                e('o','d',time=100),e('d','z',time=100)])
        full=ProblemSnapshot.from_dict(source)
        restricted=ProblemSnapshot.from_dict(dict(source,candidate_order=['a'],site_capabilities={'a':['C']}))
        one=scale.solve_scale(restricted)
        seed={k:one[k] for k in ('key','plan','legs','replay')}
        self.assertEqual(seed['key'][0],8)
        helpers.verify_scale_witness(full,seed)
        original_terminal,original_extend=scale.terminal_attempt,scale.extend_prefix
        from hiroute.exact.road_index import RoadIndex
        class Trace(RoadIndex):
            def __init__(self):super().__init__(full.directed_edges);self.requests=[]
            def selected_leg(self,a,b):self.requests.append((a,b));return super().selected_leg(a,b)
        for method in helpers.METHODS:
            observations=[]
            for eager in (False,True):
                terminal_order=[];transition_order=[];incumbents=[];provider=Trace()
                pushed=[];popped=[]
                original_push,original_pop=scale.heapq.heappush,scale.heapq.heappop
                def signature(item):
                    if len(item)!=6 or item[2] not in ('state','region'):return None
                    lower,_,kind,state,region,effect=item
                    return (lower,kind,state.plan,None if region is None else region.identifier,effect)
                def push(queue,item):
                    key=signature(item)
                    if key is not None:pushed.append(key)
                    return original_push(queue,item)
                def pop(queue):
                    item=original_pop(queue);key=signature(item)
                    if key is not None:popped.append(key)
                    return item
                def terminal(snapshot,state,*a,**kw):
                    terminal_order.append(state.plan);return original_terminal(snapshot,state,*a,**kw)
                def extend(snapshot,state,site,effect,*a,**kw):
                    transition_order.append((state.plan,site,effect));return original_extend(snapshot,state,site,effect,*a,**kw)
                with patch.object(scale,'deterministic_seed',return_value=(seed,0)),patch.object(
                        scale,'terminal_attempt',side_effect=terminal),patch.object(scale,'extend_prefix',side_effect=extend),patch.object(
                        scale.heapq,'heappush',side_effect=push),patch.object(scale.heapq,'heappop',side_effect=pop):
                    row=scale.solve_scale(full,method=method,provider=provider,inbound_energy_bound=True,
                        eager_incumbent_pruning=eager,on_incumbent=lambda r:incumbents.append(r['key']))
                self.accounting(row)
                self.assertEqual([key[0] for key in incumbents],[8,7])
                self.assertGreater(row['metrics']['pruned_regions'],0)
                observations.append((helpers.semantics(row),terminal_order,transition_order,provider.requests,pushed,popped))
            old,new=observations
            self.assertEqual(old[:4],new[:4])
            retained=set(new[4])
            self.assertEqual([key for key in old[4] if key in retained],new[4])
            self.assertEqual([key for key in old[5] if key in retained],new[5])
            self.assertGreater(sum(key[0]==8 for key in new[4]),1)

    def test_open_infimum_is_never_an_enqueue_upper_bound(self):
        e=helpers.edge
        snap=ProblemSnapshot.from_dict(helpers.raw(initial_energy_kwh='2',capacity_kwh='2',
            depth_limit=2,candidate_order=['a','b'],site_capabilities={'a':['CS'],'b':['C']},
            charging_curve=[['0','2','1','0']],schedule={'a':'0','b':'100','D':'0'},
            initial_remaining_schedule=1,directed_edges=[e('o','a'),e('a','z'),
                e('a','b',length=2),e('b','z')]))
        for method in helpers.METHODS:
            rows=[]
            for eager in (False,True):
                with patch.object(scale,'deterministic_seed',return_value=(None,0)):
                    row=scale.solve_scale(snap,method=method,inbound_energy_bound=True,
                                          eager_incumbent_pruning=eager)
                self.accounting(row)
                self.assertEqual(row['status'],'primary_unattained')
                self.assertIsNotNone(row['incumbent'])
                self.assertGreater(row['incumbent']['key'][0],row['primary_infimum'])
                helpers.verify_scale_witness(snap,row['incumbent'])
                rows.append(row)
            self.assertEqual(helpers.semantics(rows[0]),helpers.semantics(rows[1]))
            self.assertEqual(rows[0]['incumbent']['key'],rows[1]['incumbent']['key'])

    def test_inbound_none_actions_and_unrestricted_depth_keep_accounting(self):
        e=helpers.edge
        sites=[f'c{i}' for i in range(6)];nodes=['o']+sites+['z']
        source=helpers.raw(initial_energy_kwh='2',capacity_kwh='2',stop_overhead_s='10',
            stop_penalty_s='10',candidate_order=sites,site_capabilities={s:['C'] for s in sites},
            charging_curve=[['0','2','1','0']],depth_mode='unrestricted',depth_limit=0,
            directed_edges=[e(a,b,length=2) for a,b in zip(nodes,nodes[1:])])
        snap=ProblemSnapshot.from_dict(source)
        for method in helpers.METHODS:
            rows=[]
            for eager in (False,True):
                row=scale.solve_scale(snap,method=method,inbound_energy_bound=True,
                                      eager_incumbent_pruning=eager)
                self.accounting(row)
                self.assertEqual(row['key'][:3],(139,12,6))
                self.assertGreaterEqual(row['metrics']['max_depth'],6)
                self.assertGreater(row['metrics']['inbound_energy_pruned_actions'],0)
                rows.append(row)
            self.assertEqual(helpers.semantics(rows[0]),helpers.semantics(rows[1]))
            self.assertEqual(rows[0]['depth_contract'],rows[1]['depth_contract'])


    def test_equal_primary_must_retain_better_secondary_than_valid_seed(self):
        e=helpers.edge
        source=helpers.raw(initial_energy_kwh='1',capacity_kwh='5',stop_penalty_s='0',
            candidate_order=['a','b'],site_capabilities={'a':['C'],'b':['C']},depth_limit=1,
            charging_curve=[['0','5','1','0']],directed_edges=[e('o','a'),e('a','z',length=3),
                e('o','b',time=2),e('b','z',time=2)])
        snap=ProblemSnapshot.from_dict(source)
        restricted=ProblemSnapshot.from_dict(dict(source,candidate_order=['a'],site_capabilities={'a':['C']}))
        one=scale.solve_scale(restricted)
        seed={k:one[k] for k in ('key','plan','legs','replay')}
        self.assertEqual(seed['key'],(6,3,1,(('a','C'),)))
        helpers.verify_scale_witness(snap,seed)
        for method in helpers.METHODS:
            with patch.object(scale,'deterministic_seed',return_value=(seed,0)):
                row=scale.solve_scale(snap,method=method,inbound_energy_bound=True,
                                      eager_incumbent_pruning=True)
            self.assertEqual(row['key'],(6,1,1,(('b','C'),)))
            self.assertGreater(row['metrics']['equality_retained'],0)
            self.accounting(row)

if __name__=='__main__':unittest.main()
