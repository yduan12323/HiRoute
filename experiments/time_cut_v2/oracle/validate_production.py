"""Adapter-only production imports; expected results come solely from oracle.py.

Run with --repo PATH. Full symbolic C/CS checks and point-fuzz are counted
separately. No random/grid check is presented as a full-energy proof.
"""
from __future__ import annotations
import argparse
import importlib
import json
import random
import sys
import time
from dataclasses import dataclass, replace
from fractions import Fraction as Q
from itertools import combinations
from pathlib import Path
from oracle import Aff, Answer, Oracle, Seed, Span


@dataclass(frozen=True)
class Case:
    name: str
    seeds: tuple
    segments: tuple
    overhead: Q = Q(1)
    schedule: tuple | None = None

    def oracle(self):
        kwargs = {} if self.schedule is None else dict(zip(('a','b','duration'),self.schedule))
        return Oracle([Seed(Span(*d),Q(m),Q(c),chi) for d,m,c,chi in self.seeds],self.segments,self.overhead,**kwargs)


def adversarial_cases():
    linear = ((0,8,2,0),)
    cases = [
        Case('historical_open_lower_endpoint',(((0,1,False,True),60,1000,True),),((0,10,36,0),),Q(300)),
        Case('negative_tau_minus_f',(((0,2),0,100,True),),linear),
        Case('zero_tau_minus_f',(((0,2,False,False),2,100,True),),linear),
        Case('positive_tau_minus_f',(((0,2),4,100,True),),linear),
        Case('open_input_zero_tau_minus_f',(((0,2),2,100,False),),linear),
        Case('right_excluded_optimizer',(((0,1,True,False),0,100,True),),linear),
        Case('singleton_positive_charge',(((2,2),0,0,True),),linear),
        Case('at_capacity_no_positive_charge',(((8,8),0,0,True),),linear),
        Case('empty_input',(),linear),
        Case('charge_kinks',(((0,3),2,0,True),),((0,1,1,0),(1,3,3,-2))),
        Case('attainment_tie_or',(((0,1,False,True),4,0,True),((0,0),0,0,True)),linear),
        Case('same_value_open_then_closed',(((0,2),2,0,False),((0,2),2,0,True)),linear),
        Case('deadline_equality_open',(((0,0),0,4,False),),linear,schedule=(5,5,2)),
        Case('deadline_equality_closed',(((0,0),0,4,True),),linear,schedule=(5,5,2)),
        Case('plateau_open_input_boundary',(((0,0),0,0,False),),((0,8,1,0),),schedule=(5,5,2)),
        Case('plateau_closed_endpoint',(((0,0),0,0,True),),((0,8,1,0),),schedule=(5,5,2)),
        Case('deadline_crosses_energy_open',(((0,4),1,0,False),),linear,schedule=(1,3,1)),
        Case('deadline_crosses_energy_closed',(((0,4),1,0,True),),linear,schedule=(1,3,1)),
        Case('negative_time_slope_cs',(((0,4,False,False),-2,10,False),),linear,schedule=(5,10,2)),
        Case('zero_service_duration_cs',(((0,4),0,0,False),),linear,schedule=(5,6,0)),
        Case('invalid_schedule',(((0,4),0,0,True),),linear,schedule=(6,5,1)),
        Case('cs_arrival_and_departure_kinks',(((0,5,False,True),2,0,False),((1,3),0,4,True)),((0,1,1,0),(1,3,3,-2),(3,6,2,1)),schedule=(5,9,3)),
    ]
    return cases


def random_case(rng,index):
    cap = rng.randint(2,7)
    cuts = sorted({0,cap,*[rng.randint(1,cap-1) for _ in range(rng.randint(0,2))]})
    segments = []
    value = Q(0)
    for lo,hi in zip(cuts,cuts[1:]):
        slope = Q(rng.randint(1,5),rng.randint(1,3))
        intercept = value-slope*lo
        segments.append((Q(lo),Q(hi),slope,intercept))
        value = slope*hi+intercept
    seeds = []
    for _ in range(rng.randint(1,3)):
        lo,hi = sorted((Q(rng.randint(0,2*cap),2),Q(rng.randint(0,2*cap),2)))
        lc,rc = (True,True) if lo == hi else (bool(rng.randrange(2)),bool(rng.randrange(2)))
        m,c = Q(rng.randint(-5,6),rng.randint(1,3)),Q(30+rng.randint(0,5))
        seeds.append(((lo,hi,lc,rc),m,c,bool(rng.randrange(2))))
    h = Q(rng.randint(1,4),rng.randint(1,3))
    schedule = None if index%2 == 0 else (Q(rng.randint(15,35)),Q(rng.randint(28,50)),Q(rng.randint(0,8)))
    return Case(f'random_{index:04}',tuple(seeds),tuple(segments),h,schedule)


