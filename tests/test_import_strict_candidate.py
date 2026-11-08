import copy,hashlib,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from fractions import Fraction as F
import z3
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from import_strict_candidate import verify_candidate
from strict_bound_witness import publish_unverified
from incumbent_model_certificate import incumbent_bindings
from exact_physical_adapter import Encoding,relevant_depth,real
from exact_physical_fixtures import case,tiny_table
from dag_formula_export import export_dag
from run_shared_leg_pilot import source
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

class ImportTests(unittest.TestCase):
    def setUp(self):
        for name in ('Solver','Optimize','Tactic','parse_smt2_file','parse_smt2_string'):
            guard=patch('z3.'+name,side_effect=AssertionError('no solver/parser in import stage'));guard.start();self.addCleanup(guard.stop)
    def setup_case(self,root,name='empty_prefix_terminal',zero=False):
        f=case(name);t=tiny_table(f)[0];upper=copy.deepcopy(f['upper_witness']);upper['initial_wait']=str(F(upper.get('initial_wait',0))+2)
        h,u=relevant_depth(t,f['physics'],upper)
        m=Encoding(t,f['physics'],h+2,u['key'][0],finite_lookup=True);x,y=m.state_copy(),m.state_copy()
        roots=m.G+x['P']+y['P']+y['strict']+[x['J']<real(m.upper)]
        bs,_=incumbent_bindings(m,x,y,t,f['physics'],f['upper_witness'])
        if zero:
            overrides={s.get_id():F(2) for pair in x['state_symbols'] for s in pair}
            bs=[(s,overrides.get(s.get_id(),v)) for s,v in bs]
        origin=root/'origin';audit=origin/'audit-root/SMT';audit.mkdir(parents=True)
        meta=export_dag(roots,audit/'0001.dag.smt2')
        ad=dict(consumer_source={'commit':'f'*40,'dirty':False},producer_files={'physics':'frozen'},bound=str(m.upper))
        (origin/'consumer-admission.json').write_text(json.dumps(ad))
        payload=dict(bound=str(m.upper),table_sha256=t.payload_sha256,physics_sha256=m.p.sha256,assignment=[dict(name=str(s.decl().name()),sort=str(s.sort()),value=str(v)) for s,v in bs])
        publish_unverified(audit/'candidate.unverified.json',payload,lambda:None)
        expected=dict(verifier_source=source(),original_source=ad['consumer_source'],producer_files=ad['producer_files'],admission_sha256=sha(origin/'consumer-admission.json'),candidate_sha256=sha(audit/'candidate.unverified.json'),audit_sha256=sha(audit/'0001.dag.smt2'),audit_payload_sha256=meta['payload_sha256'])
        fresh=Encoding(t,f['physics'],h+2,u['key'][0],finite_lookup=True);xx,yy=fresh.state_copy(),fresh.state_copy()
        return origin,expected,fresh,xx,yy,t,f['physics'],upper
    def invoke(self,args,out):return verify_candidate(args[0],args[1],out,*args[2:])
    def mutate(self,args,fn):
        path=args[0]/'audit-root/SMT/candidate.unverified.json';raw=json.loads(path.read_text());fn(raw['payload']);raw['payload_sha256']=hashlib.sha256(json.dumps(raw['payload'],sort_keys=True,separators=(',',':')).encode()).hexdigest();path.write_text(json.dumps(raw));args[1]['candidate_sha256']=sha(path)

    def test_exact_import_alpha_names_and_zero_closure_without_solver(self):
        for name,zero in [('empty_prefix_terminal',False),('primary_unattained',True)]:
            with tempfile.TemporaryDirectory() as d,patch('z3.Solver',side_effect=AssertionError('no solver')),patch('z3.Optimize',side_effect=AssertionError('no optimizer')),patch('z3.Tactic',side_effect=AssertionError('no tactics')):
                root=Path(d);args=self.setup_case(root,name,zero);r=self.invoke(args,root/'out')['result']
                self.assertEqual(r['verification_scope'],'SEPARATE_POST_RUN_VERIFICATION');self.assertEqual(r['original_run_status'],'UNKNOWN');self.assertFalse(r['original_run_completed_in_budget']);self.assertFalse(r['optimality_certified'])
                self.assertLess(F(r['primary_value']),args[2].upper)
                if zero:self.assertGreater(F(r['witness']['charges'][0]),0)

    def test_tampered_missing_duplicate_wrong_type_and_stale_identities(self):
        mutations=[lambda p:p['assignment'].pop(),lambda p:p['assignment'].append(p['assignment'][0]),lambda p:p['assignment'][0].update(value=True),lambda p:p['assignment'][0].update(sort='Bool',value='True'),lambda p:p.update(physics_sha256='bad'),lambda p:p.update(bound='999')]
        for fn in mutations:
            with tempfile.TemporaryDirectory() as d:
                root=Path(d);args=self.setup_case(root);self.mutate(args,fn)
                with self.assertRaises((ValueError,TypeError)):self.invoke(args,root/'out')
        for field in ('original_source','verifier_source','producer_files'):
            with tempfile.TemporaryDirectory() as d:
                root=Path(d);args=self.setup_case(root);args[1][field]={}
                with self.assertRaises(ValueError):self.invoke(args,root/'out')

    def test_formula_mismatch_partial_files_deadline_and_replay_failure(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);args=self.setup_case(root);args[2].G.append(z3.BoolVal(True))
            with self.assertRaises(ValueError):self.invoke(args,root/'formula')
        for content in ('{','{"status":1,"status":2}'):
            with tempfile.TemporaryDirectory() as d:
                root=Path(d);args=self.setup_case(root);p=args[0]/'audit-root/SMT/candidate.unverified.json';p.write_text(content);args[1]['candidate_sha256']=sha(p)
                with self.assertRaises(ValueError):self.invoke(args,root/'partial')
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);args=self.setup_case(root)
            def expired():raise TimeoutError('deadline')
            with self.assertRaises(TimeoutError):verify_candidate(args[0],args[1],root/'expired',*args[2:],check=expired)
            self.assertFalse((root/'expired').exists())
            with patch('strict_bound_witness.replay',return_value={'key':(-1,0,0,())}):
                with self.assertRaises(ValueError):self.invoke(args,root/'replay')
