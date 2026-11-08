import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import z3
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'comparison')]
from dag_formula_export import export_dag,verify_export
from exact_physical_adapter import Encoding,relevant_depth
from exact_physical_fixtures import case,tiny_table,IDS
from tests.test_exact_physical_adapter import trap

class DAGExportTests(unittest.TestCase):
    def roundtrip(self,roots):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'formula.smt2'
            with patch('z3.Solver',side_effect=AssertionError('export may not solve')):
                meta=export_dag(roots,p);verified=verify_export(p)
            self.assertEqual(meta['payload_sha256'],verified['payload_sha256'])
            parsed=z3.parse_smt2_file(str(p));s=z3.Solver();s.set(timeout=2000)
            s.add(z3.Xor(z3.And(*roots),z3.And(*parsed)))
            self.assertEqual(s.check(),z3.unsat)
            q=Path(d)/'again.smt2';self.assertEqual(meta,export_dag(roots,q));self.assertEqual(p.read_bytes(),q.read_bytes())
            return meta,p.read_text()

    def test_tiny_physical_formulas_and_support_attainment_traps(self):
        for f,t in [(case(n),None) for n in IDS]+[trap(False),trap(True)]:
            if t is None:t=tiny_table(f)[0]
            h,u=relevant_depth(t,f['physics'],f['upper_witness'])
            m=Encoding(t,f['physics'],h,u['key'][0],finite_lookup=True)
            x,y=m.state_copy(),m.state_copy()
            self.roundtrip(m.G+x['P']+y['P']+y['strict'])
            self.roundtrip(m.G+x['P']+[x['J']<=z3.RealVal('1/3'),x['Q']>=0])

    def test_shared_nodes_types_exact_rationals_and_symbol_collision(self):
        x=z3.Real('hiroute_dag_0');n=z3.Int('n!3');b=z3.Bool('flag')
        shared=z3.If(b,x+z3.RealVal('-2/7'),z3.ToReal(n))
        meta,text=self.roundtrip([shared>=0,shared<3,z3.Or(b,n!=2),z3.Implies(b,x==shared)])
        self.assertIn('define-fun _hiroute_dag_',text)
        self.assertEqual(text.count('(/ 2.0 7.0)'),1)
        self.assertGreater(meta['definitions'],0)
        other=Encoding(tiny_table(case(IDS[0]))[0],case(IDS[0])['physics'],0,100,finite_lookup=True)
        second=Encoding(tiny_table(case(IDS[0]))[0],case(IDS[0])['physics'],0,100,finite_lookup=True)
        self.roundtrip([z3.BoolVal(True)]+other.G+second.G)
        self.roundtrip([z3.BoolVal(False)])

    def test_unsupported_inputs_never_publish(self):
        x=z3.Int('x');a=z3.Array('a',z3.IntSort(),z3.IntSort())
        bad=[[z3.Select(a,x)==0],[z3.ForAll(x,x==x)],[z3.Function('f',z3.IntSort(),z3.IntSort())(x)==0],
             [z3.Int('unsafe name')==0],[z3.Int('true')==0],[z3.Int('same')==0,z3.Real('same')==0],
             [z3.BitVec('bv',8)==0],[z3.Sqrt(2)==0],[],[x]]
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bad.smt2'
            for roots in bad:
                with self.assertRaises(ValueError):export_dag(roots,p)
                self.assertFalse(p.exists())
            self.assertEqual(list(Path(d).iterdir()),[])

    def test_interrupt_limits_no_overwrite_and_partial_rejection(self):
        x=z3.Int('x');roots=[x+1>0]
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'out.smt2'
            for kw in ({'max_nodes':1},{'max_bytes':20}):
                with self.assertRaises(ValueError):export_dag(roots,p,**kw)
                self.assertFalse(p.exists())
            def stop():raise TimeoutError('deadline')
            with self.assertRaises(TimeoutError):export_dag(roots,p,stop)
            def during_write():
                if any('.partial-' in q.name for q in Path(d).iterdir()):
                    raise TimeoutError('interrupted during emission')
            with self.assertRaises(TimeoutError):export_dag(roots,p,during_write)
            self.assertFalse(p.exists());self.assertEqual(list(Path(d).iterdir()),[])
            export_dag(roots,p);before=p.read_bytes()
            with self.assertRaises(FileExistsError):export_dag([x<0],p)
            self.assertEqual(before,p.read_bytes())
            for content in (before[:-1],before[:-100],before.replace(b'(assert',b';assert'),before+b'\n'):
                q=Path(d)/'partial';q.write_bytes(content)
                with self.assertRaises(ValueError):verify_export(q)
            with self.assertRaises(ValueError):verify_export(p,max_bytes=1)
            self.assertFalse(any('.partial-' in f.name for f in Path(d).iterdir()))

    def test_repeated_dag_has_one_definition_per_compound_node(self):
        x=z3.Int('dag_leaf');node=x
        for _ in range(120):node=node+node
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'chain.smt2';meta=export_dag([node>0,node<100],p)
            self.assertEqual(meta['definitions'],122)
            self.assertLess(meta['bytes'],20000)
            verify_export(p)
