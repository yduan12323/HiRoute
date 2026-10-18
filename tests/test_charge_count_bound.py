"""Pure rational synthetic checks; no routing, runtime admission or pruning."""
from dataclasses import FrozenInstanceError, replace
from fractions import Fraction as R
from itertools import combinations, product
import random
import unittest

from timecut5.charge_count_bound import (ChargeCountBoundResultV1,
    SharedConvexCurveAdmissionV1, admit_shared_convex_curve,
    charge_count_primary_lower_bound)
from timecut5.probe import AffineFamily, ChargingCurve, Interval, State
from timecut5.pwa import CutPiece
from timecut5.remaining_charge_bound import remaining_charge_primary_lower_bound


FROZEN = ChargingCurve(((0, 30, 36, 0), (30, 48, 60, -720), (48, 60, 120, -3600)))
TINY = ChargingCurve(((0, 1, 1, 0), (1, 2, 3, -2)))
LINEAR = ChargingCurve(((0, 2, 1, 0),))
ADMISSION = admit_shared_convex_curve(FROZEN, minimum_energy=R(0), capacity=R(60))
DEFAULT = dict(admission=ADMISSION, remaining_energy_lower=R(60),
    remaining_time_lower=R(0), terminal_reserve=R(0), start_time=R(0),
    stop_overhead=R(300), stop_penalty=R(600), original_hmax=3)


def piece(domain=Interval(0, 0), slope=0, intercept=0, *, count=0,
          remaining=0, anchor="v", chi=True, rho=0, name="a"):
    return CutPiece.from_affine(AffineFamily(domain, slope, intercept, chi,
        rho, ((name, "C"),) * count, State(anchor, remaining, count)))


def bound(pieces=None, **changes):
    return charge_count_primary_lower_bound((piece(),) if pieces is None else pieces,
                                           **dict(DEFAULT, **changes))


def lp_infimum(lo, hi, lines):
    """Independent rational epigraph LP vertex enumeration, no F breakpoints."""
    constraints = [(R(-1), R(0), -lo), (R(1), R(0), hi)]
    constraints.extend((m, R(-1), -b) for m, b in lines)
    values = []
    for (a, b, c), (d, e, f) in combinations(constraints, 2):
        determinant = a * e - d * b
        if determinant:
            energy = (c * e - f * b) / determinant
            clock = (a * f - d * c) / determinant
            if all(x * energy + y * clock <= z for x, y, z in constraints):
                values.append(clock)
    if not values:
        raise AssertionError("Nonempty bounded epigraph should have a vertex")
    return min(values)


def independent_oracle(p, curve, floor, capacity, energy, travel, reserve,
                       start, overhead, penalty, hmax, minimum):
    """Support-line epigraph for each h, independent of the production minimizer."""
    threshold = reserve + energy
    values = []
    for h in range(max(p.state.remaining_schedule, minimum), hmax - p.state.stop_count + 1):
        lo, hi = max(p.domain.lo, threshold - h * (capacity - floor)), p.domain.hi
        if lo > hi or lo == hi and not p.domain.contains(lo):
            continue
        lines = [(p.slope, p.intercept + h * (overhead + penalty))]
        if h:
            for left, right, m, b in curve.segments:
                if left < capacity and right > floor:
                    lines.append((p.slope - m, p.intercept + m * threshold +
                        h * (m * floor + b - curve.at(floor) + overhead + penalty)))
        values.append(lp_infimum(lo, hi, lines))
    return (None if not values else min(values) + travel - start +
            p.state.stop_count * penalty)


