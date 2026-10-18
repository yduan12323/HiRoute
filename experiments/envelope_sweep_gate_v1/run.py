"""Separate240-second OD10 N32 envelope-selector OFF/ON DEV gate."""
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

from experiments.projection_completion_gate_v1 import run as completion
from timecut5.envelope_sweep import EnvelopeSweep, EnvelopeSweepStatistics

SCHEMA = 'hiroute.envelope_sweep_gate.v1'
CASE = projection.CASE
INNER_ARM = 'support_on'
ARMS = ('envelope_off', 'envelope_on')
EXACT_PHASE_SECONDS = completion.EXACT_PHASE_SECONDS
ORIGINAL_HMAX = projection.ORIGINAL_HMAX
OBSERVER = dict(projection.OBSERVER)
LIMITS = dict(completion.LIMITS)
RESERVE = dict(completion.RESERVE)
ENVELOPE_POLICY = dict(schema='hiroute.envelope_sweep.v1',
    scope='exact_search_excluding_independent_incumbent_replay',
    rule='exact_pair_relation_interval_events_zero_better_parent_heap',
    arrangement='unchanged_original',original_parent_and_cell_order=True,
    recorder_fallback='historical_selector',default_absent_unchanged=True)
CONFIGS = {arm:dict(inner_arm=INNER_ARM,inner_configuration=projection.CONFIGS[INNER_ARM],
    envelope_sweep=arm=='envelope_on') for arm in ARMS}
POLICY = dict(projection.POLICY,time_quantum_policies={INNER_ARM:projection.TIME_POLICIES[INNER_ARM]},
    inner_experiment_schema=projection.SCHEMA,inner_arm=INNER_ARM,
    envelope_sweep_policy=ENVELOPE_POLICY,exact_phase_seconds=EXACT_PHASE_SECONDS,
    completion_requires_authenticated_result_and_fresh_replay=True)
require_exact_phase = completion.require_exact_phase
validate_common_domain = projection.validate_common_domain


def source_identity(repo):
    identity=completion.source_identity(repo)
    closure=dict(identity['closure'])
    for path in sorted((Path(repo)/'experiments/envelope_sweep_gate_v1').rglob('*')):
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



class EnvelopeProgress(projection.ProfileProgress):
    def __init__(self,*args,envelope_sweep,**kwargs):
        self.envelope_sweep=envelope_sweep
        super().__init__(*args,**kwargs)

    def metrics(self):
        # Detached scalar snapshot; a live multi-counter sample is not atomic.
        self.state['envelope_sweep_statistics']=asdict(self.envelope_sweep.snapshot())
        return super().metrics()


