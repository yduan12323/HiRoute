"""Fresh, closed-manifest mechanism experiment with bounded worker stages."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from dataclasses import dataclass
from fractions import Fraction as R
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import os
import signal
import sys
import shutil
import subprocess
import time

SCHEMA = 'hiroute.mechanism_recovery.v1'
BASE_COMMIT = '530cc6045881e1189a1bcbb169a710e9d4695ee3'
INPUT_NAMES = ('nodes.parquet', 'edges.parquet', 'metadata.json', 'queries.json', 'pools.json', 'hierarchy.json')
DEV_CASES = ('OD02_energy_only_soc3_10', 'OD07_energy_and_scheduled_soc3_10', 'OD10_energy_only_soc19_25')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


CACHE_POLICY = dict(source_cache_max_bytes=1024**3, source_cache_max_sources=2)
RESULT_PATHS = dict(prepare='prepared/common.json', arm='arm/result.json', verify='verification.json')
RESULT_SCHEMA = 'hiroute.mechanism_recovery.worker_result.v2'
MAX_RESULT_BYTES = 8 * 1024**2


def cache_capacity(policy, node_count):
    from timecut5.road_provider import TableFreeRoadSelectedLegProvider
    if (type(policy) is not dict or set(policy) != set(CACHE_POLICY) or
        any(type(v) is not int for v in policy.values()) or
        policy['source_cache_max_sources'] != 2 or policy['source_cache_max_bytes'] <= 0):
        raise ValueError('Two-source cache policy required')
    entry = TableFreeRoadSelectedLegProvider.source_cache_entry_bytes(node_count)
    if policy['source_cache_max_bytes'] < 2 * entry:
        raise ValueError('Source cache cannot retain two complete source entries')
    return dict(node_count=node_count, entry_bytes=entry, required_bytes=2*entry,
                byte_capacity=policy['source_cache_max_bytes']//entry, retained_source_cap=2)


def _result_summary(result, operation):
    if type(result) is not dict or type(result.get('status')) is not str:
        raise ValueError('Malformed full worker result')
    if operation == 'prepare':
        return dict(status=result['status'], candidate_count=len(result['sites']), max_depth=result['seed']['max_depth'])
    return {k: result[k] for k in ('status','optimality_claim') if k in result}


def result_envelope(artifacts, operation, case_id, strategy=None):
    path = Path(artifacts) / RESULT_PATHS[operation]
    raw = path.read_bytes()
    if not 0 < len(raw) <= MAX_RESULT_BYTES:
        raise ValueError('Full result artifact exceeds bounded contract')
    result = json.loads(raw)
    envelope = dict(schema=RESULT_SCHEMA, operation=operation, case_id=case_id, strategy=strategy,
        artifact=dict(path=RESULT_PATHS[operation], size=len(raw), sha256=hashlib.sha256(raw).hexdigest()),
        summary=_result_summary(result, operation))
    if len(canonical(envelope)) > 4096:
        raise ValueError('Control result exceeds compact contract')
    return envelope


def load_worker_result(directory, receipt, operation, case_id, strategy=None):
    """Authenticate the compact control record and fixed, owned result artifact."""
    envelope = receipt['worker_receipt']['result']
    if (type(envelope) is not dict or set(envelope) != {'schema','operation','case_id','strategy','artifact','summary'} or
        envelope['schema'] != RESULT_SCHEMA or envelope['operation'] != operation or
        envelope['case_id'] != case_id or envelope['strategy'] != strategy or len(canonical(envelope)) > 4096):
        raise ValueError('Worker result identity differs')
    binding = envelope['artifact']
    if (type(binding) is not dict or set(binding) != {'path','size','sha256'} or
        binding['path'] != RESULT_PATHS[operation] or type(binding['size']) is not int or
        not 0 < binding['size'] <= MAX_RESULT_BYTES or type(binding['sha256']) is not str):
        raise ValueError('Malformed artifact reference')
    root = Path(directory) / 'artifacts'
    path = root
    for part in Path(binding['path']).parts:
        path = path / part
        if path.is_symlink():
            raise ValueError('Symlink result artifact forbidden')
    if root.is_symlink() or not path.is_file() or path.stat().st_size != binding['size']:
        raise ValueError('Missing or wrong-sized result artifact')
    raw = path.read_bytes()
    if len(raw) != binding['size'] or hashlib.sha256(raw).hexdigest() != binding['sha256']:
        raise ValueError('Result artifact digest differs')
    result = json.loads(raw)
    if _result_summary(result, operation) != envelope['summary']:
        raise ValueError('Result summary differs')
    return result


def verify_inputs(directory, bindings):
    """Exactly six byte identities; a supplied historical provenance is not authority."""
    if set(bindings) != set(INPUT_NAMES):
        raise ValueError('Exactly six frozen inputs required')
    for name, expected in bindings.items():
        path = Path(directory) / name
        if set(expected) != {'sha256', 'size'} or path.stat().st_size != expected['size'] or file_hash(path) != expected['sha256']:
            raise ValueError('Input identity mismatch: ' + name)


def source_identity(repo, *, published_commit=None, publication=None):
    """Bind local bytes to the externally verified published commit manifest.

    A restored snapshot need not have .git. Its publication is independently
    verified before the closed manifest is produced; the worker checks every
    local executable source against that manifest, not a fabricated local HEAD.
    """
    import re
    repo = Path(repo)
    if (repo / '.git').exists():
        run = lambda *a: subprocess.check_output(['git', '-C', str(repo), *a], text=True).strip()
        if run('status', '--porcelain', '--untracked-files=all'):
            raise ValueError('Source checkout must be clean and committed')
        commit = run('rev-parse', 'HEAD')
        if published_commit is not None and published_commit != commit:
            raise ValueError('Local HEAD differs from published execution commit')
    else:
        commit = published_commit
    if type(commit) is not str or re.fullmatch(r'[0-9a-f]{40}',commit) is None:
        raise ValueError('Verified published execution commit required')
    names=[]
    for prefix in ('src','validation','scripts','experiments/mechanism_recovery_v1','experiments/search_extensions_v1','experiments/sequential_transport_gate_v1'):
        names += [str(p.relative_to(repo)) for p in (repo/prefix).rglob('*')
                  if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo')]
    names += [n for n in ('pyproject.toml','uv.lock','environment-linux-64.lock') if (repo/n).is_file()]
    closure = {n:file_hash(repo/n) for n in sorted(names)}
    if not (repo/'.git').exists():
        if (not isinstance(publication,dict) or set(publication) != {'commit','tree','blobs'} or
            publication['commit'] != commit or re.fullmatch(r'[0-9a-f]{40}',publication['tree']) is None or
            set(publication['blobs']) != set(closure)):
            raise ValueError('Complete verified remote tree/blob closure required for snapshot')
        for name, blob in publication['blobs'].items():
            raw=(repo/name).read_bytes()
            actual=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
            if actual != blob:
                raise ValueError('Snapshot differs from verified published blob: '+name)
    from importlib import resources
    active = {}
    for package in ('timecut5','microplan'):
        installed = resources.files(package)
        prefix = 'src/' + package + '/'
        def active_names(folder, relative=''):
            found=set()
            for child in folder.iterdir():
                if child.name == '__pycache__':continue
                name=relative+child.name
                if child.is_dir():found.update(active_names(child,name+'/'))
                elif name.endswith(('.py','.cpp')):found.add(prefix+name)
            return found
        expected_names={name for name in closure if name.startswith(prefix) and name.endswith(('.py','.cpp'))}
        if active_names(installed) != expected_names:
            raise ValueError('Active package has missing or unlisted executable source: '+package)
        for name, expected in closure.items():
            if name.startswith(prefix) and name.endswith(('.py','.cpp')):
                value = hashlib.sha256(installed.joinpath(name[len(prefix):]).read_bytes()).hexdigest()
                if value != expected:
                    raise ValueError('Active package differs from committed source: ' + name)
                active[name] = value
    return dict(publication=publication, active_package_sources=active, commit=commit, closure=closure, closure_sha256=digest(closure),
                python=platform.python_version(), dependencies={d.metadata['Name']: d.version for d in importlib.metadata.distributions()})


def original_tree(data, expected_sha256, site_ids):
    """Use validated original topology, including empty nodes and original IDs."""
    from timecut5.real_legs import restrict_frozen_tree
    from timecut5.hierarchy import Region
    restricted = restrict_frozen_tree(data, expected_sha256, list(site_ids))
    def visit(index):
        row = restricted.regions[index]
        return Region(row.region_id, row.site_ids, tuple(visit(c) for c in row.child_ids))
    return visit(0)


def tree_value(root):
    return [root.identifier, list(root.members), [tree_value(c) for c in root.children]]


def extract_case(directory, case_id, bindings, *, od07_baseline=False):
    """Extract the prescribed OD02 N128 or OD10 N32 frozen binding."""
    from timecut5.real_adapter import site_catalog_digest
    from timecut5.real_legs import RealSite
    verify_inputs(directory, bindings)
    if case_id not in DEV_CASES:
        raise ValueError('Only frozen DEV cases admitted')
    if case_id.startswith('OD07_') and not od07_baseline:

        raise ValueError('OD07 repaired 149-candidate source is missing; recovered pool has only 128')
    root = Path(directory)
    rows = json.loads((root / 'queries.json').read_bytes())['queries']
    matches = [r for r in rows if r['query_id'] == case_id]
    if len(matches) != 1:
        raise ValueError('Ambiguous query identity')
    row = matches[0]
    count = 32 if case_id.startswith('OD10_') else 128
    bound = row['bindings'][str(count)]
    pools = json.loads((root / 'pools.json').read_bytes())['pools']
    pool = next(p for p in pools if p['od_id'] == row['od_id'])
    sites = {s['site_id']: RealSite(s['site_id'], s['anchor_id'], tuple(s['effects'])) for s in pool['sites'][:count]}
    query = bound['query']
    if (len(sites) != count or
            list(sites) != bound['candidate_site_ids'] or digest(sorted(sites)) != bound['candidate_sha256'] or
            site_catalog_digest(sites) != bound['site_catalog_sha256'] or digest(query) != bound['query_sha256'] or
            query['case_id'] != case_id or query['hierarchy_sha256'] != bindings['hierarchy.json']['sha256']):
        raise ValueError('Frozen case identity mismatch')
    tree = original_tree((root / 'hierarchy.json').read_bytes(), query['hierarchy_sha256'], list(sites))
    return query, sites, tree


@dataclass(frozen=True)
class FrozenSeed:
    witness_bytes: bytes
    key_bytes: bytes
    query_sha256: str
    tree_sha256: str
    site_sha256: str
    native_sha256: str
    max_depth: int
    cache_policy_sha256: str


def depth_bound(query, key):
    denominator = R(query['overhead_s']) + R(query['lambda_stop_s'])
    if R(query['overhead_s']) <= 0 or denominator <= 0 or key[0] < 0:
        raise ValueError('Positive-overhead feasible depth theorem required')
    return int(key[0] // denominator)


class NativeDomain:
    """One explicitly bound domain with fresh authenticated graph loads."""
    def __init__(self, *, graph_factory, query, sites, tree, source_hashes, cache, compiler=None, cache_policy=None):
        from microplan.native_artifact import build_artifact
        from timecut5.terminal_energy_artifact import build_artifact as build_energy
        from timecut5.real_adapter import site_catalog_digest
        self.cache_policy = dict(CACHE_POLICY if cache_policy is None else cache_policy)
        cache_capacity(self.cache_policy, 0)
        self._cache_policy_bytes = canonical(self.cache_policy)
        self.graph_factory = graph_factory
        self.query_bytes = canonical(query)
        self.sites = dict(sites)
        self.site_sha256 = site_catalog_digest(sites)
        self.tree = tree
        self.tree_sha256 = digest(tree_value(tree))
        if set(tree.members) != set(sites):
            raise ValueError('Tree and site universe differ')
        self.source_hashes = dict(source_hashes)
        self._source_bytes = canonical(source_hashes)
        self._query_bytes = self.query_bytes
        self.cache = Path(cache)
        self.compiler = dict(compiler=str(Path(compiler or shutil.which('g++')).resolve()), compiler_flags=['-O3', '-std=c++17'])
        started = time.monotonic_ns()
        self.artifact = build_artifact(self.compiler, self.cache / 'build')
        self.energy_artifact = build_energy(dict(compiler=self.compiler['compiler'], compiler_flags=['-O3', '-std=c++17', '-fno-fast-math', '-frounding-math']), self.cache / 'build')
        self.build_wall_ns = time.monotonic_ns() - started
        self.native_sha256 = digest([self.artifact.receipt['artifact_identity_sha256'], self.energy_artifact.receipt['artifact_identity_sha256']])
        self._serial = 0

    def check(self):
        from timecut5.real_adapter import site_catalog_digest
        if canonical(self.cache_policy) != self._cache_policy_bytes:
            raise ValueError('Cache policy changed')
        if canonical(self.source_hashes) != self._source_bytes or self.query_bytes != self._query_bytes:
            raise ValueError('Query/source binding changed')
        if site_catalog_digest(self.sites) != self.site_sha256 or digest(tree_value(self.tree)) != self.tree_sha256:
            raise ValueError('Domain changed')
        self.artifact.authenticate(self.compiler)
        self.energy_artifact.authenticate()
        if digest([self.artifact.receipt['artifact_identity_sha256'], self.energy_artifact.receipt['artifact_identity_sha256']]) != self.native_sha256:
            raise ValueError('Native identity changed')

    def context(self, role):
        from timecut5.routing_config import RoutingConfig, TerminalEnergyConfig
        self.check()
        query = json.loads(self.query_bytes)
        anchors = {a: int(a.removeprefix('road:')) for a in [query['origin'], query['destination'], *[s.anchor_id for s in self.sites.values()]]}
        self._serial += 1
        graph = self.graph_factory()
        cache_capacity(self.cache_policy, graph.node_count)
        context = RoutingConfig('full', TerminalEnergyConfig()).create_context(
            graph, self.compiler, self.cache / str(self._serial), role=role,
            artifact=self.artifact, energy_artifact=self.energy_artifact,
            anchor_nodes=anchors, nodes_sha256=self.source_hashes['nodes'], edges_sha256=self.source_hashes['edges'],
            anchor_catalog_sha256=digest(anchors), **self.cache_policy)
        if any(getattr(context.provider, k) != v for k,v in self.cache_policy.items()):
            context.close()
            raise ValueError('Actual provider cache policy differs')
        return context

    def problem(self, context, depth=None):
        query = json.loads(self.query_bytes)
        if depth is not None:
            query['H_ref'] = depth
        return context.problem(query, self.sites, origin_anchor=query['origin'], destination_anchor=query['destination'], site_catalog_sha256=self.site_sha256)

    def freeze_seed(self, witness):
        from timecut5.bounded import _replay_problem
        from timecut5.provenance import witness_dict, primitive
        from timecut5.routing_config import require_full_verifier
        with self.context('verification') as context:
            require_full_verifier(context.provider, fresh=True)
            key = _replay_problem(self.problem(context), witness)
        return FrozenSeed(canonical(witness_dict(witness)), canonical(primitive(key)), digest(json.loads(self.query_bytes)), self.tree_sha256, self.site_sha256, self.native_sha256, depth_bound(json.loads(self.query_bytes), key), digest(self.cache_policy))

    def validate_seed(self, seed):
        from timecut5.durable_incumbent import _witness
        fresh = self.freeze_seed(_witness(json.loads(seed.witness_bytes)))
        if fresh != seed:
            raise ValueError('Common seed/key/Hmax/domain/native binding mismatch')
        return _witness(json.loads(seed.witness_bytes))

    def durable_binding(self, seed):
        return dict(domain_sha256=digest([json.loads(self.query_bytes), self.tree_sha256,
            self.site_sha256, json.loads(seed.key_bytes), seed.max_depth, self.native_sha256, self.cache_policy]),
            source_sha256=dict(self.source_hashes))

    def recover_durable(self, seed, path):
        from timecut5.durable_incumbent import load_verified
        from timecut5.provenance import primitive
        self.validate_seed(seed)
        with self.context('verification') as context:
            witness, key = load_verified(path, problem_factory=lambda:self.problem(context,seed.max_depth),
                binding_supplier=lambda:self.durable_binding(seed))
        expected = json.loads(seed.key_bytes)
        seed_key = (R(expected[0]),R(expected[1]),expected[2],tuple(map(tuple,expected[3])))
        if key > seed_key:
            raise ValueError('Recovered witness is worse than common seed')
        return dict(accepted_key=primitive(key), feasible_improvement=key < seed_key,
                    seed_key=expected, optimality_claim=False)

    def landmark_router(self, graph):
        from timecut5.routing_config import RoutingConfig
        for array in (graph.source, graph.target, *graph.weights.values()):
            array.flags.writeable = False
        return RoutingConfig().create_router(graph, self.compiler, self.cache / 'landmark', role='landmark', artifact=self.artifact)

    def make_bound(self, context, strategy):
        from timecut5.road_provider import TableFreeRegionBoundProvider
        query = json.loads(self.query_bytes)
        return TableFreeRegionBoundProvider(context.provider, self.sites, self.tree,
            destination_anchor=query['destination'], landmark_anchor=query['origin'],
            site_catalog_sha256=self.site_sha256, router_factory=self.landmark_router,
            alt_strategy=strategy, collect_alt_member_reads=False)

    def solve_exact(self, problem, witness, key, bound, store):
        from timecut5.hierarchy import _solve_hierarchical_problem
        return _solve_hierarchical_problem(problem, True, self.tree, witness,
            verified_primary_upper=key[0], bound_provider=bound, incumbent_hook=store)

    def run_arm(self, strategy, seed, output, *, search_seconds=None, external_phase=False):
        """Actual exact HIER in both arms. All durable replays use new native contexts."""
        from timecut5.bounded import _replay_problem
        from timecut5.hierarchy import _solve_hierarchical_problem
        from timecut5.road_provider import TableFreeRegionBoundProvider
        from timecut5.durable_incumbent import AtomicIncumbentStore
        from timecut5.provenance import primitive
        if strategy not in ('indexed', 'recompute'):
            raise ValueError('Unknown arm')
        output = Path(output); output.mkdir(parents=True, exist_ok=False)
        started = time.monotonic_ns()
        witness = self.validate_seed(seed)
        query = json.loads(self.query_bytes)
        binding = self.durable_binding(seed)
        with ExitStack() as stack:
            verifier = None
            def verification_problem():
                nonlocal verifier
                verifier = self.context('durable_verification')
                return self.problem(verifier, seed.max_depth)
            durable = AtomicIncumbentStore(output / 'incumbent.json', method='hier', problem_factory=verification_problem, binding_supplier=lambda: binding)
            def store(witness, key):
                nonlocal verifier
                try:
                    self.check()
                    durable(witness, key)
                finally:
                    if verifier is not None:
                        verifier.close()
                        verifier = None
            context = stack.enter_context(self.context('search'))
            problem = self.problem(context, seed.max_depth)
            key = _replay_problem(problem, witness)
            if canonical(primitive(key)) != seed.key_bytes:
                raise ValueError('Search seed replay differs')
            store(witness, key)
            bound = self.make_bound(context, strategy)
            setup_ns = time.monotonic_ns() - started
            if external_phase:
                if search_seconds is not None:
                    raise ValueError('External deadline cannot combine with Python timer')
                from .supervisor import publish_phase_entry
                publish_phase_entry()
            search_start = time.monotonic_ns()
            class SearchWindowExpired(Exception):
                pass
            def expire(signum, frame):
                raise SearchWindowExpired('Exact search window expired')
            previous = None
            if search_seconds is not None:
                if type(search_seconds) not in (int, float) or search_seconds <= 0:
                    raise ValueError('Positive search window required')
                if signal.getitimer(signal.ITIMER_REAL)[0]:
                    raise ValueError('Search timer already owned')
                previous = signal.signal(signal.SIGALRM, expire)
                signal.setitimer(signal.ITIMER_REAL, search_seconds)
            solved = None
            try:
                solved = self.solve_exact(problem, witness, key, bound, store)
            except SearchWindowExpired:
                pass
            finally:
                if previous is not None:
                    signal.setitimer(signal.ITIMER_REAL, 0)
                    signal.signal(signal.SIGALRM, previous)
            search_ns = time.monotonic_ns() - search_start
            if solved is not None:
                result = solved.bounded.result
                if result.witness is not None:
                    store(result.witness, result.key)
                if result.status == 'attained_optimum' and (result.witness is None or result.key != durable.best_key):
                    raise ValueError('Exact terminal contradicts durable incumbent')
                if result.status not in ('attained_optimum', 'infimum_unattained'):
                    raise ValueError('Feasible seed contradicts terminal status')
            recovered_key = durable.best_key
            if not external_phase:
                from timecut5.durable_incumbent import load_verified
                try:
                    recovered, recovered_key = load_verified(output / 'incumbent.json', problem_factory=verification_problem, binding_supplier=lambda: binding)
                finally:
                    if verifier is not None:
                        verifier.close()
                        verifier = None
            if recovered_key > key:
                raise ValueError('Durable terminal is worse than common seed')
            report = dict(schema=SCHEMA, strategy=strategy, status=solved.bounded.result.status if solved is not None else 'timeout_feasible_only', result=primitive(solved.canonical()) if solved is not None else None,
                accepted_key=primitive(recovered_key), feasible_improvement=recovered_key < key, optimality_claim=not external_phase and solved is not None and solved.bounded.result.status == 'attained_optimum',
                pending_independent_terminal_verification=external_phase,
                setup_wall_ns=setup_ns, search_wall_ns=search_ns, total_arm_wall_ns=time.monotonic_ns()-started,
                shared_native_build_wall_ns=self.build_wall_ns, native_sha256=self.native_sha256,
                seed_key=json.loads(seed.key_bytes), Hmax=seed.max_depth, tree_sha256=self.tree_sha256,
                durable_writes=durable.writes, alt_member_reads=bound.alt_member_reads, energy_search_only=True,
                full_routing=True, cold_os_cache_claim=False)
            (output / 'result.json').write_bytes(canonical(report))
            return report



def load_graph(directory, bindings):
    """Authenticated fresh immutable arrays; no import of historical launchers."""
    import numpy as np
    import pandas as pd
    from types import SimpleNamespace
    verify_inputs(directory, {n: bindings[n] for n in INPUT_NAMES})
    directory = Path(directory)
    import io
    def authenticated_bytes(name):
        raw=(directory/name).read_bytes()
        if len(raw)!=bindings[name]['size'] or hashlib.sha256(raw).hexdigest()!=bindings[name]['sha256']:
            raise ValueError('Loaded bytes differ from input identity: '+name)
        return raw
    metadata = json.loads(authenticated_bytes('metadata.json'))
    frame = pd.read_parquet(io.BytesIO(authenticated_bytes('edges.parquet')), columns=['source', 'target', 'travel_time_s', 'length_m'])
    arrays = [np.ascontiguousarray(frame[name].to_numpy(dtype=np.int64 if i < 2 else np.float64))
              for i, name in enumerate(('source', 'target', 'travel_time_s', 'length_m'))]
    n, m = metadata['node_count'], metadata['edge_count']
    if (type(n) is not int or n <= 0 or type(m) is not int or m <= 0 or
        any(a.shape != (m,) for a in arrays) or
        any((a < 0).any() or (a >= n).any() for a in arrays[:2]) or
        any(not np.isfinite(a).all() for a in arrays[2:]) or
        (arrays[2] <= 0).any() or (arrays[3] < 0).any()):
        raise ValueError('Graph arrays violate routing contract')
    for array in arrays:
        array.flags.writeable = False
    return SimpleNamespace(node_count=n, edge_count=m, source=arrays[0], target=arrays[1],
                           weights=dict(travel_time=arrays[2], distance=arrays[3]))


def proposal_witness(problem, sequence, charges):
    """Materialize exact events for a proposed charge vector; admission replays it."""
    from timecut5.probe import Event, State, Witness
    from timecut5.bounded import _replay_problem
    time_, energy, anchor = problem.start, problem.initial, problem.origin
    remaining, total, charge_index = problem.initial_remaining, R(0), 0
    events = [Event('initial', anchor, time_, time_, energy, energy)]
    def drive(target):
        nonlocal time_, energy, anchor
        leg = problem.legs[anchor, target]
        old_time, old_energy = time_, energy
        time_ += leg.time; energy -= leg.energy; anchor = target
        events.append(Event('D', target, old_time, time_, old_energy, energy))
    for site, effect in sequence:
        drive(problem.site_anchor(site))
        old_time, old_energy = time_, energy
        release = time_ + problem.overhead
        charge_done = service_done = release
        if effect in ('C', 'CS'):
            amount = R(charges[charge_index]); charge_index += 1
            energy += amount; total += amount
            charge_done += sum((max(R(0), min(energy, hi) - max(old_energy, lo)) * slope
                               for lo, hi, slope, _ in problem.curve.segments), R(0))
        if effect in ('S', 'CS'):
            a, b, duration = problem.schedule
            service_done = max(a, release) + duration
            remaining = 0
        time_ = max(charge_done, service_done)
        events.append(Event(effect, site, old_time, time_, old_energy, energy))
    drive(problem.destination)
    witness = Witness(time_, energy, total - energy, tuple(map(tuple, sequence)),
                      State(anchor, remaining, len(sequence)), tuple(events))
    _replay_problem(problem, witness)
    return witness


def _manifest(path, expected_sha256):
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('Closed manifest digest mismatch')
    manifest = json.loads(raw)
    if manifest.get('schema') != SCHEMA or manifest.get('launchable') is not True:
        raise ValueError('Prospective plan is not launchable')
    if manifest['cases'] != list(DEV_CASES) or manifest['pair_order'] != PAIR_ORDER:
        raise ValueError('Frozen DEV case/order mismatch')
    compiler = manifest['compiler']
    if (set(compiler) != {'path','sha256','version','flags'} or file_hash(compiler['path']) != compiler['sha256'] or
            subprocess.check_output([compiler['path'],'--version'],text=True) != compiler['version'] or
            compiler['flags'] != ['-O3','-std=c++17']):
        raise ValueError('Pinned compiler identity differs')
    if manifest['source'] != source_identity(manifest['repo'],published_commit=manifest['source']['commit'],publication=manifest['source'].get('publication')):
        raise ValueError('Committed executable/runtime closure differs')
    if manifest['limits'] != LIMITS:
        raise ValueError('Frozen stage limits differ')
    if set(manifest['inputs']) != set(INPUT_NAMES) | {'stop_sites.parquet','geographic_screen_v5_grid14.json','fixed_12od_candidate_slate.json'}:
        raise ValueError('Closed nine-input domain required')
    verify_inputs(manifest['input_directory'], {n: manifest['inputs'][n] for n in INPUT_NAMES})
    for name, binding in manifest['inputs'].items():
        path = Path(manifest['input_directory']) / name
        if path.stat().st_size != binding['size'] or file_hash(path) != binding['sha256']:
            raise ValueError('Catalog source drift: ' + name)
    if manifest.get('cache_policy') != CACHE_POLICY:
        raise ValueError('Frozen cache policy differs')
    metadata = json.loads((Path(manifest['input_directory'])/'metadata.json').read_bytes())
    cache_capacity(manifest['cache_policy'], metadata['node_count'])
    return manifest


def _domain(manifest, query, sites, cache):
    directory, bindings = manifest['input_directory'], manifest['inputs']
    tree = original_tree((Path(directory) / 'hierarchy.json').read_bytes(), bindings['hierarchy.json']['sha256'], list(sites))
    return NativeDomain(graph_factory=lambda: load_graph(directory, bindings), query=query, sites=sites,
        tree=tree, source_hashes=dict({n: bindings[n + '.parquet']['sha256'] for n in ('nodes', 'edges')}, source_closure=manifest['source']['closure_sha256'], **{'input:'+n:b['sha256'] for n,b in bindings.items()}), cache=cache,
        compiler=manifest['compiler']['path'], cache_policy=manifest['cache_policy'])


def prepare_case(manifest, case_id, output, *, domain_factory=None):
    """Charged common preparation. No previous witness, timing, or search reused."""
    from timecut5.real_adapter import site_catalog_digest
    from timecut5.sparse_seed import SparseSeedCatalog, sparse_domain_digest, replay_sparse_seed, SeedInfeasible
    from timecut5.deployable import iter_constructive_seed_candidates
    from timecut5.provenance import primitive
    from dataclasses import asdict
    domain_factory = domain_factory or _domain
    started = time.monotonic_ns()
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    directory, bindings = manifest['input_directory'], manifest['inputs']
    query, sites, _ = extract_case(directory, case_id, {n: bindings[n] for n in INPUT_NAMES}, od07_baseline=True)
    domain = domain_factory(manifest, query, sites, output / 'native')
    proposal_receipt = None
    if case_id.startswith('OD07_'):
        from .candidates import repair_od07
        pools = json.loads((Path(directory) / 'pools.json').read_bytes())['pools']
        baseline = next(p for p in pools if p['od_id'] == 'OD07')['sites']
        with domain.context('generation') as context:
            sources = {k: context.provider.source_sha256[k] for k in ('nodes','edges','router','anchors','tie_policy')}
            query, sites, proposal_receipt = repair_od07(directory, bindings, context.provider.graph, context.router, query, sites, sources)
        domain = domain_factory(manifest, query, sites, output / 'native')
    # The new energy policy belongs to the new experiment domain, never silently
    # to the old query's historical sparse-domain hash.
    with domain.context('generation') as context:
        query = dict(query, sparse_domain_sha256=sparse_domain_digest(context.provider.source_sha256,
            site_catalog_digest(sites), digest(sorted(sites)), query['hierarchy_sha256'], query['origin'], query['destination']))
    domain = domain_factory(manifest, query, sites, output / 'native')
    with domain.context('generation') as context:
        catalog = SparseSeedCatalog(context.provider, sites, origin_anchor=query['origin'], destination_anchor=query['destination'],
            nodes_path=Path(directory)/'nodes.parquet', edges_path=Path(directory)/'edges.parquet',
            site_catalog_sha256=site_catalog_digest(sites), hierarchy_sha256=query['hierarchy_sha256'], candidate_sha256=digest(sorted(sites)))
        witness = None
        for ordinal, (sequence, charges) in enumerate(iter_constructive_seed_candidates(query, catalog)):
            try:
                replay = replay_sparse_seed(query, catalog, sequence, charges)
            except SeedInfeasible:
                continue
            witness = proposal_witness(domain.problem(context), sequence, charges)
            break
        if witness is None:
            raise ValueError('Deterministic proposal stream produced no feasible common seed')
    seed = domain.freeze_seed(witness)
    # Separate sparse edge/physical replay, fresh verification-role native context.
    with domain.context('verification') as context:
        catalog = SparseSeedCatalog(context.provider, sites, origin_anchor=query['origin'], destination_anchor=query['destination'],
            nodes_path=Path(directory)/'nodes.parquet', edges_path=Path(directory)/'edges.parquet',
            site_catalog_sha256=site_catalog_digest(sites), hierarchy_sha256=query['hierarchy_sha256'], candidate_sha256=digest(sorted(sites)))
        replayed = replay_sparse_seed(query, catalog, witness.pi,
            tuple(e.departure_energy-e.arrival_energy for e in witness.events if e.effect in ('C','CS')))
        if canonical(primitive(replayed['lex_key'])) != seed.key_bytes:
            raise ValueError('Independent common sparse seed replay differs')
    seed_record = asdict(seed)
    for name in ('witness_bytes', 'key_bytes'):
        seed_record[name] = seed_record[name].decode()
    receipt = dict(schema=SCHEMA, status='common_feasible_seed', case_id=case_id, query=query,
        sites=[dict(site_id=s.site_id, anchor_id=s.anchor_id, effects=list(s.effects)) for s in sites.values()],
        tree_sha256=domain.tree_sha256, seed=seed_record, proposal_ordinal=ordinal,
        candidate_repair=proposal_receipt, native=dict(router=domain.artifact.receipt, energy=domain.energy_artifact.receipt),
        charged_wall_ns=time.monotonic_ns()-started, seed_policy='first_feasible_streamed_proposal_fresh_double_replay_v1',
        source=manifest['source'], inputs=bindings, cache_policy=domain.cache_policy)
    (output/'common.json').write_bytes(canonical(receipt))
    return receipt


PAIR_ORDER = [
    ['OD02_energy_only_soc3_10', ['indexed', 'recompute']],
    ['OD07_energy_and_scheduled_soc3_10', ['recompute', 'indexed']],
    ['OD10_energy_only_soc19_25', ['indexed', 'recompute']],
    ['OD10_energy_only_soc19_25', ['recompute', 'indexed']],
    ['OD07_energy_and_scheduled_soc3_10', ['indexed', 'recompute']],
    ['OD02_energy_only_soc3_10', ['recompute', 'indexed']],
]
LIMITS = dict(search_seconds=120, stage_wall_seconds=600, worker_cpu_seconds=600,
              address_space_bytes=8*1024**3, verification_wall_seconds=180,
              verification_cpu_seconds=120, parent_cpu_soft_seconds=90, parent_cpu_hard_policy='preserve_inherited_at_least_601')


def worker(manifest, operation, case_id, common_path=None, common_sha256=None, strategy=None, search_directory=None, search_receipt_sha256=None, *, domain_factory=None):
    domain_factory = domain_factory or _domain
    from timecut5.real_legs import RealSite
    output = Path(os.environ['HIROUTE_OUTPUT_DIR'])
    if operation == 'prepare':
        result = prepare_case(manifest, case_id, output/'prepared', domain_factory=domain_factory)
    else:
        common_bytes=Path(common_path).read_bytes()
        if hashlib.sha256(common_bytes).hexdigest() != common_sha256:
            raise ValueError('Common receipt digest mismatch')
        common = json.loads(common_bytes)
        if common['source'] != manifest['source'] or common['inputs'] != manifest['inputs'] or common['case_id'] != case_id or common.get('cache_policy') != manifest['cache_policy']:
            raise ValueError('Common receipt belongs to another source/case')
        sites = {s['site_id']: RealSite(s['site_id'], s['anchor_id'], tuple(s['effects'])) for s in common['sites']}
        domain = domain_factory(manifest, common['query'], sites, output/'native')
        values = common['seed']
        seed = FrozenSeed(**dict(values, witness_bytes=values['witness_bytes'].encode(), key_bytes=values['key_bytes'].encode()))
        if operation == 'arm':
            result = domain.run_arm(strategy, seed, output/'arm', external_phase=True)
        else:
            from .supervisor import read_result
            if file_hash(Path(search_directory)/'receipt.json') != search_receipt_sha256:
                raise ValueError('Search receipt identity changed')
            search_receipt = read_result(search_directory)
            phase = search_receipt.get('phase_budget', {})
            identity = phase.get('identity', {})
            if (identity.get('common_sha256') != common_sha256 or identity.get('case_id') != case_id or
                identity.get('strategy') != strategy or
                identity.get('source_closure_sha256') != manifest['source']['closure_sha256']):
                raise ValueError('Search phase belongs to another arm/common source')
            if search_receipt['status'] not in ('SUCCESS','TIMEOUT') or not search_receipt.get('cleanup_verified'):
                raise ValueError('Search has no verified owned terminal')
            result = domain.recover_durable(seed, Path(search_directory)/'artifacts/arm/incumbent.json')
            result['status'] = 'timeout_feasible_only'
            if search_receipt['status'] == 'SUCCESS':
                completed = load_worker_result(search_directory, search_receipt, 'arm', case_id, strategy)
                if completed['accepted_key'] != result['accepted_key']:
                    raise ValueError('Search terminal key differs from independent durable replay')
                result['status'] = completed['status']
                result['optimality_claim'] = completed['status'] == 'attained_optimum'
            result['search_status'] = search_receipt['status']
            (output/'verification.json').write_bytes(canonical(result))
    return result



def _run_plan(manifest_path, manifest_sha256, output, cpu, *, scope,
              manifest_loader=None, worker_module='experiments.mechanism_recovery_v1.run',
              fixed_cases=None, fixed_pairs=None, exact_phase_seconds=120):
    """One sequential supervisor; all predeclared arms remain in the ledger."""
    from .supervisor import run, Limits, PhaseBudget
    import resource
    if scope not in ('full_batch','od02_gate'):
        raise ValueError('Unknown fixed execution scope')
    if type(exact_phase_seconds) is not int or exact_phase_seconds not in (120, 240):
        raise ValueError('Exact phase must be the explicit integer120 or240')
    gate = scope == 'od02_gate'
    cases = DEV_CASES[:1] if gate else DEV_CASES
    pairs = PAIR_ORDER[:1] if gate else PAIR_ORDER
    if fixed_cases is not None:
        cases = tuple(fixed_cases)
    if fixed_pairs is not None:
        pairs = fixed_pairs
    batch_cpu_started=time.process_time()
    manifest = (manifest_loader or _manifest)(manifest_path, manifest_sha256)
    expected_limits = dict(LIMITS, search_seconds=exact_phase_seconds)
    if (exact_phase_seconds == 240 or 'limits' in manifest) and canonical(manifest.get('limits')) != canonical(expected_limits):
        raise ValueError('Declared manifest limits differ from fixed exact phase and unchanged stage caps')
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    if cpu not in os.sched_getaffinity(0):
        raise ValueError('Requested CPU unavailable')
    os.sched_setaffinity(0, {cpu})
    _, inherited_hard = resource.getrlimit(resource.RLIMIT_CPU)
    if inherited_hard != resource.RLIM_INFINITY and inherited_hard < LIMITS['worker_cpu_seconds'] + 1:
        raise ValueError('Inherited CPU hard limit cannot admit worker601s')
    # A direct child's hard limit cannot exceed its parent's inherited hard cap.
    # Keep that cap; the parent has a90s soft limit and is not claimed hard100.
    import math
    parent_deadline=batch_cpu_started+LIMITS['parent_cpu_soft_seconds']
    resource.setrlimit(resource.RLIMIT_CPU, (math.ceil(parent_deadline), inherited_hard))
    def parent_expired(signum,frame):
        raise RuntimeError('Total orchestration CPU budget exhausted')
    signal.signal(signal.SIGXCPU,parent_expired)
    limits = Limits(wall_seconds=LIMITS['stage_wall_seconds'], cpu_seconds=LIMITS['worker_cpu_seconds'],
                    address_space_bytes=LIMITS['address_space_bytes'], cpu=cpu)
    verification_limits = Limits(wall_seconds=LIMITS['verification_wall_seconds'], cpu_seconds=LIMITS['verification_cpu_seconds'], address_space_bytes=LIMITS['address_space_bytes'], cpu=cpu)
    arms=[dict(case=case, strategy=strategy, pair=i, status='PENDING')
          for i, (case, order) in enumerate(pairs) for strategy in order]
    stages=[dict(id='prepare-'+case,operation='prepare',case=case,status='PENDING') for case in cases]
    for index, arm in enumerate(arms):
        for operation in ('search','verify'):
            stages.append(dict(id=f'{operation}-{index}',operation=operation,case=arm['case'],strategy=arm['strategy'],status='PENDING'))
    ledger = dict(schema=manifest.get('schema', SCHEMA), scope=scope, denominator=len(stages), manifest_sha256=manifest_sha256,
        common={}, arms=arms, stages=stages, status='RUNNING')
    stage_by_id={row['id']:row for row in stages}
    def record_stage(identifier,receipt):
        stage_by_id[identifier]['status']=receipt['status']
    def admit(directory, receipt, operation, case, strategy=None, stage_id=None, arm=None):
        if receipt['status'] != 'SUCCESS':return None
        try:
            return load_worker_result(directory,receipt,operation,case,strategy)
        except (ValueError, KeyError, TypeError, OSError) as exc:
            ledger['artifact_admission_error'] = dict(directory=str(directory), error=str(exc))
            stage_by_id[stage_id].update(status='UNKNOWN', reason='artifact_admission_failed')
            if arm is not None:arm['status']='UNKNOWN'
            ledger['status']='UNKNOWN';save()
            return None
    def block_remaining():
        for stage in stages:
            if stage['status']=='PENDING':stage['status']='BLOCKED'
        for arm in arms:
            if arm['status']=='PENDING':arm['status']='BLOCKED'
    def save():
        ledger['parent_cpu_seconds']=time.process_time()-batch_cpu_started
        temporary=output/'ledger.tmp';temporary.write_bytes(canonical(ledger));os.replace(temporary,output/'ledger.json')
    def can_launch():
        if time.process_time() >= parent_deadline-10:
            ledger['status']='PARENT_CPU_BUDGET_EXHAUSTED'
            ledger['parent_cpu_seconds']=time.process_time()-batch_cpu_started
            save();return False
        return True
    def command(operation, case):
        return [sys.executable, '-m', worker_module, '--worker', operation,
                '--manifest', str(Path(manifest_path).resolve()), '--manifest-sha256', manifest_sha256, '--case', case]
    save()
    for case in cases:
        if not can_launch():return ledger
        directory = output / ('prepare-' + case)
        receipt = run(command('prepare',case), output_dir=directory, limits=limits, cwd=manifest['repo'])
        ledger['common'][case] = receipt; record_stage('prepare-'+case,receipt); save()
        admit(directory,receipt,'prepare',case,stage_id='prepare-'+case)
        if ledger['status']=='UNKNOWN':return ledger
        if receipt['status'] == 'UNKNOWN':
            ledger['status']='UNKNOWN';save();return ledger
        if gate and receipt['status'] != 'SUCCESS':
            ledger['status']='FAILED_COMMON_PREPARATION';block_remaining();save();return ledger
    for index, arm in enumerate(ledger['arms']):
        if not can_launch():return ledger
        case=arm['case']
        if ledger['common'][case]['status'] != 'SUCCESS':
            arm['status']='BLOCKED_COMMON_PREPARATION'
            stage_by_id[f'search-{index}']['status']='BLOCKED_COMMON_PREPARATION'
            stage_by_id[f'verify-{index}']['status']='BLOCKED_COMMON_PREPARATION'
            save();continue
        common=output/('prepare-'+case)/'artifacts/prepared/common.json'
        argv=command('arm',case)+['--common',str(common.resolve()),'--common-sha256',file_hash(common),'--strategy',arm['strategy']]
        import secrets
        identity=dict(nonce=secrets.token_hex(16), manifest_sha256=manifest_sha256,
            source_closure_sha256=manifest['source']['closure_sha256'], common_sha256=file_hash(common),
            case_id=case,strategy=arm['strategy'],arm_index=str(index))
        search_directory=output/f'arm-{index:02d}'
        receipt=run(argv,output_dir=search_directory,limits=limits,cwd=manifest['repo'],
            phase_budget=PhaseBudget(seconds=exact_phase_seconds,identity=identity))
        arm.update(status=receipt['status'],receipt=receipt);record_stage(f'search-{index}',receipt);save()
        admit(search_directory,receipt,'arm',case,arm['strategy'],f'search-{index}',arm)
        if ledger['status']=='UNKNOWN':return ledger
        if receipt['status']=='UNKNOWN':
            ledger['status']='UNKNOWN';save();return ledger
        if gate and receipt['status'] not in ('SUCCESS','TIMEOUT'):
            ledger['status']='FAILED_SEARCH';block_remaining();save();return ledger
        if receipt['status'] in ('SUCCESS','TIMEOUT'):
            if not can_launch():return ledger
            verify_argv=command('verify',case)+['--common',str(common.resolve()),'--common-sha256',file_hash(common),
                '--search-directory',str(search_directory.resolve()),'--search-receipt-sha256',file_hash(search_directory/'receipt.json'),'--strategy',arm['strategy']]
            verified=run(verify_argv,output_dir=output/f'verify-{index:02d}',limits=verification_limits,cwd=manifest['repo'])
            arm['verification']=verified
            full = admit(output/f'verify-{index:02d}',verified,'verify',case,arm['strategy'],f'verify-{index}',arm)
            if ledger['status']=='UNKNOWN':save();return ledger
            arm['status']=full['status'] if full is not None else 'VERIFICATION_'+verified['status']
            record_stage(f'verify-{index}',verified);save()
            if verified['status']=='UNKNOWN':
                ledger['status']='UNKNOWN';save();return ledger
            if gate and verified['status']!='SUCCESS':
                ledger['status']='FAILED_VERIFICATION';block_remaining();save();return ledger
        else:
            stage_by_id[f'verify-{index}']['status']='BLOCKED_SEARCH_FAILED';save()
    if not can_launch():return ledger
    ledger['status']='COMPLETED';save();return ledger


def run_batch(manifest_path, manifest_sha256, output, cpu):
    return _run_plan(manifest_path,manifest_sha256,output,cpu,scope='full_batch')


def run_gate(manifest_path, manifest_sha256, output, cpu):
    """Fixed OD02 indexed/recompute integration gate, never an arbitrary subset."""
    return _run_plan(manifest_path,manifest_sha256,output,cpu,scope='od02_gate')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--plan', action='store_true')
    choice.add_argument('--worker', choices=('prepare','arm','verify'))
    choice.add_argument('--batch', action='store_true')
    choice.add_argument('--gate', action='store_true')
    parser.add_argument('--output');parser.add_argument('--cpu',type=int)
    parser.add_argument('--manifest');parser.add_argument('--manifest-sha256')
    parser.add_argument('--case', choices=DEV_CASES)
    parser.add_argument('--common');parser.add_argument('--common-sha256')
    parser.add_argument('--search-directory');parser.add_argument('--search-receipt-sha256')
    parser.add_argument('--strategy', choices=('indexed','recompute'))
    args = parser.parse_args()
    if args.plan:
        print(Path(__file__).with_name('manifest.json').read_text())
        return
    if args.batch or args.gate:
        if args.output is None or args.cpu is None:
            parser.error('--batch/--gate requires --output and --cpu')
        if args.case is not None or args.strategy is not None:
            parser.error('--batch/--gate has fixed cases and strategies')
        ledger = (run_gate if args.gate else run_batch)(args.manifest,args.manifest_sha256,args.output,args.cpu)
        return 0 if ledger['status']=='COMPLETED' else 1
    manifest = _manifest(args.manifest, args.manifest_sha256)
    if args.case is None:
        parser.error('--case is required')
    result = worker(manifest, args.worker, args.case, args.common, args.common_sha256, args.strategy, args.search_directory, args.search_receipt_sha256)
    _manifest(args.manifest, args.manifest_sha256)
    receipt = Path(os.environ['HIROUTE_WORKER_RECEIPT'])
    receipt.write_bytes(canonical(dict(status='COMPLETED', result=result_envelope(
        os.environ['HIROUTE_OUTPUT_DIR'], args.worker, args.case, args.strategy))))


if __name__ == '__main__':
    sys.exit(main())
