"""Two dedicated case supervisors, each with five immutable reserved slots.

The coordinator never calls the low-level supervisor. Each pipeline is a fresh
single-threaded process, owns exactly one heavy child at a time, and has separate
paths and a durable ledger. Resource observations are not aggregate hard limits.
"""
import ctypes
import math
import os
from pathlib import Path
import resource
import secrets
import signal
import subprocess
import sys
import threading
import time

from experiments.mechanism_recovery_v1 import run as base
from experiments.mechanism_recovery_v1 import supervisor
from experiments.mechanism_recovery_v1.supervisor import run,Limits,PhaseBudget,THREAD_ENV
from .domain import SCHEMA,CASES,EXACT_PHASE_SECONDS,COMPLETION_POLICY


def atomic(path,value):
    path=Path(path);tmp=path.with_suffix('.tmp')
    tmp.write_bytes(base.canonical(value));os.replace(tmp,path)


def case_ledger(case,sha256):
    from .run import PAIRS
    pair=CASES.index(case);order=dict(PAIRS)[case]
    arms=[dict(case=case,strategy=m,pair=pair,status='PENDING') for m in order]
    stages=[dict(id='prepare-'+case,operation='prepare',case=case,status='PENDING')]
    for local,method in enumerate(order):
        index=pair*2+local
        stages.extend(dict(id=f'{op}-{index}',operation=op,case=case,strategy=method,status='PENDING') for op in ('search','verify'))
    return dict(schema=SCHEMA,scope='post_service_matched_case_pipeline',case=case,denominator=5,
        manifest_sha256=sha256,common={},arms=arms,stages=stages,status='RUNNING')


def block_pending(ledger,reason):
    for row in [*ledger['stages'],*ledger['arms']]:
        if row['status']=='PENDING':row['status']=reason