class TestSharedConvexCurveAdmission(unittest.TestCase):
    def test_explicit_active_immutable_exact_snapshot(self):
        self.assertEqual(ADMISSION.status, "active")
        self.assertEqual(ADMISSION.segments, FROZEN.segments)
        with self.assertRaises(FrozenInstanceError):
            ADMISSION.capacity = R(1)

    def test_nonconvex_curve_is_unsupported_not_infeasible(self):
        curve = ChargingCurve(((0, 1, 10, 0), (1, 2, 1, 9)))
        admission = admit_shared_convex_curve(curve, minimum_energy=R(0), capacity=R(2))
        self.assertEqual(admission.status, "unsupported")
        self.assertEqual(admission.reason, "nonconvex_charging_curve")
        self.assertIsNone(admission.segments)
        self.assertEqual(curve.at(R(2)) - curve.at(R(1)), 1)
        self.assertEqual(curve.at(R(1)) - curve.at(R(0)), 10)
        result = bound(admission=admission, remaining_energy_lower=R(1))
        self.assertEqual(result.status, "unsupported")
        self.assertIsNone(result.primary_lower_bound)

    def test_convexity_only_on_usable_interval_is_sufficient(self):
        curve = ChargingCurve(((0, 1, 10, 0), (1, 2, 1, 9)))
        admission = admit_shared_convex_curve(curve, minimum_energy=R(1), capacity=R(2))
        self.assertEqual(admission.status, "active")

    def test_missing_curve_is_explicitly_unsupported(self):
        admission = admit_shared_convex_curve(None, minimum_energy=R(0), capacity=R(60))
        result = bound(admission=admission)
        self.assertEqual(result.status, "unsupported")
        self.assertEqual(result.reason, "no_charging_curve")
        self.assertIsNone(result.primary_lower_bound)
        self.assertEqual(result.original_hmax, 3)

    def test_exact_physical_admission_parameters(self):
        for name in ("minimum_energy", "capacity"):
            for value in (0, True, False, 1.0, "1", None):
                kwargs = dict(minimum_energy=R(0), capacity=R(60))
                kwargs[name] = value
                with self.subTest(name=name, value=value), self.assertRaises(TypeError):
                    admit_shared_convex_curve(FROZEN, **kwargs)
        for floor, capacity in ((R(-1), R(60)), (R(0), R(0)),
                                (R(61), R(60)), (R(0), R(61))):
            with self.assertRaises(ValueError):
                admit_shared_convex_curve(FROZEN, minimum_energy=floor, capacity=capacity)
        with self.assertRaises(TypeError):
            admit_shared_convex_curve(object(), minimum_energy=R(0), capacity=R(60))

    def test_forged_active_admission_revalidates_convexity_and_exact_rows(self):
        rows = ChargingCurve(((0, 1, 10, 0), (1, 2, 1, 9))).segments
        with self.assertRaises(ValueError):
            SharedConvexCurveAdmissionV1("active", R(0), R(2), rows)
        with self.assertRaises(TypeError):
            SharedConvexCurveAdmissionV1("active", R(0), R(2), ((0, 2, 1, 0),))
        with self.assertRaises(TypeError):
            SharedConvexCurveAdmissionV1("active", R(0), R(2), list(LINEAR.segments))

    def test_malformed_snapshots_are_errors_not_unsupported_physics(self):
        cases = [((R(0), R(2), R(-1), R(0)),),
                 ((R(1), R(2), R(1), R(0)),),
                 ((R(0), R(1), R(1), R(0)), (R(1), R(2), R(1), R(1))),
                 ((R(0), R(1), R(1), R(0)), (R(3, 2), R(2), R(1), R(0)))]
        for rows in cases:
            with self.assertRaises(ValueError):
                SharedConvexCurveAdmissionV1("active", R(0), R(2), rows)


