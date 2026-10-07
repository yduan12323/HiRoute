"""Exact values/hashes against the reconstructed full-copy reference checker."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from tests.test_recovered_real_coalesced import capture
from tests.test_recovered_real_family import prepare
from validation.family5.checker import _plain,digest
from validation.real5_v2.coalesced import verify_coalesced_trace as reference
from validation.real5_v2.shared_replay import verify_coalesced_trace as shared
from validation.capture5.containers import query_digest
ROOT=Path(__file__).resolve().parents[1]

class SharedReplay(unittest.TestCase):
 def test_all_real_mocks_both_modes_exact_summaries_and_every_query(self):
  rows=json.loads((ROOT/'results/milestone_5_real_leg_contract/mock_solver_cases.json').read_text())
  for row in rows:
   for d in (False,True):
    with self.subTest(case=row['case_id'],dominance=d):
     run=capture(row,d);trusted=prepare(row)
     old=reference(run['trace'],run['bundle'],trusted)
     new=shared(run['trace'],run['bundle'],trusted)
     a,b=_plain(old.summary),_plain(new.summary);a.pop('elapsed_s');b.pop('elapsed_s')
     self.assertEqual(a,b);self.assertEqual(old.export_queries(),new.export_queries())
     self.assertEqual(new.summary['query_freeze_sha256'],digest(old.export_queries()))
     self.assertEqual(query_digest(new.queries),old.summary['query_freeze_sha256'])
     if len(new.queries)>1:
      for first in new.queries:
       for second in new.queries:
        if first['family_ids']==second['family_ids']:
         self.assertIs(first['ancestry_nodes'],second['ancestry_nodes'])
 def test_missing_parent_and_wrong_guard_still_reject(self):
  row=json.loads((ROOT/'results/milestone_5_real_leg_contract/mock_solver_cases.json').read_text())[0]
  run=capture(row,True)
  for field in ('parent','guard'):
   data=deepcopy(run)
   if field=='parent':next(n for n in data['bundle']['nodes'].values() if n['parents'])['parents'][0]='0'*64
   else:next(e['payload'] for e in data['trace']['events'] if e['kind']=='coalesce' and e['payload']['input_guards'])['input_guards'][0][0]='999'
   with self.subTest(field=field),self.assertRaises(ValueError):shared(data['trace'],data['bundle'],prepare(row))

if __name__=='__main__':unittest.main()
