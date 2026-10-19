"""Independent REF5 slot for M6-H, with no production optimization fallback.

The shared native router supplies the same physical constants, not a solution.
The independent parser, rational LP/regime enumerator and replay are REF5's.
An external phase supervisor must also enforce 120 seconds aggregate tree CPU
and wall time, including process startup, compilation, serialization and exit.
"""
from contextlib import contextmanager
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import signal
import time

from validation.reference5.real_input import IndependentLegTable
from validation.reference5.real_solver import replay_real_witness, solve_real_case

SCHEMA = 'hiroute.m6h.independent_reference.v1'
BUDGET_SECONDS = 120


class ReferenceUnsupported(ValueError):
    """A known limitation, never an exact-match result."""


class ReferenceBudgetExceeded(BaseException):
    # REF5 catches Exception around LP calls. Resource exhaustion must unwind
    # that loop immediately rather than becoming an uncertified next regime.
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def primitive(value):
    if isinstance(value, F):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [primitive(v) for v in value]
    if isinstance(value, dict):
        return {k: primitive(v) for k, v in value.items()}
    return value


@contextmanager
def bounded_reference():
    """Secondary process-local guards; does not claim aggregate CPU control."""
    kinds = ((signal.ITIMER_REAL, signal.SIGALRM), (signal.ITIMER_PROF, signal.SIGPROF))
    if any(signal.getitimer(kind) != (0.0, 0.0) for kind, _ in kinds):
        raise ValueError('REF requires a fresh process without inherited interval timers')
    handlers = {sig: signal.getsignal(sig) for _, sig in kinds}
    def expired(signum, frame):
        raise ReferenceBudgetExceeded('wall_timeout' if signum == signal.SIGALRM else 'process_cpu_timeout')
    try:
        for kind, sig in kinds:
            signal.signal(sig, expired)
            signal.setitimer(kind, BUDGET_SECONDS)
        yield
    finally:
        for kind, sig in kinds:
            signal.setitimer(kind, 0)
            signal.signal(sig, handlers[sig])


def reference_query(query, seed):
    """Explicit seed-derived depth; fixture H_ref is never an execution bound."""
    h = seed.get('max_depth')
    if type(h) is not int or h < 0:
        raise ValueError('REF requires explicit authenticated nonnegative Hmax')
    key = json.loads(seed['key_bytes'])
    if type(key) is not list or len(key) != 4:
        raise ValueError('Seed requires the complete four-component key')
    overhead, penalty, objective = F(query['overhead_s']), F(query['lambda_stop_s']), F(key[0])
    if overhead <= 0 or overhead + penalty <= 0 or objective < 0 or h != objective // (overhead + penalty):
        raise ValueError('REF Hmax differs from strict common-seed formula')
    # Metadata is passed through unchanged; REF parses physical quantities itself.
    return dict(query, H_ref=h)


def materialize_table(query, sites, provider, *, source_sha256, selection_sha256, hierarchy_sha256):
    """Freeze every directed physical pair including shared-anchor identities.

    provider.leg independently reconstructs selected edges and binary64 totals.
    No distance metric, rerouting, inferred symmetry or fake finite unreachable
    value is introduced. Forward full routing has the accepted target tie rule.
    """
    rows = [dict(site_id=s.site_id, anchor_id=s.anchor_id, effects=list(s.effects)) for s in sites.values()]
    if len({s['site_id'] for s in rows}) != len(rows):
        raise ValueError('Duplicate Site identity')
    anchors = list(dict.fromkeys([query['origin'], *[s['anchor_id'] for s in rows], query['destination']]))
    def encoded(exact, hexadecimal):
        value = float.fromhex(hexadecimal)
        numerator, denominator = value.as_integer_ratio()
        if F(numerator, denominator) != exact:
            raise ValueError('Provider binary64 and exact rational disagree')
        return dict(hex=hexadecimal, ratio=[str(numerator), str(denominator)])
    legs = []
    for source in anchors:
        for target in anchors:
            leg = provider.leg(source, target)
            if leg.source_anchor != source or leg.target_anchor != target:
                raise ValueError('Provider returned another physical pair')
            if leg.reachable and source != target and (leg.time == 0 or leg.actual_length == 0):
                raise ReferenceUnsupported('REF5 immutable parser does not support zero totals between distinct anchors')
            legs.append(dict(source_anchor=source, target_anchor=target, reachable=leg.reachable,
                label_direction=leg.label_direction,
                time_s=encoded(leg.time, leg.time_hex) if leg.reachable else None,
                actual_length_m=encoded(leg.actual_length, leg.length_hex) if leg.reachable else None))
            if hasattr(provider, 'edge_witnesses'):
                edges = provider.edge_witnesses[source, target]
                legs[-1]['selected_edge_indices'] = list(edges) if edges is not None else None
    payload = dict(schema='hiroute.immutable_selected_legs.v1',
        numerical_contract='binary64_totals_as_exact_rationals_v1', anchors=anchors,
        origin_anchor=query['origin'], destination_anchor=query['destination'], sites=rows, legs=legs,
        source_sha256=dict(source_sha256), selection_certificate_sha256=selection_sha256,
        hierarchy_sha256=hierarchy_sha256,
        backend=dict(name='authenticated_native_selected_leg_provider',
            tie_policy='min_time_then_actual_length_then_first_discovery',
            direction_policy='forward_per_source_v1', source_sha256=dict(provider.source_sha256)))
    raw = canonical(payload)
    return IndependentLegTable.from_bytes(raw, hashlib.sha256(raw).hexdigest())


