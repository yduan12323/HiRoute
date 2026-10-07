"""Extract four hash-reconciled hot jobs and profile one without a solver."""
import time
ENTRY=time.monotonic()
import argparse,hashlib,json,os,resource,signal,stat,sys,weakref
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
from . import plan as binding
from .runtime import REPLAY,PlanContext,BoundedEvidenceWriter,run_phase,worker_failure

HOT_IDS=(11835,11836,11837,11838)
EXTRACT_SECONDS=120
PROFILE_SECONDS=60
PROFILE_TOTAL_SECONDS=90
JOB_AS=1024**3
MAX_REPORT=1024**2
SWEEP_KERNEL='interval-sweep-v1'
JOIN_KERNEL='interval-join-v1'

class SampleEnd(BaseException):pass

def source_binding(args):
 current=binding.source_inventory(binding.ROOT)
 binding.require(binding.source_commit(binding.ROOT)==args.source_commit and binding.digest(current)==args.source_sha,'reviewed source changed')
 binding.assert_committed_sources(binding.ROOT,current,args.source_commit)
 return current

def read_pinned(path,expected,limit=None):
 limit=1024**3 if limit is None else limit
 binding.require(type(limit) is int and limit>0,'input limit')
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 with os.fdopen(fd,'rb') as stream:
  binding.require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode),'regular input required')
  raw=stream.read(limit+1)
 binding.require(len(raw)<=limit,'input byte cap')
 binding.require(hashlib.sha256(raw).hexdigest()==expected,'consumed input hash changed: '+str(path))
 def pairs(rows):
  value={}
  for key,item in rows:binding.require(key not in value,'duplicate JSON key');value[key]=item
  return value
 return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('nonfinite JSON')))

def read_job_bytes(path,spec):
 binding.require(type(spec['size_bytes']) is int and 0<=spec['size_bytes']<=8*1024**2,'extracted job byte cap')
 with Path(path).open('rb') as stream:raw=stream.read(8*1024**2+1)
 binding.require(len(raw)==spec['size_bytes'] and hashlib.sha256(raw).hexdigest()==spec['sha256'],'extracted job bytes changed')
 return raw

def extract(capture,v2,v4,writer,context):
 from validation.family5.checker import _piece,digest
 from validation.real5_v2.batch_jobs import make_job,sha,decode,JOB_LIMIT
 binding.require(v2['schema']=='family5-selection-ledger-v1' and v4['schema']=='family5-selection-ledger-v2' and v4['kernel']=='tau-precompute-v1','ledger versions')
 binding.require(v2['context_sha256']==v4['context_sha256']==context,'capture/ledger context')
 data=capture['bundle'];batches=data['batches'];ids=data['batch_ids'];nodes=data['nodes']
 expected=[[i,ids[i],b['kind']] for i,b in enumerate(batches) if b['kind'] in ('union','reduction')]
 binding.require(v2['expected']==v4['expected']==expected,'complete expected batch identity differs')
 def records(ledger):
  rows=ledger['submitted'];mapping={r['index']:r for r in rows}
  binding.require(len(mapping)==len(rows),'duplicate submitted identity')
  done=[r['result']['index'] for r in ledger['results']]
  binding.require(len(done)==len(set(done)) and not set(HOT_IDS)&set(done),'hot job was not pending')
  return mapping
 old,new=records(v2),records(v4);jobs=[];pending=[]
 for index in HOT_IDS:
  batch=batches[index];bh=ids[index]
  binding.require(batch['kind']=='reduction' and digest(batch)==bh,'hot batch content identity')
  a=[_piece(nodes[x]['output']) for x in batch['parents']]
  b=[_piece(nodes[x]['output']) for x in batch['outputs']]
  specs={}
  for kernel,ledger_row in (('v2',old[index]),('tau-precompute-v1',new[index])):
   raw=make_job(index,bh,'reduction',a,b,context,kernel=kernel)
   binding.require(ledger_row['index']==index and ledger_row['batch_sha256']==bh and ledger_row['kind']=='reduction' and
    ledger_row['context_sha256']==context and ledger_row.get('kernel','v2')==kernel and
    type(ledger_row['input_bytes']) is int and ledger_row['input_bytes']==len(raw) and ledger_row['job_sha256']==sha(raw),'reconstructed job differs from dispatched bytes')
   name='job-'+str(index)+'.'+kernel+'.json'
   specs[kernel]=dict(path=name,sha256=sha(raw),size_bytes=len(raw));pending.append((name,raw,specs[kernel]))
  left,right=decode(make_job(index,bh,'reduction',a,b,context)),decode(make_job(index,bh,'reduction',a,b,context,kernel='tau-precompute-v1'))
  binding.require(all(left[k]==right[k] for k in left if k!='schema'),'kernel job semantics differ')
  jobs.append(dict(index=index,batch_sha256=bh,left_pieces=len(a),right_pieces=len(b),files=specs))
 # At most eight JOB_LIMIT-byte payloads: reconcile all identities before any job publication.
 for name,raw,spec in pending:binding.require(writer.write(name,[raw])==spec,'job publication commitment')
 return dict(schema='hiroute-hot-job-extraction-v1',acceptance=False,solver_calls=0,
  context_sha256=context,indices=list(HOT_IDS),jobs=jobs,
  scope='exact dispatched job bytes reconstructed from immutable capture; no new family validation')