class Adapter:
    def __init__(self,repo):
        sys.path.insert(0,str(Path(repo)/'src'))
        self.probe = importlib.import_module('timecut5.probe')
        self.pwa = importlib.import_module('timecut5.pwa')

    def evaluate(self,case):
        p = self.probe
        state = p.State('arrival',1,0)
        families = [p.AffineFamily(p.Interval(*d),m,c,chi,Q(0),(),state) for d,m,c,chi in case.seeds]
        inputs = tuple(self.pwa.CutPiece.from_affine(f) for f in families)
        curve = p.ChargingCurve(case.segments)
        if case.schedule is None:
            outputs = self.pwa.charge_pwa(inputs,curve,case.overhead,'charger')
        else:
            a,b,duration = case.schedule
            outputs = self.pwa.combined_pwa(inputs,curve,'charger',a,b,duration,case.overhead)
        return inputs,curve,tuple(outputs)


def actual_at(pieces,energy):
    active = [p for p in pieces if p.domain.contains(energy)]
    if not active:
        return None,None
    tau = min(p.slope*energy+p.intercept for p in active)
    ties = [p for p in active if p.slope*energy+p.intercept == tau]
    chosen = next((p for p in ties if p.chi),ties[0])
    return Answer(tau,any(p.chi for p in ties)),chosen


def exact_curve_at(segments,energy):
    for lo,hi,m,c in segments:
        if lo <= energy <= hi:
            return m*energy+c
    raise AssertionError(f'energy {energy} outside charging primitive')


def replay_witness(case,witness,output_energy,expected,limit,exact):
    assert witness.energy == output_energy
    assert witness.rho == 0
    effect = 'C' if case.schedule is None else 'CS'
    assert witness.pi == (('charger',effect),)
    assert witness.state.anchor == 'charger'
    assert witness.state.stop_count == 1
    assert witness.state.remaining_schedule == (1 if case.schedule is None else 0)
    assert expected.tau <= witness.time <= limit
    assert not exact or witness.time == expected.tau
    assert len(witness.events) == 2, 'one analytic seed plus one physical transition expected'
    seed,event = witness.events
    assert seed.effect == 'analytic_seed'
    assert seed.arrival_energy == seed.departure_energy == event.arrival_energy
    assert seed.arrival_time == seed.departure_time == event.arrival_time
    assert event.effect == effect and event.site == 'charger'
    assert event.departure_energy == output_energy and event.departure_time == witness.time
    # The original analytic seed describes actual membership, including its
    # finite open-time interval (tau,tau+1]. Do not validate a relaxed closure.
    energy,t = event.arrival_energy,event.arrival_time
    memberships = []
    for d,m,c,chi in case.seeds:
        tau = m*energy+c
        memberships.append(Span(*d).contains(energy) and (t == tau if chi else tau < t <= tau+1))
    assert any(memberships), 'predecessor witness escaped the input subfamily'
    assert output_energy > energy, 'zero charging is forbidden'
    d = exact_curve_at(case.segments,output_energy)-exact_curve_at(case.segments,energy)
    assert d > 0
    if case.schedule is None:
        assert witness.time == t+case.overhead+d
    else:
        a,b,duration = case.schedule
        assert max(a,t+case.overhead) <= b, 'latest-start guard violated'
        assert witness.time == max(t+case.overhead+d,max(a,t+case.overhead)+duration)


def check_witnesses(case,piece,energy,expected):
    cut = piece.at(energy)
    assert (cut.tau,cut.chi) == (expected.tau,expected.chi)
    count = 0
    if expected.chi:
        witness = cut.minimum()
        replay_witness(case,witness,energy,expected,expected.tau,True)
        count += 1
    else:
        try:
            cut.realize_le(expected.tau)
        except ValueError:
            pass
        else:
            raise AssertionError('an open cut accepted its exact boundary budget')
    for eps in (Q(1),Q(1,7),Q(1,997)):
        witness = cut.realize_le(expected.tau+eps)
        replay_witness(case,witness,energy,expected,expected.tau+eps,expected.chi)
        if not expected.chi:
            assert witness.time > expected.tau
        count += 1
    return count


