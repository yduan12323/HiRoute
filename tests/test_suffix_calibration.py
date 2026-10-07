"""Hand-authored exact certificates; no numerical solver is invoked."""
from copy import deepcopy
from fractions import Fraction as F
import signal,time,unittest
from unittest.mock import patch
from validation.suffix5.test_convex_checker import hand_record,context
from validation.suffix5.test_certificate_checker import certificate
from validation.suffix5.independent_convex_model import build_model,strict_task
from validation.suffix5.calibration import verify_model,verification_deadline,select_calibration,POSITIONS
from validation.family5.checker import digest

def binding(record):
 m=record['model'];return dict(calibration_index=0,preview_position=0,model_sha256=digest(m),
  logical_identity=dict(source_bundle_sha256=m['family_bundle_sha256'],**{k:m[k] for k in ('family_id','word','arrival_bands')}))

class CalibrationTests(unittest.TestCase):
 def test_eight_positions_are_derived_and_keep_all_seven_families(self):
  rows=[];models=[]
  for depth,width in enumerate((64,96,64,32)):
   for j in range(width):
    i=len(rows);family=0 if depth==0 else 2*depth-1+int(j>=width//2)
    logical=dict(family_id=f'{family:064x}',word=[[f'site{i}','C']],arrival_bands=[0])
    model=dict(family_bundle_sha256='b'*64,**logical)
    rows.append(dict(position=i,prefix_depth=depth,selection=logical))
    models.append(dict(selection_position=i,model=model,model_sha256=digest(model),
     logical_identity=dict(source_bundle_sha256='b'*64,**logical)))
  selection=dict(schema='family5-static-model-preview-selection-v1',source_bundle_sha256='b'*64,models=rows)
  actual=select_calibration(selection,models)
  self.assertEqual(actual['positions'],list(POSITIONS));self.assertEqual(actual['selected_models'],8)
  self.assertEqual(len({x['logical_identity']['family_id'] for x in actual['bindings']}),7)
  bad=deepcopy(models);bad[0]['selection_position']=True
  with self.assertRaises(ValueError):select_calibration(selection,bad)
  bad=deepcopy(selection);bad['models'][0]['prefix_depth']=True
  with self.assertRaises(ValueError):select_calibration(bad,models)
  bad=deepcopy(models);bad[63]['model']['word'][0][0]='changed'
  with self.assertRaises(ValueError):select_calibration(selection,bad)
 def test_all_strict_attainment_and_infeasibility_paths(self):
  for args,status in [(('C',1,True),'attained_optimum'),(('C',1,False),'primary_unattained'),
   (('CS',1,False),'secondary_unattained'),(('C',2,False),'closed_infeasible'),(('S',0,False),'attained_optimum')]:
   ctx,record=hand_record(*args);out=verify_model(ctx,binding(record),record)
   self.assertEqual(out['result']['status'],status);self.assertFalse(out['literal_G8_closed'])
   self.assertEqual(out['physical_witness_verified'],status!='closed_infeasible')
 def test_raw_face_constants_stage_order_and_model_binding(self):
  ctx,record=hand_record('C',1,True)
  for mutate in (lambda r:r['stages'][2]['task']['equalities'][0].__setitem__(1,r['result']['J']),
   lambda r:r['stages'].__setitem__(0,r['stages'][1]),lambda r:r['model']['lp']['J'].__setitem__('constant','999'),
   lambda r:r['result'].__setitem__('H',True)):
   bad=deepcopy(record);mutate(bad)
   with self.assertRaises(ValueError):verify_model(ctx,binding(record),bad)
 def test_zero_strict_margin_is_not_a_feasible_model(self):
  ctx,ident=context('C',initial_energy_kwh='5');model=build_model(ctx,ident,[['s','C']],[2]);task=strict_task(model)
  names={r['label']:i for i,r in enumerate(model['lp']['rows'])}
  dual=[(names[k],-1) for k in ('departure_capacity:0','prefix_energy_lower','charge_positive:0')]
  proof=certificate(task,[5,0,0,1,0],dual)
  record=dict(model=model,stages=[dict(name='feasibility',task=task,certificate=proof)],result=dict(status='strict_infeasible'))
  out=verify_model(ctx,binding(record),record)
  self.assertEqual(out['result']['status'],'strict_infeasible');self.assertFalse(out['physical_witness_verified'])
 def test_foreign_or_out_of_band_physical_lifts_reject(self):
  import validation.suffix5.calibration as c
  ctx,record=hand_record('C',1,True);old=c.lift_point
  def changed(*a,**k):
   value=old(*a,**k);value['suffix_events'][1]['arrival_energy']='0';return value
  with patch.object(c,'lift_point',side_effect=changed),self.assertRaises(ValueError):verify_model(ctx,binding(record),record)
  other=binding(record);other['logical_identity']['family_id']='0'*64
  with self.assertRaises(ValueError):verify_model(ctx,other,record)
 def test_verification_wall_limit_and_handler_restoration(self):
  old=signal.getsignal(signal.SIGALRM)
  with self.assertRaises(TimeoutError):
   with verification_deadline(float(time.monotonic()+0.02)):time.sleep(0.06)
  self.assertEqual(signal.getsignal(signal.SIGALRM),old);self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.0,0.0))
  with self.assertRaises(ValueError):
   with verification_deadline(float(time.monotonic()-1)):pass
  with self.assertRaises(ValueError):
   with verification_deadline(float('inf')):pass
if __name__=='__main__':unittest.main()
