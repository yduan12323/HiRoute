"""Dedicated process owner from first source access through final queue receipt.

Real entry is unconditionally held; the CLI accepts only the built-in synthetic
fixture. An engineering fixture does not start or spend the actual M6 budget.
"""
import argparse
import os
from pathlib import Path

from .resources import Budget
from .physical_inputs import require_root_freeze
from .generation import _check_budget, _write, make_synthetic_fixture


def launch_real(*args, **kwargs):
    raise PermissionError('Strict M6 real launch remains permanently held')


def _launch_owned_recovery(output, *, interpreter, osmium, freeze, budget):
    # This must remain the first operation. No CLI/environment/data bypass exists.
    require_root_freeze()
    from . import physical
    from .generation import compiler_identity, _hash
    from .physical_inputs import sha
    from .physical_queue_adapter import PhysicalQueueAdapter
    from .queue import run_plan
    from .supervisor import run, Limits
    from experiments.shandong_preprocessing_v1.pipeline import run_preprocessing
    from experiments.shandong_preprocessing_v1.phases import gate, toolchain_identity, code_contract
    import json
    import sys
    gate(False)
    if type(freeze) is not dict or set(freeze)!={'source','compiler','toolchain','exposure_binding','protocol_sha256','recovery_admission','preprocessing_config'}:
        raise ValueError('Reviewed complete pre-source freeze required')
    repo=Path(__file__).resolve().parents[2]
    if freeze['source']!=physical.source_identity(repo) or freeze['compiler']!=compiler_identity():
        raise ValueError('Pre-source executable freeze differs')
    # The preprocessing interpreter/compiler/osmium versions and bytes must be
    # frozen before acquisition, not merely recorded after the download.
    if freeze['toolchain']!=toolchain_identity(interpreter,osmium,freeze['compiler']['path']):
        raise ValueError('Pre-source preprocessing toolchain differs')
    sha(freeze['protocol_sha256'])
    preprocessing_identity=dict(toolchain_identity=freeze['toolchain'],core_source_contract=code_contract(),
        config_sha256=freeze['preprocessing_config']['sha256'],
        implementation_sha256=_hash((repo/'experiments/shandong_preprocessing_v1/phases.py').read_bytes()))
    root=Path(output).resolve()
    os.sched_setaffinity(0,{0})
    if budget is None:raise ValueError('Original continuation owner budget required')
    root.mkdir(parents=True,exist_ok=False)
    receipt=dict(schema='hiroute.m6h.real_launch.v1',status='RUNNING',synthetic=False,
                 accounting_origin=dict(wall_start=budget.wall_start,cpu_start=budget.cpu_start),freeze=freeze)
    try:
        from experiments.shandong_preprocessing_v1.pipeline import validate_registry_once
        exposure=freeze['exposure_binding']
        receipt['registry_validation']=validate_registry_once(exposure['path'],
            byte_sha256=exposure['sha256'],canonical_sha256=freeze['recovery_admission']['registry_sha256'],
            max_bytes=256*2**20,output=root/'registry-validation',budget=budget,interpreter=interpreter,cpu=0,
            recovery_admission=freeze['recovery_admission'])
        artifacts,same=run_preprocessing(root/'preprocessing',budget=budget,interpreter=interpreter,osmium=osmium,fixture=False,cpu=0,compiler=freeze['compiler']['path'],expected_toolchain=freeze['toolchain'])
        if same is not budget:raise ValueError('Preprocessing replaced enclosing Budget')
        remaining_cpu,remaining_wall=budget.remaining()
        if remaining_cpu<7230 or remaining_wall<10830:raise RuntimeError('Global generation reservation failed')
        job=dict(artifacts=artifacts,exposure_binding=freeze['exposure_binding'],protocol_sha256=freeze['protocol_sha256'],
                 repo=str(repo),compiler=freeze['compiler'],source=freeze['source'],remaining_cpu=remaining_cpu,remaining_wall=remaining_wall,
                 preprocessing_identity=preprocessing_identity,recovery_admission=freeze['recovery_admission'])
        bound=_write(root/'generation-job.json',job)
        phase=run([sys.executable,'-m','experiments.m6h_manifest_v1.generation','--real-job',bound['path'],'--job-sha256',bound['sha256']],
            output_dir=root/'generation',cwd=repo,
            limits=Limits(wall_seconds=10800,cpu_seconds=7200,address_space_bytes=8*2**30,cpu=0,
                          file_output_bytes=8*2**30,stdout_bytes=2**20,stderr_bytes=2**20,max_output_entries=4096),
            tree_rss_stop_bytes=5*2**30,available_stop_bytes=2*2**30,prelaunch_available_bytes=7*2**30,
            tree_cpu_seconds=7200,global_cpu_remaining=remaining_cpu,global_wall_remaining=remaining_wall)
        if phase['status']!='SUCCESS' or phase.get('cleanup_verified') is not True:
            raise RuntimeError('Supervised input generation failed: '+str(phase.get('reason')))
        binding=phase['worker_receipt']['result']['generation'];raw=Path(binding['path']).read_bytes()
        if _hash(raw)!=binding['sha256']:raise ValueError('Generation receipt drift')
        generated=json.loads(raw)
        if generated['source']!=freeze['source'] or generated['protocol_sha256']!=freeze['protocol_sha256']:
            raise ValueError('Generation belongs to another freeze')
        _check_budget(budget)
        if generated['status']=='DATA_LIMITED':
            receipt.update(status='DATA_LIMITED',selected=generated['selection']['selected_group_count'],replacement=False)
            return receipt
        adapter=PhysicalQueueAdapter(generated['declaration'],generated['bindings'],selection_binding=generated['selection_binding'],
            recovery_admission=freeze['recovery_admission'])
        ledger=run_plan(generated['declaration'],root/'queue',adapter,budget=budget,cpu=0)
        receipt.update(status=ledger['status'],queue_ledger=str(root/'queue'/'ledger.json'))
        _check_budget(budget)
        return receipt
    except BaseException as exc:
        receipt.update(status='STOPPED',error=type(exc).__name__+': '+str(exc));raise
    finally:
        receipt['measured']=budget.measured()
        _write(root/'launch_receipt.json',receipt)

