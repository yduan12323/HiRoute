"""Bounded fresh-process jobs for complete independent selection-batch checks.

No graph/trace registry is sent to workers. This module does not establish
physical provenance; the coordinator must validate all node/batch origins and
join every expected job before constructing a CheckedBundle.
"""
from dataclasses import dataclass
from fractions import Fraction as F
import argparse,hashlib,json,math,os,resource,selectors,subprocess,sys,time
from validation.family5 import independent_oracle_v2 as oracle
from validation.family5.independent_oracle_v3 import exact_family_equal

JOB_LIMIT=8*1024**2
RESPONSE_LIMIT=32*1024
WORKER_AS=1024**3
MAX_PIECES=20000
SCHEMA='family5-selection-job-v1'
TAU_KERNEL='tau-precompute-v1'
KERNELS=('v2',TAU_KERNEL)

class BatchIncomplete(RuntimeError):pass

def require(ok,why):
 if not ok:raise ValueError(why)
def wire(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()
def sha(raw):return hashlib.sha256(raw).hexdigest()
def hash_id(value):return type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value)
def decode(raw):
 def pairs(rows):
  out={}
  for k,v in rows:require(k not in out,'duplicate job key');out[k]=v
  return out
 return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError('nonfinite job value')))
def number(value):
 require(type(value) in (F,int),'exact internal rational required')
 value=F(value);return [hex(value.numerator),hex(value.denominator)]
def rational(value):
 require(type(value) is list and len(value)==2 and all(type(x) is str for x in value),'rational-hex pair required')
 a,b=(int(x,16) for x in value)
 require(value==[hex(a),hex(b)] and b>0,'noncanonical rational hex')
 result=F(a,b);require((result.numerator,result.denominator)==(a,b),'unnormalized rational');return result
def encode_piece(p):
 return dict(domain=[number(p.lo),number(p.hi),p.lc,p.rc],m=number(p.m),b=number(p.b),chi=p.chi,
  rho=number(p.rho),pi=[list(x) for x in p.pi],state=list(p.state))
def read_piece(p):
 require(type(p) is dict and set(p)=={'domain','m','b','chi','rho','pi','state'},'piece fields')
 d=p['domain'];require(type(d) is list and len(d)==4 and type(d[2]) is bool and type(d[3]) is bool,'domain fields')
 lo,hi=rational(d[0]),rational(d[1]);require(lo<hi or lo==hi and d[2] and d[3],'empty domain')
 s=p['state'];pi=p['pi']
 require(type(s) is list and len(s)==3 and type(s[0]) is str and type(s[1]) is int and s[1] in (0,1) and type(s[2]) is int and s[2]>=0,'state fields')
 require(type(pi) is list and len(pi)==s[2] and all(type(x) is list and len(x)==2 and type(x[0]) is str and x[1] in ('C','S','CS') for x in pi),'prefix fields')
 require(type(p['chi']) is bool,'attainment flag')
 return oracle.Piece(lo,hi,d[2],d[3],rational(p['m']),rational(p['b']),p['chi'],rational(p['rho']),tuple(map(tuple,pi)),tuple(s))

def make_job(index,batch_sha,kind,a,b,context,*,kernel='v2'):
 require(type(kernel) is str and kernel in KERNELS,'unknown batch kernel')
 require(type(index) is int and index>=0 and hash_id(batch_sha) and hash_id(context),'job identity')
 require(kind in ('union','reduction'),'selection job kind')
 require(len(a)+len(b)<=MAX_PIECES,'piece count exceeds job cap')
 value=dict(schema=SCHEMA,index=index,batch_sha256=batch_sha,kind=kind,context_sha256=context,
  left=[encode_piece(p) for p in a],right=[encode_piece(p) for p in b])
 if kernel!='v2':value.update(schema='family5-selection-job-v2',kernel=kernel)
 raw=wire(value);require(len(raw)<=JOB_LIMIT,'serialized job exceeds cap');return raw

