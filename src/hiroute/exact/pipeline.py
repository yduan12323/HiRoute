"""Composable exact FLAT transition pipeline and recursive witness replay."""
from __future__ import annotations
from dataclasses import dataclass
from fractions import Fraction
from typing import Iterable
from .interval import Interval
from .pwa import AffineCutPiece, PwaStepWitness, drive_piece, schedule_piece, _curve_value
from .pwa_partition import TransitionWitness, family_union, stop_partition
from .scalar import exact
from .terminal import terminal_optimize

@dataclass(frozen=True)
class InitialWitness:
    energy: Fraction
    time: Fraction
    prefix: tuple = ()
    rho: Fraction = Fraction(0)

@dataclass(frozen=True)
class DriveStep:
    anchor: str
    duration: Fraction
    consumption: Fraction
    floor: Fraction = Fraction(0)

@dataclass(frozen=True)
class StopStep:
    effect: str
    site: str
    overhead: Fraction
    curve_segments: tuple = ()
    a: Fraction | None = None
    b: Fraction | None = None
    duration: Fraction = Fraction(0)

def initial_piece(domain: Interval, start_time=0, anchor="origin", remaining_schedule=1,
                  prefix=(), rho=0, witness_lifter=None):
    start_time, rho = exact(start_time), exact(rho)
    prefix=tuple(tuple(item) for item in prefix)
    if not isinstance(domain, Interval): raise TypeError("domain must be Interval")
    if not isinstance(anchor, str) or not anchor: raise ValueError("invalid initial anchor")
    if type(remaining_schedule) is not int or remaining_schedule not in (0,1):
        raise ValueError("remaining_schedule must be 0 or 1")
    if any(len(item)!=2 for item in prefix):
        raise ValueError("invalid inherited stop prefix")
    def lift(energy, budget):
        energy,budget=exact(energy),exact(budget)
        if not domain.contains(energy) or budget < start_time:
            raise ValueError("initial witness outside source domain or time budget")
        if witness_lifter is not None:
            return witness_lifter(energy,budget)
        return InitialWitness(energy,budget,prefix,rho)
    return AffineCutPiece(domain,Fraction(0),start_time,True,rho,prefix,
                          (anchor,remaining_schedule,len(prefix)),lift)

def execute_exact_plan(initial: Iterable[AffineCutPiece], steps):
    """Apply D/S/C/CS in order, merging only a single inherited family."""
    pieces=tuple(initial)
    if not pieces: return ()
    for step in steps:
        out=[]
        if isinstance(step,DriveStep):
            d,c,f=map(exact,(step.duration,step.consumption,step.floor))
            for p in pieces:
                q=drive_piece(p,step.anchor,d,c,f)
                if q is not None: out.append(q)
        elif isinstance(step,StopStep):
            h=exact(step.overhead)
            if step.effect=="S":
                a,b,d=map(exact,(step.a,step.b,step.duration))
                for p in pieces: out.extend(schedule_piece(p,step.site,a,b,d,h))
            elif step.effect in ("C","CS"):
                curve=tuple(tuple(map(exact,row)) for row in step.curve_segments)
                out.extend(stop_partition(pieces,step.effect,step.site,curve,h,
                    a=0 if step.a is None else step.a,
                    b=0 if step.b is None else step.b,duration=step.duration))
            else: raise ValueError("unsupported stop effect")
        else: raise TypeError("unknown transition step")
        pieces=family_union(out)
        if not pieces: return ()
    return pieces

def _close(a,b): return exact(a)==exact(b)

def replay_chain(witness):
    """Replay all exact transition equations and return the physical state."""
    if isinstance(witness,InitialWitness):
        return witness.energy,witness.time,tuple(witness.prefix),exact(witness.rho),()
    if not isinstance(witness,(PwaStepWitness,TransitionWitness)):
        raise TypeError("unknown witness node")
    ie,it,events,rho,trace=replay_chain(witness.predecessor)
    if not _close(ie,witness.input_energy) or not _close(it,witness.input_time):
        raise ValueError("disconnected predecessor witness")
    if witness.effect=="D":
        duration,consumption,floor=map(exact,witness.parameters)
        oe=ie-consumption; ot=it+duration
        if oe<floor: raise ValueError("drive violates energy floor")
        next_rho=rho+consumption; next_events=events
    elif witness.effect=="S":
        a,b,duration,overhead=map(exact,witness.parameters)
        if it>b-overhead: raise ValueError("schedule starts after latest start")
        oe=ie; ot=max(a+duration,it+overhead+duration)
        next_rho=rho; next_events=events+((witness.site,"S"),)
    elif witness.effect in ("C","CS"):
        curve,overhead,a,b,duration=witness.parameters
        overhead,a,b,duration=map(exact,(overhead,a,b,duration))
        curve=tuple(tuple(map(exact,row)) for row in curve)
        if witness.output_energy<=ie: raise ValueError("charge does not strictly increase energy")
        delta=_curve_value(curve,witness.output_energy)-_curve_value(curve,ie)
        if witness.effect=="C":
            oe=witness.output_energy; ot=it+overhead+delta
        else:
            if it>b-overhead: raise ValueError("combined stop starts after latest start")
            oe=witness.output_energy
            ot=max(a+duration,it+overhead+max(delta,duration))
        next_rho=rho; next_events=events+((witness.site,witness.effect),)
    else: raise ValueError("unknown witness effect")
    if not _close(oe,witness.output_energy) or not _close(ot,witness.output_time):
        raise ValueError("transition witness equation mismatch")
    next_trace=trace+((witness.effect,witness.site,ie,it,oe,ot),)
    return oe,ot,next_events,next_rho,next_trace

def replay_terminal(result, destination, reserve, start_time=0, stop_penalty=0):
    """Check terminal key and the full linked witness without a legacy solver."""
    if result.status!="attained_optimum" or result.witness is None or result.key is None:
        raise ValueError("terminal result has no replayable attained witness")
    e,t,events,rho,trace=replay_chain(result.witness.predecessor)
    w=result.witness
    if not _close(e,w.energy) or not _close(t,w.time):
        raise ValueError("terminal does not match replayed route endpoint")
    if w.state_key[0]!=destination or e<exact(reserve):
        raise ValueError("terminal destination or reserve violation")
    if tuple(events)!=w.prefix or len(events)!=w.state_key[2]:
        raise ValueError("terminal event prefix/count mismatch")
    q=e+rho
    j=t-exact(start_time)+exact(stop_penalty)*len(events)
    key=(j,q,len(events),tuple(events))
    if tuple(result.key)!=key: raise ValueError("terminal lexicographic key mismatch")
    return {"energy":e,"time":t,"rho":rho,"events":tuple(events),"trace":trace,"key":key}
