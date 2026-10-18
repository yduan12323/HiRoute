"""One fixed single-threaded supervisor with three sequential reserved slots.

Reuse the reviewed pending-window pipeline, without a two-arm coordinator.
The exact phase is1200 seconds; the search worker ceiling is1500 seconds.
"""
import math
import os
from pathlib import Path
import resource
import secrets
import signal
import sys
import threading
import time

from experiments.mechanism_recovery_v1 import run as base
from experiments.mechanism_recovery_v1.supervisor import run,Limits,PhaseBudget
from .domain import SCHEMA,ARMS,CASE,EXACT_PHASE_SECONDS,COMPLETION_POLICY


def atomic(path,value):
    path=Path(path);tmp=path.with_suffix('.tmp')
    tmp.write_bytes(base.canonical(value));os.replace(tmp,path)


def completion_ledger(arm,sha256):
    from .run import ARMS,CASE,METHOD
    if arm not in ARMS:raise ValueError('Unknown fixed pending feature arm')
    index=ARMS.index(arm)
    stages=[dict(id='prepare-'+CASE,operation='prepare',case=CASE,status='PENDING')]
    stages.extend(dict(id=f'{op}-{index}',operation=op,case=CASE,strategy=arm,status='PENDING') for op in ('search','verify'))
    return dict(schema=SCHEMA,scope='pending_window_treatment_only_completion',case=CASE,treatment_arm=arm,method=METHOD,denominator=3,
        manifest_sha256=sha256,common={},arms=[dict(case=CASE,strategy=arm,pair=0,status='PENDING')],stages=stages,status='RUNNING')

def block_pending(ledger,reason):
    for row in [*ledger['stages'],*ledger['arms']]:
        if row['status']=='PENDING':row['status']=reason


