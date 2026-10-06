"""Independent held-out point-probe checks; not a universal closure proof.

Run from the HiRoute worktree:
  PYTHONPATH=src python experiments/time_cut_v2/independent_review_checks.py

stdlib only; seed 63119. Authored and first run independently outside the
implementation worktree, then copied here for reproducibility. The C oracle enumerates exact closed-domain endpoints, charging
breakpoints, and cell midpoints, retaining endpoint admissibility separately.
The S/CS probes use a noninterval sparse executable input family.
"""
from fractions import Fraction as R
from random import Random

from timecut5.probe import (
    AffineFamily, ChargingCurve, Cut, Interval, State, Witness,
    charge_at, combined_point, dominates, schedule, terminal,
)


def check_charge():
    rng = Random(63119)
    curve = ChargingCurve(((0, 2, 3, 0), (2, 5, 1, 4), (5, 8, 5, -16)))
    state = State("s", 1, 0)
    count = 0
    for case in range(4000):
        ed = R(rng.randrange(1, 33), 4)
        fs = []
        for _ in range(rng.randrange(1, 5)):
            lo = R(rng.randrange(-4, 32), 4)
            hi = R(rng.randrange(int(lo * 4) + 1, 37), 4)
            fs.append(AffineFamily(
                Interval(lo, hi, bool(rng.randrange(2)), bool(rng.randrange(2))),
                R(rng.randrange(-12, 29), 4), R(rng.randrange(-10, 41), 3),
                bool(rng.randrange(2)), R(0), (), state,
            ))
        h = R(rng.randrange(1, 21), 3)
        result = charge_at(fs, ed, curve, h, "s")
        candidates = []
        for family in fs:
            lo, hi = max(family.domain.lo, R(0)), min(family.domain.hi, ed)
            if lo > hi or (lo == hi and (
                    not family.domain.contains(lo) or lo == ed)):
                continue
            points = sorted({lo, hi} | {x for x in (R(2), R(5)) if lo < x < hi})
            for energy in points + [(a + b) / 2 for a, b in zip(points, points[1:])]:
                candidates.append((
                    family.slope * energy + family.intercept + h
                    + curve.at(ed) - curve.at(energy),
                    family.chi and family.domain.contains(energy) and energy < ed,
                ))
        if not candidates:
            assert result is None
            continue
        expected = min(t for t, _ in candidates)
        attained = any(t == expected and att for t, att in candidates)
        assert (result.tau, result.chi) == (expected, attained), (
            case, result, expected, attained)
        for eps in (R(1000), R(1, 10**60)):
            witness = result.approach(eps)
            action = witness.events[-1]
            energy = action.arrival_energy
            assert energy < ed
            assert action.departure_time == (
                action.arrival_time + h + curve.at(ed) - curve.at(energy))
            assert any(
                family.domain.contains(energy) and (
                    action.arrival_time == family.slope * energy + family.intercept
                    if family.chi else
                    family.slope * energy + family.intercept < action.arrival_time
                    <= family.slope * energy + family.intercept + 1
                ) for family in fs
            )
        count += 1
    print("C randomized exact oracle: 4000 unions,", count, "nonempty; all passed")
    return rng, curve, state