class KernelObserver:
 def __init__(self):
  self.stage='binding';self.started=time.monotonic();self.deadline=None;self.samples=[]
  self.arrangements=[];self.cell_started=0;self.cell_completed=0;self.pairs_started=0;self.pairs_completed=0;self.current_cell=None
  self.operation_times={};self.counts={};self.sweep_ref=None;self.sweep_work=None;self.kernel=None
 def sample(self,signum,frame):
  now=time.monotonic();stack=[]
  while frame is not None and len(stack)<16:
   stack.append([Path(frame.f_code.co_filename).name,frame.f_code.co_name,frame.f_lineno]);frame=frame.f_back
  if len(self.samples)<PROFILE_SECONDS+2:
   self.samples.append(dict(elapsed_seconds=now-self.started,stage=self.stage,cell_started=self.cell_started,
    cell_completed=self.cell_completed,pairs_started=self.pairs_started,pairs_completed=self.pairs_completed,
    current_cell=None if self.current_cell is None else dict(self.current_cell),stack=stack,
    sweep_work=self.native_work()))
  if now>=self.deadline:raise SampleEnd('bounded hot-job observation ended')
 def operation(self,name,fn):
  def call(*args,**kw):
   previous=self.stage;self.stage=name;start=time.process_time()
   try:return fn(*args,**kw)
   finally:self.operation_times[name]=self.operation_times.get(name,0.)+time.process_time()-start;self.stage=previous
  return call
 def arrangement(self,fn):
  def call(pieces):
   start=time.process_time();previous=self.stage;self.stage='arrangement'
   row=dict(input_pieces=len(pieces),completed=False);self.arrangements.append(row)
   try:
    result=fn(pieces);row.update(completed=True,cells=len(result));return result
   finally:row['cpu_seconds']=time.process_time()-start;self.stage=previous
  return call
 def cell(self,fn):
  def call(a,b,lo,hi,e):
   self.cell_started+=1;start=time.process_time();pairs=self.pairs_started
   self.current_cell=dict(index=self.cell_started-1,left_active=sum(p.contains(e) for p in a),
    right_active=sum(p.contains(e) for p in b),completed=False)
   try:
    result=fn(a,b,lo,hi,e);self.cell_completed+=1;self.current_cell['completed']=True;return result
   finally:self.current_cell.update(cpu_seconds=time.process_time()-start,pair_calls=self.pairs_started-pairs)
  return call
 def pair(self,fn):
  def call(*args):
   self.pairs_started+=1;result=fn(*args);self.pairs_completed+=1;return result
  return call
 def native_work(self):
  obj=self.sweep_ref() if self.sweep_ref is not None else None
  value=getattr(obj,'work',None) if obj is not None else self.sweep_work
  return None if value is None else dict(value)
 def sweep_init(self,fn):
  def call(sweep,*args,**kw):
   self.sweep_ref=weakref.ref(sweep);previous=self.stage;self.stage='interval_build';start=time.process_time()
   try:return fn(sweep,*args,**kw)
   finally:
    self.sweep_work=getattr(sweep,'work',None)
    self.operation_times['interval_build']=self.operation_times.get('interval_build',0.)+time.process_time()-start
    self.stage=previous
  return call
 def run(self,raw,kernel,seconds=PROFILE_SECONDS):
  from validation.family5 import independent_oracle_v2 as old,independent_oracle_v4 as new,independent_oracle_v5 as sweep,independent_oracle_v6 as join
  from validation.real5_v2.batch_jobs import evaluate
  binding.require(type(seconds) in (int,float) and 0<seconds<=PROFILE_SECONDS,'profile duration')
  binding.require(signal.getitimer(signal.ITIMER_REAL)==(0.,0.),'existing alarm')
  self.kernel=kernel;mod=old if kernel=='v2' else sweep if kernel==SWEEP_KERNEL else join if kernel==JOIN_KERNEL else new
  pair_name='dominates' if kernel=='v2' else '_dominates'
  self.deadline=time.monotonic()+seconds;handler=signal.getsignal(signal.SIGALRM)
  try:
   with ExitStack() as hooks:
    hooks.enter_context(patch.object(old,'arrangement',self.arrangement(old.arrangement)))
    if kernel in (SWEEP_KERNEL,JOIN_KERNEL):
     hooks.enter_context(patch.object(mod._CoverSweep,'__init__',self.sweep_init(mod._CoverSweep.__init__)))
     hooks.enter_context(patch.object(mod,'equivalent_compact',self.operation('equivalent',mod.equivalent_compact)))
    else:
     hooks.enter_context(patch.object(mod,'_certificate_cell',self.cell(mod._certificate_cell)))
     hooks.enter_context(patch.object(mod,pair_name,self.pair(getattr(mod,pair_name))))
     hooks.enter_context(patch.object(mod,'equivalent',self.operation('equivalent',mod.equivalent)))
    hooks.enter_context(patch.object(mod,'antichain',self.operation('antichain',mod.antichain)))
    signal.signal(signal.SIGALRM,self.sample);signal.setitimer(signal.ITIMER_REAL,min(1.,seconds),1.)
    return evaluate(raw,expected_kernel=kernel)
  finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,handler)
 def summary(self):
  return dict(arrangements=self.arrangements,cell_started=self.cell_started,cell_completed=self.cell_completed,
   pair_comparisons_started=self.pairs_started,pair_comparisons_completed=self.pairs_completed,current_cell=self.current_cell,
   operation_cpu_seconds=self.operation_times,samples=self.samples,sweep_work=self.native_work(),
   overhead=('sweep native work counters and operation timing; no per-cell pair wrapper' if self.kernel in (SWEEP_KERNEL,JOIN_KERNEL) else
    'pair counters add Python calls; cell wrappers add an active-support scan; inclusive times overlap'))