def evaluate(raw,*,expected_kernel=None):
 require(type(raw) is bytes and len(raw)<=JOB_LIMIT,'job byte cap')
 job=decode(raw);require(type(job) is dict,'job object')
 kernel='v2' if job.get('schema')==SCHEMA else job.get('kernel')
 require(kernel in KERNELS and (expected_kernel is None or kernel==expected_kernel),'worker kernel mismatch')
 fields={'schema','index','batch_sha256','kind','context_sha256','left','right'}
 if kernel!='v2':fields.add('kernel')
 require(set(job)==fields and job['schema']==(SCHEMA if kernel=='v2' else 'family5-selection-job-v2'),'job fields/schema')
 require(type(job['index']) is int and job['index']>=0 and hash_id(job['batch_sha256']) and hash_id(job['context_sha256']),'job identity')
 require(type(job['left']) is list and type(job['right']) is list and len(job['left'])+len(job['right'])<=MAX_PIECES,'job piece arrays')
 a,b=[read_piece(p) for p in job['left']],[read_piece(p) for p in job['right']]
 certificate=None
 if job['kind']=='union':
  require(not a or len({p.family() for p in a})==1,'union crosses family key');cells=exact_family_equal(a,b)
 elif job['kind']=='reduction':
  comparison=oracle
  if kernel==TAU_KERNEL:
   from validation.family5 import independent_oracle_v4 as comparison
  result=comparison.equivalent(a,b);comparison.antichain(list(dict.fromkeys(b)))
  cells=result['cells'];certificate=result['sha256']
 else:raise ValueError('unknown job kind')
 response=dict(schema='family5-selection-result-v1',index=job['index'],batch_sha256=job['batch_sha256'],
  kind=job['kind'],context_sha256=job['context_sha256'],job_sha256=sha(raw),cells=cells,certificate_sha256=certificate)
 if kernel!='v2':response.update(schema='family5-selection-result-v2',kernel=kernel)
 return response

def check_result(result,job):
 kernel=job.get('kernel','v2');require(kernel in KERNELS,'unknown expected kernel')
 expected={'schema','index','batch_sha256','kind','context_sha256','job_sha256','cells','certificate_sha256'}
 if kernel!='v2':expected.add('kernel')
 require(type(result) is dict and set(result)==expected,'result fields')
 require(result['schema']==('family5-selection-result-v1' if kernel=='v2' else 'family5-selection-result-v2') and
  result.get('kernel','v2')==kernel and type(result['index']) is int and
  all(result[k]==job[k] for k in ('index','batch_sha256','kind','context_sha256','job_sha256')),'foreign batch result')
 require(type(result['cells']) is int and result['cells']>=0,'result cell count')
 require(result['certificate_sha256'] is None if result['kind']=='union' else hash_id(result['certificate_sha256']),'result certificate binding')
 return result['cells']

@dataclass
class Slot:
 process:object
 cpu:int
 pending:dict|None=None
 sending:bytes=b''
 offset:int=0
 receiving:bytearray=None

