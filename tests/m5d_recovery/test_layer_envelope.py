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
from timecut5.bounded import Problem, _replay_problem, _solve_problem
from timecut5.hierarchy import build_regions, _solve_hierarchical_problem
from timecut5.layer_envelope import run_layer_envelope, LayerEnvelopeStop, _Envelope, _hash, _bytes
from timecut5.provenance import encoded


def case(wait=10):
    return dict(origin='A',destination='D',start_time_s=0,initial_energy_kwh=2,
        capacity_kwh=10,minimum_energy_kwh=0,reserve_kwh=0,overhead_s=1,
        lambda_stop_s=1,consumption_kwh_per_m=1,H_ref=1,sites={'s':['CS']},
        charging_segments=[[0,10,1,0]],schedule=dict(a=wait,b=100,D=0),
        edges=[dict(source='A',target='s',time_s=1,length_m=1),
               dict(source='s',target='D',time_s=1,length_m=1)])


def binding(c):
    root=Path(timecut5.__file__).parent
    return dict(domain_sha256=hashlib.sha256(encoded(c).encode()).hexdigest(),
        source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.glob('*.py'))})


def seed(c):
    p=Problem(c)
    pieces=p.finish(p.advance((p.initial_piece(),),'s','CS'))
    piece=next(p for p in pieces if p.domain.contains(R(5)))
    return piece.at(R(5)).approach(R(1))


