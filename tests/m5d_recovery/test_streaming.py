"""Bounded five-node regression fixtures, no production inputs/native binary."""
import contextlib, io, json, os, resource, subprocess, sys, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch
from fractions import Fraction
ROOT=Path(__file__).parent.resolve()
sys.path[:0] = [str(ROOT), str(ROOT.parents[1])]
from timecut5 import deployable, sparse_seed
helpers={'__name__':'fixture_helpers','__file__':str(ROOT/'baseline_fixture_probe.py')}
with patch.object(sys,'argv',['fixture_probe.py','disabled']):
    exec((ROOT/'baseline_fixture_probe.py').read_text().split('results=[]')[0],helpers)

class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
    def fixture(self,index): return helpers['fixture'](index,self.root)
    def test_iterator_matches_tuple_and_observer_is_observation_only(self):
        for index in range(48):
            q,c,_=self.fixture(index)
            self.assertEqual(tuple(deployable.iter_constructive_seed_candidates(q,c)),deployable.constructive_seed_candidates(q,c))
            expected=sparse_seed.admit_sparse_seed(q,c)
            events=[]
            def observer(event,**snapshot):
                events.append((event,dict(snapshot)))
                if event=='incumbent':
                    replay=sparse_seed.replay_sparse_seed(q,c,snapshot['sequence'],snapshot['charges'])
                    self.assertEqual(snapshot['lex_key'],replay['lex_key'])
                    self.assertFalse(snapshot['generation_complete'])
                    self.assertFalse(snapshot['exact_optimum_claimed'])
                snapshot.clear() # callback cannot mutate algorithm's counters or winner
            self.assertEqual(expected,sparse_seed.admit_sparse_seed(q,c,observer=observer))
            self.assertEqual(events[0][0],'generation_begin')
            end=next(s for e,s in events if e=='generation_end')
            self.assertEqual(end['proposal_count'],expected['proposal_count'])
            self.assertTrue(end['generation_complete'])
    def test_accepted_then_generation_interrupted_is_not_final_seed(self):
        q,c,_=self.fixture(6)
        proposals=deployable.constructive_seed_candidates(q,c)
        valid=next(p for p in proposals if self.feasible(q,c,p))
        failure=RuntimeError('generation interrupted after feasible candidate')
        events=[]
        def interrupted(*args):
            yield valid
            self.assertIn('incumbent',[e for e,s in events])
            raise failure
        with patch.object(deployable,'iter_constructive_seed_candidates',interrupted):
            with self.assertRaises(RuntimeError) as caught:
                sparse_seed.admit_sparse_seed(q,c,observer=lambda e,**s:events.append((e,s)))
        self.assertIs(caught.exception,failure)
        self.assertNotIn('generation_end',[e for e,s in events])
        self.assertNotIn('seed_verified',[e for e,s in events])
    @staticmethod
    def feasible(q,c,p):
        try: sparse_seed.replay_sparse_seed(q,c,*p); return True
        except sparse_seed.SeedInfeasible: return False
    def test_rejected_candidates_are_counted_and_skipped(self):
        q,c,_=self.fixture(6)
        valid=next(p for p in deployable.constructive_seed_candidates(q,c) if self.feasible(q,c,p))
        invalid=((("missing","C"),),(Fraction(1),))
        events=[]
        with patch.object(deployable,'iter_constructive_seed_candidates',return_value=iter([invalid,valid,invalid])):
            result=sparse_seed.admit_sparse_seed(q,c,observer=lambda e,**s:events.append((e,s)))
        self.assertEqual(result['proposal_count'],3);self.assertEqual(result['accepted_count'],1)
        self.assertEqual(sum(e=='replay_rejected' for e,s in events),2)
    def test_no_accepted_proposals(self):
        q,c,_=self.fixture(6)
        with patch.object(deployable,'iter_constructive_seed_candidates',return_value=iter([])):
            self.assertEqual(sparse_seed.admit_sparse_seed(q,c)['status'],'incumbent_search_failed')
    def test_actual_generator_yields_before_later_routing_and_closes(self):
        q,c,router=self.fixture(6)
        stream=deployable.iter_constructive_seed_candidates(q,c)
        self.assertEqual(router.calls,[])
        proposal=next(stream)
        self.assertEqual(proposal,((),()))
        self.assertEqual(len(router.calls),1)
        sparse_seed.replay_sparse_seed(q,c,*proposal)
        stream.close()
        self.assertEqual(len(router.calls),1)
    def test_same_lex_key_uses_original_charges_tie_break(self):
        q,c,_=self.fixture(6)
        sequence=(("1","C"),("2","C"))
        proposals=[(sequence,(Fraction(2),Fraction(1))),
                   (sequence,(Fraction(1),Fraction(2)))]
        key=(Fraction(10),Fraction(3),2,sequence)
        with patch.object(deployable,'iter_constructive_seed_candidates',return_value=iter(proposals)), \
             patch.object(sparse_seed,'replay_sparse_seed',return_value={'lex_key':key,'edge_witnesses':()}):
            result=sparse_seed.admit_sparse_seed(q,c)
        self.assertEqual(result['charges'],min((key,*p) for p in proposals)[2])
    def test_streaming_diagnostic_complete_and_partial(self):
        from timecut5.streaming_seed_diagnostic import observe_streaming_seed, digest
        q,c,_=self.fixture(6)
        proposals=deployable.constructive_seed_candidates(q,c)
        result=observe_streaming_seed(q,c,output_dir=self.root/'complete',provenance={'fixture':6},max_journal_events=4)
        state=json.loads((self.root/'complete/snapshot.json').read_text())
        self.assertEqual(state['ordered_proposal_sha256'],digest(proposals))
        self.assertEqual(state['proposal_count'],result['proposal_count'])
        self.assertEqual(state['replay_attempts'],len(proposals))
        self.assertEqual(state['accepted_count'],result['accepted_count'])
        self.assertEqual(state['accepted_count']+state['rejected_count'],len(proposals))
        self.assertLessEqual(len((self.root/'complete/progress.jsonl').read_text().splitlines()),4)
        self.assertTrue(state['generation_complete']);self.assertEqual(state['status'],'complete')
        def interrupted(*args):
            yield ((),())
            raise RuntimeError('interrupted stream')
        with patch.object(deployable,'iter_constructive_seed_candidates',interrupted):
            with self.assertRaisesRegex(RuntimeError,'interrupted stream'):
                observe_streaming_seed(q,c,output_dir=self.root/'partial',provenance={})
        partial=json.loads((self.root/'partial/snapshot.json').read_text())
        self.assertIsNone(partial['ordered_proposal_sha256'])
        self.assertFalse(partial['generation_complete'])
        self.assertEqual(partial['status'],'error')
        self.assertIsNotNone(partial['provisional_incumbent'])
        self.assertNotEqual(partial['run_id'],state['run_id'])
    def test_diagnostic_failure_keeps_original_exception(self):
        from timecut5.streaming_seed_diagnostic import observe_streaming_seed, StreamingSeedObserver
        q,c,_=self.fixture(101)
        with patch.object(StreamingSeedObserver,'finish',side_effect=OSError('disk full')):
            with self.assertRaisesRegex(RuntimeError,'fixture native failure') as caught:
                observe_streaming_seed(q,c,output_dir=self.root/'broken',provenance={})
        self.assertTrue(any('disk full' in note for note in caught.exception.__notes__))
    def test_active_timers_exclude_replay_and_observer_work(self):
        q,c,_=self.fixture(6); tick=[0];events=[]
        def stream(*args):
            tick[0]+=10;yield ((),())
            tick[0]+=10;yield ((),())
            tick[0]+=10
        real_replay=sparse_seed.replay_sparse_seed
        def replay(*args,**kwargs):
            tick[0]+=100;return real_replay(*args,**kwargs)
        def observer(event,**data):
            events.append((event,data));tick[0]+=1000
        with patch.object(deployable,'iter_constructive_seed_candidates',stream), \
             patch.object(sparse_seed,'replay_sparse_seed',replay), \
             patch.object(sparse_seed.time,'monotonic_ns',lambda:tick[0]):
            sparse_seed.admit_sparse_seed(q,c,observer=observer)
        self.assertEqual(sum(d['wall_ns'] for e,d in events if e=='generation_step'),30)
        self.assertEqual(sum(d['wall_ns'] for e,d in events if e=='replay_step'),200)
        self.assertEqual(sum(d['wall_ns'] for e,d in events if e=='fresh_replay_step'),100)
    def test_eager_exception_and_lazy_exception_same(self):
        q,c,_=self.fixture(100)
        with self.assertRaises(ValueError) as eager: deployable.constructive_seed_candidates(q,c)
        stream=deployable.iter_constructive_seed_candidates(q,c)
        with self.assertRaises(ValueError) as lazy: next(stream)
        self.assertEqual(str(eager.exception),str(lazy.exception))
    def test_source_and_observer_failures_are_fatal(self):
        for index in [101,102]:
            q,c,_=self.fixture(index)
            with self.assertRaises((ValueError,RuntimeError)): sparse_seed.admit_sparse_seed(q,c)
        q,c,_=self.fixture(6); failure=OSError('observer failed')
        def fail(*args,**kwargs): raise failure
        with self.assertRaises(OSError) as caught: sparse_seed.admit_sparse_seed(q,c,observer=fail)
        self.assertIs(caught.exception,failure)

if __name__=='__main__':
    started=time.process_time(); before=resource.getrusage(resource.RUSAGE_CHILDREN)
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    after=resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu=time.process_time()-started+after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime
    summary={'successful':result.wasSuccessful(),'test_count':result.testsRun,'cpu_seconds_including_children':cpu,'test_cpu_limit_seconds':60,'real_od_runs':0}
    (ROOT/'TEST_RESULTS.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary));sys.exit(not result.wasSuccessful())
