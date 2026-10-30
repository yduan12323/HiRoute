"""Small physical counterexamples for the named selected-leg model."""
from fractions import Fraction as F
import itertools
import json
from pathlib import Path
import unittest

from hiroute.contracts import ProblemSnapshot, SolverConfig
from hiroute.exact import search
from hiroute.data.shandong import RawRoadGraph, RawSite, build_snapshot_from_shandong_components
from hiroute_ref.cli import snapshot_case
from hiroute_ref.model import normalize_case, selected_legs
from hiroute_ref.solver import solve_case

BASE = Path(__file__).parent / 'r0/c01_zero_stop_snapshot.json'


def raw_snapshot(**changes):
    raw = json.loads(BASE.read_text())
    raw.update(stop_penalty_s='0', capacity_kwh='5', initial_energy_kwh='5')
    raw.update(changes)
    return raw


def edge(a, b, t=1, length=1, identity=None):
    row = dict(source=a, target=b, time_s=str(t), length_m=str(length))
    if identity is not None:
        row['edge_id'] = identity
    return row


def config(method):
    return SolverConfig(method, 'none', 'bounded_time_cut_v2', 'none', 'none', 'none',
                        'full_lexicographic_J_Q_H_Pi')


def ref_result(raw):
    case, _ = snapshot_case(raw)
    return solve_case(case, keep_evidence=False)['result']


class RouteTests(unittest.TestCase):
    def check_leg(self, edges, nodes, length):
        raw = raw_snapshot(directed_edges=edges)
        snap = ProblemSnapshot.from_dict(raw)
        actual = search.selected_leg(snap, 'o', 'z')
        case, _ = snapshot_case(raw)
        expected = selected_legs(normalize_case(case))['o', 'z']
        self.assertEqual((actual.time_s, actual.length_m), (expected.time, expected.length))
        self.assertEqual(('o',) + tuple(e['target'] for e in actual.edges), nodes)
        self.assertEqual(tuple(e['edge_id'] for e in actual.edges), expected.edges)
        self.assertEqual(actual.length_m, length)
        self.assertEqual(search.selected_leg(snap, 'o', 'o').edges, ())
        self.assertIsNone(search.selected_leg(snap, 'z', 'o'))
        return raw

    def test_a1_a2_a4_time_tie_controls_energy_and_full_key(self):
        edges = [edge('o', 'a', length=2, identity='oa'), edge('a', 'z', length=2, identity='az'),
                 edge('o', 'b', identity='ob'), edge('b', 'z', identity='bz')]
        # All 24 permutations, stable explicit identities.
        for permutation in itertools.permutations(edges):
            raw = self.check_leg(list(permutation), ('o', 'a', 'z'), 4)
            for energy in ('3', '5'):
                raw['initial_energy_kwh'] = energy
                independent = ref_result(raw)
                for method in ('flat', 'hier'):
                    result = search.solve_snapshot(ProblemSnapshot.from_dict(raw), config(method))
                    if energy == '3':
                        self.assertEqual(result['status'], 'infeasible')
                        self.assertEqual(independent['status'], 'infeasible_within_H_ref')
                    else:
                        self.assertEqual(result['key'], (2, 0, 0, ()))
                        self.assertEqual(result['replay']['energy'], 1)
                        self.assertEqual(independent['lex_key'], result['key'])

    def test_a3_parallel_edge_id_precedes_length_and_input_order(self):
        edges = [edge('o', 'z', length=4, identity='a'), edge('o', 'z', length=1, identity='b')]
        for order in (edges, edges[::-1]):
            raw = self.check_leg(order, ('o', 'z'), 4)
            for method in ('flat', 'hier'):
                result = search.solve_snapshot(ProblemSnapshot.from_dict(raw), config(method))
                self.assertEqual(result['key'], (1, 0, 0, ()))
                self.assertEqual(result['replay']['energy'], 1)

    def test_a5_unique_fastest_and_string_node_order(self):
        self.check_leg([edge('o', 'z', 1, 4, 'fast'), edge('o', 'z', 2, 1, 'short')], ('o', 'z'), 4)
        self.check_leg([edge('o', '2', identity='x'), edge('2', 'z', identity='y'),
                        edge('o', '10', length=2, identity='p'), edge('10', 'z', length=2, identity='q')],
                       ('o', '10', 'z'), 4)

    def test_duplicate_edge_identity_is_invalid(self):
        with self.assertRaisesRegex(ValueError,'unique'):
            ProblemSnapshot.from_dict(raw_snapshot(directed_edges=[edge('o','z',identity='x'),
                                                                   edge('o','z',identity='x')]))

    def test_missing_ids_use_same_index_defaults_as_ref(self):
        self.check_leg([edge('o', 'z', length=4), edge('o', 'z', length=1)], ('o', 'z'), 4)


