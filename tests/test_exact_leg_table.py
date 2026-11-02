import builtins
import copy
from fractions import Fraction as F
import importlib.abc
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'comparison')]
from exact_leg_table import ExactLegTable,GroundedLookup,SCHEMA,NUMERICAL,SELECTION,dag_nodes
from exact_leg_fixtures import complete_payload,synthetic_payload
import z3


def small():
    # Literal Site 'o' is not the logical origin; two Sites share road anchor p.
    sites={'o':dict(anchor='p',effects=['C','S','CS']),
           'alias':dict(anchor='p',effects=['C']),
           'service':dict(anchor='q',effects=['S'])}
    return complete_payload('o','z',list(sites),sites)


def from_tiny_graph():
    # Existing independent tiny road-path selector, not a production router or
    # optimizer. This is a NEW fixture and never runs the old solver cohorts.
    from tiny_smt import canonical_legs
    edges=[dict(source=a,target=b,time_s=t,length_m=l,edge_id=e) for a,b,t,l,e in [
        ('o','a','1','10','oa2'),('o','a','1','10','oa1'),
        ('a','z','1','10','az'),('o','b','1','1','ob'),('b','z','1','1','bz')]]
    snap=dict(origin='o',destination='z',candidate_order=['a','b'],directed_edges=edges)
    legs=canonical_legs(snap)
    sites={'charge':dict(anchor='a',effects=['C']),
           'service':dict(anchor='b',effects=['S'])}
    payload=complete_payload('o','z',list(sites),sites)
    for row in payload['pairs']:
        leg=legs.get((row['source'],row['target']))
        row.update(reachable=leg is not None,time_s=str(leg[0]) if leg else None,
            actual_length_m=str(leg[1]) if leg else None,
            nodes=list(leg[2]) if leg else [],edges=list(leg[3]) if leg else [])
    payload['graph_identity']='SYNTHETIC_TINY_DIRECTED_TIE_FIXTURE'
    return payload,legs


