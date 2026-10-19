"""Held real preprocessing adapter; exact same bounded phases for tiny fixtures.

The caller must construct Budget before first source access and retain it for
selection, queue and terminal accounting. This module never creates a real Budget.
"""
from __future__ import annotations
import argparse
import json
import math
import os
from pathlib import Path
import sys
import shutil

HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(HERE),str(HERE.parents[1])]
from phases import gate,digest,verify_stage,write,code_contract,toolchain_identity

# Fixed planning limits; exceeding any stops preprocessing, never silently retries.
STAGES=(('source',1800,3600),('graph',7200,14400),('inventory',3600,7200),
        ('sites',3600,7200),('hierarchy',7200,14400))


def run_preprocessing(output, *, budget, interpreter, osmium, fixture=False, cpu=0, compiler=None, expected_toolchain=None):
    gate(fixture)  # Before source files, output creation or supervisor imports.
    if budget is None:raise ValueError('Enclosing pre-source Budget required')
    if not fixture and cpu!=0:raise ValueError('Real preprocessing requires CPU0')
    from experiments.m6h_manifest_v1.supervisor import run,Limits
    from experiments.m6h_manifest_v1.resources import Budget
    if not isinstance(budget,Budget):raise ValueError('Use the shared M6 Budget instance')
    output=Path(output).resolve()
    workspace=HERE.parents[2].resolve()
    if not output.is_relative_to(workspace):raise ValueError('Outputs and scratch must stay on owned workspace filesystem')
    output.mkdir(parents=True,exist_ok=False)
    prior={};records=[]
    compiler=compiler or shutil.which('g++')
    if not compiler:raise ValueError('Compiler unavailable')
    tools=toolchain_identity(interpreter,osmium,compiler)
    if expected_toolchain is not None and tools!=expected_toolchain:
        raise ValueError('Preprocessing toolchain differs from root freeze')
    config_path=HERE/'config.json'
    if not fixture:
        from experiments.m6h_manifest_v1.recovery_runtime import preprocessing_config_path
        config_path=preprocessing_config_path()
    receipt={'toolchain_identity':tools,'core_source_contract':code_contract(),'status':'RUNNING','synthetic':fixture,'budget_origin':{'wall_start':budget.wall_start,'cpu_start':budget.cpu_start},
             'stages':records,'config_sha256':digest(config_path),'driver_sha256':digest(Path(__file__)),
             'phase_source_sha256':digest(HERE/'phases.py'),'osmium_binary_sha256':digest(osmium)}
    # Terminal file is written once; stage supervisor receipts persist independently
    # on interruption. External caller's waited receipt includes this final write.
    def check_budget():
        if min(budget.remaining())<=0:raise RuntimeError('GLOBAL_BUDGET_EXHAUSTED')
    try:
        for name,max_cpu,max_wall in STAGES:
            rem_cpu,rem_wall=budget.remaining()
            if shutil.disk_usage(output).free < (64*2**20 if fixture else 10*2**30):
                raise RuntimeError('PRELAUNCH_DISK_RESERVE_FAILED:'+name)
            # Full capped-stage reservation plus cleanup/persistence allowance.
            need_cpu,need_wall=(60,120) if fixture else (max_cpu+30,max_wall+30)
            if rem_cpu<need_cpu or rem_wall<need_wall:
                raise RuntimeError('GLOBAL_BUDGET_RESERVATION_FAILED:'+name)
            stage_cpu,stage_wall=(30,60) if fixture else (max_cpu,max_wall)
            argv=[str(Path(interpreter).absolute()),'-u',str(HERE/'phases.py'),'--phase',name,
                  '--prior',json.dumps(prior,sort_keys=True),'--osmium',str(Path(osmium).resolve())]
            if fixture:argv.append('--fixture')
            env={'OSMIUM_POOL_THREADS':'1','LD_LIBRARY_PATH':str(Path(osmium).resolve().parent.parent/'lib'),
                 'TMPDIR':str(output/name/'artifacts'/'scratch'),'TMP':str(output/name/'artifacts'/'scratch'),
                 'TEMP':str(output/name/'artifacts'/'scratch'),'HIROUTE_TOOLCHAIN_IDENTITY':json.dumps(tools,sort_keys=True)}
            rem_cpu,rem_wall=budget.remaining()
            r=run(argv,output_dir=output/name,cwd=HERE.parents[1],extra_env=env,
                limits=Limits(wall_seconds=stage_wall,cpu_seconds=stage_cpu,address_space_bytes=8*2**30,cpu=cpu,
                              file_output_bytes=8*2**30,stdout_bytes=2**20,stderr_bytes=2**20,
                              cleanup_seconds=3,poll_seconds=.1,max_output_entries=1024),
                tree_rss_stop_bytes=(1 if fixture else 5)*2**30,available_stop_bytes=2*2**30,prelaunch_available_bytes=(3 if fixture else 7)*2**30,
                tree_cpu_seconds=stage_cpu,global_cpu_remaining=rem_cpu,global_wall_remaining=rem_wall,owned_temp=True)
            records.append({'phase':name,'status':r['status'],'cleanup_verified':r.get('cleanup_verified'),
                            'reason':r.get('reason'),'budget_measured':budget.measured()})
            if r.get('status')!='SUCCESS' or r.get('cleanup_verified') is not True:
                raise RuntimeError('PREPROCESSING_STOP:'+name+':'+str(r.get('reason')))
            result=(r.get('worker_receipt') or {}).get('result',{})
            identity={'path':str(output/name/'artifacts'),'manifest_sha256':result.get('artifact_manifest_sha256'),
                      'phase':name,'synthetic':fixture}
            artifacts=verify_stage(identity,name,checkpoint=check_budget)
            m=json.loads((artifacts/'artifact_manifest.json').read_text())
            if m['phase']!=name or m['synthetic'] is not fixture or m['implementation_sha256']!=receipt['phase_source_sha256']:
                raise ValueError('Stage receipt/source binding mismatch')
            if m['config_sha256']!=receipt['config_sha256']:raise ValueError('Configuration changed during stage')
            if m['toolchain_identity']!=tools:raise ValueError('Worker toolchain identity mismatch')
            if m['osmium_binary_sha256']!=receipt['osmium_binary_sha256']:raise ValueError('Osmium binary changed')
            if m['core_source_contract']!=receipt['core_source_contract']:raise ValueError('Core source/config contract changed')
            result=(r.get('worker_receipt') or {}).get('result',{})
            if result.get('artifact_manifest_sha256')!=digest(artifacts/'artifact_manifest.json') or result.get('phase')!=name:
                raise ValueError('Worker receipt artifact binding mismatch')
            prior[name]=identity
        check_budget()
        receipt['status']='PREPROCESSING_COMPLETE'
        receipt['artifacts']=prior
    except BaseException as exc:
        receipt['status']='STOPPED';receipt['error']=type(exc).__name__+': '+str(exc)
        raise
    finally:
        receipt['budget_measured']=budget.measured()
        write(output/'preprocessing_receipt.json',receipt)
    # Return the exact same Budget; caller must pass it to queue.run_plan.
    return prior,budget


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fixture',action='store_true');p.add_argument('--output',required=True)
    p.add_argument('--interpreter',required=True);p.add_argument('--osmium',required=True)
    p.add_argument('--supervisor-root',help='Source checkout providing shared M6 package (fixture integration only)')
    a=p.parse_args();gate(a.fixture)
    if not a.fixture:raise RuntimeError('Real orchestration must supply an enclosing shared Budget and approved source freeze')
    if a.supervisor_root:sys.path.insert(0,str(Path(a.supervisor_root).resolve()))
    from experiments.m6h_manifest_v1.resources import Budget
    budget=Budget(cpu_seconds=600,wall_seconds=1200)  # Before any generated fixture bytes.
    artifacts,same=run_preprocessing(a.output,budget=budget,interpreter=a.interpreter,osmium=a.osmium,fixture=True,cpu=min(os.sched_getaffinity(0)))
    if same is not budget:raise RuntimeError('Budget identity changed')
    print(json.dumps({'status':'SYNTHETIC_PREPROCESSING_COMPLETE','artifacts':artifacts,'measured':budget.measured()},indent=2))