def _fixture_executor(**kwargs):
    # Still the reviewed subprocess supervisor, never a mock executor. The
    # dedicated fixture route permits CPU1 while production remains CPU0-only.
    from .supervisor import run
    return run(**kwargs)


def launch_synthetic(output):
    from .queue import run_plan
    from .synthetic_worker import SyntheticQueueAdapter
    root=Path(output).resolve()
    if 1 not in os.sched_getaffinity(0):raise RuntimeError('Fixture CPU1 unavailable')
    os.sched_setaffinity(0,{1})
    # Before fixture generation; the identical object is passed through to queue.
    budget=Budget()
    root.mkdir(parents=True,exist_ok=False)
    receipt=dict(schema='hiroute.m6h.synthetic_launch.v1',synthetic=True,status='RUNNING',
        accounting_origin=dict(wall_start=budget.wall_start,cpu_start=budget.cpu_start),actual_holdout_started=False)
    try:
        generated=make_synthetic_fixture(root/'frozen',budget=budget)
        if generated['status']!='FROZEN':raise ValueError('Built-in synthetic fixture unexpectedly data limited')
        _check_budget(budget)
        adapter=SyntheticQueueAdapter(generated['declaration'],generated['bindings'],selection_binding=generated['selection_binding'])
        _check_budget(budget)
        ledger=run_plan(generated['declaration'],root/'queue',adapter,budget=budget,executor=_fixture_executor,cpu=1)
        receipt.update(status=ledger['status'],queue_ledger=str(root/'queue'/'ledger.json'),
                       denominator=generated['declaration']['denominator'])
        _check_budget(budget)
        return receipt
    except BaseException as exc:
        receipt.update(status='STOPPED',error=type(exc).__name__+': '+str(exc))
        raise
    finally:
        receipt['measured']=budget.measured()
        _write(root/'launch_receipt.json',receipt)


def supervise_real_round(output, *, interpreter, osmium, freeze):
    """Outer waited receipt includes launcher's final write and process exit.

    Source authorization remains separately held. The outer monitor applies the
    approved cap conservatively to setup, all descendants and owned cleanup; it
    does not add nested receipts or reset the inner persistent round Budget.
    """
    raise PermissionError('Historical fresh-budget outer launcher remains held')
    from .supervisor import run, Limits
    from .generation import _hash
    import json
    import sys
    budget=Budget()
    root=Path(output).resolve();root.mkdir(parents=True,exist_ok=False)
    job=_write(root/'launcher-job.json',dict(interpreter=interpreter,osmium=osmium,freeze=freeze))
    cpu,wall=budget.remaining()
    if min(cpu,wall)<=30:raise RuntimeError('Outer cleanup/receipt reserve exhausted')
    receipt=run([sys.executable,'-m','experiments.m6h_manifest_v1.launcher','--real-launch-job',job['path'],
                 '--job-sha256',job['sha256']],output_dir=root/'round-process',cwd=Path(__file__).resolve().parents[2],
        limits=Limits(wall_seconds=min(172770,wall-30),cpu_seconds=min(143970,int(cpu)-30),
            address_space_bytes=8*2**30,cpu=0,file_output_bytes=8*2**30,
            stdout_bytes=2**20,stderr_bytes=2**20,max_output_entries=16384),
        tree_rss_stop_bytes=5*2**30,available_stop_bytes=2*2**30,prelaunch_available_bytes=7*2**30,
        tree_cpu_seconds=cpu-30,global_cpu_remaining=cpu-30,global_wall_remaining=wall-30)
    summary=dict(schema='hiroute.m6h.waited_round.v1',status=receipt['status'],cleanup_verified=receipt.get('cleanup_verified'),
        measured_through_launcher_exit=budget.measured(),outer_receipt_write_reserve_seconds=30,
        accounting='outer_self_plus_waited_descendants_once_no_nested_receipt_sum',
        sampling_boundary='excludes_this_outer_summary_write_after_waited_launcher_exit')
    if receipt['status']=='SUCCESS' and receipt.get('cleanup_verified') is True:
        bound=receipt['worker_receipt']['result']['launch_receipt'];raw=Path(bound['path']).read_bytes()
        if _hash(raw)!=bound['sha256']:raise ValueError('Final launcher receipt changed after exit')
        summary['launcher']=json.loads(raw)
    _check_budget(budget)
    _write(root/'waited_round_receipt.json',summary)
    return summary


