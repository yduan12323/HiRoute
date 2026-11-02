import copy
from fractions import Fraction as F
import importlib.abc
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'comparison')]
from exact_physical_adapter import Encoding,Engine,Unknown,validate,replay,relevant_depth,solve,real
from exact_physical_fixtures import IDS,case,tiny_table,legacy_snapshot,semantics,edges,physics,schedule,seed
from tiny_smt import replay as separate_replay
import z3


def trap(primary_face=False):
    if primary_face:
        sites={s:dict(anchor=s,effects=['CS']) for s in ('a','b')}
        road=edges([('o','a','1','1/2'),('a','z','1','1/2'),('o','b','1/2','1/2'),('b','z','1/2','3/2')])
        p=physics(B=2,e=1,curve=[['0','2/3','1','0'],['2/3','4/3','1','0'],['4/3','2','1','0']],
                  schedule=schedule(0,10,0))
        w=seed([['b','CS']],['1'],wait='1')
    else:
        sites={'a':dict(anchor='a',effects=['CS']),'b':dict(anchor='b',effects=['S'])}
        road=edges([('o','a',1,1),('a','z',1,1),('o','b',4,1),('b','z',4,1)])
        p=physics(B=1,e=1,rate=0,curve=[['0','1/3','1','0'],['1/3','2/3','1','0'],['2/3','1','1','0']],
                  schedule=schedule(0,100,1))
        w=seed([['b','S']])
    fixture=dict(sites=sites,edges=road,physics=p,upper_witness=w)
    return fixture,tiny_table(fixture)[0]


