"""Finite selected-leg fixtures only: no graph, native router, or experiment."""
import ast
import hashlib
import itertools
import json
from pathlib import Path
import sys
import unittest
from fractions import Fraction as F

ROOT = Path(__file__).resolve().parent
# Production imports use the installed package or caller-supplied PYTHONPATH.
from timecut5 import deployable as optimized
from timecut5.real_legs import RealSite, SelectedLeg
from timecut5.sparse_seed import SparseSeedCatalog

# Execute the frozen original function with the exact same dependency classes.
source = (ROOT / 'fixtures' / 'seed_generator_before_short_circuit.py').read_text()
tree = ast.parse(source)
node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'iter_constructive_seed_candidates')
namespace = dict(vars(optimized))
exec(compile(ast.Module(body=[node], type_ignores=[]), 'frozen_original', 'exec'), namespace)
original = namespace[node.name]

class CountingRouter:
    """Mock selected-leg router; counts cold source runs and exact leg requests."""
    def __init__(self, lengths, fail=None):
        self.lengths, self.fail, self.calls, self.sources = lengths, fail, [], []
    def leg(self, source, target):
        self.calls.append((source, target))
        if source not in self.sources:
            self.sources.append(source)
        if (source, target) == self.fail:
            raise RuntimeError('mock source failure')
        length = self.lengths.get((source, target), 1 if source != target else 0)
        value = None if length is None else F(length)
        return SelectedLeg(source, target, value is not None, value, value,
                           'forward', None, None)

class Catalog(SparseSeedCatalog):
    # Deliberately mock the bound source: no graph loading/routing is performed.
    def __init__(self, sites, lengths, fail=None):
        self.origin_anchor, self.destination_anchor = 'o', 'd'
        self.hierarchy_sha256 = self.domain_sha256 = '0' * 64
        self.sites = {sid: RealSite(sid, anchor, effects) for sid, anchor, effects in sites}
        self.provider = CountingRouter(lengths, fail)

def query(**updates):
    result = dict(origin='o', destination='d', hierarchy_sha256='0'*64,
        sparse_domain_sha256='0'*64, H_ref=1, initial_energy_kwh=4, capacity_kwh=6,
        minimum_energy_kwh=0, reserve_kwh=1, consumption_kwh_per_m=1,
        start_time_s=0, overhead_s=1, charging_segments=((0,6,1,0),), schedule=None)
    result.update(updates)
    return result

def run(fn, q, sites, lengths, fail=None):
    catalog = Catalog(sites, lengths, fail)
    return tuple(fn(q, catalog)), catalog.provider

