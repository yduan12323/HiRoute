"""Verify a sealed assignment against its original DAG and raw path evidence."""
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import time

from .io import load, sha, verify_paths
from .provenance import source


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def verify_bundle(bundle_path, root, output, limit_s=120):
    from contextlib import ExitStack
    from unittest.mock import patch
    from .exact_leg_table import ExactLegTable
    from .exact_physical_adapter import Encoding, table_relevant_depth, replay, validate
    from .import_strict_candidate import verify_candidate
    from .split_leg_table import read as read_split
    from .streaming_road_graph import connect

    started = time.monotonic()
    def check():
        if time.monotonic() - started >= limit_s:
            raise TimeoutError('independent verification deadline')
    root, output = Path(root).resolve(), Path(output).resolve()
    bundle_path = Path(bundle_path).resolve()
    original_bundle_sha = sha(bundle_path, check)
    bundle = load(bundle_path)
    fields = {'schema', 'files', 'table', 'parameters', 'incumbent', 'graph_db', 'origin', 'depth', 'expected'}
    if set(bundle) != fields or bundle['schema'] != 'hiroute.compare_bundle.v1':
        raise ValueError('strict compare_bundle.v1 fields required')
    files = {}
    def path(name):
        p = (root / name).resolve()
        if Path(name).is_absolute() or not p.is_relative_to(root):
            raise ValueError('unsafe bundle path')
        return p
    for row in bundle['files']:
        if set(row) != {'path', 'bytes', 'sha256'} or row['path'] in files:
            raise ValueError('duplicate or invalid artifact descriptor')
        files[row['path']] = row
    def sealed(name):
        if name not in files:
            raise ValueError('unsealed required input: ' + name)
        return path(name)
    def verify_inputs():
        if sha(bundle_path, check) != original_bundle_sha:
            raise ValueError('bundle changed during verification')
        for name, row in files.items():
            p = path(name)
            if type(row['bytes']) is not int or p.stat().st_size != row['bytes'] or sha(p, check) != row['sha256']:
                raise ValueError('artifact integrity mismatch: ' + name)
    verify_inputs()
    for key in ('parameters', 'incumbent', 'graph_db'):
        sealed(bundle[key])
    origin = path(bundle['origin'])
    for suffix in ('consumer-admission.json', 'audit-root/SMT/0001.dag.smt2', 'audit-root/SMT/candidate.unverified.json'):
        sealed((Path(bundle['origin']) / suffix).as_posix())
    table_spec = bundle['table']
    if set(table_spec) != {'format', 'path'}:
        raise ValueError('table format/path required')
    if table_spec['format'] == 'split':
        for name in ('manifest.json', 'numeric.json', 'paths.index.json', 'paths.bin'):
            sealed((Path(table_spec['path']) / name).as_posix())
        table = read_split(path(table_spec['path']), check)
    elif table_spec['format'] == 'json':
        p = sealed(table_spec['path'])
        if p.stat().st_size > 256 * 1024**2:
            raise ValueError('JSON table quota; use split format')
        table = ExactLegTable.from_bytes(p.read_bytes(), check)
    else:
        raise ValueError('unsupported table format')
    try:
        parameters, incumbent = load(sealed(bundle['parameters'])), load(sealed(bundle['incumbent']))
        depth, upper = table_relevant_depth(table, parameters, incumbent)
        if type(bundle['depth']) is not int or bundle['depth'] < depth:
            raise ValueError('original DAG depth is below complete table-derived depth')
        expected = dict(bundle['expected'])
        if set(expected) != {'original_source', 'producer_files', 'admission_sha256', 'candidate_sha256', 'audit_sha256', 'audit_payload_sha256'}:
            raise ValueError('original admission and candidate/DAG provenance required')
        expected['verifier_source'] = source()
        # This entry point never asks Z3 to solve, optimize, parse or run tactics.
        with ExitStack() as stack:
            for name in ('Solver', 'Optimize', 'Tactic', 'parse_smt2_file', 'parse_smt2_string'):
                stack.enter_context(patch('z3.' + name, side_effect=AssertionError('solver-free verification')))
            m = Encoding(table, parameters, bundle['depth'], upper['key'][0], check, finite_lookup=True)
            x, y = m.state_copy(check), m.state_copy(check)
            audit = output / 'verification'
            comparison = verify_candidate(origin, expected, audit, m, x, y, table, parameters, incumbent, check)
            witness_path = audit / 'separate-witness.verified.json'
            stored = load(witness_path)
            verified = comparison['result']
            payload_sha = hashlib.sha256(canonical(verified)).hexdigest()
            if (canonical(stored['result']) != canonical(verified) or stored['result_sha256'] != payload_sha or
                    comparison['receipt']['result_sha256'] != payload_sha or
                    stored['verification'] != 'VERIFIED_REPLAY' or stored['requires_successful_consumer_terminal'] is not True):
                raise ValueError('verified witness receipt mismatch')
            w = verified['witness']
            replayed = replay(table, parameters, w['plan'], w['charges'], w['initial_wait'])
            if replayed['key'][0] != Fraction(verified['primary_value']) or not replayed['key'][0] < upper['key'][0]:
                raise ValueError('final strict improvement replay mismatch')
            db = connect(sealed(bundle['graph_db']))
            try:
                def edge(eid):
                    check()
                    row = db.execute('SELECT u,v,t,l FROM edges WHERE eid=? COLLATE BINARY', (eid,)).fetchone()
                    if row is None:
                        raise ValueError('missing raw edge')
                    return row
                pairs = [(p.source, p.target) for p in table.literal_plan_legs(w['plan'], validate(table, parameters).pending)]
                pairs += [(p.source, p.target) for p in table.literal_plan_legs(incumbent['plan'], validate(table, parameters).pending)]
                paths = verify_paths(table, pairs, edge, check)
            finally:
                db.close()
            verify_inputs()
            if source() != expected['verifier_source']:
                raise ValueError('verifier code/environment changed within this run')
            check()
            return dict(status='COMPLETE', comparison=verified, output_path_checks=paths,
                        bundle_sha256=original_bundle_sha, source=expected['verifier_source'],
                        verified_witness_file_sha256=sha(witness_path, check), verified_payload_sha256=payload_sha,
                        original_run_status='UNKNOWN', original_run_completed_in_budget=False,
                        optimality_certified=False, full_key_optimality_certified=False, road_selection_certified=False,
                        scope='Strict feasible improvement conditional on the supplied selected-leg table',
                        elapsed_s=time.monotonic() - started)
    finally:
        if hasattr(table, '_path_store'):
            table._path_store.close()
