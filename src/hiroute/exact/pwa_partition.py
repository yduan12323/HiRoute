"""Exact piecewise C/CS transitions, family envelopes and witness lifting.

This module ports the legacy four-variable projection semantics. It is an
exact rational transform; it does not call an optimizer or certify global
route optimality.
"""
from __future__ import annotations
from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations
from typing import Iterable

from .interval import Interval
from .linear import Projection, Row
from .pwa import AffineCutPiece, _interval, _curve_value
from .scalar import exact

@dataclass(frozen=True)
class TransitionWitness:
    effect: str
    site: str
    input_energy: Fraction
    input_time: Fraction
    output_energy: Fraction
    output_time: Fraction
    predecessor: object | None = None
    parameters: tuple = ()


def _interval_rows(domain: Interval, variable: int):
    lo, hi = [Fraction(0)] * 4, [Fraction(0)] * 4
    lo[variable], hi[variable] = Fraction(-1), Fraction(1)
    return (Row(tuple(lo), -domain.lo, not domain.left_closed),
            Row(tuple(hi), domain.hi, not domain.right_closed))


def _cells(domain: Interval, knots):
    order = sorted({domain.lo, domain.hi} | {x for x in knots if domain.lo < x < domain.hi})
    result = []
    for i, x in enumerate(order):
        if domain.contains(x): result.append(Interval(x, x))
        if i + 1 < len(order): result.append(Interval(x, order[i+1], False, False))
    return tuple(result)


def _sample(cell):
    return cell.lo if cell.lo == cell.hi else (cell.lo + cell.hi) / 2


def _partition_projection(projection, source, effect, site, overhead, curve,
                          a, b, duration, rho, prefix, state_key):
    lower = upper = None
    lc = rc = True
    lines = []
    for row in projection.rows:
        x, t, e, budget = row.coefficients
        if x or t or budget > 0:
            raise AssertionError("Projection is not a lower-time epigraph")
        if budget < 0:
            lines.append((-e / budget, row.rhs / budget, row.strict))
        elif e:
            bound = row.rhs / e
            if e < 0:
                if lower is None or bound > lower: lower, lc = bound, not row.strict
                elif bound == lower: lc = lc and not row.strict
            else:
                if upper is None or bound < upper: upper, rc = bound, not row.strict
                elif bound == upper: rc = rc and not row.strict
        elif not row.holds((Fraction(0),) * 4):
            return ()
    if lower is None or upper is None or not lines:
        raise AssertionError("Expected bounded output energy domain and finite cut")
    if lower > upper or lower == upper and not (lc and rc): return ()
    domain = Interval(lower, upper, lc, rc)
    knots = {(d-c)/(m-n) for (m,c,_),(n,d,_) in combinations(lines,2) if m != n}
    pieces = []
    for cell in _cells(domain, knots):
        energy = _sample(cell)
        value = max(m*energy+c for m,c,_ in lines)
        active = [(m,c,strict) for m,c,strict in lines if m*energy+c == value]
        slope, intercept, _ = active[0]
        attained = not any(strict for _,_,strict in active)
        pi = prefix + ((site, effect),)
        key = (site, state_key[1] if effect == "C" else 0, state_key[2]+1)
        def lift(output_energy, output_budget, projection=projection, source=source,
                 effect=effect, site=site, overhead=overhead, curve=curve,
                 a=a, b=b, duration=duration):
            output_energy, output_budget = exact(output_energy), exact(output_budget)
            ea, tau, ed, tout = projection.lift({2: output_energy, 3: output_budget})
            if effect == "C":
                # The projected polyhedron describes a lower-time epigraph.
                # A physical charge event must lie on its transition equation;
                # an arbitrary interior point of the feasible tau interval can
                # satisfy all inequalities yet fail exact witness replay.
                delta = _curve_value(curve, ed) - _curve_value(curve, ea)
                tau = tout - overhead - delta
                if not all(row.holds((ea, tau, ed, tout)) for row in projection.original):
                    raise ValueError("No charge witness on the exact transition face")
            predecessor = None
            if source.witness_lifter is not None:
                predecessor = source.witness_lifter(ea, tau)
            parameters = (tuple(curve), overhead, a, b, duration)
            return TransitionWitness(effect, site, ea, tau, ed, tout, predecessor, parameters)
        pieces.append(AffineCutPiece(cell, slope, intercept, attained, rho, pi,
                                     key, lift))
    return tuple(pieces)


