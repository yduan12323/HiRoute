import copy
from fractions import Fraction as F
import json
from pathlib import Path
import sys,tempfile,time,unittest
from unittest.mock import patch,Mock
from types import SimpleNamespace
import z3
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from strict_bound_decision import decide,decide_real
from exact_physical_adapter import Engine,Unknown,replay
from exact_physical_fixtures import case,tiny_table
from tests.test_exact_physical_adapter import trap

class StrictBoundTests(unittest.TestCase):
    def run_case(self,f,bound,t=None):
        t=t or tiny_table(f)[0]
        with tempfile.TemporaryDirectory() as d:
            result=decide(t,f['physics'],f['upper_witness'],bound,Path(d)/'audit')
            if result['status']!='unknown':
                self.assertEqual(len(result['checks']),1)
                self.assertEqual(result['checks'][0]['kind'],'strict-primary-bound')
                self.assertEqual(result['checks'][0]['status'],'completed')
                self.assertFalse(result['full_key_certified']);self.assertFalse(result['secondary_certified'])
            return result

    def test_exact_boundary_and_no_optimize(self):
        f=case('empty_prefix_terminal')
        with patch('z3.Optimize',side_effect=AssertionError('not optimization')):
            self.assertEqual(self.run_case(f,F(2))['status'],'primary_optimal_only')
            self.assertEqual(self.run_case(f,F(3,2))['status'],'unsat_below_bound')
            r=self.run_case(f,F(5,2));self.assertEqual(r['status'],'sat_supported_below_bound')
            self.assertFalse(r['attained_improvement_certified'])

    def test_support_traps_and_unattainment_do_not_claim_full_key(self):
        self.assertEqual(self.run_case(case('primary_unattained'),F(10))['status'],'unsat_below_bound')
        self.assertEqual(self.run_case(case('secondary_unattained'),F(14))['status'],'primary_optimal_only')
        for f,t in [trap(False),trap(True)]:
            u=replay(t,f['physics'],f['upper_witness']['plan'],f['upper_witness']['charges'],f['upper_witness'].get('initial_wait',0))['key'][0]
            r=self.run_case(f,u,t)
            self.assertNotEqual(r['status'],'unknown')
            self.assertFalse(r['full_key_certified'])

    def test_original_roots_and_only_strict_bound_added(self):
        import strict_bound_decision as module
        captured={};cert=module.certify;feasible=Engine.feasible
        def remember(*args):
            captured['base']=tuple(args[6]);captured['J']=args[1]['J'];return cert(*args)
        def check(engine,roots,kind):
            self.assertEqual(len(roots),len(captured['base'])+1)
            self.assertTrue(all(z3.eq(a,b) for a,b in zip(roots,captured['base'])))
            self.assertTrue(z3.eq(roots[-1],captured['J']<z3.RealVal(2)))
            return feasible(engine,roots,kind)
        with patch.object(module,'certify',side_effect=remember),patch.object(Engine,'feasible',check):
            self.assertEqual(self.run_case(case('empty_prefix_terminal'),F(2))['status'],'primary_optimal_only')

    def test_failures_and_invalid_exact_inputs(self):
        f=case('empty_prefix_terminal');t=tiny_table(f)[0]
        for bound in (True,2.0,'2'):
            with self.assertRaises(TypeError):decide(t,f['physics'],f['upper_witness'],bound,'unused')
        with self.assertRaises(ValueError):decide(t,f['physics'],f['upper_witness'],2,None)
        for target,error in [('strict_bound_decision.certify',ValueError('bad witness')),('exact_physical_adapter.Engine.feasible',Unknown('timeout')),('dag_formula_export.AssertionDAGCache.export',ValueError('audit quota'))]:
            with patch(target,side_effect=error):self.assertEqual(self.run_case(f,2)['status'],'unknown')
        bad=copy.deepcopy(f);bad['upper_witness']['initial_wait']='-1'
        self.assertEqual(self.run_case(bad,2,t)['status'],'unknown')

    def test_phase_memory_samples_observational(self):
        e=Engine(time.monotonic()+3)
        with patch.object(Engine,'memory_sample',return_value={'process_RSS_bytes':123}):
            with e.phase('tiny'):pass
            with self.assertRaises(ValueError):
                with e.phase('failure'):raise ValueError('stop')
        for row in e.phases:
            self.assertEqual(row['memory_start']['process_RSS_bytes'],123)
            self.assertEqual(row['memory_end']['process_RSS_bytes'],123)
        self.assertEqual(e.phases[-1]['status'],'interrupted')
        with patch.dict(sys.modules,{'psutil':SimpleNamespace(Process=Mock(side_effect=RuntimeError('unavailable')))}):
            self.assertIsNone(Engine.memory_sample()['process_RSS_bytes'])


class RealBoundProfileTests(unittest.TestCase):
    def fixture(self):
        f=case('empty_prefix_terminal');return tiny_table(f)[0],f['physics'],f['upper_witness']

    def test_complete_depth_callback_deadline_and_same_semantics(self):
        import strict_bound_decision as mod
        data=self.fixture();seen=[];depth=mod.table_relevant_depth
        def loader(check):check();seen.append('load');return data
        with tempfile.TemporaryDirectory() as d,patch.object(mod,'table_relevant_depth',wraps=depth) as full,patch.object(mod,'relevant_depth',side_effect=AssertionError('wrong profile')):
            result=decide_real(loader,F(2),Path(d)/'audit',time.monotonic()+8)
            self.assertEqual(result['status'],'primary_optimal_only');self.assertTrue(result['complete_depth'])
            self.assertEqual(full.call_count,1);self.assertEqual(seen,['load'])
            self.assertEqual(result['derived_depth'],0);self.assertGreaterEqual(result['end_to_end_wall_s'],result['load_wall_s'])
            self.assertFalse(result['full_key_certified'])

    def test_preflight_existing_unwritable_and_engine_initialization(self):
        data=self.fixture()
        with tempfile.TemporaryDirectory() as d:
            output=Path(d)/'existing';output.mkdir();marker=output/'keep';marker.write_text('evidence')
            loader=Mock(return_value=data)
            result=decide_real(loader,2,output,time.monotonic()+8)
            self.assertEqual(result['status'],'unknown');loader.assert_not_called();self.assertEqual(marker.read_text(),'evidence')
            for target in ('strict_bound_decision.tempfile.mkstemp','strict_bound_decision.Engine'):
                with patch(target,side_effect=PermissionError('denied')):
                    self.assertEqual(decide_real(loader,2,Path(d)/'fresh',time.monotonic()+8)['status'],'unknown')
            self.assertEqual(decide(*data,2,output)['status'],'unknown')

    def test_expiry_during_load_and_after_solver_result(self):
        data=self.fixture()
        with tempfile.TemporaryDirectory() as d:
            def load(check):raise Unknown('load deadline')
            self.assertEqual(decide_real(load,2,Path(d)/'load',time.monotonic()+8)['status'],'unknown')
            for candidate in (None,object()):
                def expired(engine,*args):engine.deadline=time.monotonic()-1;return candidate
                with patch.object(Engine,'feasible',expired):
                    result=decide_real(lambda check:data,2,Path(d)/str(candidate is None),time.monotonic()+8)
                    self.assertEqual(result['status'],'unknown');self.assertNotIn('primary_certified',result)

    def test_invalid_remaining_deadline_and_no_loading(self):
        loader=Mock()
        for deadline in (time.monotonic()-1,time.monotonic()+121,float('nan'),True):
            self.assertEqual(decide_real(loader,2,'unused',deadline)['status'],'unknown')
        loader.assert_not_called()
