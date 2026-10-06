"""Directed independent whole-domain D/S/reduction/congruence checks."""
from __future__ import annotations
import argparse
import json
from dataclasses import dataclass, replace
from fractions import Fraction as Q
from itertools import combinations
from pathlib import Path
from oracle import Aff, Oracle, Seed, Span
from validate_production import Adapter, exact_curve_at


@dataclass(frozen=True)
class Piece:
    domain: Span
    line: Aff
    chi: bool
    rho: Q
    pi: tuple
    state: tuple

    @classmethod
    def read(cls,p):
        d = p.domain
        s = p.state
        return cls(Span(d.lo,d.hi,d.left_closed,d.right_closed),Aff(p.slope,p.intercept),p.chi,p.rho,p.pi,(s.anchor,s.remaining_schedule,s.stop_count))


def knots_for(pieces):
    knots = {x for p in pieces for x in (p.domain.lo,p.domain.hi)}
    for p,q in combinations(pieces,2):
        root = p.line.root_against(q.line)
        if root is not None and knots and min(knots) <= root <= max(knots):
            knots.add(root)
    return sorted(knots)


def cells_for(pieces):
    knots = knots_for(pieces)
    return [Span(x,x) for x in knots]+[Span(x,y,False,False) for x,y in zip(knots,knots[1:])]


def dominates(p,q,e):
    pt,qt = p.line(e),q.line(e)
    time_ok = pt < qt or pt == qt and (p.chi or not q.chi)
    return p.state == q.state and time_ok and p.rho <= q.rho and (p.rho < q.rho or p.pi <= q.pi)


def minimal_classes(active,e):
    """Pairwise strict domination + equivalence classes; no production reducer."""
    classes = []
    for p in active:
        if any(dominates(q,p,e) and not dominates(p,q,e) for q in active):
            continue
        if not any(dominates(q,p,e) and dominates(p,q,e) for q in classes):
            classes.append(p)
    return classes


def verify_coverage(expected,actual,*,antichain=False):
    """A complete affine arrangement freezes every support/dominance predicate."""
    count = {'open_cells':0,'singletons':0}
    for cell in cells_for(tuple(expected)+tuple(actual)):
        e = cell.member()
        want = [p for p in expected if p.domain.contains(e)]
        got = [p for p in actual if p.domain.contains(e)]
        assert all(any(dominates(p,q,e) for p in want) for q in got),f'extra/non-covered actual class at E={e}'
        assert all(any(dominates(p,q,e) for p in got) for q in want),f'missing expected class at E={e}'
        if antichain:
            assert len(got) == len(minimal_classes(got,e)),f'nonminimal/duplicate class at E={e}'
        count['singletons' if cell.lo == cell.hi else 'open_cells'] += 1
    return count


def independent_reduce(pieces):
    output = []
    for cell in cells_for(pieces):
        e = cell.member()
        output.extend(replace(p,domain=cell) for p in minimal_classes([p for p in pieces if p.domain.contains(e)],e))
    return tuple(output)


def independent_drive(pieces,duration,consumption,floor):
    result = []
    for p in pieces:
        d = Span(p.domain.lo-consumption,p.domain.hi-consumption,p.domain.lc,p.domain.rc)
        if d.hi < floor:
            continue
        d = d.intersect(Span(floor,d.hi))
        if d:
            result.append(replace(p,domain=d,line=Aff(p.line.slope,p.line.intercept+p.line.slope*consumption+duration),rho=p.rho+consumption,state=('next',p.state[1],p.state[2])))
    return tuple(result)