class Equivalence(unittest.TestCase):
    def compare(self, q, sites, lengths):
        old, before = run(original, q, sites, lengths)
        new, after = run(optimized.iter_constructive_seed_candidates, q, sites, lengths)
        self.assertEqual(old, new)
        self.assertLessEqual(len(after.calls), len(before.calls))
        return new, before, after

    def test_finite_full_stream_matrix(self):
        count = 0
        # Attainable positive charge, boundary-zero infimum-style charge, service
        # completion, already discharged schedule, unreachable, energy edges.
        for bound, pending, initial, inbound, outbound, effects in itertools.product(
                (0,1,2,3), (None,0,1), (0,4,6), (None,0,4,5), (None,0,2,8),
                (('C',),('S',),('CS',),('C','CS','S'))):
            q = query(H_ref=bound, initial_energy_kwh=initial)
            if pending is not None:
                q.update(schedule={'a':0,'b':20,'D':2}, initial_remaining_schedule=pending)
            sites = [('z','z',('C','S','CS')), ('a','a',effects), ('terminal','d',('C',))]
            self.compare(q, sites, {('o','a'):inbound, ('a','d'):outbound, ('o','d'):8})
            count += 1
        self.assertEqual(count, 2304)

    def test_specific_saved_source_runs(self):
        cases = [
            ('ineligible', query(), ('S',), 1, 1),
            ('unreachable', query(), ('C',), None, 1),
            ('below_floor', query(minimum_energy_kwh=1), ('C',), 4, 1),
            ('no_headroom', query(initial_energy_kwh=6), ('C',), 0, 1),
            ('pending_charge_only', query(schedule={'a':0,'b':10,'D':1}), ('C',), 1, 1),
        ]
        for name, q, effects, inbound, outbound in cases:
            with self.subTest(name=name):
                _, before, after = self.compare(q, [('a','a',effects)],
                    {('o','a'):inbound, ('a','d'):outbound, ('o','d'):8})
                self.assertIn(('a','d'), before.calls)
                self.assertNotIn(('a','d'), after.calls)
                self.assertEqual(before.sources, ['o','a'])
                self.assertEqual(after.sources, ['o'])

    def test_charge_values_and_zero_need(self):
        out, _, _ = self.compare(query(), [('a','a',('C',))],
                                {('o','d'):8, ('o','a'):1, ('a','d'):2})
        self.assertEqual(out, ((((('a','C'),)), (F(1,2),)),))
        out, _, _ = self.compare(query(), [('a','a',('C',))],
                                {('o','d'):8, ('o','a'):4, ('a','d'):5})
        self.assertEqual(out, ((((('a','C'),)), (F(6),)),))

    def test_attained_and_unattained_single_cs_cases(self):
        # Mandatory CS is the only event and H=1. Service duration is zero,
        # charge slope is one, so J = fixed travel/overhead/stop terms + q.
        # terminal_need=0: infimum q=0 is excluded by strict q>0 (unattained J).
        # terminal_need=2: minimum q=2 is feasible (attained J).
        q = query(schedule={'a':0,'b':20,'D':0}, lambda_stop_s=1)
        for outbound, expected in ((2,F(1,2)), (4,F(2))):
            out, _, _ = self.compare(q, [('a','a',('CS',))],
                                    {('o','d'):8, ('o','a'):1, ('a','d'):outbound})
            self.assertEqual(out, ((((('a','CS'),)), (expected,)),))

    def test_service_at_zero_headroom_is_retained(self):
        q = query(initial_energy_kwh=6, schedule={'a':0,'b':20,'D':1})
        out, _, after = self.compare(q, [('a','a',('C','CS','S'))],
                                    {('o','a'):0, ('a','d'):1})
        self.assertEqual(out, ((((('a','S'),)), ()),))
        self.assertIn(('a','d'), after.calls)

    def test_invalid_queries_same_rejection(self):
        cases = [dict(origin='wrong'),dict(initial_energy_kwh=1.2),
            dict(initial_energy_kwh=True),dict(capacity_kwh=3),dict(H_ref=-1),
            dict(H_ref=True),dict(consumption_kwh_per_m=0),dict(reserve_kwh=7),
            dict(initial_remaining_schedule=1),dict(initial_remaining_schedule=2),
            dict(initial_energy_kwh='invalid')]
        for fields in cases:
            errors=[]
            for fn in (original, optimized.iter_constructive_seed_candidates):
                with self.assertRaises(ValueError) as caught:
                    run(fn, query(**fields), [('a','a',('C',))], {})
                errors.append((type(caught.exception), str(caught.exception)))
            self.assertEqual(*errors)

    def test_needed_source_errors_still_fatal(self):
        for pair in (('o','d'), ('o','a'), ('a','d')):
            for fn in (original, optimized.iter_constructive_seed_candidates):
                with self.assertRaisesRegex(RuntimeError, 'mock source failure'):
                    run(fn, query(), [('a','a',('C',))], {}, fail=pair)

    def test_skipped_source_errors_explicitly_outside_stream_contract(self):
        # Failing unused outbound is not a valid selected-leg source. Original
        # eagerly touched it; short-circuit intentionally does not validate it.
        sites, lengths = [('a','a',('C',))], {('o','a'):None, ('o','d'):8}
        with self.assertRaises(RuntimeError):
            run(original, query(), sites, lengths, fail=('a','d'))
        output, after = run(optimized.iter_constructive_seed_candidates, query(), sites,
                            lengths, fail=('a','d'))
        self.assertEqual(output, ())
        self.assertNotIn(('a','d'), after.calls)

if __name__ == '__main__':
    unittest.main(verbosity=2)