def canonical_outcome(result):
    """Keep exact attainment distinctions; no hypothetical Q for unattained J."""
    status = result.get('status')
    if status == 'attained_optimum':
        key = (result['J'], result['Q_total'], result['H'], result['site_action_tuple'])
        if primitive(key) != primitive(result['lex_key']) or result.get('witness_replayed') is not True:
            raise ValueError('REF attained full key/replay inconsistency')
        return dict(status=status, lex_key=primitive(key))
    if status == 'primary_unattained':
        return dict(status=status, primary_infimum=str(F(result['primary_infimum'])))
    if status == 'secondary_unattained':
        return dict(status=status, J=str(F(result['J'])), secondary_infimum=str(F(result['secondary_infimum'])))
    if status == 'infeasible_within_H_ref':
        return dict(status=status)
    return None


def solve_independent(query, seed, table):
    """Independently certify all admitted depths, retaining strict-bound evidence."""
    query = reference_query(query, seed)
    witness = json.loads(seed['witness_bytes'])
    sequence = witness['pi']
    events = witness['events']
    if any(e.get('effect') not in ('initial','D','C','S','CS') for e in events):
        raise ValueError('Common seed contains an unknown event effect')
    # Physical witnesses include initial/driving events; pi contains only stops.
    # The independent replay below reconstructs all driving and stop semantics.
    actions=[e for e in events if e['effect'] in ('C','S','CS')]
    if [(e['site'], e['effect']) for e in actions] != [tuple(p) for p in sequence]:
        raise ValueError('Common seed events and action sequence differ')
    charges = tuple(F(e['departure_energy']) - F(e['arrival_energy'])
                    for e in events if e['effect'] in ('C', 'CS'))
    replay = replay_real_witness(query, table, sequence, charges)
    if primitive(replay['lex_key']) != json.loads(seed['key_bytes']):
        raise ValueError('Independent REF common-seed replay contradicts authenticated full key')
    solved = solve_real_case(query, table, keep_evidence=False, regime_limit=None,
        seed_witness=dict(sequence=sequence, charges=charges))
    if type(solved) is not dict or type(solved.get('result')) is not dict:
        raise ValueError('Malformed independent REF result')
    if solved['result'].get('status') == 'invalid_input':
        raise ValueError('Independent REF invalid input: ' + str(solved['result'].get('reason')))
    if solved['result'].get('status') not in ('attained_optimum', 'primary_unattained', 'secondary_unattained', 'infeasible_within_H_ref', 'unresolved'):
        raise ValueError('Unexpected independent REF result status')
    outcome = canonical_outcome(solved['result'])
    if solved.get('H_ref') != seed['max_depth']:
        raise ValueError('Independent reference returned another depth')
    if solved.get('all_regimes_certified') is not True or outcome is None:
        return dict(status='UNKNOWN', reason='independent_reference_unresolved',
            independent_exact=False, canonical_outcome=None, reference_status=solved['result']['status'])
    if outcome['status'] == 'infeasible_within_H_ref':
        raise ValueError('Independent REF infeasibility contradicts its own common-seed replay')
    if outcome['status'] == 'attained_optimum':
        result = solved['result']
        # Parse the frozen bytes again, then independently replay the attained
        # winner; no result-supplied drive/time/energy stream is trusted.
        fresh = IndependentLegTable.from_bytes(table.raw_bytes, table.payload_sha256)
        checked = replay_real_witness(query, fresh, result['site_action_tuple'], result['charges'])
        if primitive(checked['lex_key']) != outcome['lex_key']:
            raise ValueError('Independent REF attained winner fails fresh replay')
    witness_record = (dict(sequence=primitive(solved['result']['site_action_tuple']),
        charges=primitive(solved['result']['charges'])) if outcome['status'] == 'attained_optimum' else None)
    return dict(status='SUCCESS', independent_exact=True, canonical_outcome=outcome, witness=witness_record,
        reference_status=solved['result']['status'], all_regimes_certified=True,
        witness_replayed=outcome['status'] == 'attained_optimum',
        regime_counts={k: v for k, v in solved.items() if k.endswith('_count')},
        depth_certificate=primitive(solved['preflight']['depth_certificate']))


