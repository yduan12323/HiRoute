"""Single-worker cumulative CPU admission for the declared shared-input pilot."""
import argparse
from decimal import Decimal,ROUND_CEILING
import fcntl
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import time


def atomic(path, value):
    temp=path.with_suffix('.tmp')
    with temp.open('w') as f:
        json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    temp.replace(path)


def total_spent(d):
    value=Decimal(str(d['fixed_precharge_CPU_s']))+sum(
        (Decimal(str(v)) for v in d['phase_charged_CPU_s'].values()),Decimal(0))
    return value.quantize(Decimal('.000000001'),rounding=ROUND_CEILING)


def admit(d, phase, reserve, cpu, wall):
    if d.get('active'):raise ValueError('uncertain active work; inspect receipt/PID before continuation')
    if d['state'].startswith('closed'):raise ValueError('stage closed')
    if d.get('real_work_stopped') and phase not in ('development','close'):
        raise ValueError('real phase failed; no retry or downstream real admission')
    if phase not in d['allocations_CPU_s']:raise ValueError('unknown phase')
    if not 0<cpu+16<=reserve or not 0<wall<=300:raise ValueError('child/controller/tail envelope')
    used=Decimal(str(d['phase_charged_CPU_s'][phase]))
    if phase==d['fixed_precharge_phase']:used+=Decimal(str(d['fixed_precharge_CPU_s']))
    used=used.quantize(Decimal('.000000001'),rounding=ROUND_CEILING)
    if used+reserve>d['allocations_CPU_s'][phase]:raise ValueError('phase exhausted')
    if total_spent(d)+reserve>d['cap_CPU_s']:raise ValueError('stage exhausted')
    if Decimal(d['carried_research_CPU_s'])+total_spent(d)+reserve>d['original_cap_CPU_s']:
        raise ValueError('global research budget exhausted')
    count=sum(r['phase']==phase for r in d['records'])
    if phase in d['allowed_real_attempts'] and count>=d['allowed_real_attempts'][phase]:
        raise ValueError('one real attempt only; no automatic retry')
    if phase=='generation' and (cpu>270 or wall>300):raise ValueError('generation envelope')
    if phase=='validation' and cpu>150:raise ValueError('validation envelope')
    if phase=='optimization' and (cpu!=120 or wall!=120):raise ValueError('fixed120s optimizer envelope')


def tree_usage(process):
    # Waited children disappear from the live tree. Their cumulative CPU stays
    # in their living parent's children_* counters, so compiler work is retained.
    group=[process,*process.children(recursive=True)]
    cpu=rss=0
    for p in group:
        try:
            c=p.cpu_times();cpu+=sum(getattr(c,k,0) for k in ('user','system','children_user','children_system'))
            rss+=p.memory_info().rss
        except __import__('psutil').NoSuchProcess:pass
    return cpu,rss


def disk_size(root):
    total=0
    for p in root.rglob('*'):
        try:
            if p.is_file():total+=p.stat().st_size
        except FileNotFoundError:pass
    return total


def file_digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024**2),b''):h.update(block)
    return h.hexdigest()


def reap_group(worker):
    if worker is None:return
    # The root may have exited while its compiler still lives in the session.
    # Cleanup owns the session, not just the root's current poll() state.
    try:os.killpg(worker.pid,signal.SIGKILL)
    except ProcessLookupError:pass
    worker.wait()


def terminal_summary(path):
    """Bound metadata decoding; the complete artifact is hashed separately."""
    if not path.exists():return None,None,None,'missing terminal receipt'
    try:
        with path.open('rb') as f:data=f.read(4*1024**2+1)
        if len(data)>4*1024**2:return None,None,None,'terminal metadata byte quota'
        value=json.loads(data)
        return value.get('mode'),value.get('status'),value.get('comparison',{}).get('status'),None
    except (ValueError,TypeError,AttributeError) as exc:return None,None,None,'invalid terminal metadata: '+str(exc)


def record_outcome(d,r):
    """The actual controller finalization, including automatic real stop."""
    d['phase_charged_CPU_s'][r['phase']]=str(Decimal(str(d['phase_charged_CPU_s'][r['phase']]))+Decimal(str(r['charged_CPU_s'])))
    d['records'].append(r);d['active']=None
    if r['phase'] not in ('freeze','generation','validation','optimization'):return
    failed=(r.get('actual_child_returncode')!=0 or r.get('guard_reason') is not None
        or r.get('terminal_read_error') is not None or r.get('terminal_mode')!=r['phase']
        or r.get('terminal_status')!='COMPLETE')
    if r['phase']=='optimization' and r.get('comparison_status') not in (
            'attained_optimum','primary_unattained','secondary_unattained'):failed=True
    if failed:
        d['real_work_stopped']=True;d['state']='failed_real_phase_stopped'
        d['real_work_stopped_reason']=dict(phase=r['phase'],label=r['label'],
            child_returncode=r.get('actual_child_returncode'),guard=r.get('guard_reason'),
            terminal_status=r.get('terminal_status'),comparison_status=r.get('comparison_status'))


