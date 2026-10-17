"""Closed, opt-in OD02 gate; reuses the verified recovery supervisor and runner."""
from __future__ import annotations
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from experiments.mechanism_recovery_v1 import run as base

SCHEMA = 'hiroute.search_extensions.v1'
CASE = base.DEV_CASES[0]
ARMS = ('baseline', 'onward_only', 'coalescing_only')
CONFIGS = {
    'baseline': dict(onward_alt=False, coalescing=False),
    'onward_only': dict(onward_alt=True, coalescing=False),
    'coalescing_only': dict(onward_alt=False, coalescing=True),
}
POLICY = dict(case=CASE, candidate_count=128, routing='full', terminal_energy='search_only_ON',
    hierarchy_policy='original_frozen_tree_restricted_without_renumbering',
    seed_policy='first_feasible_streamed_proposal_fresh_double_replay_v1',
    cache_policy=base.CACHE_POLICY, alt_strategy='indexed', historical_pooling=False,
    holdout=False, require_positive_result=False)
DENOMINATOR = dict(common_preparations=1, search_arms=3, independent_replays=3, total_stages=7)
RESERVE = dict(exact_search_seconds_per_arm=120,total_exact_search_seconds=360,
    maximum_worker_wall_seconds=2940,maximum_worker_cpu_soft_seconds=2760,
    independent_replay_budget_excluded_from_search=True)
COUNTERS = ('source_run_count','target_run_count','source_cache_hits','source_cache_evictions',
    'source_cache_skips','source_cache_bytes','route_wall_ns','route_process_cpu_ns')


def configuration(arm):
    if arm not in CONFIGS:
        raise ValueError('Unknown extension arm')
    return dict(CONFIGS[arm])


def _manifest(path, expected_sha256):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('Closed manifest digest mismatch')
    m = json.loads(raw)
    if m.get('schema') != SCHEMA or m.get('launchable') is not True:
        raise ValueError('Prospective extension plan is not launchable')
    if (m.get('policy') != POLICY or m.get('arms') != CONFIGS or
        m.get('order') != list(ARMS) or m.get('denominator') != DENOMINATOR or
        m.get('limits') != base.LIMITS or m.get('cache_policy') != base.CACHE_POLICY or
        m.get('reverse_order_auto_launch') is not False or m.get('reserve_plan') != RESERVE):
        raise ValueError('Frozen extension gate policy differs')
    # Retain the original strict domain checks under the new fixed gate policy.
    expected_inputs = json.loads(Path(base.__file__).with_name('manifest.json').read_bytes())['inputs']
    if m.get('inputs') != expected_inputs:
        raise ValueError('Original nine input identities differ')
    c = m['compiler']
    if (set(c) != {'path','sha256','version','flags'} or
        base.file_hash(c['path']) != c['sha256'] or
        subprocess.check_output([c['path'],'--version'], text=True) != c['version'] or
        c['flags'] != ['-O3','-std=c++17']):
        raise ValueError('Pinned compiler identity differs')
    if m['source'] != base.source_identity(m['repo'], published_commit=m['source']['commit'], publication=m['source'].get('publication')):
        raise ValueError('Committed executable/runtime closure differs')
    if not any(n.startswith('experiments/search_extensions_v1/') for n in m['source']['closure']):
        raise ValueError('Extension executable closure missing')
    for name, binding in m['inputs'].items():
        p = Path(m['input_directory']) / name
        if p.stat().st_size != binding['size'] or base.file_hash(p) != binding['sha256']:
            raise ValueError('Input identity mismatch: ' + name)
    metadata = json.loads((Path(m['input_directory'])/'metadata.json').read_bytes())
    base.cache_capacity(m['cache_policy'], metadata['node_count'])
    if m.get('acceptance') != ACCEPTANCE or m.get('stop_conditions') != STOP_CONDITIONS:
        raise ValueError('Frozen acceptance or stop conditions differ')
    return m


ACCEPTANCE = ['all_three_arms_replay_same_common_domain', 'complete_lexicographic_keys_recorded',
    'all_owned_cleanup_verified', 'no_unknown_or_missing_stage', 'no_positive_effect_required']
STOP_CONDITIONS = ['common_preparation_failure', 'unknown_or_unverified_owned_cleanup',
    'search_failure_other_than_exact_phase_timeout', 'independent_replay_failure',
    'source_input_policy_drift', 'parent_cpu_budget_exhaustion',
    'after_forward_three_arm_gate_no_automatic_reverse']


