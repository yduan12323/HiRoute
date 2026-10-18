"""Experiment-only method-aware lifecycle with identical physical configuration."""
from contextlib import ExitStack
from dataclasses import asdict
from fractions import Fraction as F
import json
from pathlib import Path
import signal
import time

from experiments.mechanism_recovery_v1 import run as base
from experiments.projection_support_gate_v1 import run as projection
from experiments.envelope_sweep_gate_v1 import run as envelope
from experiments.remaining_charge_gate_v1.singleton import RemainingChargeSingletonBound, POLICY_SCHEMA
from timecut5.exact_progress import operation,event
from timecut5.envelope_sweep import EnvelopeSweep
from timecut5.pwa import ProjectionSupportPrefilter

SCHEMA='hiroute.dev_cohort.v1'
METHODS=('flat','hier')
INNER_ARM='support_on'
METHOD_POLICY=dict(schema='hiroute.dev_cohort_method.v1',
    flat_entry='_solve_problem',hier_entry='_solve_hierarchical_problem',
    flat_bound=POLICY_SCHEMA,hier_bound=projection.BOUND_POLICY,envelope_policy=envelope.ENVELOPE_POLICY,
    remaining_charge_family='max_existing_ALT_prefix_and_whole_route_at_next_stop',
    strict_pruning_owned_by_engine=True,original_action_coverage=True,
    durable_method_tag_required=True,canonical_terminal_payload_shared=True)


def shared_configuration(envelope_enabled):
    if type(envelope_enabled) is not bool:raise ValueError('Explicit common envelope boolean required')
    return dict(projection.CONFIGS[INNER_ARM],envelope_sweep=envelope_enabled)


def normalize_result(method,solved):
    """Normalize the real method return types, including unattained infima."""
    from timecut5.bounded import BoundedResult
    from timecut5.hierarchy import HierarchyResult
    if method=='flat' and isinstance(solved,BoundedResult):return solved
    if method=='hier' and isinstance(solved,HierarchyResult):return solved.bounded
    raise ValueError('Exact result type does not match declared method')


class CohortProgress(envelope.EnvelopeProgress):
    def __init__(self,*args,singleton=None,**kwargs):
        self.singleton=singleton
        super().__init__(*args,**kwargs)

    def metrics(self):
        self.state['singleton_bound_statistics']=None if self.singleton is None else self.singleton.statistics_snapshot()
        return super().metrics()