class TestChargeCountBound(unittest.TestCase):
    def test_all_counts_are_enumerated_nonmonotone_in_h(self):
        # q=60: h1/2/3 cost 4500/3960/4860. Neither count endpoint is safe.
        result = bound()
        self.assertEqual(result.status, "active")
        self.assertEqual(result.primary_lower_bound, 3960)
        self.assertEqual(result.original_hmax, 3)
        self.assertEqual(bound(original_hmax=1).primary_lower_bound, 4500)
        self.assertEqual(bound(original_hmax=2).primary_lower_bound, 3960)
        self.assertEqual(bound(minimum_future_stops=3).primary_lower_bound, 4860)

    def test_zero_future_stops_only_when_no_charge_is_required(self):
        zero = bound(remaining_energy_lower=R(0), original_hmax=0)
        self.assertEqual(zero.status, "active")
        self.assertEqual(zero.primary_lower_bound, 0)
        deficit = bound(remaining_energy_lower=R(1), original_hmax=0)
        self.assertEqual(deficit.status, "infeasible")
        self.assertEqual(deficit.reason, "no_feasible_future_count")
        self.assertIsNone(deficit.primary_lower_bound)

    def test_pending_service_requires_one_paid_relaxed_stop(self):
        result = bound((piece(remaining=1),), remaining_energy_lower=R(0))
        self.assertEqual(result.primary_lower_bound, 900)
        result = bound((piece(remaining=1),), remaining_energy_lower=R(0), original_hmax=0)
        self.assertEqual(result.status, "infeasible")
        self.assertEqual(result.reason, "no_legal_future_count")

    def test_caller_justified_next_stop_condition_is_explicit(self):
        self.assertEqual(bound(remaining_energy_lower=R(0)).primary_lower_bound, 0)
        self.assertEqual(bound(remaining_energy_lower=R(0), minimum_future_stops=1).primary_lower_bound, 900)
        result = bound(original_hmax=2, minimum_future_stops=3)
        self.assertEqual(result.status, "infeasible")
        self.assertEqual(result.reason, "no_legal_future_count")

    def test_original_hmax_counts_completed_stops_and_is_not_rewritten(self):
        p = piece(count=2)
        result = bound((p,), original_hmax=3)
        self.assertEqual(result.primary_lower_bound, 4500 + 1200)
        self.assertEqual(result.original_hmax, 3)
        self.assertEqual(bound((p,), original_hmax=2).status, "infeasible")
        with self.assertRaises(ValueError):
            bound((p,), original_hmax=1)

    def test_capacity_equality_is_kept_and_just_above_is_infeasible(self):
        self.assertEqual(bound(original_hmax=1).status, "active")
        result = bound(original_hmax=1, remaining_energy_lower=R(60001, 1000))
        self.assertEqual(result.status, "infeasible")
        self.assertEqual(result.reason, "no_feasible_future_count")

    def test_clipped_open_singleton_is_empty_before_closure_infimum(self):
        p = piece(Interval(0, 60, True, False))
        result = bound((p,), original_hmax=1, remaining_energy_lower=R(120))
        self.assertEqual(result.status, "infeasible")
        closed = piece(Interval(0, 60, True, True))
        self.assertEqual(bound((closed,), original_hmax=1,
            remaining_energy_lower=R(120)).primary_lower_bound, 4500)

    def test_h0_clipped_open_singleton_does_not_create_zero_charge_branch(self):
        p = piece(Interval(0, 60, True, False))
        self.assertEqual(bound((p,), original_hmax=0).status, "infeasible")
        self.assertEqual(bound((piece(Interval(0, 60)),), original_hmax=0).primary_lower_bound, 0)

    def test_open_energy_and_clock_faces_return_only_an_infimum(self):
        p = piece(Interval(0, 60, False, False), slope=1, chi=False)
        result = bound((p,), original_hmax=0, remaining_energy_lower=R(0))
        self.assertEqual(result.primary_lower_bound, 0)
        self.assertIs(type(result.primary_lower_bound), R)
        self.assertFalse(result.primary_lower_bound > R(0))  # Equality stays eligible.
        with self.assertRaises(ValueError):
            p.at(R(0))

    def test_interior_transformed_curve_breakpoint_is_not_missed(self):
        p = piece(Interval(0, 60), slope=50)
        result = bound((p,), original_hmax=1, minimum_future_stops=1)
        self.assertEqual(result.primary_lower_bound, 3480)  # e=30, q=30.
        endpoint_values = [R(4500), R(3900)]
        self.assertLess(result.primary_lower_bound, min(endpoint_values))

    def test_nonzero_floor_inside_segment_and_capacity_degenerate_interval(self):
        admission = admit_shared_convex_curve(TINY, minimum_energy=R(1, 2), capacity=R(2))
        result = bound((piece(Interval(R(1, 2), R(1, 2))),), admission=admission,
            remaining_energy_lower=R(1), terminal_reserve=R(1, 2),
            original_hmax=1, stop_overhead=R(1), stop_penalty=R(0))
        self.assertEqual(result.primary_lower_bound, 3)  # F(1.5)-F(.5)+overhead.
        degenerate = admit_shared_convex_curve(TINY, minimum_energy=R(2), capacity=R(2))
        p = piece(Interval(2, 2))
        no_charge = bound((p,), admission=degenerate, remaining_energy_lower=R(0),
            terminal_reserve=R(2), minimum_future_stops=1)
        self.assertEqual(no_charge.primary_lower_bound, 900)
        self.assertEqual(bound((p,), admission=degenerate, remaining_energy_lower=R(1),
            terminal_reserve=R(2)).status, "infeasible")

    def test_past_costs_and_start_offset_counted_once(self):
        p = piece(Interval(20, 20), intercept=100, count=2)
        result = bound((p,), remaining_energy_lower=R(0), terminal_reserve=R(6),
            remaining_time_lower=R(5), start_time=R(50), stop_overhead=R(3),
            stop_penalty=R(7), original_hmax=2)
        self.assertEqual(result.primary_lower_bound, 69)

    def test_frontier_union_and_different_histories_preserve_same_state(self):
        first = piece(intercept=20, rho=3, name="z", count=1)
        second = piece(intercept=10, rho=2, name="a", count=1)
        actual = bound(iter((first, second))).primary_lower_bound
        self.assertEqual(actual, min(bound((first,)).primary_lower_bound,
                                     bound((second,)).primary_lower_bound))

    def test_no_callback_is_called_and_no_witness_is_returned(self):
        def forbidden(energy):
            raise AssertionError("Pure bound must never realize a witness")
        p = replace(piece(chi=False), _point=forbidden)
        result = bound((p,))
        self.assertEqual(result.primary_lower_bound, 3960)
        self.assertFalse(hasattr(result, "witness"))
        self.assertFalse(hasattr(result, "attained"))

    def test_charge_service_overlap_uses_max_of_complete_bounds(self):
        curve = ChargingCurve(((0, 20, 1, 0),))
        admission = admit_shared_convex_curve(curve, minimum_energy=R(0), capacity=R(20))
        result = bound((piece(remaining=1),), admission=admission,
            remaining_energy_lower=R(5), remaining_time_lower=R(1),
            stop_overhead=R(1), stop_penalty=R(0), original_hmax=1)
        actual = max(5, 10) + 1 + 1
        self.assertEqual(result.primary_lower_bound, 7)
        self.assertEqual(max(result.primary_lower_bound, R(12)), actual)
        self.assertGreater(result.primary_lower_bound + R(12), actual)

    def test_exact_random_intervals_match_independent_epigraph_oracle(self):
        rng = random.Random(20261017)
        for curve, floor, capacity in ((FROZEN, R(0), R(60)),
                                       (TINY, R(1, 2), R(2)), (LINEAR, R(0), R(2))):
            admission = admit_shared_convex_curve(curve, minimum_energy=floor, capacity=capacity)
            width = capacity - floor
            for case in range(100):
                lo, hi = sorted(floor + width * R(rng.randrange(9), 8) for _ in range(2))
                lc, rc = (True, True) if lo == hi else (bool(rng.randrange(2)), bool(rng.randrange(2)))
                count, remaining = rng.randrange(3), rng.randrange(2)
                hmax, minimum = count + rng.randrange(5), rng.randrange(3)
                energy, travel = width * R(rng.randrange(25), 8), R(rng.randrange(5), 3)
                reserve = floor + width * R(rng.randrange(9), 8)
                overhead, penalty, start = R(rng.randrange(1, 5), 3), R(rng.randrange(5), 3), R(-2, 3)
                p = piece(Interval(lo, hi, lc, rc), R(rng.randrange(-6, 130), 3),
                          R(rng.randrange(-5, 6), 2), count=count, remaining=remaining,
                          chi=bool(rng.randrange(2)))
                expected = independent_oracle(p, curve, floor, capacity, energy, travel,
                    reserve, start, overhead, penalty, hmax, minimum)
                result = bound((p,), admission=admission, remaining_energy_lower=energy,
                    remaining_time_lower=travel, terminal_reserve=reserve, start_time=start,
                    stop_overhead=overhead, stop_penalty=penalty, original_hmax=hmax,
                    minimum_future_stops=minimum)
                with self.subTest(curve=curve, case=case):
                    self.assertEqual(result.primary_lower_bound, expected)
                    self.assertEqual(result.status, "infeasible" if expected is None else "active")
                    if expected is not None:
                        linear = remaining_charge_primary_lower_bound((p,),
                            remaining_energy_lower=energy, remaining_time_lower=travel,
                            terminal_reserve=reserve, start_time=start, stop_penalty=penalty,
                            min_charge_seconds_per_kwh=min(row[2] for row in curve.segments))
                        self.assertGreaterEqual(result.primary_lower_bound, linear)

    def test_relaxation_bounds_enumerated_charge_allocations(self):
        admission = admit_shared_convex_curve(TINY, minimum_energy=R(0), capacity=R(2))
        for h in range(1, 4):
            for amounts in product((R(0), R(1, 2), R(1), R(3, 2), R(2)), repeat=h):
                actual = sum((TINY.at(x) + R(1) for x in amounts), R(0))
                result = bound(admission=admission, remaining_energy_lower=sum(amounts, R(0)),
                    stop_overhead=R(1), stop_penalty=R(0), original_hmax=h)
                self.assertEqual(result.status, "active")
                self.assertLessEqual(result.primary_lower_bound, actual)

    def test_systematic_fixed_count_infima_match_independent_lp(self):
        # Mirrors the separate pure-rational study's 5,400 interval/count cases.
        checked = 0
        for curve, floor, capacity in ((FROZEN, R(0), R(60)),
                (FROZEN, R(10), R(60)), (TINY, R(1, 2), R(2)),
                (LINEAR, R(0), R(2))):
            admission = admit_shared_convex_curve(curve, minimum_energy=floor, capacity=capacity)
            width = capacity - floor
            intervals = [Interval(floor, capacity, lc, rc)
                         for lc, rc in product((False, True), repeat=2)]
            middle = floor + width / 2
            intervals.extend((Interval(middle, middle), Interval(floor, middle, True, False)))
            for threshold, slope, h, domain in product(
                    (floor, middle, capacity, capacity + width, capacity + 2 * width),
                    map(R, (-2, 0, 1, 2, 36, 50, 60, 120, 121)), range(5), intervals):
                p = piece(domain, slope, R(7), chi=False)
                expected = independent_oracle(p, curve, floor, capacity,
                    threshold - floor, R(0), floor, R(0), R(9), R(0), h, h)
                result = bound((p,), admission=admission,
                    remaining_energy_lower=threshold - floor, remaining_time_lower=R(0),
                    terminal_reserve=floor, start_time=R(0), stop_overhead=R(9),
                    stop_penalty=R(0), original_hmax=h, minimum_future_stops=h)
                with self.subTest(floor=floor, capacity=capacity, threshold=threshold,
                                  slope=slope, h=h, domain=domain):
                    self.assertEqual(result.primary_lower_bound, expected)
                    self.assertEqual(result.status, "infeasible" if expected is None else "active")
                checked += 1
        self.assertEqual(checked, 5400)

    def test_exact_parameters_and_integer_count_contract(self):
        for name in ("remaining_energy_lower", "remaining_time_lower", "terminal_reserve",
                     "start_time", "stop_overhead", "stop_penalty"):
            for value in (0, 1, False, True, 0.0, "0", None):
                with self.subTest(name=name, value=value), self.assertRaises(TypeError):
                    bound(**{name: value})
        for name in ("original_hmax", "minimum_future_stops"):
            for value in (True, False, R(1), 1.0, "1", None):
                with self.subTest(name=name, value=value), self.assertRaises(TypeError):
                    bound(**{name: value})
            with self.assertRaises(ValueError):
                bound(**{name: -1})
        for name in ("remaining_energy_lower", "remaining_time_lower", "terminal_reserve", "stop_penalty"):
            with self.assertRaises(ValueError):
                bound(**{name: R(-1)})
        for overhead in (R(-1), R(0)):
            with self.assertRaises(ValueError):
                bound(stop_overhead=overhead)
        with self.assertRaises(ValueError):
            bound(terminal_reserve=R(61))

    def test_empty_nonphysical_cross_state_or_out_of_domain_frontier_is_rejected(self):
        with self.assertRaises(ValueError):
            bound(())
        with self.assertRaises(TypeError):
            bound((object(),))
        for changed in (piece(anchor="other"), piece(remaining=1), piece(count=1)):
            with self.assertRaisesRegex(ValueError, "cross-state"):
                bound((piece(), changed))
        for domain in (Interval(-1, 2), Interval(0, 61), Interval(0, 2, 1, True)):
            with self.assertRaises(ValueError):
                bound((piece(domain),))
        with self.assertRaises(TypeError):
            bound((replace(piece(), domain=object()),))
        with self.assertRaises(TypeError):
            bound(admission=FROZEN)

    def test_result_statuses_reject_ambiguous_none_or_numeric_infeasibility(self):
        for status in ("unsupported", "infeasible"):
            with self.assertRaises(ValueError):
                ChargeCountBoundResultV1(status, R(1), 3)
        with self.assertRaises(TypeError):
            ChargeCountBoundResultV1("active", None, 3)
        with self.assertRaises(ValueError):
            ChargeCountBoundResultV1("unknown", None, 3)


if __name__ == "__main__":
    unittest.main()
