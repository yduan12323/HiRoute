"""Whole-arrangement C differential checks and physical restricted witnesses."""
from dataclasses import replace
from fractions import Fraction as F
from itertools import combinations, product
import unittest

from hiroute.exact import AffineCutPiece, Interval, stop_partition, restrict_family
from hiroute.exact.pipeline import InitialWitness, replay_chain

CURVE = ((F(0), F(2), F(1), F(0)), (F(2), F(5), F(2), F(-2)))


def source(domain, slope=0, attained=True, intercept=3):
    def lift(x, budget):
        lower = slope*x + intercept
        if not domain.contains(x) or budget < lower or budget == lower and not attained:
            raise ValueError('outside inherited family')
        # Deliberately return earlier than budget. C must use this actual time.
        time = lower if attained else (lower+budget)/2
        return InitialWitness(x, time, (), F(7))
    return AffineCutPiece(domain, F(slope), F(intercept), attained, F(7), (),
                          ('o', 1, 0), lift)


def compare_arrangement(test, left, right):
    """Compare entire affine cells plus singleton endpoints, including gaps."""
    pieces = (*left, *right)
    knots = {e for p in pieces for e in (p.domain.lo, p.domain.hi)}
    for p, q in combinations(pieces, 2):
        if p.slope != q.slope:
            x = (q.intercept-p.intercept)/(p.slope-q.slope)
            if max(p.domain.lo, q.domain.lo) <= x <= min(p.domain.hi, q.domain.hi):
                knots.add(x)
    order = sorted(knots)
    cells = [(e, e) for e in order] + list(zip(order, order[1:]))
    for lo, hi in cells:
        e = (lo+hi)/2
        def semantic(family):
            at = [p for p in family if p.domain.contains(e)]
            return {(p.cut_time_at(e), p.attained, p.rho, p.prefix, p.state_key)
                    if lo == hi else
                    (p.slope, p.intercept, p.attained, p.rho, p.prefix, p.state_key)
                    for p in at}
        test.assertEqual(semantic(left), semantic(right), (lo, hi))


class COperatorTests(unittest.TestCase):
    def differential(self, sources, curve=CURVE):
        old = stop_partition(sources, 'C', 'c', curve, 1, c_backend='projection')
        new = stop_partition(sources, 'C', 'c', curve, 1, c_backend='analytic')
        compare_arrangement(self, old, new)
        for p in new:
            y = (p.domain.lo+p.domain.hi)/2
            cut = p.cut_time_at(y)
            for slack in (F(0), F(1, 10**40), F(1, 3)):
                if not slack and not p.attained:
                    with self.assertRaises(ValueError): p.witness_lifter(y, cut)
                    continue
                w = p.witness_lifter(y, cut+slack)
                self.assertLess(w.input_energy, y)
                self.assertLessEqual(w.output_time, cut+slack)
                self.assertEqual(w.input_time, w.predecessor.time
                    if isinstance(w.predecessor, InitialWitness) else w.predecessor.output_time)
                self.assertEqual(replay_chain(w)[:4], (y, w.output_time, p.prefix, p.rho))
                self.assertTrue(any(s.domain.contains(w.input_energy) for s in sources))
            with self.assertRaises(ValueError): p.witness_lifter(y, cut-1)
        return new

    def test_sixty_deterministic_domain_slope_attainment_cases(self):
        domains = (Interval(0, 2), Interval(0, 2, False, False),
                   Interval(0, 2, False, True), Interval(0, 2, True, False),
                   Interval(2, 2), Interval(6, 7), Interval(-2, -1),
                   Interval(1, 4), Interval(2, 4, False, False), Interval(4, 5))
        for domain, slope, attained in product(domains, (0, 1, 3), (True, False)):
            with self.subTest(domain=domain, slope=slope, attained=attained):
                self.differential((source(domain, slope, attained),))

    def test_zero_delta_open_support_is_attained_and_strict_charge(self):
        result = self.differential((source(Interval(0, 2, False, False), 1),), CURVE[:1])
        self.assertTrue(all(p.attained for p in result))
        self.assertFalse(any(p.domain.contains(0) for p in result))

    def test_ties_multiple_pieces_gaps_and_inherited_restrictions(self):
        open_cut = source(Interval(0, 2, False, False), 1, False)
        closed_cut = source(Interval(0, 2, False, False), 1, True)
        result = self.differential((open_cut, closed_cut, closed_cut))
        self.assertTrue(next(p for p in result if p.domain.contains(1)).attained)
        self.differential((source(Interval(0,1),3), source(Interval(3,4),0)))
        first = stop_partition((source(Interval(0, 0)),), 'C', 'one', CURVE, 1,
                               c_backend='analytic')
        restricted = restrict_family(first, Interval(F(3, 2), F(3, 2)))
        second = self.differential(restricted)
        for p in second:
            y = (p.domain.lo+p.domain.hi)/2
            w = p.witness_lifter(y, p.cut_time_at(y)+(0 if p.attained else F(1, 9)))
            self.assertEqual(w.input_energy, F(3, 2))
            self.assertEqual(w.predecessor.site, 'one')
            self.assertEqual((p.rho, p.prefix, p.state_key),
                             (F(7), (('one','C'),('c','C')), ('c',1,2)))

    def test_analytic_never_silently_uses_projection(self):
        from unittest.mock import patch
        from hiroute.exact.linear import Projection
        with patch.object(Projection, "build", side_effect=AssertionError("generic projection")):
            stop_partition((source(Interval(0,1)),), "C", "c", CURVE, 1, c_backend="analytic")
            with self.assertRaises(AssertionError):
                stop_partition((source(Interval(0,1)),), "CS", "s", CURVE, 1,
                               a=10,b=20,c_backend="analytic")

    def test_invalid_backend_is_explicit(self):
        with self.assertRaises(ValueError):
            stop_partition((), 'C', 'c', CURVE, 1, c_backend='fallback')

