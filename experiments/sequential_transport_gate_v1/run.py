"""Closed, one-attempt OD07 sequential feasible-construction transport gate."""
from __future__ import annotations

import argparse
from fractions import Fraction as R
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time

from experiments.mechanism_recovery_v1 import run as base
from experiments.mechanism_recovery_v1.candidates import CASE_ID, repair_od07
from experiments.mechanism_recovery_v1.supervisor import Limits, run, _atomic

SCHEMA = 'hiroute.sequential_transport_gate.v1'
OPERATIONS = ('construct', 'replay-sequential', 'replay-joint')
TEMPLATE = Path(__file__).with_name('manifest.json')
canonical, digest, file_hash = base.canonical, base.digest, base.file_hash


def load_manifest(path, sha256):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != sha256:
        raise ValueError('Manifest digest differs')
    m = json.loads(raw)
    frozen = json.loads(TEMPLATE.read_bytes())
    if m.get('launchable') is not True:
        raise ValueError('Prospective gate is not launchable')
    for field in ('schema', 'inputs', 'cache_policy', 'case_id', 'Hmax',
                  'candidate_count', 'policy', 'holdout', 'attempts', 'limits', 'comparator'):
        if m.get(field) != frozen[field]:
            raise ValueError('Frozen gate policy differs: ' + field)
    if not Path(m['repo']).is_absolute() or not Path(m['input_directory']).is_absolute():
        raise ValueError('Explicit absolute source/input paths required')
    if m['source'] != base.source_identity(m['repo'], published_commit=m['source']['commit'],
                                         publication=m['source'].get('publication')):
        raise ValueError('Published source/runtime closure differs')
    c = m['compiler']
    if (set(c) != {'path', 'sha256', 'version', 'flags'} or
            file_hash(c['path']) != c['sha256'] or c['flags'] != ['-O3', '-std=c++17'] or
            subprocess.check_output([c['path'], '--version'], text=True) != c['version']):
        raise ValueError('Compiler identity differs')
    base.verify_inputs(m['input_directory'], {n: m['inputs'][n] for n in base.INPUT_NAMES})
    for name, expected in m['inputs'].items():
        path = Path(m['input_directory'])/name
        if path.stat().st_size != expected['size'] or file_hash(path) != expected['sha256']:
            raise ValueError('Input identity differs: '+name)
    # Hash bytes only. Construction never parses comparator routes or charges.
    if file_hash(Path(m['repo']) / m['comparator']['bundle_path']) != m['comparator']['bundle_sha256']:
        raise ValueError('Predeclared comparator bundle differs')
    return m


def catalog_for(context, m, query, sites):
    from timecut5.real_adapter import site_catalog_digest
    from timecut5.sparse_seed import SparseSeedCatalog
    root = Path(m['input_directory'])
    return SparseSeedCatalog(context.provider, sites, origin_anchor=query['origin'],
        destination_anchor=query['destination'], nodes_path=root/'nodes.parquet',
        edges_path=root/'edges.parquet', site_catalog_sha256=site_catalog_digest(sites),
        hierarchy_sha256=query['hierarchy_sha256'], candidate_sha256=digest(sorted(sites)))


def construct(m, output):
    from timecut5.real_adapter import site_catalog_digest
    from timecut5.sparse_seed import first_sequential_feasible, sparse_domain_digest
    from timecut5.provenance import primitive
    started, cpu = time.monotonic_ns(), time.process_time_ns()
    query, sites, _ = base.extract_case(m['input_directory'], CASE_ID,
        {n: m['inputs'][n] for n in base.INPUT_NAMES}, od07_baseline=True)
    original_query = dict(query)
    domain = base._domain(m, query, sites, output/'native-baseline')
    with domain.context('generation') as context:
        sources = {k: context.provider.source_sha256[k]
                   for k in ('nodes', 'edges', 'router', 'anchors', 'tie_policy')}
        query, sites, repair = repair_od07(m['input_directory'], m['inputs'],
            context.provider.graph, context.router, query, sites, sources)
    if len(sites) != 149:
        raise ValueError('Complete repaired candidate count differs')
    query = dict(query, H_ref=37)
    domain = base._domain(m, query, sites, output/'native-repaired')
    with domain.context('generation') as context:
        query = dict(query, sparse_domain_sha256=sparse_domain_digest(
            context.provider.source_sha256, site_catalog_digest(sites), digest(sorted(sites)),
            query['hierarchy_sha256'], query['origin'], query['destination']))
    domain = base._domain(m, query, sites, output/'native-final')
    binding = dict(schema=SCHEMA, case_id=CASE_ID, Hmax=37, query=query,
        original_query=original_query, sites=[dict(site_id=s.site_id, anchor_id=s.anchor_id,
            effects=list(s.effects)) for s in sites.values()], candidate_repair=repair,
        tree_sha256=domain.tree_sha256, native_sha256=domain.native_sha256,
        native=dict(router=domain.artifact.receipt, energy=domain.energy_artifact.receipt),
        source=m['source'], inputs=m['inputs'], policy=m['policy'],
        optimality_claim=False, comparison_scope='two_feasible_plans_only')
    def persist(event, **snapshot):
        if event != 'first_feasible':
            raise ValueError('Unexpected construction event')
        record = dict(binding, construction=primitive(snapshot), status='first_feasible',
            construction_local_wall_ns=time.monotonic_ns()-started, construction_local_process_cpu_ns=time.process_time_ns()-cpu)
        _atomic(output/'construction.json', record)
    with domain.context('generation') as context:
        result = first_sequential_feasible(query, catalog_for(context, m, query, sites), observer=persist)
    if result['status'] != 'first_feasible':
        _atomic(output/'construction.json', dict(binding, status='unknown', construction=primitive(result)))
        return json.loads((output/'construction.json').read_bytes())
    return json.loads((output/'construction.json').read_bytes())


