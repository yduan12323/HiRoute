"""Conditional exact arithmetic only; no road certificate or pruning enabled."""
from dataclasses import replace
from fractions import Fraction as R
from itertools import combinations, product
import random
import unittest

from timecut5.probe import AffineFamily, Interval, State
from timecut5.pwa import CutPiece
from timecut5.remaining_charge_bound import (remaining_charge_primary_lower_bound,
                                            complete_route_primary_lower_bound)


def piece(domain=Interval(0, 20), slope=1, intercept=100, *, chi=True,
          rho=0, name="a", remaining=0, count=1, anchor="v"):
    return CutPiece.from_affine(AffineFamily(domain, slope, intercept, chi,
        rho, ((name, "C"),)*count, State(anchor, remaining, count)))


DEFAULT = dict(remaining_energy_lower=R(10), remaining_time_lower=R(5),
    terminal_reserve=R(6), min_charge_seconds_per_kwh=R(36),
    start_time=R(100), stop_penalty=R(10))


def bound(pieces, **kwargs):
    return remaining_charge_primary_lower_bound(pieces, **dict(DEFAULT, **kwargs))


def epigraph_lp_minimum(lo, hi, lines):
    """Independent exact two-variable LP vertex enumeration, no hinge rule."""
    constraints = [(R(-1), R(0), -lo), (R(1), R(0), hi)]
    constraints.extend((slope, R(-1), -intercept) for slope, intercept in lines)
    candidates = []
    for (a,b,c), (d,e,f) in combinations(constraints, 2):
        determinant = a*e-d*b
        if not determinant:
            continue
        energy, clock = (c*e-f*b)/determinant, (a*f-d*c)/determinant
        if all(x*energy+y*clock <= z for x,y,z in constraints):
            candidates.append(clock)
    if not candidates:
        raise AssertionError("Bounded epigraph unexpectedly has no vertex")
    return min(candidates)


