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


class HierarchyRouteAuditTests(unittest.TestCase):
    def test_region_relaxation_cannot_strengthen_its_same_information_singletons(self):
        from hiroute.exact.scale_bounds import service_summary, pending_service_travel_bound
        fixture=SummaryRegionTests();fixture.setUp()
        service=service_summary(fixture.capabilities,fixture.features)
        for node in fixture.walk(fixture.root):
            for effect,mask in node.effect_masks.items():
                for anchor,slope,remaining in itertools.product(('o','b'),(-1,1),(0,1)):
                    af=fixture.features[anchor]
                    prefix=() if anchor=='o' else ((anchor,'C'),)
                    piece=AffineCutPiece(Interval(0,10,False,False),F(slope),F(20),False,
                        prefix=prefix,state_key=(anchor,remaining,len(prefix)))
                    rt,rd=region_travel_lower_bounds(node,effect,af)
                    need_r=rd-node.summaries[effect].min_to_destination_distance
                    for i,site in enumerate(fixture.sites):
                        if not mask & (1<<i):continue
                        single=singleton_region(site,fixture.capabilities[site],fixture.features[site])
                        st,sd=region_travel_lower_bounds(single,effect,af)
                        need_s=sd-single.summaries[effect].min_to_destination_distance
                        self.assertLessEqual(rt,st);self.assertLessEqual(rd,sd)
                        self.assertLessEqual(need_r,need_s)
                        for inbound in (False,True):
                            options=dict(start_time=0,reserve=1,overhead=1,stop_penalty=2,
                                         charge_slope=2,service_duration=4)
                            rb=completion_bound((piece,),travel_time=rt,drive_energy=rd,
                                inbound_energy=need_r if inbound else None,**options)
                            sb=completion_bound((piece,),travel_time=st,drive_energy=sd,
                                inbound_energy=need_s if inbound else None,**options)
                            if rb is None:self.assertIsNone(sb)
                            elif sb is not None:self.assertLessEqual(rb,sb)
                        self.assertLessEqual(pending_service_travel_bound(af,service,
                            node.summaries[effect],effect,1),pending_service_travel_bound(
                            af,service,single.summaries[effect],effect,1))

    def test_batching_can_save_bound_queries_or_add_them_without_changing_exact_work(self):
        import test_scale_search as cases
        from hiroute.contracts import ProblemSnapshot
        from hiroute.exact.scale import solve_scale
        sites=[f'c{i:02}' for i in range(64)]
        sources=[cases.raw(candidate_order=sites,site_capabilities={s:['C'] for s in sites},
            charging_curve=[['0','10','1','0']],depth_mode='unrestricted',depth_limit=0,
            directed_edges=[cases.edge('o','z',time=20)]+[
                e for s in sites for e in (cases.edge('o',s,time=100),cases.edge(s,'z',time=100))]),
            cases.raw(initial_energy_kwh='20',capacity_kwh='20',candidate_order=['a','b'],
                site_capabilities={'a':['C'],'b':['C']},charging_curve=[['0','20','1','0']],
                depth_mode='unrestricted',depth_limit=0,directed_edges=[cases.edge('o','a',2,2),
                    cases.edge('a','b',6,6),cases.edge('b','z',2,2),cases.edge('o','z',10,10)])]
        for source,expected in zip(sources,((64,1),(2,3))):
            snapshot=ProblemSnapshot.from_dict(source)
            a,b=[solve_scale(snapshot,method=m,eager_incumbent_pruning=True) for m in cases.METHODS]
            self.assertEqual(cases.semantics(a),cases.semantics(b))
            self.assertEqual(a['status'],'attained_optimum')
            self.assertEqual((a['metrics']['singleton_queries'],b['metrics']['summary_queries']),expected)
            self.assertEqual(a['metrics']['transitions'],0);self.assertEqual(b['metrics']['transitions'],0)
            self.assertEqual(a['metrics']['leaf_routes'],0);self.assertEqual(b['metrics']['leaf_routes'],0)

    def test_closed_cs_shortcut_admits_an_empty_strict_branch(self):
        # Common-model comparator design guard, not a Core counterexample.
        root=initial_piece(Interval(1,1),anchor='o',remaining_schedule=1,rho=-1)
        steps=(DriveStep('s',F(1),F(0)),StopStep('CS','s',F(1),
            ((F(0),F(1),F(1),F(0)),),F(0),F(10),F(1)),DriveStep('z',F(1),F(0)))
        self.assertEqual(execute_exact_plan((root,),steps),())
        # Replacing q>0 by q>=0 admits this closed point, although no positive
        # charge at a full battery exists anywhere in that fixed branch.
        q=F(0);arrival=F(1);output_energy=F(1)+q
        self.assertLessEqual(output_energy,1)
        self.assertLessEqual(arrival,10-1)
        closed_finish=max(F(0)+1,arrival+1+max(q,F(1)))+1
        self.assertEqual(closed_finish,4)
        self.assertEqual(closed_finish+1,5)  #J with one stop penalty.


if __name__ == "__main__":
    unittest.main()