def read_bound(path, expected):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('Construction artifact binding differs')
    return json.loads(raw)


def comparator_plan(m):
    """Only the joint verification worker calls this, after sequential verification."""
    from timecut5.durable_incumbent import _witness
    ref = m['comparator']
    raw = json.loads((Path(m['repo'])/ref['bundle_path']).read_bytes())['files'][ref['artifact_path']].encode()
    if hashlib.sha256(raw).hexdigest() != ref['artifact_sha256']:
        raise ValueError('Predeclared comparator artifact differs')
    historic = json.loads(raw)
    witness = _witness(historic['payload']['witness'])
    charges = tuple(e.departure_energy-e.arrival_energy for e in witness.events if e.effect in ('C', 'CS'))
    return witness.pi, charges, historic['payload']['binding']


def replay(m, output, operation, construction_path, construction_sha256):
    from timecut5.real_legs import RealSite
    from timecut5.sparse_seed import replay_sparse_seed
    from timecut5.provenance import primitive
    from timecut5.routing_config import require_full_verifier
    record = read_bound(construction_path, construction_sha256)
    if (record['source'] != m['source'] or record['inputs'] != m['inputs'] or
            record['policy'] != m['policy'] or record['case_id'] != CASE_ID or record['Hmax'] != 37 or
            record['query']['H_ref'] != 37 or record['status'] != 'first_feasible'):
        raise ValueError('Construction domain differs')
    sites = {s['site_id']: RealSite(s['site_id'], s['anchor_id'], tuple(s['effects'])) for s in record['sites']}
    if len(sites) != 149 or list(sites) != record['candidate_repair']['insertion_order']:
        raise ValueError('Repaired site domain differs')
    query = record['query']
    domain = base._domain(m, query, sites, output/'native')
    if domain.tree_sha256 != record['tree_sha256'] or domain.native_sha256 != record['native_sha256']:
        raise ValueError('Fresh native/tree identity differs')
    historical_binding = None
    sequential = operation == 'replay-sequential'
    if sequential:
        sequence, charges = record['construction']['sequence'], record['construction']['charges']
    else:
        sequence, charges, historical_binding = comparator_plan(m)
    with domain.context('verification') as context:
        require_full_verifier(context.provider, fresh=True)
        evidence = replay_sparse_seed(query, catalog_for(context, m, query, sites), sequence, charges,
                                     sequential_no_overlap=sequential, include_events=True)
    if sequential and (primitive(evidence['lex_key']) != record['construction']['lex_key'] or
                       primitive(evidence['edge_witnesses']) != record['construction']['edge_witnesses']):
        raise ValueError('Fresh sequential objective or selected paths differ')
    result = dict(schema=SCHEMA, status='fresh_feasible', operation=operation,
        construction_sha256=construction_sha256, policy=m['policy'], query=query,
        sequence=sequence, charges=charges, replay=primitive(evidence), metrics=primitive(metrics(evidence)),
        source=m['source'], native_sha256=domain.native_sha256,
        historical_comparator_binding=historical_binding, historical_certificate_reused=False,
        optimality_claim=False, comparison_scope='two_feasible_plans_only')
    _atomic(output/'result.json', primitive(result))
    return result


def metrics(evidence):
    """Expose only independently replayed quantities, with exact rational units."""
    return dict(J=evidence['lex_key'][0], Q_kwh=evidence['lex_key'][1], H=evidence['lex_key'][2],
        elapsed_s=evidence['elapsed_s'], distance_m=evidence['distance_m'],
        overlap_s=evidence['overlap_s'], service_events=[e for e in evidence['events']
            if e['effect'] in ('S', 'CS')])


def envelope(output, operation):
    name = 'construction.json' if operation == 'construct' else 'result.json'
    raw = (output/name).read_bytes()
    return dict(schema=SCHEMA, operation=operation, artifact=name,
                sha256=hashlib.sha256(raw).hexdigest(), size=len(raw))


