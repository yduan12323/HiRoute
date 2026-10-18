"""Separate240-second OD10 N32 projection OFF/ON authenticated-completion gate."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from experiments.mechanism_recovery_v1 import run as base
from experiments.scalability_development_v1 import run as development
from experiments.projection_support_gate_v1 import run as projection
from timecut5.exact_progress import operation, event
from experiments.scalability_profile_v1 import run as profile
from experiments.remaining_charge_gate_v1 import run as remaining
from experiments.dyadic_alt_gate_v1 import run as dyadic
from dataclasses import asdict
from fractions import Fraction as F

SCHEMA = 'hiroute.projection_completion_gate.v1'
EXACT_PHASE_SECONDS = 240
ORIGINAL_HMAX = projection.ORIGINAL_HMAX
CASE = projection.CASE
ARMS = projection.ARMS
CONFIGS = projection.CONFIGS
SUPPORT_POLICY = projection.SUPPORT_POLICY
TIME_POLICIES = projection.TIME_POLICIES
BOUND_POLICY = projection.BOUND_POLICY
OBSERVER = projection.OBSERVER
COMPLETION_POLICY = dict(schema=SCHEMA,exact_phase_seconds=240,
    inner_experiment_schema=projection.SCHEMA,matched_projection_control=True,
    envelope_sweep=False,includes_postsolver_finalization=True,
    completion_requires_authenticated_result_and_fresh_replay=True,
    supersedes_historical_timeout=False,automatic_repeat=False)
POLICY = dict(projection.POLICY,completion_policy=COMPLETION_POLICY)
LIMITS = dict(base.LIMITS,search_seconds=EXACT_PHASE_SECONDS)
RESERVE = dict(development.RESERVE,exact_search_seconds_per_arm=240,total_exact_search_seconds=480)


def source_identity(repo):
    identity=projection.source_identity(repo)
    closure=dict(identity['closure'])
    for path in sorted((Path(repo)/'experiments/projection_completion_gate_v1').rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix not in ('.pyc','.pyo'):
            closure[str(path.relative_to(repo))]=base.file_hash(path)
    return dict(identity,closure=closure,closure_sha256=base.digest(closure))


def prospective():
    return dict(schema=SCHEMA,launchable=False,status='prospective_pending_source_review',
        candidate_count=32,policy=POLICY,arms=CONFIGS,order=list(ARMS),observer=OBSERVER,
        denominator=development.DENOMINATOR,reserve_plan=RESERVE,
        limits=LIMITS,cache_policy=base.CACHE_POLICY,inputs=development.prospective()['inputs'],
        repo=None,input_directory=None,compiler=None,source=None,auto_next_gate=False,
        holdout=False,historical_pooling=False,require_positive_result=False)


def _manifest(path, expected_sha256):
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected_sha256:raise ValueError('Profile manifest digest differs')
    manifest=json.loads(raw);expected=prospective()
    if manifest.get('schema')!=SCHEMA or manifest.get('launchable') is not True:
        raise ValueError('Prospective profile plan is not launchable')
    runtime={'launchable','status','repo','input_directory','compiler','source'}
    if set(manifest)!=set(expected) or any(base.canonical(manifest[k])!=base.canonical(v) for k,v in expected.items() if k not in runtime):
        raise ValueError('Frozen profile policy differs')
    compiler=manifest['compiler']
    if (set(compiler)!={'path','sha256','version','flags'} or base.file_hash(compiler['path'])!=compiler['sha256'] or
        subprocess.check_output([compiler['path'],'--version'],text=True)!=compiler['version'] or
        compiler['flags']!=['-O3','-std=c++17']):raise ValueError('Pinned compiler differs')
    if manifest['source']!=source_identity(manifest['repo']):raise ValueError('Profile executable source closure differs')
    for name,binding in manifest['inputs'].items():
        path=Path(manifest['input_directory'])/name
        if path.stat().st_size!=binding['size'] or base.file_hash(path)!=binding['sha256']:
            raise ValueError('Profile input differs: '+name)
    return manifest


class CompletionDomain(projection.ProjectionSupportDomain):
    """Keep inherited arm/config fixed; add a separate completion binding."""
    def durable_binding(self,seed):
        binding=super().durable_binding(seed)
        binding['domain_sha256']=base.digest([binding['domain_sha256'],SCHEMA,self.arm,COMPLETION_POLICY,self.manifest_binding])
        binding['source_sha256']=dict(binding['source_sha256'],completion_policy=base.digest([SCHEMA,self.arm,COMPLETION_POLICY,self.manifest_binding]))
        return binding

    def make_bound(self,context,strategy):
        bound=super().make_bound(context,strategy)
        receipt=dict(schema=SCHEMA,arm=self.arm,completion_policy=COMPLETION_POLICY,
            manifest_binding=self.manifest_binding,inner_experiment_schema=projection.SCHEMA,
            inner_configuration=self.config,inner_admission_sha256=base.file_hash(self._output/'remaining_charge_admission.json'))
        (self._output/'completion_admission.json').write_bytes(base.canonical(receipt))
        return bound

    def run_arm(self,strategy,seed,output,**kwargs):
        result=super().run_arm(strategy,seed,output,**kwargs)
        result.update(schema=SCHEMA,inner_experiment_schema=projection.SCHEMA,
            completion_policy=COMPLETION_POLICY,completion_admission_sha256=base.file_hash(Path(output)/'completion_admission.json'))
        (Path(output)/'result.json').write_bytes(base.canonical(result))
        return result


def domain_factory(manifest,query,sites,cache,*,arm):
    if len(sites)!=32:raise ValueError('Profile requires original N32')
    directory,bindings=manifest['input_directory'],manifest['inputs']
    tree=base.original_tree((Path(directory)/'hierarchy.json').read_bytes(),bindings['hierarchy.json']['sha256'],list(sites))
    return CompletionDomain(arm=arm,required_hmax=ORIGINAL_HMAX,manifest_binding=base.digest(manifest),graph_factory=lambda:base.load_graph(directory,bindings),
        query=query,sites=sites,tree=tree,source_hashes=dict({n:bindings[n+'.parquet']['sha256'] for n in ('nodes','edges')},
            source_closure=manifest['source']['closure_sha256'],**{'input:'+n:b['sha256'] for n,b in bindings.items()}),
        cache=cache,compiler=manifest['compiler']['path'],cache_policy=manifest['cache_policy'])


def progress_binding(manifest,arm,common):
    inner,sources=projection.progress_binding(manifest,arm,common)
    manifest_binding=base.digest(manifest)
    return (base.digest([inner,SCHEMA,arm,COMPLETION_POLICY,manifest_binding]),
        dict(sources,completion_policy=base.digest([SCHEMA,arm,COMPLETION_POLICY,manifest_binding])))


validate_activation_receipt = projection.validate_activation_receipt
validate_support_statistics = projection.validate_support_statistics
validate_common_domain = projection.validate_common_domain


def require_exact_phase(search):
    phase=search.get('phase_budget',{})
    if (search.get('status') not in ('SUCCESS','TIMEOUT') or search.get('phase_entered_monotonic') is None or
        type(phase.get('seconds')) is not int or phase['seconds']!=EXACT_PHASE_SECONDS or
        search['status']=='TIMEOUT' and search.get('reason')!='phase_timeout'):
        raise ValueError('Search did not complete or exhaust its declared240-second exact phase')


def validate_completion_admission(receipt,manifest,arm,inner_sha):
    expected=dict(schema=SCHEMA,arm=arm,completion_policy=COMPLETION_POLICY,
        manifest_binding=base.digest(manifest),inner_experiment_schema=projection.SCHEMA,
        inner_configuration=CONFIGS[arm],inner_admission_sha256=inner_sha)
    if base.canonical(receipt)!=base.canonical(expected):raise ValueError('Outer completion admission differs')


def read_progress(path,manifest,arm,common,*,search_status,completed_result=None):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size>OBSERVER['max_snapshot_bytes']:
        raise ValueError('Missing or unbounded profile snapshot')
    raw=path.read_bytes();value=json.loads(raw)
    expected_domain,expected_sources=progress_binding(manifest,arm,common)
    if (value.get('domain_sha256')!=expected_domain or value.get('source_sha256')!=expected_sources or
        value.get('profile_schema')!=projection.SCHEMA or value.get('arm')!=arm or base.canonical(value.get('configuration'))!=base.canonical(CONFIGS[arm]) or
        value.get('manifest_binding')!=base.digest(manifest) or value.get('candidate_count')!=32 or
        value.get('query_sha256')!=base.digest(common['query']) or value.get('Hmax')!=common['seed']['max_depth'] or
        value.get('status') not in ('running','returned') or value.get('io_error') is not None or value.get('heartbeat_error') is not None):
        raise ValueError('Profile snapshot binding or observer health differs')
    admission_path=path.parent.parent/'remaining_charge_admission.json'
    if admission_path.is_symlink() or not admission_path.is_file() or admission_path.stat().st_size>OBSERVER['max_snapshot_bytes']:
        raise ValueError('Missing or unbounded remaining-charge admission')
    admission_raw=admission_path.read_bytes();admission=json.loads(admission_raw)
    admission_sha=hashlib.sha256(admission_raw).hexdigest()
    if (value.get('remaining_charge_admission_sha256')!=admission_sha or admission.get('schema')!=projection.SCHEMA or
        admission.get('arm')!=arm or admission.get('portable_bound_policy')!=BOUND_POLICY or
        admission.get('original_Hmax')!=common['seed']['max_depth'] or admission.get('context_receipt_portable') is not False):
        raise ValueError('Remaining-charge admission binding differs')
    completion_path=path.parent.parent/'completion_admission.json'
    if completion_path.is_symlink() or not completion_path.is_file() or completion_path.stat().st_size>OBSERVER['max_snapshot_bytes']:
        raise ValueError('Missing or unbounded completion admission')
    completion_raw=completion_path.read_bytes();completion_sha=hashlib.sha256(completion_raw).hexdigest()
    validate_completion_admission(json.loads(completion_raw),manifest,arm,admission_sha)
    validate_activation_receipt(admission,value,arm,common)
    validate_support_statistics(value.get('projection_support_statistics'),arm,completed=False)
    raw_sha=hashlib.sha256(raw).hexdigest()
    if search_status not in ('SUCCESS','TIMEOUT'):raise ValueError('Profile search outcome not admitted')
    final_health=False
    if search_status=='SUCCESS':
        if not isinstance(completed_result,dict):raise ValueError('Authenticated normal arm result required')
        if (completed_result.get('schema')!=SCHEMA or completed_result.get('inner_experiment_schema')!=projection.SCHEMA or
            base.canonical(completed_result.get('completion_policy'))!=base.canonical(COMPLETION_POLICY) or
            completed_result.get('completion_admission_sha256')!=completion_sha):raise ValueError('Authenticated completion result outer binding differs')
        final=completed_result.get('observer',{})
        if (completed_result.get('remaining_charge_admission_sha256')!=admission_sha or
            completed_result.get('remaining_charge_activation_wall_ns')!=admission['activation_wall_ns'] or completed_result.get('progress_sha256')!=raw_sha or completed_result.get('strategy')!=arm or
            base.canonical(completed_result.get('time_policy'))!=base.canonical(TIME_POLICIES[arm]) or base.canonical(completed_result.get('configuration'))!=base.canonical(CONFIGS[arm]) or completed_result.get('manifest_binding')!=base.digest(manifest) or
            final.get('status')!='returned' or 'io_error' not in final or 'heartbeat_error' not in final or
            final['io_error'] is not None or final['heartbeat_error'] is not None or value['status']!='returned'):
            raise ValueError('Authenticated final observer result is unhealthy or snapshot hash differs')
        if (base.canonical(completed_result.get('projection_support_policy'))!=base.canonical(SUPPORT_POLICY) or
            completed_result.get('projection_support_statistics')!=value['projection_support_statistics']):
            raise ValueError('Authenticated final projection statistics differ')
        validate_support_statistics(completed_result['projection_support_statistics'],arm,completed=True)
        final_health=True
    return dict(completion_admission_sha256=completion_sha,sha256=raw_sha,bytes=len(raw),status=value['status'],remaining_charge_admission_sha256=admission_sha,
        remaining_charge_activation_diagnostic=admission.get('diagnostic'),projection_support_statistics=value['projection_support_statistics'],
        sampled_wall_ns=value['sampled_wall_ns'],last_active_stack=value['active_stack'],
        maximum_observed_write_gap_ns=value['maximum_observed_write_gap_ns'],
        timeout_snapshot_is_censored=search_status=='TIMEOUT',terminal_observer_health_proved=final_health)


def run_gate(path,sha256,output,cpu):
    manifest=_manifest(path,sha256)
    ledger=base._run_plan(path,sha256,output,cpu,scope='od02_gate',manifest_loader=_manifest,
        worker_module='experiments.projection_completion_gate_v1.run',fixed_cases=(CASE,),fixed_pairs=[[CASE,list(ARMS)]],exact_phase_seconds=EXACT_PHASE_SECONDS)
    ledger.update(scope='od10_n32_projection_completion240_gate',operational_admission=False,diagnostic_admission='inconclusive',
        both_authenticated_complete=False,completion_outcome='inconclusive')
    try:
        if (ledger['status']!='COMPLETED' or ledger['denominator']!=5 or len(ledger['stages'])!=5 or
            len(ledger.get('arms',[]))!=2 or [a.get('strategy') for a in ledger['arms']]!=list(ARMS)):
            raise ValueError('Profile gate has incomplete stages')
        common=base.load_worker_result(Path(output)/('prepare-'+CASE),ledger['common'][CASE],'prepare',CASE)
        validate_common_domain(common)
        stages=ledger['stages']
        receipts=[ledger['common'][CASE]]
        for index,arm in enumerate(ledger['arms']):
            if arm['strategy']!=ARMS[index] or arm.get('case')!=CASE or arm.get('pair')!=0:
                raise ValueError('Profile arm identity differs')
            search,verified=arm['receipt'],arm['verification']
            if search['status'] not in ('SUCCESS','TIMEOUT') or verified['status']!='SUCCESS':
                raise ValueError('Profile receipt status not admitted')
            require_exact_phase(search)
            identity=search.get('phase_budget',{}).get('identity',{})
            if (identity.get('case_id')!=CASE or identity.get('strategy')!=arm['strategy'] or
                identity.get('arm_index')!=str(index) or identity.get('manifest_sha256')!=sha256 or
                identity.get('source_closure_sha256')!=manifest['source']['closure_sha256']):
                raise ValueError('Profile search phase identity differs')
            receipts.extend([search,verified])
            for position,op,receipt in ((1+2*index,'search',search),(2+2*index,'verify',verified)):
                if stages[position]!=dict(id=f'{op}-{index}',operation=op,case=CASE,strategy=arm['strategy'],status=receipt['status']):
                    raise ValueError('Profile stage/receipt differs')
            full=base.load_worker_result(Path(output)/f'verify-{index:02d}',verified,'verify',CASE,arm['strategy'])
            if arm['status']!=full['status']:raise ValueError('Profile verified outcome differs')
            arm['authenticated_completion']=False
            completed=None
            if search['status']=='SUCCESS':
                completed=base.load_worker_result(Path(output)/f'arm-{index:02d}',search,'arm',CASE,arm['strategy'])
                exact=completed.get('result')
                payload=exact.get('result') if type(exact) is dict else None
                terminal_payloads={'attained_optimum':('attained_optimum',),
                    'infimum_unattained':('primary_unattained','secondary_unattained')}
                if (completed.get('status') not in terminal_payloads or type(payload) is not dict or
                    payload.get('status') not in terminal_payloads[completed['status']]):
                    raise ValueError('Completed answer lacks an exact terminal result payload')
                if (completed['accepted_key']!=full['accepted_key'] or completed['status']!=full['status'] or
                    full.get('search_status')!='SUCCESS'):raise ValueError('Completed answer lacks matching fresh full replay')
                arm['authenticated_completion']=True
            arm['progress']=read_progress(Path(output)/f'arm-{index:02d}/artifacts/arm/progress/progress.json',
                manifest,arm['strategy'],common,search_status=search['status'],completed_result=completed)
        if (stages[0]!=dict(id='prepare-'+CASE,operation='prepare',case=CASE,status='SUCCESS') or
            ledger['common'][CASE]['status']!='SUCCESS' or any(not r.get('cleanup_verified') for r in receipts)):
            raise ValueError('Profile common receipt or cleanup differs')
        if all(a['receipt']['status']=='SUCCESS' for a in ledger['arms']):
            payloads=[]
            for index,arm in enumerate(ledger['arms']):
                finished=base.load_worker_result(Path(output)/f'arm-{index:02d}',arm['receipt'],'arm',CASE,arm['strategy'])
                payload=dict(finished['result']['result']);payload.pop('charges',None);payload.pop('witness_replayed',None)
                payloads.append(payload)
            if payloads[0]!=payloads[1]:raise ValueError('Completed exact answers disagree')
        ledger['both_authenticated_complete']=all(a['authenticated_completion'] for a in ledger['arms'])
        ledger['completion_outcome']='both_authenticated_complete' if ledger['both_authenticated_complete'] else 'partial_or_timeout_feasible_only'
        ledger['operational_admission']=True
        ledger['diagnostic_admission']='admitted_observed_prefixes'
    except (KeyError,TypeError,ValueError,OSError) as exc:
        ledger['admission_error']=str(exc)
        if ledger['status']=='COMPLETED':ledger['status']='FAILED_ADMISSION'
    temporary=Path(output)/'ledger.tmp';temporary.write_bytes(base.canonical(ledger));os.replace(temporary,Path(output)/'ledger.json')
    return ledger


def main():
    parser=argparse.ArgumentParser(description=__doc__);mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--plan',action='store_true');mode.add_argument('--freeze',action='store_true');mode.add_argument('--gate',action='store_true')
    mode.add_argument('--worker',choices=('prepare','arm','verify'))
    for name in ('manifest','manifest-sha256','output','input-directory','common','common-sha256','search-directory','search-receipt-sha256'):
        parser.add_argument('--'+name)
    parser.add_argument('--cpu',type=int);parser.add_argument('--case',choices=(CASE,));parser.add_argument('--strategy',choices=ARMS)
    args=parser.parse_args()
    if args.plan:print(json.dumps(prospective(),indent=2,sort_keys=True));return 0
    if args.freeze:
        if not args.output or not args.input_directory:parser.error('--freeze requires --output and --input-directory')
        root=Path.cwd().resolve();compiler=Path(shutil.which('g++')).resolve();manifest=prospective()
        manifest.update(launchable=True,status='frozen_projection_completion240_gate_not_launched',repo=str(root),input_directory=str(Path(args.input_directory).resolve()),
            compiler=dict(path=str(compiler),sha256=base.file_hash(compiler),version=subprocess.check_output([str(compiler),'--version'],text=True),flags=['-O3','-std=c++17']),source=source_identity(root))
        raw=base.canonical(manifest)
        with Path(args.output).open('xb') as stream:stream.write(raw)
        sha=hashlib.sha256(raw).hexdigest();_manifest(args.output,sha)
        print(json.dumps(dict(manifest=str(Path(args.output).resolve()),sha256=sha)));return 0
    if args.gate:
        if args.output is None or args.cpu is None or args.case is not None or args.strategy is not None:
            parser.error('--gate requires output/cpu and fixed cases/arms')
        return 0 if run_gate(args.manifest,args.manifest_sha256,args.output,args.cpu)['operational_admission'] else 1
    manifest=_manifest(args.manifest,args.manifest_sha256)
    if args.case!=CASE or (args.worker!='prepare' and args.strategy is None):parser.error('Worker requires fixed case/arm')
    if args.worker=='prepare':
        result=development.prepare_case(manifest,Path(os.environ['HIROUTE_OUTPUT_DIR'])/'prepared')
        validate_common_domain(result)
        result.update(schema=SCHEMA,profile_seed_policy='inherited_originalN32_full_energy_generation_double_replay')
        (Path(os.environ['HIROUTE_OUTPUT_DIR'])/'prepared/common.json').write_bytes(base.canonical(result))
    else:
        if args.worker=='verify':
            from experiments.mechanism_recovery_v1.supervisor import read_result
            require_exact_phase(read_result(args.search_directory))
        factory=lambda m,q,s,c:domain_factory(m,q,s,c,arm=args.strategy)
        base.worker(manifest,args.worker,args.case,args.common,args.common_sha256,args.strategy,args.search_directory,args.search_receipt_sha256,domain_factory=factory)
    _manifest(args.manifest,args.manifest_sha256)
    Path(os.environ['HIROUTE_WORKER_RECEIPT']).write_bytes(base.canonical(dict(status='COMPLETED',
        result=base.result_envelope(os.environ['HIROUTE_OUTPUT_DIR'],args.worker,args.case,args.strategy))))
    return 0


if __name__=='__main__':sys.exit(main())