class PhysicalTests(unittest.TestCase):
    def test_eight_frozen_seeds_independently_replay_and_have_complete_depth(self):
        self.assertEqual(len(IDS),8)
        for name in IDS:
            with self.subTest(name=name):
                f=case(name);table,_,cert=tiny_table(f);H,u=relevant_depth(table,f['physics'],f['upper_witness'])
                self.assertFalse(table.road_selection_certified);self.assertFalse(cert['real_graph'])
                self.assertEqual(cert['table_sha256'],table.payload_sha256)
                p=validate(table,f['physics']);self.assertEqual(H,int(u['key'][0]//(p.get('stop_overhead_s')+p.get('stop_penalty_s'))))
                old=legacy_snapshot(f)
                if old is not None:
                    w=f['upper_witness'];self.assertEqual(separate_replay(old,tuple(tuple(a) for a in w['plan']),w['charges'],w['initial_wait'])['key'],u['key'])
                if name not in ('empty_prefix_terminal','directed_unreachable'):self.assertEqual(len(p.curve),3)

    def test_three_piece_curve_and_repeated_literal_visits_have_analytic_replay(self):
        for name in ('repeated_C_S_C','CS_overlap','equality_attained'):
            f=case(name);t,_,_=tiny_table(f);w=f['upper_witness'];r=replay(t,f['physics'],w['plan'],w['charges'],w['initial_wait'])
            self.assertEqual(semantics(dict(status='attained_optimum',key=r['key'])),f['expected'])
        f=case('repeated_C_S_C');t,_,_=tiny_table(f);w=f['upper_witness']
        trace=replay(t,f['physics'],w['plan'],w['charges'])['trace']
        self.assertEqual([row['site'] for row in trace],['c','s','c'])
        self.assertEqual(trace[0]['finish'],5)  # arrival1 + overhead1 + phi(2)=3

    def test_invalid_input_and_nonpositive_upper_charges_fail_closed(self):
        f=case('alias_positive_charge');t,_,_=tiny_table(f)
        for key,value in [('capacity_kwh',True),('departure_time_s',.5),('stop_overhead_s','0')]:
            p=copy.deepcopy(f['physics']);p[key]=value
            with self.subTest(key=key),self.assertRaises((TypeError,ValueError)):validate(t,p)
        for alter in ('gap','slope','coverage'):
            p=copy.deepcopy(f['physics'])
            if alter=='gap':p['charging_curve'][1][0]='3'
            elif alter=='slope':p['charging_curve'][1][2]='0'
            else:p['charging_curve'].pop()
            with self.subTest(alter=alter),self.assertRaises(ValueError):validate(t,p)
        for charges in (['0'],[],['7'],['6','1']):
            with self.subTest(charges=charges),self.assertRaises(ValueError):replay(t,f['physics'],[['alpha','C']],charges)
        with self.assertRaises(TypeError):replay(t,f['physics'],['alphaC'],['6'])

    def test_no_seed_is_unknown_not_infeasible(self):
        f=case('alias_positive_charge');t,_,_=tiny_table(f)
        self.assertEqual(solve(t,f['physics'])['status'],'unknown_no_attained_bound')
        with self.assertRaises(ValueError):replay(t,f['physics'],[],[])
        H,u=relevant_depth(t,f['physics'],f['upper_witness']);self.assertEqual(u['key'][0],18)
        m=Encoding(t,f['physics'],0,18);x=m.state_copy()
        self.assertIsNone(Engine(time.monotonic()+5).feasible(m.G+x['P']+x['strict'],'empty-terminal-energy'))

    def test_directed_dead_terminal_and_pending_empty_prefix_are_rejected(self):
        f=case('directed_unreachable');t,_,_=tiny_table(f)
        self.assertFalse(t.pairs['dead','z'].reachable)
        with self.assertRaises(ValueError):replay(t,f['physics'],[['dead','S']],[])
        with self.assertRaises(ValueError):replay(t,f['physics'],[],[])
        with self.assertRaises(ValueError):replay(t,f['physics'],[['a','S'],['a','S']],[])

    def test_full_depth_is_not_capped_by_site_count_or_old_prototype_guard(self):
        f=case('alias_positive_charge');t,_,_=tiny_table(f);w=copy.deepcopy(f['upper_witness']);w['initial_wait']='100'
        H,u=relevant_depth(t,f['physics'],w);self.assertGreater(H,6);self.assertGreater(H,len(t.candidate_order))
        # Construction-only diagnostic: this is not a bounded-H optimum claim.
        m=Encoding(t,f['physics'],7,u['key'][0]);self.assertEqual(len(m.choices),7)
        self.assertEqual(m.actions,(('alpha','C'),('omega','C')))
        self.assertEqual(len(m.lookup.source_index),1)

    def test_strict_empty_disjunct_cannot_contribute_its_closed_optimum(self):
        f,t=trap();H,u=relevant_depth(t,f['physics'],f['upper_witness']);m=Encoding(t,f['physics'],H,u['key'][0]);x=m.state_copy()
        e=Engine(time.monotonic()+5)
        self.assertEqual(e.minimum(m.G+x['P'],x['J'],'unsafe-closed'),14)
        result=solve(t,f['physics'],f['upper_witness'])
        self.assertEqual(result['key'],(F(20),F(0),1,(('b','S'),)))
        self.assertFalse(result['road_selection_certified'])

    def test_secondary_support_witness_must_attain_the_primary_face(self):
        f,t=trap(True);H,u=relevant_depth(t,f['physics'],f['upper_witness']);m=Encoding(t,f['physics'],H,u['key'][0])
        x,y=m.state_copy(),m.state_copy();base=m.G+x['P']+y['P']+y['strict']+[x['J']==real(13)]
        self.assertEqual(Engine(time.monotonic()+5).minimum(base,x['Q'],'unsafe-primary-support'),0)
        result=solve(t,f['physics'],f['upper_witness'])
        self.assertEqual(result['key'],(F(13),F(1),1,(('b','CS'),)))

    def test_H_precedes_literal_Pi_on_an_attained_waiting_plateau(self):
        f=dict(sites={'p':dict(anchor='p',effects=['C','S','CS'])},
            edges=edges([('o','p','1/10',1),('p','z','1/10',1)]),
            physics=physics(B=1,e=1,penalty=0,schedule=schedule('11/5',10,'1/10'),
                curve=[['0','1/3','1/10','0'],['1/3','2/3','1/10','0'],['2/3','1','1/10','0']]),
            upper_witness=seed([['p','CS']],['1']))
        t,_,_=tiny_table(f);w=f['upper_witness'];r=solve(t,f['physics'],w)
        self.assertEqual(r['derived_depth'],2)
        self.assertEqual(r['key'],(F(12,5),F(1),1,(('p','CS'),)))
        two=replay(t,f['physics'],[['p','C'],['p','S']],['1'])
        self.assertEqual(two['key'][:2],r['key'][:2]);self.assertEqual(two['key'][2],2)

    def test_equality_latest_start_and_time_translation_in_exact_replay(self):
        f=case('equality_attained');t,_,_=tiny_table(f);w=f['upper_witness']
        reference=replay(t,f['physics'],w['plan'],w['charges']);self.assertEqual(reference['trace'][1]['arrival'],106)
        self.assertEqual(reference['trace'][1]['arrival'],F(f['physics']['schedule']['b'])-1)
        for shift in (-200,100):
            p=copy.deepcopy(f['physics']);p['departure_time_s']=str(F(p['departure_time_s'])+shift)
            for k in ('a','b'):p['schedule'][k]=str(F(p['schedule'][k])+shift)
            self.assertEqual(replay(t,p,w['plan'],w['charges'])['key'],reference['key'])

    def test_deadline_returns_unknown_and_never_an_optimum_or_infeasibility(self):
        f=case('CS_overlap');t,_,_=tiny_table(f)
        with patch.object(Engine,'minimum',side_effect=Unknown('injected resource stop')):
            r=solve(t,f['physics'],f['upper_witness'])
        self.assertEqual(r['status'],'unknown_resource_or_solver');self.assertNotIn('key',r)
        with self.assertRaises(Unknown):Engine(time.monotonic()-1).remaining()

    def test_unknown_SMT_receipt_is_retained(self):
        class Fake:
            def set(self,**kw):pass
            def sexpr(self):return '(assert false)'
            def check(self):return z3.unknown
            def reason_unknown(self):return 'mock-resource-stop'
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'audit';e=Engine(time.monotonic()+5,path)
            with self.assertRaises(Unknown):e.check(Fake(),'mocked-unknown')
            rows=json.loads((path/'checks.json').read_text());self.assertEqual(rows[0]['result'],'unknown')
            self.assertEqual(len(list(path.glob('*.smt2'))),1)

    def test_prepared_eight_cell_admission_fails_closed_on_missing_or_changed_identity(self):
        from run_exact_physical_gate import validate_ready
        src=dict(commit='mock-source',dirty=False)
        ready=dict(state='prepared',source=src,config_sha256='mock-config',case_denominator=8,case_ids=list(IDS),
                   cells=[dict(case=name,status='prepared_unrun') for name in IDS])
        validate_ready(ready,'mock-config',src)
        for mode in ('empty','missing','duplicate','source','config','unfinished'):
            altered=copy.deepcopy(ready)
            if mode=='empty':altered['cells']=[]
            elif mode=='missing':altered['cells'].pop()
            elif mode=='duplicate':altered['cells'][1]=altered['cells'][0]
            elif mode=='source':altered['source']['commit']='different'
            elif mode=='config':altered['config_sha256']='different'
            else:altered['cells'][0]['status']='unprepared'
            with self.subTest(mode=mode),self.assertRaises(ValueError):validate_ready(altered,'mock-config',src)

    def test_receipt_join_requires_all_cells_and_consistent_semantics_and_SMT_files(self):
        import hashlib
        from report_exact_physical_gate import report
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);src=dict(commit='mock',dirty=False);cells=[];records=[]
            for name in IDS:
                folder=root/'cases'/name;folder.mkdir(parents=True);(folder/'SMT').mkdir()
                raw=('mock tiny table '+name).encode();(folder/'tiny-table.json').write_bytes(raw)
                expected=dict(status='attained_optimum',key=['1','0',0,[]]);fixture=dict(expected=expected)
                (folder/'input.json').write_text(json.dumps(fixture))
                cells.append(dict(case=name,status='prepared_unrun',derived_depth=1,
                    table_sha256=hashlib.sha256(raw).hexdigest(),
                    fixture_sha256=hashlib.sha256(json.dumps(fixture,sort_keys=True,separators=(',',':')).encode()).hexdigest()))
                worker=dict(case=name,source=src,config_sha256='cfg',derived_depth=1,status='verified',
                    expected=expected,actual=expected,result=expected,production_optimizer_called=False,
                    real_road_generation=False,real_scale_solve=False,holdout=False)
                (folder/'receipt.json').write_text(json.dumps(worker))
                text='(assert true)';(folder/'SMT'/'0001-mock.smt2').write_text(text+'\n(check-sat)\n')
                checks=[dict(kind='mock',status='completed',result='sat',sha256=hashlib.sha256(text.encode()).hexdigest())]
                (folder/'SMT'/'checks.json').write_text(json.dumps(checks))
                records.append(dict(label='gate_'+name,pid=100,returncode=0,charged_CPU_s=0,
                    sampled_process_group_peak_rss_bytes=0,host_available_min_bytes=4*1024**3))
            ready=dict(state='prepared',case_denominator=8,case_ids=list(IDS),cells=cells,source=src,config_sha256='cfg')
            admission=root/'admission.json';admission.write_text(json.dumps(ready))
            for label in ('admission_semantics_normal','admission_semantics_optimized','frozen_tiny_preparation',
                          'final_report_semantics_normal','final_report_semantics_optimized'):
                records.append(dict(label=label,returncode=0))
            budget=dict(active=None,records=records,charged_commands_CPU_s=0,carried_research_CPU_s='15308.219957741')
            bp=root/'budget.json';bp.write_text(json.dumps(budget))
            self.assertEqual(report(root)['gate_status'],'PASS_TINY_CONDITIONAL_MODEL')
            records[0]['charged_CPU_s']=.0000001;records[1]['charged_CPU_s']=.0000001
            budget['charged_commands_CPU_s']=.0000002;bp.write_text(json.dumps(budget))
            self.assertEqual(report(root)['accounting']['stage_conservative_CPU_s'],'300.000002')
            records[0]['charged_CPU_s']=0;records[1]['charged_CPU_s']=0;budget['charged_commands_CPU_s']=0
            bp.write_text(json.dumps(budget))
            for mode in ('empty','missing','duplicate'):
                bad=copy.deepcopy(ready)
                if mode=='empty':bad['cells']=[]
                elif mode=='missing':bad['cells'].pop()
                else:bad['cells'][1]=bad['cells'][0]
                admission.write_text(json.dumps(bad))
                with self.subTest(mode=mode),self.assertRaises(ValueError):report(root)
            admission.write_text(json.dumps(ready));folder=root/'cases'/IDS[0];rp=folder/'receipt.json';saved=rp.read_text()
            rp.unlink();self.assertEqual(report(root)['gate_status'],'LIMITED_OR_FAILED');rp.write_text(saved)
            bad=json.loads(saved);bad['actual']=dict(status='infeasible');rp.write_text(json.dumps(bad))
            self.assertEqual(report(root)['gate_status'],'LIMITED_OR_FAILED');rp.write_text(saved)
            file=folder/'SMT'/'0001-mock.smt2';old=file.read_text();file.write_text('(changed)')
            self.assertEqual(report(root)['gate_status'],'LIMITED_OR_FAILED');file.write_text(old)
            budget['records'].append(dict(label='gate_outside',pid=101,returncode=0));bp.write_text(json.dumps(budget))
            with self.assertRaisesRegex(ValueError,'unexpected numerical'):report(root)

    def test_independent_model_does_not_import_production_optimizers(self):
        class Block(importlib.abc.MetaPathFinder):
            def find_spec(self,fullname,path=None,target=None):
                if fullname.split('.')[0] in ('hiroute','hiroute_ref','timecut5'):raise AssertionError('production optimizer import')
        block=Block();sys.meta_path.insert(0,block)
        try:
            f=case('alias_positive_charge');t,_,_=tiny_table(f)
            m=Encoding(t,f['physics'],3,18);x,y=m.state_copy(),m.state_copy()
            self.assertNotEqual(x['wait'].get_id(),y['wait'].get_id())
            self.assertEqual(len(m.p.curve),3)
        finally:sys.meta_path.remove(block)


if __name__=='__main__':unittest.main()
