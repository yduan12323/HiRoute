"""Complete-cell exact coalescing checks; optional prototype stays disabled."""
from dataclasses import replace
from fractions import Fraction as R
from itertools import product
import random
import unittest

from timecut5.coalesce import coalesce_pieces,CoalescedDispatch
from timecut5.probe import Interval,State,Event,Witness,Cut,terminal
from timecut5.pwa import CutPiece,charge_pwa,schedule_pwa
from timecut5.bounded import Problem,replay_witness


def seed(domain,slope=R(1),intercept=R(30),chi=True,rho=R(0),pi=(),state=State('x',1,0),tag='seed'):
    def point(energy):
        if not domain.contains(energy):raise AssertionError('Escaped inherited energy guard')
        tau=slope*energy+intercept
        def approach(epsilon):
            time=tau if chi else tau+epsilon/2
            return Witness(time,energy,rho,pi,state,(Event('analytic',tag,time,time,energy,energy),))
        return Cut(tau,chi,energy,rho,pi,state,approach)
    return CutPiece(domain,slope,intercept,chi,rho,pi,state,point)


def cells(pieces):
    endpoints=sorted({e for p in pieces for e in (p.domain.lo,p.domain.hi)})
    points=[]
    for i,e in enumerate(endpoints):
        points.append((e,False))
        if i+1<len(endpoints):points.append(((e+endpoints[i+1])/2,True))
    return points


def fingerprint(pieces,energy,open_cell):
    return {(p.slope,p.intercept,p.chi,p.rho,p.pi,p.state) if open_cell else
            (p.slope*energy+p.intercept,p.chi,p.rho,p.pi,p.state)
            for p in pieces if p.domain.contains(energy)}


def equivalent(test,before,after):
    # Endpoint arrangement is complete: each affine metadata tuple is constant
    # on each open cell. This compares symbolic affine functions, not sampled SOC.
    for energy,open_cell in cells((*before,*after)):
        test.assertEqual(fingerprint(before,energy,open_cell),fingerprint(after,energy,open_cell))
        for piece in after:
            if piece.domain.contains(energy):
                for epsilon in (R(100),R(1,10**30)):
                    cut=piece.at(energy);w=cut.approach(epsilon)
                    test.assertEqual((w.energy,w.rho,w.pi,w.state),(energy,piece.rho,piece.pi,piece.state))
                    test.assertGreaterEqual(w.time,cut.tau)
                    test.assertLess(w.time,cut.tau+epsilon)
                    if cut.chi:test.assertEqual(w.time,cut.tau)


