"""Small independent admissibility and partition checks for scale bounds."""
from fractions import Fraction as F
import itertools
import unittest

from hiroute.exact.interval import Interval
from hiroute.exact.pipeline import DriveStep, StopStep, execute_exact_plan, initial_piece
from hiroute.exact.pwa import AffineCutPiece
from hiroute.exact.scale_bounds import (
    SiteFeatures, build_region_tree, completion_bound,
    region_travel_lower_bounds, singleton_region,
)
from hiroute.exact.terminal import terminal_optimize


class CompletionBoundTests(unittest.TestCase):
    def bound(self, pieces, **changes):
        options = dict(start_time=0, travel_time=7, drive_energy=7, reserve=1,
                       overhead=1, stop_penalty=2, charge_slope=2,
                       service_duration=4)
        options.update(changes)
        return completion_bound(pieces, **options)

    def test_exact_minimum_can_be_at_charge_service_kink(self):
        p = AffineCutPiece(Interval(0, 10), F(1), F(0), True,
                           state_key=("a", 1, 0))
        # needed=8, mu=2, service=4: kink at E=6, tau+extra=10.
        self.assertEqual(self.bound((p,)), 20)
        values = [e+max(2*max(0, 8-e), 4)+10 for e in range(11)]
        self.assertEqual(self.bound((p,)), min(values))

    def test_open_endpoint_is_infimum_not_executable_point(self):
        p = AffineCutPiece(Interval(0, 1, False, False), F(1), F(0), False,
                           state_key=("a", 0, 2))
        value = self.bound((p,), drive_energy=0, reserve=0)
        self.assertEqual(value, 14)  # tau inf 0 + drive7 + h1 + 3*lambda2.
        for e in (F(1, 10), F(1, 2), F(9, 10)):
            self.assertLess(value, e+14)
        self.assertFalse(p.domain.contains(0))

    def test_pending_service_is_removed_after_service_action(self):
        base = dict(domain=Interval(10, 10), slope=F(0), intercept=F(5), attained=True)
        pending = AffineCutPiece(**base, state_key=("a", 1, 1))
        done = AffineCutPiece(**base, state_key=("a", 0, 1))
        self.assertEqual(self.bound((pending,))-self.bound((done,)), 4)

    def test_positive_and_negative_time_translation_preserves_relative_bound(self):
        for shift in (-100, 200):
            original = AffineCutPiece(Interval(2, 6), F(-1), F(12), True,
                                      state_key=("a", 1, 1))
            translated = AffineCutPiece(original.domain, original.slope,
                                        original.intercept+shift, original.attained,
                                        state_key=original.state_key)
            self.assertEqual(self.bound((original,)),
                             self.bound((translated,), start_time=shift))

    def test_empty_physical_family_and_invalid_relaxations(self):
        self.assertIsNone(self.bound(()))
        for name in ("travel_time", "drive_energy", "reserve", "overhead",
                     "stop_penalty", "charge_slope", "service_duration"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.bound((), **{name: -1})

    def test_admissible_against_exact_energy_schedule_continuations(self):
        # Independent finite route enumeration includes a detour, repeated
        # charging, and both S and CS completion. Each first-stop class is
        # checked against every feasible terminal, not only its optimizer.
        distance = {("o", "a"): 2, ("o", "b"): 4,
                    ("a", "a"): 0, ("b", "b"): 0,
                    ("a", "b"): 2, ("b", "a"): 1,
                    ("a", "z"): 5, ("b", "z"): 3}
        for pending, energy in itertools.product((0, 1), (2, 3, 6)):
            root = initial_piece(Interval(energy, energy), anchor="o",
                                 remaining_schedule=pending, rho=-energy)
            for first in ("a", "b"):
                remaining = distance[("o", first)]+distance[(first, "z")]
                bound = self.bound((root,), travel_time=remaining,
                                   drive_energy=remaining)
                checked = 0
                for count in (1, 2, 3):
                    for tail in itertools.product(("a", "b"), repeat=count-1):
                        sites = (first,)+tail
                        for effects in itertools.product(("C", "S", "CS"), repeat=count):
                            if sum(effect in {"S", "CS"} for effect in effects) != pending:
                                continue
                            steps = []
                            anchor = "o"
                            for site, effect in zip(sites, effects):
                                d = distance[(anchor, site)]
                                steps.append(DriveStep(site, F(d), F(d), F(0)))
                                steps.append(StopStep(effect, site, F(1),
                                                      ((F(0), F(6), F(2), F(0)),),
                                                      F(0), F(100), F(4)))
                                anchor = site
                            d = distance[(anchor, "z")]
                            steps.append(DriveStep("z", F(d), F(d), F(0)))
                            pieces = execute_exact_plan((root,), steps)
                            terminal = terminal_optimize(pieces, "z", 1, 0, 2)
                            value = (terminal.primary_infimum if terminal.status == "primary_unattained"
                                     else terminal.primary_value)
                            if value is not None:
                                checked += 1
                                self.assertLessEqual(bound, value)
                if energy >= distance[("o", first)]:
                    self.assertGreater(checked, 0)
                else:
                    # A finite relaxation need not detect physical infeasibility.
                    self.assertEqual(checked, 0)


class SummaryRegionTests(unittest.TestCase):
    def setUp(self):
        # Independent Floyd-Warshall on a directed graph; the road distance and
        # time metrics deliberately have different edge weights and orderings.
        self.nodes = ("o", "a", "b", "c", "d", "z")
        edges = (("o", "a", 2, 5), ("a", "b", 3, 2),
                 ("b", "c", 1, 4), ("c", "d", 4, 1),
                 ("d", "z", 2, 5), ("a", "d", 5, 2),
                 ("d", "b", 2, 1), ("b", "a", 1, 7),
                 ("c", "z", 8, 2), ("o", "b", 3, 3))
        self.metrics = []
        for index in (2, 3):
            d = {(a, b): (F(0) if a == b else None)
                 for a in self.nodes for b in self.nodes}
            for edge in edges:
                a, b = edge[:2]
                value = F(edge[index])
                if d[a, b] is None or value < d[a, b]:
                    d[a, b] = value
            for k, a, b in itertools.product(self.nodes, repeat=3):
                if d[a, k] is not None and d[k, b] is not None:
                    value = d[a, k]+d[k, b]
                    if d[a, b] is None or value < d[a, b]:
                        d[a, b] = value
            self.metrics.append(d)
        t, d = self.metrics
        self.features = {s: SiteFeatures(t["o", s], t[s, "z"],
                                          d["o", s], d[s, "z"])
                         for s in self.nodes}
        self.sites = ("a", "b", "c", "d")
        self.capabilities = {"a": ("C",), "b": ("C", "CS"),
                             "c": ("S",), "d": ("C", "S", "CS")}
        self.root = build_region_tree(self.sites, self.capabilities, self.features)

    def walk(self, node):
        yield node
        for child in node.children:
            yield from self.walk(child)

    def test_refinement_is_complete_and_disjoint_for_every_effect(self):
        all_nodes = tuple(self.walk(self.root))
        leaves = tuple(n for n in all_nodes if not n.children)
        self.assertEqual({leaf.site for leaf in leaves}, set(self.sites))
        for node in all_nodes:
            self.assertFalse(hasattr(node, "members"))
            for effect, mask in node.effect_masks.items():
                self.assertEqual(mask.bit_count(), node.summaries[effect].count)
                if node.children:
                    a, b = (c.effect_masks.get(effect, 0) for c in node.children)
                    self.assertEqual(a & b, 0)
                    self.assertEqual(a | b, mask)

    def test_every_region_bound_is_below_every_represented_continuation(self):
        for node in self.walk(self.root):
            for effect, mask in node.effect_masks.items():
                for anchor in self.nodes[:-1]:
                    bounds = region_travel_lower_bounds(node, effect, self.features[anchor])
                    for i, site in enumerate(self.sites):
                        if not mask & (1 << i):
                            continue
                        for lower, d in zip(bounds, self.metrics):
                            if d[anchor, site] is not None:
                                self.assertLessEqual(lower, d[anchor, site]+d[site, "z"])

    def test_singleton_and_region_share_information(self):
        for leaf in self.walk(self.root):
            if leaf.site is None:
                continue
            single = singleton_region(leaf.site, self.capabilities[leaf.site],
                                      self.features[leaf.site])
            self.assertEqual(single.summaries, leaf.summaries)
            for effect in leaf.summaries:
                self.assertEqual(region_travel_lower_bounds(single, effect, self.features["o"]),
                                 region_travel_lower_bounds(leaf, effect, self.features["o"]))

    def test_missing_or_invalid_features_never_silently_remove_candidate(self):
        with self.assertRaises(ValueError):
            build_region_tree(self.sites, self.capabilities, {})
        with self.assertRaises(ValueError):
            SiteFeatures(-1, 0, 0, 0)
        self.assertIsNone(build_region_tree((), {}, {}))
        self.assertIsNone(region_travel_lower_bounds(
            singleton_region("a", ("C",), self.features["a"]), "CS", self.features["o"]))


if __name__ == "__main__":
    unittest.main()
