"""Independent completeness checks against real instrumented tiny-HIER runs."""
from copy import deepcopy
import json,os,subprocess,sys,unittest
from pathlib import Path
from timecut5.hierarchy import solve_hierarchical
from timecut5.invocation_trace import InvocationTrace
from timecut5.provenance import Recorder
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from validation.trace5.checker import verify_trace


def capture(case,dominance=True):
    with Recorder() as recorder,InvocationTrace(recorder) as trace:
        result=solve_hierarchical(case,dominance=dominance)
    data=trace.export();bundle=recorder.export()
    bundle['roots']=data['events'][-1]['payload']['terminal_families']
    return dict(trace=data,bundle=bundle,case=case),result


def renumber(trace):
    # Repair ordinary counters/references so grammar mutations are not rejected
    # merely because deleting/reordering an event left a superficial ID gap.
    seq_map={};invoke_map={};next_invoke=0
    for i,event in enumerate(trace['events']):
        seq_map.setdefault(event['seq'],i)
        if event['kind']=='invoke':
            invoke_map.setdefault(event['payload']['invocation_id'],next_invoke);next_invoke+=1
    next_invoke=0
    for i,event in enumerate(trace['events']):
        event['seq']=i;p=event['payload']
        if event['kind']=='pop':p['query_seq']=seq_map.get(p['query_seq'],p['query_seq'])
        if event['kind']=='invoke':
            p['invocation_id']=next_invoke;next_invoke+=1
            if p['params'].get('advance_id') is not None:
                p['params']['advance_id']=invoke_map.get(p['params']['advance_id'],p['params']['advance_id'])


def target(trace,kind,condition=lambda p:True):
    return next(i for i,e in enumerate(trace['events']) if e['kind']==kind and condition(e['payload']))


class InvocationCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case=json.loads((ROOT/'tests/fixtures/invocation_trace_pilot_v1.json').read_text())
        cls.data={d:capture(cls.case,d)[0] for d in (False,True)}

    def verify(self,data):return verify_trace(data['trace'],data['bundle'],data['case'])

    def mutated(self):return deepcopy(self.data[True])

    def reject(self,data):
        with self.assertRaises(ValueError):self.verify(data)

    def test_positive_modes_and_same_answer(self):
        for dominance,data in self.data.items():
            with self.subTest(dominance=dominance):
                checked=self.verify(data)
                self.assertTrue(checked.summary['verified'])
                self.assertFalse(checked.summary['literal_G8_closed'])
                self.assertEqual(data['trace']['events'][-1]['payload']['canonical']['result']['J'],'5')

    def test_missing_duplicate_or_empty_output_advance(self):
        for site,duplicate in (('c',False),('c',True),('e',False)):
            with self.subTest(site=site,duplicate=duplicate):
                d=self.mutated();t=d['trace'];i=target(t,'invoke',lambda p:p['operation']=='advance' and p['params']['site']==site)
                if duplicate:t['events'].insert(i,deepcopy(t['events'][i]))
                else:t['events'].pop(i)
                renumber(t);self.reject(d)

    def test_unreachable_query_is_mandatory(self):
        d=self.mutated();t=d['trace'];i=target(t,'query',lambda p:p['classification']=='unreachable')
        t['events'].pop(i);renumber(t);self.reject(d)

    def test_duplicate_unreachable_action_and_false_classification(self):
        for mutation in ('duplicate_query','duplicate_coverage','unreachable_to_queued','reachable_to_unreachable'):
            with self.subTest(mutation=mutation):
                d=self.mutated();t=d['trace']
                if mutation=='duplicate_coverage':
                    p=t['events'][target(t,'expansion_end')]['payload'];p['covered_actions'].append(['u','C'])
                else:
                    p=t['events'][target(t,'query',lambda p:p['classification']==('queued' if mutation=='reachable_to_unreachable' else 'unreachable'))]['payload']
                    if mutation=='duplicate_query':p['actions'].append(['u','C'])
                    elif mutation=='unreachable_to_queued':p.update(classification='queued',bound='1',queue_serial=5)
                    else:p.update(classification='unreachable',bound=None,queue_serial=None)
                self.reject(d)

    def test_reordered_and_foreign_invocations(self):
        d=self.mutated();t=d['trace'];a=target(t,'invoke',lambda p:p['operation']=='finish');b=target(t,'invoke',lambda p:p['operation']=='advance')
        t['events'][a],t['events'][b]=t['events'][b],t['events'][a];renumber(t);self.reject(d)
        d=self.mutated();events=d['trace']['events']
        initial=events[1]['payload']['output_families']
        inv=next(e['payload'] for e in events if e['kind']=='invoke' and e['payload']['operation']=='finish' and e['payload']['params']['source']=='leaf')
        inv['input_families']=initial;self.reject(d)

    def test_skip_before_expand(self):
        d=self.mutated();e=d['trace']['events'][target(d['trace'],'expansion_start')]
        e['kind']='skip_terminal';self.reject(d)

    def test_missing_empty_query_candidate_and_layer(self):
        for kind,condition in (('query',lambda p:p['classification']=='empty_actions'),('candidate',lambda p:True),('layer_start',lambda p:p['depth']==1)):
            with self.subTest(kind=kind):
                d=self.mutated();t=d['trace'];t['events'].pop(target(t,kind,condition));renumber(t);self.reject(d)

    def test_batch_span_and_prune_queue_mutations(self):
        for kind in ('span','pop','disposition','incumbent'):
            with self.subTest(kind=kind):
                d=self.mutated();t=d['trace']
                if kind=='span':
                    p=t['events'][target(t,'invoke',lambda p:p['operation']=='advance')]['payload'];p['batch_range'][1]-=1
                else:
                    p=t['events'][target(t,'pop',lambda p:p['decision']=='prune')]['payload']
                    if kind=='pop':p['query_seq']=5
                    elif kind=='disposition':p['decision']='leaf'
                    else:p['incumbent_key'][0]='100'
                self.reject(d)

    def test_region_partition_and_terminal_pool(self):
        d=self.mutated();d['trace']['events'][0]['payload']['regions']['children'][0]['members'].append('u');self.reject(d)
        d=self.mutated();d['trace']['events'][-1]['payload']['terminal_families']=[];self.reject(d)
        d=self.mutated();d['trace']['events'][-1]['payload']['canonical']['result']['charges']=['2'];self.reject(d)
        d=self.mutated();d['trace']['events'].append(deepcopy(d['trace']['events'][1]));renumber(d['trace']);self.reject(d)

    def test_exact_identifier_types(self):
        for field,value in (('seq',True),('seq',1.0),('invocation_id',False),('group_id',False),('queue_serial',True)):
            with self.subTest(field=field,value=value):
                d=self.mutated();t=d['trace']
                if field=='seq':t['events'][1]['seq']=value
                elif field=='invocation_id':t['events'][1]['payload'][field]=value
                elif field=='group_id':t['events'][target(t,'expansion_start')]['payload'][field]=value
                else:t['events'][target(t,'query',lambda p:p['classification']=='queued')]['payload'][field]=value
                self.reject(d)

    def test_scheduled_combined_and_A06_regressions(self):
        scheduled=deepcopy(self.case)
        scheduled['sites']['c']=['C','S','CS'];scheduled['schedule']={'a':3,'b':5,'D':1}
        a06=json.loads((ROOT/'tests/fixtures/invocation_trace_A06_regression.json').read_text())[0]
        for case in (scheduled,a06):
            with self.subTest(case=case['case_id']):
                data,_=capture(case);self.verify(data)

    def test_terminal_initial_and_stop_bound_positive(self):
        for bound,terminal in ((0,False),(1,False),(2,True)):
            with self.subTest(bound=bound,terminal=terminal):
                case=deepcopy(self.case);case['H_ref']=bound
                if terminal:case['origin']='z'
                data,_=capture(case);self.verify(data)

if __name__=='__main__':unittest.main()