def run_reference(manifest, case_id, common, output):
    """Called only inside a supervised REF phase after authenticated common load."""
    from . import physical
    from .physical_inputs import require_root_freeze, spec_for
    require_root_freeze()
    started = time.monotonic_ns()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    physical.validate_common(common, case_id, manifest)
    query = common['query']
    spec = spec_for(manifest, case_id)
    if spec['candidate_count'] != 8 or F(query['initial_energy_kwh']) / F(query['capacity_kwh']) != F(3, 10):
        raise ValueError('Independent REF slot is only registered for low-SOC N8')
    envelope = dict(schema=SCHEMA, case_id=case_id, Hmax=common['seed']['max_depth'],
        common_sha256=digest(common), query_sha256=digest(query), manifest_sha256=digest(manifest),
        optimizer='validation.reference5.real_solver.solve_real_case',
        physical_router_shared=True, production_optimizer_used=False,
        budget_seconds=BUDGET_SECONDS, aggregate_cpu_enforcement='external_phase_supervisor_required')
    try:
        with bounded_reference():
            _, sites, _ = physical.extract_case(manifest['input_directory'], case_id, manifest['inputs'], manifest)
            domain = physical.domain_factory(manifest, query, sites, output/'native', arm='flat',
                case_id=case_id, admitted_hmax=common['seed']['max_depth'])
            with domain.context('verification') as context:
                table = materialize_table(query, sites, context.provider,
                    source_sha256=domain.source_hashes, selection_sha256=manifest['selection_sha256'],
                    hierarchy_sha256=query['hierarchy_sha256'])
            (output/'selected_legs.json').write_bytes(table.raw_bytes)
            envelope['leg_payload_sha256'] = table.payload_sha256
            result = solve_independent(query, common['seed'], table)
    except ReferenceUnsupported as exc:
        result = dict(status='UNKNOWN', reason='unsupported_physical_domain', detail=str(exc),
            independent_exact=False, canonical_outcome=None)
    except ReferenceBudgetExceeded as exc:
        result = dict(status='UNKNOWN', reason=str(exc), independent_exact=False, canonical_outcome=None)
    # Invalid input, binding drift, contradictory replay/key, and unexpected
    # failures deliberately propagate; they must not be relabeled a timeout.
    envelope.update(result, charged_wall_ns=time.monotonic_ns()-started)
    (output/'reference.json').write_bytes(canonical(envelope))
    return envelope


RESULT_SCHEMA = 'hiroute.m6h.reference_result.v1'
RESULT_PATH = 'reference/reference.json'
MAX_RESULT_BYTES = 1024 * 1024


def _summary(result):
    if result.get('schema') != SCHEMA or result.get('status') not in ('SUCCESS', 'UNKNOWN'):
        raise ValueError('Unknown REF result schema/status')
    return {k: result[k] for k in ('status', 'Hmax', 'common_sha256', 'manifest_sha256', 'independent_exact', 'canonical_outcome')}


def result_envelope(artifacts, case_id):
    raw = (Path(artifacts)/RESULT_PATH).read_bytes()
    if not 0 < len(raw) <= MAX_RESULT_BYTES:
        raise ValueError('REF result exceeds bounded artifact contract')
    result = json.loads(raw)
    if result['case_id'] != case_id:
        raise ValueError('REF result case differs')
    return dict(schema=RESULT_SCHEMA, operation='ref', case_id=case_id,
        artifact=dict(path=RESULT_PATH, size=len(raw), sha256=hashlib.sha256(raw).hexdigest()), summary=_summary(result))


