"""Separately selected representation mode; baseline public APIs stay unchanged."""
from __future__ import annotations

from dataclasses import dataclass,asdict

from .bounded import Problem,_solve_problem
from .hierarchy import build_regions,_solve_hierarchical_problem
from .real_adapter import RealProblem,RealResult,original_region_view
from .pwa import reduce_frontier
from .coalesce import VERSION,coalesce_pieces


@dataclass(frozen=True)
class CoalescingStatistics:
    calls: int
    input_pieces: int
    output_pieces: int
    max_input_pieces: int
    max_output_pieces: int


class _Coalescing:
    def __init__(self,*args,**kwargs):
        self._coalescing_counts=[0,0,0,0,0]
        super().__init__(*args,**kwargs)

    def compact(self,pieces):
        pieces=tuple(pieces)
        if any(getattr(piece, '_family', None) is not None for piece in pieces):
            raise ValueError('Optional untraced mode rejects known proof families before processing')
        result=coalesce_pieces(pieces)
        counters=self._coalescing_counts
        counters[0]+=1;counters[1]+=len(pieces);counters[2]+=len(result)
        counters[3]=max(counters[3],len(pieces));counters[4]=max(counters[4],len(result))
        return result

    def advance(self,pieces,site,effect):
        return self.compact(super().advance(self.compact(pieces),site,effect))

    def finish(self,pieces):
        return self.compact(super().finish(self.compact(pieces)))

    def reduce(self,pieces):
        return self.compact(reduce_frontier(self.compact(pieces)))

    def statistics(self):return CoalescingStatistics(*self._coalescing_counts)


class _SyntheticProblem(_Coalescing,Problem):pass
class _RealProblem(_Coalescing,RealProblem):pass


@dataclass(frozen=True)
class CoalescedResult:
    base: object
    statistics: CoalescingStatistics

    @property
    def inner(self):
        return self.base.inner if isinstance(self.base,RealResult) else self.base

    def canonical(self):
        result=self.base.canonical()
        result.update(representation_version=VERSION,coalescing_statistics=asdict(self.statistics))
        return result


def solve_bounded_coalesced(case,dominance=True):
    problem=_SyntheticProblem(case)
    result=_solve_problem(problem,dominance,reducer=problem.reduce)
    return CoalescedResult(result,problem.statistics())


def solve_hierarchical_coalesced(case,dominance=True,leaf_size=1,incumbent=None):
    problem=_SyntheticProblem(case);root=build_regions(problem.sites,leaf_size)
    result=_solve_hierarchical_problem(problem,dominance,root,incumbent,reducer=problem.reduce)
    return CoalescedResult(result,problem.statistics())


def solve_bounded_real_coalesced(query,table,restriction=None,dominance=True):
    if restriction is not None:original_region_view(table,restriction)
    problem=_RealProblem(query,table)
    result=_solve_problem(problem,dominance,reducer=problem.reduce)
    base=RealResult(result,table.payload_sha256,table.selection_certificate_sha256,
                    restriction.original_sha256 if restriction is not None else None)
    return CoalescedResult(base,problem.statistics())


def solve_hierarchical_real_coalesced(query,table,restriction,dominance=True,incumbent=None):
    problem=_RealProblem(query,table);root=original_region_view(table,restriction)
    result=_solve_hierarchical_problem(problem,dominance,root,incumbent,reducer=problem.reduce)
    base=RealResult(result,table.payload_sha256,table.selection_certificate_sha256,restriction.original_sha256)
    return CoalescedResult(base,problem.statistics())
