"""Tiny real glue checks; no original real population or LP execution."""
from copy import deepcopy
import json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tests.test_recovered_real_family import prepare,blob,repin
from validation.real5_v2.coalesced import verify_coalesced_trace
from validation.family5.checker import _plain,digest,CheckedBundle
from validation.trace5.checker import CheckedTrace


def capture(row,dominance):
 from timecut5.coalesce import VERSION
 from timecut5.coalesced_solver import solve_hierarchical_real_coalesced
 from timecut5.invocation_trace import InvocationTrace
 from timecut5.provenance import Recorder
 from timecut5.real_legs import ImmutableLegTable,restrict_frozen_tree
 table=ImmutableLegTable.from_bytes(blob(row['table']),row['table_sha256'])
 tree=restrict_frozen_tree(blob(row['original_tree']),row['original_tree_sha256'],list(table.sites))
 plain=solve_hierarchical_real_coalesced(row['query'],table,tree,dominance=dominance)
 with Recorder() as recorder,InvocationTrace(recorder,representation=VERSION) as trace:
  recorded=solve_hierarchical_real_coalesced(row['query'],table,tree,dominance=dominance,record_lineage=True)
 stream,bundle=trace.export(),recorder.export();bundle['roots']=stream['events'][-1]['payload']['terminal_families']
 return dict(trace=stream,bundle=bundle,canonical=plain.inner.canonical(),recorded=recorded.inner.canonical())


class RealCoalescedRecovery(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.rows=json.loads((ROOT/'results/milestone_5_real_leg_contract/mock_solver_cases.json').read_text())
  cls.runs={(i,d):capture(row,d) for i,row in enumerate(cls.rows) for d in (False,True)}
 def test_all_five_mocks_both_modes_full_trusted_grammar(self):
  for (i,d),data in self.runs.items():
   with self.subTest(case=i,dominance=d):
    trusted=prepare(self.rows[i]);checked=verify_coalesced_trace(data['trace'],data['bundle'],trusted)
    self.assertIs(type(checked),CheckedTrace);self.assertIs(type(checked.bundle),CheckedBundle)
    self.assertEqual(_plain(checked.summary['canonical']),json.loads(blob(data['canonical'])))
    self.assertEqual(data['canonical'],data['recorded'])
    self.assertEqual(checked.summary['coalescings'],2*(checked.summary['invocations']-1))
    self.assertEqual(checked.summary['query_freeze_sha256'],digest(checked.export_queries()))
    self.assertEqual(_plain(checked.summary['real_input']),trusted.source_snapshot())
    self.assertFalse(checked.summary['literal_G8_closed'])
    for query in checked.queries:self.assertEqual(query['onward_travel_lower_bound'],'0')
 def test_original_member_order_and_empty_regions_survive_composition(self):
  row=deepcopy(self.rows[0]);ids=row['original_tree']['site_ids']
  row['original_tree']=dict(site_ids=ids,regions=[dict(parent=-1,children=[2,1],members=[1,0]),dict(parent=0,children=[],members=[]),dict(parent=0,children=[],members=[0,1])]);repin(row)
  data=capture(row,True);checked=verify_coalesced_trace(data['trace'],data['bundle'],prepare(row))
  self.assertGreater(checked.summary['empty_action_queries'],0)
  self.assertEqual(checked.snapshot()['events'][0]['payload']['regions']['members'],list(reversed(ids)))
 def test_missing_compact_wrong_guard_tree_and_family_hash_reject(self):
  for mutation in ('compact','guard','tree','family'):
   data=deepcopy(self.runs[0,True]);trace,bundle=data['trace'],data['bundle']
   if mutation=='compact':
    trace['events'].pop(next(i for i,e in enumerate(trace['events']) if e['kind']=='coalesce'))
    for i,e in enumerate(trace['events']):e['seq']=i
   elif mutation=='guard':next(e['payload'] for e in trace['events'] if e['kind']=='coalesce' and e['payload']['input_guards'])['input_guards'][0][0]='999'
   elif mutation=='tree':trace['events'][0]['payload']['regions']['members'].reverse()
   else:next(iter(bundle['nodes'].values()))['output']['chi']=False
   with self.subTest(mutation=mutation),self.assertRaises(ValueError):verify_coalesced_trace(trace,bundle,prepare(self.rows[0]))
 def test_consumer_import_fence_all_ten_traces(self):
  rows=[dict(row=self.rows[i],evidence=data) for (i,d),data in self.runs.items()]
  script=r'''
import importlib.abc,json,sys
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,name,path=None,target=None):
  if name.split('.')[0] in {'timecut5','numpy','scipy','sympy'} or name.startswith(('validation.reference5','validation.suffix5')):raise RuntimeError('forbidden '+name)
sys.meta_path.insert(0,Block())
from validation.real5_v2 import prepare_real_case
from validation.real5_v2.coalesced import verify_coalesced_trace
from validation.family5.checker import canonical,digest
for item in json.load(open(sys.argv[1])):
 row,evidence=item['row'],item['evidence'];trusted=prepare_real_case(row['query'],digest(row['query']),canonical(row['table']).encode(),row['table_sha256'],canonical(row['original_tree']).encode(),row['original_tree_sha256'])
 checked=verify_coalesced_trace(evidence['trace'],evidence['bundle'],trusted)
 if not checked.summary['verified']:raise RuntimeError('incomplete')
print('10 independently checked real coalesced mocks')
'''
  with tempfile.TemporaryDirectory() as temp:
   path=Path(temp)/'fixtures.json';path.write_bytes(blob(rows))
   flags=['-'+('O'*sys.flags.optimize)] if sys.flags.optimize else []
   run=subprocess.run([sys.executable,'-B',*flags,'-c',script,str(path)],cwd=ROOT,capture_output=True,text=True,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),timeout=30)
   self.assertEqual(run.returncode,0,run.stderr);self.assertIn('10 independently',run.stdout)

if __name__=='__main__':unittest.main()