class ExactLegTests(unittest.TestCase):
    def setUp(self):
        # Even an accidental tiny optimization/check is a test failure.
        self.block_solver=patch('z3.Solver',side_effect=AssertionError('Solver forbidden'))
        self.block_opt=patch('z3.Optimize',side_effect=AssertionError('Optimize forbidden'))
        self.block_solver_for=patch('z3.SolverFor',side_effect=AssertionError('SolverFor forbidden'))
        self.block_solver.start();self.block_opt.start();self.block_solver_for.start()
        self.addCleanup(self.block_solver.stop);self.addCleanup(self.block_opt.stop);self.addCleanup(self.block_solver_for.stop)

    def test_exact_types_and_legacy_contract_rejected(self):
        for value in (True,0.5,'0.5','nan'):
            p=small();p['pairs'][0]['time_s']=value
            with self.subTest(value=value),self.assertRaises((ValueError,TypeError)):ExactLegTable.from_dict(p)
        for key,value in [('selected_leg_contract','min_time_then_actual_length_then_first_discovery'),
                          ('numerical_contract','binary64_totals_as_exact_rationals_v1'),
                          ('road_selection_certified',True)]:
            p=small();p[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):ExactLegTable.from_dict(p)

    def test_missing_duplicate_and_extra_pair_fail_closed(self):
        for mode in ('missing','duplicate','extra'):
            p=small()
            if mode=='missing':p['pairs'].pop()
            elif mode=='duplicate':p['pairs'].append(copy.deepcopy(p['pairs'][0]))
            else:p['pairs'].append(dict(p['pairs'][0],source='outside'))
            with self.subTest(mode=mode),self.assertRaises(ValueError):ExactLegTable.from_dict(p)

    def test_alias_zero_and_literal_identity_are_not_coalesced(self):
        t=ExactLegTable.from_dict(small())
        self.assertEqual(len(t.candidate_order),3);self.assertEqual(len(t.pairs),9)
        self.assertIn(('o','C'),t.actions);self.assertIn(('alias','C'),t.actions)
        self.assertEqual((t.pairs['p','p'].time,t.pairs['p','p'].length),(F(0),F(0)))
        for field,value in [('time_s','1'),('reachable',False)]:
            p=small();row=next(r for r in p['pairs'] if r['source']==r['target']);row[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):ExactLegTable.from_dict(p)

    def test_independent_tiny_path_ties_lengths_directions_and_unreachable(self):
        payload,expected=from_tiny_graph();t=ExactLegTable.from_dict(payload)
        self.assertEqual(t.pairs['o','z'].nodes,('o','a','z'))
        self.assertEqual(t.pairs['o','z'].edges,('oa1','az'))
        self.assertEqual(t.pairs['o','z'].length,20)
        # Length triangle fails through b; it is intentionally accepted.
        self.assertGreater(t.pairs['o','z'].length,t.pairs['o','b'].length+t.pairs['b','z'].length)
        lookup=GroundedLookup(t)
        for (s,d),pair in t.pairs.items():
            expr=lookup.at(lookup.source_index[s],lookup.target_index[d])
            self.assertEqual(z3.is_true(z3.simplify(expr.guard)),pair.reachable)
            if pair.reachable:
                self.assertEqual((pair.time,pair.length,pair.nodes,pair.edges),expected[s,d])
                for x,value in ((expr.time,pair.time),(expr.length,pair.length)):
                    v=z3.simplify(x);self.assertEqual(F(v.numerator_as_long(),v.denominator_as_long()),value)
        self.assertFalse(t.pairs['a','b'].reachable)
        self.assertFalse(t.road_selection_certified)

    def test_reachability_time_and_edge_identity_inconsistency_rejected(self):
        p=small();row=next(r for r in p['pairs'] if r['source']=='o' and r['target']=='z')
        row.update(reachable=False,time_s=None,actual_length_m=None,nodes=[],edges=[])
        with self.assertRaisesRegex(ValueError,'reachability'):ExactLegTable.from_dict(p)
        p=small();row=next(r for r in p['pairs'] if r['source']=='o' and r['target']=='z');row['time_s']='1000'
        with self.assertRaisesRegex(ValueError,'shortest time'):ExactLegTable.from_dict(p)
        p=small();positive=[r for r in p['pairs'] if len(r['edges'])==1]
        positive[1]['edges']=positive[0]['edges']
        with self.assertRaisesRegex(ValueError,'edge identity'):ExactLegTable.from_dict(p)

    def test_finite_index_bounds_and_missing_data_cannot_invent_a_leg(self):
        lookup=GroundedLookup(ExactLegTable.from_dict(small()));s,d=z3.Ints('s d')
        leg=lookup.at(s,d)
        for source,target in [(-1,0),(len(lookup.source_index),0),(0,-1),(0,lookup.width)]:
            self.assertTrue(z3.is_false(z3.simplify(z3.substitute(leg.guard,(s,z3.IntVal(source)),(d,z3.IntVal(target))))))

    def test_boolean_real_and_fractional_indices_are_rejected_not_coerced(self):
        lookup=GroundedLookup(ExactLegTable.from_dict(small()))
        for index in (True,0.5,F(1,2),z3.RealVal('1/2'),z3.Real('accidental_real')):
            with self.subTest(index=str(index)),self.assertRaises(TypeError):lookup.at(index,0)
            with self.subTest(index=str(index)),self.assertRaises(TypeError):lookup.at(0,index)

    def test_lookup_requires_parser_validated_input(self):
        with self.assertRaises(TypeError):GroundedLookup(ExactLegTable())
        with self.assertRaises(TypeError):GroundedLookup(small())

    def test_empty_prefix_repeated_C_S_C_and_inactive_suffix_terminal(self):
        t=ExactLegTable.from_dict(small());lookup=GroundedLookup(t)
        empty=lookup.resolve(lookup.trace(0,0),[])
        self.assertEqual(empty['legs'],((t.pairs['o','z'].time,t.pairs['o','z'].length),))
        with self.assertRaises(ValueError):lookup.resolve(lookup.trace(0,1),[])
        plan=[('o','C'),('service','S'),('alias','C')]
        trace=lookup.trace(7,1);resolved=lookup.resolve(trace,plan)
        literal=t.literal_plan_legs(plan,1)
        self.assertEqual(resolved['plan'],tuple(plan))
        self.assertEqual(resolved['legs'][:3]+resolved['legs'][-1:],tuple((x.time,x.length) for x in literal))
        self.assertEqual(resolved['legs'][3:-1],((F(0),F(0)),)*4)
        self.assertEqual(resolved['stop_count'],3)
        # Seven is greater than Site count and the old H6 guard: no hidden cap.
        self.assertEqual(len(trace.choices),7)
        with self.assertRaises(ValueError):lookup.resolve(trace,[('service','S'),('o','S')])

    def test_immutable_inputs_json_duplicate_keys_and_trace_ownership(self):
        payload=small();t=ExactLegTable.from_dict(payload);payload['sites']['o']['anchor']='changed'
        self.assertEqual(t.aliases['o'],'p')
        with self.assertRaises(TypeError):t.aliases['o']='changed'
        with self.assertRaisesRegex(ValueError,'duplicate JSON'):ExactLegTable.from_bytes(b'{"schema":1,"schema":2}')
        lookup=GroundedLookup(t);trace=lookup.trace(0,0)
        other=small();other['graph_identity']='another';different=GroundedLookup(ExactLegTable.from_dict(other))
        with self.assertRaisesRegex(ValueError,'another immutable'):different.resolve(trace,[])

    def test_no_internal_optimizer_import_and_two_traces_do_not_share_selectors(self):
        original=builtins.__import__
        def block(name,*a,**kw):
            if name.split('.')[0] in ('hiroute','hiroute_ref','timecut5'):
                raise AssertionError('internal optimizer import')
            return original(name,*a,**kw)
        import importlib.util
        spec=importlib.util.spec_from_file_location('isolated_exact_table',ROOT/'tools/exact_leg_table.py')
        module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module
        try:
            with patch('builtins.__import__',side_effect=block):
                spec.loader.exec_module(module)
                lookup=module.GroundedLookup(module.ExactLegTable.from_dict(small()))
                a,b=lookup.trace(1,0),lookup.trace(1,0)
                self.assertNotEqual(a.choices[0].get_id(),b.choices[0].get_id())
                self.assertGreater(module.dag_nodes(lookup.roots(a)),len(lookup.table.pairs))
        finally:sys.modules.pop(spec.name,None)


if __name__=='__main__':unittest.main()