class ExtensionDomain(base.NativeDomain):
    def __init__(self, *, arm, manifest_binding, **kwargs):
        self.arm = arm
        self.extension_config = configuration(arm)
        self._extension_bytes = base.canonical(self.extension_config)
        self.manifest_binding = manifest_binding
        self._manifest_binding = manifest_binding
        super().__init__(**kwargs)

    def check(self):
        super().check()
        if (base.canonical(self.extension_config) != self._extension_bytes or
            self.extension_config != configuration(self.arm) or
            self.manifest_binding != self._manifest_binding):
            raise ValueError('Extension runtime policy changed')

    def durable_binding(self, seed):
        binding = super().durable_binding(seed)
        binding['domain_sha256'] = base.digest([binding['domain_sha256'], SCHEMA, self.arm,
            self.extension_config, self.manifest_binding])
        binding['source_sha256'] = dict(binding['source_sha256'],
            extension_policy=base.digest([self.arm,self.extension_config,self.manifest_binding]))
        return binding

    def problem(self, context, depth=None):
        if not self.extension_config['coalescing'] or context.role != 'search':
            return super().problem(context, depth)
        context.check_policy()
        if (context._closed or context.router.role != context.role or
            context.router.mode != context.config.effective_mode(context.role)):
            raise ValueError('Closed or changed routing context')
        from timecut5.coalesced_solver import table_free_problem
        from timecut5.terminal_energy import activate
        query = json.loads(self.query_bytes)
        if depth is not None:
            query['H_ref'] = depth
        problem = table_free_problem(query, self.sites, context.provider,
            origin_anchor=query['origin'], destination_anchor=query['destination'],
            site_catalog_sha256=self.site_sha256, coalescing=True, terminal_target_routing=False)
        activate(problem, context.provider, context.config.terminal_energy,
            kernel=context._energy_kernel, observation=context.observation)
        return problem

    def make_bound(self, context, strategy):
        from timecut5.road_provider import TableFreeRegionBoundProvider
        query = json.loads(self.query_bytes)
        self._search_provider = context.provider
        return TableFreeRegionBoundProvider(context.provider, self.sites, self.tree,
            destination_anchor=query['destination'], landmark_anchor=query['origin'],
            site_catalog_sha256=self.site_sha256, router_factory=self.landmark_router,
            alt_strategy='indexed', collect_alt_member_reads=False,
            onward_alt=self.extension_config['onward_alt'])

    def solve_exact(self, problem, witness, key, bound, store):
        from timecut5.hierarchy import _solve_hierarchical_problem
        search_start = time.monotonic_ns()
        setup_ns = search_start-self._started
        last_checkpoint = {}
        counter_names = ('attempted_extensions','feasible_prefixes','max_layer_piece_count',
            'region_nodes','leaf_actions','bound_member_scans','pruned_regions',
            'equality_nodes_retained','coverage_groups')
        def snapshot(*checkpoint, terminal_result=None):
            terminal = terminal_result is not None
            if checkpoint:
                last_checkpoint.update(depth=checkpoint[0], counters=dict(zip(counter_names,checkpoint[4])))
            counters = dict(last_checkpoint.get('counters', {}))
            if terminal:
                counters.update({name:getattr(terminal_result.bounded,name) for name in counter_names[:3]})
                counters.update({name:getattr(terminal_result,name) for name in counter_names[3:]})
                counters['terminal_piece_count'] = terminal_result.bounded.terminal_piece_count
            pieces = asdict(problem.statistics()) if self.extension_config['coalescing'] else dict(
                calls=0,input_pieces=0,output_pieces=0,max_input_pieces=0,max_output_pieces=0)
            value = dict(schema=SCHEMA, arm=self.arm, configuration=self.extension_config,
                manifest_binding=self.manifest_binding, setup_wall_ns=setup_ns,
                search_observed_wall_ns=time.monotonic_ns()-search_start,
                route={n:getattr(self._search_provider,n) for n in COUNTERS},
                coalescing=pieces, checkpoint_depth=last_checkpoint.get('depth'),
                search_counters=counters, counters_complete=terminal,
                counter_semantics=dict(cumulative='complete_at_solver_return' if terminal else 'last_checkpoint_lower_bound',
                    source_cache_bytes='instantaneous_gauge_at_snapshot',
                    checkpoint_depth='last_observed_layer_start',
                    search_observed_wall_ns='elapsed_at_snapshot_not_phase_budget'))
            tmp=self._output/'metrics.tmp';tmp.write_bytes(base.canonical(value))
            os.replace(tmp,self._output/'metrics.json')
        snapshot()
        result = _solve_hierarchical_problem(problem, True, self.tree, witness,
            reducer=problem.reduce if self.extension_config['coalescing'] else None,
            verified_primary_upper=key[0], bound_provider=bound, incumbent_hook=store,
            checkpoint_hook=snapshot)
        snapshot(terminal_result=result)
        return result

    def run_arm(self, strategy, seed, output, **kwargs):
        if strategy != self.arm:
            raise ValueError('Arm differs from runtime configuration')
        self._output=Path(output);self._started=time.monotonic_ns()
        result=super().run_arm('indexed',seed,output,**kwargs)
        result.update(schema=SCHEMA, strategy=self.arm, configuration=self.extension_config,
            manifest_binding=self.manifest_binding,
            metrics_sha256=base.file_hash(self._output/'metrics.json'))
        (self._output/'result.json').write_bytes(base.canonical(result))
        return result


