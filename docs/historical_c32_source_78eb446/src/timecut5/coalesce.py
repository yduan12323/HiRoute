"""Optional exact cut-piece coalescing; not enabled in production operators.

Only identical affine cut semantics and full (state, rho, pi) context merge.
Their domains must have a connected exact union. Witnesses always dispatch to
an original constrained piece, preserving inherited predecessor restrictions.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from .probe import Interval
from .pwa import CutPiece

VERSION = 'exact-adjacent-cut-coalescing-v1'


def _signature(piece: CutPiece):
    return (piece.state, piece.rho, piece.pi, piece.slope, piece.intercept, piece.chi)


def _connected_union(left: Interval, right: Interval) -> Interval | None:
    """left.lo <= right.lo; a missing shared endpoint remains a real hole."""
    if left.lo > right.lo:
        raise ValueError('Intervals must be ordered by lower endpoint')
    if left.hi < right.lo or (left.hi == right.lo and not (left.right_closed or right.left_closed)):
        return None
    left_closed = left.left_closed or (left.lo == right.lo and right.left_closed)
    if left.hi > right.hi:
        high, right_closed = left.hi, left.right_closed
    elif left.hi < right.hi:
        high, right_closed = right.hi, right.right_closed
    else:
        high, right_closed = left.hi, left.right_closed or right.right_closed
    return Interval(left.lo, high, left_closed, right_closed)


@dataclass(frozen=True)
class GuardedParent:
    input_index: int
    parent_family_id: str | None
    energy_guard: Interval
    piece: CutPiece


@dataclass(frozen=True)
class CoalescedDispatch:
    """Immutable guarded-union provenance, with original constrained callbacks."""
    parents: tuple[GuardedParent, ...]

    def select(self, energy) -> GuardedParent:
        for parent in self.parents:
            if parent.energy_guard.contains(energy):
                return parent
        raise AssertionError('Connected union has no original witness at this energy')

    def __call__(self, energy):
        return self.select(energy).piece.at(energy)


def _joined(domain: Interval, members: list[tuple[int, CutPiece]], family_ids) -> CutPiece:
    if len(members) == 1:
        return members[0][1]
    if any(getattr(piece, '_family', None) is not None for _, piece in members):
        raise ValueError('Known proof families require a fresh certified guarded-union constructor')
    # Fixed original input order; no optimal dispatch complexity is claimed.
    originals = tuple(sorted(members, key=lambda pair: pair[0]))
    dispatch = CoalescedDispatch(tuple(GuardedParent(index, family_ids[index], piece.domain, piece)
                                       for index, piece in originals))
    return replace(originals[0][1], domain=domain, _point=dispatch)


def coalesce_pieces(pieces: Iterable[CutPiece], *, family_ids: Iterable[str | None] | None = None) -> tuple[CutPiece, ...]:
    """Return the same cut union using exact connected-domain clusters.

    This is neither dominance pruning nor an energy approximation. Open-open
    touching intervals stay separate unless another member covers the knot.
    Different chi, affine functions, rho, pi or physical states never merge.
    Duplicates may disappear, but every represented cut retains an original
    witness capable of realizing any legal budget/epsilon requested of it.
    """
    pieces = tuple(pieces)
    family_ids = (None,) * len(pieces) if family_ids is None else tuple(family_ids)
    if len(family_ids) != len(pieces) or any(x is not None and (not isinstance(x, str) or not x) for x in family_ids):
        raise ValueError('Parent-family IDs must match the pieces and be nonempty strings or None')
    groups = {}
    for index, piece in enumerate(pieces):
        if not isinstance(piece, CutPiece):
            raise TypeError('Expected CutPiece')
        groups.setdefault(_signature(piece), []).append((index, piece))
    result = []
    for group in groups.values():
        ordered = sorted(group, key=lambda pair: (pair[1].domain.lo, not pair[1].domain.left_closed,
                                                 pair[1].domain.hi, not pair[1].domain.right_closed, pair[0]))
        domain = ordered[0][1].domain
        members = [ordered[0]]
        for pair in ordered[1:]:
            union = _connected_union(domain, pair[1].domain)
            if union is None:
                result.append(_joined(domain, members, family_ids))
                domain, members = pair[1].domain, [pair]
            else:
                domain = union
                members.append(pair)
        result.append(_joined(domain, members, family_ids))
    return tuple(result)