class TestExactCoalescing(unittest.TestCase):
    def test_all_touching_endpoint_combinations(self):
        for right,left in product((False,True),repeat=2):
            with self.subTest(right=right,left=left):
                original=(seed(Interval(0,1,True,right)),seed(Interval(1,2,left,True)))
                result=coalesce_pieces(original)
                self.assertEqual(len(result),1 if right or left else 2)
                equivalent(self,original,result)

    def test_covering_singleton_and_missing_point(self):
        original=(seed(Interval(0,1,False,False)),seed(Interval(1,2,False,False)))
        self.assertEqual(len(coalesce_pieces(original)),2)
        covered=(*original,seed(Interval(1,1)))
        result=coalesce_pieces(covered)
        self.assertEqual(tuple(p.domain for p in result),(Interval(0,2,False,False),))
        equivalent(self,covered,result)

    def test_singletons_disconnected_cells_and_crossings(self):
        original=(seed(Interval(0,0)),seed(Interval(1,1)),seed(Interval(2,3)),seed(Interval(2,3),slope=R(-1),intercept=R(35)))
        result=coalesce_pieces(original)
        self.assertEqual(len(result),4)
        equivalent(self,original,result)

    def test_context_and_attainment_never_merge(self):
        context=dict(pi=(('x','C'),),state=State('x',1,1))
        base=seed(Interval(0,1),**context)
        def changed(**values):return seed(Interval(1,2),**dict(context,**values))
        variants=[changed(chi=False),changed(rho=R(1)),changed(pi=(('y','C'),)),
          changed(state=State('y',1,1)),changed(state=State('x',0,1)),
          changed(state=State('x',1,2),pi=(('x','C'),('x','C'))),
          changed(slope=R(2)),changed(intercept=R(31))]
        for variant in variants:
            result=coalesce_pieces((base,variant))
            self.assertEqual(len(result),2)
            equivalent(self,(base,variant),result)

    def test_terminal_primary_nonattainment_is_unchanged(self):
        pieces=(seed(Interval(0,1,False,False),state=State('z',0,0)),
                seed(Interval(1,2),state=State('z',0,0)))
        values=[terminal(x,'z',R(0),R(0),R(0)) for x in (pieces,coalesce_pieces(pieces))]
        for value in values:
            self.assertEqual(value.status,'infimum_unattained')
            self.assertEqual(value.unattained_component,'J')
            self.assertEqual(value.primary_infimum,30)
            self.assertIsNone(value.witness)

    def test_immutable_guarded_dispatch_and_distinct_witnesses(self):
        a=seed(Interval(0,2,False,False),chi=False,tag='first')
        b=seed(Interval(1,3),chi=False,tag='second')
        result=coalesce_pieces((a,b),family_ids=('parent-A','parent-B'))[0]
        self.assertIsInstance(result._point,CoalescedDispatch)
        self.assertEqual(result._point.parents[0].parent_family_id,'parent-A')
        self.assertEqual(result._point.parents[0].energy_guard,a.domain)
        self.assertIs(result._point.parents[0].piece,a)
        self.assertEqual(result.at(R(3,2)).approach(R(1)).events[0].site,'first')
        self.assertEqual(result.at(R(2)).approach(R(1)).events[0].site,'second')
        with self.assertRaises(ValueError):result.at(R(0))
        equivalent(self,(a,b),(result,))

    def test_nested_union_preserves_original_guards(self):
        original=tuple(seed(Interval(i,i+1),tag=str(i)) for i in range(4))
        first=coalesce_pieces(original[:2],family_ids=('A','B'))[0]
        result=coalesce_pieces((first,*original[2:]),family_ids=('union-AB','C','D'))
        self.assertEqual(len(result),1)
        equivalent(self,original,result)
        self.assertIs(result[0]._point.parents[0].piece,first)

    def test_random_exact_symbolic_unions(self):
        rng=random.Random(762013)
        for _ in range(250):
            pieces=[]
            for index in range(rng.randrange(1,10)):
                lo=R(rng.randrange(0,12),3);hi=lo+R(rng.randrange(0,9),3)
                lc,rc=(True,True) if lo==hi else (rng.choice((False,True)),rng.choice((False,True)))
                pieces.append(seed(Interval(lo,hi,lc,rc),slope=R(rng.choice((0,1,2))),
                   intercept=R(rng.choice((30,31))),chi=rng.choice((False,True)),tag=str(index)))
            result=coalesce_pieces(pieces)
            self.assertLessEqual(len(result),len(pieces))
            equivalent(self,tuple(pieces),result)
            equivalent(self,result,coalesce_pieces(result))

    def test_many_redundant_cells_collapse_without_grid_approximation(self):
        pieces=[]
        for i in range(30):
            pieces.append(seed(Interval(R(i,7),R(i,7))))
            pieces.append(seed(Interval(R(i,7),R(i+1,7),False,False)))
        pieces.append(seed(Interval(R(30,7),R(30,7))))
        result=coalesce_pieces(pieces)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0].domain,Interval(0,R(30,7)))
        equivalent(self,tuple(pieces),result)

    def test_cropped_physical_prefix_then_C_S_terminal(self):
        case=dict(H_ref=3,origin='x',destination='z',start_time_s=0,initial_energy_kwh=2,capacity_kwh=5,
          minimum_energy_kwh=0,reserve_kwh=0,consumption_kwh_per_m=1,overhead_s=1,lambda_stop_s=0,
          schedule=dict(a=10,b=20,D=1),charging_segments=[[0,5,1,0]],sites={'x':['C'],'y':['S']},
          edges=[dict(source='x',target='y',time_s=1,length_m=1),dict(source='y',target='z',time_s=1,length_m=1)])
        problem=Problem(case);first=problem.advance((problem.initial_piece(),),'x','C')
        # Split each existing constrained piece; never reconstruct from the
        # unrestricted initial prefix. A singleton3 can supply its own guard.
        splits=[]
        for p in first:
            for window in (Interval(2,3,False,False),Interval(3,3),Interval(3,5,False,True)):
                domain=p.domain.intersect(window)
                if domain is not None:splits.append(replace(p,domain=domain))
        merged=coalesce_pieces(splits,family_ids=tuple(f'cropped-{i}' for i in range(len(splits))))
        equivalent(self,tuple(splits),merged)
        outputs=[]
        for inputs in (tuple(splits),merged):
            second=problem.advance(inputs,'x','C');scheduled=problem.advance(second,'y','S');finished=problem.finish(scheduled)
            outputs.append(terminal(finished,'z',R(0),R(0),R(0)))
            for p in finished:
                energy=(p.domain.lo+p.domain.hi)/2
                if not p.domain.contains(energy):continue
                witness=p.at(energy).approach(R(1,10**12))
                replay_witness(case,witness)
                first_charge=next(e for e in witness.events if e.effect=='C')
                self.assertTrue(any(q.domain.contains(first_charge.departure_energy) for q in splits))
        self.assertEqual((outputs[0].status,outputs[0].primary_infimum,outputs[0].secondary_infimum),
                         (outputs[1].status,outputs[1].primary_infimum,outputs[1].secondary_infimum))
        self.assertEqual(outputs[1].status,'infimum_unattained')
        self.assertEqual(outputs[1].unattained_component,'Q')

    def test_empty_and_invalid_parent_metadata(self):
        self.assertEqual(coalesce_pieces(()),())
        with self.assertRaises(ValueError):coalesce_pieces((seed(Interval(0,1)),),family_ids=())
        with self.assertRaises(ValueError):coalesce_pieces((seed(Interval(0,1)),),family_ids=('',))
        with self.assertRaises(TypeError):coalesce_pieces((None,))


if __name__=='__main__':unittest.main()