class EnvelopeDomain(projection.ProjectionSupportDomain):
    """Immutable support_on inner adapter with a separately bound outer arm."""
    def __init__(self,*,arm,**kwargs):
        if arm not in CONFIGS:raise ValueError('Unknown envelope arm')
        self.outer_arm=arm
        self.outer_config=json.loads(base.canonical(CONFIGS[arm]))
        self._outer_binding=base.canonical([arm,self.outer_config])
        super().__init__(arm=INNER_ARM,**kwargs)

    def check(self):
        super().check()
        if (self.arm!=INNER_ARM or self.outer_arm not in CONFIGS or
            base.canonical([self.outer_arm,self.outer_config])!=self._outer_binding or
            base.canonical(self.outer_config)!=base.canonical(CONFIGS[self.outer_arm])):
            raise ValueError('Envelope runtime policy changed')

    def durable_binding(self,seed):
        binding=super().durable_binding(seed)
        policy=[SCHEMA,self.outer_arm,self.outer_config,ENVELOPE_POLICY,self.manifest_binding]
        binding['domain_sha256']=base.digest([binding['domain_sha256'],*policy])
        binding['source_sha256']=dict(binding['source_sha256'],envelope_policy=base.digest(policy))
        return binding

    def make_bound(self,context,strategy):
        bound=super().make_bound(context,strategy)
        receipt=outer_admission(self.manifest_binding,self.outer_arm,
            base.file_hash(self._output/'remaining_charge_admission.json'))
        (self._output/'envelope_admission.json').write_bytes(base.canonical(receipt))
        return bound

    def solve_exact(self,problem,witness,key,bound,store):
        from timecut5.hierarchy import _solve_hierarchical_problem
        from timecut5.pwa import reduce_frontier_skyline,ProjectionSupportPrefilter
        binding=self.durable_binding(self._seed)
        prefilter=ProjectionSupportPrefilter(enabled=self.config['projection_support'])
        if prefilter.enabled is not self.config['projection_support']:raise ValueError('Projection support context policy differs')
        envelope=EnvelopeSweep(enabled=self.outer_config['envelope_sweep'])
        observer=EnvelopeProgress(self._output/'progress',query_sha256=base.digest(json.loads(self.query_bytes)),
            domain_sha256=binding['domain_sha256'],source_sha256=binding['source_sha256'],provider=self._search_provider,projection_support=prefilter,envelope_sweep=envelope)
        observer.state.update(profile_schema=projection.SCHEMA,arm=self.arm,configuration=self.config,manifest_binding=self.manifest_binding,
            candidate_count=len(self.sites),Hmax=self._seed.max_depth,remaining_charge_activation_wall_ns=self._activation_wall_ns,
            remaining_charge_admission_sha256=base.file_hash(self._output/'remaining_charge_admission.json'),
            remaining_charge_activation_diagnostic=self._activation_receipt.get('diagnostic'),
            remaining_charge_seed_bound=self._activation_receipt.get('seed_bound'),
            time_policy=projection.TIME_POLICIES[self.arm],time_admission=self._activation_receipt['time_admission'],
            projection_support_policy=projection.SUPPORT_POLICY,projection_support_enabled=self.config['projection_support'])
        observer.state.update(envelope_schema=SCHEMA,envelope_arm=self.outer_arm,envelope_configuration=self.outer_config,
            envelope_sweep_policy=ENVELOPE_POLICY,envelope_admission_sha256=base.file_hash(self._output/'envelope_admission.json'))
        observer.state['timings']['durable_incumbent_callback']=dict(calls=0,wall_ns=0,cpu_ns=0,errors=0)
        @operation('durable_incumbent_callback')
        def observed_store(candidate,candidate_key):
            # A distinct disabled context prevents the ON feature from entering
            # fresh full incumbent verification and keeps its counts separate.
            with EnvelopeSweep(enabled=False), ProjectionSupportPrefilter(enabled=False):
                result=store(candidate,candidate_key)
            bound.current_upper=min(bound.current_upper,candidate_key[0])
            return result
        # Counterfactual skip candidates use the same current verified upper
        # bound; actual pruning and equality retention stay in the engine.
        bound.current_upper=key[0]
        def checkpoint(depth,layer,terminals,incumbent,counters):
            event('remaining_charge_engine_checkpoint',actual_pruned_regions_at_last_checkpoint=counters[6],
                actual_equality_nodes_at_last_checkpoint=counters[7],engine_checkpoint_depth=depth)
        try:
            with envelope, prefilter:
                solved=_solve_hierarchical_problem(problem,True,self.tree,witness,reducer=reduce_frontier_skyline,
                    verified_primary_upper=key[0],bound_provider=bound,incumbent_hook=observed_store,progress_hook=observer,checkpoint_hook=checkpoint)
            self._actual_engine_prunes=solved.pruned_regions
            return solved
        finally:
            self._envelope_statistics=asdict(envelope.snapshot())
            self._support_statistics=asdict(prefilter.snapshot())
            self._observer_status=dict(io_error=observer.state['io_error'],heartbeat_error=observer.state.get('heartbeat_error'),
                status=observer.state['status'],persist_attempts=observer.state['persist_attempts'])
    def run_arm(self,strategy,seed,output,**kwargs):
        self.check()
        if strategy!=self.outer_arm:raise ValueError('Envelope requested arm differs')
        result=super().run_arm(INNER_ARM,seed,output,**kwargs)
        result.update(schema=SCHEMA,strategy=self.outer_arm,inner_experiment_schema=projection.SCHEMA,
            inner_arm=INNER_ARM,outer_configuration=self.outer_config,envelope_sweep_policy=ENVELOPE_POLICY,
            envelope_admission_sha256=base.file_hash(Path(output)/'envelope_admission.json'),
            envelope_sweep_statistics=self._envelope_statistics)
        (Path(output)/'result.json').write_bytes(base.canonical(result))
        return result


