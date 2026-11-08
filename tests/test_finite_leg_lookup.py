import sys
from pathlib import Path
import unittest
from unittest.mock import patch
import z3
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'comparison')]
from exact_leg_table import GroundedLookup
from finite_leg_lookup import FiniteGroundedLookup
from exact_physical_adapter import Encoding,_solve,relevant_depth
from exact_physical_fixtures import case,tiny_table,IDS,semantics
from tests.test_exact_physical_adapter import trap


class FiniteLookupTests(unittest.TestCase):
    def test_all_integer_indices_and_defaults_symbolically_equivalent(self):
        for fixture in IDS:
            f=case(fixture);t,_,_=tiny_table(f);old=GroundedLookup(t);new=FiniteGroundedLookup(old)
            index=z3.Int('finite_probe')
            solver=z3.Solver();solver.set(timeout=1000)
            for name in ('T','L','R','AS','AT','C','S'):
                a=getattr(old,name);solver.push()
                solver.add(z3.Select(a,index)!=new._select(a,index))
                self.assertEqual(solver.check(),z3.unsat,(fixture,name))
                solver.pop()

    def test_trace_grounding_all_fixture_seeds_including_empty_and_inactive(self):
        with patch('z3.Solver',side_effect=AssertionError('grounding may not solve')):
            for name in IDS:
                f=case(name);t,_,_=tiny_table(f);old=GroundedLookup(t);new=FiniteGroundedLookup(old)
                plan=f['upper_witness']['plan'];depth=len(plan)+2
                self.assertEqual(old.resolve(old.trace(depth,1 if f['physics']['initial_remaining_schedule'] else 0),plan),
                                 new.resolve(new.trace(depth,1 if f['physics']['initial_remaining_schedule'] else 0),plan))
                for s in range(-1,len(t.sources)+1):
                    for target in range(-1,len(t.targets)+1):
                        x,y=old.at(s,target),new.at(s,target)
                        for attr in ('guard','time','length'):
                            self.assertTrue(z3.is_true(z3.simplify(getattr(x,attr)==getattr(y,attr))))

    def test_encoding_contains_no_arrays_and_preserves_original_trace(self):
        f=case('repeated_C_S_C');t,_,_=tiny_table(f);h,u=relevant_depth(t,f['physics'],f['upper_witness'])
        m=Encoding(t,f['physics'],h,u['key'][0],finite_lookup=True);x=m.state_copy()
        pending=list(m.G)+x['P']+x['strict']+[x['J'],x['Q']];seen=set()
        while pending:
            e=pending.pop()
            if e.get_id() in seen:continue
            seen.add(e.get_id());self.assertNotEqual(e.sort().kind(),z3.Z3_ARRAY_SORT)
            self.assertNotIn(e.decl().kind(),(z3.Z3_OP_SELECT,z3.Z3_OP_STORE))
            pending.extend(e.children())
        self.assertEqual(m.lookup.resolve(m.ground_trace,f['upper_witness']['plan'])['stop_count'],3)

    def test_all_exact_fixture_outcomes_and_strict_support_traps(self):
        # Shared-array outcomes and seven-definition preservation are checked
        # independently in test_exact_physical_adapter. Compare both modes to
        # the same analytic expectations rather than repeat the shared solves.
        fixtures=[(case(name),None,case(name)['expected']) for name in IDS]+[
            (*trap(False),dict(status='attained_optimum',key=['20','0',1,[['b','S']]])),
            (*trap(True),dict(status='attained_optimum',key=['13','1',1,[['b','CS']]]))]
        for f,t,expected in fixtures:
            if t is None:t=tiny_table(f)[0]
            new=_solve(t,f['physics'],f['upper_witness'],None,8,False,finite_lookup=True)
            self.assertEqual(semantics(new),expected)
            self.assertNotIn('unknown',new['status'])

    def test_distinct_source_target_spaces_and_owned_trace_rejection(self):
        f=case('directed_unreachable');a=tiny_table(f)[0];b=tiny_table(f)[0]
        old=GroundedLookup(a);new=FiniteGroundedLookup(old)
        self.assertNotEqual(old.source_index,old.target_index)
        trace=new.trace(2,1)
        with self.assertRaises(ValueError):FiniteGroundedLookup(GroundedLookup(b)).resolve(trace,[])
        for bad in (True,0.5,z3.Real('bad')):
            with self.assertRaises(TypeError):new._select(old.T,bad)