def main():
    import psutil
    a=argparse.ArgumentParser();a.add_argument('--ledger',required=True);a.add_argument('--phase',required=True)
    a.add_argument('--label',required=True);a.add_argument('--cpu',type=int,required=True)
    a.add_argument('--reserve',type=int,required=True);a.add_argument('--wall',type=int,required=True)
    a.add_argument('command',nargs=argparse.REMAINDER);a=a.parse_args()
    path=Path(a.ledger).resolve();root=path.parent
    lock=(root/'controller.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    d=json.loads(path.read_text());admit(d,a.phase,a.reserve,a.cpu,a.wall)
    argv=a.command[1:] if a.command[:1]==['--'] else a.command
    log=root/(a.label+'.log')
    if log.exists():raise ValueError('existing output; do not repeat uncertain/completed work')
    r=dict(label=a.label,phase=a.phase,argv=argv,reserved_CPU_s=a.reserve,started_at=time.time(),
           controller_pid=os.getpid(),controller_created_at=psutil.Process().create_time(),
           controller_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
           child_CPU_limit=a.cpu,controller_hard_CPU_limit=15,wall_limit=a.wall,
           RSS_limit_bytes=3*1024**3,host_headroom_bytes=2*1024**3)
    d['active']=r;atomic(path,d);worker=None;reason=None;peak=cpu_peak=0;start=None
    minimum=psutil.virtual_memory().available;free=shutil.disk_usage(root).free
    maximum=(1 if a.phase in ('development','freeze','close') else 3)*1024**3
    rss_limit=min(maximum,max(0,minimum-2*1024**3-64*1024**2))
    r.update(RSS_limit_bytes=rss_limit,admission_host_available_bytes=minimum,
             controller_memory_margin_bytes=64*1024**2)
    class Stop(Exception):pass
    def stopped(signum,frame):raise Stop('controller signal '+str(signum))
    for sig in (signal.SIGXCPU,signal.SIGTERM,signal.SIGINT):signal.signal(sig,stopped)
    before=resource.getrusage(resource.RUSAGE_CHILDREN)
    try:
        if rss_limit<1024**3 or free<4*1024**3:
            reason='unstarted_host_resource_guard';r['returncode']=75
        else:
            def limit():
                resource.setrlimit(resource.RLIMIT_CPU,(a.cpu,a.cpu))
                resource.setrlimit(resource.RLIMIT_FSIZE,(512*1024**2,512*1024**2))
            temp=root/'scratch-temp';temp.mkdir(exist_ok=True)
            env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',
                     VECLIB_MAXIMUM_THREADS='1',TMPDIR=str(temp),SQLITE_TMPDIR=str(temp))
            with log.open('x') as stream:
                worker=subprocess.Popen(argv,stdout=stream,stderr=subprocess.STDOUT,text=True,
                    start_new_session=True,preexec_fn=limit,env=env)
                resource.setrlimit(resource.RLIMIT_CPU,(10,15))
                r.update(pid=worker.pid,process_created_at=psutil.Process(worker.pid).create_time());atomic(path,d)
                start=time.monotonic()
                while worker.poll() is None:
                    minimum=min(minimum,psutil.virtual_memory().available)
                    try:
                        cpu,rss=tree_usage(psutil.Process(worker.pid));cpu_peak=max(cpu_peak,cpu);peak=max(peak,rss)
                    except psutil.NoSuchProcess:pass
                    if cpu_peak>=a.cpu:reason='process_tree_CPU_guard'
                    if peak>rss_limit:reason='process_tree_RSS_guard'
                    if minimum<2*1024**3:reason='host_memory_guard'
                    free=min(free,shutil.disk_usage(root).free)
                    if free<2*1024**3:reason='host_disk_guard'
                    if disk_size(root)>2*1024**3:reason='aggregate_output_disk_guard'
                    if time.monotonic()-start>a.wall:reason='wall_guard'
                    if reason:raise Stop(reason)
                    time.sleep(.1)
                r['returncode']=worker.wait()
    except BaseException as exc:
        reason=reason or 'controller_exception';r.update(error=repr(exc),returncode=125)
    finally:
        reap_group(worker)
    after=resource.getrusage(resource.RUSAGE_CHILDREN)
    child=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime
    elapsed=time.monotonic()-start if start is not None else 0
    if elapsed>a.wall and reason is None:reason='wall_guard_after_exit'
    terminal=root/(a.phase+'.result.json')
    terminal_digest=file_digest(terminal) if terminal.exists() else None
    mode,status,comparison,error=terminal_summary(terminal)
    cost=Decimal(str(max(child,cpu_peak)+time.process_time()+1)).quantize(Decimal('.000000001'),rounding=ROUND_CEILING)
    r.update(charged_CPU_s=str(cost),finished_at=time.time(),guard_reason=reason,elapsed_wall_s=elapsed,
             terminal_sha256=terminal_digest,
             terminal_mode=mode,terminal_status=status,comparison_status=comparison,terminal_read_error=error,
             actual_child_returncode=worker.returncode if worker else None,
             measured_waited_child_CPU_s=child,sampled_tree_CPU_peak_s=cpu_peak,
             process_tree_peak_RSS_bytes=peak,host_available_min_bytes=minimum,
             host_disk_free_min_bytes=free,child_maxrss_native=after.ru_maxrss)
    record_outcome(d,r)
    atomic(path,d);print(json.dumps(r),flush=True)
    if log.exists():
        with log.open('rb') as f:
            f.seek(max(0,log.stat().st_size-4000));tail=f.read(4000).decode('utf-8',errors='replace')
    else:tail='worker not started'
    print(tail,flush=True)
    if total_spent(d)>d['cap_CPU_s']:raise SystemExit('observed cap exceeded')
    raise SystemExit(75 if reason else r['returncode'])


if __name__=='__main__':main()