def run_case_plan(manifest_path,manifest_sha256,output,case,cpu,*,manifest_loader,expected_limits):
    """One preparation followed by two serial search/replay pairs; no retry."""
    from .run import CPU_BY_CASE
    started=time.process_time();manifest=manifest_loader(manifest_path,manifest_sha256)
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    ledger=case_ledger(case,manifest_sha256);limits=manifest.get('limits');strategy=None
    def save():
        ledger['parent_cpu_seconds']=time.process_time()-started;atomic(output/'ledger.json',ledger)
    def stop(status,blocked):
        ledger['status']=status;block_pending(ledger,blocked);save();return ledger
    save()
    try:
        if base.canonical(limits)!=base.canonical(expected_limits):raise ValueError('Cohort worker limits differ')
        if (EXACT_PHASE_SECONDS!=600 or limits['search_seconds']!=600 or limits['search_worker_wall_seconds']!=900 or
            limits['search_worker_cpu_seconds']!=900):raise ValueError('Fixed600 phase/900 search worker required')
        if type(cpu) is not int or cpu!=CPU_BY_CASE[case] or cpu not in os.sched_getaffinity(0):raise ValueError('Fixed case CPU unavailable')
        os.sched_setaffinity(0,{cpu})
        _,hard=resource.getrlimit(resource.RLIMIT_CPU)
        if hard!=resource.RLIM_INFINITY and hard<901:raise ValueError('Inherited CPU hard limit cannot admit search worker901s')
        as_hard=resource.getrlimit(resource.RLIMIT_AS)[1]
        if as_hard!=resource.RLIM_INFINITY and as_hard<limits['address_space_bytes']:raise ValueError('Inherited address-space hard limit is too small')
        resource.setrlimit(resource.RLIMIT_AS,(limits['address_space_bytes'],)*2)
        deadline=started+limits['parent_cpu_soft_seconds']
        resource.setrlimit(resource.RLIMIT_CPU,(math.ceil(deadline),hard))
        def expire(signum,frame):raise RuntimeError('Case orchestration CPU budget exhausted')
        signal.signal(signal.SIGXCPU,expire)
        common_limits=dict(address_space_bytes=limits['address_space_bytes'],cpu=cpu)
        preparation=Limits(wall_seconds=limits['stage_wall_seconds'],cpu_seconds=limits['worker_cpu_seconds'],**common_limits)
        search=Limits(wall_seconds=limits['search_worker_wall_seconds'],cpu_seconds=limits['search_worker_cpu_seconds'],**common_limits)
        verification=Limits(wall_seconds=limits['verification_wall_seconds'],cpu_seconds=limits['verification_cpu_seconds'],**common_limits)
        def can_launch():
            if time.process_time()<deadline-10:return True
            stop('PARENT_CPU_BUDGET_EXHAUSTED','BLOCKED_PARENT_CPU_BUDGET');return False
        def admit(directory,receipt,operation,position):
            if receipt.get('status')!='SUCCESS':return None
            try:return base.load_worker_result(directory,receipt,operation,case,None if operation=='prepare' else strategy)
            except (ValueError,KeyError,TypeError,OSError,AttributeError) as exc:
                ledger['artifact_admission_error']=dict(directory=str(directory),error=str(exc))
                ledger['stages'][position].update(status='UNKNOWN',reason='artifact_admission_failed')
                stop('UNKNOWN','BLOCKED_ARTIFACT_ADMISSION');return None
        def command(operation):
            return [sys.executable,'-m','experiments.post_service_cohort_v1.run','--worker',operation,
                '--manifest',str(Path(manifest_path).resolve()),'--manifest-sha256',manifest_sha256,'--case',case]
        def launch(position,argv,**kwargs):
            try:
                receipt=run(argv,**kwargs)
                if type(receipt) is not dict:raise ValueError('Supervisor receipt is not a dictionary')
                if receipt.get('cleanup_verified') is not True:
                    ledger.setdefault('unadmitted_receipts',{})[ledger['stages'][position]['id']]=receipt
                    ledger['cleanup_error']=dict(stage=ledger['stages'][position]['id'],reported_status=receipt.get('status'),cleanup_verified=False)
                    ledger['stages'][position]['status']='UNKNOWN';stop('UNKNOWN','BLOCKED_UNVERIFIED_CLEANUP');return None
                return receipt
            except Exception as exc:
                ledger['launch_error']=dict(stage=ledger['stages'][position]['id'],type=type(exc).__name__,error=str(exc)[:4000],cleanup_verified=False)
                ledger['stages'][position]['status']='UNKNOWN';stop('UNKNOWN','BLOCKED_LAUNCH_EXCEPTION');return None
        if not can_launch():return ledger
        directory=output/('prepare-'+case)
        receipt=launch(0,command('prepare'),output_dir=directory,limits=preparation,cwd=manifest['repo'])
        if receipt is None:return ledger
        ledger['common'][case]=receipt;ledger['stages'][0]['status']=receipt['status'];save()
        admit(directory,receipt,'prepare',0)
        if ledger['status']=='UNKNOWN':return ledger
        if receipt['status']!='SUCCESS':return stop('UNKNOWN' if receipt['status']=='UNKNOWN' else 'FAILED_COMMON_PREPARATION','BLOCKED_COMMON_PREPARATION')
        common=directory/'artifacts/prepared/common.json';common_sha=base.file_hash(common)
        for local,arm in enumerate(ledger['arms']):
            strategy=arm['strategy'];index=2*CASES.index(case)+local;search_position=1+2*local
            if not can_launch():return ledger
            argv=command('arm')+['--common',str(common.resolve()),'--common-sha256',common_sha,'--strategy',strategy]
            identity=dict(nonce=secrets.token_hex(16),manifest_sha256=manifest_sha256,
                source_closure_sha256=manifest['source']['closure_sha256'],common_sha256=common_sha,
                case_id=case,strategy=strategy,method=strategy,arm_index=str(index),experiment_schema=SCHEMA,
                completion_policy_sha256=base.digest(COMPLETION_POLICY))
            search_directory=output/f'arm-{index:02d}'
            receipt=launch(search_position,argv,output_dir=search_directory,limits=search,cwd=manifest['repo'],
                phase_budget=PhaseBudget(seconds=EXACT_PHASE_SECONDS,identity=identity))
            if receipt is None:return ledger
            arm.update(status=receipt['status'],receipt=receipt);ledger['stages'][search_position]['status']=receipt['status'];save()
            admit(search_directory,receipt,'arm',search_position)
            if ledger['status']=='UNKNOWN':return ledger
            if receipt['status'] not in ('SUCCESS','TIMEOUT'):
                return stop('UNKNOWN' if receipt['status']=='UNKNOWN' else 'FAILED_SEARCH','BLOCKED_SEARCH_FAILED')
            if not can_launch():return ledger
            argv=command('verify')+['--common',str(common.resolve()),'--common-sha256',common_sha,
                '--search-directory',str(search_directory.resolve()),'--search-receipt-sha256',base.file_hash(search_directory/'receipt.json'),'--strategy',strategy]
            verify_directory=output/f'verify-{index:02d}'
            receipt=launch(search_position+1,argv,output_dir=verify_directory,limits=verification,cwd=manifest['repo'])
            if receipt is None:return ledger
            arm['verification']=receipt;ledger['stages'][search_position+1]['status']=receipt['status'];save()
            full=admit(verify_directory,receipt,'verify',search_position+1)
            if ledger['status']=='UNKNOWN':return ledger
            arm['status']=full['status'] if full is not None else 'VERIFICATION_'+receipt['status']
            if receipt['status']!='SUCCESS':return stop('UNKNOWN' if receipt['status']=='UNKNOWN' else 'FAILED_VERIFICATION','BLOCKED_VERIFICATION_FAILED')
        ledger['status']='COMPLETED';save();return ledger
    except Exception as exc:
        ledger['pipeline_error']=dict(type=type(exc).__name__,error=str(exc)[:4000])
        return stop('UNKNOWN','BLOCKED_PIPELINE_EXCEPTION')


