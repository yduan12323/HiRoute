"""One bound phase. Only the supervisor supplies resource/evidence context."""
import argparse,hashlib,importlib.abc,json,math,os,sys,time
from dataclasses import asdict
from pathlib import Path
from .plan import ROOT,verify_plan,pin,load,require,canonical
from .runtime import CAPTURE,REPLAY,BoundedEvidenceWriter,verify_manifest,worker_failure,read_phase_result
from . import domain

CAPTURE_FILES={'run-binding.json','stage-before-search.json','stage-after-search.json',
 'stage-before-publication.json','capture.json','capture-summary.json','stage-after-publication.json'}
REPLAY_FILES={'run-binding.json','stage-before-decode.json','stage-after-decode.json',
 'stage-after-trace.json','callback-receipts.json','stage-after-callbacks.json',
 'query-index.json','stage-after-query-index.json','structural-summary.json'}

class Fence(importlib.abc.MetaPathFinder):
 def __init__(self,phase):self.phase=phase
 def find_spec(self,name,path=None,target=None):
  if name.split('.')[0] in {'numpy','scipy','sympy'} or name.startswith(('validation.reference5','validation.suffix5')):
   raise ImportError('structural phase forbids optimizer/dependency '+name)
  if self.phase=='replay' and (name=='timecut5' or name.startswith('timecut5.')):
   raise ImportError('independent replay forbids producer '+name)
  return None

def verify_loaded(plan):
 for name,module in tuple(sys.modules.items()):
  if name=='validation' or name.startswith(('validation.','timecut5')):
   path=Path(module.__file__).resolve();require(path.is_relative_to(ROOT),'foreign math module')
   relative=path.relative_to(ROOT).as_posix();require(relative in plan['source_files'],'unbound math module')
   require(pin(path)==plan['source_files'][relative],'loaded source bytes changed')

def prior_capture(plan,plan_sha,attempt,manifest_sha,result_sha,decision_sha,deadline,*,successful_return_path,successful_return_sha):
 attempt=Path(attempt);evidence=attempt/'evidence'
 require(pin(attempt/'result.json')['sha256']==result_sha,'prior resource report changed')
 require(pin(attempt/'decision.json')['sha256']==decision_sha,'prior capture final decision changed')
 receipt_path=Path(successful_return_path)
 require(receipt_path.is_file() and not receipt_path.is_symlink(),'regular successful return file required')
 with receipt_path.open('rb') as stream:raw_return=stream.read(65537)
 require(len(raw_return)<=65536 and hashlib.sha256(raw_return).hexdigest()==successful_return_sha,'prior successful launcher return changed')
 def pairs(rows):
  result={}
  for key,value in rows:
   require(key not in result,'duplicate successful return key');result[key]=value
  return result
 successful_return=json.loads(raw_return,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('nonfinite successful return')))
 result=read_phase_result(attempt,successful_return=successful_return,deadline_monotonic=deadline)
 require(result['status']=='completed' and result.get('descendants_reaped') is True,'prior capture resource phase incomplete')
 require(canonical(result['profile'])==canonical(asdict(CAPTURE)),'prior capture profile changed')
 expected=dict(plan_sha256=plan_sha,source_sha256=plan['source_sha256'],input_sha256=plan['input_sha256'],profile_name=CAPTURE.name)
 require(canonical(result['context'])==canonical(expected),'prior capture source context changed')
 require(pin(evidence/'__manifest.json')['sha256']==manifest_sha,'prior capture manifest changed')
 require(result['verified_manifest_sha256']==manifest_sha and result['verified_manifest_size_bytes']==pin(evidence/'__manifest.json')['size_bytes'],'runtime manifest binding differs from capture input')
 manifest=verify_manifest(evidence,expected_cap_bytes=CAPTURE.worker_evidence_bytes,
     expected_profile_name=CAPTURE.name,deadline_monotonic=deadline)
 require({r['path'] for r in manifest['files']}==CAPTURE_FILES,'prior capture exact output coverage changed')
 files={r['path']:r for r in manifest['files']};summary=load(evidence/'capture-summary.json')
 require(summary['source_plan_sha256']==plan_sha and summary['capture']==files['capture.json'],'capture summary commitment changed')
 return evidence/'capture.json',files['capture.json']['sha256']

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--phase',choices=('capture','replay'),required=True)
 parser.add_argument('--plan',type=Path,required=True);parser.add_argument('--plan-sha',required=True)
 parser.add_argument('--deadline',type=float,required=True);parser.add_argument('--capture-attempt',type=Path)
 parser.add_argument('--capture-manifest-sha');parser.add_argument('--capture-result-sha');parser.add_argument('--capture-decision-sha');parser.add_argument('--capture-return',type=Path);parser.add_argument('--capture-return-sha');args=parser.parse_args()
 writer=None;current='binding'
 def before():require(math.isfinite(args.deadline) and time.monotonic()<args.deadline,'absolute phase deadline')
 try:
  before();profile=CAPTURE if args.phase=='capture' else REPLAY
  require(os.environ.get('HIROUTE_PROFILE')==profile.name and int(os.environ['HIROUTE_EVIDENCE_CAP_BYTES'])==profile.worker_evidence_bytes,'wrong supervisor phase profile')
  require(not any(n=='timecut5' or n.startswith(('timecut5.','validation.')) for n in sys.modules),'mathematics imported before fence')
  sys.meta_path.insert(0,Fence(args.phase));sys.path[:0]=[str(ROOT),str(ROOT/'src')]
  plan=verify_plan(ROOT,args.plan,args.plan_sha,args.deadline)
  writer=BoundedEvidenceWriter(os.environ['HIROUTE_EVIDENCE_ROOT'],profile.worker_evidence_bytes,profile_name=profile.name)
  binding=dict(plan_sha256=args.plan_sha,source_sha256=plan['source_sha256'],input_sha256=plan['input_sha256'],
      phase=args.phase,profile_name=profile.name,reference_usage='comparison_after_unseeded_search_only')
  if args.phase=='replay':
   binding['capture_commitments']=dict(result_sha256=args.capture_result_sha,decision_sha256=args.capture_decision_sha,
    manifest_sha256=args.capture_manifest_sha,successful_return_sha256=args.capture_return_sha)
  writer.write('run-binding.json',domain.chunks(binding))
  current=args.phase
  if args.phase=='capture':domain.capture(plan,ROOT,writer,args.plan_sha,before)
  else:
   require(args.capture_attempt is not None and args.capture_manifest_sha and args.capture_result_sha and args.capture_decision_sha and args.capture_return is not None and args.capture_return_sha,'replay requires independently pinned capture commitments')
   path,sha=prior_capture(plan,args.plan_sha,args.capture_attempt,args.capture_manifest_sha,args.capture_result_sha,args.capture_decision_sha,args.deadline,
    successful_return_path=args.capture_return,successful_return_sha=args.capture_return_sha)
   domain.replay(plan,ROOT,writer,args.plan_sha,path,sha,before)
  current='final-binding';verify_loaded(plan);verify_plan(ROOT,args.plan,args.plan_sha,args.deadline);before()
  expected=CAPTURE_FILES if args.phase=='capture' else REPLAY_FILES
  require({row['path'] for row in writer.files}==expected,'phase exact output coverage mismatch')
  writer.finalize();before();return 0
 except BaseException as error:
  worker_failure(type(error).__name__,str(error)[:4096],current)
  return 1
 finally:
  if writer is not None:writer.close()
if __name__=='__main__':raise SystemExit(main())