def outer_admission(manifest_binding,arm,inner_sha):
    return dict(schema=SCHEMA,arm=arm,configuration=CONFIGS[arm],envelope_sweep_policy=ENVELOPE_POLICY,
        exact_phase_seconds=EXACT_PHASE_SECONDS,manifest_binding=manifest_binding,
        inner_experiment_schema=projection.SCHEMA,inner_arm=INNER_ARM,
        inner_configuration=projection.CONFIGS[INNER_ARM],inner_admission_sha256=inner_sha)


def domain_factory(manifest,query,sites,cache,*,arm):
    if len(sites)!=32:raise ValueError('Envelope gate requires original N32')
    directory,bindings=manifest['input_directory'],manifest['inputs']
    tree=base.original_tree((Path(directory)/'hierarchy.json').read_bytes(),bindings['hierarchy.json']['sha256'],list(sites))
    return EnvelopeDomain(arm=arm,required_hmax=ORIGINAL_HMAX,manifest_binding=base.digest(manifest),graph_factory=lambda:base.load_graph(directory,bindings),
        query=query,sites=sites,tree=tree,source_hashes=dict({n:bindings[n+'.parquet']['sha256'] for n in ('nodes','edges')},
            source_closure=manifest['source']['closure_sha256'],**{'input:'+n:b['sha256'] for n,b in bindings.items()}),
        cache=cache,compiler=manifest['compiler']['path'],cache_policy=manifest['cache_policy'])


def progress_binding(manifest,arm,common):
    inner,sources=projection.progress_binding(manifest,INNER_ARM,common)
    policy=[SCHEMA,arm,CONFIGS[arm],ENVELOPE_POLICY,base.digest(manifest)]
    return base.digest([inner,*policy]),dict(sources,envelope_policy=base.digest(policy))


def validate_envelope_statistics(statistics,arm,*,completed):
    names=set(EnvelopeSweepStatistics.__dataclass_fields__)
    if (type(statistics) is not dict or set(statistics)!=names or type(statistics['enabled']) is not bool or
        statistics['enabled'] is not CONFIGS[arm]['envelope_sweep'] or
        any(type(statistics[n]) is not int or statistics[n]<0 for n in names-{'enabled'})):
        raise ValueError('Envelope statistics types or policy differ')
    sweep_only=('pair_tests','relation_intervals','event_updates','heap_pushes','heap_pops')
    if not statistics['enabled'] and any(statistics[n] for n in sweep_only):
        raise ValueError('Disabled envelope reported sweep work')
    if completed and (statistics['completed_calls']!=statistics['calls'] or
        statistics['selected_cells']>statistics['arrangement_cells'] or
        statistics['recorded_fallback_calls']>statistics['calls']):
        raise ValueError('Completed envelope counters do not conserve')


