"""One fixed, previously dispatched11840 payload; no extraction or full replay."""
import time
ENTRY=time.monotonic()
import argparse,hashlib,json,os,resource,sys
from pathlib import Path
from . import plan as binding
from . import hot_jobs as hot
from .runtime import REPLAY,PlanContext,BoundedEvidenceWriter,run_phase,worker_failure

INDEX=11840
JOB_SHA='4506dc60a82f757a0d9af47a4b4850ca595daf1bc409d9bfb0cc57319a383fc5'
JOB_BYTES=1108114
BATCH_SHA='5fe25f24d7f9ccf3c06964cbe75f8be7fc3aa0dd68a36479cb1a10ec7b09b954'
CAPTURE_SHA='66bdff79410db1e27aa7e1226e0698ef07bd7b5d307d00f61fbd07edaaede2ff'
KERNEL='interval-join-v1'

def rebind(raw):
 from validation.real5_v2.batch_jobs import decode,read_piece,make_job
 binding.require(len(raw)==JOB_BYTES and hashlib.sha256(raw).hexdigest()==JOB_SHA,'fixed11840 payload changed')
 value=decode(raw)
 binding.require(value['schema']=='family5-selection-job-v2' and value['kernel']=='interval-sweep-v1' and
  type(value['index']) is int and value['index']==INDEX and value['batch_sha256']==BATCH_SHA and
  value['context_sha256']==CAPTURE_SHA and value['kind']=='reduction','fixed11840 identity changed')
 a=[read_piece(p) for p in value['left']];b=[read_piece(p) for p in value['right']]
 args=(INDEX,BATCH_SHA,'reduction',a,b,CAPTURE_SHA)
 binding.require(make_job(*args,kernel='interval-sweep-v1')==raw,'noncanonical source job')
 return make_job(*args,kernel=KERNEL)

def worker(args):
 from .worker import Fence
 sys.meta_path.insert(0,Fence('replay'))
 binding.require(os.environ.get('HIROUTE_PROFILE')==REPLAY.name and
  int(os.environ['HIROUTE_EVIDENCE_CAP_BYTES'])==REPLAY.worker_evidence_bytes,'wrong diagnostic guard')
 resource.setrlimit(resource.RLIMIT_AS,(hot.JOB_AS,hot.JOB_AS));hot.source_binding(args)
 original=hot.read_job_bytes(args.job,dict(size_bytes=JOB_BYTES,sha256=JOB_SHA));raw=rebind(original)
 result=hot.profile_job(raw,KERNEL)
 binding.require(result['index']==INDEX and result['batch_sha256']==BATCH_SHA and result['context_sha256']==CAPTURE_SHA and
  result['job_sha256']==hashlib.sha256(raw).hexdigest(),'profile result identity changed')
 result['source_job_sha256']=JOB_SHA;result['source_pins']=dict(source_commit=args.source_commit,source_sha256=args.source_sha)
 encoded=binding.canonical(result)+b'\n';binding.require(len(encoded)<=hot.MAX_REPORT,'profile report cap')
 with BoundedEvidenceWriter(os.environ['HIROUTE_EVIDENCE_ROOT'],REPLAY.worker_evidence_bytes,profile_name=REPLAY.name) as writer:
  writer.write('diagnostic.json',[encoded]);writer.finalize()
 return 0

def main():
 p=argparse.ArgumentParser();p.add_argument('--worker',action='store_true');p.add_argument('--job',type=Path,required=True)
 p.add_argument('--source-commit',required=True);p.add_argument('--source-sha',required=True)
 p.add_argument('--cpu',type=int);p.add_argument('--attempt-dir',type=Path);a=p.parse_args()
 if a.worker:
  try:return worker(a)
  except BaseException as exc:worker_failure(type(exc).__name__,str(exc)[:4096],'fixed11840-join-profile');return 1
 binding.require(a.cpu is not None and a.attempt_dir is not None,'explicit CPU and fresh attempt required')
 soft,hard=resource.getrlimit(resource.RLIMIT_AS)
 resource.setrlimit(resource.RLIMIT_AS,(min(512*1024**2,soft) if soft!=resource.RLIM_INFINITY else 512*1024**2,hard))
 hot.source_binding(a);binding.require(binding.pin(a.job)==dict(sha256=JOB_SHA,size_bytes=JOB_BYTES),'fixed job pin changed')
 argv=[sys.executable,'-B','-m','experiments.time_cut_v2.recorded_real.join_profile','--worker','--job',str(a.job.resolve()),
  '--source-commit',a.source_commit,'--source-sha',a.source_sha]
 result=run_phase(argv,attempt_dir=a.attempt_dir,profile=REPLAY,cpu=a.cpu,
  context=PlanContext(JOB_SHA,a.source_sha,binding.digest(dict(job_sha256=JOB_SHA,kernel=KERNEL)),REPLAY.name),
  entry_monotonic=float(ENTRY),deadline_monotonic=float(ENTRY+hot.PROFILE_TOTAL_SECONDS))
 print(json.dumps(result,sort_keys=True));return 0 if result['status']=='completed' else 1
if __name__=='__main__':raise SystemExit(main())
