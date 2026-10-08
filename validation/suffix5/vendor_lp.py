"""Independent rational LP certificates, with HiGHS used only for candidates.

Adapted from the archived B21 diagnostic certificate idea. No production
propagation, reduction, projection, or optimization code is imported.
"""
from __future__ import annotations

from fractions import Fraction as R
import math

import numpy as np
from scipy.optimize import linprog


class UncertifiedLP(ArithmeticError):
    """A floating candidate did not supply an exactly checkable certificate."""


def dot(a, b):
    return sum((x * y for x, y in zip(a, b)), R(0))


def rational(value):
    if not math.isfinite(float(value)):
        raise UncertifiedLP("Nonfinite candidate")
    return R(str(float(value))).limit_denominator(1_000_000_000)


def require(condition, message):
    if not condition:
        raise UncertifiedLP(message)


def verify_certificate(c, A, b, equalities, certificate):
    """Recheck an optimal primal/dual certificate without invoking a solver."""
    n = len(c)
    require(len(A) == len(b) and all(len(row) == n for row in A), "Invalid certificate inequality shape")
    require(all(len(row) == n for row, _ in equalities), "Invalid certificate equality shape")
    x = certificate["x"]
    y = certificate["inequality_dual"]
    z = certificate["equality_dual"]
    require(len(x) == n and len(y) == len(A) and len(z) == len(equalities),
            "Certificate dimension mismatch")
    require(all(dot(row, x) <= rhs for row, rhs in zip(A, b)), "Primal infeasible")
    require(all(dot(row, x) == rhs for row, rhs in equalities), "Equality infeasible")
    require(all(v <= 0 for v in y), "Dual sign invalid")
    require(all(sum((row[j] * v for row, v in zip(A, y)), R(0))
                + sum((row[j] * v for (row, _), v in zip(equalities, z)), R(0)) == c[j]
                for j in range(n)), "Dual infeasible")
    primal = dot(c, x)
    dual = dot(b, y) + dot([rhs for _, rhs in equalities], z)
    require(primal == dual == certificate["objective"], "Strong duality not verified")
    return True



def solve_rational_equalities(rows, rhs, seed):
    """Recover an affine point by exact elimination, retaining free seed values.

    This is candidate reconstruction, not an LP feasibility or optimality
    decision. Its output must still pass the complete certificate verifier.
    """
    n = len(seed)
    matrix = [list(map(R, row)) + [R(value)] for row, value in zip(rows, rhs)]
    require(len(rows) == len(rhs) and all(len(row) == n + 1 for row in matrix),
            "Invalid recovery equality shape")
    pivots = []
    for column in range(n):
        pivot = next((i for i in range(len(pivots), len(matrix)) if matrix[i][column]), None)
        if pivot is None:
            continue
        target = len(pivots)
        matrix[target], matrix[pivot] = matrix[pivot], matrix[target]
        scale = matrix[target][column]
        matrix[target] = [value / scale for value in matrix[target]]
        for i, row in enumerate(matrix):
            if i != target and row[column]:
                scale = row[column]
                matrix[i] = [a - scale * b for a, b in zip(row, matrix[target])]
        pivots.append(column)
    require(all(any(row[:-1]) or not row[-1] for row in matrix),
            "Inconsistent candidate active equalities")
    values = list(map(R, seed))
    free = [j for j in range(n) if j not in pivots]
    for i, column in enumerate(pivots):
        values[column] = matrix[i][-1] - sum((matrix[i][j] * values[j] for j in free), R(0))
    return tuple(values), len(pivots)


def recover_certificate(c, A, b, equalities, candidate, dual_support=None):
    """Reconstruct an exact primal/dual pair from candidate active constraints.

    Independent coordinate rationalization can move an apparently optimal
    point slightly off its common rational face. Recover the primal from exact
    active rows and recover dual multipliers from exact stationarity. Solver
    support and residual order are hints only. Every candidate is subjected to
    the unchanged full rational feasibility, sign and strong-duality checks.
    Failure is still UncertifiedLP, never a tolerance-based acceptance.
    """
    n = len(c)
    support = tuple(dual_support if dual_support is not None else
                    (i for i, value in enumerate(candidate["inequality_dual"]) if value))
    rows = [row for row, _ in equalities] + [A[i] for i in support]
    rhs = [value for _, value in equalities] + [b[i] for i in support]
    # Reconstruct duals as well: a small floating error in a multiplier must
    # not force a spurious high-denominator rational stationarity violation.
    dual_columns = [A[i] for i in support] + [row for row, _ in equalities]
    stationarity = [tuple(column[j] for column in dual_columns) for j in range(n)]
    dual_seed = tuple(candidate["inequality_dual"][i] for i in support) + candidate["equality_dual"]
    dual, _ = solve_rational_equalities(stationarity, c, dual_seed)
    y = [R(0)] * len(A)
    for i, value in zip(support, dual):
        y[i] = value
    require(all(value <= 0 for value in y), "Recovered dual sign invalid")
    z = dual[len(support):]
    seed = candidate["x"]
    selected_rows = list(support)

    def check(values):
        certificate = dict(status="optimal", x=values, objective=dot(c, values),
                           inequality_dual=tuple(y), equality_dual=z)
        verify_certificate(c, A, b, equalities, certificate)
        certificate.update(exact_primal_dual_verified=True,
                           candidate_recovery="exact_active_constraints",
                           recovery_inequality_rows=tuple(selected_rows),
                           recovery_dual_support=support)
        return certificate

    values, rank = solve_rational_equalities(rows, rhs, seed)
    try:
        return check(values)
    except UncertifiedLP:
        pass
    # A degenerate/zero-objective face may leave free seed coordinates slightly
    # outside the polyhedron. Add independent nearby rows as candidate equalities.
    # There is no threshold in the verifier, or in this residual ordering.
    remaining = sorted((i for i in range(len(A)) if i not in support),
                       key=lambda i: (abs(dot(A[i], seed) - b[i]) /
                                      (R(1) + abs(b[i]) + sum((abs(a * x) for a, x in zip(A[i], seed)), R(0))), i))
    for i in remaining:
        try:
            trial, new_rank = solve_rational_equalities(rows + [A[i]], rhs + [b[i]], seed)
        except UncertifiedLP:
            continue
        if new_rank == rank:
            continue
        rows.append(A[i])
        rhs.append(b[i])
        selected_rows.append(i)
        rank = new_rank
        try:
            return check(trial)
        except UncertifiedLP:
            pass
    # Preserve the ordinary and greedy recovery paths. Only a previously
    # unresolved full basis reaches the bounded exact exchange neighborhood.
    from .basis_exchange import recover_exchange
    try:
        return recover_exchange(c, A, b, equalities, candidate, selected_rows)
    except UncertifiedLP as error:
        if str(error) != 'Exact basis-exchange neighborhood did not certify the candidate':
            raise
    from .basis_walk import recover_walk
    return recover_walk(c, A, b, equalities, candidate, selected_rows)


