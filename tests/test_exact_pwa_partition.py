from fractions import Fraction as Q
from dataclasses import fields, is_dataclass
import json
import unittest

from hiroute.exact import (AffineCutPiece, Interval, stop_partition,
                           family_union, restrict_family, TransitionWitness)
from hiroute.exact.pipeline import InitialWitness, replay_chain
from timecut5.probe import AffineFamily, FROZEN_CURVE, State
from timecut5.pwa import CutPiece, charge_pwa, combined_pwa


def source_piece(domain, slope, intercept, attained, state, witness_lifter=None):
    return AffineCutPiece(domain, Q(slope), Q(intercept), attained, Q(0), (),
                          (state.anchor, state.remaining_schedule, state.stop_count), witness_lifter)


class TestFullPwaPartition(unittest.TestCase):
    def compare(self, effect, source, old, site, **kwargs):
        new = stop_partition((source,), effect, site, FROZEN_CURVE.segments,
                             kwargs.pop("overhead"), **kwargs)
        self.assertTrue(new)
        points = {p.domain.lo for p in new} | {p.domain.hi for p in new}
        for p in new:
            if p.domain.lo < p.domain.hi:
                points.add((p.domain.lo + p.domain.hi) / 2)
        for energy in sorted(points):
            if not any(p.domain.contains(energy) for p in new):
                continue
            prior = [p for p in old if p.domain.contains(energy)]
            current = [p for p in new if p.domain.contains(energy)]
            self.assertTrue(prior, (effect, energy, old))
            self.assertTrue(current, (effect, energy, new))
            old_cut = prior[0].at(energy)
            new_cut = current[0]
            self.assertEqual((new_cut.cut_time_at(energy), new_cut.attained),
                             (old_cut.tau, old_cut.chi), (effect, energy))
            budget = new_cut.cut_time_at(energy) if new_cut.attained else new_cut.cut_time_at(energy) + Q(1, 10)
            witness = new_cut.witness_lifter(energy, budget)
            self.assertIsInstance(witness, TransitionWitness)
            self.assertEqual((witness.effect, witness.output_energy), (effect, energy))
            self.assertLess(witness.input_energy, witness.output_energy)
        return new

    def test_full_c_partition_and_projection_lift_match_legacy(self):
        domain = Interval(0, 1, False, True)
        state = State("s", 1, 0)
        old_source = CutPiece.from_affine(AffineFamily(domain, 60, 1000, True, 0, (), state))
        new_source = source_piece(domain, 60, 1000, True, state,
                                 lambda e, t: ("inherited-family", e, t))
        old = charge_pwa((old_source,), FROZEN_CURVE, 300, "c")
        migrated = self.compare("C", new_source, old, "c", overhead=300)
        sample = next(p for p in migrated if p.domain.contains(Q(48)))
        witness = sample.witness_lifter(Q(48), sample.cut_time_at(Q(48)) + (Q(0) if sample.attained else Q(1,10)))
        self.assertEqual(witness.predecessor[0], "inherited-family")
        self.assertEqual(witness.predecessor[1], witness.input_energy)

    def test_full_cs_partition_and_projection_lift_match_legacy(self):
        domain = Interval(0, 1)
        state = State("s", 1, 0)
        old_source = CutPiece.from_affine(AffineFamily(domain, 2, 3, True, 0, (), state))
        new_source = source_piece(domain, 2, 3, True, state)
        old = combined_pwa((old_source,), FROZEN_CURVE, "cs", 5, 20, 2, 1)
        self.compare("CS", new_source, old, "cs", overhead=1, a=5, b=20, duration=2)

    def test_c18_two_transition_restricted_family_witness_json_cold_replay(self):
        initial = AffineCutPiece(
            Interval(Q(1), Q(1)), Q(0), Q(0), True, Q(0), (),
            ("origin", 0, 0),
            lambda energy, budget: InitialWitness(energy, budget),
        )
        curve = ((Q(0), Q(10), Q(1), Q(0)),)
        first = family_union(stop_partition((initial,), "C", "c1", curve, 1))
        first = restrict_family(first, Interval(Q(2), Q(2)))
        self.assertEqual(len(first), 1)
        second = family_union(stop_partition(first, "C", "c2", curve, 1))
        second = restrict_family(second, Interval(Q(3), Q(3)))
        self.assertEqual(len(second), 1)
        piece = second[0]
        budget = piece.cut_time_at(Q(3))
        witness = piece.witness_lifter(Q(3), budget)
        self.assertIsInstance(witness, TransitionWitness)
        self.assertEqual(witness.predecessor.site, "c1")
        self.assertEqual(witness.predecessor.predecessor, InitialWitness(Q(1), Q(0)))

        def encode(value):
            if isinstance(value, Q):
                return {"$fraction": str(value)}
            if isinstance(value, tuple):
                return {"$tuple": [encode(item) for item in value]}
            if is_dataclass(value):
                return {"$type": type(value).__name__,
                        "fields": {field.name: encode(getattr(value, field.name))
                                   for field in fields(value)}}
            if isinstance(value, list):
                return [encode(item) for item in value]
            return value

        types = {cls.__name__: cls for cls in (InitialWitness, TransitionWitness)}
        def decode(value):
            if isinstance(value, list):
                return [decode(item) for item in value]
            if not isinstance(value, dict):
                return value
            if "$fraction" in value:
                return Q(value["$fraction"])
            if "$tuple" in value:
                return tuple(decode(item) for item in value["$tuple"])
            if "$type" in value:
                cls = types[value["$type"]]
                return cls(**{key: decode(item) for key, item in value["fields"].items()})
            return {key: decode(item) for key, item in value.items()}

        cold = decode(json.loads(json.dumps(encode(witness))))
        self.assertEqual(cold, witness)
        energy, time, events, rho, trace = replay_chain(cold)
        self.assertEqual((energy, time, events, rho), (Q(3), Q(4), (("c1", "C"), ("c2", "C")), Q(0)))
        self.assertEqual([row[:2] for row in trace], [("C", "c1"), ("C", "c2")])

    def test_family_union_restriction_and_cross_family_rejection(self):
        d = Interval(0, 2)
        a = AffineCutPiece(d, Q(1), Q(0), False, Q(0), (), ("s", 1, 0))
        b = AffineCutPiece(d, Q(-1), Q(2), True, Q(0), (), ("s", 1, 0))
        env = family_union((a, b))
        self.assertEqual(len(env), 5)  # endpoint/open-cell partition at the crossing
        self.assertEqual(next(p for p in env if p.domain.contains(Q(1))).attained, True)
        restricted = restrict_family(env, Interval(Q(1,2), Q(3,2)))
        self.assertTrue(all(p.domain.lo >= Q(1,2) and p.domain.hi <= Q(3,2) for p in restricted))
        other = AffineCutPiece(d, Q(0), Q(-1), True, Q(0), (), ("x", 1, 0))
        with self.assertRaises(ValueError): family_union((a, other))


if __name__ == "__main__":
    unittest.main()
