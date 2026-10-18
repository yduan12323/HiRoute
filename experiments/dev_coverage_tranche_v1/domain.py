"""Explicit FLAT/HIER dispatch with the same pending/post-service policy.

This experimental policy does not redefine the historical product-order
certificate. The engine supplies whole next-departure layers; the reducer's
own admission and recorder fallbacks remain mandatory.
"""
from dataclasses import asdict
import json
from pathlib import Path

from experiments.mechanism_recovery_v1 import run as base
from experiments.projection_support_gate_v1 import run as projection
from experiments.dev_cohort_v1 import domain as cohort
from experiments.analytic_charge_gate_v1.domain import ANALYTIC_POLICY
from timecut5.analytic_charge import AnalyticCharge
from timecut5.envelope_sweep import EnvelopeSweep
from timecut5.pwa import ProjectionSupportPrefilter
from timecut5.exact_progress import operation,event

SCHEMA='hiroute.dev_coverage_tranche.v1'
METHODS=('flat','hier')
ARMS=METHODS
INNER_ARM=cohort.INNER_ARM
METHOD_POLICY=cohort.METHOD_POLICY
EXACT_PHASE_SECONDS=1200
REVIEW_STATUS='approved_independent_dev_coverage_tranche_B_review'
CURRENT_PAIR_STATUS='root_tranche_A_terminal_reviewed'
SOURCE_BASE_COMMIT='43e83b57429dc06c18763339f06444bd5b40f44d'
from experiments.pending_window_completion_v1.domain import (
    PENDING_WINDOW_POLICY, POST_SERVICE_POLICY, historical_operators, PendingWindowProgress)
COMPLETION_POLICY=dict(schema='hiroute.dev_coverage_tranche_policy.v1',
    purpose='matched_bound_family_FLAT_HIER_known_DEV_comparison',exact_phase_seconds=EXACT_PHASE_SECONDS,
    search_worker_wall_seconds=1500,search_worker_cpu_seconds=1500,
    includes_postsolver_finalization_until_worker_exit=True,
    same_budget_method_comparison=True,fixed_order=list(METHODS),
    physical_common_seed_policy='same_fresh_original_proposal_seed_no_improved_seed_or_replacement',
    standalone_full_cost='each_method_charged_full_fresh_shared_preparation_plus_own_search_and_replay',
    historical_treatment_completion_is_paired_result=False,
    supersedes_historical_results=False,automatic_retry=False,
    convex_charge_count_runtime=False,operator_compaction_candidate=False,
    lazy_native_allocation_backend=False,service_deadline_screen=False,
    runtime_variant='historical_remaining_charge_runtime_v1',
    performance_interpretation='descriptive_fixed_order_shared_host_not_isolated_hierarchy_effect',
    bound_comparison='same_certificate_bound_family_with_method_specific_queue_semantics',
    comparison='canonical_status_full_key_or_proper_unattained_components',
    identical_witness_bytes_required=False)
CONFIGS={method:dict(method=method,inner_arm=INNER_ARM,
    shared_configuration=cohort.shared_configuration(False),analytic_charge=True,
    post_service_dominance=True,pending_window_dominance=True,
    convex_charge_count_runtime=False,operator_compaction_candidate=False,
    lazy_native_allocation_backend=False,service_deadline_screen=False) for method in METHODS}


