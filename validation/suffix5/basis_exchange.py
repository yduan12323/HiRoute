"""Bounded exact one-row exchanges after the legacy candidate recovery fails.

Floating support can name an empty rational optimal face when two bounds round
to the same binary64 value. Likewise, greedy completion can choose a nearby
inactive row. An exchange is only another candidate: all original inequalities,
equalities, signs, stationarity and exact strong duality remain mandatory.
This is deliberately incomplete. Exhausting its finite neighborhood remains
UncertifiedLP, not an infeasibility or approximate-optimality decision.
"""
from fractions import Fraction as R

MAX_VARIABLES = 32
MAX_INEQUALITIES = 256
MAX_EQUALITIES = 32
MAX_EXCHANGE_TRIALS = 512


def recover_exchange(c, A, b, equalities, candidate, selected_rows):
    # Imported lazily to keep the ordinary vendor paths and their bytes intact.
    from .vendor_lp import UncertifiedLP, dot, require, solve_rational_equalities, verify_certificate
    n = len(c)
    require(0 < n <= MAX_VARIABLES and len(A) <= MAX_INEQUALITIES and
            len(equalities) <= MAX_EQUALITIES, 'Exact basis-exchange dimension cap')
    require(type(MAX_EXCHANGE_TRIALS) is int and MAX_EXCHANGE_TRIALS > 0,
            'Exact basis-exchange trial cap')
    require(len(set(selected_rows)) == len(selected_rows) and
            all(type(i) is int and 0 <= i < len(A) for i in selected_rows),
            'Invalid candidate recovery row identities')
    seed = tuple(map(R, candidate['x']))
    eq_rows = [row for row, _ in equalities]
    eq_rhs = [rhs for _, rhs in equalities]
    _, rank = solve_rational_equalities(eq_rows, eq_rhs, seed)
    rows, rhs, basis = list(eq_rows), list(eq_rhs), []
    # Keep every original equality, but only independent inequality rows in the
    # trial basis. Redundant rows are still checked in the original full system.
    for i in selected_rows:
        _, new_rank = solve_rational_equalities(rows + [A[i]], rhs + [b[i]], seed)
        if new_rank > rank:
            rows.append(A[i]); rhs.append(b[i]); basis.append(i); rank = new_rank
    require(rank == n and basis, 'Exact basis-exchange requires a full candidate basis')
    rest = sorted((i for i in range(len(A)) if i not in basis),
        key=lambda i: (abs(dot(A[i], seed)-b[i]) /
            (R(1)+abs(b[i])+sum((abs(a*x) for a,x in zip(A[i],seed)), R(0))), i))
    trials = 0
    for position in range(len(basis)):
        for entering in rest:
            require(trials < MAX_EXCHANGE_TRIALS, 'Exact basis-exchange trial cap exhausted')
            trials += 1
            proposed = basis[:position] + [entering] + basis[position+1:]
            try:
                x, rank = solve_rational_equalities(eq_rows + [A[i] for i in proposed],
                    eq_rhs + [b[i] for i in proposed], seed)
                if rank != n or not all(dot(row,x) <= value for row,value in zip(A,b)):
                    continue
                # Reconstruct stationarity on the exchanged basis as well.
                # Retaining the old floating dual would preserve the wrong
                # exact objective in the empty-dual-face failure mode.
                columns = [A[i] for i in proposed] + eq_rows
                transpose = [tuple(row[j] for row in columns) for j in range(n)]
                dual, _ = solve_rational_equalities(transpose, c, (R(0),)*len(columns))
                y = [R(0)]*len(A)
                for i,value in zip(proposed,dual):
                    y[i] = value
                certificate = dict(status='optimal', x=x, objective=dot(c,x),
                    inequality_dual=tuple(y), equality_dual=dual[len(proposed):])
                verify_certificate(c,A,b,equalities,certificate)
                certificate.update(exact_primal_dual_verified=True,
                    candidate_recovery='exact_active_constraints',
                    recovery_inequality_rows=tuple(proposed),
                    recovery_dual_support=tuple(i for i,value in enumerate(y) if value))
                return certificate
            except UncertifiedLP:
                continue
    raise UncertifiedLP('Exact basis-exchange neighborhood did not certify the candidate')
