"""Bounded exhaustive continuous REF with sequential lexicographic attainment."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from fractions import Fraction as R
from time import perf_counter

from .lp import UncertifiedLP, exact_lp, strict_face
from .model import InvalidInput, assignments, normalize_case, regime_model, replay_witness, selected_legs, sequences


SCOPE = "bounded_H_ref_diagnostic"


def jsonable(value):
    """Canonical rational JSON conversion, also covering route dataclasses."""
    if isinstance(value, R):
        return str(value)
    if is_dataclass(value):
        return jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return value


def choose_result(contenders):
    """Optimize J, then Q on the attained J face, then finite H and tuple.

    A regime with unattained primary infimum cannot donate its hypothetical Q
    to the next stage. Conversely an unattained smaller Q blocks a larger
    attained Q. These are different statuses, with no fabricated lex key.
    """
    if not contenders:
        return dict(status="infeasible_within_H_ref")
    J = min(result["primary_infimum"] for result in contenders)
    primary_face = [r for r in contenders if r["primary_infimum"] == J and r["primary_attained"]]
    if not primary_face:
        return dict(status="primary_unattained", primary_infimum=J, unattained_component="J")
    Q = min(r["secondary_infimum"] for r in primary_face)
    attained = [r for r in primary_face if r["secondary_infimum"] == Q and r["secondary_attained"]]
    if not attained:
        return dict(status="secondary_unattained", J=J, primary_infimum=J,
                    secondary_infimum=Q, unattained_component="Q")
    # Charges are only a deterministic witness-selection tie break. They are
    # deliberately absent from the accepted four-component plan key.
    winner = min(attained, key=lambda r: (r["witness"]["H"], r["witness"]["site_action_tuple"], r["witness"]["charges"]))
    return dict(status="attained_optimum", primary_infimum=J, secondary_infimum=Q, **winner["witness"])


def solve_case(source, *, keep_evidence=True, allow_nonnegative_extension=False):
    started = perf_counter()
    envelope = dict(scope=SCOPE, model_domain=("exploratory_nonnegative_extension" if allow_nonnegative_extension
                                              else "positive_overhead_and_positive_road_edges"), H_ref=source.get("H_ref") if isinstance(source, dict) else None,
                    case_id=source.get("case_id") if isinstance(source, dict) else None)
    try:
        case = normalize_case(source, allow_nonnegative_extension=allow_nonnegative_extension)
    except (InvalidInput, TypeError, ValueError) as error:
        return dict(**envelope, result=dict(status="invalid_input", reason=str(error)))
    sequence_records, evidence_records, contenders = [], [], []
    counts = dict(sequence_count=0, terminal_sequence_count=0, regime_count=0,
                  closed_infeasible_regime_count=0, empty_strict_regime_count=0,
                  strict_feasible_regime_count=0, certified_regime_count=0)
    context = {}
    try:
        legs = selected_legs(case)
        for sequence, remaining, current in sequences(case, legs):
            counts["sequence_count"] += 1
            record = dict(sequence=sequence, remaining_schedule=remaining, regimes=0)
            sequence_records.append(record)
            if remaining:
                record["rejection"] = "unsatisfied_hard_schedule"
                continue
            if (current, case["destination"]) not in legs:
                record["rejection"] = "directed_destination_unreachable"
                continue
            counts["terminal_sequence_count"] += 1
            for assignment in assignments(case, sequence):
                context = dict(sequence=sequence, segments=assignment[0],
                               schedule_branch=assignment[1], completion_branch=assignment[2])
                evidence = dict(context)
                counts["regime_count"] += 1
                record["regimes"] += 1
                A, b, objective = regime_model(case, sequence, legs, assignment)
                n = len(objective.coefficients)
                primary = exact_lp(objective.coefficients, A, b)
                evidence["primary_certificate"] = primary
                if primary["status"] == "infeasible":
                    evidence["status"] = "closed_regime_infeasible"
                    counts["closed_infeasible_regime_count"] += 1
                else:
                    feasibility = strict_face(A, b, n)
                    evidence["strict_feasibility_certificate"] = feasibility
                    if feasibility["status"] != "optimal":
                        raise UncertifiedLP("Strict auxiliary face contradicts feasible closed LP")
                    if feasibility["x"][-1] == 0:
                        evidence["status"] = "empty_strict_regime"
                        counts["empty_strict_regime_count"] += 1
                    else:
                        counts["strict_feasible_regime_count"] += 1
                        J = primary["objective"] + objective.constant
                        face = [(objective.coefficients, primary["objective"])]
                        primary_face = strict_face(A, b, n, face)
                        evidence["primary_face_certificate"] = primary_face
                        if primary_face["status"] != "optimal":
                            raise UncertifiedLP("Primary optimal face unexpectedly infeasible")
                        contender = dict(primary_infimum=J, primary_attained=primary_face["x"][-1] > 0)
                        if not contender["primary_attained"]:
                            evidence.update(status="primary_unattained", primary_infimum=J)
                        else:
                            secondary = exact_lp((R(1),) * n, A, b, face)
                            evidence["secondary_certificate"] = secondary
                            if secondary["status"] != "optimal":
                                raise UncertifiedLP("Primary face missing a secondary optimum")
                            Q = secondary["objective"]
                            tie_face = strict_face(A, b, n, face + [((R(1),) * n, Q)])
                            evidence["secondary_face_certificate"] = tie_face
                            if tie_face["status"] != "optimal":
                                raise UncertifiedLP("Secondary optimal face unexpectedly infeasible")
                            contender.update(secondary_infimum=Q, secondary_attained=tie_face["x"][-1] > 0)
                            if not contender["secondary_attained"]:
                                evidence.update(status="secondary_unattained", primary_infimum=J, secondary_infimum=Q)
                            else:
                                witness = replay_witness(case, sequence, tie_face["x"][:-1], legs,
                                                         allow_nonnegative_extension=allow_nonnegative_extension)
                                if witness["J"] != J or witness["Q_total"] != Q:
                                    raise UncertifiedLP("Original-semantics replay disagrees with LP objective")
                                contender["witness"] = witness
                                evidence.update(status="attained_optimum", J=J, Q_total=Q)
                        contenders.append(contender)
                counts["certified_regime_count"] += 1
                if keep_evidence:
                    evidence_records.append(evidence)
        result = choose_result(contenders)
    except Exception as error:
        # Conservative failure contract: not one unverified regime may be
        # discarded while the overall result is presented as an exact answer.
        result = dict(status="unresolved", reason=f"{type(error).__name__}: {error}",
                      uncertified_regime=context)
    return dict(**envelope, result=result, **counts, sequences=sequence_records,
                regimes=evidence_records if keep_evidence else None,
                all_regimes_certified=result["status"] not in ("unresolved", "invalid_input"),
                elapsed_seconds=perf_counter() - started)
