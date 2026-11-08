import sys
from fractions import Fraction as F
from pathlib import Path
import unittest
from unittest.mock import patch
import z3
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'comparison')]
from finite_leg_lookup import FiniteGroundedLookup
from exact_leg_table import GroundedLookup,dag_nodes
from exact_physical_fixtures import case,tiny_table

class FoldedLookupTests(unittest.TestCase):
    def view(self):
        return FiniteGroundedLookup(GroundedLookup(tiny_table(case('alias_positive_charge'))[0]))

    def test_repeated_exact_values_all_integer_indices_and_defaults(self):
        vectors=[[],[F(0)],[F(2,7)]*8,[F(1)]*4+[F(3)]*4,
                 [F(1),F(2),F(1),F(2)],[F(-3),F(-3),F(0),F(0),F(7,9)]]
        for values in vectors:
            view=self.view();default=z3.RealVal('-11/3');terms=tuple(z3.RealVal(str(v)) for v in values)
            view._finite['T']=(terms,default);index=z3.Int('all_integer_indices')
            with patch('z3.Solver',side_effect=AssertionError('construction may not solve')):
                expression=view._select(view.T,index)
            original=z3.K(z3.IntSort(),default)
            for i,value in enumerate(terms):original=z3.Store(original,i,value)
            solver=z3.Solver();solver.set(timeout=1000);solver.add(expression!=z3.Select(original,index))
            self.assertEqual(solver.check(),z3.unsat)
            for i in (-100,-1,0,len(values)-1,len(values),100):
                actual=z3.simplify(z3.substitute(expression,(index,z3.IntVal(i))))
                self.assertTrue(z3.is_true(z3.simplify(actual==(terms[i] if 0<=i<len(terms) else default))))

    def test_bottom_up_folding_retains_outer_default_guard(self):
        view=self.view();index=z3.Int('index');view._finite['T']=((z3.RealVal('2/7'),)*16,z3.RealVal(-1))
        expression=view._select(view.T,index)
        self.assertTrue(z3.is_app_of(expression,z3.Z3_OP_ITE))
        self.assertTrue(z3.eq(expression.arg(1),z3.RealVal('2/7')))
        self.assertTrue(z3.eq(expression.arg(2),z3.RealVal(-1)))
        self.assertEqual(expression.arg(0).sexpr(),z3.And(index>=0,index<16).sexpr())
        # An old balanced implementation keeps every identical branch pair.
        def old(lo,hi):
            if hi-lo==1:return z3.RealVal('2/7')
            mid=(lo+hi)//2;return z3.If(index<mid,old(lo,mid),old(mid,hi))
        previous=z3.If(z3.And(index>=0,index<16),old(0,16),z3.RealVal(-1))
        self.assertLess(dag_nodes([expression]),dag_nodes([previous]))
        # Exact-value equality only: distinct fractions are never rounded.
        view._finite['T']=((z3.RealVal('1/3'),z3.RealVal('333333333333333333/1000000000000000000')),z3.RealVal(0))
        different=view._select(view.T,index)
        self.assertTrue(z3.is_app_of(different.arg(1),z3.Z3_OP_ITE))

    def test_boolean_unreachable_and_action_defaults_and_original_grounding(self):
        for name,values,default in (
            ('R',[False]*8,False),('R',[True]*8,False),
            ('C',[False,True,True,False],False),('S',[False]*8,False),
            ('AS',[0,0,2,2],0),('AT',[0,3,3,1],0)):
            view=self.view();boolean=type(default) is bool
            # Synthetic vectors must have distinct owned handles: original AS/AT
            # may be structurally equal and intentionally share their selector.
            setattr(view,name,z3.FreshConst(getattr(view,name).sort(),'synthetic_'+name))
            wrap=z3.BoolVal if boolean else z3.IntVal
            terms=tuple(wrap(v) for v in values);view._finite[name]=(terms,wrap(default));index=z3.Int('i')
            expression=view._select(getattr(view,name),index)
            original=z3.K(z3.IntSort(),wrap(default))
            for i,value in enumerate(terms):original=z3.Store(original,i,value)
            solver=z3.Solver();solver.set(timeout=1000);solver.add(expression!=z3.Select(original,index));self.assertEqual(solver.check(),z3.unsat)
        f=case('alias_positive_charge');table=tiny_table(f)[0];original=GroundedLookup(table);folded=FiniteGroundedLookup(original)
        plan=f['upper_witness']['plan']
        with patch('z3.Solver',side_effect=AssertionError('grounding may not solve')):
            self.assertEqual(original.resolve(original.trace(len(plan)+2,0),plan),folded.resolve(folded.trace(len(plan)+2,0),plan))
