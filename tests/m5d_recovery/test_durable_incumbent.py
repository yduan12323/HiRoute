import copy
from dataclasses import replace
from fractions import Fraction as R
import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import timecut5
from timecut5.bounded import Problem,_solve_problem,_replay_problem
from timecut5.hierarchy import _solve_hierarchical_problem,build_regions
from timecut5.durable_incumbent import AtomicIncumbentStore,load_verified
from timecut5.provenance import encoded


def case(wait=10):
    return dict(origin='A',destination='D',start_time_s=0,initial_energy_kwh=2,
        capacity_kwh=10,minimum_energy_kwh=0,reserve_kwh=0,overhead_s=1,
        lambda_stop_s=1,consumption_kwh_per_m=1,H_ref=1,sites={'s':['CS']},
        charging_segments=[[0,10,1,0]],schedule=dict(a=wait,b=100,D=0),
        edges=[dict(source='A',target='s',time_s=1,length_m=1),
               dict(source='s',target='D',time_s=1,length_m=1)])


def binding(c):
    module=Path(timecut5.__file__).resolve().parent
    return dict(domain_sha256=hashlib.sha256(encoded(c).encode()).hexdigest(),
        source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(module.glob('*.py'))})


def solve(c,method,hook=None):
    p=Problem(c)
    if method=='flat':
        return _solve_problem(p,singleton_bound=lambda *_:R(0),incumbent_hook=hook)
    return _solve_hierarchical_problem(p,True,build_regions(p.sites),incumbent_hook=hook).bounded


