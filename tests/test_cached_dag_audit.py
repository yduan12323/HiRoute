import json
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch,MagicMock
import z3
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'comparison')]
from dag_formula_export import AssertionDAGCache,export_dag,verify_export
from exact_physical_adapter import Engine
import run_grounded_lookup_consumer as c

class CachedDAGTests(unittest.TestCase):
    def test_exact_cache_hit_and_objective_semantics(self):
        x=z3.Real('x');y=z3.Real('y');j=x+y;roots=[j<=10,x>=0,y>=0]
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);cache=AssertionDAGCache();first=cache.export(roots,p/'a')
            self.assertFalse(first['cache_hit'])
            with patch('dag_formula_export.export_dag',side_effect=AssertionError('cache hit must not rebuild')):
                second=cache.export(roots,p/'b',objectives=(j,x))
            self.assertTrue(second['cache_hit']);verify_export(p/'b')
            export_dag(roots,p/'plain',objectives=(j,x))
            for name in ('b','plain'):
                o=z3.Optimize();o.from_file(str(p/name));self.assertEqual(len(o.objectives()),2)
                s=z3.Solver();s.set(timeout=1000)
                s.add(z3.Or(z3.Xor(z3.And(*roots),z3.And(*o.assertions())),o.objectives()[0]!=j,o.objectives()[1]!=x))
                self.assertEqual(s.check(),z3.unsat)

    def test_misses_context_roots_order_new_objective_and_limits(self):
        x=z3.Real('hiroute_dag_0');roots=[x>=0,x<=4]
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);cache=AssertionDAGCache();cache.export(roots,p/'a')
            self.assertFalse(cache.export(roots,p/'new',objectives=(x+z3.RealVal('1/7'),))['cache_hit'])
            self.assertFalse(cache.export(roots[::-1],p/'order')['cache_hit'])
            self.assertFalse(cache.export([x>=1],p/'changed')['cache_hit'])
            ctx=z3.Context();other=z3.Real('hiroute_dag_0',ctx=ctx)
            self.assertFalse(cache.export([other>=1],p/'context')['cache_hit'])
            limited=AssertionDAGCache(max_nodes=1,max_bytes=10000)
            limited.export(roots,p/'limit');self.assertIsNone(limited.entry)
            self.assertFalse(limited.export(roots,p/'again')['cache_hit'])

    def test_corruption_and_interrupt_fail_without_published_output(self):
        x=z3.Int('x');roots=[x>=0]
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);cache=AssertionDAGCache();cache.export(roots,p/'a')
            (p/'a').write_bytes((p/'a').read_bytes().replace(b'(assert',b';assert'))
            with self.assertRaises(ValueError):cache.export(roots,p/'b')
            self.assertIsNone(cache.entry);self.assertFalse((p/'b').exists())
            cache.export(roots,p/'c')
            def stop():
                if any('.partial-' in q.name for q in p.iterdir()):raise TimeoutError('stop during cache copy')
            with self.assertRaises(TimeoutError):cache.export(roots,p/'d',stop)
            self.assertFalse((p/'d').exists());self.assertIsNone(cache.entry)
            self.assertFalse(any('.partial-' in q.name for q in p.iterdir()))
            tight=AssertionDAGCache();meta=tight.export(roots,p/'e');tight.max_bytes=meta['bytes']
            with self.assertRaises(ValueError):tight.export(roots,p/'f',objectives=(x,))
            self.assertFalse((p/'f').exists())

    def test_engine_never_reuses_sat_result(self):
        with tempfile.TemporaryDirectory() as d:
            e=Engine(time.monotonic()+5,Path(d)/'audit',dag_audit=True)
            solver=MagicMock(spec=z3.Solver);solver.assertions.return_value=[z3.BoolVal(True)];solver.check.return_value=z3.sat
            e.check(solver,'one');e.check(solver,'two')
            self.assertEqual(solver.check.call_count,2)
            self.assertFalse(e.audit[0]['cache_hit']);self.assertTrue(e.audit[1]['cache_hit'])

    def test_validated_producer_finalization_missing_and_mismatched_admission(self):
        old=dict(source=dict(commit=c.PRODUCER,dirty=False));ad=dict(consumer_source={'commit':'consumer','dirty':False})
        table=SimpleNamespace(payload_sha256='table');result=dict(status='UNKNOWN')
        c.completed_result(result,{'status':'primary_unattained'},[],ad,old,table)
        self.assertEqual(result['producer_source'],old['source']);self.assertEqual(result['status'],'COMPLETE')
        for bad_old,bad_ad in (({'source':{'commit':'bad','dirty':False}},ad),(old,dict(ad,producer_source={'commit':'bad'})),({},ad)):
            with self.assertRaises((ValueError,KeyError)):c.completed_result({}, {}, [], bad_ad,bad_old,table)

    def test_consumer_successful_closure_and_final_verification_failure(self):
        for final_failure in (False,True):
            with tempfile.TemporaryDirectory() as d:
                out=Path(d);ad=dict(consumer_source={'commit':'consumer','dirty':False},producer_root=d,producer_files=c.PINNED,real_attempts=1,wall_s=120)
                (out/'consumer-admission.json').write_text(json.dumps(ad))
                old=dict(source=dict(commit=c.PRODUCER,dirty=False),graph_db=d+'/db',graph_db_sha256='hash',sample_pairs=[],upper_witness={'plan':[]})
                table=MagicMock();table.payload_sha256='table';table.literal_plan_legs.return_value=[]
                table._path_store.manifest={'files':{name:{'sha256':'hash'} for name in ('numeric.json','paths.index.json','paths.bin')}}
                comparison={'status':'primary_unattained','primary_infimum':'1'}
                chain=([(old,{})]*2 if not final_failure else [(old,{}),ValueError('final identity failure')])
                with patch.object(c,'source',return_value=ad['consumer_source']),patch.object(c,'verify_identity'),patch.object(c,'verify_controller'),patch.object(c,'producer_chain',side_effect=chain),patch.object(c,'load_verified_table',return_value=(table,{})),patch.object(c,'raw_replay',return_value=[]),patch.object(c,'sha',return_value='hash'),patch('exact_physical_adapter.solve_real',return_value=comparison):
                    code=c.run(out)
                result=json.loads((out/'optimization.result.json').read_text())
                self.assertEqual(code,75 if final_failure else 0)
                self.assertEqual(result['status'],'UNKNOWN' if final_failure else 'COMPLETE')
                if not final_failure:self.assertEqual(result['producer_source'],old['source'])
                self.assertTrue((out/'optimization.started.json').exists());table._path_store.close.assert_called_once()