def independent_schedule(pieces,a,b,duration,h):
    out = []
    if a > b:
        return ()
    for p in pieces:
        knots = {p.domain.lo,p.domain.hi}
        if p.line.slope:
            for threshold in (a-h,b-h):
                e = (threshold-p.line.intercept)/p.line.slope
                if p.domain.lo <= e <= p.domain.hi:
                    knots.add(e)
        knots = sorted(knots)
        cells = [Span(x,x) for x in knots if p.domain.contains(x)]
        cells += [Span(x,y,False,False) for x,y in zip(knots,knots[1:])]
        for cell in cells:
            e = cell.member()
            tau = p.line(e)
            if tau > b-h or tau == b-h and not p.chi:
                continue
            line = Aff(Q(0),a+duration) if tau+h <= a else Aff(p.line.slope,p.line.intercept+h+duration)
            chi = p.chi or tau < a-h
            out.append(Piece(cell,line,chi,p.rho,p.pi+(('stop','S'),),('stop',0,p.state[2]+1)))
    return tuple(out)


def group(pieces):
    groups = {}
    for p in pieces:
        key = (p.state,p.rho,p.pi)
        groups.setdefault(key,[]).append(p)
    return groups.values()


def independent_stop(pieces,segments,h,schedule=None):
    out = []
    for family in group(pieces):
        first = family[0]
        kwargs = {} if schedule is None else dict(zip(('a','b','duration'),schedule))
        oracle = Oracle([Seed(p.domain,p.line.slope,p.line.intercept,p.chi) for p in family],segments,h,**kwargs)
        effect = 'C' if schedule is None else 'CS'
        state = ('stop',first.state[1] if schedule is None else 0,first.state[2]+1)
        for domain,line,chi in oracle.pieces():
            out.append(Piece(domain,line,chi,first.rho,first.pi+(('stop',effect),),state))
    return tuple(out)


def directed_frontiers():
    def p(d,m,c,chi=True,rho=0,name='a'):
        return Piece(Span(*d),Aff(Q(m),Q(c)),chi,Q(rho),((name,'C'),),('arrival',1,1))
    return {
        'rho_tradeoff_survives_then_plateau':(p((0,5),0,0,rho=5),p((0,5),0,2,rho=1,name='b')),
        'strict_rho_overrides_pi':(p((0,5),0,0,rho=0,name='z'),p((0,5),0,2,rho=1)),
        'equal_rho_pi_still_matters':(p((0,5),0,0,name='z'),p((0,5),0,2)),
        'singleton_closed_beats_open':(p((0,5),0,0,False),p((2,2),0,0,True)),
        'disjoint_domains_and_holes':(p((0,1,False,False),0,0),p((2,3,True,False),0,1,name='b'),p((5,5),0,0)),
        'affine_crossing_and_chi_tie':(p((0,5),1,0,False),p((0,5),-1,4,True)),
        'equivalent_duplicates_keep_one':(p((0,5),0,0),p((0,5),0,0),p((2,2),0,0)),
        'excluded_deadline_face':(p((0,5,False,True),1,3,False),p((1,4,True,False),-1,8,True,name='b')),
        'rational_disjoint_singleton':(p((Q(1,3),Q(7,3),False,False),Q(2,3),Q(1,7),False),p((Q(7,3),Q(7,3)),0,2,True,name='b')),
    }


def to_public(adapter,pieces):
    p = adapter.probe
    return tuple(adapter.pwa.CutPiece.from_affine(p.AffineFamily(p.Interval(x.domain.lo,x.domain.hi,x.domain.lc,x.domain.rc),x.line.slope,x.line.intercept,x.chi,x.rho,x.pi,p.State(*x.state))) for x in pieces)


def transform_public(adapter,pieces,effect,curve):
    if effect == 'D':
        return adapter.pwa.drive_pwa(pieces,'next',Q(2),Q(1),Q(1,2))
    result = []
    families = {}
    for p in pieces:
        families.setdefault((p.state,p.rho,p.pi),[]).append(p)
    for family in families.values():
        if effect == 'S':
            transformed = adapter.pwa.schedule_pwa(family,'stop',Q(6),Q(8),Q(2),Q(1))
        elif effect == 'C':
            transformed = adapter.pwa.charge_pwa(family,curve,Q(1),'stop')
        else:
            transformed = adapter.pwa.combined_pwa(family,curve,'stop',Q(6),Q(8),Q(2),Q(1))
        result.extend(transformed)
    return tuple(result)