class ProducerTests(unittest.TestCase):
    def produce(self, order=('a', 'b'), edges=None, attachments=None, origin='o'):
        raw = raw_snapshot(candidate_order=[], site_capabilities={}, charging_curve=[['0','5','1','0']],
                           depth_limit=1, initial_energy_kwh='1', origin=origin)
        query = {k: raw[k] for k in ('origin', 'destination', 'departure_time_s', 'initial_energy_kwh',
                    'capacity_kwh', 'minimum_energy_kwh', 'destination_reserve_kwh', 'stop_overhead_s',
                    'stop_penalty_s', 'consumption_kwh_per_m', 'charging_curve', 'schedule', 'initial_remaining_schedule')}
        query.update(H_ref=1, diagnostic_depth_limit=1)
        graph = RawRoadGraph('synthetic', 0, tuple(dict(node_id=n) for n in ('o','a','b','u','z')),
                  tuple(edges if edges is not None else [edge('o','a',identity='oa'), edge('a','z',identity='az'),
                         edge('o','b',identity='ob'), edge('b','z',identity='bz')]), 'synthetic', {})
        sites = tuple(RawSite(n,0,0,'charging_station',('C',),'synthetic') for n in ('a','b','u'))
        return build_snapshot_from_shandong_components(graph,sites,query,
                    site_access_nodes=attachments if attachments is not None else {n:n for n in ('a','b','u')},
                    detour_scores={},candidate_site_ids=list(order))

    def test_fork_order_is_not_a_required_itinerary(self):
        keys = []
        for order in (('a','b'), ('b','a'), ('a','u','b')):
            produced = self.produce(order)
            self.assertEqual(produced.snapshot.candidate_order, order)
            self.assertEqual(len(produced.selected_legs), len(order)+1)
            self.assertTrue(any(not row['reachable'] for row in produced.selected_legs))
            for method in ('flat','hier'):
                result = search.solve_snapshot(produced.snapshot,config(method))
                self.assertEqual(result['status'], 'attained_optimum')
                self.assertEqual(result['replay']['key'], result['key'])
                keys.append(result['key'])
        self.assertEqual(len(set(keys)),1)
        self.assertEqual(keys[0], (4,1,1,(('a','C'),)))

    def test_legal_disconnected_problem_is_solver_infeasible(self):
        produced = self.produce(edges=[edge('o','a',identity='oa')])
        for method in ('flat','hier'):
            self.assertEqual(search.solve_snapshot(produced.snapshot,config(method))['status'],'infeasible')

    def test_missing_attachment_and_endpoint_stay_invalid(self):
        with self.assertRaisesRegex(ValueError,'attachment|access node'):
            self.produce(attachments={'a':'a'})
        with self.assertRaisesRegex(ValueError,'endpoint'):
            self.produce(origin='absent')


