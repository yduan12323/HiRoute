"""C09 original 76 kWh path-local old/new PWA parity, not a global solve."""
from fractions import Fraction as Q
import hashlib
import json
from pathlib import Path
import unittest

from hiroute.exact import AffineCutPiece, Interval, drive_piece, schedule_piece, stop_partition
from timecut5.probe import AffineFamily, ChargingCurve, State
from timecut5.pwa import (CutPiece, charge_pwa, combined_pwa, drive_pwa,
                          schedule_pwa)

FIXTURE = Path(__file__).parent / "fixtures/milestone_4r_b2_b21/hand_cases.json"
EXPECTED_SHA = "5e8f4b92bdbefdf5f35104b9430bbc2d0541517e0df41b4ecdb9ca67f85a5744"


def new_piece(p):
    return AffineCutPiece(p.domain, p.slope, p.intercept, p.chi, p.rho, p.pi,
                          (p.state.anchor, p.state.remaining_schedule, p.state.stop_count))


def compare_frontiers(old, new, label):
    points = {p.domain.lo for p in old + new} | {p.domain.hi for p in old + new}
    points |= {(p.domain.lo + p.domain.hi) / 2 for p in old + new
               if p.domain.lo < p.domain.hi}
    checked = 0
    for energy in sorted(points):
        o = [p for p in old if p.domain.contains(energy)]
        n = [p for p in new if p.domain.contains(energy)]
        if not n:
            continue
        if not o:
            raise AssertionError((label, energy, "new frontier has no legacy member"))
        oc, nc = o[0].at(energy), n[0]
        actual = (nc.cut_time_at(energy), nc.attained, nc.rho, nc.prefix,
                  nc.state_key[1:])
        expected = (oc.tau, oc.chi, oc.rho, oc.pi,
                    (oc.state.remaining_schedule, oc.state.stop_count))
        if actual != expected:
            raise AssertionError((label, energy, actual, expected))
        checked += 1
    if checked == 0:
        raise AssertionError((label, "no common feasible samples"))
    return checked


class TestOriginal76C09PathParity(unittest.TestCase):
    def test_site2_site3_site4_frontier_matches_legacy(self):
        raw = FIXTURE.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), EXPECTED_SHA)
        case = json.loads(raw)[0]
        self.assertEqual(case["case_id"], "A15_waiting_erases_prefix_time_advantage")
        self.assertEqual(case["independent_expected"]["Q_total"], "76")
        curve = ChargingCurve(tuple(tuple(Q(x) for x in row)
                                     for row in case["charging_segments"]))
        h = Q(case["overhead_s"])
        nodes = ("4r:node/2", "4r:node/3", "4r:node/4")
        # origin -> node/2: 18,750 m * 0.00016 kWh/m = 3 kWh; 9,300 s.
        s0 = State(nodes[0], 1, 0)
        old = (CutPiece.from_affine(AffineFamily(Interval(7, 7), 0, 9300,
                    True, 0, (), s0)),)
        new = (AffineCutPiece(Interval(7,7), Q(0), Q(9300), True, Q(0), (),
                    (nodes[0],1,0)),)
        for i, (node, next_node, duration, consumption) in enumerate(
                ((nodes[0], nodes[1], 9300, 35),
                 (nodes[1], nodes[2], 9000, 40))):
            old = charge_pwa(old, curve, h, node)
            new = stop_partition(new, "C", node, curve.segments, h)
            c_count = compare_frontiers(old, new, f"C{i+1}@{node}")
            self.assertGreater(c_count, 0)
            if i == 1:
                a, b, d = (Q(case["schedule"][k]) for k in ("a", "b", "D"))
                old = schedule_pwa(old, node, a, b, d, h)
                new = tuple(piece for source in new
                            for piece in schedule_piece(source, node, a, b, d, h))
                scount = compare_frontiers(old, new, "S@node4")
                self.assertGreater(scount, 0)
                break
            old = drive_pwa(old, next_node, duration, consumption, 0)
            new = tuple(x for source in new
                        if (x := drive_piece(source, next_node, duration, consumption, 0)) is not None)
            d_count = compare_frontiers(old, new, "D@node3")
            self.assertGreater(d_count, 0)


if __name__ == "__main__":
    unittest.main()
