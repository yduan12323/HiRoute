from fractions import Fraction as Q
import unittest

from hiroute.exact import (DriveStep, StopStep, Interval, initial_piece,
                            execute_exact_plan, terminal_optimize, replay_terminal)
from hiroute.exact.pipeline import replay_chain
from timecut5.probe import (AffineFamily, FROZEN_CURVE, Interval as OldInterval,
                            State, terminal)
from timecut5.pwa import (CutPiece, drive_pwa, charge_pwa, combined_pwa,
                          schedule_pwa)


def old_families(pieces):
    return tuple(AffineFamily(OldInterval(p.domain.lo,p.domain.hi,
        p.domain.left_closed,p.domain.right_closed),p.slope,p.intercept,p.chi,
        p.rho,p.pi,p.state) for p in pieces)


class TestExactPipeline(unittest.TestCase):
    def assert_case(self, start_energy, sequence_kind):
        domain=Interval(Q(start_energy),Q(start_energy+2))
        exact_seed=initial_piece(domain,0,"origin",1,rho=-Q(start_energy))
        old_seed=CutPiece.from_affine(AffineFamily(
            OldInterval(domain.lo,domain.hi),Q(0),Q(0),True,-Q(start_energy),(),State("origin",1,0)))
        curve=FROZEN_CURVE.segments
        if sequence_kind=="cs":
            steps=(DriveStep("c",2,1),StopStep("C","c",300,curve),
                   DriveStep("d",3,1),StopStep("CS","d",300,curve,0,5000,4))
            old=drive_pwa((old_seed,),"c",2,1)
            old=charge_pwa(old,FROZEN_CURVE,300,"c")
            old=drive_pwa(old,"d",3,1)
            old=combined_pwa(old,FROZEN_CURVE,"d",0,5000,4,300)
            dest="d"; reserve=Q(25)
        else:
            steps=(DriveStep("d",2,1),StopStep("S","d",300,(),0,5000,4))
            old=drive_pwa((old_seed,),"d",2,1)
            old=schedule_pwa(old,"d",0,5000,4,300)
            dest="d"; reserve=Q(9)
        new=execute_exact_plan((exact_seed,),steps)
        self.assertTrue(new)
        # Compare a common exact arrangement: every endpoint and every affine
        # crossing between old/new expressions, checking singleton boundaries
        # and each intervening open cell. This compares whole cell expressions,
        # not merely sampled cut values.
        all_pieces=tuple(old)+tuple(new)
        knots={x for p in all_pieces for x in (p.domain.lo,p.domain.hi)}
        for i,p in enumerate(all_pieces):
            for q in all_pieces[i+1:]:
                overlap=p.domain.intersect(q.domain)
                if overlap is None or p.slope==q.slope: continue
                x=(q.intercept-p.intercept)/(p.slope-q.slope)
                if overlap.lo <= x <= overlap.hi: knots.add(x)
        knots=sorted(knots)
        cells=[(x,x) for x in knots]
        cells.extend((a,b) for a,b in zip(knots,knots[1:]) if a<b)
        def semantic_piece(piece, x, singleton):
            if hasattr(piece,"state_key"):
                state,attained,prefix=piece.state_key,piece.attained,piece.prefix
            else:
                state=(piece.state.anchor,piece.state.remaining_schedule,piece.state.stop_count)
                attained,prefix=piece.chi,piece.pi
            value=piece.slope*x+piece.intercept
            return ((value,attained,piece.rho,prefix,state) if singleton else
                    (piece.slope,piece.intercept,attained,piece.rho,prefix,state))
        for lo,hi in cells:
            singleton=lo==hi
            e=lo if singleton else (lo+hi)/2
            old_at=[p for p in old if p.domain.contains(e)]
            new_at=[p for p in new if p.domain.contains(e)]
            self.assertEqual(bool(old_at),bool(new_at),(sequence_kind,lo,hi))
            self.assertEqual(sorted(semantic_piece(p,e,singleton) for p in new_at),
                             sorted(semantic_piece(p,e,singleton) for p in old_at),
                             (sequence_kind,lo,hi))
            # Check the inherited witness callback over every singleton and
            # open-cell representative as well as the PWA expressions.
            if new_at and new_at[0].attained:
                exact_chain=replay_chain(new_at[0].witness_lifter(
                    e,new_at[0].cut_time_at(e)))
                old_witness=old_at[0].at(e).minimum()
                old_actions=tuple((event.site,event.effect) for event in old_witness.events
                                  if event.effect in {"S","C","CS"})
                self.assertEqual((exact_chain[0],exact_chain[1],exact_chain[2],exact_chain[3]),
                                 (old_witness.energy,old_witness.time,old_actions,old_witness.rho),
                                 ("witness",sequence_kind,lo,hi))
        # Execute the same itinerary in two calls. The second call inherits
        # the first family's callback and must preserve the complete witness chain.
        if sequence_kind=="cs":
            split=execute_exact_plan((exact_seed,),steps[:2])
            split=execute_exact_plan(split,steps[2:])
            probes={x for piece in (*new,*split) for x in (piece.domain.lo,piece.domain.hi)}
            probes.update((lo+hi)/2 for lo,hi in cells if lo<hi)
            for e in sorted(probes):
                left=[p for p in new if p.domain.contains(e)]
                right=[p for p in split if p.domain.contains(e)]
                self.assertEqual(bool(left),bool(right),("split",e))
                if left:
                    self.assertEqual((left[0].cut_time_at(e),left[0].attained,left[0].rho,
                                      left[0].prefix,left[0].state_key),
                                     (right[0].cut_time_at(e),right[0].attained,right[0].rho,
                                      right[0].prefix,right[0].state_key))
        new_result=terminal_optimize(new,dest,reserve)
        old_result=terminal(old_families(old),dest,reserve)
        expected_status={"infeasible":"infeasible","primary_unattained":"infimum_unattained",
                         "secondary_unattained":"infimum_unattained","attained_optimum":"attained_optimum"}
        self.assertEqual(new_result.status,expected_status[old_result.status])
        if old_result.status!="attained_optimum":
            self.assertEqual(new_result.primary_infimum,old_result.primary_infimum)
            return
        self.assertEqual(new_result.key,old_result.key)
        replay=replay_terminal(new_result,dest,reserve)
        self.assertEqual(replay["key"],old_result.key)
        # Replay correspondence: reconstruct the old PWA predecessor witness
        # at the old solver's selected terminal energy. This is not an
        # independent third optimizer/oracle.
        e=old_result.witness.energy
        candidates=[p for p in old if p.domain.contains(e) and
                    p.state==old_result.witness.state and p.pi==old_result.witness.pi]
        self.assertTrue(candidates)
        physical=candidates[0].at(e).minimum()
        self.assertEqual((physical.energy,physical.time,physical.rho,physical.pi),
                         (replay["energy"],replay["time"],replay["rho"],
                          new_result.witness.prefix))
        legacy_trace=tuple((x.effect,x.site,x.arrival_energy,x.arrival_time,
                            x.departure_energy,x.departure_time)
                           for x in physical.events if x.effect!="analytic_seed")
        self.assertEqual(legacy_trace,replay["trace"])

    def test_d_c_d_cs_generated_rational_cases_old_new_and_replay(self):
        for i in range(5):
            with self.subTest(seed=i): self.assert_case(10+i,"cs")

    def test_open_primary_and_secondary_faces_keep_old_new_approach_witnesses(self):
        source = Interval(Q(0), Q(1), False, True)
        epsilon = Q(1, 1000)
        seed = initial_piece(source, 0, "z", 0, rho=0)
        old_seed = CutPiece.from_affine(AffineFamily(OldInterval(Q(0), Q(1), False, True), Q(0), Q(0), True, 0, (), State("z", 0, 0)))
        curve = FROZEN_CURVE.__class__(((Q(0), Q(2), Q(1), Q(0)),))
        steps = (StopStep("C", "z", 1, curve.segments),)
        new = execute_exact_plan((seed,), steps)
        old = charge_pwa((old_seed,), curve, 1, "z")
        new_result = terminal_optimize(new, "z", Q(0))
        old_result = terminal(old_families(old), "z", Q(0))
        self.assertEqual((new_result.status, new_result.primary_infimum), ("primary_unattained", old_result.primary_infimum))
        self.assertEqual(old_result.status, "infimum_unattained")
        energy = Q(1, 2)
        np = next(p for p in new if p.domain.contains(energy))
        op = next(p for p in old if p.domain.contains(energy))
        nt = replay_chain(np.witness_lifter(energy, np.cut_time_at(energy) + epsilon / 2))
        ow = op.at(energy).approach(epsilon)
        oa = tuple((e.site, e.effect) for e in ow.events if e.effect in {"S", "C", "CS"})
        self.assertEqual((nt[0], nt[2], nt[3]), (ow.energy, oa, ow.rho))
        self.assertEqual(nt[2], (("z", "C"),))
        self.assertGreaterEqual(nt[1], Q(1))
        self.assertLess(nt[1], Q(1) + epsilon)
        self.assertGreaterEqual(ow.time, Q(1))
        self.assertLess(ow.time, Q(1) + epsilon)

        seed2 = initial_piece(source, 0, "z", 1, rho=0)
        old_seed2 = CutPiece.from_affine(AffineFamily(OldInterval(Q(0), Q(1), False, True), Q(0), Q(0), True, 0, (), State("z", 1, 0)))
        steps2 = (StopStep("S", "z", 1, (), 5, 10, 0),)
        new2 = execute_exact_plan((seed2,), steps2)
        old2 = schedule_pwa((old_seed2,), "z", 5, 10, 0, 1)
        nr = terminal_optimize(new2, "z", Q(0))
        orr = terminal(old_families(old2), "z", Q(0))
        self.assertEqual((nr.status, nr.primary_infimum), ("secondary_unattained", orr.primary_infimum))
        self.assertEqual(orr.status, "infimum_unattained")
        self.assertEqual(nr.primary_infimum, Q(5))
        energy2 = Q(1, 2)
        np2 = next(p for p in new2 if p.domain.contains(energy2))
        op2 = next(p for p in old2 if p.domain.contains(energy2))
        nt2 = replay_chain(np2.witness_lifter(energy2, np2.cut_time_at(energy2)))
        ow2 = op2.at(energy2).minimum()
        oa2 = tuple((e.site, e.effect) for e in ow2.events if e.effect in {"S", "C", "CS"})
        self.assertEqual((nt2[0], nt2[1], nt2[2], nt2[3]), (ow2.energy, ow2.time, oa2, ow2.rho))
        self.assertEqual(nt2[2], (("z", "S"),))
        self.assertEqual(nt2[1], Q(5))

    def test_d_s_generated_rational_cases_old_new_and_replay(self):
        for i in range(5):
            with self.subTest(seed=i): self.assert_case(10+i,"s")

if __name__=="__main__": unittest.main()