def killed_atomic(path, data, after):
    from timecut5.layer_envelope import _atomic
    original=os.replace
    def interrupted(source,target):
        if after:original(source,target)
        os._exit(77)
    with patch('timecut5.layer_envelope.os.replace',side_effect=interrupted):
        _atomic(Path(path),data)


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.c=case();self.serial=0
    def run_search(self, method, **kwargs):
        self.serial+=1
        options=dict(problem_factory=lambda:Problem(self.c),verifier_factory=lambda:Problem(copy.deepcopy(self.c)),
            binding_supplier=lambda:binding(self.c),initial_witness=seed(self.c),method=method,
            output_path=self.base/f'run{self.serial}.json',bound_policy_sha256='a'*64,
            root=build_regions(Problem(self.c).sites) if method=='hier' else None)
        options.update(kwargs)
        return run_layer_envelope(**options)
    def checkpoint(self, method='flat', depth=1, **kwargs):
        with self.assertRaises(LayerEnvelopeStop) as ctx:
            self.run_search(method, stop_after_depth=depth, **kwargs)
        return ctx.exception.checkpoint_bytes
    def test_both_engines_resume_original_seed_parity(self):
        for method in ('flat','hier'):
            plain=self.run_search(method)
            data=self.checkpoint(method)
            row=json.loads(data)
            self.assertFalse(row['header']['complete'])
            self.assertEqual(row['header']['status'],'incomplete_boundary_evidence')
            self.assertEqual(row['state']['depth'],1)
            self.assertTrue(row['state']['frontier'])
            self.assertEqual(row['state']['H_ref'],1)
            resumed=self.run_search(method,previous_checkpoint=data)
            self.assertEqual(plain.canonical(),resumed.canonical())
            lb=R(row['state']['lower_bounds']['bounded_domain_conservative_primary'])
            optimum=plain.result.key[0] if plain.result.key else plain.result.primary_infimum
            self.assertLessEqual(lb,optimum)
            self.assertNotIn('gap',row['state'])
    def test_saved_terminals_and_all_groups_enter_bound(self):
        self.c['H_ref']=2;self.c['sites']={'s':['C','CS']}
        for method in ('flat','hier'):
            row=json.loads(self.checkpoint(method,depth=2))
            self.assertTrue(row['state']['terminals'])
            lower=row['state']['lower_bounds']
            self.assertIsNotNone(lower['saved_terminal_relaxation_primary'])
            expected=min(R(lower[k]) for k in ('open_suffix_primary','saved_terminal_relaxation_primary'))
            expected=min(expected,R(row['state']['feasible_incumbent']['payload']['lex_key'][0]))
            self.assertEqual(R(lower['bounded_domain_conservative_primary']),expected)
            resumed=self.run_search(method,previous_checkpoint=_bytes(row))
            plain=self.run_search(method)
            self.assertEqual(plain.canonical(),resumed.canonical())
    def test_bound_covers_every_frontier_group(self):
        self.c['H_ref']=2;self.c['sites']={'s':['C','CS']}
        for method in ('flat','hier'):
            row=json.loads(self.checkpoint(method,depth=1))
            groups=row['state']['frontier'];self.assertGreater(len(groups),1)
            piece_bounds=[]
            for group in groups:
                for piece in group:
                    m=R(piece['m']);lo,hi=map(R,piece['domain'][:2])
                    time=m*(lo if m>=0 else hi)+R(piece['b'])
                    piece_bounds.append(time-R(self.c['start_time_s'])+R(self.c['lambda_stop_s'])*piece['state'][2])
            self.assertEqual(R(row['state']['lower_bounds']['open_suffix_primary']),min(piece_bounds))
    def test_zero_primary_interval_still_not_optimality_or_completion(self):
        c=case();c.update(origin='D',sites={},edges=[],schedule=None,H_ref=0)
        p=Problem(c);w=p.initial_piece().at(p.initial).approach(R(1))
        with self.assertRaises(LayerEnvelopeStop) as ctx:
            run_layer_envelope(problem_factory=lambda:Problem(c),verifier_factory=lambda:Problem(c),
                binding_supplier=lambda:binding(c),initial_witness=w,method='flat',
                output_path=self.base/'zero.json',bound_policy_sha256='a'*64,stop_after_depth=0)
        row=json.loads(ctx.exception.checkpoint_bytes)
        self.assertEqual(row['state']['lower_bounds']['bounded_domain_conservative_primary'],'0')
        self.assertEqual(row['state']['feasible_incumbent']['payload']['lex_key'][0],'0')
        self.assertFalse(row['header']['complete'])
        self.assertEqual(row['header']['status'],'incomplete_boundary_evidence')
    def test_primary_bounds_against_independent_reference_solver(self):
        from validation.reference5.solver import solve_case
        for wait,reserve,status,expected_j in ((10,2,'attained_optimum',R(12)),
                (10,0,'secondary_unattained',R(12)),(0,0,'primary_unattained',R(4))):
            self.c=case(wait);self.c['reserve_kwh']=reserve
            reference=solve_case(copy.deepcopy(self.c),keep_evidence=False)['result']
            self.assertEqual(reference['status'],status)
            self.assertEqual(reference['primary_infimum'],expected_j)
            for method in ('flat','hier'):
                for depth in (0,1):
                    row=json.loads(self.checkpoint(method,depth))
                    lower=R(row['state']['lower_bounds']['bounded_domain_conservative_primary'])
                    upper=R(row['state']['feasible_incumbent']['payload']['lex_key'][0])
                    self.assertLessEqual(lower,reference['primary_infimum'])
                    self.assertLessEqual(reference['primary_infimum'],upper)
                    self.assertFalse(row['header']['complete'])
    def test_rehashed_descriptors_incumbent_and_bounds_rejected(self):
        data=self.checkpoint()
        for kind in ('slope','endpoint','chi','lower','key','depth','terminals'):
            row=json.loads(data);s=row['state']
            if kind=='slope':s['frontier'][0][0]['m']='999'
            if kind=='endpoint':s['frontier'][0][0]['domain'][2]=not s['frontier'][0][0]['domain'][2]
            if kind=='chi':s['frontier'][0][0]['chi']=not s['frontier'][0][0]['chi']
            if kind=='lower':s['lower_bounds']['bounded_domain_conservative_primary']='999'
            if kind=='key':s['feasible_incumbent']['payload']['lex_key'][0]='999'
            if kind=='depth':s['depth']=0
            if kind=='terminals':s['terminals']=[s['frontier'][0][0]]
            row['history'][-1]=_hash(s)
            with self.subTest(kind=kind),self.assertRaises(ValueError):
                self.run_search('flat',previous_checkpoint=_bytes(row))
    def test_source_domain_policy_h_ref_and_initial_seed_mismatch(self):
        data=self.checkpoint()
        for field in ('domain','source','policy','H_ref','seed','bool_H_ref'):
            row=json.loads(data);h=row['header']
            if field=='domain':h['binding']['domain_sha256']='b'*64
            if field=='source':h['search_source_sha256']['bounded.py']='b'*64
            if field=='policy':h['config']['bound_policy_sha256']='b'*64
            if field=='H_ref':h['config']['H_ref']=2
            if field=='bool_H_ref':h['config']['H_ref']=True
            if field=='seed':h['initial_seed']['lex_key'][0]='999'
            with self.subTest(field=field),self.assertRaises(ValueError):
                self.run_search('flat',previous_checkpoint=_bytes(row))
    def test_open_endpoint_lower_bound_is_not_attainment_claim(self):
        self.c=case(0)
        for method in ('flat','hier'):
            row=json.loads(self.checkpoint(method))
            exact=self.run_search(method)
            self.assertEqual(exact.result.status,'infimum_unattained')
            self.assertTrue(any(not p['domain'][2] or not p['domain'][3]
                                for g in row['state']['frontier'] for p in g))
            self.assertLessEqual(R(row['state']['lower_bounds']['bounded_domain_conservative_primary']),
                                 exact.result.primary_infimum)
            self.assertGreater(R(row['state']['feasible_incumbent']['payload']['lex_key'][0]),
                               exact.result.primary_infimum)
    def envelope(self, method='flat'):
        self.serial+=1;p=Problem(self.c)
        return _Envelope(problem=p,verifier_factory=lambda:Problem(self.c),
            binding_supplier=lambda:binding(self.c),initial_witness=seed(self.c),method=method,
            path=self.base/f'envelope{self.serial}.json',config={},previous_checkpoint=None,stop_after_depth=None)
    def test_missing_candidate_or_too_low_scalar_fails_closed(self):
        for method in ('flat','hier'):
            hook=self.envelope(method);p=hook.problem
            too_low=R(0) if method=='flat' else ((R(0),R(0),0,()),None)
            with self.assertRaisesRegex(ValueError,'historical pruning'):
                hook(0,((p.initial_piece(),),),(),too_low,(0,1,1))
            self.assertFalse(hook.path.exists())
    def test_homogeneous_groups_and_depth_checked(self):
        for fault in ('mixed','depth'):
            hook=self.envelope();p=hook.problem;initial=p.initial_piece()
            other=replace(initial,state=replace(initial.state,remaining_schedule=0))
            group=(initial,other) if fault=='mixed' else (initial,)
            with self.assertRaises(ValueError):
                hook(0 if fault=='mixed' else 1,(group,),(),hook.seed_key[0],(0,1,1))
    def test_same_j_secondary_improvement_retained(self):
        for method in ('flat','hier'):
            row=json.loads(self.checkpoint(method))
            initial=row['header']['initial_seed']['lex_key']
            best=row['state']['feasible_incumbent']['payload']['lex_key']
            self.assertEqual(initial[0],best[0]);self.assertLess(R(best[1]),R(initial[1]))
            resumed=self.run_search(method,previous_checkpoint=_bytes(row))
            self.assertEqual(resumed.result.key[0] if resumed.result.key else resumed.result.primary_infimum,R(best[0]))
    def test_untouched_core_result_and_action_order_parity(self):
        original=Problem.advance
        for method in ('flat','hier'):
            calls=[]
            def tracked(problem, pieces, site, effect):
                calls.append((tuple(p.pi for p in pieces),site,effect))
                return original(problem,pieces,site,effect)
            p=Problem(self.c);upper=_replay_problem(p,seed(self.c))[0]
            with patch.object(Problem,'advance',tracked):
                baseline=(_solve_problem(p,verified_primary_upper=upper) if method=='flat' else
                    _solve_hierarchical_problem(p,True,build_regions(p.sites),verified_primary_upper=upper).bounded)
                expected=list(calls);calls.clear()
                # Seed construction has advance calls; supply a prebuilt witness
                # and compare only calls made by the exact search instance.
            with patch.object(Problem,'advance',tracked):
                actual=self.run_search(method)
            self.assertEqual(actual.canonical(),baseline.canonical())
            # The first call in run_search builds its initial witness.
            self.assertEqual(calls[1:],expected)
    def test_abrupt_kill_before_and_after_atomic_rename(self):
        old=self.checkpoint(depth=0);new=self.checkpoint(depth=1)
        for after in (False,True):
            path=self.base/('abrupt-'+str(after)+'.json');path.write_bytes(old)
            process=multiprocessing.get_context('fork').Process(target=killed_atomic,args=(str(path),new,after))
            process.start();process.join(5)
            if process.is_alive():process.kill();process.join();self.fail('atomic tiny test exceeded limit')
            self.assertEqual(process.exitcode,77)
            self.assertEqual(path.read_bytes(),new if after else old)
            recovered=self.run_search('flat',previous_checkpoint=path.read_bytes())
            self.assertEqual(recovered.canonical(),self.run_search('flat').canonical())
    def test_pre_rename_failure_preserves_last_layer(self):
        hook=self.envelope();p=hook.problem
        hook(0,((p.initial_piece(),),),(),hook.seed_key[0],(0,1,1));old=hook.path.read_bytes()
        groups=(p.advance((p.initial_piece(),),'s','CS'),)
        with patch('timecut5.layer_envelope.os.replace',side_effect=OSError('disk')):
            with self.assertRaises(OSError):hook(1,groups,(),hook.seed_key[0],(1,2,1))
        self.assertEqual(hook.path.read_bytes(),old)
        self.assertTrue(hook.failed)
        with self.assertRaises(RuntimeError):hook(1,groups,(),hook.seed_key[0],(1,2,1))
    def test_post_rename_directory_sync_failure_is_not_success(self):
        hook=self.envelope();p=hook.problem
        import os
        original=os.fsync;calls=[]
        def fail_directory(fd):
            calls.append(fd)
            if len(calls)==2:raise OSError('directory fsync')
            original(fd)
        with patch('timecut5.layer_envelope.os.fsync',side_effect=fail_directory):
            with self.assertRaises(OSError):hook(0,((p.initial_piece(),),),(),hook.seed_key[0],(0,1,1))
        self.assertTrue(hook.path.exists());self.assertTrue(hook.failed)
        row=json.loads(hook.path.read_bytes())
        self.assertEqual(row['history'][-1],_hash(row['state']))
    def test_replay_cannot_finish_or_stop_before_saved_depth(self):
        data=self.checkpoint()
        with self.assertRaisesRegex(ValueError,'Cannot stop'):
            self.run_search('flat',previous_checkpoint=data,stop_after_depth=0)
        row=json.loads(data);row['history'].append(row['history'][-1])
        with self.assertRaises(ValueError):self.run_search('flat',previous_checkpoint=_bytes(row))

if __name__=='__main__':unittest.main()