def exact_lp(c, A, b, equalities=(), *, _phase=False):
    """Minimize c*x on A*x<=b with exact primal/dual or Phase-I evidence.

    There are no implicit variable bounds. All solver results, including
    infeasibility, need rational certificates. Numerical trouble is unresolved,
    never interpreted as infeasibility. Equalities are supported in Phase I.
    """
    c = tuple(map(R, c))
    A = [tuple(map(R, row)) for row in A]
    b = list(map(R, b))
    equalities = [(tuple(map(R, row)), R(rhs)) for row, rhs in equalities]
    n = len(c)
    require(len(A) == len(b) and all(len(row) == n for row in A), "Invalid inequality shape")
    require(all(len(row) == n for row, _ in equalities), "Invalid equality shape")
    if n == 0:
        if any(rhs < 0 for rhs in b) or any(rhs != 0 for _, rhs in equalities):
            return {"status": "infeasible", "constant_constraints_verified": True}
        result = dict(status="optimal", x=(), objective=R(0),
                      inequality_dual=(R(0),) * len(A),
                      equality_dual=(R(0),) * len(equalities))
        verify_certificate(c, A, b, equalities, result)
        result["exact_primal_dual_verified"] = True
        return result
    ae = [row for row, _ in equalities]
    be = [rhs for _, rhs in equalities]
    result = linprog(np.asarray(c, dtype=float),
                     A_ub=np.asarray(A, dtype=float) if A else None,
                     b_ub=np.asarray(b, dtype=float) if b else None,
                     A_eq=np.asarray(ae, dtype=float) if ae else None,
                     b_eq=np.asarray(be, dtype=float) if be else None,
                     bounds=[(None, None)] * n, method="highs",
                     options={"primal_feasibility_tolerance": 1e-9,
                              "dual_feasibility_tolerance": 1e-9})
    if result.status == 2:
        require(not _phase, "Feasible Phase-I auxiliary LP reported infeasible")
        # Every equality is represented by two rows for the Phase-I proof.
        rows, rhs = list(A), list(b)
        for row, value in equalities:
            rows.extend((row, tuple(-v for v in row)))
            rhs.extend((value, -value))
        phase_A = [row + (R(-1),) for row in rows]
        phase_A.append((R(0),) * n + (R(-1),))
        phase_b = rhs + [R(0)]
        phase_c = (R(0),) * n + (R(1),)
        phase = exact_lp(phase_c, phase_A, phase_b, _phase=True)
        require(phase["status"] == "optimal" and phase["objective"] > 0,
                "Infeasibility lacks a positive exact Phase-I optimum")
        return dict(status="infeasible", phase_I_certificate=phase)
    require(result.success, f"Unverified LP result: {result.message}")
    x = tuple(map(rational, result.x))
    certificate = dict(status="optimal", x=x, objective=dot(c, x),
                       inequality_dual=tuple(map(rational, result.ineqlin.marginals)),
                       equality_dual=tuple(map(rational, result.eqlin.marginals)))
    try:
        verify_certificate(c, A, b, equalities, certificate)
    except UncertifiedLP as error:
        # Keep the ordinary fast path. Recovery changes only how a candidate
        # certificate is obtained, never any LP row or exact acceptance check.
        support = tuple(i for i, value in enumerate(result.ineqlin.marginals) if value != 0)
        recovered = recover_certificate(c, A, b, equalities, certificate, support)
        recovered["initial_candidate_failure"] = str(error)
        return recovered
    certificate["exact_primal_dual_verified"] = True
    return certificate


def strict_face(A, b, n, equalities=()):
    """Certify existence of all q_j>0, optionally on sequential optimum faces.

    Maximize a common auxiliary slack s with 0<=s<=1, q_j>=s. The cap merely
    makes this auxiliary LP bounded. Any exact positive s qualifies, however
    small; this is not a charge quantum or SOC grid.
    """
    rows = [tuple(row) + (R(0),) for row in A]
    rhs = list(b)
    for j in range(n):
        row = [R(0)] * (n + 1)
        row[j], row[-1] = R(-1), R(1)
        rows.append(tuple(row))
        rhs.append(R(0))
    rows.extend([(R(0),) * n + (R(-1),), (R(0),) * n + (R(1),)])
    rhs.extend([R(0), R(1)])
    eq = [(tuple(row) + (R(0),), value) for row, value in equalities]
    return exact_lp((R(0),) * n + (R(-1),), rows, rhs, eq)
