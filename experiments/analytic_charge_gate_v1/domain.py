"""Isolated HIER lifecycle with one explicitly bound C-operator switch."""
from contextlib import contextmanager
from dataclasses import asdict
import json
from pathlib import Path

from experiments.mechanism_recovery_v1 import run as base
from experiments.projection_support_gate_v1 import run as projection
from experiments.dev_cohort_v1 import domain as cohort
from timecut5.analytic_charge import AnalyticCharge
from timecut5.envelope_sweep import EnvelopeSweep
from timecut5.pwa import ProjectionSupportPrefilter
from timecut5.exact_progress import operation,event

SCHEMA='hiroute.analytic_charge_gate.v1'
CASE='OD02_energy_only_soc3_10'
METHOD='hier'
INNER_ARM=cohort.INNER_ARM
METHOD_POLICY=cohort.METHOD_POLICY
ARMS=('analytic_off','analytic_on')
EXACT_PHASE_SECONDS=240
ORIGINAL_HMAX=33
ANALYTIC_POLICY=dict(schema='hiroute.analytic_charge.v1',operator='C_only',
    scope='exact_search_excluding_independent_incumbent_replay',
    boundary='historical_redundant_FME_fan_and_row_order',lift='historical_constrained_midpoints',
    recorder_fallback='historical_generic_projection',default_absent_unchanged=True,
    counter_semantics='C_pair_and_build_entries_including_empty_results')
CONFIGS={arm:dict(method=METHOD,inner_arm=INNER_ARM,
    shared_configuration=cohort.shared_configuration(False),analytic_charge=arm=='analytic_on') for arm in ARMS}


@contextmanager
def historical_operators():
    """Fresh disabled contexts also isolate counts from the search observer."""
    with AnalyticCharge(enabled=False),EnvelopeSweep(enabled=False),ProjectionSupportPrefilter(enabled=False):
        yield


class AnalyticProgress(cohort.CohortProgress):
    def __init__(self,*args,analytic_charge,**kwargs):
        self.analytic_charge=analytic_charge
        super().__init__(*args,**kwargs)

    def metrics(self):
        # Detached scalar fields; live multi-field samples are nontransactional.
        self.state['analytic_charge_statistics']=asdict(self.analytic_charge.snapshot())
        return super().metrics()


class AnalyticDomain(cohort.CohortDomain):
    def __init__(self,*,arm,**kwargs):
        if arm not in ARMS:raise ValueError('Unknown analytic arm')
        self.outer_arm=arm
        self.outer_config=json.loads(base.canonical(CONFIGS[arm]))
        self._outer_binding=base.canonical([arm,self.outer_config])
        super().__init__(method=METHOD,envelope_enabled=False,**kwargs)

    def check(self):
        super().check()
        if (self.method!=METHOD or self.shared_configuration!=cohort.shared_configuration(False) or
            self.outer_arm not in ARMS or base.canonical([self.outer_arm,self.outer_config])!=self._outer_binding or
            base.canonical(self.outer_config)!=base.canonical(CONFIGS[self.outer_arm])):
            raise ValueError('Analytic outer arm or fixed HIER policy changed')

    def durable_binding(self,seed):
        inner=super().durable_binding(seed)
        policy=[SCHEMA,self.outer_arm,self.outer_config,ANALYTIC_POLICY,self.manifest_binding]
        return dict(domain_sha256=base.digest([inner['domain_sha256'],*policy]),
            source_sha256=dict(inner['source_sha256'],analytic_policy=base.digest(policy)))

    def make_bound(self,context,strategy):
        bound=super().make_bound(context,strategy)
        receipt=outer_admission(self.manifest_binding,self.outer_arm,
            base.file_hash(self._output/'method_admission.json'))
        (self._output/'analytic_admission.json').write_bytes(base.canonical(receipt))
        return bound

    def solve_exact(self,problem,witness,key,bound,store):
        from timecut5.hierarchy import _solve_hierarchical_problem
        from timecut5.pwa import reduce_frontier_skyline
        binding=self.durable_binding(self._seed)
        prefilter=ProjectionSupportPrefilter(enabled=True)
        sweep=EnvelopeSweep(enabled=False)
        analytic=AnalyticCharge(enabled=self.outer_config['analytic_charge'])
        observer=AnalyticProgress(self._output/'progress',query_sha256=base.digest(json.loads(self.query_bytes)),
            domain_sha256=binding['domain_sha256'],source_sha256=binding['source_sha256'],provider=self._search_provider,
            projection_support=prefilter,envelope_sweep=sweep,singleton=None,analytic_charge=analytic)
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
        observer.state.update(analytic_schema=SCHEMA,analytic_arm=self.outer_arm,analytic_configuration=self.outer_config,
            analytic_policy=ANALYTIC_POLICY,analytic_admission_sha256=base.file_hash(self._output/'analytic_admission.json'))
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
                solved=_solve_hierarchical_problem(problem,True,self.tree,witness,reducer=reduce_frontier_skyline,
                    verified_primary_upper=key[0],bound_provider=bound,incumbent_hook=observed_store,
                    progress_hook=observer,checkpoint_hook=checkpoint)
            self._actual_engine_prunes=solved.pruned_regions
            return cohort.normalize_result(METHOD,solved)
        finally:
            self._analytic_statistics=asdict(analytic.snapshot())
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
        return dict(result,analytic_schema=SCHEMA,analytic_arm=self.outer_arm,
            analytic_configuration=self.outer_config,analytic_policy=ANALYTIC_POLICY)

    def run_arm(self,strategy,seed,output,**kwargs):
        self.check()
        if strategy!=self.outer_arm:raise ValueError('Requested analytic arm differs')
        # Generation/seed checks, final store and fresh verification stay on
        # historical operators. Only solve_exact installs the selected policy.
        with historical_operators():result=super().run_arm(METHOD,seed,output,**kwargs)
        result.update(schema=SCHEMA,strategy=self.outer_arm,method=METHOD,
            analytic_arm=self.outer_arm,analytic_configuration=self.outer_config,analytic_policy=ANALYTIC_POLICY,
            analytic_admission_sha256=base.file_hash(Path(output)/'analytic_admission.json'),
            analytic_charge_statistics=self._analytic_statistics)
        (Path(output)/'result.json').write_bytes(base.canonical(result))
        return result


def outer_admission(manifest_binding,arm,method_sha):
    return dict(schema=SCHEMA,arm=arm,method=METHOD,configuration=CONFIGS[arm],analytic_policy=ANALYTIC_POLICY,
        exact_phase_seconds=EXACT_PHASE_SECONDS,manifest_binding=manifest_binding,
        inner_experiment_schema=cohort.SCHEMA,inner_method=METHOD,method_admission_sha256=method_sha)
