"""Fixed OD10 HIER baseline/skyline gates: original N32 before original N128."""
from __future__ import annotations
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from experiments.mechanism_recovery_v1 import run as base
from experiments.search_extensions_v1.run import require_exact_phase

SCHEMA = 'hiroute.scalability_development.v1'
CASE = 'OD10_energy_only_soc19_25'
ARMS = ('baseline', 'skyline_only')
CONFIGS = {
    'baseline': dict(reducer='reduce_frontier', onward_alt=False, coalescing=False, source_locality=False),
    'skyline_only': dict(reducer='reduce_frontier_skyline', onward_alt=False, coalescing=False, source_locality=False),
}
POLICY = dict(case=CASE, method='HIER', routing='full', terminal_energy='search_only_ON',
    hierarchy_policy='original_frozen_tree_restricted_without_renumbering', alt_strategy='indexed',
    seed_policy='first_feasible_streamed_proposal_fresh_double_replay_v1',
    cache_policy=base.CACHE_POLICY, historical_pooling=False, holdout=False,
    require_positive_result=False, candidate_policy='original_pool_prefix',
    cross_size_seed_policy='independent_generation_record_Hmax_no_candidate_only_causality')
DENOMINATOR = dict(common_preparations=1, search_arms=2, independent_replays=2, total_stages=5)
RESERVE = dict(exact_search_seconds_per_arm=120, total_exact_search_seconds=240,
    maximum_worker_wall_seconds=2160, maximum_worker_cpu_soft_seconds=2040,
    parent_cpu_soft_seconds=90, independent_replay_budget_excluded_from_search=True,
    aggregate_worker_cpu_measured=False, aggregate_RSS_hard_limit=False)
ACCEPTANCE = ['same_common_seed_domain_and_Hmax', 'both_search_phases_entered',
    'both_independent_physical_replays_pass', 'all_owned_cleanup_verified',
    'no_unknown_failed_or_missing_stage', 'completed_exact_results_agree_if_both_completed',
    'no_positive_effect_required']
STOP_CONDITIONS = ['common_preparation_failure', 'search_failure_except_exact_phase_timeout',
    'unknown_or_unverified_owned_cleanup', 'independent_replay_failure',
    'completed_exact_result_disagreement', 'source_input_policy_drift',
    'parent_cpu_budget_exhaustion', 'no_automatic_next_size_repeat_or_holdout']


def configuration(arm):
    if arm not in CONFIGS:
        raise ValueError('Unknown scalability arm')
    return dict(CONFIGS[arm])