def available_memory_admission(policy):
    """Read-only preflight. MemAvailable can change immediately after sampling."""
    entries={line.split(':',1)[0]:line.split(':',1)[1].split() for line in Path('/proc/meminfo').read_text().splitlines()}
    row=entries.get('MemAvailable')
    if row is None or len(row)!=2 or row[1]!='kB' or not row[0].isdigit():raise ValueError('MemAvailable observation unavailable')
    available=int(row[0])*1024;required=policy['required_available_memory_bytes']
    if type(required) is not int or required!=2*policy['admission_rss_budget_bytes_per_heavy_worker']+policy['available_memory_reserve_bytes']:
        raise ValueError('Fixed two-case memory admission policy differs')
    return dict(available_bytes=available,required_bytes=required,admitted=available>=required,
        sampled_wall_ns=time.monotonic_ns(),reservation=False,aggregate_hard_limit=False)


def run_coordinator(manifest_path,manifest_sha256,output,*,manifest_loader,expected_limits):
    """Supervise exactly two pipeline processes; never run heavy work here."""
    from .run import CPU_BY_CASE,CONCURRENCY_POLICY
    from experiments.envelope_sweep_gate_v1.run import read_bounded_json
    manifest=manifest_loader(manifest_path,manifest_sha256);output=Path(output);output.mkdir(parents=True,exist_ok=False)
    pipelines={case:case_ledger(case,manifest_sha256) for case in CASES}
    ledger=dict(schema=SCHEMA,scope='post_service_matched_two_case_cohort',denominator=10,manifest_sha256=manifest_sha256,
        pipelines=pipelines,status='RUNNING',concurrency_policy=CONCURRENCY_POLICY)
    def save():
        ledger['stages']=[r for case in CASES for r in pipelines[case]['stages']]
        ledger['arms']=[r for case in CASES for r in pipelines[case]['arms']]
        atomic(output/'ledger.json',ledger)
    save();procs={};streams=[];old=ctypes.c_int();enabled=False;cleanup=False;cleaning=False;handlers={};error=None
    libc=ctypes.CDLL(None,use_errno=True)
    def interrupt(signum,frame):
        if not cleaning:raise InterruptedError('Coordinator signal '+str(signum))
    try:
        if base.canonical(manifest.get('limits'))!=base.canonical(expected_limits):raise ValueError('Cohort worker limits differ')
        if set(CPU_BY_CASE.values())!={0,1} or not {0,1}<=os.sched_getaffinity(0):raise ValueError('Fixed cohort CPUs0/1 unavailable')
        ledger['memory_admission']=available_memory_admission(CONCURRENCY_POLICY);save()
        if not ledger['memory_admission']['admitted']:raise ValueError('Insufficient MemAvailable for fixed two-case budget; concurrency unchanged')
        if threading.active_count()!=1 or threading.current_thread() is not threading.main_thread():raise ValueError('Dedicated single-threaded coordinator required')
        if supervisor._children(os.getpid()):raise ValueError('Coordinator must have no pre-existing children')
        cpu_hard=resource.getrlimit(resource.RLIMIT_CPU)[1]
        if cpu_hard!=resource.RLIM_INFINITY and cpu_hard<901:raise ValueError('Inherited CPU hard limit cannot admit search worker901s')
        if libc.prctl(37,ctypes.byref(old),0,0,0) or libc.prctl(36,1,0,0,0):raise OSError('Linux coordinator subreaper required')
        enabled=True
        # Only the fresh command-line coordinator is affected by these limits.
        _,hard=resource.getrlimit(resource.RLIMIT_AS)
        if hard!=resource.RLIM_INFINITY and hard<expected_limits['address_space_bytes']:raise ValueError('Coordinator inherited address-space limit too small')
        resource.setrlimit(resource.RLIMIT_AS,(expected_limits['address_space_bytes'],)*2)
        for sig in (signal.SIGTERM,signal.SIGINT):handlers[sig]=signal.getsignal(sig);signal.signal(sig,interrupt)
        env=os.environ.copy();env.update(THREAD_ENV)
        for case in CASES:
            stdout=(output/(case+'.stdout')).open('xb');stderr=(output/(case+'.stderr')).open('xb');streams.extend((stdout,stderr))
            argv=[sys.executable,'-m','experiments.post_service_cohort_v1.run','--pipeline','--manifest',str(Path(manifest_path).resolve()),
                '--manifest-sha256',manifest_sha256,'--case',case,'--cpu',str(CPU_BY_CASE[case]),'--output',str((output/case).resolve())]
            proc=subprocess.Popen(argv,cwd=manifest['repo'],env=env,stdout=stdout,stderr=stderr,start_new_session=True)
            procs[case]=dict(process=proc,started=time.monotonic())
        while True:
            live=False
            for case,entry in procs.items():
                proc=entry['process'];rc=proc.poll()
                if rc is None:
                    live=True
                    if time.monotonic()-entry['started']>=expected_limits['pipeline_wall_seconds']:raise TimeoutError('Case pipeline wall watchdog: '+case)
                elif rc!=0:raise RuntimeError('Case pipeline process failed: '+case+' returncode='+str(rc))
            if any(stream.tell()>1024*1024 for stream in streams):raise RuntimeError('Case pipeline log limit exceeded')
            if not live:break
            time.sleep(.1)
    except BaseException as exc:
        error=dict(type=type(exc).__name__,error=str(exc)[:4000]);ledger['coordinator_error']=error
    finally:
        cleaning=True
        # On an interrupted/crashed pipeline, adopted descendants are still
        # owned by this subreaper. Kill and reap all owned descendants before
        # admitting cleanup. Never count a vanished pipeline as proof by itself.
        if enabled:
            try:
                deadline=time.monotonic()+5
                while time.monotonic()<deadline:
                    tree,overflow=supervisor._tree(256)
                    for pid,identity in tree.items():
                        current=supervisor._stat(pid)
                        if current and current[0]==identity[0]:
                            try:os.kill(pid,signal.SIGKILL)
                            except ProcessLookupError:pass
                    for pid in supervisor._children(os.getpid()):
                        try:
                            got,status=os.waitpid(pid,os.WNOHANG)
                            if got:
                                for entry in procs.values():
                                    if entry['process'].pid==got:entry['process'].returncode=os.waitstatus_to_exitcode(status)
                        except ChildProcessError:pass
                    if not supervisor._children(os.getpid()):cleanup=not overflow;break
                    time.sleep(.02)
                if cleanup:libc.prctl(36,old.value,0,0,0)
            except (OSError,ValueError,RuntimeError) as exc:
                cleanup=False;ledger['cleanup_error']=dict(type=type(exc).__name__,error=str(exc)[:4000])
        else:cleanup=not procs
        for sig,handler in handlers.items():signal.signal(sig,handler)
        for stream in streams:stream.close()
    for case in CASES:
        original=pipelines[case]
        if case in procs:
            proc=procs[case]['process'];rc=proc.poll()
            try:
                value,sha,size=read_bounded_json(output/case/'ledger.json')
                if (type(value) is not dict or value.get('schema')!=SCHEMA or value.get('case')!=case or value.get('manifest_sha256')!=manifest_sha256 or
                    value.get('denominator')!=5 or len(value.get('stages',[]))!=5 or len(value.get('arms',[]))!=2):raise ValueError('Pipeline ledger identity/denominator differs')
                original=value;original['pipeline_ledger_sha256']=sha;pipelines[case]=original
            except (OSError,ValueError,KeyError,TypeError,AttributeError) as exc:
                original['pipeline_admission_error']=str(exc);original['status']='UNKNOWN'
            original.update(process_returncode=rc,pipeline_cleanup_verified=cleanup)
            if rc!=0 or not cleanup:original['status']='UNKNOWN'
        else:
            original.update(status='UNKNOWN',process_returncode=None,pipeline_cleanup_verified=cleanup)
        if error is not None:original['status']='UNKNOWN'
        block_pending(original,'BLOCKED_COORDINATOR_ERROR' if error else 'BLOCKED_PIPELINE_STOPPED')
    ledger['cleanup_verified']=cleanup
    ledger['status']='COMPLETED' if error is None and cleanup and all(x['status']=='COMPLETED' for x in pipelines.values()) else 'UNKNOWN'
    save();return ledger
