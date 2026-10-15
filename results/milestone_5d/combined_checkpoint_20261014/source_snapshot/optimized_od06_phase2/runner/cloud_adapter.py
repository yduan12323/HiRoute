"""Exploratory Linux process supervisor; explicitly NOT a cgroup replacement."""
from dataclasses import dataclass, asdict
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import signal
import subprocess
import time
import psutil

THREAD_ENV = {name:'1' for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS',
    'VECLIB_MAXIMUM_THREADS','NUMEXPR_NUM_THREADS','BLIS_NUM_THREADS','ARROW_NUM_THREADS')}

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def atomic(path, data):
    path=Path(path);tmp=path.with_name(path.name+'.tmp')
    with tmp.open('w') as stream:
        json.dump(data,stream,sort_keys=True,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
    os.replace(tmp,path)
    fd=os.open(path.parent,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)

@dataclass(frozen=True)
class Limits:
    wall_seconds:float
    cpu_seconds:int
    address_space_bytes:int
    cpu:int
    cleanup_seconds:float=3.
    def validate(self):
        if (type(self.wall_seconds) not in (int,float) or not math.isfinite(self.wall_seconds)
            or self.wall_seconds<=0 or type(self.cpu_seconds) is not int or self.cpu_seconds<1
            or type(self.address_space_bytes) is not int or self.address_space_bytes<1
            or type(self.cpu) is not int or self.cpu not in os.sched_getaffinity(0)
            or type(self.cleanup_seconds) not in (int,float) or not 0<self.cleanup_seconds<=10):
            raise ValueError('Invalid exploratory limits or unavailable CPU affinity')

def _subreaper():
    libc=ctypes.CDLL(None,use_errno=True);old=ctypes.c_int()
    if libc.prctl(37,ctypes.byref(old),0,0,0)!=0 or libc.prctl(36,1,0,0,0)!=0:
        raise OSError(ctypes.get_errno(),'Linux child-subreaper required for verified cleanup')
    return libc,old.value

def run(argv, *, output_dir, limits, cwd=None, extra_env=None, pass_fds=(), parent_cpu_limit=None):
    """Only a single invocation per supervisor process; all commands are explicit.

    Per-process AS/CPU limits, single-core affinity, watchdog, and verified group/
    adopted-descendant cleanup. Never advertises hard aggregate RSS accounting.
    """
    limits.validate()
    if not argv or not Path(argv[0]).is_absolute():raise ValueError('Absolute executable required')
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=False)
    env=os.environ.copy();env.update(extra_env or {});env.update(THREAD_ENV)
    started=time.monotonic();parent_cpu=time.process_time();libc=old=None;proc=None
    observed={};usages=[];peak_rss=0;reason=None;root_status=None;error=None;cleanup_ok=False
    terminating=False
    class Interrupted(Exception):pass
    def interrupted(signum,frame):
        if not terminating:raise Interrupted('Supervisor interrupted by signal '+str(signum))
    handlers={sig:signal.getsignal(sig) for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGXCPU)}
    for sig in handlers:signal.signal(sig,interrupted)
    baseline={p.pid for p in psutil.Process().children()}
    start_record=dict(schema='hiroute.exploratory_cloud_receipt.v1',started_monotonic=started,
        argv=list(argv),limits=asdict(limits),thread_environment=THREAD_ENV,
        cgroup_enforced=False,aggregate_memory_hard_limit=False,
        memory_limit_kind='per_process_virtual_address_space',cpu_limit_kind='per_process_CPU_and_one_core_affinity',
        adapter_sha256=sha(__file__),complete=False)
    atomic(out/'receipt.json',start_record)
    def prepare():
        os.sched_setaffinity(0,{limits.cpu})
        resource.setrlimit(resource.RLIMIT_AS,(limits.address_space_bytes,limits.address_space_bytes))
        resource.setrlimit(resource.RLIMIT_CPU,(limits.cpu_seconds,limits.cpu_seconds+1))
    def sample():
        nonlocal peak_rss
        rss=0
        if proc is not None:
            for child in psutil.Process().children(recursive=True):
                if child.pid in baseline:continue
                try:
                    observed[child.pid]=child.create_time()
                    rss+=child.memory_info().rss
                except (psutil.NoSuchProcess,psutil.ZombieProcess):pass
        peak_rss=max(peak_rss,rss)
    def reap():
        nonlocal root_status
        # Single-invocation supervisor owns all newly adopted children.
        for child in psutil.Process().children():
            if child.pid in baseline:continue
            try:pid,status,usage=os.wait4(child.pid,os.WNOHANG)
            except ChildProcessError:continue
            if pid:
                usages.append(dict(pid=pid,user_s=usage.ru_utime,system_s=usage.ru_stime,maxrss_kib=usage.ru_maxrss))
                if proc is not None and pid==proc.pid:
                    root_status=status;proc.returncode=os.waitstatus_to_exitcode(status)
    try:
        libc,old=_subreaper()
        with (out/'stdout.txt').open('wb') as stdout,(out/'stderr.txt').open('wb') as stderr:
            proc=subprocess.Popen(argv,cwd=cwd,env=env,stdout=stdout,stderr=stderr,
                start_new_session=True,preexec_fn=prepare,pass_fds=tuple(pass_fds))
            if parent_cpu_limit is not None:
                resource.setrlimit(resource.RLIMIT_CPU,tuple(parent_cpu_limit))
            observed[proc.pid]=psutil.Process(proc.pid).create_time()
            atomic(out/'worker.json',dict(pid=proc.pid,process_group=proc.pid,started_monotonic=started))
            while root_status is None:
                sample();reap()
                if root_status is not None:break
                if time.monotonic()-started>=limits.wall_seconds:
                    reason='wall_timeout';break
                time.sleep(.02)
    except BaseException as exc:
        error=dict(type=type(exc).__name__,message=str(exc));reason='supervisor_exception'
    finally:
        terminating=True
        if proc is not None:
            # Kill the owned process group even after normal root completion.
            try:os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError:pass
        deadline=time.monotonic()+limits.cleanup_seconds
        while time.monotonic()<deadline:
            sample()
            for child in psutil.Process().children(recursive=True):
                if child.pid in baseline:continue
                try:child.kill()
                except psutil.NoSuchProcess:pass
            reap()
            remaining=[]
            for pid,created in observed.items():
                try:
                    obj=psutil.Process(pid)
                    if obj.create_time()==created:remaining.append(pid)
                except psutil.NoSuchProcess:pass
            if not remaining and not [p for p in psutil.Process().children() if p.pid not in baseline]:
                cleanup_ok=True;break
            time.sleep(.02)
        if libc is not None:libc.prctl(36,old,0,0,0)
        for sig,handler in handlers.items():signal.signal(sig,handler)
    if reason is None:
        rc=proc.returncode
        reason='success' if rc==0 else ('cpu_limit' if rc==-signal.SIGXCPU else 'worker_failed')
    if not cleanup_ok:reason='cleanup_failed'
    receipt=dict(start_record,complete=True,reason=reason,error=error,
        returncode=None if proc is None else proc.returncode,cleanup_verified=cleanup_ok,
        wall_seconds=time.monotonic()-started,parent_cpu_seconds=time.process_time()-parent_cpu,
        wait4_records=usages,conservative_wait4_cpu_seconds=sum(x['user_s']+x['system_s'] for x in usages),
        wait4_may_double_count_waited_descendants=True,sampled_process_tree_peak_rss_bytes=peak_rss,
        observed_pids=sorted(observed),thread_environment=THREAD_ENV)
    atomic(out/'receipt.json',receipt)
    if not cleanup_ok:raise RuntimeError('Owned descendant cleanup could not be verified')
    return receipt
