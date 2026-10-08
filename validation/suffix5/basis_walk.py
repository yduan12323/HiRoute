"""Finite exact repair after the frozen one-row neighborhood is exhausted.

The walk changes only candidate reconstruction. Violated rational rows guide
new bases; zero-objective epigraph coordinates may move upward. Acceptance is
still the original full primal/dual certificate check, with no tolerances.
"""
from collections import deque
from fractions import Fraction as R

MAX_BASES = 512
MAX_DISCOVERED = 4096
MAX_VARIABLES = 32
MAX_INEQUALITIES = 256
MAX_EQUALITIES = 32


def _upward_columns(c, A, equalities):
    """Discover an acyclic order of objective/equality-neutral directions."""
    remaining = {j for j, value in enumerate(c) if not value and
                 all(not row[j] for row, _ in equalities)}
    ordered = []
    while remaining:
        # Every row worsened by this direction has an already discovered
        # negative direction. Reverse-order lifting repairs that row later.
        column = next((j for j in sorted(remaining) if all(row[j] <= 0 or
            any(row[k] < 0 for k in ordered) for row in A)), None)
        if column is None:
            break
        ordered.append(column)
        remaining.remove(column)
    return tuple(ordered)


def _lift(x, A, b, ordered):
    from .vendor_lp import dot
    values = list(x)
    for j in reversed(ordered):
        increase = max((max(R(0), (dot(row, values)-rhs)/(-row[j]))
                        for row, rhs in zip(A, b) if row[j] < 0), default=R(0))
        values[j] += increase
    return tuple(values)


def recover_walk(c, A, b, equalities, candidate, selected_rows):
    from .vendor_lp import (UncertifiedLP, dot, require,
                           solve_rational_equalities, verify_certificate)
    n = len(c)
    require(0 < n <= MAX_VARIABLES and len(A) <= MAX_INEQUALITIES and
            len(equalities) <= MAX_EQUALITIES, 'Exact basis-walk dimension cap')
    require(type(MAX_BASES) is int and MAX_BASES > 0 and
            type(MAX_DISCOVERED) is int and MAX_DISCOVERED > 0,
            'Exact basis-walk count caps')
    require(len(set(selected_rows)) == len(selected_rows) and
            all(type(i) is int and 0 <= i < len(A) for i in selected_rows),
            'Invalid basis-walk row identities')
    seed = tuple(map(R, candidate['x']))
    require(len(seed) == n, 'Exact basis-walk seed dimension')
    eq_rows = [row for row, _ in equalities]
    eq_rhs = [rhs for _, rhs in equalities]
    rows, rhs, basis = list(eq_rows), list(eq_rhs), []
    _, rank = solve_rational_equalities(rows, rhs, seed)
    for i in selected_rows:
        _, new_rank = solve_rational_equalities(rows+[A[i]], rhs+[b[i]], seed)
        if new_rank > rank:
            rows.append(A[i]); rhs.append(b[i]); basis.append(i); rank = new_rank
    require(rank == n and basis, 'Exact basis-walk requires a full candidate basis')
    first = tuple(sorted(basis))
    queue, seen = deque([first]), {first}
    ordered = _upward_columns(c, A, equalities)
    trials = 0
    while queue:
        require(trials < MAX_BASES, 'Exact basis-walk trial cap exhausted')
        proposed = queue.popleft()
        trials += 1
        try:
            x, rank = solve_rational_equalities(eq_rows+[A[i] for i in proposed],
                                                eq_rhs+[b[i] for i in proposed], seed)
        except UncertifiedLP:
            continue
        if rank != n:
            continue
        x = _lift(x, A, b, ordered)
        bad = [i for i, (row, value) in enumerate(zip(A, b)) if dot(row, x) > value]
        if not bad:
            try:
                columns = [A[i] for i in proposed]+eq_rows
                transpose = [tuple(row[j] for row in columns) for j in range(n)]
                dual, _ = solve_rational_equalities(transpose, c, (R(0),)*len(columns))
                y = [R(0)]*len(A)
                for i, value in zip(proposed, dual):
                    y[i] = value
                certificate = dict(status='optimal', x=x, objective=dot(c, x),
                    inequality_dual=tuple(y), equality_dual=dual[len(proposed):])
                verify_certificate(c, A, b, equalities, certificate)
                certificate.update(exact_primal_dual_verified=True,
                    candidate_recovery='exact_active_constraints',
                    recovery_inequality_rows=tuple(i for i in proposed if dot(A[i], x) == b[i]),
                    recovery_dual_support=tuple(i for i, value in enumerate(y) if value))
                return certificate
            except UncertifiedLP:
                # A feasible vertex with no accepted dual is not a result.
                # This bounded primal-repair walk need not explore from it.
                continue
        for entering in bad:
            for position in range(len(proposed)):
                node = tuple(sorted(proposed[:position]+(entering,)+proposed[position+1:]))
                if len(set(node)) != len(proposed) or node in seen:
                    continue
                require(len(seen) < MAX_DISCOVERED, 'Exact basis-walk discovered-state cap exhausted')
                seen.add(node)
                queue.append(node)
    raise UncertifiedLP('Exact basis-walk neighborhood did not certify the candidate')
