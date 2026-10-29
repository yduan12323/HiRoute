"""Exact lexicographic terminal selection over affine PWA cut pieces."""
from __future__ import annotations
from dataclasses import dataclass
from fractions import Fraction
from typing import Iterable
from .interval import Interval
from .pwa import AffineCutPiece
from .scalar import exact

@dataclass(frozen=True)
class TerminalWitness:
    energy: Fraction
    time: Fraction
    rho: Fraction
    prefix: tuple[tuple[str,str], ...]
    state_key: tuple[object,...]
    predecessor: object | None = None

@dataclass(frozen=True)
class TerminalResult:
    status: str
    primary_value: Fraction | None = None
    primary_infimum: Fraction | None = None
    secondary_infimum: Fraction | None = None
    key: tuple | None = None
    witness: TerminalWitness | None = None
    unattained_component: str | None = None


def terminal_optimize(pieces: Iterable[AffineCutPiece], destination: str, reserve,
                      start_time=0, stop_penalty=0) -> TerminalResult:
    """Sequential attained-face optimization in exact lexicographic order.

    J = cut_time - start_time + stop_penalty*H; Q = E + rho. An unattained
    primary infimum prevents reporting later coordinates. If J is attained,
    Q is minimized only over attained J minimizers.
    """
    reserve, start_time, penalty = map(exact, (reserve,start_time,stop_penalty))
    if penalty < 0: raise ValueError("Negative stop penalty")
    candidates=[]
    for p in pieces:
        if not isinstance(p,AffineCutPiece): raise TypeError("Expected AffineCutPiece")
        if (len(p.state_key)!=3 or p.state_key[0]!=destination or
                p.state_key[1]!=0 or len(p.prefix)!=p.state_key[2]):
            continue
        lo=max(p.domain.lo,reserve)
        domain=p.domain.intersect(Interval(lo,max(lo,p.domain.hi)))
        if domain is None: continue
        e,closed=domain.affine_infimum(p.slope)
        j=p.slope*e+p.intercept-start_time+penalty*p.state_key[2]
        candidates.append((j,p,domain,e,closed and p.attained))
    if not candidates: return TerminalResult("infeasible")
    j=min(x[0] for x in candidates)
    face=[x for x in candidates if x[0]==j]
    attained=[x for x in face if x[4]]
    if not attained:
        return TerminalResult("primary_unattained", primary_infimum=j,
                              unattained_component="J")
    qs=[]
    for _,p,domain,e,_ in attained:
        # On a flat primary face, the lowest feasible energy minimizes Q;
        # on a nonflat face, the primary minimizer is its unique endpoint.
        q_energy = domain.lo if p.slope == 0 else e
        q_closed=domain.contains(q_energy)
        q=q_energy+p.rho
        qs.append((q,p,q_energy,q_closed))
    q=min(x[0] for x in qs)
    qface=[x for x in qs if x[0]==q]
    executable=[x for x in qface if x[3]]
    if not executable:
        return TerminalResult("secondary_unattained", primary_value=j,
                              primary_infimum=j, secondary_infimum=q,
                              unattained_component="Q")
    q,p,e,_=min(executable,key=lambda x:(x[1].state_key[2],x[1].prefix))
    time=p.slope*e+p.intercept
    predecessor=p.witness_lifter(e,time) if p.witness_lifter else None
    witness=TerminalWitness(e,time,p.rho,p.prefix,p.state_key,predecessor)
    key=(j,q,p.state_key[2],p.prefix)
    return TerminalResult("attained_optimum",primary_value=j,key=key,witness=witness)
