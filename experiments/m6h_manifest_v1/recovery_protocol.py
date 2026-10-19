"""Portable disclosed-history validation contract, held before real input access.

This is a new configuration, not a retrospective independent holdout claim.
Release requires a separately reviewed source change; no argument enables it.
"""
from copy import deepcopy
from .contract import digest, plan
from .resources import ContinuationBudget, conservative_transition_debit

MODE = 'disclosed_recovered_history_new_map_validation'
DEADLINE = '2026-10-20T10:19:43.011913Z'
ACTIVE_SINCE = '2026-10-19T10:05:00Z'
CARRIED_CPU = 70893
CPU_CAPACITY = 9

PROTOCOL = {
    'schema': 'hiroute.m6h.disclosed_recovery_protocol.v1',
    'mode': MODE,
    'purpose': 'new_map_correctness_and_performance_validation',
    'strict_independent_holdout_claim': False,
    'release_control': 'separate_source_review_and_explicit_go_required',
    'cpu_limit_seconds': 144000,
    'absolute_deadline_utc': DEADLINE,
    'budget_history': {
        'conditional_carried_cpu_bound_seconds': CARRIED_CPU,
        'bound_as_of_utc': '2026-10-19T04:45:00Z',
        'historical_base_seconds': 28773,
        'additional_active_windows': [
            {'start_utc':'2026-10-19T03:07:00Z','end_utc':'2026-10-19T04:23:00Z','cpu_bound_seconds':41040},
            {'start_utc':'2026-10-19T04:43:00Z','end_utc':'2026-10-19T04:45:00Z','cpu_bound_seconds':1080}],
        'provenance':'parent_tool_and_worker_history_missing_original_receipts',
        'idle_until_utc': ACTIVE_SINCE,
        'active_conservative_cpu_capacity': CPU_CAPACITY,
        'prior_17413_subtotal_already_included': True,
        'historical_infrastructure_attempts': 3,
        'historical_numerical_slots': 0,
        'historical_attempt_receipts': 'lost_unrecoverable_evidence_gap',
        'bound_is_measured_cpu': False,
    },
    'design': plan(6),
    'physical_model': {
        'capacity_kwh': '60', 'initial_energy_kwh': ['18', '228/5'],
        'reserve_kwh': '6', 'consumption_kwh_per_m': '1/6250',
        'overhead_s': '300', 'lambda_stop_s': '600', 'D_s': '2700',
        'window_direct_time_ratios': ['2/5', '7/10'],
        'depth': 'floor(J_original_seed/900)',
        'candidate_pool': 'original_capability_balanced_128_nested_prefixes',
        'seed_repair': False, 'depth_clipping': False,
    },
    'failure_policy': 'retain_fixed_slots_no_replacement_no_favorable_retry',
    'road_policy': 'exact_street_lamp_excluded_yes_only_original_closed_building_yes_and_amenity_shelter',
    'production_source_entries': 97,
    'production_src_sha256': 'fe1232d4061ab43f92d320ee3937222e88c3e1eead054a53cdd49a6c2ac39fbc',
    'historical_source_guards': 'unchanged',
}


def protocol():
    return deepcopy(PROTOCOL)


def validate_protocol(value):
    if value != PROTOCOL:
        raise ValueError('Disclosed recovery protocol differs from frozen design')
    return digest(value)


def make_continuation_budget(*, transition_utc):
    """Charge the entire active interval once, then metered owner descendants.

    The existing ContinuationBudget also covers transition-to-construction delay
    at the same conservative capacity. No nested receipt totals are added.
    This function is accounting-only and grants no source/selection access.
    """
    debit = conservative_transition_debit(prior_debit=CARRIED_CPU,
        active_since_utc=ACTIVE_SINCE, transition_utc=transition_utc,
        cpu_capacity=CPU_CAPACITY)
    return ContinuationBudget(carried_cpu_seconds=debit,deadline_utc=DEADLINE,
        transition_utc=transition_utc,transition_cpu_capacity=CPU_CAPACITY)


def validate_recovery_binding(binding, registry):
    from experiments.m6h_selection_v1.rules import validate_recovered_exposures
    validate_recovered_exposures(registry, binding)
    return binding


def launch_recovery(*args, **kwargs):
    # Deliberately before inspection of any user-supplied paths or objects.
    from . import recovery_runtime
    if recovery_runtime.ROOT_RELEASE!='reviewed_disclosed_recovery_v1':
        raise PermissionError('Disclosed validation held for root release')
    from .recovery_runner import supervise
    return supervise(*args, **kwargs)