class TestRemainingChargeBound(unittest.TestCase):
    def test_reserve_and_current_energy_are_jointly_optimized(self):
        # tau=e+100; charge hinge is reserve6+consumption10=16.
        # min clock116 + driving5 - start100 + past penalty10 =31.
        self.assertEqual(bound((piece(),)), 31)
        self.assertEqual(bound((piece(),), terminal_reserve=R(0)), 25)
        self.assertEqual(bound((piece(),), remaining_time_lower=R(0)), 26)

    def test_naive_separate_minima_are_weaker(self):
        result = bound((piece(Interval(0,10), slope=1, intercept=0, count=0),),
            remaining_energy_lower=R(10), remaining_time_lower=R(0),
            terminal_reserve=R(0), min_charge_seconds_per_kwh=R(2),
            start_time=R(0), stop_penalty=R(0))
        self.assertEqual(result, 10)
        self.assertGreater(result, 0)  # min tau + min charge deficit.

    def test_random_exact_intervals_match_independent_lp(self):
        rng = random.Random(20261017)
        for _ in range(180):
            lo, hi = sorted(R(rng.randrange(0,21), rng.randrange(1,6)) for _ in range(2))
            m = R(rng.randrange(-8,9), rng.randrange(1,6))
            b = R(rng.randrange(0,21), rng.randrange(1,6))
            alpha = R(rng.randrange(1,9), rng.randrange(1,6))
            reserve = R(rng.randrange(0,11), rng.randrange(1,6))
            consumption = R(rng.randrange(0,21), rng.randrange(1,6))
            threshold = reserve+consumption
            expected = epigraph_lp_minimum(lo, hi, ((m,b), (m-alpha,b+alpha*threshold)))
            flags = [(True,True)] if lo == hi else product((False,True), repeat=2)
            for left, right in flags:
                for chi in (False,True):
                    p = piece(Interval(lo,hi,left,right), m,b,chi=chi,count=0)
                    actual = bound((p,), remaining_energy_lower=consumption,
                        remaining_time_lower=R(0), terminal_reserve=reserve,
                        min_charge_seconds_per_kwh=alpha, start_time=R(0),stop_penalty=R(0))
                    self.assertEqual(actual, expected)

    def test_singleton_flat_slopes_and_hinge_outside_domain(self):
        for domain, slope, threshold in product((Interval(3,3), Interval(1,2,False,False)),
                                               (R(-2),R(0),R(1),R(2)),
                                               (R(0),R(3,2),R(10))):
            p = piece(domain,slope,0,count=0)
            self.assertEqual(bound((p,), remaining_energy_lower=threshold,
                remaining_time_lower=R(0), terminal_reserve=R(0),
                min_charge_seconds_per_kwh=R(1), start_time=R(0),stop_penalty=R(0)),
                epigraph_lp_minimum(domain.lo,domain.hi,((slope,R(0)),(slope-1,threshold))))

    def test_open_face_is_an_infimum_not_a_claimed_witness(self):
        p = piece(Interval(0,1,False,False),1,0,chi=False,count=0)
        value = bound((p,),remaining_energy_lower=R(0),remaining_time_lower=R(0),
            terminal_reserve=R(0),start_time=R(0),stop_penalty=R(0))
        self.assertEqual(value,0)
        self.assertIs(type(value),R)
        self.assertFalse(value > R(0))  # Equal incumbent must remain eligible.
        with self.assertRaises(ValueError):
            p.at(R(0))

    def test_frontier_union_accepts_different_histories_but_same_state(self):
        first = piece(intercept=120,rho=2,name="z")
        second = piece(intercept=100,rho=3,name="a")
        self.assertEqual(bound(iter((first,second))), min(bound((first,)),bound((second,))))

    def test_scheduled_and_unscheduled_states_share_this_relaxed_bound(self):
        self.assertEqual(bound((piece(remaining=0),)),bound((piece(remaining=1),)))

    def test_charge_service_overlap_invalidates_adding_schedule_bound(self):
        # CS: h1, charge5, service10, final travel1 => actual terminal12.
        p = piece(Interval(0,0),0,0,remaining=1,count=0)
        relaxed = bound((p,),remaining_energy_lower=R(0),remaining_time_lower=R(1),
            terminal_reserve=R(5),min_charge_seconds_per_kwh=R(1),
            start_time=R(0),stop_penalty=R(0))
        actual = max(1+5,1+10)+1
        schedule_bound = R(12)
        self.assertEqual(relaxed,6)  # No future h or D was silently included.
        self.assertLessEqual(relaxed,actual)
        self.assertEqual(max(relaxed,schedule_bound),actual)
        self.assertGreater(relaxed+schedule_bound,actual)

    def test_past_penalty_only_and_start_time_are_explicit(self):
        p = piece(Interval(20,20),0,100,count=2)
        self.assertEqual(bound((p,),start_time=R(50),stop_penalty=R(3)),61)
        self.assertEqual(bound((p,),start_time=R(-50),stop_penalty=R(3)),161)

    def test_no_callback_or_native_certificate_is_constructed(self):
        def forbidden(energy):
            raise AssertionError("Mathematical helper must not realize a witness")
        p = replace(piece(),_point=forbidden)
        self.assertEqual(bound((p,)),31)

    def test_empty_wrong_type_and_cross_state_are_rejected(self):
        with self.assertRaises(ValueError):bound(())
        with self.assertRaises(TypeError):bound((object(),))
        for changed in (piece(anchor="other"),piece(remaining=1),piece(count=2)):
            with self.assertRaisesRegex(ValueError,"cross-state"):
                bound((piece(),changed))

    def test_only_exact_fraction_parameters_are_accepted(self):
        for name in DEFAULT:
            for value in (0,1,False,True,0.0,"0",None):
                with self.subTest(name=name,value=value),self.assertRaises(TypeError):
                    bound((piece(),),**{name:value})

    def test_negative_bounds_reserve_or_penalty_and_nonpositive_alpha_fail(self):
        for name in ("remaining_energy_lower","remaining_time_lower","terminal_reserve","stop_penalty"):
            with self.assertRaises(ValueError):bound((piece(),),**{name:R(-1)})
        for alpha in (R(-1),R(0)):
            with self.assertRaises(ValueError):bound((piece(),),min_charge_seconds_per_kwh=alpha)

    def test_bad_energy_domain_and_affine_types_fail(self):
        with self.assertRaises(ValueError):bound((piece(Interval(-1,2)),))
        with self.assertRaises(ValueError):bound((piece(Interval(0,2,1,True)),))
        with self.assertRaises(TypeError):bound((replace(piece(),domain=object()),))


