"""Tiny execution of the combined worker's actual recovery result/catch block."""
import ast
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'integration'))
import test_sparse_layer_integration as fixtures
import production_boundary as boundary
from timecut5.layer_envelope import LayerEnvelopeStop
from timecut5.durable_incumbent import load_verified

class RecoveryWithoutLayer(Exception):pass

class Tests(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.Tests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        source=ROOT/'real_trial/worker.py';tree=ast.parse(source.read_text())
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        outer=next(n for n in fn.body if isinstance(n,ast.Try))
        index=next(i for i,n in enumerate(outer.body) if isinstance(n,ast.Try) and any(
            isinstance(v,ast.Call) and isinstance(v.func,ast.Name) and v.func.id=='run_production' for v in ast.walk(n)))
        part=outer.body[index:]
        wrapper=ast.FunctionDef(name='execute_tail',args=ast.arguments(posonlyargs=[],args=[],kwonlyargs=[],kw_defaults=[],defaults=[]),body=part,decorator_list=[])
        self.code=compile(ast.fix_missing_locations(ast.Module(body=[wrapper],type_ignores=[])),str(source),'exec')
    def run_tail(self,previous,run,save):
        from types import SimpleNamespace
        import hashlib
        env=dict(sys=SimpleNamespace(argv=['worker','out','digest','flat','fd','verify']),json=json,
            previous=previous,previous_digest=hashlib.sha256(previous).hexdigest() if previous else None,
            run_production=run,save=save,LayerEnvelopeStop=LayerEnvelopeStop,RecoveryWithoutLayer=RecoveryWithoutLayer,
            inputs={},spec={},native={},router_factory=None,stage=None,complete_closure_check=None,
            progress_factory=None,checkpoint_factory=None)
        exec(self.code,env);env['execute_tail']()
    def prior(self,method):
        options,factory,_,_,path=self.f.context(depth=1)
        with self.assertRaises(LayerEnvelopeStop):
            boundary._execute_admitted(method=method,**options,checkpoint_factory=factory)
        return path.read_bytes(),path.with_name(path.name+'.incumbent')
    def test_fresh_witness_then_exact_worker_recovery_catch(self):
        for method in ('flat','hier'):
            previous,record=self.prior(method);saved={}
            options,factory,_,_,_=self.f.context(previous=previous,depth=1)
            def verified_factory(*args):
                session=factory(*args)
                witness,key=load_verified(record,problem_factory=session.verifier_problem,binding_supplier=session.bindings)
                saved['witness_verification_result.json']={'status':'verified_feasible_only','J':str(key[0])}
                return session
            def run(**_):
                return boundary._execute_admitted(method=method,**options,checkpoint_factory=verified_factory)
            self.run_tail(previous,run,lambda name,value:saved.update({name:value}))
            self.assertEqual(saved['verification_result.json']['status'],'witness_and_layer_verified')
            self.assertIn('witness_verification_result.json',saved)
            self.assertFalse(saved['verification_result.json']['exact_optimum_claimed'])
    def test_witness_only_and_mismatched_replay_never_claim_layer_verified(self):
        saved={}
        def witness_only(**_):
            saved['verification_result.json']={'status':'witness_verified_no_layer','layer_status':'absent'}
            raise RecoveryWithoutLayer()
        self.run_tail(None,witness_only,lambda name,value:saved.update({name:value}))
        self.assertEqual(saved['verification_result.json']['layer_status'],'absent')
        previous,_=self.prior('flat')
        def wrong(**_):raise LayerEnvelopeStop(b'wrong checkpoint')
        with self.assertRaisesRegex(ValueError,'unequal reconstructed'):
            self.run_tail(previous,wrong,lambda *a:None)

if __name__=='__main__':unittest.main(verbosity=2)