def load_worker_result(directory, receipt, case_id, *, common, manifest):
    """Validate the supervisor-authenticated control record and owned artifact."""
    if receipt.get('status') != 'SUCCESS' or receipt.get('cleanup_verified') is not True:
        raise ValueError('REF worker did not complete with verified cleanup')
    envelope = receipt['worker_receipt']['result']
    if (set(envelope) != {'schema', 'operation', 'case_id', 'artifact', 'summary'} or
        envelope['schema'] != RESULT_SCHEMA or envelope['operation'] != 'ref' or envelope['case_id'] != case_id):
        raise ValueError('REF envelope identity differs')
    binding = envelope['artifact']
    if (set(binding) != {'path', 'size', 'sha256'} or binding['path'] != RESULT_PATH or
        type(binding['size']) is not int or not 0 < binding['size'] <= MAX_RESULT_BYTES):
        raise ValueError('REF artifact binding differs')
    root = Path(directory)/'artifacts'
    path = root
    for part in Path(RESULT_PATH).parts:
        path = path/part
        if path.is_symlink():
            raise ValueError('REF artifact symlink forbidden')
    if root.is_symlink() or not path.is_file() or path.stat().st_size != binding['size']:
        raise ValueError('REF artifact missing or wrong size')
    raw = path.read_bytes()
    if len(raw) != binding['size'] or hashlib.sha256(raw).hexdigest() != binding['sha256']:
        raise ValueError('REF artifact digest differs')
    result = json.loads(raw)
    if _summary(result) != envelope['summary']:
        raise ValueError('REF artifact summary differs')
    if (result.get('case_id') != case_id or result.get('common_sha256') != digest(common) or
        result.get('manifest_sha256') != digest(manifest) or result.get('query_sha256') != digest(common['query']) or
        type(result.get('Hmax')) is not int or result['Hmax'] != common['seed']['max_depth'] or
        result.get('production_optimizer_used') is not False or
        result.get('optimizer') != 'validation.reference5.real_solver.solve_real_case' or
        result.get('budget_seconds') != BUDGET_SECONDS):
        raise ValueError('REF physical domain/common seed/source identity differs')
    if result['status'] == 'SUCCESS':
        outcome = result['canonical_outcome']
        if result['independent_exact'] is not True or result.get('all_regimes_certified') is not True or type(outcome) is not dict:
            raise ValueError('REF success lacks complete independent certificate')
        if outcome.get('status') not in ('attained_optimum', 'primary_unattained', 'secondary_unattained'):
            raise ValueError('REF success lacks an admitted exact outcome')
        validate_outcome(outcome, result['Hmax'])
        if outcome['status'] == 'attained_optimum' and result.get('witness_replayed') is not True:
            raise ValueError('REF attained outcome lacks independent fresh replay')
    elif result['independent_exact'] is not False or result['canonical_outcome'] is not None:
        raise ValueError('Unknown REF must not assert exact evidence')
    return result


def validate_outcome(outcome, hmax):
    """Validate canonical output bytes before comparison to FLAT/HIER."""
    def rational(value):
        if type(value) is not str or str(F(value)) != value or F(value) < 0:
            raise ValueError('REF outcome requires canonical nonnegative rational strings')
    status = outcome.get('status')
    if status == 'attained_optimum':
        if set(outcome) != {'status','lex_key'}:
            raise ValueError('REF attained outcome fields differ')
        key = outcome['lex_key']
        if type(key) is not list or len(key) != 4:
            raise ValueError('REF attained key must have four components')
        rational(key[0]); rational(key[1])
        if type(key[2]) is not int or not 0 <= key[2] <= hmax or type(key[3]) is not list or len(key[3]) != key[2]:
            raise ValueError('REF key stop depth/sequence differs')
        if any(type(p) is not list or len(p) != 2 or type(p[0]) is not str or not p[0] or p[1] not in ('C','S','CS') for p in key[3]):
            raise ValueError('REF key action sequence malformed')
    else:
        fields = {'primary_unattained': {'primary_infimum'},
                  'secondary_unattained': {'J','secondary_infimum'}}.get(status)
        if fields is None or set(outcome) != {'status', *fields}:
            raise ValueError('REF unattained outcome fields differ')
        for key in fields:rational(outcome[key])
    return outcome


def admit_queue_reference(manifest, case_id, common_value, receipt, slot_directory, prior_results):
    result = load_worker_result(slot_directory, receipt, case_id, common=common_value, manifest=manifest)
    compared = []
    if result['independent_exact']:
        for method, prior in prior_results.items():
            outcome = prior.get('canonical_outcome')
            if outcome is not None:
                validate_outcome(outcome, common_value['seed']['max_depth'])
                if canonical(outcome) != canonical(result['canonical_outcome']):
                    raise ValueError('Independent REF and exact method outcome contradict: ' + str(method))
                compared.append(method)
    return dict(result, matched_exact_methods=sorted(compared))


def worker(manifest_path, manifest_sha256, case_id, common_path, common_sha256):
    import os
    from . import physical
    manifest = physical._manifest(manifest_path, manifest_sha256)
    raw = Path(common_path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != common_sha256:
        raise ValueError('REF common artifact digest differs')
    common = json.loads(raw)
    run_reference(manifest, case_id, common, Path(os.environ['HIROUTE_OUTPUT_DIR'])/'reference')
    physical._manifest(manifest_path, manifest_sha256)
    Path(os.environ['HIROUTE_WORKER_RECEIPT']).write_bytes(canonical(dict(status='COMPLETED',
        result=result_envelope(os.environ['HIROUTE_OUTPUT_DIR'], case_id))))


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('manifest', 'manifest-sha256', 'case', 'common', 'common-sha256'):
        parser.add_argument('--'+name, required=True)
    args = parser.parse_args()
    worker(args.manifest, args.manifest_sha256, args.case, args.common, args.common_sha256)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
