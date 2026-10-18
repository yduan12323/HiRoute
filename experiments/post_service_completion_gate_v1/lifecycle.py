"""Isolated fixed three-slot orchestration around the historical supervisor.

The historical batch helper admits only120/240-second phases. This adapter
does not change that helper: it declares exactly one600-second treatment and
separate900-second search-worker caps, keeping preparation/replay caps intact.
"""
import math
import os
from pathlib import Path
import resource
import secrets
import signal
import sys
import time

from experiments.mechanism_recovery_v1 import run as base
from experiments.mechanism_recovery_v1.supervisor import run,Limits,PhaseBudget
from .domain import SCHEMA,CASE,ARMS,EXACT_PHASE_SECONDS,COMPLETION_POLICY


def run_plan(manifest_path,manifest_sha256,output,cpu,*,manifest_loader,expected_limits):
    """One preparation, one treatment search, one independent replay; no retry."""
    started=time.process_time();manifest=manifest_loader(manifest_path,manifest_sha256)
    limits=manifest.get('limits')
    if base.canonical(limits)!=base.canonical(expected_limits):raise ValueError('Completion worker limits differ')
    if (len(ARMS)!=1 or EXACT_PHASE_SECONDS!=600 or limits['search_seconds']!=600 or
        limits['search_worker_wall_seconds']!=900 or limits['search_worker_cpu_seconds']!=900):
        raise ValueError('Fixed600-second treatment/900-second search worker required')
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    if type(cpu) is not int or cpu not in os.sched_getaffinity(0):raise ValueError('Requested CPU unavailable')
    os.sched_setaffinity(0,{cpu})
    _,hard=resource.getrlimit(resource.RLIMIT_CPU)
    if hard!=resource.RLIM_INFINITY and hard<limits['search_worker_cpu_seconds']+1:
        raise ValueError('Inherited CPU hard limit cannot admit search worker901s')
    deadline=started+limits['parent_cpu_soft_seconds']
    resource.setrlimit(resource.RLIMIT_CPU,(math.ceil(deadline),hard))
    def expire(signum,frame):raise RuntimeError('Total orchestration CPU budget exhausted')
    signal.signal(signal.SIGXCPU,expire)
    common_limits=dict(address_space_bytes=limits['address_space_bytes'],cpu=cpu)
    preparation=Limits(wall_seconds=limits['stage_wall_seconds'],cpu_seconds=limits['worker_cpu_seconds'],**common_limits)
    search=Limits(wall_seconds=limits['search_worker_wall_seconds'],cpu_seconds=limits['search_worker_cpu_seconds'],**common_limits)
    verification=Limits(wall_seconds=limits['verification_wall_seconds'],cpu_seconds=limits['verification_cpu_seconds'],**common_limits)
    strategy=ARMS[0]
    arm=dict(case=CASE,strategy=strategy,pair=0,status='PENDING')
    stages=[dict(id='prepare-'+CASE,operation='prepare',case=CASE,status='PENDING'),
        dict(id='search-0',operation='search',case=CASE,strategy=strategy,status='PENDING'),
        dict(id='verify-0',operation='verify',case=CASE,strategy=strategy,status='PENDING')]
    ledger=dict(schema=SCHEMA,scope='post_service_treatment_only_completion',denominator=3,
        manifest_sha256=manifest_sha256,common={},arms=[arm],stages=stages,status='RUNNING')
    def save():
        ledger['parent_cpu_seconds']=time.process_time()-started
        temporary=output/'ledger.tmp';temporary.write_bytes(base.canonical(ledger));os.replace(temporary,output/'ledger.json')
    def stop(status,blocked):
        ledger['status']=status
        for row in stages:
            if row['status']=='PENDING':row['status']=blocked
        if arm['status']=='PENDING':arm['status']=blocked
        save();return ledger
    def can_launch():
        if time.process_time()<deadline-10:return True
        stop('PARENT_CPU_BUDGET_EXHAUSTED','BLOCKED_PARENT_CPU_BUDGET');return False
    def admit(directory,receipt,operation,position):
        if receipt.get('status')!='SUCCESS':return None
        try:return base.load_worker_result(directory,receipt,operation,CASE,None if operation=='prepare' else strategy)
        except (ValueError,KeyError,TypeError,OSError) as exc:
            ledger['artifact_admission_error']=dict(directory=str(directory),error=str(exc))
            stages[position].update(status='UNKNOWN',reason='artifact_admission_failed')
            arm['status']='UNKNOWN';stop('UNKNOWN','BLOCKED_ARTIFACT_ADMISSION');return None
    def command(operation):
        return [sys.executable,'-m','experiments.post_service_completion_gate_v1.run','--worker',operation,
            '--manifest',str(Path(manifest_path).resolve()),'--manifest-sha256',manifest_sha256,'--case',CASE]
    def launch(position,argv,**kwargs):
        try:
            receipt=run(argv,**kwargs)
            if type(receipt) is not dict:raise ValueError('Supervisor receipt is not a dictionary')
            if receipt.get('cleanup_verified') is not True:
                ledger['cleanup_error']=dict(stage=stages[position]['id'],reported_status=receipt.get('status'),cleanup_verified=False)
                stages[position]['status']='UNKNOWN';arm['status']='UNKNOWN'
                stop('UNKNOWN','BLOCKED_UNVERIFIED_CLEANUP');return None
            return receipt
        except Exception as exc:
            # The supervisor can fail during preflight, before its own receipt
            # exists. Never infer cleanup or silently drop the reserved slots.
            ledger['launch_error']=dict(stage=stages[position]['id'],type=type(exc).__name__,
                error=str(exc)[:4000],cleanup_verified=False)
            stages[position]['status']='UNKNOWN';arm['status']='UNKNOWN'
            stop('UNKNOWN','BLOCKED_LAUNCH_EXCEPTION');return None
    save()
    if not can_launch():return ledger
    directory=output/('prepare-'+CASE)
    receipt=launch(0,command('prepare'),output_dir=directory,limits=preparation,cwd=manifest['repo'])
    if receipt is None:return ledger
    ledger['common'][CASE]=receipt;stages[0]['status']=receipt['status'];save()
    admit(directory,receipt,'prepare',0)
    if ledger['status']=='UNKNOWN':return ledger
    if receipt['status']!='SUCCESS':
        return stop('UNKNOWN' if receipt['status']=='UNKNOWN' else 'FAILED_COMMON_PREPARATION','BLOCKED_COMMON_PREPARATION')
    if not can_launch():return ledger
    common=directory/'artifacts/prepared/common.json';common_sha=base.file_hash(common)
    argv=command('arm')+['--common',str(common.resolve()),'--common-sha256',common_sha,'--strategy',strategy]
    identity=dict(nonce=secrets.token_hex(16),manifest_sha256=manifest_sha256,
        source_closure_sha256=manifest['source']['closure_sha256'],common_sha256=common_sha,
        case_id=CASE,strategy=strategy,arm_index='0',experiment_schema=SCHEMA,
        completion_policy_sha256=base.digest(COMPLETION_POLICY))
    search_directory=output/'arm-00'
    receipt=launch(1,argv,output_dir=search_directory,limits=search,cwd=manifest['repo'],
        phase_budget=PhaseBudget(seconds=EXACT_PHASE_SECONDS,identity=identity))
    if receipt is None:return ledger
    arm.update(status=receipt['status'],receipt=receipt);stages[1]['status']=receipt['status'];save()
    admit(search_directory,receipt,'arm',1)
    if ledger['status']=='UNKNOWN':return ledger
    if receipt['status'] not in ('SUCCESS','TIMEOUT'):
        return stop('UNKNOWN' if receipt['status']=='UNKNOWN' else 'FAILED_SEARCH','BLOCKED_SEARCH_FAILED')
    if not can_launch():return ledger
    argv=command('verify')+['--common',str(common.resolve()),'--common-sha256',common_sha,
        '--search-directory',str(search_directory.resolve()),'--search-receipt-sha256',base.file_hash(search_directory/'receipt.json'),
        '--strategy',strategy]
    verify_directory=output/'verify-00'
    receipt=launch(2,argv,output_dir=verify_directory,limits=verification,cwd=manifest['repo'])
    if receipt is None:return ledger
    arm['verification']=receipt;stages[2]['status']=receipt['status'];save()
    full=admit(verify_directory,receipt,'verify',2)
    if ledger['status']=='UNKNOWN':return ledger
    arm['status']=full['status'] if full is not None else 'VERIFICATION_'+receipt['status']
    if receipt['status']!='SUCCESS':return stop('UNKNOWN' if receipt['status']=='UNKNOWN' else 'FAILED_VERIFICATION','BLOCKED_VERIFICATION_FAILED')
    if not can_launch():return ledger
    ledger['status']='COMPLETED';save();return ledger