class BatchExecutor:
 """At most four in-flight jobs; no unbounded queue or inherited graph heap."""
 def __init__(self,cpus,deadline,context,*,worker_as=WORKER_AS,kernel='v2'):
  require(type(cpus) in (tuple,list) and 1<=len(cpus)<=4 and all(type(x) is int for x in cpus) and len(set(cpus))==len(cpus),'worker CPU list')
  require(set(cpus)<=os.sched_getaffinity(0),'worker CPU outside allowed mask')
  require(type(deadline) is float and math.isfinite(deadline) and deadline>time.monotonic() and hash_id(context),'executor context/deadline')
  require(type(worker_as) is int and 128*1024**2<=worker_as<=WORKER_AS,'worker AS cap')
  require(type(kernel) is str and kernel in KERNELS,'unknown batch kernel')
  self.kernel=kernel;self.cpus=tuple(cpus);self.deadline=deadline;self.context=context;self.worker_as=worker_as
  self.slots=[];self.expected=None;self.submitted={};self.results={};self.closed=False;self.workers_joined=False
 def __enter__(self):
  try:
   for cpu in self.cpus:
    flags=['-'+('O'*sys.flags.optimize)] if sys.flags.optimize else []
    command=[sys.executable,'-B',*flags,'-m',__name__,'--worker','--cpu',str(cpu),'--as-bytes',str(self.worker_as)]
    if self.kernel!='v2':command+=['--kernel',self.kernel]
    def limits(cpu=cpu):
     resource.setrlimit(resource.RLIMIT_AS,(self.worker_as,self.worker_as))
     resource.setrlimit(resource.RLIMIT_CORE,(0,0));os.sched_setaffinity(0,{cpu})
    child=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,bufsize=0,preexec_fn=limits)
    os.set_blocking(child.stdin.fileno(),False);os.set_blocking(child.stdout.fileno(),False)
    self.slots.append(Slot(child,cpu,receiving=bytearray()))
   return self
  except BaseException:self.close();raise
 def start(self,expected):
  require(self.expected is None and bool(self.slots),'executor not entered or started twice')
  rows=list(expected)
  require(all(type(i) is int and i>=0 and hash_id(h) and k in ('union','reduction') for i,h,k in rows),'expected job fields')
  require(len({i for i,h,k in rows})==len(rows) and [i for i,h,k in rows]==sorted(i for i,h,k in rows),'duplicate or unordered expected jobs')
  self.expected=tuple(rows)
 def submit(self,index,batch_sha,kind,a,b):
  require(not self.closed and self.expected is not None,'inactive batch executor')
  n=len(self.submitted);require(n<len(self.expected) and (index,batch_sha,kind)==self.expected[n],'missing duplicate or reordered job submission')
  raw=make_job(index,batch_sha,kind,a,b,self.context,kernel=self.kernel)
  record=dict(index=index,batch_sha256=batch_sha,kind=kind,context_sha256=self.context,job_sha256=sha(raw),input_bytes=len(raw))
  if self.kernel!='v2':record['kernel']=self.kernel
  while all(s.pending is not None for s in self.slots):self.pump()
  slot=next(s for s in self.slots if s.pending is None)
  self.submitted[index]=record;slot.pending=record;slot.sending=raw+b'\n';slot.offset=0;slot.receiving=bytearray()
  while slot.pending is not None and slot.offset<len(slot.sending):self.pump()
 def pump(self,block=True):
  if time.monotonic()>=self.deadline:raise BatchIncomplete('batch deadline exceeded')
  with selectors.DefaultSelector() as selector:
   for slot in self.slots:
    if slot.process.poll() is not None:raise BatchIncomplete('batch worker exited before complete join')
    if slot.pending is None:continue
    selector.register(slot.process.stdout,selectors.EVENT_READ,slot)
    if slot.offset<len(slot.sending):selector.register(slot.process.stdin,selectors.EVENT_WRITE,slot)
   for key,event in selector.select(min(.05,max(0.,self.deadline-time.monotonic())) if block else 0):
    slot=key.data
    if event&selectors.EVENT_WRITE:
     try:slot.offset+=os.write(slot.process.stdin.fileno(),memoryview(slot.sending)[slot.offset:slot.offset+65536])
     except BlockingIOError:pass
    if event&selectors.EVENT_READ:
     chunk=os.read(slot.process.stdout.fileno(),min(65536,RESPONSE_LIMIT+1-len(slot.receiving)))
     if not chunk:raise BatchIncomplete('batch worker EOF')
     slot.receiving.extend(chunk)
     if len(slot.receiving)>RESPONSE_LIMIT:raise BatchIncomplete('batch response cap exceeded')
     if b'\n' in slot.receiving:
      raw,tail=bytes(slot.receiving).split(b'\n',1);require(not tail,'extra batch response bytes')
      envelope=decode(raw)
      require(type(envelope) is dict and set(envelope)=={'status','result','error','telemetry'},'worker response fields')
      if envelope['status']!='completed':raise BatchIncomplete('batch check failed: '+str(envelope['error'])[:512])
      require(slot.offset==len(slot.sending),'premature worker response')
      result=envelope['result'];check_result(result,slot.pending)
      require(result['index'] not in self.results,'duplicate worker result')
      telemetry=envelope['telemetry']
      require(type(telemetry) is dict and set(telemetry)=={'pid','cpu','as_bytes','cpu_seconds','kernel_peak_rss_bytes'},'worker telemetry fields')
      require(all(type(telemetry[k]) is int for k in ('pid','cpu','as_bytes','kernel_peak_rss_bytes')) and telemetry['kernel_peak_rss_bytes']>=0 and
       telemetry['pid']==slot.process.pid and telemetry['cpu']==slot.cpu and telemetry['as_bytes']==self.worker_as,'worker telemetry context')
      require(type(telemetry['cpu_seconds']) is float and math.isfinite(telemetry['cpu_seconds']) and telemetry['cpu_seconds']>=0,'worker CPU telemetry')
      self.results[result['index']]=dict(result=result,telemetry=telemetry,response_sha256=sha(raw))
      slot.pending=None;slot.sending=b'';slot.receiving=bytearray()
 def finish(self):
  require(not self.workers_joined and self.expected is not None and len(self.submitted)==len(self.expected),'missing submitted jobs or repeated finish')
  while any(s.pending is not None for s in self.slots):self.pump()
  require(set(self.results)==set(self.submitted)=={i for i,h,k in self.expected},'incomplete batch result join')
  # EOF handshake prevents unnoticed duplicate/trailing results after the last job.
  for slot in self.slots:slot.process.stdin.close()
  remaining=set(range(len(self.slots)))
  with selectors.DefaultSelector() as selector:
   for i,slot in enumerate(self.slots):selector.register(slot.process.stdout,selectors.EVENT_READ,i)
   while remaining:
    if time.monotonic()>=self.deadline:raise BatchIncomplete('batch shutdown deadline exceeded')
    for key,event in selector.select(.05):
     i=key.data;chunk=os.read(self.slots[i].process.stdout.fileno(),RESPONSE_LIMIT+1)
     require(not chunk,'unexpected trailing worker result')
     selector.unregister(key.fileobj);remaining.remove(i)
  for slot in self.slots:
   require(slot.process.wait(timeout=max(.001,self.deadline-time.monotonic()))==0,'batch worker failed at shutdown')
  self.workers_joined=True
  return sum(check_result(self.results[i]['result'],self.submitted[i]) for i,h,k in self.expected)
 def snapshot(self):
  result=dict(schema='family5-selection-ledger-v1',context_sha256=self.context,expected=self.expected,
   submitted=[self.submitted[i] for i in sorted(self.submitted)],results=[self.results[i] for i in sorted(self.results)],
   submitted_count=len(self.submitted),completed_count=len(self.results),cpus=list(self.cpus),worker_as_bytes=self.worker_as,
   complete=self.workers_joined and self.expected is not None and len(self.submitted)==len(self.results)==len(self.expected))
  if self.kernel!='v2':result.update(schema='family5-selection-ledger-v2',kernel=self.kernel)
  return result
 def close(self):
  self.closed=True
  for slot in self.slots:
   if slot.process.poll() is None:slot.process.kill()
  end=time.monotonic()+2
  failed=False
  for slot in self.slots:
   try:slot.process.wait(timeout=max(.001,end-time.monotonic()))
   except subprocess.TimeoutExpired:failed=True
   finally:
    slot.process.stdin.close();slot.process.stdout.close()
  if failed:raise BatchIncomplete('worker cleanup deadline exceeded')
 def __exit__(self,*exc):self.close()

