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
    verify_certificate(c, A, b, equalities, certificate)
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