def rebind_sweep_job(raw):
 from validation.real5_v2.batch_jobs import decode,read_piece,make_job
 value=decode(raw)
 binding.require(value['schema']=='family5-selection-job-v1' and 'kernel' not in value,'sweep source must be original v2 job')
 a=[read_piece(p) for p in value['left']];b=[read_piece(p) for p in value['right']]
 args=(value['index'],value['batch_sha256'],value['kind'],a,b,value['context_sha256'])
 binding.require(make_job(*args)==raw,'noncanonical or changed original job')
 return make_job(*args,kernel=SWEEP_KERNEL)

def profile_job(raw,kernel,seconds=PROFILE_SECONDS):
 from validation.real5_v2.batch_jobs import decode,read_piece,sha
 job=decode(raw);a=[read_piece(p) for p in job['left']];b=[read_piece(p) for p in job['right']]
 observer=KernelObserver();result=None;error=None;start=time.process_time()
 try:result=observer.run(raw,kernel,seconds)
 except SampleEnd as exc:error=dict(type=type(exc).__name__,message=str(exc))
 except Exception as exc:error=dict(type=type(exc).__name__,message=str(exc)[:1000])
 return dict(schema='hiroute-hot-job-diagnostic-v1',acceptance=False,structural_verified=False,solver_calls=0,
  kernel=kernel,index=job['index'],job_sha256=sha(raw),batch_sha256=job['batch_sha256'],context_sha256=job['context_sha256'],
  population=dict(left=len(a),right=len(b),distinct_lines=len({(p.m,p.b) for p in a+b}),
   distinct_states=len({p.state for p in a+b}),distinct_full_keys=len({p.family() for p in a+b}),
   distinct_endpoints=len({x for p in a+b for x in (p.lo,p.hi)})),
  completed=result is not None,result=result,error=error,cpu_seconds=time.process_time()-start,observations=observer.summary(),
  kernel_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024)