def check_scheduled(rng, curve, state):
    count = 0
    for case in range(4000):
        tau = R(rng.randrange(-20, 81), 3)
        chi = bool(rng.randrange(2))
        energy = R(rng.randrange(0, 24), 3)
        ed = energy + R(rng.randrange(1, int((8 - energy) * 3) + 1), 3)

        # Sparse executable family {tau + 2^-n}, n >= 0; or attained tau.
        def approach(eps, tau=tau, chi=chi, energy=energy):
            gap = R(1)
            while gap >= eps:
                gap /= 2
            return Witness(tau if chi else tau + gap, energy, R(0), (), state)

        cut = Cut(tau, chi, energy, R(0), (), state, approach)
        a = R(rng.randrange(0, 91), 3)
        b = a + R(rng.randrange(-2, 31), 3)
        h = R(rng.randrange(1, 16), 3)
        d = R(rng.randrange(0, 31), 3)
        for is_cs in (False, True):
            result = (combined_point(cut, ed, curve, "s", a, b, d, h)
                      if is_cs else schedule(cut, "s", a, b, d, h))
            feasible = a <= b and (tau < b - h or (tau == b - h and chi))
            assert (result is not None) == feasible
            if result is None:
                continue
            charge = curve.at(ed) - curve.at(energy) if is_cs else R(0)
            expected = max(tau + h + charge, max(a, tau + h) + d)
            plateau_right = a + d - h - max(charge, d)
            assert (result.tau, result.chi) == (expected, chi or tau < plateau_right)
            for eps in (R(1000), R(1, 10**60)):
                witness = result.approach(eps)
                action = witness.events[-1]
                assert max(a, action.arrival_time + h) <= b
                assert action.departure_time == max(
                    action.arrival_time + h + charge,
                    max(a, action.arrival_time + h) + d,
                )
                assert (action.arrival_time == tau if chi else action.arrival_time > tau)
            count += 1
    print("S/CS sparse-family boundary checks: 8000 actions,", count, "feasible; all passed")


def family(lo=0, hi=1, lc=True, rc=True, slope=0, t=10, chi=True,
           rho=0, pi=(), anchor="z", remaining=0):
    return AffineFamily(Interval(lo, hi, lc, rc), slope, t, chi, rho,
                        pi, State(anchor, remaining, len(pi)))


def check_terminal():
    cases = [
        ("primary tied open plus closed", (family(chi=False, rho=-5), family(rho=2)),
         (10, 2, 0, ())),
        ("secondary open beats worse attained", (family(lc=False), family(lo=1, hi=1)),
         None),
        ("secondary tied singleton restores attainment", (family(lc=False), family(lo=0, hi=0)),
         (10, 0, 0, ())),
        ("H tie breaks after J Q", (family(pi=(("1", "C"),)), family()),
         (10, 0, 0, ())),
        ("Q beats H", (family(rho=1), family(pi=(("9", "C"),))),
         (10, 0, 1, (("9", "C"),))),
        ("open right reserve singleton is infeasible", (family(rc=False),), None),
    ]
    for name, families, expected in cases:
        result = terminal(families, "z", 1 if name.startswith("open right") else 0)
        assert result.key == expected, (name, result)
        if name.startswith("secondary open"):
            assert (result.status, result.unattained_component) == ("infimum_unattained", "Q")
        if name.startswith("open right"):
            assert result.status == "infeasible"
        print("PASS", name)


def check_dominance():
    checks = 0
    for ta in range(3):
        for tb in range(3):
            for ca in (False, True):
                for cb in (False, True):
                    for ra in (R(-1), R(0), R(1)):
                        for rb in (R(-1), R(0), R(1)):
                            a = family(lo=1, hi=1, t=ta, chi=ca, rho=ra,
                                       pi=(("1", "C"),), anchor="s", remaining=1).at(1)
                            b = family(lo=1, hi=1, t=tb, chi=cb, rho=rb,
                                       pi=(("2", "C"),), anchor="s", remaining=1).at(1)
                            if not dominates(a, b):
                                continue
                            for eps in (R(10), R(1, 10**60)):
                                wb = b.approach(eps)
                                wa = a.realize_le(wb.time)
                                assert wa.time <= wb.time and wa.charge <= wb.charge
                                assert (wa.time, wa.charge, len(wa.pi), wa.pi) <= (
                                    wb.time, wb.charge, len(wb.pi), wb.pi)
                                checks += 1
    print("PASS", checks, "constructive dominated-witness replay checks")


if __name__ == "__main__":
    check_scheduled(*check_charge())
    check_terminal()
    check_dominance()