def stop_partition(pieces: Iterable[AffineCutPiece], effect: str, site: str,
                   curve_segments, overhead, *, a=0, b=0, duration=0):
    """Full exact C or CS output-energy partition for supplied source pieces."""
    if effect not in ("C", "CS"): raise ValueError("effect must be C or CS")
    if not isinstance(site, str) or not site: raise ValueError("site must be non-empty")
    sources = tuple(pieces)
    overhead, a, b, duration = map(exact, (overhead, a, b, duration))
    if overhead <= 0 or duration < 0: raise ValueError("Invalid overhead or duration")
    segments = tuple(tuple(map(exact, seg)) for seg in curve_segments)
    result = []
    for source in sources:
        if len(source.state_key) != 3: raise ValueError("Invalid source state key")
        anchor, remaining, stops = source.state_key
        if type(stops) is not int or stops < 0 or len(source.prefix) != stops:
            raise ValueError("Source prefix/state mismatch")
        if effect == "CS" and remaining != 1: raise ValueError("CS requires one remaining schedule")
        seed = [*_interval_rows(source.domain, 0),
                Row((source.slope, -1, 0, 0), -source.intercept, not source.attained)]
        if effect == "CS":
            if a > b: continue
            seed.extend((Row((0,1,0,0), b-overhead),
                         Row((0,0,0,-1), -a-duration),
                         Row((0,1,0,-1), -overhead-duration)))
        for il, ih, im, ic in segments:
            for ol, oh, om, oc in segments:
                rows = seed + [*_interval_rows(Interval(il,ih),0),
                               *_interval_rows(Interval(ol,oh),2),
                               Row((1,0,-1,0),0,True),
                               Row((-im,1,om,-1),-overhead-oc+ic)]
                projection = Projection.build(rows, (1,0))
                if projection is not None:
                    result.extend(_partition_projection(projection, source, effect, site,
                        overhead, segments, a,b,duration,source.rho,source.prefix,
                        source.state_key))
    return family_union(result)


def _family_key(piece):
    return piece.state_key, piece.rho, piece.prefix


def family_union(pieces: Iterable[AffineCutPiece]):
    """Exact lower envelope of a single inherited-prefix family."""
    pieces = tuple(pieces)
    if not pieces: return ()
    key = _family_key(pieces[0])
    if any(_family_key(p) != key for p in pieces):
        raise ValueError("Union is restricted to one discrete-prefix family")
    knots = {p.domain.lo for p in pieces} | {p.domain.hi for p in pieces}
    for p,q in combinations(pieces,2):
        lo,hi=max(p.domain.lo,q.domain.lo),min(p.domain.hi,q.domain.hi)
        d=p.slope-q.slope
        if d:
            x=(q.intercept-p.intercept)/d
            if lo <= x <= hi: knots.add(x)
    domain=Interval(min(knots),max(knots))
    out=[]
    for cell in _cells(domain,knots):
        x=_sample(cell); active=[p for p in pieces if p.domain.contains(x)]
        if not active: continue
        best=min(p.slope*x+p.intercept for p in active)
        tied=[p for p in active if p.slope*x+p.intercept==best]
        chosen=next((p for p in tied if p.attained),tied[0])
        out.append(AffineCutPiece(cell,chosen.slope,chosen.intercept,
            any(p.attained for p in tied),chosen.rho,chosen.prefix,chosen.state_key,
            chosen.witness_lifter))
    return tuple(out)


def restrict_family(pieces: Iterable[AffineCutPiece], domain: Interval):
    """Intersect each source member with a requested energy interval."""
    result=[]
    for p in pieces:
        overlap=p.domain.intersect(domain)
        if overlap is not None:
            result.append(AffineCutPiece(overlap,p.slope,p.intercept,p.attained,
                p.rho,p.prefix,p.state_key,p.witness_lifter))
    return tuple(result)