class CohortDomain(projection.ProjectionSupportDomain):
    def __init__(self,*,method,envelope_enabled,case_binding,**kwargs):
        if method not in METHODS:raise ValueError('Unknown cohort method')
        self.method=method
        self.shared_configuration=shared_configuration(envelope_enabled)
        self.case_binding=json.loads(base.canonical(case_binding))
        self._method_binding=base.canonical([method,self.shared_configuration,self.case_binding])
        super().__init__(arm=INNER_ARM,**kwargs)

    def check(self):
        super().check()
        if (self.arm!=INNER_ARM or self.method not in METHODS or
            base.canonical([self.method,self.shared_configuration,self.case_binding])!=self._method_binding):
            raise ValueError('Cohort method/configuration/case binding changed')

    def durable_binding(self,seed):
        inner=super().durable_binding(seed)
        policy=[SCHEMA,self.method,self.shared_configuration,self.case_binding,METHOD_POLICY,self.manifest_binding]
        return dict(domain_sha256=base.digest([inner['domain_sha256'],*policy]),
            source_sha256=dict(inner['source_sha256'],cohort_method=base.digest(policy)))

    def make_bound(self,context,strategy):
        region=super().make_bound(context,'indexed')
        self._singleton=None
        if self.method=='flat':
            self._singleton=RemainingChargeSingletonBound(region.original,self._search_problem,runtime=region.runtime)
        receipt=method_admission(self.manifest_binding,self.method,self.shared_configuration,self.case_binding,
            base.file_hash(self._output/'remaining_charge_admission.json'))
        (self._output/'method_admission.json').write_bytes(base.canonical(receipt))
        return region

    def solve_exact(self,problem,witness,key,bound,store):
        from timecut5.bounded import _solve_problem
        from timecut5.hierarchy import _solve_hierarchical_problem
        from timecut5.pwa import reduce_frontier_skyline
        binding=self.durable_binding(self._seed)
        prefilter=ProjectionSupportPrefilter(enabled=True)
        sweep=EnvelopeSweep(enabled=self.shared_configuration['envelope_sweep'])
        observer=CohortProgress(self._output/'progress',query_sha256=base.digest(json.loads(self.query_bytes)),
            domain_sha256=binding['domain_sha256'],source_sha256=binding['source_sha256'],provider=self._search_provider,
            projection_support=prefilter,envelope_sweep=sweep,singleton=self._singleton)
        observer.state.update(profile_schema=projection.SCHEMA,arm=INNER_ARM,configuration=self.config,
            manifest_binding=self.manifest_binding,candidate_count=len(self.sites),Hmax=self._seed.max_depth,
            remaining_charge_activation_wall_ns=self._activation_wall_ns,
            remaining_charge_admission_sha256=base.file_hash(self._output/'remaining_charge_admission.json'),
            remaining_charge_activation_diagnostic=self._activation_receipt.get('diagnostic'),
            remaining_charge_seed_bound=self._activation_receipt.get('seed_bound'),
            time_policy=projection.TIME_POLICIES[INNER_ARM],time_admission=self._activation_receipt['time_admission'],
            projection_support_policy=projection.SUPPORT_POLICY,projection_support_enabled=True,
            cohort_schema=SCHEMA,method=self.method,shared_configuration=self.shared_configuration,
            case_binding_sha256=base.digest(self.case_binding),method_policy=METHOD_POLICY,
            method_admission_sha256=base.file_hash(self._output/'method_admission.json'))
        observer.state['timings']['durable_incumbent_callback']=dict(calls=0,wall_ns=0,cpu_ns=0,errors=0)
        @operation('durable_incumbent_callback')
        def observed_store(candidate,candidate_key):
            with EnvelopeSweep(enabled=False),ProjectionSupportPrefilter(enabled=False):
                result=store(candidate,candidate_key)
            bound.current_upper=min(bound.current_upper,candidate_key[0])
            return result
        bound.current_upper=key[0]
        def checkpoint(depth,layer,terminals,incumbent,counters):
            values=dict(engine_checkpoint_depth=depth,method=self.method)
            if self.method=='hier':values.update(actual_pruned_regions_at_last_checkpoint=counters[6],actual_equality_nodes_at_last_checkpoint=counters[7])
            event('cohort_engine_checkpoint',**values)
        try:
            with sweep,prefilter:
                if self.method=='flat':
                    solved=_solve_problem(problem,True,reducer=reduce_frontier_skyline,verified_primary_upper=key[0],
                        singleton_bound=self._singleton.singleton_bound,incumbent_hook=observed_store,
                        progress_hook=observer,checkpoint_hook=checkpoint)
                else:
                    solved=_solve_hierarchical_problem(problem,True,self.tree,witness,reducer=reduce_frontier_skyline,
                        verified_primary_upper=key[0],bound_provider=bound,incumbent_hook=observed_store,
                        progress_hook=observer,checkpoint_hook=checkpoint)
            self._actual_engine_prunes=solved.pruned_regions if self.method=='hier' else None
            return normalize_result(self.method,solved)
        finally:
            self._envelope_statistics=asdict(sweep.snapshot())
            self._support_statistics=asdict(prefilter.snapshot())
            self._singleton_statistics=None if self._singleton is None else self._singleton.statistics_snapshot()
            self._observer_status=dict(io_error=observer.state['io_error'],heartbeat_error=observer.state.get('heartbeat_error'),
                status=observer.state['status'],persist_attempts=observer.state['persist_attempts'])

    def recover_durable(self,seed,path):
        # The portable binding includes method, but the record's explicit tag
        # must also match. Recheck bytes after the independent full replay.
        path=Path(path);raw=path.read_bytes();record=json.loads(raw)
        if record.get('payload',{}).get('method')!=self.method:raise ValueError('Durable method tag differs')
        result=super().recover_durable(seed,path)
        if path.read_bytes()!=raw:raise ValueError('Durable record changed during fresh replay')
        return dict(result,method=self.method,case_binding_sha256=base.digest(self.case_binding))

    def run_arm(self,strategy,seed,output,*,search_seconds=None,external_phase=False):
        """Reviewed lifecycle with explicit method tags and normalized returns."""
        from timecut5.bounded import _replay_problem
        from timecut5.durable_incumbent import AtomicIncumbentStore
        from timecut5.provenance import primitive
        self.check()
        if strategy!=self.method:raise ValueError('Requested cohort method differs')
        self._seed=seed;self._output=Path(output);output=self._output;output.mkdir(parents=True,exist_ok=False)
        started=time.monotonic_ns();witness=self.validate_seed(seed);binding=self.durable_binding(seed)
        with ExitStack() as stack:
            verifier=None
            def verification_problem():
                nonlocal verifier
                verifier=self.context('durable_verification')
                return self.problem(verifier,seed.max_depth)
            durable=AtomicIncumbentStore(output/'incumbent.json',method=self.method,problem_factory=verification_problem,binding_supplier=lambda:binding)
            def store(witness,key):
                nonlocal verifier
                try:self.check();durable(witness,key)
                finally:
                    if verifier is not None:verifier.close();verifier=None
            context=stack.enter_context(self.context('search'));problem=self.problem(context,seed.max_depth)
            key=_replay_problem(problem,witness)
            if base.canonical(primitive(key))!=seed.key_bytes:raise ValueError('Search seed replay differs')
            store(witness,key);bound=self.make_bound(context,'indexed');setup_ns=time.monotonic_ns()-started
            if external_phase:
                if search_seconds is not None:raise ValueError('External phase cannot combine with Python timer')
                from experiments.mechanism_recovery_v1.supervisor import publish_phase_entry
                publish_phase_entry()
            search_start=time.monotonic_ns()
            class SearchWindowExpired(Exception):pass
            def expire(signum,frame):raise SearchWindowExpired('Exact search window expired')
            previous=None
            if search_seconds is not None:
                if type(search_seconds) not in (int,float) or search_seconds<=0:raise ValueError('Positive search window required')
                if signal.getitimer(signal.ITIMER_REAL)[0]:raise ValueError('Search timer already owned')
                previous=signal.signal(signal.SIGALRM,expire);signal.setitimer(signal.ITIMER_REAL,search_seconds)
            solved=None
            try:solved=self.solve_exact(problem,witness,key,bound,store)
            except SearchWindowExpired:pass
            finally:
                if previous is not None:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)
            search_ns=time.monotonic_ns()-search_start
            if solved is not None:
                terminal=solved.result
                if terminal.witness is not None:store(terminal.witness,terminal.key)
                if terminal.status=='attained_optimum' and (terminal.witness is None or terminal.key!=durable.best_key):
                    raise ValueError('Exact terminal contradicts durable incumbent')
                if terminal.status not in ('attained_optimum','infimum_unattained'):raise ValueError('Feasible seed contradicts terminal status')
            recovered_key=durable.best_key
            if not external_phase:
                from timecut5.durable_incumbent import load_verified
                try:_,recovered_key=load_verified(output/'incumbent.json',problem_factory=verification_problem,binding_supplier=lambda:binding)
                finally:
                    if verifier is not None:verifier.close();verifier=None
            if recovered_key>key:raise ValueError('Durable terminal is worse than common seed')
            report=dict(schema=SCHEMA,strategy=self.method,method=self.method,status=solved.result.status if solved is not None else 'timeout_feasible_only',
                result=primitive(solved.canonical()) if solved is not None else None,accepted_key=primitive(recovered_key),
                feasible_improvement=recovered_key<key,optimality_claim=not external_phase and solved is not None and solved.result.status=='attained_optimum',
                pending_independent_terminal_verification=external_phase,setup_wall_ns=setup_ns,search_wall_ns=search_ns,total_arm_wall_ns=time.monotonic_ns()-started,
                shared_native_build_wall_ns=self.build_wall_ns,native_sha256=self.native_sha256,seed_key=json.loads(seed.key_bytes),Hmax=seed.max_depth,
                tree_sha256=self.tree_sha256,durable_writes=durable.writes,alt_member_reads=bound.alt_member_reads,
                energy_search_only=True,full_routing=False,cold_os_cache_claim=False,
                inner_arm=INNER_ARM,configuration=self.config,shared_configuration=self.shared_configuration,method_policy=METHOD_POLICY,
                case_binding_sha256=base.digest(self.case_binding),manifest_binding=self.manifest_binding,
                method_admission_sha256=base.file_hash(output/'method_admission.json'),
                time_policy=projection.TIME_POLICIES[INNER_ARM],projection_support_policy=projection.SUPPORT_POLICY,
                projection_support_statistics=self._support_statistics,envelope_sweep_statistics=self._envelope_statistics,
                singleton_bound_statistics=self._singleton_statistics,remaining_charge_counters=dict(bound.counters),
                actual_engine_pruned_regions=getattr(self,'_actual_engine_prunes',None),observer=self._observer_status,
                remaining_charge_activation_wall_ns=self._activation_wall_ns,
                remaining_charge_admission_sha256=base.file_hash(output/'remaining_charge_admission.json'),progress_sha256=base.file_hash(output/'progress/progress.json'))
            (output/'result.json').write_bytes(base.canonical(report));return report


def method_admission(manifest_binding,method,configuration,case_binding,inner_sha):
    return dict(schema=SCHEMA,method=method,shared_configuration=configuration,method_policy=METHOD_POLICY,
        case_binding_sha256=base.digest(case_binding),manifest_binding=manifest_binding,
        inner_experiment_schema=projection.SCHEMA,inner_arm=INNER_ARM,
        inner_configuration=projection.CONFIGS[INNER_ARM],inner_admission_sha256=inner_sha)
