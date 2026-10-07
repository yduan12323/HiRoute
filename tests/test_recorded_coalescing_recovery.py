"""Reconstructed producer protocol; independently checked grammar is separate."""
from dataclasses import replace
from fractions import Fraction as R
import json
from pathlib import Path
import unittest

from timecut5.coalesce import VERSION,coalesce_pieces
from timecut5.coalesced_solver import solve_hierarchical_coalesced
from timecut5.invocation_trace import InvocationTrace
from timecut5.provenance import Recorder,bind,encoded
from timecut5.probe import Interval
from tests.test_time_cut_coalescing import seed

ROOT=Path(__file__).resolve().parents[1]

class RecordedCoalescingRecovery(unittest.TestCase):
 def test_opt_in_keeps_results_and_emits_every_compact(self):
  case=json.loads((ROOT/'tests/fixtures/invocation_trace_pilot_v1.json').read_text())
  for dominance in (False,True):
   with self.subTest(dominance=dominance):
    plain=solve_hierarchical_coalesced(case,dominance=dominance)
    with Recorder() as rec,InvocationTrace(rec,representation=VERSION) as trace:
     value=solve_hierarchical_coalesced(case,dominance=dominance,record_lineage=True)
    self.assertEqual(value.canonical(),plain.canonical())
    stream=trace.export();self.assertEqual(stream['schema'],'family5-hier-trace-v2')
    compact=[e['payload'] for e in stream['events'] if e['kind']=='coalesce']
    invokes=[e['payload'] for e in stream['events'] if e['kind']=='invoke']
    self.assertEqual(len(compact),2*(len(invokes)-1));self.assertEqual(len(compact),value.statistics.calls)
    self.assertEqual([r['coalescing_id'] for r in compact],list(range(len(compact))))
    for row in compact:self.assertEqual(row['batch_range'][0],row['batch_range'][1])
    self.assertTrue(any(not r['input_families'] for r in compact))
    self.assertEqual(stream['events'][-1]['kind'],'run_end')
 def test_fresh_union_preserves_guards_dispatch_and_witnesses(self):
  with Recorder() as rec,InvocationTrace(rec,representation=VERSION):
   a=bind(seed(Interval(0,2,False,False),chi=False,tag='first'),'analytic')
   b=bind(seed(Interval(1,3),chi=False,tag='second'),'analytic')
   joined=coalesce_pieces((a,b),record_lineage=True)[0]
   row=json.loads(joined._family.payload)
   self.assertEqual(row['kind'],'guarded_union');self.assertEqual(row['parents'],[a._family.node_id,b._family.node_id])
   self.assertNotIn(joined._family.node_id,row['parents'])
   self.assertEqual(row['params']['guards'],[['0','2',False,False],['1','3',True,True]])
   self.assertEqual(joined.at(R(3,2)).approach(R(1)).events[0].site,'first')
   self.assertEqual(joined.at(R(3)).approach(R(1)).events[0].site,'second')
   with self.assertRaises(ValueError):coalesce_pieces((a,b),family_ids=(b._family.node_id,a._family.node_id),record_lineage=True)
   forged=replace(joined._point,parents=tuple(reversed(joined._point.parents)))
   with self.assertRaises(ValueError):forged.select(R(3,2))
 def test_stale_foreign_and_wrong_wire_types_reject(self):
  with Recorder() as old:foreign=bind(seed(Interval(0,1)),'analytic')
  with Recorder() as rec,InvocationTrace(rec,representation=VERSION):
   with self.assertRaises(ValueError):coalesce_pieces((foreign,),record_lineage=True)
   p=bind(seed(Interval(0,1)),'analytic')
   with self.assertRaises(ValueError):coalesce_pieces((replace(p,intercept=p.intercept+1),),record_lineage=True)
   bad=replace(p);object.__setattr__(bad,'chi',1)
   with self.assertRaises(ValueError):coalesce_pieces((bad,),record_lineage=True)
 def test_explicit_context_required_and_defaults_unchanged(self):
  with self.assertRaises(ValueError):coalesce_pieces((),record_lineage=True)
  with Recorder() as rec,InvocationTrace(rec):
   with self.assertRaises(ValueError):coalesce_pieces((),record_lineage=True)
  with self.assertRaises(TypeError):coalesce_pieces((),record_lineage=1)
  self.assertEqual(coalesce_pieces(()),())

if __name__=='__main__':unittest.main()