def interrupted(c,method,path):
    store=AtomicIncumbentStore(path,method=method,problem_factory=lambda:Problem(c),binding_supplier=lambda:binding(c))
    p=Problem(c)
    pieces=p.finish(p.advance((p.initial_piece(),),'s','CS'))
    piece=next(piece for piece in pieces if piece.domain.contains(R(5)))
    initial=piece.at(R(5)).approach(R(1))
    initial_key=_replay_problem(p,initial)
    store(initial,initial_key)
    def hook(w,k):
        store(w,k)
        if not k<initial_key:raise AssertionError('expected strict lex improvement')
        os._exit(77)  # abrupt bounded interruption, bypassing solver/finally completion
    solve(c,method,hook)


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'incumbent.json';self.c=case()
    def store(self,method='flat'):
        return AtomicIncumbentStore(self.path,method=method,problem_factory=lambda:Problem(self.c),binding_supplier=lambda:binding(self.c))
    def load(self):
        return load_verified(self.path,problem_factory=lambda:Problem(self.c),binding_supplier=lambda:binding(self.c))
    def witnesses(self):
        p=Problem(self.c)
        pieces=p.finish(p.advance((p.initial_piece(),),'s','CS'))
        found=[]
        for energy in (R(1),R(2)):
            piece=next(piece for piece in pieces if piece.domain.contains(energy))
            w=piece.at(energy).approach(R(1));found.append((w,_replay_problem(p,w)))
        return found
    def test_abrupt_interrupt_both_methods_durable_and_independent(self):
        for method in ('flat','hier'):
            with self.subTest(method=method):
                path=self.path.with_name(method+'.json')
                process=multiprocessing.get_context('fork').Process(target=interrupted,args=(self.c,method,path))
                process.start();process.join(5)
                if process.is_alive():process.kill();process.join();self.fail('tiny search exceeded bound')
                self.assertEqual(process.exitcode,77)
                witness,key=load_verified(path,problem_factory=lambda:Problem(copy.deepcopy(self.c)),binding_supplier=lambda:binding(self.c))
                self.assertEqual(_replay_problem(Problem(self.c),witness),key)
                self.assertEqual(key[0],R(12));self.assertLess(key[1],R(5))
                self.assertEqual(json.loads(path.read_bytes())['payload']['status'],'feasible_only')
    def test_equal_j_secondary_improvement_and_nonimproving_ignored(self):
        low,high=self.witnesses();self.assertEqual(low[1][0],high[1][0]);self.assertLess(low[1],high[1])
        store=self.store();store(*high);store(*low);saved=self.path.read_bytes();store(*high)
        self.assertEqual(store.writes,2);self.assertEqual(saved,self.path.read_bytes());self.assertEqual(self.load(),low)
    def test_enabled_disabled_exact_results_and_order(self):
        for method in ('flat','hier'):
            calls=[]; original=Problem.advance
            def tracked(problem,pieces,site,effect):
                calls.append((tuple(piece.pi for piece in pieces),site,effect))
                return original(problem,pieces,site,effect)
            with patch.object(Problem,'advance',tracked):
                plain=solve(self.c,method)
                first=list(calls);calls.clear();seen=[]
                actual=solve(self.c,method,lambda w,k:seen.append((w,k)))
                self.assertEqual(first,calls)
            self.assertEqual(plain.canonical(),actual.canonical());self.assertTrue(seen)
            self.assertTrue(all(a[1]>b[1] for a,b in zip(seen,seen[1:])))
    def test_open_primary_infimum_is_only_feasible_approximation(self):
        self.c=case(0)
        for method in ('flat','hier'):
            path=self.path.with_name(method+'open.json')
            store=AtomicIncumbentStore(path,method=method,problem_factory=lambda:Problem(self.c),binding_supplier=lambda:binding(self.c))
            solved=solve(self.c,method,store)
            witness,key=load_verified(path,problem_factory=lambda:Problem(self.c),binding_supplier=lambda:binding(self.c))
            self.assertEqual(solved.result.status,'infimum_unattained')
            self.assertGreater(key[0],solved.result.primary_infimum)
            self.assertGreater(witness.charge,0)
    def test_digest_domain_source_and_rehashed_witness_tamper_rejected(self):
        self.store()(*self.witnesses()[0]);original=self.path.read_bytes()
        for field in ('digest','domain','source','witness','key','status'):
            row=json.loads(original)
            if field=='digest':row['sha256']='0'*64
            else:
                p=row['payload']
                if field=='domain':p['binding']['domain_sha256']='0'*64
                if field=='source':p['binding']['source_sha256']['bounded.py']='0'*64
                if field=='witness':p['witness']['events'][-1]['departure_energy']='9'
                if field=='key':p['lex_key'][0]='0'
                if field=='status':p['status']='attained_optimum'
                row['sha256']=hashlib.sha256(encoded(p).encode()).hexdigest()
            self.path.write_text(encoded(row))
            with self.subTest(field=field),self.assertRaises((ValueError,AssertionError)):self.load()
    def test_binding_change_and_malformed_key_fail_before_write(self):
        store=self.store();w,k=self.witnesses()[0]
        with self.assertRaises(ValueError):store(w,(R(0),*k[1:]))
        self.assertFalse(self.path.exists());self.c['reserve_kwh']=1
        with self.assertRaises(ValueError):store(w,k)
        self.assertFalse(self.path.exists())
    def test_io_failure_stops_search_and_preserves_previous_commit(self):
        store=self.store();low,high=self.witnesses();store(*high);old=self.path.read_bytes()
        with patch('timecut5.durable_incumbent.os.replace',side_effect=OSError('disk error')):
            with self.assertRaisesRegex(OSError,'disk error'):store(*low)
        self.assertEqual(old,self.path.read_bytes());self.assertEqual(store.writes,1)
        self.assertEqual(list(self.path.parent.glob('.incumbent.json.*')),[])
        for method in ('flat','hier'):
            with self.assertRaisesRegex(OSError,'failed persistence'):
                solve(self.c,method,lambda *_:(_ for _ in ()).throw(OSError('failed persistence')))
    def test_directory_sync_failure_is_explicit_and_recovery_resolves_commit(self):
        store=self.store();low,high=self.witnesses();store(*high)
        original=os.fsync; calls=[]
        def fail_directory(fd):
            calls.append(fd)
            if len(calls)==2:raise OSError('directory sync failed')
            return original(fd)
        with patch('timecut5.durable_incumbent.os.fsync',side_effect=fail_directory):
            with self.assertRaisesRegex(OSError,'directory sync failed'):store(*low)
        # Rename happened; the synchronous call failed, so callers must recover.
        self.assertEqual(store.writes,1);self.assertEqual(self.load(),low)
        with self.assertRaisesRegex(RuntimeError,'independently recover'):store(*high)
    def test_rehashed_boolean_and_float_integer_impostors_rejected(self):
        self.store()(*self.witnesses()[0]);original=self.path.read_bytes()
        for field in ('state','key'):
            for value in (True,1.0):
                row=json.loads(original);p=row['payload']
                if field=='state':p['witness']['state'][2]=value
                else:p['lex_key'][2]=value
                # Deliberately rehash arbitrary JSON without the strict encoder.
                data=json.dumps(p,sort_keys=True,separators=(',',':'))
                row['sha256']=hashlib.sha256(data.encode()).hexdigest()
                self.path.write_text(json.dumps(row))
                with self.subTest(field=field,value=value),self.assertRaises((ValueError,TypeError)):self.load()
    def test_existing_destination_not_silently_overwritten(self):
        self.store()(*self.witnesses()[0])
        with self.assertRaises(FileExistsError):self.store()

if __name__=='__main__':unittest.main()