class BoundTests(unittest.TestCase):
    def test_translation_bound_witness_and_unattainment(self):
        # A direct incumbent is available before the useful scheduled action.
        # Negative t0 used to inflate the bound and prune the optimum.
        base = raw_snapshot(initial_energy_kwh='1', charging_curve=[['0','5','1','0']],
                candidate_order=['a'],site_capabilities={'a':['S','CS']},depth_limit=1,
                schedule={'a':'10','b':'20','D':'3'},initial_remaining_schedule=1,
                directed_edges=[edge('o','a',identity='oa'),edge('a','z',identity='az')])
        for shift in (0,3600,-3600):
            raw = dict(base, departure_time_s=str(shift),
                       schedule={'a':str(10+shift),'b':str(20+shift),'D':'3'})
            for method in ('flat','hier'):
                result = search.solve_snapshot(ProblemSnapshot.from_dict(raw), config(method))
                self.assertEqual(result['status'],'attained_optimum')
                self.assertEqual(result['key'], (14,1,1,(('a','CS'),)))
                self.assertEqual(result['replay']['time'],14+shift)
                self.assertEqual(result['replay']['key'],result['key'])
            self.assertEqual(ref_result(raw)['lex_key'],result['key'])

    def test_negative_origin_does_not_prune_a_better_sibling(self):
        for shift in (0, 3600, -3600):
            raw = raw_snapshot(departure_time_s=str(shift), initial_energy_kwh='1',
                candidate_order=['a','b'],site_capabilities={'a':['C'],'b':['C']},depth_limit=1,
                charging_curve=[['0','5','1','0']],directed_edges=[
                    edge('o','a',identity='oa'),edge('a','z',length=3,identity='az'),
                    edge('o','b',identity='ob'),edge('b','z',identity='bz')])
            for method in ('flat','hier'):
                result = search.solve_snapshot(ProblemSnapshot.from_dict(raw), config(method))
                self.assertEqual(result['key'], (4,1,1,(('b','C'),)))
                self.assertEqual(result['replay']['time'],4+shift)
            self.assertEqual(ref_result(raw)['lex_key'],result['key'])

    def test_primary_and_secondary_unattainment_translate(self):
        frozen = json.loads((BASE.parents[1]/'fixtures/milestone_5_reference/frozen_cases_v2.json').read_text())
        for c in (frozen[5], frozen[6]):
            expected = c['independent_expected']
            self.assertIn(expected['status'], ('primary_unattained','secondary_unattained'))
            for shift in (0,3600,-3600):
                raw = raw_snapshot(origin=c['origin'],destination=c['destination'],
                    departure_time_s=str(F(c['start_time_s'])+shift),
                    initial_energy_kwh=c['initial_energy_kwh'], capacity_kwh=c['capacity_kwh'],
                    minimum_energy_kwh=c['minimum_energy_kwh'],destination_reserve_kwh=c['reserve_kwh'],
                    stop_overhead_s=c['overhead_s'],stop_penalty_s=c['lambda_stop_s'],
                    consumption_kwh_per_m=c['consumption_kwh_per_m'],
                    charging_curve=c['charging_segments'],candidate_order=list(c['sites']),
                    site_capabilities=c['sites'],depth_limit=c['H_ref'],
                    schedule={k:str(F(v)+shift) if k in ('a','b') else str(v) for k,v in c['schedule'].items()},
                    initial_remaining_schedule=1,directed_edges=c['edges'])
                independent=ref_result(raw)
                for method in ('flat','hier'):
                    result=search.solve_snapshot(ProblemSnapshot.from_dict(raw),config(method))
                    self.assertEqual(result['status'], independent['status'])
                    for key in ('primary_infimum','secondary_infimum'):
                        if key in independent:
                            self.assertEqual(result[key], independent[key])
                    self.assertIsNone(result.get('key'))

    def test_tiny_nonempty_suffix_bound_and_equal_primary_better_q(self):
        raw = raw_snapshot(initial_energy_kwh='1',candidate_order=['a','b'],
                site_capabilities={'a':['C'],'b':['C']},depth_limit=1,charging_curve=[['0','5','1','0']],
                directed_edges=[edge('o','a',identity='oa'),edge('a','z',length=3,identity='az'),
                                edge('o','b',t=2,identity='ob'),edge('b','z',t=2,identity='bz')])
        for method in ('flat','hier'):
            self.assertEqual(search.solve_snapshot(ProblemSnapshot.from_dict(raw),config(method))['key'],
                             (6,1,1,(('b','C'),)))
        raw = raw_snapshot(initial_energy_kwh='2',capacity_kwh='2',candidate_order=['a','b'],
                site_capabilities={'a':['C'],'b':['C']},depth_limit=2,charging_curve=[['0','2','1','0']],
                directed_edges=[edge('o','a',length=2,identity='oa'),edge('a','b',length=2,identity='ab'),
                                edge('b','z',length=2,identity='bz')])
        snap=ProblemSnapshot.from_dict(raw)
        optimum=ref_result(raw)['lex_key'][0]
        for prefix_time,anchor,site,stops in ((F(0),'o','a',0),(F(1),'a','b',1)):
            bound=search._next_stop_bound(snap,prefix_time,search.selected_leg(snap,anchor,site),
                                         search.selected_leg(snap,site,'z'),stops)
            self.assertLessEqual(bound,optimum)

    def test_bound_values_and_tiny_independent_suffix_optima(self):
        for shift in (0,3600,-3600):
            raw = raw_snapshot(departure_time_s=str(shift), initial_energy_kwh='1',
                    candidate_order=['a'],site_capabilities={'a':['C']},depth_limit=1,
                    charging_curve=[['0','5','1','0']],
                    directed_edges=[edge('o','a',identity='oa'),edge('a','z',identity='az')])
            snap = ProblemSnapshot.from_dict(raw)
            inbound = search.selected_leg(snap,'o','a')
            onward = search.selected_leg(snap,'a','z')
            bound = search._next_stop_bound(snap,F(0),inbound,onward,0)
            self.assertEqual(bound,2)
            self.assertLessEqual(bound,ref_result(raw)['lex_key'][0])