def admit(directory, receipt, operation):
    e = receipt['worker_receipt']['result']
    name = 'construction.json' if operation == 'construct' else 'result.json'
    if set(e) != {'schema', 'operation', 'artifact', 'sha256', 'size'} or e['schema'] != SCHEMA or e['operation'] != operation or e['artifact'] != name:
        raise ValueError('Invalid worker envelope')
    path = Path(directory)/'artifacts'/name
    if path.is_symlink() or path.parent.is_symlink() or not 0 < e['size'] <= 16*1024**2 or path.stat().st_size != e['size']:
        raise ValueError('Invalid owned result artifact')
    return read_bound(path, e['sha256'])


def run_gate(manifest_path, manifest_sha256, output, cpu):
    started = time.process_time()
    deadline = started + 120
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    ledger = dict(schema=SCHEMA, status='RUNNING', manifest_sha256=manifest_sha256,
        stages=[dict(operation=op, status='PENDING') for op in OPERATIONS],
        attempts=1, optimality_claim=False, comparison_scope='two_feasible_plans_only')
    def save():
        ledger['controller_cpu_seconds'] = time.process_time()-started
        _atomic(output/'ledger.json', ledger)
    def fail(status, reason):
        ledger.update(status=status, reason=reason)
        for stage in ledger['stages']:
            if stage['status'] == 'PENDING': stage['status'] = 'BLOCKED'
        save()
        return ledger
    save()
    try:
        _, hard = resource.getrlimit(resource.RLIMIT_CPU)
        if hard != resource.RLIM_INFINITY and hard < 241:
            raise ValueError('Inherited CPU hard limit cannot admit construction')
        resource.setrlimit(resource.RLIMIT_CPU, (math.ceil(deadline), hard))
        def expired(signum, frame):
            raise RuntimeError('Controller CPU exhausted')
        signal.signal(signal.SIGXCPU, expired)
        m = load_manifest(manifest_path, manifest_sha256)
        if cpu not in os.sched_getaffinity(0): raise ValueError('Unavailable CPU')
        os.sched_setaffinity(0, {cpu})
        construction = output/'construct'/'artifacts'/'construction.json'
        for stage in ledger['stages']:
            op = stage['operation']
            if time.process_time() >= deadline-10:
                return fail('CONTROLLER_CPU_EXHAUSTED', 'No further worker admitted')
            seconds = 240 if op == 'construct' else 120
            command = [sys.executable, '-m', 'experiments.sequential_transport_gate_v1.run',
                '--worker', op, '--manifest', str(Path(manifest_path).resolve()), '--manifest-sha256', manifest_sha256]
            if op != 'construct':
                command += ['--construction', str(construction.resolve()), '--construction-sha256', file_hash(construction)]
            receipt = run(command, output_dir=output/op, cwd=m['repo'],
                limits=Limits(wall_seconds=seconds, cpu_seconds=seconds,
                              address_space_bytes=m['limits']['address_space_bytes'], cpu=cpu))
            stage.update(status=receipt['status'], receipt=receipt); save()
            if receipt['status'] != 'SUCCESS':
                return fail(receipt['status'], op+' did not complete; no retry')
            try:
                result = admit(output/op, receipt, op)
                if result['status'] != ('first_feasible' if op == 'construct' else 'fresh_feasible'):
                    raise ValueError('Non-feasible worker result')
            except (ValueError, KeyError, TypeError, OSError) as exc:
                stage['status'] = 'UNKNOWN'
                return fail('UNKNOWN', str(exc))
        ledger['comparison'] = {op: json.loads((output/op/'artifacts'/'result.json').read_bytes())['metrics']
                                for op in OPERATIONS[1:]}
        ledger['status'] = 'COMPLETED'; save(); return ledger
    except (ValueError, KeyError, TypeError, OSError, RuntimeError) as exc:
        return fail('BLOCKED', str(exc))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument('--plan', action='store_true')
    group.add_argument('--gate', action='store_true')
    group.add_argument('--worker', choices=OPERATIONS)
    for name in ('manifest', 'manifest-sha256', 'output', 'construction', 'construction-sha256'):
        p.add_argument('--'+name)
    p.add_argument('--cpu', type=int)
    args = p.parse_args()
    if args.plan:
        print(TEMPLATE.read_text()); return 0
    if args.gate:
        return int(run_gate(args.manifest, args.manifest_sha256, args.output, args.cpu)['status'] != 'COMPLETED')
    m = load_manifest(args.manifest, args.manifest_sha256)
    output = Path(os.environ['HIROUTE_OUTPUT_DIR'])
    if args.worker == 'construct': construct(m, output)
    else: replay(m, output, args.worker, args.construction, args.construction_sha256)
    load_manifest(args.manifest, args.manifest_sha256)
    _atomic(Path(os.environ['HIROUTE_WORKER_RECEIPT']), dict(status='COMPLETED', result=envelope(output, args.worker)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
