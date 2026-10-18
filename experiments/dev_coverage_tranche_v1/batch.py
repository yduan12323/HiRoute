"""Seven declared independent five-slot pairs, serial and without retries."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time

from experiments.mechanism_recovery_v1 import run as base
from experiments.mechanism_recovery_v1.supervisor import run,Limits,THREAD_ENV
from experiments.pending_window_completion_v1.lifecycle import atomic
from . import run as gate
from .bindings import QUEUE,PLAN_SHA256,PLAN,LINKED_GATE

SCHEMA='hiroute.dev_coverage_tranche_batch.v1'
PAIR_WALL_SECONDS=4200
PAIR_CONSERVATIVE_CHARGE_SECONDS=4320
BATCH_CPU_SECONDS=1440
AGGREGATE_CHARGE_CEILING_SECONDS=20*3600
DENOMINATOR=dict(domains=7,method_rows=14,common_preparations=7,searches=14,replays=14,operational_slots=35)


def prospective():
    return dict(schema=SCHEMA,launchable=False,status='prospective_held_for_tranche_A_terminal_and_B_review',
        selection_sha256=PLAN_SHA256,prospective_full_selection=PLAN,tranche='B',tranche_A_launchable=False,linked_existing_gate=LINKED_GATE,
        queue=[dict(index=i,case_id=c,candidate_count=n,methods=['flat','hier'],manifest=None,sha256=None) for i,(c,n) in enumerate(QUEUE)],
        denominator=DENOMINATOR,max_heavy_workers=1,numeric_threads=1,cpu=0,automatic_retry=False,
        pair_wall_seconds=PAIR_WALL_SECONDS,pair_conservative_CPU_charge_seconds=PAIR_CONSERVATIVE_CHARGE_SECONDS,
        queue_supervisor_cpu_soft_seconds=BATCH_CPU_SECONDS,queue_required_CPU_hard_floor_seconds=1501,
        outer_sampler_poll_seconds=0.2,parent_CPU_soft_seconds_per_pair=180,
        aggregate_conservative_CPU_charge_ceiling_seconds=AGGREGATE_CHARGE_CEILING_SECONDS,
        full_queue_conservative_CPU_charge_reservation_seconds=len(QUEUE)*PAIR_CONSERVATIVE_CHARGE_SECONDS+BATCH_CPU_SECONDS,
        aggregate_charge_method='precharge_fixed_pair_wall_reservation_plus_queue_parent_reservation_on_single_CPU0_all_descendants_no_nested_timer_sum',
        aggregate_charge_is_unique_measured_CPU=False,historical_48_CPU_hour_accounting_reconciled=False,
        separate_tranche_A_conservative_reservation_seconds=36000,
        combined_A_B_conservative_reservation_seconds=36000+len(QUEUE)*PAIR_CONSERVATIVE_CHARGE_SECONDS+BATCH_CPU_SECONDS,
        integrity_unknown_cleanup_resource_unsafe_halts_new_starts=True,
        clean_typed_no_seed_preserves_failed_preparation_and_four_blocked_descendants_may_continue=True,
        root_tranche_A_terminal_and_independent_B_review_required=True,repo=None,source=None,compiler=None,input_directory=None)


def _manifest(path,sha256):
    raw=Path(path).read_bytes()
    if len(raw)>8*1024**2 or hashlib.sha256(raw).hexdigest()!=sha256:raise ValueError('Batch manifest bytes differ')
    manifest=json.loads(raw);expected=prospective()
    runtime={'launchable','status','queue','repo','source','compiler','input_directory'}
    if (set(manifest)!=set(expected) or manifest['launchable'] is not True or manifest['status']!='frozen_tranche_B_not_launched' or
        any(base.canonical(manifest[k])!=base.canonical(v) for k,v in expected.items() if k not in runtime)):
        raise ValueError('Prespecified fixed Tranche B batch policy differs')
    gate.require_launch_review()
    if type(manifest['queue']) is not list or len(manifest['queue'])!=7:raise ValueError('Exactly seven pair descriptors required')
    for expected_row,row in zip(expected['queue'],manifest['queue']):
        if set(row)!=set(expected_row) or any(row[k]!=v for k,v in expected_row.items() if k not in ('manifest','sha256')):
            raise ValueError('Prespecified queue order or case/N differs')
        if type(row['manifest']) is not str or not Path(row['manifest']).is_absolute() or type(row['sha256']) is not str:
            raise ValueError('Closed pair manifest reference required')
        pair=gate._manifest(row['manifest'],row['sha256'])
        if (pair['case_id']!=row['case_id'] or pair['candidate_count']!=row['candidate_count'] or
            any(pair[k]!=manifest[k] for k in ('repo','source','compiler','input_directory'))):
            raise ValueError('Pair and batch committed closure or exact case/N differ')
    return manifest


def freeze(output,input_directory):
    gate.require_launch_review()
    root=Path.cwd().resolve();compiler=Path(gate.shutil.which('g++')).resolve()
    shared=dict(repo=str(root),input_directory=str(Path(input_directory).resolve()),
        compiler=dict(path=str(compiler),sha256=base.file_hash(compiler),version=subprocess.check_output([str(compiler),'--version'],text=True),flags=['-O3','-std=c++17']),
        source=gate.source_identity(root))
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    manifest=prospective();manifest.update(shared,launchable=True,status='frozen_tranche_B_not_launched')
    for row in manifest['queue']:
        pair=gate.prospective(row['case_id'],row['candidate_count']);pair.update(shared,launchable=True,status='frozen_dev_coverage_pair_not_launched')
        path=output/f"pair-{row['index']:02d}.json";path.write_bytes(base.canonical(pair))
        row.update(manifest=str(path),sha256=base.file_hash(path))
    path=output/'batch.json';path.write_bytes(base.canonical(manifest));sha=base.file_hash(path);_manifest(path,sha)
    return dict(manifest=str(path),sha256=sha)


def batch_ledger(sha256):
    rows=[]
    for i,(case,n) in enumerate(QUEUE):
        stages=[dict(operation='prepare',strategy=None,status='PLANNED_NOT_LAUNCHED')]
        stages.extend(dict(operation=op,strategy=arm,status='PLANNED_NOT_LAUNCHED') for arm in ('flat','hier') for op in ('search','verify'))
        rows.append(dict(index=i,case_id=case,candidate_count=n,status='PLANNED_NOT_LAUNCHED',stages=stages))
    return dict(schema=SCHEMA,manifest_sha256=sha256,selection_sha256=PLAN_SHA256,denominator=DENOMINATOR,
        status='RUNNING',pairs=rows,conservative_CPU_charge_seconds=BATCH_CPU_SECONDS,
        charge_is_unique_measured_CPU=False,tranche='B',linked_existing_gate=LINKED_GATE)


def pair_envelope(path):
    raw=Path(path).read_bytes()
    if not 0<len(raw)<=1024**2:raise ValueError('Pair ledger exceeds bounded result contract')
    return dict(schema=SCHEMA,path='pair/ledger.json',size=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def load_pair(directory,receipt):
    if receipt.get('status')!='SUCCESS' or receipt.get('cleanup_verified') is not True:raise ValueError('Pair supervisor outcome or cleanup unverified')
    b=receipt['worker_receipt']['result'];root=Path(directory)/'artifacts';path=root/'pair/ledger.json'
    if (type(b) is not dict or set(b)!={'schema','path','size','sha256'} or b['schema']!=SCHEMA or b['path']!='pair/ledger.json' or
        type(b['size']) is not int or not 0<b['size']<=1024**2 or root.is_symlink() or path.parent.is_symlink() or path.is_symlink() or path.stat().st_size!=b['size']):
        raise ValueError('Pair ledger artifact reference differs')
    raw=path.read_bytes()
    if len(raw)!=b['size'] or hashlib.sha256(raw).hexdigest()!=b['sha256']:raise ValueError('Pair ledger digest differs')
    return json.loads(raw)


def admit_pair_ledger(ledger,descriptor,manifest,directory):
    """Independently repeat pair result admission before another domain may start."""
    pair=gate._manifest(descriptor['manifest'],descriptor['sha256'])
    if (ledger.get('case')!=descriptor['case_id'] or ledger.get('candidate_count')!=descriptor['candidate_count'] or
        ledger.get('manifest_sha256')!=descriptor['sha256']):raise ValueError('Pair result case/N differs')
    if ledger['status']=='FAILED_PREPARATION_NO_SEED':outcome=gate.admit_no_seed_pair(ledger,pair,descriptor['sha256'],directory)
    else:outcome=gate.admit_pair(ledger,pair,descriptor['sha256'],directory)
    safe=bool(outcome.get('clean_expected_no_seed') or outcome['operational_admission'])
    if ledger.get('safe_to_continue') is not safe:raise ValueError('Pair continuation claim differs from authenticated evidence')
    return outcome,safe


def run_batch(path,sha256,output,cpu):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    ledger=batch_ledger(sha256);started=time.process_time()
    def save():ledger['queue_parent_CPU_seconds']=time.process_time();ledger['queue_parent_CPU_scope']='absolute_process_CPU_including_startup_and_preflight';atomic(output/'ledger.json',ledger)
    def stop(status,error=None):
        ledger['status']=status
        if error is not None:ledger['error']=dict(type=type(error).__name__,error=str(error)[:4000])
        save();return ledger
    save()
    try:
        if type(cpu) is not int or cpu!=0 or cpu not in os.sched_getaffinity(0):raise ValueError('Fixed CPU0 required')
        import threading
        if threading.active_count()!=1 or threading.current_thread() is not threading.main_thread():raise ValueError('Dedicated single-threaded queue required')
        os.sched_setaffinity(0,{cpu})
        hard=resource.getrlimit(resource.RLIMIT_CPU)[1]
        if hard!=resource.RLIM_INFINITY and hard<1501:raise ValueError('Queue inherited CPU hard limit cannot admit worker1501 and absolute queue1440')
        deadline=BATCH_CPU_SECONDS
        resource.setrlimit(resource.RLIMIT_CPU,(BATCH_CPU_SECONDS,hard))
        def expire(signum,frame):raise RuntimeError('Queue parent CPU budget exhausted')
        signal.signal(signal.SIGXCPU,expire)
        manifest=_manifest(path,sha256)
        for descriptor,row in zip(manifest['queue'],ledger['pairs']):
            if time.process_time()>=deadline-10:return stop('BLOCKED_QUEUE_PARENT_CPU_BUDGET')
            charge=ledger['conservative_CPU_charge_seconds']+PAIR_CONSERVATIVE_CHARGE_SECONDS
            if charge>AGGREGATE_CHARGE_CEILING_SECONDS:return stop('BLOCKED_AGGREGATE_CONSERVATIVE_CPU_CHARGE')
            ledger['conservative_CPU_charge_seconds']=charge;row['status']='STARTED';save()
            argv=[sys.executable,'-m','experiments.dev_coverage_tranche_v1.batch','--pair-driver',
                '--manifest',descriptor['manifest'],'--manifest-sha256',descriptor['sha256'],'--cpu','0']
            directory=output/f"domain-{descriptor['index']:02d}"
            receipt=run(argv,output_dir=directory,cwd=manifest['repo'],limits=Limits(
                wall_seconds=PAIR_WALL_SECONDS,cpu_seconds=1500,address_space_bytes=8*1024**3,cpu=0,
                file_output_bytes=96*1024**2,max_output_entries=6144,poll_seconds=0.2),extra_env=THREAD_ENV)
            row['driver_receipt']=receipt;save()
            pair_ledger=load_pair(directory,receipt)
            outcome,safe=admit_pair_ledger(pair_ledger,descriptor,manifest,directory/'artifacts/pair')
            row.update(status=outcome['status'],stages=pair_ledger['stages'],arms=pair_ledger['arms'],pair_outcome=outcome,
                pair_ledger_sha256=base.file_hash(directory/'artifacts/pair/ledger.json'))
            if type(receipt.get('wall_seconds')) not in (int,float) or not math.isfinite(receipt['wall_seconds']) or receipt['wall_seconds']>PAIR_CONSERVATIVE_CHARGE_SECONDS:
                return stop('BLOCKED_CONSERVATIVE_CPU_CHARGE_OVERRUN')
            if not safe:return stop('BLOCKED_PAIR_INTEGRITY_CLEANUP_RESOURCE_OR_CORRECTNESS')
            save()
        return stop('COMPLETED_DECLARED_TRANCHE_B')
    except Exception as exc:
        for row in ledger['pairs']:
            if row['status']=='STARTED':
                row['status']='UNKNOWN_NOT_AUTHENTICATED'
                for stage in row['stages']:stage['status']='UNKNOWN_NOT_AUTHENTICATED'
        return stop('UNKNOWN_HALTED_NO_NEW_STARTS',exc)


def main():
    parser=argparse.ArgumentParser(description=__doc__);m=parser.add_mutually_exclusive_group(required=True)
    m.add_argument('--plan',action='store_true');m.add_argument('--freeze',action='store_true');m.add_argument('--batch',action='store_true');m.add_argument('--pair-driver',action='store_true')
    for name in ('manifest','manifest-sha256','output','input-directory'):parser.add_argument('--'+name)
    parser.add_argument('--cpu',type=int);args=parser.parse_args()
    if args.plan:print(json.dumps(prospective(),indent=2,sort_keys=True));return 0
    if args.freeze:
        if not args.output or not args.input_directory:parser.error('Freeze requires output and input directory')
        print(json.dumps(freeze(args.output,args.input_directory)));return 0
    if args.pair_driver:
        if args.cpu!=0:parser.error('Pair driver requires CPU0')
        directory=Path(os.environ['HIROUTE_OUTPUT_DIR'])/'pair'
        gate.run_gate(args.manifest,args.manifest_sha256,directory,args.cpu)
        gate._manifest(args.manifest,args.manifest_sha256)
        Path(os.environ['HIROUTE_WORKER_RECEIPT']).write_bytes(base.canonical(dict(status='COMPLETED',result=pair_envelope(directory/'ledger.json'))))
        return 0
    if not args.output or args.cpu!=0:parser.error('Batch requires output and CPU0')
    ledger=run_batch(args.manifest,args.manifest_sha256,args.output,args.cpu)
    return 0 if ledger['status']=='COMPLETED_DECLARED_TRANCHE_B' else 1


if __name__=='__main__':sys.exit(main())
