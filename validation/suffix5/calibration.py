"""Fixed small calibration bindings and optimizer-free exact acceptance.

No LP backend is imported here. Existing independent strict/lexicographic and
physical witness checkers decide every selected model's acceptance.
"""
from fractions import Fraction as F
import math,signal,time
from contextlib import contextmanager
from validation.family5.checker import require,digest,wire_equal
from .convex_checker import check_regime
from .convex_witness import lift_point,result_contract
from .convex_evidence import check_result_witness

POSITIONS=(0,63,64,159,160,223,224,255)
EPSILON=F(1,10**6)

def select_calibration(selection,models):
 require(type(selection) is dict and selection['schema']=='family5-static-model-preview-selection-v1',
  'authenticated fixed preview selection required')
 rows=selection['models'];require(type(rows) is list and len(rows)==256 and type(models) is list and len(models)==256,
  'original 256-model preview required')
 require(all(type(r['position']) is int and r['position']==i and type(r['prefix_depth']) is int
  and r['prefix_depth'] in range(4) for i,r in enumerate(rows)),'preview position/depth changed')
 positions=[]
 for depth,total in enumerate((64,96,64,32)):
  group=[i for i,r in enumerate(rows) if r['prefix_depth']==depth]
  require(len(group)==total,'preview depth population changed');positions.extend([group[0],group[-1]])
 require(tuple(positions)==POSITIONS,'fixed calibration positions changed')
 bindings=[]
 for number,position in enumerate(positions):
  row=models[position];selected=rows[position]['selection'];model=row['model']
  require(type(row['selection_position']) is int and row['selection_position']==position and digest(model)==row['model_sha256'],
   'preview model position/hash changed')
  require(wire_equal({k:model[k] for k in ('family_id','word','arrival_bands')},selected),'preview logical model changed')
  identity=dict(source_bundle_sha256=selection['source_bundle_sha256'],**selected)
  require(wire_equal(row['logical_identity'],identity) and model['family_bundle_sha256']==selection['source_bundle_sha256'],
   'preview family/source identity changed')
  bindings.append(dict(calibration_index=number,preview_position=position,prefix_depth=rows[position]['prefix_depth'],
   model_sha256=row['model_sha256'],logical_identity=identity))
 require(len({b['logical_identity']['family_id'] for b in bindings})==7,'fixed seven-family calibration changed')
 return dict(schema='family5-eight-model-calibration-selection-v1',positions=positions,bindings=bindings,
  selection_uses_outcomes=False,selected_models=8,maximum_logical_stage_slots=40,maximum_candidate_passes=96,
  candidate_seconds_per_model=30,verification_seconds_per_model=30,epsilon=str(EPSILON),
  certificate_reuse_enabled=False,full_population_complete=False,literal_G8_closed=False)

@contextmanager
def verification_deadline(deadline):
 """Bound exact checking, reconstruction and caller publication on main thread."""
 require(type(deadline) is float and math.isfinite(deadline),'finite verification deadline required')
 remaining=deadline-time.monotonic();require(remaining>0,'verification deadline exhausted')
 previous=signal.getsignal(signal.SIGALRM);timer=signal.getitimer(signal.ITIMER_REAL)
 require(timer==(0.0,0.0),'nested verification timer unsupported')
 def expired(signum,frame):raise TimeoutError('exact verification/physical lifting deadline')
 signal.signal(signal.SIGALRM,expired)
 try:
  signal.setitimer(signal.ITIMER_REAL,remaining);yield
  require(time.monotonic()<deadline,'verification completed after its deadline')
 finally:
  signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)

def _point(model,checked):
 result=checked['result'];stages={s['name']:s for s in checked['audit']['stages']};status=result['status']
 if status=='attained_optimum':return tuple(map(F,stages['secondary_attainment']['x'][:-1]))
 require(status in ('primary_unattained','secondary_unattained'),'empty model has no physical point')
 if status=='primary_unattained':left,right,objective='primary','feasibility','J'
 else:left,right,objective='secondary','primary_attainment','Q'
 a=tuple(map(F,stages[left]['x']));b=tuple(map(F,stages[right]['x'][:-1]));c=tuple(map(F,model['lp'][objective]['coefficients']))
 require(len(a)==len(b)==len(c),'audited approach dimension changed')
 gap=sum((v*(y-x) for v,x,y in zip(c,a,b)),F(0));require(gap>0,'nonattained optimum lacks strict approach gap')
 weight=min(F(1,2),EPSILON/(2*gap))
 return tuple((1-weight)*x+weight*y for x,y in zip(a,b))

def verify_model(ctx,binding,record):
 """Certify one fixed model, never a whole query or the full population."""
 require(type(binding) is dict and digest(record['model'])==binding['model_sha256'],'candidate changed bound model bytes')
 identity=dict(source_bundle_sha256=record['model']['family_bundle_sha256'],
  **{k:record['model'][k] for k in ('family_id','word','arrival_bands')})
 require(wire_equal(identity,binding['logical_identity']),'candidate changed full logical identity')
 wall=time.monotonic();cpu=time.process_time();checked=check_regime(ctx,record,with_audit=True)
 times=dict(exact_certificate_wall_seconds=time.monotonic()-wall,exact_certificate_cpu_seconds=time.process_time()-cpu)
 result=checked['result'];evidence=contract=physical=None
 if result['status'] in ('attained_optimum','primary_unattained','secondary_unattained'):
  wall=time.monotonic();cpu=time.process_time()
  evidence=lift_point(ctx,record['model'],_point(record['model'],checked));contract=result_contract(result,EPSILON)
  physical=check_result_witness(ctx,record,evidence,contract)
  times.update(physical_lift_and_recheck_wall_seconds=time.monotonic()-wall,
   physical_lift_and_recheck_cpu_seconds=time.process_time()-cpu)
 return dict(schema='family5-calibrated-model-check-v1',binding=binding,result=result,exact_certificate_verified=True,
  checked_stage_count=len(record['stages']),physical_witness_verified=evidence is not None,
  evidence=evidence,contract=contract,physical_audit=physical,timings=times,
  query_optimum_certified=False,full_population_complete=False,literal_G8_closed=False)
