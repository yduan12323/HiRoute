"""Separate OD10 N32 dyadic ALT q=0 versus q=10 DEV gate."""
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
from experiments.search_extensions_v1.run import require_exact_phase
from timecut5.exact_progress import operation, event
from experiments.scalability_profile_v1 import run as profile
from experiments.remaining_charge_gate_v1 import run as remaining
from fractions import Fraction as F

SCHEMA = 'hiroute.dyadic_alt_gate.v1'
ORIGINAL_HMAX = 26
CASE = development.CASE
ARMS = ('time_q0', 'time_q10')
QUANTA = dict(zip(ARMS,(0,10)))
TIME_POLICIES = {arm:dict(time_quantum_exponent=q,time_units_per_second=2**q,
    bound_output_unit='exact_seconds',certificate_schema=('hiroute.m5d.dyadic_second_landmark.v2' if q else 'hiroute.m5d.integer_second_landmark.v1'),
    suffix_binding_schema=('hiroute.suffix_time_potential.v2' if q else 'hiroute.suffix_time_potential.v1'),
    edge_weight_policy=('floor(nextafter(ldexp(frozen_binary64_time,time_quantum_exponent),-infinity))' if q else 'floor(nextafter(frozen_binary64_time,-infinity))'))
    for arm,q in QUANTA.items()}
BOUND_POLICY = dict(schema='hiroute.remaining_charge_region_gate.v1',
    runtime_api='hiroute.remaining_charge_runtime.v1',
    rule='max_existing_region_prefix_and_whole_route_at_next_stop',
    preserve_original_none=True, preserve_original_Hmax=True, strict_pruning_owned_by_engine=True,
    frontier_origin='trusted_current_solver_same_problem', caching=False)
CONFIGS = {arm:dict(routing='destination_target',terminal_energy=True,reducer='reduce_frontier_skyline',
    onward_alt=True,coalescing=False,remaining_charge=True,time_quantum_exponent=QUANTA[arm],bound_policy=BOUND_POLICY)
    for arm in ARMS}
OBSERVER = dict(profile.OBSERVER)
POLICY = dict(development.POLICY,routing='destination_target',candidate_count=32,
    observer=OBSERVER,cross_size_seed_policy='not_applicable_fixed_N32',method='HIER',
    reducer='reduce_frontier_skyline',onward_alt=True,remaining_charge_bound=BOUND_POLICY,
    time_quantum_policies=TIME_POLICIES,original_Hmax=ORIGINAL_HMAX)