def validate_registry_once(path, *, byte_sha256, canonical_sha256, max_bytes,
                           output, budget, interpreter, cpu, recovery_admission=None):
    """Release registry heap before graph build; same enclosing budget required.

    Hashes must come from the caller's independently recovered frozen identity.
    SUCCESS is schema/content validation, never evidence of historical coverage.
    """
    from experiments.m6h_manifest_v1.resources import Budget
    from experiments.m6h_manifest_v1.supervisor import run, Limits
    if not isinstance(budget,Budget):raise ValueError('Enclosing Budget required')
    if type(max_bytes) is not int or not 0<max_bytes<=256*2**20:
        raise ValueError('Registry byte bound required (maximum 256 MiB)')
    rem_cpu,rem_wall=budget.remaining()
    if rem_cpu<630 or rem_wall<630:raise RuntimeError('GLOBAL_BUDGET_RESERVATION_FAILED:registry')
    argv=[str(Path(interpreter).absolute()),'-u',str(HERE/'registry_worker.py'),
          '--path',str(Path(path).absolute()),'--sha256',byte_sha256,
          '--canonical-sha256',canonical_sha256,'--max-bytes',str(max_bytes)]
    if recovery_admission is not None:
        from experiments.m6h_manifest_v1.recovery_runtime import require_active
        if recovery_admission!=require_active()['recovery_admission']:
            raise ValueError('Registry admission differs from root release')
        argv+=['--recovery-admission',json.dumps(recovery_admission,sort_keys=True)]
    result=run(argv,output_dir=output,cwd=HERE.parents[1],owned_temp=True,
               limits=Limits(wall_seconds=600,cpu_seconds=600,address_space_bytes=8*2**30,cpu=cpu),
               tree_cpu_seconds=600,global_cpu_remaining=rem_cpu,global_wall_remaining=rem_wall)
    if result.get('status')!='SUCCESS' or result.get('cleanup_verified') is not True:
        raise RuntimeError('REGISTRY_VALIDATION_STOP:'+str(result.get('reason')))
    return result['worker_receipt']['result']

if __name__=='__main__':main()