def source_identity(repo):
    """Keep inherited source closure and explicitly add this new executable package."""
    identity = base.source_identity(repo)
    closure = dict(identity['closure'])
    prefix = Path(repo) / 'experiments/scalability_development_v1'
    for path in sorted(prefix.rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix not in ('.pyc', '.pyo'):
            closure[str(path.relative_to(repo))] = base.file_hash(path)
    return dict(identity, closure=closure, closure_sha256=base.digest(closure))


def prospective(count=32):
    if type(count) is not int or count not in (32, 128):
        raise ValueError('Only original N32/N128 admitted')
    inherited = json.loads(Path(base.__file__).with_name('manifest.json').read_bytes())
    return dict(schema=SCHEMA, launchable=False, status='prospective_pending_source_freeze',
        candidate_count=count, policy=POLICY, arms=CONFIGS, order=list(ARMS),
        denominator=DENOMINATOR, reserve_plan=RESERVE, limits=base.LIMITS,
        cache_policy=base.CACHE_POLICY, acceptance=ACCEPTANCE, stop_conditions=STOP_CONDITIONS,
        inputs=inherited['inputs'], repo=None, input_directory=None, compiler=None, source=None,
        auto_next_size=False, prior_n32_gate_required=count == 128)


def _manifest(path, expected_sha256):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('Closed manifest digest mismatch')
    manifest = json.loads(raw)
    if manifest.get('schema') != SCHEMA or manifest.get('launchable') is not True:
        raise ValueError('Prospective scalability plan is not launchable')
    count = manifest.get('candidate_count')
    expected = prospective(count)
    runtime = {'launchable', 'status', 'repo', 'input_directory', 'compiler', 'source'}
    if set(manifest) != set(expected) or any(manifest[k] != v for k, v in expected.items() if k not in runtime):
        raise ValueError('Frozen scalability policy differs')
    compiler = manifest['compiler']
    if (set(compiler) != {'path', 'sha256', 'version', 'flags'} or
        base.file_hash(compiler['path']) != compiler['sha256'] or
        subprocess.check_output([compiler['path'], '--version'], text=True) != compiler['version'] or
        compiler['flags'] != ['-O3', '-std=c++17']):
        raise ValueError('Pinned compiler identity differs')
    if manifest['source'] != source_identity(manifest['repo']):
        raise ValueError('Committed executable/runtime closure differs')
    for name, binding in manifest['inputs'].items():
        source = Path(manifest['input_directory']) / name
        if source.stat().st_size != binding['size'] or base.file_hash(source) != binding['sha256']:
            raise ValueError('Input identity mismatch: ' + name)
    metadata = json.loads((Path(manifest['input_directory']) / 'metadata.json').read_bytes())
    base.cache_capacity(manifest['cache_policy'], metadata['node_count'])
    return manifest


def extract_case(directory, count, bindings):
    """Authenticate both original nested domains, including historical anchor bindings."""
    from timecut5.real_adapter import site_catalog_digest
    from timecut5.real_legs import RealSite, TIE_POLICY
    from timecut5.sparse_seed import sparse_domain_digest
    if type(count) is not int or count not in (32, 128):
        raise ValueError('Only original N32/N128 admitted')
    base.verify_inputs(directory, {n: bindings[n] for n in base.INPUT_NAMES})
    root = Path(directory)
    queries = json.loads((root / 'queries.json').read_bytes())
    matches = [r for r in queries['queries'] if r['query_id'] == CASE]
    pools = json.loads((root / 'pools.json').read_bytes())['pools']
    candidates = [r for r in pools if r['od_id'] == 'OD10']
    if len(matches) != 1 or len(candidates) != 1:
        raise ValueError('Ambiguous frozen OD10 identity')
    row, pool = matches[0], candidates[0]
    a, b = row['bindings']['32'], row['bindings']['128']
    if a['candidate_site_ids'] != b['candidate_site_ids'][:32]:
        raise ValueError('Original candidates are not nested prefixes')
    physical = lambda q: {k: v for k, v in q.items() if k != 'sparse_domain_sha256'}
    if physical(a['query']) != physical(b['query']):
        raise ValueError('N32/N128 physical query changed')
    sources = queries['source_sha256']
    for key, name in (('graph_nodes','nodes.parquet'), ('graph_edges','edges.parquet'),
                      ('hierarchy','hierarchy.json'), ('pools','pools.json')):
        if sources[key] != bindings[name]['sha256']:
            raise ValueError('Frozen query source mismatch: ' + key)
    extracted = {}
    for size in (32, 128):
        bound = row['bindings'][str(size)]
        records = pool['sites'][:size]
        sites = {r['site_id']: RealSite(r['site_id'], r['anchor_id'], tuple(r['effects'])) for r in records}
        query = bound['query']
        anchors = {anchor: int(anchor.removeprefix('road:')) for anchor in dict.fromkeys(
            [query['origin']] + [r['anchor_id'] for r in records] + [query['destination']])}
        old_sources = dict(nodes=sources['graph_nodes'], edges=sources['graph_edges'],
            router=sources['router_cpp'], anchors=base.digest(anchors),
            tie_policy=hashlib.sha256(TIE_POLICY.encode()).hexdigest())
        domain = sparse_domain_digest(old_sources, site_catalog_digest(sites), base.digest(sorted(sites)),
            query['hierarchy_sha256'], query['origin'], query['destination'])
        if (len(sites) != size or list(sites) != bound['candidate_site_ids'] or
            base.digest(sorted(sites)) != bound['candidate_sha256'] or
            site_catalog_digest(sites) != bound['site_catalog_sha256'] or
            base.digest(query) != bound['query_sha256'] or
            query['case_id'] != CASE or query['hierarchy_sha256'] != bindings['hierarchy.json']['sha256'] or
            base.digest(anchors) != bound['anchor_catalog_sha256'] or
            domain != bound['sparse_domain_sha256'] or domain != query['sparse_domain_sha256']):
            raise ValueError('Frozen candidate/query/domain identity mismatch')
        extracted[size] = query, sites
    query, sites = extracted[count]
    tree = base.original_tree((root / 'hierarchy.json').read_bytes(), bindings['hierarchy.json']['sha256'], list(sites))
    return query, sites, tree


class ScalabilityDomain(base.NativeDomain):
    def __init__(self, *, arm, manifest_binding, **kwargs):
        self.arm = arm
        self.config = configuration(arm)
        self._config_bytes = base.canonical(self.config)
        self.manifest_binding = manifest_binding
        self._manifest_binding = manifest_binding
        super().__init__(**kwargs)

    def check(self):
        super().check()
        if (base.canonical(self.config) != self._config_bytes or self.config != configuration(self.arm) or
            self.manifest_binding != self._manifest_binding):
            raise ValueError('Scalability runtime policy changed')

    def durable_binding(self, seed):
        value = super().durable_binding(seed)
        value['domain_sha256'] = base.digest([value['domain_sha256'], SCHEMA, self.arm, self.config, self.manifest_binding])
        value['source_sha256'] = dict(value['source_sha256'], scalability_policy=base.digest([self.arm, self.config, self.manifest_binding]))
        return value

    def make_bound(self, context, strategy):
        self._search_provider = context.provider
        return super().make_bound(context, 'indexed')

    def solve_exact(self, problem, witness, key, bound, store):
        from timecut5.hierarchy import _solve_hierarchical_problem
        from timecut5.pwa import reduce_frontier, reduce_frontier_skyline
        reducer = reduce_frontier if self.arm == 'baseline' else reduce_frontier_skyline
        stats = dict(calls=0, input_piece_visits=0, output_piece_visits=0, inclusive_wall_ns=0)
        started = time.monotonic_ns()
        latest = {}
        route_names = ('source_run_count', 'target_run_count', 'source_cache_hits', 'source_cache_evictions',
            'source_cache_skips', 'source_cache_bytes', 'route_wall_ns', 'route_process_cpu_ns')
        route_start = {name: getattr(self._search_provider, name) for name in route_names}
        telemetry_start = self._search_provider.routing_telemetry_snapshot()
        durable_stats = dict(calls=0, inclusive_wall_ns=0)
        def measured_store(witness, key):
            before = time.monotonic_ns()
            try:
                return store(witness, key)
            finally:
                durable_stats['calls'] += 1
                durable_stats['inclusive_wall_ns'] += time.monotonic_ns() - before
        counter_names = ('attempted_extensions', 'feasible_prefixes', 'max_layer_piece_count',
            'region_nodes', 'leaf_actions', 'bound_member_scans', 'pruned_regions',
            'equality_nodes_retained', 'coverage_groups')
        def measured(values):
            before = time.monotonic_ns()
            result = reducer(values)
            stats['calls'] += 1
            stats['input_piece_visits'] += len(values)
            stats['output_piece_visits'] += len(result)
            stats['inclusive_wall_ns'] += time.monotonic_ns() - before
            return result
        def snapshot(*checkpoint, result=None):
            if checkpoint:
                latest.update(checkpoint_depth=checkpoint[0], counters=dict(zip(counter_names, checkpoint[4])))
            counters = dict(latest.get('counters', {}))
            if result is not None:
                counters.update({name: getattr(result.bounded, name) for name in counter_names[:3]})
                counters.update({name: getattr(result, name) for name in counter_names[3:]})
                counters['terminal_piece_count'] = result.bounded.terminal_piece_count
            current = {name: getattr(self._search_provider, name) for name in route_names}
            metrics = dict(schema=SCHEMA, arm=self.arm, configuration=self.config, manifest_binding=self.manifest_binding,
                search_observed_wall_ns=time.monotonic_ns()-started, reducer=dict(stats), durable_callback=dict(durable_stats),
                routing_telemetry_phase_baseline=telemetry_start,
                routing_telemetry_search_delta=self._search_provider.routing_telemetry_delta(telemetry_start),
                route_at_phase_start=route_start,
                route_at_snapshot=current, search_route_counter_deltas={k: current[k]-route_start[k]
                    for k in route_names if k != 'source_cache_bytes'},
                source_cache_bytes_gauge=current['source_cache_bytes'], checkpoint_depth=latest.get('checkpoint_depth'),
                search_counters=counters, counters_complete=result is not None,
                observation_scope='complete_solver_return' if result is not None else 'last_completed_checkpoint_partial',
                counters_are_unique_pieces=False, phase_timeout_does_not_finalize_metrics=True)
            temporary = self._output / 'metrics.tmp'
            temporary.write_bytes(base.canonical(metrics)); os.replace(temporary, self._output / 'metrics.json')
        snapshot()
        result = _solve_hierarchical_problem(problem, True, self.tree, witness, reducer=measured,
            verified_primary_upper=key[0], bound_provider=bound, incumbent_hook=measured_store, checkpoint_hook=snapshot)
        snapshot(result=result)
        return result

    def run_arm(self, strategy, seed, output, **kwargs):
        if strategy != self.arm:
            raise ValueError('Arm differs from runtime configuration')
        self._output = Path(output)
        report = super().run_arm('indexed', seed, output, **kwargs)
        report.update(schema=SCHEMA, strategy=self.arm, configuration=self.config,
            manifest_binding=self.manifest_binding, metrics_sha256=base.file_hash(self._output / 'metrics.json'))
        (self._output / 'result.json').write_bytes(base.canonical(report))
        return report


def domain_factory(manifest, query, sites, cache, *, arm):
    directory, bindings = manifest['input_directory'], manifest['inputs']
    if len(sites) != manifest['candidate_count']:
        raise ValueError('Candidate count differs from closed manifest')
    tree = base.original_tree((Path(directory) / 'hierarchy.json').read_bytes(), bindings['hierarchy.json']['sha256'], list(sites))
    return ScalabilityDomain(arm=arm, manifest_binding=base.digest(manifest),
        graph_factory=lambda: base.load_graph(directory, bindings), query=query, sites=sites, tree=tree,
        source_hashes=dict({n: bindings[n+'.parquet']['sha256'] for n in ('nodes','edges')},
            source_closure=manifest['source']['closure_sha256'], **{'input:'+n:b['sha256'] for n,b in bindings.items()}),
        cache=cache, compiler=manifest['compiler']['path'], cache_policy=manifest['cache_policy'])


def prepare_case(manifest, output):
    """Fresh deterministic seed with two independent full-routing physical replays."""
    from timecut5.real_adapter import site_catalog_digest
    from timecut5.sparse_seed import SparseSeedCatalog, sparse_domain_digest, replay_sparse_seed, SeedInfeasible
    from timecut5.deployable import iter_constructive_seed_candidates
    from timecut5.provenance import primitive
    started = time.monotonic_ns()
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    directory, bindings = manifest['input_directory'], manifest['inputs']
    query, sites, _ = extract_case(directory, manifest['candidate_count'], bindings)
    historical_query_sha256 = base.digest(query)
    make = lambda q: domain_factory(manifest, q, sites, output / 'native', arm='baseline')
    domain = make(query)
    with domain.context('generation') as context:
        query = dict(query, sparse_domain_sha256=sparse_domain_digest(context.provider.source_sha256,
            site_catalog_digest(sites), base.digest(sorted(sites)), query['hierarchy_sha256'], query['origin'], query['destination']))
    domain = make(query)
    def catalog(context):
        return SparseSeedCatalog(context.provider, sites, origin_anchor=query['origin'], destination_anchor=query['destination'],
            nodes_path=Path(directory)/'nodes.parquet', edges_path=Path(directory)/'edges.parquet',
            site_catalog_sha256=site_catalog_digest(sites), hierarchy_sha256=query['hierarchy_sha256'],
            candidate_sha256=base.digest(sorted(sites)))
    with domain.context('generation') as context:
        sparse = catalog(context)
        witness = None
        for ordinal, (sequence, charges) in enumerate(iter_constructive_seed_candidates(query, sparse)):
            try:
                replay_sparse_seed(query, sparse, sequence, charges)
            except SeedInfeasible:
                continue
            witness = base.proposal_witness(domain.problem(context), sequence, charges)
            break
        if witness is None:
            raise ValueError('incumbent_search_failed: deterministic proposal stream exhausted; feasibility unknown')
    seed = domain.freeze_seed(witness)
    with domain.context('verification') as context:
        replayed = replay_sparse_seed(query, catalog(context), witness.pi,
            tuple(e.departure_energy-e.arrival_energy for e in witness.events if e.effect in ('C','CS')))
        if base.canonical(primitive(replayed['lex_key'])) != seed.key_bytes:
            raise ValueError('Independent common sparse seed replay differs')
    values = asdict(seed)
    for name in ('witness_bytes', 'key_bytes'):
        values[name] = values[name].decode()
    common = dict(schema=SCHEMA, status='common_feasible_seed', case_id=CASE, candidate_count=manifest['candidate_count'],
        query=query, historical_query_sha256=historical_query_sha256, runtime_rebinding_fields=['sparse_domain_sha256'],
        sites=[dict(site_id=s.site_id, anchor_id=s.anchor_id, effects=list(s.effects)) for s in sites.values()],
        tree_sha256=domain.tree_sha256, seed=values, proposal_ordinal=ordinal, candidate_repair=None,
        native=dict(router=domain.artifact.receipt, energy=domain.energy_artifact.receipt),
        charged_wall_ns=time.monotonic_ns()-started, seed_policy=POLICY['seed_policy'],
        source=manifest['source'], inputs=bindings, cache_policy=domain.cache_policy)
    (output / 'common.json').write_bytes(base.canonical(common))
    return common


def admission(ledger):
    """Check each retained stage against its actual receipt and arm identity."""
    stages = ledger.get('stages', [])
    arms = ledger.get('arms', [])
    if (ledger.get('schema') != SCHEMA or ledger.get('status') != 'COMPLETED' or
        ledger.get('denominator') != 5 or len(stages) != 5 or len(arms) != 2 or
        [a.get('strategy') for a in arms] != list(ARMS)):
        raise ValueError('Prior gate lacks all five operational terminals')
    if set(ledger.get('common', {})) != {CASE}:
        raise ValueError('Prior common preparation identity differs')

    def check_stage(position, identifier, operation, receipt, allowed, strategy=None):
        if not isinstance(receipt, dict) or receipt.get('status') not in allowed:
            raise ValueError('Prior stage receipt status is not admitted: ' + identifier)
        expected = dict(id=identifier, operation=operation, case=CASE, status=receipt['status'])
        if strategy is not None:
            expected['strategy'] = strategy
        if stages[position] != expected:
            raise ValueError('Prior stage/receipt identity or status differs: ' + identifier)
        if not receipt.get('cleanup_verified'):
            raise ValueError('Prior gate lacks verified owned cleanup')
        if operation == 'search':
            require_exact_phase(receipt)
            identity = receipt.get('phase_budget', {}).get('identity', {})
            if (identity.get('case_id') != CASE or identity.get('strategy') != strategy or
                identity.get('arm_index') != identifier.removeprefix('search-')):
                raise ValueError('Prior search receipt belongs to another case/arm')
        else:
            result = receipt.get('worker_receipt', {}).get('result', {})
            expected_operation = 'prepare' if operation == 'prepare' else 'verify'
            if (result.get('operation') != expected_operation or result.get('case_id') != CASE or
                result.get('strategy') != strategy):
                raise ValueError('Prior worker receipt belongs to another operation/case/arm')

    common = ledger['common'][CASE]
    check_stage(0, 'prepare-'+CASE, 'prepare', common, ('SUCCESS',))
    for index, arm in enumerate(arms):
        if arm.get('case') != CASE or type(arm.get('pair')) is not int or arm['pair'] != 0:
            raise ValueError('Prior arm case/pair identity differs')
        search, verification = arm.get('receipt'), arm.get('verification')
        check_stage(1+2*index, f'search-{index}', 'search', search,
            ('SUCCESS', 'TIMEOUT'), arm['strategy'])
        check_stage(2+2*index, f'verify-{index}', 'verify', verification,
            ('SUCCESS',), arm['strategy'])
        reported_status = verification['worker_receipt']['result'].get('summary', {}).get('status')
        if not isinstance(reported_status, str) or arm.get('status') != reported_status:
            raise ValueError('Prior arm outcome differs from verification receipt')
    if ledger.get('operational_admission') is not True:
        raise ValueError('Prior gate was not independently admitted')


def prior_gate(path, expected_sha256, manifest):
    """Verify actual prior artifacts, not a caller-supplied success flag."""
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('Prior N32 ledger digest mismatch')
    ledger = json.loads(raw)
    if ledger.get('candidate_count') != 32 or ledger.get('source') != manifest['source']:
        raise ValueError('Prior gate source/count differs')
    admission(ledger)
    root = Path(path).parent
    prior_manifest = _manifest(ledger['manifest_path'], ledger['manifest_sha256'])
    if prior_manifest['candidate_count'] != 32 or any(prior_manifest[k] != manifest[k]
            for k in manifest if k not in ('candidate_count', 'prior_n32_gate_required')):
        raise ValueError('Prior manifest differs beyond candidate count')
    for index, arm in enumerate(ledger['arms']):
        from experiments.mechanism_recovery_v1.supervisor import read_result
        for operation, folder, saved in (('arm', f'arm-{index:02d}', arm['receipt']),
                                         ('verify', f'verify-{index:02d}', arm['verification'])):
            disk = read_result(root / folder)
            if disk != saved:
                raise ValueError('Prior stage receipt changed')
            if disk['status'] == 'SUCCESS':
                base.load_worker_result(root / folder, disk, operation, CASE, arm['strategy'])
    prepared = root / ('prepare-' + CASE)
    from experiments.mechanism_recovery_v1.supervisor import read_result
    if read_result(prepared) != ledger['common'][CASE]:
        raise ValueError('Prior preparation receipt changed')
    base.load_worker_result(prepared, ledger['common'][CASE], 'prepare', CASE)
    return dict(path=str(Path(path).resolve()), sha256=expected_sha256, candidate_count=32,
        operational_only=True, exact_completion_required=False)


def run_gate(path, sha256, output, cpu, *, prior_path=None, prior_sha256=None):
    manifest = _manifest(path, sha256)
    prior = None
    if manifest['candidate_count'] == 128:
        if not prior_path or not prior_sha256:
            raise ValueError('N128 requires authenticated successful N32 gate')
        prior = prior_gate(prior_path, prior_sha256, manifest)
    elif prior_path is not None or prior_sha256 is not None:
        raise ValueError('N32 cannot supply a prior gate')
    ledger = base._run_plan(path, sha256, output, cpu, scope='od02_gate', manifest_loader=_manifest,
        worker_module='experiments.scalability_development_v1.run', fixed_cases=(CASE,),
        fixed_pairs=[[CASE, list(ARMS)]])
    ledger.update(scope=f"od10_n{manifest['candidate_count']}_gate", candidate_count=manifest['candidate_count'], source=manifest['source'],
        manifest_path=str(Path(path).resolve()), prior_n32_gate=prior, operational_admission=False)
    try:
        verified = []
        for index, arm in enumerate(ledger['arms']):
            require_exact_phase(arm['receipt'])
            full = base.load_worker_result(Path(output)/f'verify-{index:02d}', arm['verification'], 'verify', CASE, arm['strategy'])
            verified.append(full)
        if all(a['receipt']['status'] == 'SUCCESS' for a in ledger['arms']):
            completed = [base.load_worker_result(Path(output)/f'arm-{i:02d}', a['receipt'], 'arm', CASE, a['strategy'])
                for i, a in enumerate(ledger['arms'])]
            mathematical = []
            for result in completed:
                payload = dict(result['result']['result'])
                payload.pop('charges', None)  # Valid continuous witness allocations may differ.
                payload.pop('witness_replayed', None)
                mathematical.append(payload)
            if mathematical[0] != mathematical[1]:
                raise ValueError('Completed exact results disagree')
        ledger['operational_admission'] = True
        admission(ledger)
    except (KeyError, TypeError, ValueError, OSError) as exc:
        ledger['operational_admission'] = False
        ledger['admission_error'] = str(exc)
        if ledger['status'] == 'COMPLETED':
            ledger['status'] = 'FAILED_ADMISSION'
    temporary = Path(output)/'ledger.tmp'; temporary.write_bytes(base.canonical(ledger))
    os.replace(temporary, Path(output)/'ledger.json')
    return ledger


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--plan', action='store_true'); mode.add_argument('--freeze', action='store_true')
    mode.add_argument('--gate', action='store_true'); mode.add_argument('--worker', choices=('prepare','arm','verify'))
    parser.add_argument('--candidate-count', type=int, choices=(32,128), default=32)
    for name in ('manifest','manifest-sha256','output','input-directory','common','common-sha256',
                 'search-directory','search-receipt-sha256','prior-ledger','prior-ledger-sha256'):
        parser.add_argument('--'+name)
    parser.add_argument('--cpu',type=int); parser.add_argument('--case',choices=(CASE,)); parser.add_argument('--strategy',choices=ARMS)
    args = parser.parse_args()
    if args.plan:
        print(json.dumps(prospective(args.candidate_count), indent=2, sort_keys=True)); return 0
    if args.freeze:
        if not args.output or not args.input_directory:
            parser.error('--freeze requires --output and --input-directory')
        root = Path.cwd().resolve(); compiler = Path(shutil.which('g++')).resolve()
        manifest = prospective(args.candidate_count)
        manifest.update(repo=str(root), input_directory=str(Path(args.input_directory).resolve()),
            compiler=dict(path=str(compiler), sha256=base.file_hash(compiler),
                version=subprocess.check_output([str(compiler),'--version'],text=True),flags=['-O3','-std=c++17']),
            source=source_identity(root), launchable=True, status='frozen_development_gate_not_launched')
        raw = base.canonical(manifest)
        with Path(args.output).open('xb') as stream: stream.write(raw)
        sha = hashlib.sha256(raw).hexdigest(); _manifest(args.output,sha)
        print(json.dumps(dict(manifest=str(Path(args.output).resolve()), sha256=sha, candidate_count=args.candidate_count))); return 0
    if args.gate:
        if args.output is None or args.cpu is None or args.case is not None or args.strategy is not None:
            parser.error('--gate requires --output/--cpu and has fixed case/arm order')
        ledger = run_gate(args.manifest,args.manifest_sha256,args.output,args.cpu,
            prior_path=args.prior_ledger,prior_sha256=args.prior_ledger_sha256)
        return 0 if ledger.get('operational_admission') else 1
    manifest = _manifest(args.manifest,args.manifest_sha256)
    if args.case != CASE or (args.worker != 'prepare' and args.strategy is None):
        parser.error('worker requires fixed case and arm')
    if args.worker == 'prepare':
        result = prepare_case(manifest, Path(os.environ['HIROUTE_OUTPUT_DIR'])/'prepared')
    else:
        if args.worker == 'verify':
            from experiments.mechanism_recovery_v1.supervisor import read_result
            require_exact_phase(read_result(args.search_directory))
        factory = lambda m,q,s,c: domain_factory(m,q,s,c,arm=args.strategy)
        result = base.worker(manifest,args.worker,args.case,args.common,args.common_sha256,args.strategy,
            args.search_directory,args.search_receipt_sha256,domain_factory=factory)
    _manifest(args.manifest,args.manifest_sha256)
    Path(os.environ['HIROUTE_WORKER_RECEIPT']).write_bytes(base.canonical(dict(status='COMPLETED',
        result=base.result_envelope(os.environ['HIROUTE_OUTPUT_DIR'],args.worker,args.case,args.strategy))))
    return 0


if __name__ == '__main__':
    sys.exit(main())
