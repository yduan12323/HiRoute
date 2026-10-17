"""Opt-in feasible-only admission in the existing full exact QueryDomain.

No heuristic enumeration or solver call occurs. The default completed-seed
entrypoint stays untouched. Full table selection validity remains the existing
externally approved QueryDomain precondition; sparse receipts are not accepted.
"""
from dataclasses import dataclass, field
from fractions import Fraction as R
import hashlib
import inspect
import json
from pathlib import Path
from typing import Mapping

from .deployable import DomainBinding, QueryDomain, VerifiedSeed, certified_depth, _json_object, _sha

SCHEMA = 'hiroute.exact_feasible_witness.v1'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def _verifier(approved):
    import validation.reference5 as package
    from validation.reference5 import real_solver, real_input, model, solver, lp
    modules = dict(package=package, real_solver=real_solver, real_input=real_input,
                   model=model, solver=solver, lp=lp)
    if not isinstance(approved, Mapping) or set(approved) != set(modules):
        raise ValueError('Complete approved pinned REF source closure required')
    for name, module in modules.items():
        _sha(approved[name], name)
        if sha(Path(inspect.getsourcefile(module)).read_bytes()) != approved[name]:
            raise ValueError('Approved pinned REF source closure mismatch')
    replay = real_solver.replay_real_witness_bytes
    if (replay.__module__ != real_solver.__name__ or
            inspect.getsourcefile(replay) != inspect.getsourcefile(real_solver)):
        raise ValueError('Approved independent replay entrypoint changed')
    return replay, real_input


@dataclass(frozen=True)
class ExactFeasibleCertificate:
    domain: QueryDomain
    witness_bytes: bytes
    witness_sha256: str
    verifier_sha256: tuple
    source_sha256: tuple
    seed: VerifiedSeed
    max_depth: int
    sequence: tuple
    charges: tuple
    status: str = field(default='feasible_incumbent_available', init=False)
    heuristic_minimum_claimed: bool = field(default=False, init=False)
    exact_optimum_claimed: bool = field(default=False, init=False)


@dataclass(frozen=True)
class ExactFeasibleAdmission:
    """Freshly reverified solver inputs, without claiming a search has run."""
    certificate: ExactFeasibleCertificate
    bounded_query_bytes: bytes
    primary_upper: R
    max_depth: int


