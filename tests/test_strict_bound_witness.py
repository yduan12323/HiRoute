import copy,json,sys,tempfile,unittest
from pathlib import Path
from fractions import Fraction as F
from unittest.mock import patch
import z3
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from strict_bound_witness import certificate,extract,constants,exact_value,publish_unverified
from exact_physical_adapter import real,replay,Encoding
from exact_physical_fixtures import case,IDS
from tests.test_incumbent_model_certificate import fixture_model
from tests.test_exact_physical_adapter import trap


def prepared(f,t=None,zero=False):
    f=copy.deepcopy(f)
    t,original,_,_,_=fixture_model(f,t)
    m=Encoding(t,f['physics'],len(original.choices),original.upper+2,finite_lookup=True)
    x,y=m.state_copy(),m.state_copy();base=m.G+x['P']+y['P']+y['strict']
    roots=[*base,x['J']<real(m.upper)]
    solver=z3.Solver();solver.set(timeout=2000);solver.add(*roots)
    if zero:solver.add(x['qs'][0]==0)
    if solver.check()!=z3.sat:raise AssertionError('tiny SAT fixture required')
    model=solver.model();bs=[(s,exact_value(model.eval(s,model_completion=False),s.sort())) for s in constants(roots,lambda:None)]
    return f,t,m,x,y,roots,model,bs


class WitnessTests(unittest.TestCase):
    def test_all_tiny_cases_aliases_boundaries_and_inactive_slots(self):
        for f,t in [(case(n),None) for n in IDS]+[trap(False),trap(True)]:
            f,t,m,x,y,roots,model,bs=prepared(f,t)
            with tempfile.TemporaryDirectory() as d,patch('z3.Solver',side_effect=AssertionError('no solve in extraction')),patch('z3.Optimize',side_effect=AssertionError('no optimize')):
                out=Path(d)/'candidate.json';result=extract(m,x,y,t,f['physics'],m.upper,roots,model,out)
                self.assertEqual(result['status'],'VERIFIED_ATTAINED_IMPROVEMENT');self.assertFalse(result['optimality_certified'])
                w=result['witness'];r=replay(t,f['physics'],w['plan'],w['charges'],w['initial_wait'])
                self.assertLess(r['key'][0],m.upper)
                self.assertEqual(json.loads(out.read_text())['status'],'UNVERIFIED_CANDIDATE')

    def test_zero_charge_closure_becomes_strict_positive(self):
        f,t,m,x,y,roots,model,bs=prepared(case('primary_unattained'),zero=True)
        self.assertEqual(model.eval(x['qs'][0]).as_fraction(),0)
        result=certificate(m,x,y,t,f['physics'],m.upper,roots,bs)
        self.assertGreater(F(result['witness']['charges'][0]),0)
        self.assertLess(F(result['primary_value']),m.upper)

    def test_missing_false_malformed_nonrational_and_changed_roots_reject(self):
        f,t,m,x,y,roots,model,bs=prepared(case('empty_prefix_terminal'))
        for bad in (bs[:-1],bs+bs[:1],[(s,0.1) for s,v in bs],[(s,True) for s,v in bs]):
            with self.assertRaises(ValueError):certificate(m,x,y,t,f['physics'],m.upper,roots,bad)
        with self.assertRaises(ValueError):certificate(m,x,y,t,f['physics'],m.upper,roots[:-1],bs)
        with self.assertRaises(ValueError):certificate(m,x,y,t,f['physics'],m.upper-1,roots,bs)
        with self.assertRaises(ValueError):certificate(m,x,x,t,f['physics'],m.upper,roots,bs)
        for value in (z3.Real('unbound'),z3.simplify(z3.Sqrt(2))):
            with self.assertRaises(ValueError):exact_value(value,z3.RealSort())
        bad=[(s,F(-1)) if z3.eq(s,y['wait']) else (s,v) for s,v in bs]
        with self.assertRaises(ValueError):certificate(m,x,y,t,f['physics'],m.upper,roots,bad)

    def test_deadline_partial_publication_and_replay_disagreement(self):
        f,t,m,x,y,roots,model,bs=prepared(case('empty_prefix_terminal'))
        def expired():raise TimeoutError('deadline')
        with self.assertRaises(TimeoutError):certificate(m,x,y,t,f['physics'],m.upper,roots,bs,expired)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'candidate.json'
            with self.assertRaises(TimeoutError):publish_unverified(p,{'assignment':[]},expired)
            self.assertFalse(p.exists());self.assertEqual(list(Path(d).iterdir()),[])
            def broken_dump(value,stream,**kwargs):stream.write('{');raise OSError('interrupted write')
            with patch('strict_bound_witness.json.dump',side_effect=broken_dump):
                with self.assertRaises(OSError):publish_unverified(p,{},lambda:None)
            self.assertFalse(p.exists());self.assertEqual(list(Path(d).iterdir()),[])
            p.write_text('partial')
            with self.assertRaises(FileExistsError):publish_unverified(p,{},lambda:None)
            self.assertEqual(p.read_text(),'partial')
        with patch('strict_bound_witness.replay',return_value={'key':(F(-999),0,0,())}):
            with self.assertRaises(ValueError):certificate(m,x,y,t,f['physics'],m.upper,roots,bs)