def domain_factory(manifest, query, sites, cache, *, arm):
    directory, bindings = manifest['input_directory'], manifest['inputs']
    tree = base.original_tree((Path(directory)/'hierarchy.json').read_bytes(), bindings['hierarchy.json']['sha256'],list(sites))
    if len(sites) != 128:
        raise ValueError('OD02 original N128 required')
    return ExtensionDomain(arm=arm, manifest_binding=base.digest(manifest),
        graph_factory=lambda:base.load_graph(directory,bindings), query=query,sites=sites,tree=tree,
        source_hashes=dict({n:bindings[n+'.parquet']['sha256'] for n in ('nodes','edges')},
            source_closure=manifest['source']['closure_sha256'],
            **{'input:'+n:b['sha256'] for n,b in bindings.items()}), cache=cache,
        compiler=manifest['compiler']['path'],cache_policy=manifest['cache_policy'])


def run_gate(path, sha256, output, cpu):
    return base._run_plan(path,sha256,output,cpu,scope='od02_gate',manifest_loader=_manifest,
        worker_module='experiments.search_extensions_v1.run',fixed_cases=(CASE,),fixed_pairs=[[CASE,list(ARMS)]])


def require_exact_phase(search):
    if (search.get('phase_entered_monotonic') is None or
        search.get('phase_budget', {}).get('seconds') != 120 or
        (search.get('status') == 'TIMEOUT' and search.get('reason') != 'phase_timeout')):
        raise ValueError('Search did not complete or exhaust its exact phase')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    modes=p.add_mutually_exclusive_group(required=True)
    modes.add_argument('--plan',action='store_true');modes.add_argument('--gate',action='store_true')
    modes.add_argument('--worker',choices=('prepare','arm','verify'))
    for name in ('manifest','manifest-sha256','output','common','common-sha256','search-directory','search-receipt-sha256'):
        p.add_argument('--'+name)
    p.add_argument('--cpu',type=int);p.add_argument('--case',choices=(CASE,));p.add_argument('--strategy',choices=ARMS)
    a=p.parse_args()
    if a.plan:
        print(Path(__file__).with_name('manifest.json').read_text());return 0
    if a.gate:
        if a.output is None or a.cpu is None or a.case is not None or a.strategy is not None:
            p.error('--gate requires --output and --cpu and has fixed case/order')
        ledger=run_gate(a.manifest,a.manifest_sha256,a.output,a.cpu)
        return 0 if ledger['status']=='COMPLETED' else 1
    manifest=_manifest(a.manifest,a.manifest_sha256)
    if a.case != CASE or (a.worker != 'prepare' and a.strategy is None):
        p.error('worker requires fixed case and arm')
    if a.worker == 'verify':
        from experiments.mechanism_recovery_v1.supervisor import read_result
        search = read_result(a.search_directory)
        require_exact_phase(search)
    arm=a.strategy or 'baseline'
    factory=lambda m,q,s,c:domain_factory(m,q,s,c,arm=arm)
    result = base.worker(manifest,a.worker,a.case,a.common,a.common_sha256,a.strategy,
        a.search_directory,a.search_receipt_sha256,domain_factory=factory)
    if a.worker == 'verify':
        result.update(schema=SCHEMA, strategy=arm, configuration=configuration(arm),
            manifest_binding=base.digest(manifest))
        Path(os.environ['HIROUTE_OUTPUT_DIR'],'verification.json').write_bytes(base.canonical(result))
    _manifest(a.manifest,a.manifest_sha256)
    Path(os.environ['HIROUTE_WORKER_RECEIPT']).write_bytes(base.canonical(dict(status='COMPLETED',
        result=base.result_envelope(os.environ['HIROUTE_OUTPUT_DIR'],a.worker,a.case,a.strategy))))
    return 0


if __name__ == '__main__':
    sys.exit(main())
