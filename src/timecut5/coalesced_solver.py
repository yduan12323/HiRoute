"""Separately selected representation mode; baseline public APIs stay unchanged."""
from __future__ import annotations

from dataclasses import dataclass,asdict

from .bounded import Problem,_solve_problem
from .hierarchy import build_regions,_solve_hierarchical_problem
from .real_adapter import RealProblem,RealResult,TableFreeRealProblem,original_region_view
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
    def __init__(self,*args,record_lineage=False,**kwargs):
        if type(record_lineage) is not bool:
            raise TypeError('record_lineage must be boolean')
        if record_lineage:
            from .invocation_trace import require_coalescing_context
            require_coalescing_context()
        self._record_lineage=record_lineage
        self._coalescing_counts=[0,0,0,0,0]
        super().__init__(*args,**kwargs)

    def compact(self,pieces):
        pieces=tuple(pieces)
        if not self._record_lineage and any(getattr(piece, '_family', None) is not None for piece in pieces):
            raise ValueError('Optional untraced mode rejects known proof families before processing')
        result=coalesce_pieces(pieces,record_lineage=self._record_lineage)
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


def solve_hierarchical_coalesced(case,dominance=True,leaf_size=1,incumbent=None,*,record_lineage=False):
    problem=_SyntheticProblem(case,record_lineage=record_lineage);root=build_regions(problem.sites,leaf_size)
    result=_solve_hierarchical_problem(problem,dominance,root,incumbent,reducer=problem.reduce)
    return CoalescedResult(result,problem.statistics())


def solve_bounded_real_coalesced(query,table,restriction=None,dominance=True):
    if restriction is not None:original_region_view(table,restriction)
    problem=_RealProblem(query,table)
    result=_solve_problem(problem,dominance,reducer=problem.reduce)
    base=RealResult(result,table.payload_sha256,table.selection_certificate_sha256,
                    restriction.original_sha256 if restriction is not None else None)
    return CoalescedResult(base,problem.statistics())


def solve_hierarchical_real_coalesced(query,table,restriction,dominance=True,incumbent=None,*,record_lineage=False):
    problem=_RealProblem(query,table,record_lineage=record_lineage);root=original_region_view(table,restriction)
    result=_solve_hierarchical_problem(problem,dominance,root,incumbent,reducer=problem.reduce)
    base=RealResult(result,table.payload_sha256,table.selection_certificate_sha256,restriction.original_sha256)
    return CoalescedResult(base,problem.statistics())


class _TableFreeProblem(_Coalescing, TableFreeRealProblem):
    """The same exact representation hook over native, on-demand road legs."""


@dataclass(frozen=True)
class TableFreeCoalescingResult:
    """Diagnostic bounded result; does not claim seed/bound admission or REF proof."""
    base: object
    statistics: CoalescingStatistics
    coalescing_enabled: bool

    @property
    def inner(self):
        return self.base

    def canonical(self):
        result = self.base.canonical()
        result.update(coalescing_enabled=self.coalescing_enabled,
                      coalescing_statistics=asdict(self.statistics))
        if self.coalescing_enabled:
            result['representation_version'] = VERSION
        return result


def table_free_problem(query, sites, provider, *, origin_anchor,
                       destination_anchor, site_catalog_sha256,
                       terminal_target_routing=False, coalescing=False):
    """Build a separately selected adapter; existing entry points are untouched.

    This unrecorded mode deliberately rejects known proof families. It makes
    no certified-lineage claim and never loads an immutable ordered-leg table.
    """
    if type(coalescing) is not bool:
        raise TypeError('coalescing must be boolean')
    adapter = _TableFreeProblem if coalescing else TableFreeRealProblem
    return adapter(query, sites, provider, origin_anchor=origin_anchor,
                   destination_anchor=destination_anchor,
                   site_catalog_sha256=site_catalog_sha256,
                   terminal_target_routing=terminal_target_routing)


def _table_free_result(problem, result, coalescing):
    statistics = (problem.statistics() if coalescing else
                  CoalescingStatistics(0, 0, 0, 0, 0))
    return TableFreeCoalescingResult(result, statistics, coalescing)


def solve_bounded_table_free(query, sites, provider, *, origin_anchor,
                             destination_anchor, site_catalog_sha256,
                             coalescing=False, dominance=True,
                             terminal_target_routing=False,
                             verified_primary_upper=None, singleton_bound=None,
                             checkpoint_hook=None, incumbent_hook=None):
    """Opt-in exact coalescing for bounded table-free FLAT, default OFF.

    Bound/seed admission and independent physical replay remain caller gates.
    Hooks are the existing solver hooks, without a new pruning rule.
    """
    problem = table_free_problem(query, sites, provider,
        origin_anchor=origin_anchor, destination_anchor=destination_anchor,
        site_catalog_sha256=site_catalog_sha256,
        terminal_target_routing=terminal_target_routing, coalescing=coalescing)
    result = _solve_problem(problem, dominance,
        reducer=problem.reduce if coalescing else None,
        verified_primary_upper=verified_primary_upper,
        singleton_bound=singleton_bound, checkpoint_hook=checkpoint_hook,
        incumbent_hook=incumbent_hook)
    return _table_free_result(problem, result, coalescing)


def solve_hierarchical_table_free(query, sites, provider, root, *, origin_anchor,
                                  destination_anchor, site_catalog_sha256,
                                  coalescing=False, dominance=True, incumbent=None,
                                  terminal_target_routing=False,
                                  verified_primary_upper=None, bound_provider=None,
                                  checkpoint_hook=None, incumbent_hook=None):
    """Opt-in exact coalescing for bounded table-free HIER, default OFF.

    The caller supplies its already admitted hierarchy and optional bound
    provider. This API does not silently substitute a synthetic Region tree.
    """
    problem = table_free_problem(query, sites, provider,
        origin_anchor=origin_anchor, destination_anchor=destination_anchor,
        site_catalog_sha256=site_catalog_sha256,
        terminal_target_routing=terminal_target_routing, coalescing=coalescing)
    result = _solve_hierarchical_problem(problem, dominance, root, incumbent,
        reducer=problem.reduce if coalescing else None,
        verified_primary_upper=verified_primary_upper, bound_provider=bound_provider,
        checkpoint_hook=checkpoint_hook, incumbent_hook=incumbent_hook)
    return _table_free_result(problem, result, coalescing)