def replay_one_step(source,outputs,effect,segments):
    count = 0
    for piece in outputs:
        e = (piece.domain.lo+piece.domain.hi)/2
        cut = piece.at(e)
        for epsilon in (Q(1,7),Q(1,10**12)):
            witness = cut.realize_le(cut.tau+epsilon)
            assert witness.energy == e and cut.tau <= witness.time <= cut.tau+epsilon
            assert witness.time == cut.tau if cut.chi else witness.time > cut.tau
            assert (witness.rho,witness.pi,witness.state) == (piece.rho,piece.pi,piece.state)
            assert len(witness.events) == 2
            seed,event = witness.events
            assert seed.effect == 'analytic_seed' and event.effect == effect
            assert seed.arrival_time == seed.departure_time == event.arrival_time
            assert seed.arrival_energy == seed.departure_energy == event.arrival_energy
            assert event.departure_time == witness.time and event.departure_energy == e
            old_pi = piece.pi if effect == 'D' else piece.pi[:-1]
            old_rho = piece.rho-Q(1) if effect == 'D' else piece.rho
            x,t = event.arrival_energy,event.arrival_time
            assert any(p.pi == old_pi and p.rho == old_rho and p.domain.contains(x)
                       and (t == p.line(x) if p.chi else p.line(x) < t <= p.line(x)+1)
                       for p in source), 'witness escaped original analytic input'
            if effect == 'D':
                assert x-e == 1 and e >= Q(1,2) and witness.time == t+2
            else:
                assert piece.pi[-1] == ('stop',effect)
                if effect in ('C','CS'):
                    assert e > x
                    d = exact_curve_at(segments,e)-exact_curve_at(segments,x)
                if effect in ('S','CS'):
                    assert max(Q(6),t+1) <= 8
                    service = max(Q(6),t+1)+2
                assert witness.time == (t+1+d if effect == 'C' else service if effect == 'S' else max(t+1+d,service))
                if effect == 'S':
                    assert e == x
            count += 1
    return count