class ScheduledMethodDomain(cohort.CohortDomain):
    def __init__(self,*,arm,**kwargs):
        if arm not in ARMS:raise ValueError('Unknown pending-window arm')
        self.outer_arm=arm
        self.outer_config=json.loads(base.canonical(CONFIGS[arm]))
        self._outer_binding=base.canonical([arm,self.outer_config])
        super().__init__(method=arm,envelope_enabled=False,**kwargs)

    def check(self):
        super().check()
        if (self.method!=self.outer_arm or self.shared_configuration!=cohort.shared_configuration(False) or
            self.outer_arm not in ARMS or base.canonical([self.outer_arm,self.outer_config])!=self._outer_binding or
            base.canonical(self.outer_config)!=base.canonical(CONFIGS[self.outer_arm])):
            raise ValueError('Pending-window feature arm or fixed method policy changed')

    def durable_binding(self,seed):
        inner=super().durable_binding(seed)
        policy=[SCHEMA,self.outer_arm,self.outer_config,PENDING_WINDOW_POLICY,POST_SERVICE_POLICY,ANALYTIC_POLICY,COMPLETION_POLICY,self.manifest_binding]
        return dict(domain_sha256=base.digest([inner['domain_sha256'],*policy]),
            source_sha256=dict(inner['source_sha256'],pending_window_policy=base.digest(policy)))

    def make_bound(self,context,strategy):
        bound=super().make_bound(context,strategy)
        receipt=outer_admission(self.manifest_binding,self.outer_arm,
            base.file_hash(self._output/'method_admission.json'))
        (self._output/'pending_window_admission.json').write_bytes(base.canonical(receipt))
        return bound

    def solve_exact(self,problem,witness,key,bound,store):
        from timecut5.bounded import _solve_problem
        from timecut5.hierarchy import _solve_hierarchical_problem
        from timecut5.pending_window_dominance import VERSION,make_pending_window_reducer
        if VERSION!=PENDING_WINDOW_POLICY['reducer_version']:raise ValueError('Pending-window reducer version differs')
        binding=self.durable_binding(self._seed)
        prefilter=ProjectionSupportPrefilter(enabled=True)
        sweep=EnvelopeSweep(enabled=False)
        analytic=AnalyticCharge(enabled=True)
        reducer=make_pending_window_reducer(problem,enabled=self.outer_config['pending_window_dominance'],
            post_service_enabled=self.outer_config['post_service_dominance'],
            completed_departure_layers=True,runtime=getattr(bound,'runtime',None))
        observer=PendingWindowProgress(self._output/'progress',query_sha256=base.digest(json.loads(self.query_bytes)),
            domain_sha256=binding['domain_sha256'],source_sha256=binding['source_sha256'],provider=self._search_provider,
            projection_support=prefilter,envelope_sweep=sweep,singleton=self._singleton,analytic_charge=analytic,pending_window=reducer)
        observer.state.update(profile_schema=projection.SCHEMA,arm=INNER_ARM,configuration=self.config,
            manifest_binding=self.manifest_binding,candidate_count=len(self.sites),Hmax=self._seed.max_depth,
            remaining_charge_activation_wall_ns=self._activation_wall_ns,
            remaining_charge_admission_sha256=base.file_hash(self._output/'remaining_charge_admission.json'),
            remaining_charge_activation_diagnostic=self._activation_receipt.get('diagnostic'),
            remaining_charge_seed_bound=self._activation_receipt.get('seed_bound'),
            time_policy=projection.TIME_POLICIES[INNER_ARM],time_admission=self._activation_receipt['time_admission'],
            projection_support_policy=projection.SUPPORT_POLICY,projection_support_enabled=True,
            cohort_schema=cohort.SCHEMA,method=self.method,shared_configuration=self.shared_configuration,
            case_binding_sha256=base.digest(self.case_binding),method_policy=METHOD_POLICY,
            method_admission_sha256=base.file_hash(self._output/'method_admission.json'))
        observer.state.update(pending_window_schema=SCHEMA,pending_window_arm=self.outer_arm,pending_window_configuration=self.outer_config,
            pending_window_policy=PENDING_WINDOW_POLICY,post_service_policy=POST_SERVICE_POLICY,analytic_charge_policy=ANALYTIC_POLICY,completion_policy=COMPLETION_POLICY,
            pending_window_admission_sha256=base.file_hash(self._output/'pending_window_admission.json'))
        observer.state['timings']['durable_incumbent_callback']=dict(calls=0,wall_ns=0,cpu_ns=0,errors=0)
        @operation('durable_incumbent_callback')
        def observed_store(candidate,candidate_key):
            with historical_operators():
                result=store(candidate,candidate_key)
            bound.current_upper=min(bound.current_upper,candidate_key[0])
            return result
        bound.current_upper=key[0]
        def checkpoint(depth,layer,terminals,incumbent,counters):
            values=dict(engine_checkpoint_depth=depth,method=self.method)
            if self.method=='hier':values.update(actual_pruned_regions_at_last_checkpoint=counters[6],actual_equality_nodes_at_last_checkpoint=counters[7])
            event('cohort_engine_checkpoint',**values)
        try:
            with sweep,prefilter,analytic:
                if self.method=='flat':
                    solved=_solve_problem(problem,True,reducer=reducer,verified_primary_upper=key[0],
                        singleton_bound=self._singleton.singleton_bound,incumbent_hook=observed_store,
                        progress_hook=observer,checkpoint_hook=checkpoint)
                else:
                    solved=_solve_hierarchical_problem(problem,True,self.tree,witness,reducer=reducer,
                        verified_primary_upper=key[0],bound_provider=bound,incumbent_hook=observed_store,
                        progress_hook=observer,checkpoint_hook=checkpoint)
            self._actual_engine_prunes=solved.pruned_regions if self.method=='hier' else None
            return cohort.normalize_result(self.method,solved)
        finally:
            self._analytic_statistics=asdict(analytic.snapshot())
            self._post_service_statistics=asdict(reducer.post_service_snapshot())
            self._pending_window_statistics=asdict(reducer.snapshot())
            self._envelope_statistics=asdict(sweep.snapshot())
            self._support_statistics=asdict(prefilter.snapshot())
            self._singleton_statistics=None if self._singleton is None else self._singleton.statistics_snapshot()
            self._observer_status=dict(io_error=observer.state['io_error'],heartbeat_error=observer.state.get('heartbeat_error'),
                status=observer.state['status'],persist_attempts=observer.state['persist_attempts'])

    def freeze_seed(self,witness):
        with historical_operators():return super().freeze_seed(witness)

    def validate_seed(self,seed):
        with historical_operators():return super().validate_seed(seed)

    def recover_durable(self,seed,path):
        self.check()
        with historical_operators():result=super().recover_durable(seed,path)
        return dict(result,pending_window_schema=SCHEMA,pending_window_arm=self.outer_arm,
            pending_window_configuration=self.outer_config,pending_window_policy=PENDING_WINDOW_POLICY,post_service_policy=POST_SERVICE_POLICY,
            analytic_charge_policy=ANALYTIC_POLICY,completion_policy=COMPLETION_POLICY)

    def run_arm(self,strategy,seed,output,**kwargs):
        self.check()
        if strategy!=self.outer_arm:raise ValueError('Requested pending-window arm differs')
        # Generation/seed checks, final store and fresh verification stay on
        # historical operators. Only solve_exact installs the selected policy.
        with historical_operators():result=super().run_arm(self.method,seed,output,**kwargs)
        result.update(schema=SCHEMA,pending_window_schema=SCHEMA,strategy=self.outer_arm,method=self.method,
            pending_window_arm=self.outer_arm,pending_window_configuration=self.outer_config,pending_window_policy=PENDING_WINDOW_POLICY,post_service_policy=POST_SERVICE_POLICY,
            analytic_charge_policy=ANALYTIC_POLICY,completion_policy=COMPLETION_POLICY,post_service_statistics=self._post_service_statistics,
            pending_window_statistics=self._pending_window_statistics,
            pending_window_admission_sha256=base.file_hash(Path(output)/'pending_window_admission.json'),
            analytic_charge_statistics=self._analytic_statistics)
        (Path(output)/'result.json').write_bytes(base.canonical(result))
        return result


def outer_admission(manifest_binding,arm,method_sha):
    if arm not in ARMS:raise ValueError('Unknown pending-window arm')
    return dict(schema=SCHEMA,arm=arm,method=arm,configuration=CONFIGS[arm],pending_window_policy=PENDING_WINDOW_POLICY,post_service_policy=POST_SERVICE_POLICY,
        analytic_charge_policy=ANALYTIC_POLICY,completion_policy=COMPLETION_POLICY,
        exact_phase_seconds=EXACT_PHASE_SECONDS,manifest_binding=manifest_binding,
        inner_experiment_schema=cohort.SCHEMA,inner_method=arm,method_admission_sha256=method_sha)