def run_plan(manifest_path,manifest_sha256,output,cpu,*,manifest_loader,expected_limits):
    """One fresh historical preparation, one exact search and one replay; no retry."""
    from .run import FIXED_CPU,ARMS,CASE,METHOD,PENDING_WINDOW_POLICY,CONFIGS
    arm=ARMS[0]
    started=time.process_time();manifest=manifest_loader(manifest_path,manifest_sha256)
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    ledger=completion_ledger(arm,manifest_sha256);limits=manifest.get('limits')
    index=ARMS.index(arm)
    def save():
        ledger['parent_cpu_seconds']=time.process_time()-started;atomic(output/'ledger.json',ledger)
    def stop(status,blocked):
        ledger['status']=status;block_pending(ledger,blocked);save();return ledger
    save()
    try:
        if base.canonical(limits)!=base.canonical(expected_limits):raise ValueError('Pending-window worker limits differ')
        if (len(ARMS)!=1 or EXACT_PHASE_SECONDS!=1200 or limits['search_seconds']!=1200 or limits['search_worker_wall_seconds']!=1500 or
            limits['search_worker_cpu_seconds']!=1500):raise ValueError('Fixed1200 phase/1500 search worker required')
        if threading.active_count()!=1 or threading.current_thread() is not threading.main_thread():
            raise ValueError('Dedicated single-threaded arm pipeline required')
        if type(cpu) is not int or cpu!=FIXED_CPU or cpu not in os.sched_getaffinity(0):raise ValueError('Fixed arm CPU unavailable')
        os.sched_setaffinity(0,{cpu})
        _,hard=resource.getrlimit(resource.RLIMIT_CPU)
        if hard!=resource.RLIM_INFINITY and hard<1501:raise ValueError('Inherited CPU hard limit cannot admit search worker1501s')
        as_hard=resource.getrlimit(resource.RLIMIT_AS)[1]
        if as_hard!=resource.RLIM_INFINITY and as_hard<limits['address_space_bytes']:raise ValueError('Inherited address-space hard limit is too small')
        resource.setrlimit(resource.RLIMIT_AS,(limits['address_space_bytes'],)*2)
        deadline=started+limits['parent_cpu_soft_seconds']
        resource.setrlimit(resource.RLIMIT_CPU,(math.ceil(deadline),hard))
        def expire(signum,frame):raise RuntimeError('Arm orchestration CPU budget exhausted')
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
            try:return base.load_worker_result(directory,receipt,operation,CASE,None if operation=='prepare' else arm)
            except (ValueError,KeyError,TypeError,OSError,AttributeError) as exc:
                ledger['artifact_admission_error']=dict(directory=str(directory),error=str(exc))
                ledger['stages'][position].update(status='UNKNOWN',reason='artifact_admission_failed')
                stop('UNKNOWN','BLOCKED_ARTIFACT_ADMISSION');return None
        def command(operation):
            return [sys.executable,'-m','experiments.pending_window_completion_v1.run','--worker',operation,
                '--manifest',str(Path(manifest_path).resolve()),'--manifest-sha256',manifest_sha256,'--case',CASE]
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
        directory=output/('prepare-'+CASE)
        receipt=launch(0,command('prepare'),output_dir=directory,limits=preparation,cwd=manifest['repo'])
        if receipt is None:return ledger
        ledger['common'][CASE]=receipt;ledger['stages'][0]['status']=receipt['status'];save()
        admit(directory,receipt,'prepare',0)
        if ledger['status']=='UNKNOWN':return ledger
        if receipt['status']!='SUCCESS':return stop('UNKNOWN' if receipt['status']=='UNKNOWN' else 'FAILED_COMMON_PREPARATION','BLOCKED_COMMON_PREPARATION')
        common=directory/'artifacts/prepared/common.json';common_sha=base.file_hash(common)
        row=ledger['arms'][0]
        if not can_launch():return ledger
        argv=command('arm')+['--common',str(common.resolve()),'--common-sha256',common_sha,'--strategy',arm]
        identity=dict(nonce=secrets.token_hex(16),manifest_sha256=manifest_sha256,
            source_closure_sha256=manifest['source']['closure_sha256'],common_sha256=common_sha,
            case_id=CASE,strategy=arm,feature_arm=arm,method=METHOD,arm_index=str(index),experiment_schema=SCHEMA,
            configuration_sha256=base.digest(CONFIGS[arm]),pending_window_policy_sha256=base.digest(PENDING_WINDOW_POLICY),
            completion_policy_sha256=base.digest(COMPLETION_POLICY))
        search_directory=output/f'arm-{index:02d}'
        receipt=launch(1,argv,output_dir=search_directory,limits=search,cwd=manifest['repo'],
            phase_budget=PhaseBudget(seconds=EXACT_PHASE_SECONDS,identity=identity))
        if receipt is None:return ledger
        row.update(status=receipt['status'],receipt=receipt);ledger['stages'][1]['status']=receipt['status'];save()
        admit(search_directory,receipt,'arm',1)
        if ledger['status']=='UNKNOWN':return ledger
        if receipt['status'] not in ('SUCCESS','TIMEOUT'):
            return stop('UNKNOWN' if receipt['status']=='UNKNOWN' else 'FAILED_SEARCH','BLOCKED_SEARCH_FAILED')
        if not can_launch():return ledger
        argv=command('verify')+['--common',str(common.resolve()),'--common-sha256',common_sha,
            '--search-directory',str(search_directory.resolve()),'--search-receipt-sha256',base.file_hash(search_directory/'receipt.json'),'--strategy',arm]
        verify_directory=output/f'verify-{index:02d}'
        receipt=launch(2,argv,output_dir=verify_directory,limits=verification,cwd=manifest['repo'])
        if receipt is None:return ledger
        row['verification']=receipt;ledger['stages'][2]['status']=receipt['status'];save()
        full=admit(verify_directory,receipt,'verify',2)
        if ledger['status']=='UNKNOWN':return ledger
        row['status']=full['status'] if full is not None else 'VERIFICATION_'+receipt['status']
        if receipt['status']!='SUCCESS':return stop('UNKNOWN' if receipt['status']=='UNKNOWN' else 'FAILED_VERIFICATION','BLOCKED_VERIFICATION_FAILED')
        ledger['status']='COMPLETED';save();return ledger
    except Exception as exc:
        ledger['pipeline_error']=dict(type=type(exc).__name__,error=str(exc)[:4000])
        return stop('UNKNOWN','BLOCKED_PIPELINE_EXCEPTION')