def worker(cpu,as_bytes,kernel='v2'):
 require(kernel in KERNELS,'unknown worker kernel')
 require(cpu in os.sched_getaffinity(0),'worker affinity');os.sched_setaffinity(0,{cpu})
 require(128*1024**2<=as_bytes<=WORKER_AS,'worker AS cap');resource.setrlimit(resource.RLIMIT_AS,(as_bytes,as_bytes))
 resource.setrlimit(resource.RLIMIT_CORE,(0,0))
 for raw in iter(lambda:sys.stdin.buffer.readline(JOB_LIMIT+2),b''):
  require(raw.endswith(b'\n') and len(raw)<=JOB_LIMIT+1,'worker request framing/cap');raw=raw[:-1]
  start=time.process_time()
  try:result=evaluate(raw,expected_kernel=kernel);status='completed';error=None
  except Exception as exc:result=None;status='unresolved';error=type(exc).__name__+': '+str(exc)[:512]
  envelope=dict(status=status,result=result,error=error,telemetry=dict(pid=os.getpid(),cpu=cpu,as_bytes=as_bytes,
   cpu_seconds=time.process_time()-start,kernel_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024))
  response=wire(envelope)+b'\n';require(len(response)<=RESPONSE_LIMIT,'worker response cap')
  sys.stdout.buffer.write(response);sys.stdout.buffer.flush()

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--worker',action='store_true',required=True);parser.add_argument('--cpu',type=int,required=True);parser.add_argument('--as-bytes',type=int,required=True)
 parser.add_argument('--kernel',choices=KERNELS,default='v2')
 args=parser.parse_args();worker(args.cpu,args.as_bytes,args.kernel)