def source_identity(repo):
    identity=remaining.source_identity(repo)
    closure=dict(identity['closure'])
    for path in sorted((Path(repo)/'experiments/dyadic_alt_gate_v1').rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix not in ('.pyc','.pyo'):
            closure[str(path.relative_to(repo))]=base.file_hash(path)
    return dict(identity,closure=closure,closure_sha256=base.digest(closure))


def prospective():
    return dict(schema=SCHEMA,launchable=False,status='prospective_pending_source_review',
        candidate_count=32,policy=POLICY,arms=CONFIGS,order=list(ARMS),observer=OBSERVER,
        denominator=development.DENOMINATOR,reserve_plan=development.RESERVE,
        limits=base.LIMITS,cache_policy=base.CACHE_POLICY,inputs=development.prospective()['inputs'],
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


ProfileProgress = profile.ProfileProgress


RemainingChargeRegionBound = remaining.RemainingChargeRegionBound

class DyadicALTDomain(base.NativeDomain):
    def __init__(self,*,arm,manifest_binding,required_hmax=None,**kwargs):
        if arm not in CONFIGS:raise ValueError('Unknown remaining-charge arm')
        self.arm=arm;self.config=json.loads(base.canonical(CONFIGS[arm]));self._config=base.canonical(self.config)
        self.manifest_binding=manifest_binding;self._manifest=manifest_binding
        self._search_problem=None;self.required_hmax=required_hmax
        super().__init__(**kwargs)

    def check(self):
        super().check()
        if (base.canonical(self.config)!=self._config or self.config!=CONFIGS[self.arm] or
            self.manifest_binding!=self._manifest):raise ValueError('Remaining-charge runtime policy changed')

    context = profile.ProfileDomain.context

    def problem(self,context,depth=None):
        result=super().problem(context,depth)
        if context.role=='search':self._search_problem=result
        return result

    def durable_binding(self,seed):
        # Stable semantic policy/source only: context-specific admission hashes
        # contain process-local identity and must never prevent fresh replay.
        if self.required_hmax is not None and seed.max_depth!=self.required_hmax:
            raise ValueError('Original declared Hmax differs from frozen dyadic domain')
        binding=super().durable_binding(seed)
        binding['domain_sha256']=base.digest([binding['domain_sha256'],SCHEMA,self.arm,self.config,self.manifest_binding])
        binding['source_sha256']=dict(binding['source_sha256'],profile_policy=base.digest([self.arm,self.config,self.manifest_binding]))
        return binding

    def make_bound(self,context,strategy):
        from timecut5.remaining_charge_runtime import admit_remaining_charge_runtime
        self._search_provider=context.provider
        from timecut5.road_provider import TableFreeRegionBoundProvider
        query=json.loads(self.query_bytes)
        original=TableFreeRegionBoundProvider(context.provider,self.sites,self.tree,
            destination_anchor=query['destination'],landmark_anchor=query['origin'],
            site_catalog_sha256=self.site_sha256,router_factory=self.landmark_router,
            alt_strategy='indexed',collect_alt_member_reads=False,onward_alt=True,
            time_quantum_exponent=self.config['time_quantum_exponent'])
        problem=self._search_problem
        if problem is None or problem.provider is not context.provider:
            raise ValueError('Actual search problem required before runtime admission')
        started=time.monotonic_ns();runtime=None
        seed_key=json.loads(self._seed.key_bytes)
        initial_upper=F(seed_key[0])
        receipt=dict(schema=SCHEMA,arm=self.arm,status='disabled_by_policy',
            original_Hmax=problem.bound,seed_H=seed_key[2],seed_J=seed_key[0],
            portable_bound_policy=BOUND_POLICY,context_receipt_portable=False)
        if self.config['remaining_charge']:
            runtime=admit_remaining_charge_runtime(problem,energy_screen=problem._terminal_energy_screen,travel_provider=original)
            seed_bound=runtime.whole_route_lower_bound(seed_key[2])
            zero_bound=runtime.whole_route_lower_bound(0)
            hmax_bound=runtime.whole_route_lower_bound(problem.bound)
            if seed_bound.status=='active' and seed_bound.primary_lower_bound>initial_upper:
                raise ValueError('Certified whole-route bound contradicts independently verified seed')
            if runtime.original_hmax!=problem.bound or problem.bound!=self._seed.max_depth:
                raise ValueError('Runtime admission changed original Hmax')
            if any(x.binding_sha256!=runtime.binding_sha256 or x.status!=seed_bound.status for x in (seed_bound,zero_bound,hmax_bound)):
                raise ValueError('Activation bound statuses or bindings differ')
            diagnostic=dict(global_lower_zero=None,global_lower_original_Hmax=None,stop_threshold=None,changes_declared_Hmax=False)
            if seed_bound.status=='active':
                step=problem.overhead+problem.penalty
                if step<=0:raise ValueError('Positive original stop cost required')
                threshold=min(problem.bound,(initial_upper-zero_bound.primary_lower_bound)//step)
                if threshold<seed_key[2]:raise ValueError('Diagnostic stop threshold excludes verified seed')
                diagnostic.update(global_lower_zero=str(zero_bound.primary_lower_bound),
                    global_lower_original_Hmax=str(hmax_bound.primary_lower_bound),stop_threshold=threshold)
            receipt.update(diagnostic=diagnostic,status=seed_bound.status,seed_bound=None if seed_bound.primary_lower_bound is None else str(seed_bound.primary_lower_bound),
                runtime_binding_sha256=runtime.binding_sha256,runtime_binding=runtime.binding)
        time_receipt=time_admission_receipt(original,problem,runtime,self.arm)
        receipt['time_policy']=TIME_POLICIES[self.arm]
        receipt['time_admission']=time_receipt
        self._activation_wall_ns=time.monotonic_ns()-started
        receipt['activation_wall_ns']=self._activation_wall_ns
        self._activation_receipt=receipt
        (self._output/'remaining_charge_admission.json').write_bytes(base.canonical(receipt))
        wrapped=RemainingChargeRegionBound(original,problem,runtime=runtime,current_upper=initial_upper)
        self._remaining_bound=wrapped
        return wrapped

    def solve_exact(self,problem,witness,key,bound,store):
        from timecut5.hierarchy import _solve_hierarchical_problem
        from timecut5.pwa import reduce_frontier_skyline
        binding=self.durable_binding(self._seed)
        observer=ProfileProgress(self._output/'progress',query_sha256=base.digest(json.loads(self.query_bytes)),
            domain_sha256=binding['domain_sha256'],source_sha256=binding['source_sha256'],provider=self._search_provider)
        observer.state.update(profile_schema=SCHEMA,arm=self.arm,configuration=self.config,manifest_binding=self.manifest_binding,
            candidate_count=len(self.sites),Hmax=self._seed.max_depth,remaining_charge_activation_wall_ns=self._activation_wall_ns,
            remaining_charge_admission_sha256=base.file_hash(self._output/'remaining_charge_admission.json'),
            remaining_charge_activation_diagnostic=self._activation_receipt.get('diagnostic'),
            remaining_charge_seed_bound=self._activation_receipt.get('seed_bound'),
            time_policy=TIME_POLICIES[self.arm],time_admission=self._activation_receipt['time_admission'])
        observer.state['timings']['durable_incumbent_callback']=dict(calls=0,wall_ns=0,cpu_ns=0,errors=0)
        @operation('durable_incumbent_callback')
        def observed_store(candidate,candidate_key):
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
            solved=_solve_hierarchical_problem(problem,True,self.tree,witness,reducer=reduce_frontier_skyline,
                verified_primary_upper=key[0],bound_provider=bound,incumbent_hook=observed_store,progress_hook=observer,checkpoint_hook=checkpoint)
            self._actual_engine_prunes=solved.pruned_regions
            return solved
        finally:
            self._observer_status=dict(io_error=observer.state['io_error'],heartbeat_error=observer.state.get('heartbeat_error'),
                status=observer.state['status'],persist_attempts=observer.state['persist_attempts'])

    def run_arm(self,strategy,seed,output,**kwargs):
        if strategy!=self.arm:raise ValueError('Remaining-charge arm differs')
        self._seed=seed;self._output=Path(output)
        result=super().run_arm('indexed',seed,output,**kwargs)
        result.update(schema=SCHEMA,strategy=self.arm,configuration=self.config,manifest_binding=self.manifest_binding,
            full_routing=False,time_policy=TIME_POLICIES[self.arm],observer=self._observer_status,remaining_charge_counters=dict(self._remaining_bound.counters),
            actual_engine_pruned_regions=getattr(self,'_actual_engine_prunes',None),
            remaining_charge_activation_wall_ns=self._activation_wall_ns,
            remaining_charge_admission_sha256=base.file_hash(self._output/'remaining_charge_admission.json'),
            progress_sha256=base.file_hash(self._output/'progress/progress.json'))
        (self._output/'result.json').write_bytes(base.canonical(result));return result


def domain_factory(manifest,query,sites,cache,*,arm):
    if len(sites)!=32:raise ValueError('Profile requires original N32')
    directory,bindings=manifest['input_directory'],manifest['inputs']
    tree=base.original_tree((Path(directory)/'hierarchy.json').read_bytes(),bindings['hierarchy.json']['sha256'],list(sites))
    return DyadicALTDomain(arm=arm,required_hmax=ORIGINAL_HMAX,manifest_binding=base.digest(manifest),graph_factory=lambda:base.load_graph(directory,bindings),
        query=query,sites=sites,tree=tree,source_hashes=dict({n:bindings[n+'.parquet']['sha256'] for n in ('nodes','edges')},
            source_closure=manifest['source']['closure_sha256'],**{'input:'+n:b['sha256'] for n,b in bindings.items()}),
        cache=cache,compiler=manifest['compiler']['path'],cache_policy=manifest['cache_policy'])


def progress_binding(manifest,arm,common):
    seed=common['seed']
    ordinary=base.digest([common['query'],common['tree_sha256'],seed['site_sha256'],
        json.loads(seed['key_bytes']),seed['max_depth'],seed['native_sha256'],manifest['cache_policy']])
    manifest_binding=base.digest(manifest)
    sources=dict({n:manifest['inputs'][n+'.parquet']['sha256'] for n in ('nodes','edges')},
        source_closure=manifest['source']['closure_sha256'],
        **{'input:'+n:b['sha256'] for n,b in manifest['inputs'].items()},
        profile_policy=base.digest([arm,CONFIGS[arm],manifest_binding]))
    return base.digest([ordinary,SCHEMA,arm,CONFIGS[arm],manifest_binding]),sources


def time_admission_receipt(provider,problem,runtime,arm):
    """Public provider properties/certificate and live suffix accessor only."""
    policy=TIME_POLICIES[arm]
    if (type(provider.time_quantum_exponent) is not int or provider.time_quantum_exponent!=policy['time_quantum_exponent'] or
        type(provider.time_units_per_second) is not int or provider.time_units_per_second!=policy['time_units_per_second']):
        raise ValueError('Constructed time quantum differs from arm')
    suffix=provider.certified_suffix_time_v1(problem,problem.origin)
    if suffix.binding_sha256!=runtime.binding['potential_bindings'][1]:
        raise ValueError('Admitted suffix time binding differs')
    return dict(certificate=json.loads(provider.landmark_certificate),certificate_sha256=provider.landmark_sha256,
        suffix_binding_sha256=suffix.binding_sha256,origin_suffix_status=suffix.status,
        origin_suffix_seconds=None if suffix.lower_bound is None else str(suffix.lower_bound))


def validate_activation_receipt(admission,value,arm,common):
    if (admission.get('schema')!=SCHEMA or admission.get('arm')!=arm or
        base.canonical(admission.get('time_policy'))!=base.canonical(TIME_POLICIES[arm]) or base.canonical(value.get('time_policy'))!=base.canonical(TIME_POLICIES[arm]) or
        value.get('time_admission')!=admission.get('time_admission')):
        raise ValueError('Dyadic time policy or snapshot echoes differ')
    evidence=admission['time_admission'];policy=TIME_POLICIES[arm]
    if type(evidence) is not dict or set(evidence)!={'certificate','certificate_sha256','suffix_binding_sha256','origin_suffix_status','origin_suffix_seconds'}:
        raise ValueError('Time admission evidence fields differ')
    cert=evidence['certificate'];sources=admission['runtime_binding']['provider_sources']
    if (type(cert) is not dict or base.digest(cert)!=evidence['certificate_sha256'] or
        cert.get('schema')!=policy['certificate_schema'] or cert.get('edge_weight_policy')!=policy['edge_weight_policy'] or
        cert.get('exact_integer_limit')!=2**53 or cert.get('graph_nodes_sha256')!=sources['nodes'] or
        cert.get('graph_edges_sha256')!=sources['edges'] or cert.get('router_source_sha256')!=sources['router'] or
        cert.get('root_anchor')!=common['query']['origin']):raise ValueError('Time certificate policy/source differs')
    if QUANTA[arm]:
        if (type(cert.get('time_quantum_exponent')) is not int or cert['time_quantum_exponent']!=QUANTA[arm] or
            type(cert.get('time_units_per_second')) is not int or cert['time_units_per_second']!=policy['time_units_per_second']):
            raise ValueError('Dyadic certificate quantum differs')
    elif 'time_quantum_exponent' in cert or 'time_units_per_second' in cert:
        raise ValueError('Legacy q0 certificate unexpectedly carries quantum fields')
    expected_suffix=base.digest(dict(schema=policy['suffix_binding_schema'],construction_sha256=evidence['certificate_sha256'],
        source_sha256=sources,destination=common['query']['destination'],site_catalog_sha256=common['seed']['site_sha256']))
    if (evidence['suffix_binding_sha256']!=expected_suffix or
        admission['runtime_binding']['potential_bindings'][1]!=expected_suffix):
        raise ValueError('Runtime suffix binding/time units differ')
    if evidence['origin_suffix_status']=='active':
        text=evidence['origin_suffix_seconds']
        try:
            if type(text) is not str or str(F(text))!=text or F(text)<0:raise ValueError('Exact nonnegative origin suffix seconds required')
        except ZeroDivisionError as exc:raise ValueError('Invalid origin suffix denominator') from exc
        labels=cert['anchor_labels'];origin=labels[common['query']['origin']];destination=labels[common['query']['destination']]
        if any(type(row) is not list or len(row)!=2 or any(x is not None and (type(x) is not int or not 0<=x<2**53) for x in row) for row in (origin,destination)):
            raise ValueError('Malformed integer-unit origin/destination labels')
        terms=[0]+[left-right for left,right in ((destination[0],origin[0]),(origin[1],destination[1])) if left is not None and right is not None]
        if F(text)!=F(max(terms),policy['time_units_per_second']):raise ValueError('Origin suffix bound/unit conversion differs')
    elif evidence['origin_suffix_status']!='disabled_unsupported' or evidence['origin_suffix_seconds'] is not None:
        raise ValueError('Unknown origin suffix status')
    # Reuse the reviewed activation semantics validator with only the outer
    # experiment identity translated; both quantum arms enable the same bound.
    translated=dict(admission);translated.pop('time_policy');translated.pop('time_admission')
    translated.update(schema=remaining.SCHEMA,arm=remaining.ARMS[1])
    remaining.validate_activation_receipt(translated,value,remaining.ARMS[1],common)


def validate_common_domain(common):
    if (common.get('case_id')!=CASE or common.get('candidate_count')!=32 or len(common.get('sites',[]))!=32 or
        type(common['seed']['max_depth']) is not int or common['seed']['max_depth']!=ORIGINAL_HMAX):
        raise ValueError('Original OD10 N32/Hmax26 common domain differs')


def read_progress(path,manifest,arm,common,*,search_status,completed_result=None):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size>OBSERVER['max_snapshot_bytes']:
        raise ValueError('Missing or unbounded profile snapshot')
    raw=path.read_bytes();value=json.loads(raw)
    expected_domain,expected_sources=progress_binding(manifest,arm,common)
    if (value.get('domain_sha256')!=expected_domain or value.get('source_sha256')!=expected_sources or
        value.get('profile_schema')!=SCHEMA or value.get('arm')!=arm or base.canonical(value.get('configuration'))!=base.canonical(CONFIGS[arm]) or
        value.get('manifest_binding')!=base.digest(manifest) or value.get('candidate_count')!=32 or
        value.get('query_sha256')!=base.digest(common['query']) or value.get('Hmax')!=common['seed']['max_depth'] or
        value.get('status') not in ('running','returned') or value.get('io_error') is not None or value.get('heartbeat_error') is not None):
        raise ValueError('Profile snapshot binding or observer health differs')
    admission_path=path.parent.parent/'remaining_charge_admission.json'
    if admission_path.is_symlink() or not admission_path.is_file() or admission_path.stat().st_size>OBSERVER['max_snapshot_bytes']:
        raise ValueError('Missing or unbounded remaining-charge admission')
    admission_raw=admission_path.read_bytes();admission=json.loads(admission_raw)
    admission_sha=hashlib.sha256(admission_raw).hexdigest()
    if (value.get('remaining_charge_admission_sha256')!=admission_sha or admission.get('schema')!=SCHEMA or
        admission.get('arm')!=arm or admission.get('portable_bound_policy')!=BOUND_POLICY or
        admission.get('original_Hmax')!=common['seed']['max_depth'] or admission.get('context_receipt_portable') is not False):
        raise ValueError('Remaining-charge admission binding differs')
    validate_activation_receipt(admission,value,arm,common)
    raw_sha=hashlib.sha256(raw).hexdigest()
    if search_status not in ('SUCCESS','TIMEOUT'):raise ValueError('Profile search outcome not admitted')
    final_health=False
    if search_status=='SUCCESS':
        if not isinstance(completed_result,dict):raise ValueError('Authenticated normal arm result required')
        final=completed_result.get('observer',{})
        if (completed_result.get('remaining_charge_admission_sha256')!=admission_sha or
            completed_result.get('remaining_charge_activation_wall_ns')!=admission['activation_wall_ns'] or completed_result.get('progress_sha256')!=raw_sha or completed_result.get('strategy')!=arm or
            base.canonical(completed_result.get('time_policy'))!=base.canonical(TIME_POLICIES[arm]) or base.canonical(completed_result.get('configuration'))!=base.canonical(CONFIGS[arm]) or completed_result.get('manifest_binding')!=base.digest(manifest) or
            final.get('status')!='returned' or 'io_error' not in final or 'heartbeat_error' not in final or
            final['io_error'] is not None or final['heartbeat_error'] is not None or value['status']!='returned'):
            raise ValueError('Authenticated final observer result is unhealthy or snapshot hash differs')
        final_health=True
    return dict(sha256=raw_sha,bytes=len(raw),status=value['status'],remaining_charge_admission_sha256=admission_sha,
        remaining_charge_activation_diagnostic=admission.get('diagnostic'),
        sampled_wall_ns=value['sampled_wall_ns'],last_active_stack=value['active_stack'],
        maximum_observed_write_gap_ns=value['maximum_observed_write_gap_ns'],
        timeout_snapshot_is_censored=search_status=='TIMEOUT',terminal_observer_health_proved=final_health)


def run_gate(path,sha256,output,cpu):
    manifest=_manifest(path,sha256)
    ledger=base._run_plan(path,sha256,output,cpu,scope='od02_gate',manifest_loader=_manifest,
        worker_module='experiments.dyadic_alt_gate_v1.run',fixed_cases=(CASE,),fixed_pairs=[[CASE,list(ARMS)]])
    ledger.update(scope='od10_n32_dyadic_alt_gate',operational_admission=False,diagnostic_admission='inconclusive')
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
            completed=None
            if search['status']=='SUCCESS':
                completed=base.load_worker_result(Path(output)/f'arm-{index:02d}',search,'arm',CASE,arm['strategy'])
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
        manifest.update(launchable=True,status='frozen_dyadic_alt_gate_not_launched',repo=str(root),input_directory=str(Path(args.input_directory).resolve()),
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
