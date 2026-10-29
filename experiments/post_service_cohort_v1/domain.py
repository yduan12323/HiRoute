"""Method-aware matched lifecycle with the completed-departure reducer enabled.

This experimental policy does not redefine the historical product-order
certificate. The engine supplies whole next-departure layers; the reducer's
own admission and recorder fallbacks remain mandatory.
"""
from contextlib import contextmanager
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

SCHEMA='hiroute.post_service_cohort.v1'
CASES=('OD02_energy_only_soc3_10','OD06_energy_and_scheduled_soc3_10')
METHODS=cohort.METHODS
INNER_ARM=cohort.INNER_ARM
METHOD_POLICY=cohort.METHOD_POLICY
ARMS=METHODS
EXACT_PHASE_SECONDS=600
ORIGINAL_HMAX={CASES[0]:33,CASES[1]:39}
REVIEW_STATUS='approved_independent_cohort_review'
BASELINE_SOURCE_COMMIT='d7a38c02f83058efe8e710989695407c5f2e9483'
COMPLETION_POLICY=dict(schema='hiroute.post_service_cohort_policy.v1',
    purpose='matched_exact_outcomes_and_scheduled_coverage',exact_phase_seconds=EXACT_PHASE_SECONDS,
    search_worker_wall_seconds=900,search_worker_cpu_seconds=900,
    includes_postsolver_finalization_until_worker_exit=True,
    same_budget_speedup_comparison=True,matched_control=True,
    supersedes_historical_240_timeouts=False,automatic_retry=False,
    convex_charge_count_runtime=False,operator_compaction_candidate=False,
    runtime_variant='historical_remaining_charge_runtime_v1',
    performance_interpretation='descriptive_shared_host_only',
    comparison='canonical_status_full_key_or_proper_unattained_components',
    identical_witness_bytes_required=False)
POST_SERVICE_POLICY=dict(schema='hiroute.post_service_objective_reducer.v1',
    reducer_version='post-service-total-cut-order-v1',
    scope='exact_search_completed_departure_layers_only',
    phase='remaining_schedule_equals_zero',
    state='identical_complete_physical_departure_State',
    objective='exact_common_continuation_lexicographic_objective',
    default_enabled=False,recorded_fallback='historical_reduce_frontier_skyline',
    inherited_family_fallback='historical_reduce_frontier_skyline',
    r_equals_one_fallback='historical_reduce_frontier_skyline',
    selected_parent_compaction='identical_original_parent_connected_energy_union_original_callback_retained',
    legacy_product_order_certificate_unchanged=True,
    counter_semantics='repeated_cell_candidate_visits_not_unique_prefixes')
CONFIGS={arm:dict(method=arm,inner_arm=INNER_ARM,
    shared_configuration=cohort.shared_configuration(False),analytic_charge=True,
    post_service_dominance=True,convex_charge_count_runtime=False,operator_compaction_candidate=False) for arm in ARMS}


@contextmanager
def historical_operators():
    """Fresh disabled contexts also isolate counts from the search observer."""
    with AnalyticCharge(enabled=False),EnvelopeSweep(enabled=False),ProjectionSupportPrefilter(enabled=False):
        yield


class PostServiceCohortProgress(cohort.CohortProgress):
    def __init__(self,*args,analytic_charge,post_service,**kwargs):
        self.analytic_charge=analytic_charge
        self.post_service=post_service
        super().__init__(*args,**kwargs)

    def metrics(self):
        # Detached scalar fields; live multi-field samples are nontransactional.
        self.state['analytic_charge_statistics']=asdict(self.analytic_charge.snapshot())
        self.state['post_service_statistics']=asdict(self.post_service.snapshot())
        return super().metrics()


