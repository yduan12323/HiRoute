"""Hand-authored toy runtime inputs, injected only by explicit test decorators.

No graph/download artifacts or real pool records are embedded here. Repeating a
simple toy site shape preserves the 32/128 planning boundary tests without
turning production's missing-input behavior into a synthetic fallback.
"""
import copy
from functools import wraps
from unittest.mock import patch
from experiments.mechanism_recovery_v1 import run as base
from timecut5.real_adapter import site_catalog_digest
from timecut5.real_legs import RealSite


def toy_prefix(spec):
    return [dict(site_id=f'toy-site-{i}', anchor_id=f'toy-anchor-{i}', effects=['C', 'S', 'CS'])
            for i in range(spec['candidate_count'])]


def toy_binding(spec):
    prefix = toy_prefix(spec)
    sites = {s['site_id']: RealSite(s['site_id'], s['anchor_id'], tuple(s['effects'])) for s in prefix}
    query = dict(case_id=spec['case_id'].split('_n')[0],
                 origin='toy-origin', destination='toy-destination', H_ref=4,
                 start_time_s='0', initial_energy_kwh='2', capacity_kwh='10', minimum_energy_kwh='0',
                 reserve_kwh='0', overhead_s='1', lambda_stop_s='1', consumption_kwh_per_m='1',
                 charging_segments=[['0', '10', '1', '0']], schedule=dict(a='0', b='100', D='1'),
                 hierarchy_sha256=spec['original_binding']['query']['hierarchy_sha256'], sparse_domain_sha256='d'*64)
    return dict(query=query, query_sha256=base.digest(query), candidate_site_ids=list(sites),
                candidate_sha256=base.digest(sorted(sites)), site_catalog_sha256=site_catalog_digest(sites),
                anchor_catalog_sha256=base.digest(['toy anchors']), sparse_domain_sha256='d'*64)


def toy_spec(spec):
    result = copy.deepcopy(spec)
    binding = toy_binding(spec)
    result.pop('original_pool_prefix', None)
    result['original_pool_prefix_sha256'] = base.digest(toy_prefix(spec))
    binding['candidate_site_ids_sha256'] = base.digest(binding.pop('candidate_site_ids'))
    result['original_binding'] = binding
    return result


def synthetic_cohort(test):
    @wraps(test)
    def run(*args, **kwargs):
        from experiments.dev_cohort_v1 import run as cohort
        plan = copy.deepcopy(cohort.COHORT)
        plan['cases'] = [toy_spec(s) for s in plan['cases']]
        with patch.object(cohort, 'COHORT', plan), patch.object(cohort, 'SPECS', {s['case_id']: s for s in plan['cases']}):
            return test(*args, **kwargs)
    return run


def synthetic_tranche(test):
    @wraps(test)
    def run(*args, **kwargs):
        from experiments.dev_coverage_tranche_v1 import bindings, run as gate
        plan = copy.deepcopy(bindings.PLAN)
        for case in plan['cases']:
            case['domains'] = [toy_spec(s) for s in case['domains']]
        with patch.object(bindings, 'PLAN', plan), patch.object(gate, 'PLAN', plan):
            return test(*args, **kwargs)
    return run