def worker(args):
 from .worker import Fence
 sys.meta_path.insert(0,Fence('replay'))
 binding.require(os.environ.get('HIROUTE_PROFILE')==REPLAY.name and
  int(os.environ['HIROUTE_EVIDENCE_CAP_BYTES'])==REPLAY.worker_evidence_bytes,'wrong diagnostic guard profile')
 if args.mode=='profile':resource.setrlimit(resource.RLIMIT_AS,(JOB_AS,JOB_AS))
 source_binding(args)
 with BoundedEvidenceWriter(os.environ['HIROUTE_EVIDENCE_ROOT'],REPLAY.worker_evidence_bytes,profile_name=REPLAY.name) as writer:
  if args.mode=='extract':
   capture=read_pinned(args.capture,args.capture_sha)
   binding.require(capture['schema']=='hiroute-recorded-real-capture-v1' and capture['source_plan_sha256']==args.plan_sha,'original capture plan binding')
   v2=read_pinned(args.v2_ledger,args.v2_ledger_sha,32*1024**2);v4=read_pinned(args.v4_ledger,args.v4_ledger_sha,32*1024**2)
   result=extract(capture,v2,v4,writer,args.capture_sha)
   result['source_pins']=dict(original_plan_sha256=args.plan_sha,capture_sha256=args.capture_sha,v2_ledger_sha256=args.v2_ledger_sha,v4_ledger_sha256=args.v4_ledger_sha,
    source_commit=args.source_commit,source_sha256=args.source_sha)
   writer.write('jobs.json',[binding.canonical(result)+b'\n'])
  else:
   manifest=read_pinned(args.manifest,args.manifest_sha,MAX_REPORT)
   binding.require(manifest['schema']=='hiroute-hot-job-extraction-v1' and manifest['indices']==list(HOT_IDS),'extracted population')
   match=[r for r in manifest['jobs'] if r['index']==args.index];binding.require(len(match)==1,'hot-job identity')
   if args.kernel==SWEEP_KERNEL:binding.require(type(args.index) is int and args.index in HOT_IDS,'sweep pilot requires a fixed extracted hot-job identity')
   source_kernel='v2' if args.kernel==SWEEP_KERNEL else args.kernel
   spec=match[0]['files'][source_kernel];path=binding.inside(args.manifest.parent,spec['path'])
   original=read_job_bytes(path,spec);raw=rebind_sweep_job(original) if args.kernel==SWEEP_KERNEL else original
   result=profile_job(raw,args.kernel);result['source_job_sha256']=hashlib.sha256(original).hexdigest()
   binding.require(result['source_job_sha256']==spec['sha256'] and result['job_sha256']==hashlib.sha256(raw).hexdigest() and result['index']==args.index and result['context_sha256']==manifest['context_sha256'] and result['batch_sha256']==match[0]['batch_sha256'],'profile input context')
   result['source_pins']=dict(manifest_sha256=args.manifest_sha,source_commit=args.source_commit,source_sha256=args.source_sha)
   encoded=binding.canonical(result)+b'\n';binding.require(len(encoded)<=MAX_REPORT,'profile report cap');writer.write('diagnostic.json',[encoded])
  writer.finalize()
 return 0