class TestConditionalCompleteRouteBound(unittest.TestCase):
    def arguments(self, **kwargs):
        return dict(dict(total_stops=2,initial_energy=R(10),origin_energy_lower=R(15),
            origin_time_lower=R(100),terminal_reserve=R(5),min_charge_seconds_per_kwh=R(2),
            stop_overhead=R(3),stop_penalty=R(7)),**kwargs)

    def test_travel_charge_and_each_stop_overhead_penalty_counted_once(self):
        self.assertEqual(complete_route_primary_lower_bound(**self.arguments()),140)
        self.assertEqual(complete_route_primary_lower_bound(**self.arguments(total_stops=0)),120)
        self.assertEqual(complete_route_primary_lower_bound(**self.arguments(initial_energy=R(20))),120)

    def test_equality_inclusive_depth_floor_is_only_a_necessary_condition(self):
        primary_upper = R(150)
        base = complete_route_primary_lower_bound(**self.arguments(total_stops=0))
        last_competitive = (primary_upper-base)//(R(3)+R(7))
        self.assertEqual(last_competitive,3)
        self.assertEqual(complete_route_primary_lower_bound(**self.arguments(total_stops=3)),primary_upper)
        self.assertGreater(complete_route_primary_lower_bound(**self.arguments(total_stops=4)),primary_upper)
        # A proposed upper below the independently verified seed-H bound is
        # inconsistent, not evidence that the seed may be silently discarded.
        seed_stops=4
        self.assertGreater(complete_route_primary_lower_bound(**self.arguments(total_stops=seed_stops)),primary_upper)

    def test_cs_overlap_does_not_remove_overhead_or_add_service_duration(self):
        args = dict(total_stops=1,initial_energy=R(0),origin_energy_lower=R(0),
            origin_time_lower=R(1),terminal_reserve=R(5),min_charge_seconds_per_kwh=R(1),
            stop_overhead=R(1),stop_penalty=R(0))
        self.assertEqual(complete_route_primary_lower_bound(**args),7)
        actual_terminal = max(1+5,1+10)+1
        self.assertLessEqual(complete_route_primary_lower_bound(**args),actual_terminal)

    def test_exact_nonnegative_contract_and_positive_overhead(self):
        for name in self.arguments():
            if name=="total_stops":
                for value in (True,False,R(1),1.0,"1"):
                    with self.assertRaises(TypeError):
                        complete_route_primary_lower_bound(**self.arguments(**{name:value}))
            else:
                for value in (True,False,0,1.0,"1"):
                    with self.assertRaises(TypeError):
                        complete_route_primary_lower_bound(**self.arguments(**{name:value}))
            with self.assertRaises(ValueError):
                complete_route_primary_lower_bound(**self.arguments(**{name:-1 if name=="total_stops" else R(-1)}))
        for name in ("min_charge_seconds_per_kwh","stop_overhead"):
            with self.assertRaises(ValueError):
                complete_route_primary_lower_bound(**self.arguments(**{name:R(0)}))


if __name__ == "__main__":
    unittest.main()