class CCompositionTests(unittest.TestCase):
    def test_full_domain_compositions_and_physical_budget_replay(self):
        from hiroute.exact.pipeline import initial_piece, execute_exact_plan, StopStep, DriveStep
        curve = ((0,5,1,0),)
        seed = initial_piece(Interval(0,1), remaining_schedule=1)
        c = StopStep('C','c',1,curve)
        s = StopStep('S','s',1,(),10,20,0)
        cs = StopStep('CS','s',1,curve,10,20,0)
        for steps in ((c,c), (c,s), (s,c), (c,cs), (c,s,DriveStep('z',1,0))):
            with self.subTest(steps=steps):
                old = execute_exact_plan((seed,),steps,c_backend='projection')
                new = execute_exact_plan((seed,),steps,c_backend='analytic')
                compare_arrangement(self,old,new)
                for p in new:
                    y = (p.domain.lo+p.domain.hi)/2
                    cut = p.cut_time_at(y)
                    w = p.witness_lifter(y,cut+(0 if p.attained else F(1,10**30)))
                    state = replay_chain(w)
                    self.assertEqual(state[0],y)
                    self.assertLessEqual(state[1],cut+(0 if p.attained else F(1,10**30)))
                if steps == (c,s):
                    p = next(p for p in new if p.domain.contains(1))
                    self.assertTrue(p.attained)
                    self.assertEqual(replay_chain(p.witness_lifter(1,10))[1],10)

    def test_terminal_faces_cache_reuse_and_independent_physical_replay(self):
        import json
        from pathlib import Path
        from unittest.mock import patch
        from hiroute.contracts import ProblemSnapshot
        from hiroute.exact import search
        from hiroute_ref.cli import snapshot_case
        from hiroute_ref.model import normalize_case, replay_witness
        from test_prefix_reuse import raw_case, config, math_result
        raw = raw_case()
        cases = [raw]
        frozen = json.loads((Path(__file__).parent/'fixtures/milestone_5_reference/frozen_cases_v2.json').read_text())
        for case in (frozen[5],frozen[6]):
            item = dict(raw,origin=case['origin'],destination=case['destination'],
                departure_time_s=case['start_time_s'],initial_energy_kwh=case['initial_energy_kwh'],
                capacity_kwh=case['capacity_kwh'],minimum_energy_kwh=case['minimum_energy_kwh'],
                destination_reserve_kwh=case['reserve_kwh'],stop_overhead_s=case['overhead_s'],
                stop_penalty_s=case['lambda_stop_s'],consumption_kwh_per_m=case['consumption_kwh_per_m'],
                charging_curve=case['charging_segments'],candidate_order=list(case['sites']),
                site_capabilities=case['sites'],depth_limit=case['H_ref'],schedule=case['schedule'],
                initial_remaining_schedule=1,directed_edges=case['edges'])
            cases.append(item)
        for raw in cases:
            for method in ('flat','hier'):
                snap=ProblemSnapshot.from_dict(raw)
                old=search.solve_snapshot(snap,config(method),c_backend='projection',observer='detailed_trace')
                new=search.solve_snapshot(snap,config(method),c_backend='analytic',observer='detailed_trace')
                self.assertEqual(math_result(old),math_result(new))
                self.assertEqual(old['observer']['trace'],new['observer']['trace'])
                def cold(cache,plan,steps):
                    return search.execute_exact_plan(cache.families[()],steps,c_backend=cache.c_backend)
                with patch.object(search._PlanPrefixCache,'propagate',cold):
                    uncached=search.solve_snapshot(snap,config(method),c_backend='analytic')
                self.assertEqual(math_result(new),math_result(uncached))
                if new['status']=='attained_optimum':
                    source_case,_=snapshot_case(raw)
                    charges=[oe-ie for effect,_,ie,_,oe,_ in new['replay']['trace'] if effect in ('C','CS')]
                    replay=replay_witness(normalize_case(source_case),new['plan'],charges)
                    self.assertEqual(replay['lex_key'],new['key'])


if __name__ == "__main__": unittest.main()