def main():
 p=argparse.ArgumentParser();p.add_argument('--worker',action='store_true');p.add_argument('--mode',choices=('extract','profile'),required=True)
 for name in ('capture','v2-ledger','v4-ledger','manifest'):p.add_argument('--'+name,type=Path);p.add_argument('--'+name+'-sha')
 p.add_argument('--plan-sha');p.add_argument('--index',type=int,choices=HOT_IDS);p.add_argument('--kernel',choices=('v2','tau-precompute-v1',SWEEP_KERNEL))
 p.add_argument('--source-commit',required=True);p.add_argument('--source-sha',required=True);p.add_argument('--cpu',type=int);p.add_argument('--attempt-dir',type=Path)
 args=p.parse_args()
 if args.worker:
  try:return worker(args)
  except BaseException as exc:worker_failure(type(exc).__name__,str(exc)[:4096],'hot-job-'+args.mode);return 1
 binding.require(args.cpu is not None and args.attempt_dir is not None,'explicit CPU/new attempt required')
 soft,hard=resource.getrlimit(resource.RLIMIT_AS);resource.setrlimit(resource.RLIMIT_AS,(min(512*1024**2,soft) if soft!=resource.RLIM_INFINITY else 512*1024**2,hard))
 source_binding(args);argv=[sys.executable,'-B','-m','experiments.time_cut_v2.recorded_real.hot_jobs','--worker','--mode',args.mode,
  '--source-commit',args.source_commit,'--source-sha',args.source_sha]
 if args.mode=='extract':
  binding.require(type(args.plan_sha) is str and len(args.plan_sha)==64,'original plan SHA required');argv+=['--plan-sha',args.plan_sha]
  for name in ('capture','v2_ledger','v4_ledger'):
   path=getattr(args,name);digest=getattr(args,name+'_sha');binding.require(path is not None and digest,'extraction pins required')
   argv+=['--'+name.replace('_','-'),str(path.resolve()),'--'+name.replace('_','-')+'-sha',digest]
  input_hash=binding.digest(dict(plan=args.plan_sha,capture=args.capture_sha,v2=args.v2_ledger_sha,v4=args.v4_ledger_sha));seconds=EXTRACT_SECONDS
 else:
  binding.require(args.manifest is not None and args.manifest_sha and args.index in HOT_IDS and args.kernel is not None,'profile pins required')
  if args.kernel==SWEEP_KERNEL:binding.require(type(args.index) is int and args.index in HOT_IDS,'sweep pilot requires a fixed extracted hot-job identity')
  argv+=['--manifest',str(args.manifest.resolve()),'--manifest-sha',args.manifest_sha,'--index',str(args.index),'--kernel',args.kernel]
  input_hash=binding.digest(dict(manifest=args.manifest_sha,index=args.index,kernel=args.kernel));seconds=PROFILE_TOTAL_SECONDS
 result=run_phase(argv,attempt_dir=args.attempt_dir,profile=REPLAY,cpu=args.cpu,
  context=PlanContext(args.plan_sha if args.mode=='extract' else args.manifest_sha,args.source_sha,input_hash,REPLAY.name),entry_monotonic=float(ENTRY),deadline_monotonic=float(ENTRY+seconds))
 print(json.dumps(result,sort_keys=True));return 0 if result['status']=='completed' else 1
if __name__=='__main__':raise SystemExit(main())