def _real_launch_worker(job_path,job_sha256):
    require_root_freeze()
    from .generation import _hash
    import json
    raw=Path(job_path).read_bytes()
    if _hash(raw)!=job_sha256:raise ValueError('Outer launch job changed')
    job=json.loads(raw)
    if set(job)!={'interpreter','osmium','freeze'}:raise ValueError('Unexpected real launcher job')
    root=Path(os.environ['HIROUTE_OUTPUT_DIR'])/'round'
    result=launch_real(root,**job)
    receipt=root/'launch_receipt.json'
    _write(Path(os.environ['HIROUTE_WORKER_RECEIPT']),dict(status='COMPLETED',result=dict(
        status=result['status'],launch_receipt=dict(path=str(receipt),sha256=_hash(receipt.read_bytes())))))


def supervise_synthetic_round(output):
    """Exercise the final waited-receipt boundary with ONLY the fixed fixture."""
    from .supervisor import run, Limits
    from .generation import _hash
    import json
    import sys
    budget=Budget(cpu_seconds=3600,wall_seconds=7200)
    root=Path(output).resolve();root.mkdir(parents=True,exist_ok=False)
    cpu,wall=budget.remaining()
    receipt=run([sys.executable,'-m','experiments.m6h_manifest_v1.launcher','--sealed-synthetic-launch'],
        output_dir=root/'round-process',cwd=Path(__file__).resolve().parents[2],
        limits=Limits(wall_seconds=7170,cpu_seconds=3570,address_space_bytes=8*2**30,cpu=1,
            file_output_bytes=512*2**20,stdout_bytes=2**20,stderr_bytes=2**20,max_output_entries=16384),
        tree_rss_stop_bytes=5*2**30,available_stop_bytes=2*2**30,prelaunch_available_bytes=7*2**30,
        tree_cpu_seconds=cpu-30,global_cpu_remaining=cpu-30,global_wall_remaining=wall-30)
    summary=dict(schema='hiroute.m6h.waited_synthetic_round.v1',status=receipt['status'],synthetic=True,
        cleanup_verified=receipt.get('cleanup_verified'),measured_through_launcher_exit=budget.measured(),
        outer_receipt_write_reserve_seconds=30,sampling_boundary='excludes_this_outer_summary_write_after_waited_launcher_exit',
        accounting='outer_self_plus_waited_descendants_once_no_nested_receipt_sum')
    if receipt['status']=='SUCCESS' and receipt.get('cleanup_verified') is True:
        binding=receipt['worker_receipt']['result']['launch_receipt'];raw=Path(binding['path']).read_bytes()
        if _hash(raw)!=binding['sha256']:raise ValueError('Synthetic final receipt changed after exit')
        summary['launcher']=json.loads(raw)
    _check_budget(budget)
    _write(root/'waited_round_receipt.json',summary)
    return summary


def _synthetic_launch_worker():
    from .generation import _hash
    root=Path(os.environ['HIROUTE_OUTPUT_DIR'])/'round'
    result=launch_synthetic(root)
    receipt=root/'launch_receipt.json'
    _write(Path(os.environ['HIROUTE_WORKER_RECEIPT']),dict(status='COMPLETED',result=dict(
        status=result['status'],launch_receipt=dict(path=str(receipt),sha256=_hash(receipt.read_bytes())))))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--synthetic-fixture',action='store_true')
    parser.add_argument('--sealed-synthetic-launch',action='store_true')
    parser.add_argument('--output')
    parser.add_argument('--real-launch-job')
    parser.add_argument('--job-sha256')
    args=parser.parse_args()
    if args.sealed_synthetic_launch:
        if args.synthetic_fixture or any(x is not None for x in (args.real_launch_job,args.output,args.job_sha256)):
            raise ValueError('Sealed fixture does not accept source overrides')
        _synthetic_launch_worker()
    elif args.real_launch_job is not None:
        if args.synthetic_fixture or args.output is not None:raise ValueError('Mixed fixture/real launch modes')
        _real_launch_worker(args.real_launch_job,args.job_sha256)
    elif args.synthetic_fixture:
        if args.output is None or args.job_sha256 is not None:raise ValueError('Fixture output only')
        launch_synthetic(args.output)
    else:launch_real()


if __name__=='__main__':main()