def replay_restricted_two_charge(adapter):
    """Analytic expected 4-Ea at Ed=1, restricted Ea<=1/2: minimum 7/2."""
    p,w = adapter.probe,adapter.pwa
    seed = w.CutPiece.from_affine(p.AffineFamily(p.Interval(0,0),0,0,True,0,(),p.State('start',1,0)))
    f1,f2 = p.ChargingCurve(((0,2,1,0),)),p.ChargingCurve(((0,2,2,0),))
    first = w.charge_pwa((seed,),f1,1,'one')
    restricted = []
    for piece in first:
        d = piece.domain.intersect(p.Interval(0,Q(1,2),False,True))
        if d:
            restricted.append(replace(piece,domain=d))
    second = w.charge_pwa(restricted,f2,1,'two')
    active = [x for x in second if x.domain.contains(Q(1))]
    assert active
    winner = min(active,key=lambda x:(x.slope+x.intercept,not x.chi))
    cut = winner.at(Q(1))
    assert (cut.tau,cut.chi) == (Q(7,2),True)
    witness = cut.minimum()
    assert len(witness.events) == 3
    seed_event,one,two = witness.events
    assert seed_event.arrival_energy == seed_event.departure_energy == 0
    assert seed_event.arrival_time == seed_event.departure_time == 0
    assert one.effect == two.effect == 'C'
    assert one.arrival_energy == 0 and 0 < one.departure_energy <= Q(1,2)
    assert one.departure_energy == two.arrival_energy < two.departure_energy == 1
    assert one.arrival_time == 0 and one.departure_time == 1+one.departure_energy
    assert two.arrival_time == one.departure_time
    assert two.departure_time == two.arrival_time+1+2*(1-two.arrival_energy) == Q(7,2)
    # On the open restriction Ea<1/2, the same infimum is not attained.
    restricted_open = []
    for piece in first:
        d = piece.domain.intersect(p.Interval(0,Q(1,2),False,False))
        if d:
            restricted_open.append(replace(piece,domain=d))
    second_open = w.charge_pwa(restricted_open,f2,1,'two')
    cut_open = next(x.at(Q(1)) for x in second_open if x.domain.contains(Q(1)))
    assert (cut_open.tau,cut_open.chi) == (Q(7,2),False)
    for epsilon in (Q(1,7),Q(1,10**12)):
        witness = cut_open.realize_le(Q(7,2)+epsilon)
        _,one,two = witness.events
        assert 0 < one.departure_energy == two.arrival_energy < Q(1,2)
        assert witness.time == 4-two.arrival_energy
        assert Q(7,2) < witness.time <= Q(7,2)+epsilon
    return 3


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo',required=True)
    parser.add_argument('--output',default='frontier_results.json')
    args = parser.parse_args()
    adapter = Adapter(args.repo)
    segments = ((Q(0),Q(2),Q(1),Q(0)),(Q(2),Q(6),Q(3),Q(-4)))
    curve = adapter.probe.ChargingCurve(segments)
    result = {'frontiers':0,'checks':0,'open_cells':0,'singletons':0,'operator_witnesses':0,'cases':[]}
    def record(name,stats):
        result['checks'] += 1
        for k,v in stats.items():
            result[k] += v
        result['cases'].append({'name':name,**stats})
    for name,source in directed_frontiers().items():
        inputs = to_public(adapter,source)
        for index,family in enumerate(group(source)):
            envelope = adapter.pwa.lower_envelope(to_public(adapter,family))
            record(name+f'/envelope_{index}',verify_coverage(family,tuple(map(Piece.read,envelope)),antichain=True))
            backwards = adapter.pwa.lower_envelope(tuple(reversed(to_public(adapter,family))))
            record(name+f'/envelope_order_{index}',verify_coverage(tuple(map(Piece.read,envelope)),tuple(map(Piece.read,backwards)),antichain=True))
        reduced = adapter.pwa.reduce_frontier(inputs)
        read_reduced = tuple(map(Piece.read,reduced))
        record(name+'/R_independent',verify_coverage(independent_reduce(source),read_reduced,antichain=True))
        rr = adapter.pwa.reduce_frontier(reduced)
        record(name+'/R_idempotence',verify_coverage(read_reduced,tuple(map(Piece.read,rr)),antichain=True))
        for effect in ('D','S','C','CS'):
            actual = transform_public(adapter,inputs,effect,curve)
            after_reduction = transform_public(adapter,reduced,effect,curve)
            result['operator_witnesses'] += replay_one_step(source,actual,effect,segments)
            result['operator_witnesses'] += replay_one_step(source,after_reduction,effect,segments)
            if effect == 'D':
                want = independent_drive(source,Q(2),Q(1),Q(1,2))
            elif effect == 'S':
                want = independent_schedule(source,Q(6),Q(8),Q(2),Q(1))
            else:
                want = independent_stop(source,segments,Q(1),None if effect == 'C' else (Q(6),Q(8),Q(2)))
            actual_read = tuple(map(Piece.read,actual))
            record(name+'/'+effect+'_independent',verify_coverage(want,actual_read))
            keys = {(p.state,p.rho,p.pi) for p in tuple(want)+actual_read}
            for index,key in enumerate(sorted(keys)):
                want_family = tuple(p for p in want if (p.state,p.rho,p.pi) == key)
                got_family = tuple(p for p in actual_read if (p.state,p.rho,p.pi) == key)
                record(name+'/'+effect+f'_family_{index}',verify_coverage(want_family,got_family))
            left = adapter.pwa.reduce_frontier(after_reduction)
            right = adapter.pwa.reduce_frontier(actual)
            record(name+'/'+effect+'_congruence',verify_coverage(tuple(map(Piece.read,right)),tuple(map(Piece.read,left)),antichain=True))
            record(name+'/'+effect+'_reduced_independent',verify_coverage(independent_reduce(want),tuple(map(Piece.read,left)),antichain=True))
        result['frontiers'] += 1
        print('PASS',name,flush=True)
    result['restricted_multistop_witnesses'] = replay_restricted_two_charge(adapter)
    Path(args.output).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k != 'cases'},indent=2))


if __name__ == '__main__':
    main()