def read_bounded_json(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size>OBSERVER['max_snapshot_bytes']:
        raise ValueError('Missing or unbounded envelope artifact')
    raw=path.read_bytes()
    return json.loads(raw),hashlib.sha256(raw).hexdigest(),len(raw)


def read_progress(path,manifest,arm,common,*,search_status,completed_result=None):
    path=Path(path);value,raw_sha,size=read_bounded_json(path)
    admission,admission_sha,_=read_bounded_json(path.parent.parent/'remaining_charge_admission.json')
    outer,outer_sha,_=read_bounded_json(path.parent.parent/'envelope_admission.json')
    # Validate the actual outer identities before invoking any inner validator.
    if base.canonical(outer)!=base.canonical(outer_admission(base.digest(manifest),arm,admission_sha)):
        raise ValueError('Outer envelope admission differs')
    if (value.get('envelope_schema')!=SCHEMA or value.get('envelope_arm')!=arm or
        base.canonical(value.get('envelope_configuration'))!=base.canonical(CONFIGS[arm]) or
        base.canonical(value.get('envelope_sweep_policy'))!=base.canonical(ENVELOPE_POLICY) or
        value.get('envelope_admission_sha256')!=outer_sha):
        raise ValueError('Outer envelope progress binding differs')
    expected_domain,expected_sources=progress_binding(manifest,arm,common)
    if (value.get('domain_sha256')!=expected_domain or value.get('source_sha256')!=expected_sources or
        value.get('profile_schema')!=projection.SCHEMA or value.get('arm')!=INNER_ARM or
        base.canonical(value.get('configuration'))!=base.canonical(projection.CONFIGS[INNER_ARM]) or
        value.get('manifest_binding')!=base.digest(manifest) or value.get('candidate_count')!=32 or
        value.get('query_sha256')!=base.digest(common['query']) or value.get('Hmax')!=common['seed']['max_depth'] or
        value.get('status') not in ('running','returned') or value.get('io_error') is not None or value.get('heartbeat_error') is not None):
        raise ValueError('Inner snapshot binding or observer health differs')
    if (value.get('remaining_charge_admission_sha256')!=admission_sha or
        admission.get('portable_bound_policy')!=projection.BOUND_POLICY or
        admission.get('original_Hmax')!=common['seed']['max_depth'] or admission.get('context_receipt_portable') is not False):
        raise ValueError('Inner activation admission binding differs')
    projection.validate_activation_receipt(admission,value,INNER_ARM,common)
    projection.validate_support_statistics(value.get('projection_support_statistics'),INNER_ARM,completed=False)
    validate_envelope_statistics(value.get('envelope_sweep_statistics'),arm,completed=False)
    if search_status not in ('SUCCESS','TIMEOUT'):raise ValueError('Envelope search outcome not admitted')
    final_health=False
    if search_status=='SUCCESS':
        result=completed_result
        if not isinstance(result,dict):raise ValueError('Authenticated normal envelope result required')
        if (result.get('schema')!=SCHEMA or result.get('strategy')!=arm or result.get('inner_experiment_schema')!=projection.SCHEMA or
            result.get('inner_arm')!=INNER_ARM or base.canonical(result.get('outer_configuration'))!=base.canonical(CONFIGS[arm]) or
            base.canonical(result.get('envelope_sweep_policy'))!=base.canonical(ENVELOPE_POLICY) or result.get('envelope_admission_sha256')!=outer_sha):
            raise ValueError('Authenticated outer envelope result differs')
        final=result.get('observer',{})
        if (result.get('remaining_charge_admission_sha256')!=admission_sha or
            result.get('remaining_charge_activation_wall_ns')!=admission['activation_wall_ns'] or result.get('progress_sha256')!=raw_sha or
            base.canonical(result.get('time_policy'))!=base.canonical(projection.TIME_POLICIES[INNER_ARM]) or
            base.canonical(result.get('configuration'))!=base.canonical(projection.CONFIGS[INNER_ARM]) or result.get('manifest_binding')!=base.digest(manifest) or
            final.get('status')!='returned' or 'io_error' not in final or 'heartbeat_error' not in final or
            final['io_error'] is not None or final['heartbeat_error'] is not None or value['status']!='returned'):
            raise ValueError('Authenticated final observer is unhealthy or hash differs')
        if (base.canonical(result.get('projection_support_policy'))!=base.canonical(projection.SUPPORT_POLICY) or
            result.get('projection_support_statistics')!=value['projection_support_statistics'] or
            result.get('envelope_sweep_statistics')!=value['envelope_sweep_statistics']):
            raise ValueError('Authenticated final operator statistics differ')
        projection.validate_support_statistics(result['projection_support_statistics'],INNER_ARM,completed=True)
        validate_envelope_statistics(result['envelope_sweep_statistics'],arm,completed=True)
        final_health=True
    return dict(sha256=raw_sha,bytes=size,status=value['status'],remaining_charge_admission_sha256=admission_sha,
        envelope_admission_sha256=outer_sha,remaining_charge_activation_diagnostic=admission.get('diagnostic'),
        projection_support_statistics=value['projection_support_statistics'],envelope_sweep_statistics=value['envelope_sweep_statistics'],
        sampled_wall_ns=value['sampled_wall_ns'],last_active_stack=value['active_stack'],
        maximum_observed_write_gap_ns=value['maximum_observed_write_gap_ns'],
        timeout_snapshot_is_censored=search_status=='TIMEOUT',terminal_observer_health_proved=final_health)


def run_gate(path,sha256,output,cpu):
    manifest=_manifest(path,sha256)
    ledger=base._run_plan(path,sha256,output,cpu,scope='od02_gate',manifest_loader=_manifest,
        worker_module='experiments.envelope_sweep_gate_v1.run',fixed_cases=(CASE,),fixed_pairs=[[CASE,list(ARMS)]],exact_phase_seconds=EXACT_PHASE_SECONDS)
    ledger.update(scope='od10_n32_envelope_sweep240_gate',operational_admission=False,diagnostic_admission='inconclusive',
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
        manifest.update(launchable=True,status='frozen_envelope_sweep240_gate_not_launched',repo=str(root),input_directory=str(Path(args.input_directory).resolve()),
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