class PostServiceCohortDomain(cohort.CohortDomain):
    def __init__(self,*,arm,**kwargs):
        if arm not in ARMS:raise ValueError('Unknown post-service arm')
        self.outer_arm=arm
        self.outer_config=json.loads(base.canonical(CONFIGS[arm]))
        self._outer_binding=base.canonical([arm,self.outer_config])
        super().__init__(method=arm,envelope_enabled=False,**kwargs)

    def check(self):
        super().check()
        if (self.method!=self.outer_arm or self.shared_configuration!=cohort.shared_configuration(False) or
            self.outer_arm not in ARMS or base.canonical([self.outer_arm,self.outer_config])!=self._outer_binding or
            base.canonical(self.outer_config)!=base.canonical(CONFIGS[self.outer_arm])):
            raise ValueError('Post-service outer arm or fixed matched method policy changed')

    def durable_binding(self,seed):
        inner=super().durable_binding(seed)
        policy=[SCHEMA,self.outer_arm,self.outer_config,POST_SERVICE_POLICY,ANALYTIC_POLICY,COMPLETION_POLICY,self.manifest_binding]
        return dict(domain_sha256=base.digest([inner['domain_sha256'],*policy]),
            source_sha256=dict(inner['source_sha256'],post_service_policy=base.digest(policy)))

    def make_bound(self,context,strategy):
        bound=super().make_bound(context,strategy)
        receipt=outer_admission(self.manifest_binding,self.outer_arm,
            base.file_hash(self._output/'method_admission.json'))
        (self._output/'post_service_cohort_admission.json').write_bytes(base.canonical(receipt))
        return bound

    def solve_exact(self,problem,witness,key,bound,store):
        from timecut5.hierarchy import _solve_hierarchical_problem
        from timecut5.bounded import _solve_problem
        from timecut5.post_service_dominance import VERSION,make_post_service_reducer
        if VERSION!=POST_SERVICE_POLICY['reducer_version']:raise ValueError('Post-service reducer version differs')
        binding=self.durable_binding(self._seed)
        prefilter=ProjectionSupportPrefilter(enabled=True)
        sweep=EnvelopeSweep(enabled=False)
        analytic=AnalyticCharge(enabled=True)
        reducer=make_post_service_reducer(problem,enabled=self.outer_config['post_service_dominance'],
            completed_departure_layers=True,runtime=getattr(bound,'runtime',None))
        observer=PostServiceCohortProgress(self._output/'progress',query_sha256=base.digest(json.loads(self.query_bytes)),
            domain_sha256=binding['domain_sha256'],source_sha256=binding['source_sha256'],provider=self._search_provider,
            projection_support=prefilter,envelope_sweep=sweep,singleton=self._singleton,analytic_charge=analytic,post_service=reducer)
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
        observer.state.update(post_service_cohort_schema=SCHEMA,post_service_cohort_arm=self.outer_arm,post_service_cohort_configuration=self.outer_config,
            post_service_policy=POST_SERVICE_POLICY,analytic_charge_policy=ANALYTIC_POLICY,completion_policy=COMPLETION_POLICY,
            post_service_cohort_admission_sha256=base.file_hash(self._output/'post_service_cohort_admission.json'))
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
            self._post_service_statistics=asdict(reducer.snapshot())
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
        return dict(result,post_service_cohort_schema=SCHEMA,post_service_cohort_arm=self.outer_arm,
            post_service_cohort_configuration=self.outer_config,post_service_policy=POST_SERVICE_POLICY,
            analytic_charge_policy=ANALYTIC_POLICY,completion_policy=COMPLETION_POLICY)

    def run_arm(self,strategy,seed,output,**kwargs):
        self.check()
        if strategy!=self.outer_arm:raise ValueError('Requested post-service arm differs')
        # Generation/seed checks, final store and fresh verification stay on
        # historical operators. Only solve_exact installs the selected policy.
        with historical_operators():result=super().run_arm(self.method,seed,output,**kwargs)
        result.update(schema=SCHEMA,strategy=self.outer_arm,method=self.method,
            post_service_cohort_arm=self.outer_arm,post_service_cohort_configuration=self.outer_config,post_service_policy=POST_SERVICE_POLICY,
            analytic_charge_policy=ANALYTIC_POLICY,completion_policy=COMPLETION_POLICY,post_service_statistics=self._post_service_statistics,
            post_service_cohort_admission_sha256=base.file_hash(Path(output)/'post_service_cohort_admission.json'),
            analytic_charge_statistics=self._analytic_statistics)
        (Path(output)/'result.json').write_bytes(base.canonical(result))
        return result


def outer_admission(manifest_binding,arm,method_sha):
    if arm not in ARMS:raise ValueError('Unknown post-service arm')
    return dict(schema=SCHEMA,arm=arm,method=arm,configuration=CONFIGS[arm],post_service_policy=POST_SERVICE_POLICY,
        analytic_charge_policy=ANALYTIC_POLICY,completion_policy=COMPLETION_POLICY,
        exact_phase_seconds=EXACT_PHASE_SECONDS,manifest_binding=manifest_binding,
        inner_experiment_schema=cohort.SCHEMA,inner_method=arm,method_admission_sha256=method_sha)
