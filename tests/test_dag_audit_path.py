import hashlib
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
import z3
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'comparison')]
from exact_physical_adapter import Engine,Unknown,_solve
from exact_physical_fixtures import case,tiny_table,IDS,semantics
from tests.test_exact_physical_adapter import trap
from dag_formula_export import export_dag,verify_export

class DAGAuditTests(unittest.TestCase):
    def test_objective_export_roundtrip_and_separate_symbol_binding(self):
        x=z3.Real('objective_only');n=z3.Int('n');b=z3.Bool('b')
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'o.smt2';expr=x+z3.RealVal('2/7')+n
            m=export_dag([b,n>=0],p,objectives=(expr,));self.assertEqual(m['objectives'],1)
            verify_export(p);o=z3.Optimize();o.from_file(str(p))
            self.assertEqual(len(o.objectives()),1)
            s=z3.Solver();s.set(timeout=1000);s.add(o.objectives()[0]!=expr);self.assertEqual(s.check(),z3.unsat)
            with self.assertRaises(ValueError):export_dag([b],Path(d)/'bad',objectives=(b,))

    def test_all_check_paths_outcomes_and_live_formula_unchanged(self):
        kinds=set();original=Engine.check
        def checked(engine,solver,kind,objectives=()):
            before=tuple(solver.assertions())
            if objectives:
                self.assertEqual(len(solver.objectives()),len(objectives))
                self.assertTrue(all(z3.eq(a,b) for a,b in zip(solver.objectives(),objectives)))
            result=original(engine,solver,kind,objectives)
            self.assertEqual(len(before),len(solver.assertions()))
            self.assertTrue(all(z3.eq(a,b) for a,b in zip(before,solver.assertions())))
            kinds.add(kind);return result
        with tempfile.TemporaryDirectory() as d:
            for i,(f,t) in enumerate([(case(n),None) for n in IDS]+[trap(False),trap(True)]):
                if t is None:t=tiny_table(f)[0]
                old=_solve(t,f['physics'],f['upper_witness'],None,8,False,finite_lookup=True)
                path=Path(d)/str(i)
                with patch.object(Engine,'check',checked),patch.object(z3.Solver,'sexpr',side_effect=AssertionError('recursive audit forbidden')),patch.object(z3.Optimize,'sexpr',side_effect=AssertionError('recursive audit forbidden')),patch('z3.parse_smt2_file',side_effect=AssertionError('no parsed transport')),patch('z3.parse_smt2_string',side_effect=AssertionError('no parsed transport')):
                    new=_solve(t,f['physics'],f['upper_witness'],path,8,False,finite_lookup=True,dag_audit=True)
                self.assertEqual(semantics(new),semantics(old));self.assertNotIn('unknown',new['status'])
                for row in json.loads((path/'checks.json').read_text()):
                    p=path/row['file'];meta=verify_export(p)
                    self.assertEqual(meta['payload_sha256'],row['expected_payload_sha256'])
                    self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),row['sha256'])
                    self.assertEqual(row['status'],'completed');self.assertGreater(row['effective_solver_timeout_ms'],0)
                    self.assertEqual(p.read_text().count('(minimize '),row['objective_count'])
        for kind in ('supported-disjunction','supported-J','supported-J-better','supported-J-face','primary-attainment','supported-primary-face-Q','supported-primary-face-Q-better','supported-primary-face-Q-face','joint-attainment','attained-H','attained-H-better','attained-H-face','attained-Pi-0','attained-Pi-0-better','attained-Pi-0-face','attained-full-key'):
            self.assertIn(kind,kinds)

    def test_precheck_failures_never_invoke_solver(self):
        for mode in ('io','quota','mismatch','deadline','unsupported'):
            with tempfile.TemporaryDirectory() as d:
                e=Engine(time.monotonic()+5,Path(d)/'a',dag_audit=True)
                solver=MagicMock(spec=z3.Solver);solver.assertions.return_value=[z3.BoolVal(True)]
                if mode=='unsupported':solver.assertions.return_value=[z3.Select(z3.Array('a',z3.IntSort(),z3.IntSort()),0)==0]
                if mode in ('io','quota','deadline'):
                    exc={'io':OSError('disk'),'quota':ValueError('byte quota'),'deadline':Unknown('deadline')}[mode]
                    context=patch('dag_formula_export.export_dag',side_effect=exc)
                elif mode=='mismatch':context=patch('dag_formula_export.verify_export',return_value=dict(payload_sha256='wrong',bytes=0))
                else:context=patch('dag_formula_export.verify_export',wraps=verify_export)
                with context,self.assertRaises(Unknown):e.check(solver,'failure')
                solver.check.assert_not_called()
                self.assertEqual(json.loads((Path(d)/'a/checks.json').read_text())[0]['status'],'failed')

    def test_started_timeout_receipt_precedes_check_unknown_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'a';e=Engine(time.monotonic()+5,path,dag_audit=True)
            solver=MagicMock(spec=z3.Solver);solver.assertions.return_value=[z3.BoolVal(True)];solver.reason_unknown.return_value='bounded stop'
            def check():
                row=json.loads((path/'checks.json').read_text())[0]
                self.assertEqual(row['status'],'started');self.assertGreater(row['effective_solver_timeout_ms'],0)
                return z3.unknown
            solver.check.side_effect=check
            with self.assertRaises(Unknown):e.check(solver,'unknown')
            row=json.loads((path/'checks.json').read_text())[0]
            self.assertEqual(row['result'],'unknown');self.assertEqual(row['reason'],'bounded stop')
