"""Hand-certificate block completion and witness representatives; no LP."""
from copy import deepcopy
import unittest
from validation.family5.checker import digest
from validation.suffix5.block_certificates import BlockCertificates
from validation.suffix5.test_convex_checker import hand_record
from validation.suffix5.calibration import verify_model
from validation.suffix5.checker import aggregate_records

def declaration(records):
 rows=[]
 for i,record in enumerate(records):
  model=record['model'];identity=dict(source_bundle_sha256=model['family_bundle_sha256'],
   **{k:deepcopy(model[k]) for k in ('family_id','word','arrival_bands')})
  rows.append(dict(ordinal=i,segment_id=0,prefix_depth=0,logical_identity=identity,logical_identity_sha256=digest(identity)))
 return [dict(range=dict(block_id=0,start=0,end=len(rows),model_count=len(rows)),descriptors=rows)]

class BlockCertificateTests(unittest.TestCase):
 def test_out_of_order_completion_preserves_every_tie_and_first_winner(self):
  ctx,first=hand_record('C',0,True);_,second=hand_record('C',1,True);_,excluded=hand_record('C',2,True)
  rows=[first,second,excluded];checker=BlockCertificates(ctx,declaration(rows))
  for i in (2,1,0):checker.check(i,rows[i])
  summary=checker.summary(0);expected=aggregate_records(rows,with_audit=True)
  self.assertTrue(summary['complete_certificates']);self.assertEqual(summary['aggregate']['result'],expected['result'])
  for key in ('primary_tied','secondary_tied','winning'):
   actual=[i for lo,hi in summary['aggregate']['audit'][key+'_regime_ranges'] for i in range(lo,hi)]
   self.assertEqual(actual,expected['audit'][key+'_regimes'])
  self.assertEqual(summary['aggregate']['audit']['exclusion_counts'],expected['audit']['exclusion_counts'])
  winner=checker.winner(0);self.assertEqual(winner['model_ordinal'],0)
  result=verify_model(ctx,dict(model_sha256=digest(winner['record']['model']),logical_identity=winner['descriptor']['logical_identity']),winner['record'])
  self.assertTrue(result['physical_witness_verified'])
 def test_unattained_and_all_excluded_block_statuses_are_exact(self):
  for effect,band,attained in (('C',1,False),('CS',1,False),('C',2,False),('S',0,False)):
   ctx,record=hand_record(effect,band,attained);checker=BlockCertificates(ctx,declaration([record]));checker.check(0,record)
   summary=checker.summary(0);self.assertTrue(summary['complete_certificates'])
   expected=aggregate_records([record]);self.assertEqual(summary['aggregate']['result'],expected)
   self.assertEqual(checker.winner(0) is None,record['result']['status']=='closed_infeasible')
 def test_unresolved_or_unsubmitted_never_aggregates_as_excluded(self):
  ctx,record=hand_record('C',1,True);checker=BlockCertificates(ctx,declaration([record]))
  self.assertEqual(checker.summary(0)['unsubmitted_ordinals'],[0]);self.assertIsNone(checker.summary(0)['aggregate'])
  checker.unresolved(0,'candidate deadline')
  self.assertEqual(checker.summary(0)['unresolved_ordinals'],[0]);self.assertIsNone(checker.summary(0)['aggregate'])
  with self.assertRaises(ValueError):checker.winner(0)
  with self.assertRaises(ValueError):checker.check(0,record)
 def test_bad_certificate_foreign_band_duplicate_and_aliases_reject(self):
  ctx,record=hand_record('C',1,True);blocks=declaration([record]);checker=BlockCertificates(ctx,blocks)
  bad=deepcopy(record);bad['result']['J']='999'
  with self.assertRaises(ValueError):checker.check(0,bad)
  bad=deepcopy(record);bad['model']['arrival_bands']=[0]
  with self.assertRaises(ValueError):checker.check(0,bad)
  blocks[0]['descriptors'][0]['logical_identity']['word'][0][0]='foreign'
  checker.check(0,record);record['result']['J']='999'
  self.assertNotEqual(checker.winner(0)['record']['result']['J'],'999')
  with self.assertRaises(ValueError):checker.check(0,record)
  with self.assertRaises(ValueError):checker.unresolved(True,'foreign')

if __name__=='__main__':unittest.main()
