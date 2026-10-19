"""Guarded disclosed validation owner; fixed deadline and cumulative CPU lineage.

The outer waited owner is authoritative. The launcher child receives a cumulative
snapshot, never a fresh full allowance. Its subordinate ledger is not summed.
"""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import sys
from . import recovery_runtime as runtime
from .recovery_protocol import make_continuation_budget, DEADLINE, ACTIVE_SINCE, CARRIED_CPU
from .resources import ContinuationBudget, conservative_transition_debit
from .generation import _write, _hash, _check_budget


def now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')


def supervise(output, *, configuration):
    # Source guard precedes config/input access. Entire validation interval is
    # already inside the nine-CPU conservative envelope before metering begins.
    freeze=runtime.activate(configuration)
    budget=make_continuation_budget(transition_utc=freeze['transition_utc'])
    from .physical import source_identity
    from .generation import compiler_identity
    from .supervisor import run,Limits
    if source_identity(freeze['repo'])!=freeze['source'] or compiler_identity()!=freeze['compiler']:
        raise ValueError('Recovery executable freeze differs')
    root=Path(output).resolve()
    repo=Path(freeze['repo']).resolve()
    if root.is_relative_to(repo):raise ValueError('Actual artifacts must remain outside Git checkout')
    root.mkdir(parents=True,exist_ok=False)
    cpu,wall=budget.remaining()
    if min(cpu,wall)<=30:raise RuntimeError('Continuation cleanup reserve exhausted')
    transfer_stamp=now()
    transfer_floor=conservative_transition_debit(prior_debit=CARRIED_CPU,active_since_utc=ACTIVE_SINCE,
        transition_utc=transfer_stamp,cpu_capacity=9)
    transfer=dict(carried_cpu_seconds=max(budget.measured()['cpu_seconds'],transfer_floor),transition_utc=transfer_stamp,
                  deadline_utc=DEADLINE,transition_cpu_capacity=9)
    job=_write(root/'job.json',dict(configuration=configuration,transfer=transfer))
    receipt=run([sys.executable,'-m','experiments.m6h_manifest_v1.recovery_runner',
        '--worker-job',job['path'],'--sha256',job['sha256']],output_dir=root/'owner',cwd=repo,
        extra_env={'HIROUTE_RECOVERY_OWNER_JOB':json.dumps(job,sort_keys=True)},
        limits=Limits(wall_seconds=wall-30,cpu_seconds=max(1,int(cpu)-30),
            address_space_bytes=8*2**30,cpu=0,file_output_bytes=8*2**30,
            stdout_bytes=2**20,stderr_bytes=2**20,max_output_entries=32768),
        tree_rss_stop_bytes=5*2**30,available_stop_bytes=2*2**30,prelaunch_available_bytes=7*2**30,
        tree_cpu_seconds=cpu-30,global_cpu_remaining=cpu-30,global_wall_remaining=wall-30)
    summary=dict(schema='hiroute.m6h.disclosed_waited_round.v1',status=receipt['status'],
        cleanup_verified=receipt.get('cleanup_verified'),configuration=configuration,
        protocol=freeze['protocol'],cumulative_measured_plus_conservative_carry=budget.measured(),
        accounting='authoritative_outer_self_plus_waited_children_once_no_nested_sum',
        sampling_boundary='through_waited_launcher_exit_excludes_this_final_summary_write',
        terminal_write_reserve_seconds=30)
    if receipt['status']=='SUCCESS' and receipt.get('cleanup_verified') is True:
        b=receipt['worker_receipt']['result']['launch_receipt']
        raw=Path(b['path']).read_bytes()
        if _hash(raw)!=b['sha256']:raise ValueError('Waited launch receipt changed')
        summary['launcher']=json.loads(raw)
    if min(budget.remaining())<=0:
        summary['status']='GLOBAL_BUDGET_EXHAUSTED'
    _write(root/'waited_round_receipt.json',summary)
    return summary


def worker(path,sha256):
    runtime.require_active()
    expected=json.loads(os.environ.get('HIROUTE_RECOVERY_OWNER_JOB','null'))
    if expected!={'path':path,'sha256':sha256}:raise PermissionError('Worker requires enclosing owner job binding')
    raw=Path(path).read_bytes()
    if _hash(raw)!=sha256:raise ValueError('Continuation worker job changed')
    job=json.loads(raw)
    if set(job)!={'configuration','transfer'}:raise ValueError('Unexpected continuation job')
    freeze=runtime.activate(job['configuration'])
    transfer=job['transfer']
    if transfer['deadline_utc']!=DEADLINE or transfer['transition_cpu_capacity']!=9:
        raise ValueError('Continuation ownership transfer expands deadline/capacity')
    floor=conservative_transition_debit(prior_debit=CARRIED_CPU,active_since_utc=ACTIVE_SINCE,
        transition_utc=transfer['transition_utc'],cpu_capacity=9)
    if transfer['carried_cpu_seconds']<floor:raise ValueError('Continuation transfer resets cumulative debit')
    budget=ContinuationBudget(**transfer)
    _check_budget(budget)
    from .launcher import _launch_owned_recovery
    from .contract import digest
    runtime_freeze={k:freeze[k] for k in ('source','compiler','toolchain','exposure_binding','recovery_admission','preprocessing_config')}
    runtime_freeze['protocol_sha256']=digest(freeze['protocol'])
    root=Path(os.environ['HIROUTE_OUTPUT_DIR'])/'round'
    result=_launch_owned_recovery(root,interpreter=freeze['toolchain']['interpreter']['requested_executable'],
        osmium=freeze['toolchain']['osmium']['path'],freeze=runtime_freeze,budget=budget)
    receipt=root/'launch_receipt.json'
    _write(Path(os.environ['HIROUTE_WORKER_RECEIPT']),dict(status='COMPLETED',result=dict(
        status=result['status'],launch_receipt=dict(path=str(receipt),sha256=_hash(receipt.read_bytes())))))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker-job');parser.add_argument('--sha256');parser.add_argument('--configuration');parser.add_argument('--output')
    a=parser.parse_args()
    if a.worker_job:
        if a.configuration or a.output:raise ValueError('Mixed continuation entry modes')
        worker(a.worker_job,a.sha256)
    else:
        if not a.configuration or not a.sha256 or not a.output:raise ValueError('Configuration binding and output required')
        supervise(a.output,configuration=dict(path=a.configuration,sha256=a.sha256))

if __name__=='__main__':main()