def admit_exact_feasible_incumbent(domain, witness_bytes, *, expected_domain,
        approved_verifier_sha256, actual_source_paths):
    """Verify one supplied full-domain witness, even if it is not heuristic-best.

    expected_domain is the independently frozen caller target, not a binding
    copied from the untrusted witness. Every one of its eleven fields must
    agree. Actual graph/router source files declared by the complete table are
    rehashed before and after replay. A sparse/checkpoint hash is no substitute.
    """
    if (type(domain) is not QueryDomain or type(expected_domain) is not DomainBinding or
            domain.binding != expected_domain or type(witness_bytes) is not bytes):
        raise ValueError('Same frozen full QueryDomain and immutable witness required')
    # Reconstruct rather than relying on a dataclass whose fields may have
    # arrived through untrusted deserialization.
    domain = QueryDomain(domain.binding, domain.query_bytes, domain.candidate_bytes,
                         domain.table_bytes, domain.table_sha256)
    query, table = domain.open()
    if query.get('hierarchy_sha256') != expected_domain.hierarchy_sha256:
        raise ValueError('Query hierarchy differs from frozen exact domain')
    record = _json_object(witness_bytes)
    if (set(record) != {'schema','domain','table_sha256','sequence','charges'} or
            record['schema'] != SCHEMA or
            record['domain'] != {k:getattr(expected_domain,k) for k in expected_domain.__dataclass_fields__} or
            record['table_sha256'] != domain.table_sha256):
        raise ValueError('Witness belongs to a different full exact domain/table')
    seq, amounts = record['sequence'], record['charges']
    if (type(seq) is not list or any(type(x) is not list or len(x) != 2 or
            any(type(y) is not str for y in x) for x in seq) or
            type(amounts) is not list or any(type(x) not in (str,int) for x in amounts)):
        raise ValueError('Exact semantic sequence and non-boolean rational charges required')
    sequence, charges = tuple(map(tuple,seq)), tuple(map(R,amounts))
    replay, real_input = _verifier(approved_verifier_sha256)
    independent = real_input.IndependentLegTable.from_bytes(domain.table_bytes, domain.table_sha256)
    def sources():
        result = real_input.verify_source_files(independent, actual_source_paths)
        if not result['complete']:
            raise ValueError('Full graph/router source-file verification failed')
    sources()
    result = replay(_json_object(domain.query_bytes), domain.table_bytes,
                    domain.table_sha256, sequence, charges)
    if (type(result) is not dict or result.get('witness_replayed') is not True or
            result.get('H') != len(sequence) or result.get('site_action_tuple') != sequence or
            result.get('charges') != charges or type(result.get('J')) is not R or result['J'] < 0 or
            type(result.get('Q_total')) is not R or result['Q_total'] != sum(charges,R(0)) or
            result.get('lex_key') != (result['J'],sum(charges,R(0)),len(sequence),sequence)):
        raise ValueError('Independent exact physical replay is inconsistent')
    # Explicitly cross-check each freshly reconstructed immutable selected leg
    # against the production parser, never against a supplied drive trace.
    anchors = [table.origin_anchor] + [table.site(s).anchor_id for s,_ in sequence] + [table.destination_anchor]
    legs = result.get('route_legs')
    if type(legs) is not list or len(legs) != len(anchors)-1:
        raise ValueError('Independent replay omitted selected legs')
    for a,b,leg in zip(anchors,anchors[1:],legs):
        pair = table.leg(a,b)
        if (not pair.reachable or (leg.source_road_anchor,leg.target_road_anchor,
                leg.time,leg.length,leg.time_hex,leg.length_hex,leg.label_direction,leg.table_sha256) !=
                (a,b,pair.time,pair.actual_length,pair.time_hex,pair.length_hex,
                 pair.label_direction,domain.table_sha256)):
            raise ValueError('Fresh independent selected-leg replay mismatch')
    closure = tuple(sorted(dict(approved_verifier_sha256).items()))
    seed = VerifiedSeed(expected_domain, result['J'], sha(witness_bytes), sha(canonical(dict(closure))))
    def exact(name):
        if type(query[name]) not in (str,int):
            raise ValueError('Exact physical query quantities required')
        return R(query[name])
    depth = certified_depth(seed, expected_domain, exact('overhead_s'), exact('lambda_stop_s'))
    if len(sequence) > depth:
        raise ValueError('Witness contradicts equality-inclusive depth theorem')
    sources(); _verifier(approved_verifier_sha256)
    claims = tuple(sorted({**independent.source_sha256, **independent.router_source_sha256}.items()))
    return ExactFeasibleCertificate(domain,witness_bytes,sha(witness_bytes),closure,claims,
                                    seed,depth,sequence,charges)


def prepare_exact_feasible_admission(certificate, *, expected_domain,
        approved_verifier_sha256, actual_source_paths):
    """Opt-in search boundary: recompute every bound before supplying it."""
    if type(certificate) is not ExactFeasibleCertificate:
        raise ValueError('Separate exact feasible certificate required')
    fresh = admit_exact_feasible_incumbent(certificate.domain,certificate.witness_bytes,
        expected_domain=expected_domain, approved_verifier_sha256=approved_verifier_sha256,
        actual_source_paths=actual_source_paths)
    if fresh != certificate:
        raise ValueError('Exact feasible certificate failed fresh-boundary replay')
    query = _json_object(fresh.domain.query_bytes)
    return ExactFeasibleAdmission(fresh,canonical(dict(query,H_ref=fresh.max_depth)),
                                  fresh.seed.primary_j,fresh.max_depth)


def solve_deployable_pair_with_feasible_incumbent(certificate, hierarchy_bytes, *,
        expected_domain, approved_verifier_sha256, actual_source_paths,
        landmarks=(), summaries=None, selected_leg_provider=None):
    """Opt-in exact FLAT/HIER search from one freshly reverified feasible plan.

    The default completed-seed solver entrypoint is unchanged. No partial OPEN
    state is resumed, and a sparse receipt is not a full-domain certificate.
    """
    if type(hierarchy_bytes) is not bytes:
        raise ValueError('Frozen original hierarchy bytes required')
    admitted = prepare_exact_feasible_admission(certificate,
        expected_domain=expected_domain, approved_verifier_sha256=approved_verifier_sha256,
        actual_source_paths=actual_source_paths)
    from .deployable import _solve_deployable_pair_verified
    return _solve_deployable_pair_verified(admitted.certificate, hierarchy_bytes,
        landmarks=landmarks, summaries=summaries, selected_leg_provider=selected_leg_provider)