def symbolic_compare(case,oracle,outputs,witnesses=True):
    expected = oracle.pieces()
    boundaries = set(oracle.boundaries())
    for p in outputs:
        assert 0 <= p.domain.lo <= p.domain.hi <= oracle.capacity, 'output support outside capacity'
        boundaries.update((p.domain.lo,p.domain.hi))
    for p,q in combinations(outputs,2):
        root = Aff(p.slope,p.intercept).root_against(Aff(q.slope,q.intercept))
        if root is not None and 0 <= root <= oracle.capacity:
            boundaries.add(root)
    knots = sorted(boundaries)
    singleton_count = cell_count = witness_count = 0
    for energy in knots:
        want = oracle.at(energy)
        got,piece = actual_at(outputs,energy)
        assert got == want, f'{case.name}: singleton E={energy}: actual={got}, expected={want}'
        singleton_count += 1
        if got is not None and witnesses:
            witness_count += check_witnesses(case,piece,energy,want)
    for lo,hi in zip(knots,knots[1:]):
        mid = (lo+hi)/2
        exp = next((row for row in expected if row[0].contains(mid)),None)
        got,piece = actual_at(outputs,mid)
        if exp is None:
            assert got is None, f'{case.name}: extra output on ({lo},{hi})'
        else:
            _,line,chi = exp
            assert piece is not None, f'{case.name}: missing output on ({lo},{hi})'
            assert (piece.slope,piece.intercept,got.chi) == (line.slope,line.intercept,chi), f'{case.name}: affine/chi mismatch on ({lo},{hi}): actual={(piece.slope,piece.intercept,got.chi)}, expected={(line.slope,line.intercept,chi)}'
            if witnesses:
                witness_count += check_witnesses(case,piece,mid,Answer(line(mid),chi))
        cell_count += 1
    return dict(open_cells=cell_count,singletons=singleton_count,witnesses=witness_count)


def mutation_sentinels(adapter):
    """Prove the validator rejects numerical, attainment and support faults."""
    case = next(c for c in adversarial_cases() if c.name == 'plateau_closed_endpoint')
    _,_,outputs = adapter.evaluate(case)
    assert outputs
    fault_sets = [
        ('value',tuple(replace(p,intercept=p.intercept+Q(1,10**9)) for p in outputs)),
        ('attainment',tuple(replace(p,chi=not p.chi) for p in outputs)),
        ('missing_support',()),
    ]
    caught = []
    for name,mutant in fault_sets:
        try:
            symbolic_compare(case,case.oracle(),mutant,witnesses=False)
        except AssertionError:
            caught.append(name)
        else:
            raise AssertionError(f'validator failed to reject {name} mutation')
    return caught


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo',required=True)
    parser.add_argument('--symbolic-random',type=int,default=80)
    parser.add_argument('--point-random',type=int,default=120)
    parser.add_argument('--output',default='validation_results.json')
    args = parser.parse_args()
    start = time.monotonic()
    adapter = Adapter(args.repo)
    rng = random.Random(20261006)
    cases = adversarial_cases()+[random_case(rng,i) for i in range(args.symbolic_random)]
    report = {'method':'independent analytic candidate arrangement; no production projection/reduction helpers','full_symbolic':{'cases':0,'open_cells':0,'singletons':0,'witnesses':0},'point_fuzz_only':{'cases':0,'energies':0,'witnesses':0},'cases':[]}
    for case in cases:
        _,_,outputs = adapter.evaluate(case)
        try:
            stats = symbolic_compare(case,case.oracle(),outputs)
        except Exception:
            print('FAILED CASE',repr(case),flush=True)
            raise
        report['full_symbolic']['cases'] += 1
        for k,v in stats.items():
            report['full_symbolic'][k] += v
        report['cases'].append({'name':case.name,'mode':'full_symbolic','production_pieces':len(outputs),**stats})
        print('PASS',case.name,stats,flush=True)
    for i in range(args.point_random):
        case = random_case(rng,i+10000)
        _,_,outputs = adapter.evaluate(case)
        oracle = case.oracle()
        for energy in {Q(0),oracle.capacity,*[Q(rng.randrange(0,1001),1000)*oracle.capacity for _ in range(8)]}:
            got,piece = actual_at(outputs,energy)
            want = oracle.at(energy)
            assert got == want, f'point-fuzz-only {case!r}, E={energy}: {got} != {want}'
            report['point_fuzz_only']['energies'] += 1
            if got is not None:
                report['point_fuzz_only']['witnesses'] += check_witnesses(case,piece,energy,want)
        report['point_fuzz_only']['cases'] += 1
    report['mutation_sentinels'] = mutation_sentinels(adapter)
    report['seconds'] = round(time.monotonic()-start,3)
    Path(args.output).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k != 'cases'},indent=2))


if __name__ == '__main__':
    main()
