"""Conditional proof, guards and tiny physical/native checks; no real-road run."""
from copy import deepcopy
from dataclasses import asdict, replace
from fractions import Fraction as F
from itertools import product
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from timecut5.bounded import Problem, _solve_problem, _replay_problem, _groups
from timecut5.hierarchy import _solve_hierarchical_problem, build_regions
from timecut5.pending_window_dominance import (VERSION, make_pending_window_reducer,
    PendingWindowDominanceStatistics)
from timecut5.post_service_dominance import make_post_service_reducer, PostServiceDominanceStatistics
from timecut5.probe import Cut, Event, Interval, State, Witness, reduce_cuts, terminal
from timecut5.pwa import CutPiece, _arrangement, charge_pwa, reduce_frontier_skyline
from timecut5.provenance import Recorder, signature
from timecut5.real_adapter import RealProblem
from timecut5.real_legs import ImmutableLegTable

ROOT = Path(__file__).resolve().parents[1]


def case():
    return dict(H_ref=3, origin='o', destination='z', start_time_s=0,
        initial_energy_kwh=1, capacity_kwh=4, minimum_energy_kwh=0,
        reserve_kwh=0, consumption_kwh_per_m=1, overhead_s=1,
        lambda_stop_s=0, schedule=dict(a=7, b=20, D=1),
        sites={'a':['C'], 'b':['C'], 'x':['C','S','CS']},
        charging_segments=[[0,4,1,0]],
        edges=[dict(source=s,target=t,time_s=time,length_m=energy)
               for s,t,time,energy in [('o','a','1/2',1),('a','x','1/2',1),
                   ('o','b','3/2','1/2'),('b','x','3/2','1/2'),('x','z',1,'1/2')]])


def seed(domain=None, *, slope=0, intercept=0, chi=True, rho=0, name='a',
         state=None, pi=None, seen=None):
    domain = domain or Interval(0,4)
    state = state or State('x',1,2)
    pi = pi if pi is not None else ((name,'C'),('x','C'))
    slope, intercept, rho = F(slope), F(intercept), F(rho)
    def point(energy):
        if not domain.contains(energy):
            raise AssertionError('Callback escaped inherited domain')
        if seen is not None:
            seen.append(energy)
        tau = slope*energy+intercept
        def approach(epsilon):
            time = tau if chi else tau+min(F(1),epsilon/2)
            return Witness(time,energy,rho,pi,state,
                (Event('analytic',name,time,time,energy,energy),))
        return Cut(tau,chi,energy,rho,pi,state,approach)
    return CutPiece(domain,slope,intercept,chi,rho,pi,state,point)


def policy(problem=None, **kwargs):
    return make_pending_window_reducer(problem or Problem(case()), enabled=True,
        completed_departure_layers=True, **kwargs)


def canonical(result):
    r = result.canonical()['result']
    if r['status']=='attained_optimum':
        return r['status'],r['J'],r['Q_total'],r['H'],tuple(map(tuple,r['site_action_tuple']))
    if r['status']=='primary_unattained':
        return r['status'],r['primary_infimum']
    if r['status']=='secondary_unattained':
        return r['status'],r['J'],r['secondary_infimum']
    return (r['status'],)


def consistent(test, reducer):
    s = reducer.snapshot()
    test.assertIs(type(s),PendingWindowDominanceStatistics)
    test.assertTrue(all(type(v) is int and v>=0 for k,v in asdict(s).items()
                        if k not in ('enabled','post_service_enabled')))
    test.assertEqual(s.calls,s.strong_calls+s.disabled_fallback_calls+
        s.recorded_fallback_calls+s.phase_fallback_calls+s.unsupported_fallback_calls)
    test.assertEqual(s.candidate_visits,s.product_discarded+s.late_primary_discarded+s.kept_candidate_visits)
    old = reducer.post_service_snapshot()
    test.assertIs(type(old),PostServiceDominanceStatistics)
    test.assertEqual(old.enabled,s.post_service_enabled)
    test.assertEqual(old.calls,s.calls-s.strong_calls)


class PointAndArrangementTests(unittest.TestCase):
    def test_defaults_explicit_features_and_separate_counters(self):
        p = Problem(case())
        pre = (seed(intercept=5,rho=2),seed(intercept=7,name='b'))
        for pending,post in product((False,True),repeat=2):
            r = make_pending_window_reducer(p,enabled=pending,post_service_enabled=post,
                completed_departure_layers=True)
            if not pending:
                self.assertEqual(tuple(map(signature,r(pre))),tuple(map(signature,reduce_frontier_skyline(pre))))
            else:
                self.assertEqual(len(r(pre)),1)
            postpieces = tuple(replace(q,state=State('x',0,2),pi=(('a','C'),('x','S')),
                _point=lambda e,q=q:replace(q.at(e),state=State('x',0,2),pi=(('a','C'),('x','S')))) for q in pre)
            expected = make_post_service_reducer(p,enabled=post,completed_departure_layers=True)(postpieces)
            self.assertEqual(tuple(map(signature,r(postpieces))),tuple(map(signature,expected)))
            consistent(self,r)
        r = make_pending_window_reducer(p)
        r(pre)
        self.assertEqual(r.snapshot().disabled_fallback_calls,1)
        self.assertFalse(r.post_service_snapshot().enabled)
        with self.assertRaisesRegex(ValueError,'completed-departure'):
            make_pending_window_reducer(p,enabled=True)
        with self.assertRaisesRegex(ValueError,'completed-departure'):
            make_pending_window_reducer(p,post_service_enabled=True)
        for kwargs in (dict(enabled=1),dict(post_service_enabled=1),dict(completed_departure_layers=1)):
            with self.assertRaises(TypeError):make_pending_window_reducer(p,**kwargs)

    def test_exhaustive_point_rule_matches_product_then_late_filter(self):
        p = Problem(case());r=policy(p)
        choices = [seed(Interval(1,1),intercept=t,chi=chi,rho=rho,name=name)
                   for t,chi,rho,name in product((5,6,7),(False,True),(0,1),('a','b'))]
        for pa,pb in product(choices,repeat=2):
            points = (pa.at(F(1)),pb.at(F(1)))
            skyline = reduce_cuts(points)
            minimum = min((c.tau,not c.chi) for c in points)
            expected = [c for c in skyline if not ((c.tau>6 or c.tau==6 and not c.chi)
                        and (c.tau,not c.chi)>minimum)]
            out = r((pa,pb))
            self.assertEqual([(q.intercept,q.chi,q.rho,q.pi) for q in out],
                             [(c.tau,c.chi,c.rho,c.pi) for c in expected])
            self.assertTrue(out)
        consistent(self,r)

    def test_attained_threshold_stays_and_open_threshold_can_drop(self):
        a=seed(Interval(1,1),intercept=5,rho=9,name='b')
        for attained,expected in ((True,2),(False,1)):
            b=seed(Interval(1,1),intercept=6,chi=attained,name='a')
            self.assertEqual(len(policy()((a,b))),expected)
        # Primary equality alone does not allow worse-secondary deletion.
        self.assertEqual(len(policy()((seed(intercept=7,rho=2),seed(intercept=7,name='b')))),1)

    def test_missing_threshold_knots_are_mandatory_physical_regression(self):
        p=Problem(case());front=[]
        for name in ('a','b'):
            q=p.advance((p.initial_piece(),),name,'C')
            front.extend(p.advance(q,'x','C'))
        self.assertTrue(front)
        r=policy(p);out=r(front)
        for energy,keep_b in ((F(1,2),True),(F(1),True),(F(3,2),False)):
            self.assertEqual(any(q.pi[0][0]=='b' and q.domain.contains(energy) for q in out),keep_b)
        def complete(pieces):
            done=[]
            for group in _groups(pieces):
                done.extend(p.finish(p.advance(group,'x','S')))
            return terminal(done,p.destination,p.reserve,p.start,p.penalty)
        original,new=complete(front),complete(out)
        self.assertEqual(new.key,original.key)
        self.assertEqual(new.key[:3],(F(9),F(1,2),3))
        self.assertEqual(_replay_problem(p,new.witness),new.key)
        # Reproduce the old-arrangement-only bug on the actual two affine families.
        a=seed(Interval(0,4,False,True),slope=1,intercept=4,rho=1)
        b=seed(Interval(0,4,False,True),slope=1,intercept=5,name='b')
        bad=[]
        for cell in _arrangement((a,b)):
            e=(cell.lo+cell.hi)/2;active=[q for q in (a,b) if q.domain.contains(e)]
            cuts=[q.at(e) for q in active]
            if not cuts:continue
            minimum=min((c.tau,not c.chi) for c in cuts)
            for q,c in zip(active,cuts):
                if not ((c.tau>6 or c.tau==6 and not c.chi) and (c.tau,not c.chi)>minimum):
                    bad.append(replace(q,domain=cell))
        self.assertFalse(any(q.pi[0][0]=='b' for q in bad))
        self.assertGreater(r.snapshot().added_threshold_knots,0)
        consistent(self,r)

    def test_threshold_singleton_crossings_and_parent_callbacks(self):
        seen=[]
        a=seed(Interval(0,4,False,True),slope=1,intercept=4,rho=2,seen=seen)
        b=seed(Interval(0,4,False,True),slope=1,intercept=5,name='b',seen=seen)
        out=policy()((a,b))
        for q in out:
            parent=a if q.pi==a.pi else b
            self.assertIs(q._point,parent._point)
            e=(q.domain.lo+q.domain.hi)/2
            for eps in (F(1),F(1,10**80)):q.at(e).approach(eps)
        self.assertTrue(seen)
        # A genuinely missing knot cannot be reintroduced by connected joining.
        l=seed(Interval(0,1,False,False),intercept=7)
        u=seed(Interval(1,2,False,False),intercept=7)
        result=policy()((l,u))
        self.assertFalse(any(q.domain.contains(F(1)) for q in result))
        self.assertEqual([q.domain for q in result],[l.domain,u.domain])
        a=seed(slope=1,intercept=6,rho=2)
        b=seed(slope=-1,intercept=10,name='b')
        out=policy()((a,b))
        self.assertTrue(any(q.domain.contains(F(2)) and q.pi==b.pi for q in out))

    def test_joining_requires_identical_original_parent(self):
        winner=seed(intercept=7)
        a=seed(slope=1,intercept=10,rho=2)
        b=seed(slope=-1,intercept=14,rho=2,name='b')
        r=policy();out=r((winner,a,b))
        self.assertEqual(len(out),1)
        self.assertIs(out[0]._point,winner._point)
        self.assertEqual(out[0].domain,winner.domain)
        self.assertGreater(r.snapshot().parent_run_coalesces,0)
        isolated=seed(Interval(1,1),intercept=6,name='b')
        out=policy()((winner,isolated))
        self.assertEqual(len(out),3)
        self.assertFalse(out[0].domain.right_closed)
        self.assertFalse(out[2].domain.left_closed)

    def test_every_active_callback_validated_and_failed_counts_uncommitted(self):
        r=policy();good=seed(intercept=5)
        bad=replace(seed(intercept=8),_point=lambda e:(_ for _ in ()).throw(ValueError('bad inherited cut')))
        with self.assertRaisesRegex(ValueError,'bad inherited cut'):r((good,bad))
        self.assertEqual(r.snapshot().calls,0)
        self.assertEqual(r.post_service_snapshot().calls,0)

    def test_future_projection_keeps_restricted_parent_and_tiny_epsilons(self):
        p=Problem(case());seen=[]
        a=seed(Interval(F(1,4),F(3,4),False,False),slope=3,intercept=7,seen=seen)
        out=policy(p)((a,))
        for q in charge_pwa(out,p.curve,p.overhead,'x'):
            e=(q.domain.lo+q.domain.hi)/2
            for eps in (F(1),F(1,10**60)):
                w=q.at(e).approach(eps)
                self.assertTrue(a.domain.contains(w.events[0].arrival_energy))
                self.assertGreater(w.events[-1].departure_energy,w.events[-1].arrival_energy)
        self.assertTrue(seen)
        self.assertTrue(all(a.domain.contains(e) for e in seen))


class GuardAndFallbackTests(unittest.TestCase):
    def test_mutated_model_bound_owner_method_and_unsupported_subclass(self):
        class Extended(Problem):pass
        with self.assertRaises(TypeError):policy(Extended(case()))
        for change in ('bound','case','owner','leg','method'):
            p=Problem(case());r=policy(p)
            if change=='bound':p.bound+=1
            elif change=='case':p.case['overhead_s']=2
            elif change=='owner':p.site_anchors=dict(p.site_anchors)
            elif change=='leg':
                pair=next(iter(p.legs));p.legs[pair]=replace(p.legs[pair],time=p.legs[pair].time+1)
            else:p.advance=lambda *args:()
            with self.subTest(change=change),self.assertRaises((ValueError,TypeError)):r((seed(),))
            self.assertEqual(r.snapshot().calls,0)

    def test_same_state_energy_history_departure_and_exact_type_guards(self):
        p=Problem(case());r=policy(p)
        for bad in (seed(state=State('a',1,2)),seed(Interval(0,5)),
                    seed(pi=(('a','S'),('x','C'))),seed(pi=(('missing','C'),('x','C')))):
            with self.assertRaises((ValueError,TypeError)):r((seed(),bad))
        bad=seed();object.__setattr__(bad,'chi',1)
        with self.assertRaises((ValueError,TypeError)):r((bad,))
        bad=seed(state=State('a',1,2))
        with self.assertRaisesRegex(ValueError,'physical departure'):r((bad,))
        initial=(p.initial_piece(),)
        self.assertTrue(r(initial))
        consistent(self,r)
        self.assertEqual(r(()),())
        self.assertEqual(r.snapshot().phase_fallback_calls,1)

    def test_active_recorder_and_inherited_family_keep_historical_semantics(self):
        from validation.family5 import verify_bundle
        p=Problem(case());r=policy(p,post_service_enabled=True)
        with Recorder() as recorder:
            solved=_solve_problem(p,True,reducer=r)
            bundle=recorder.export()
        self.assertTrue(verify_bundle(bundle,p.case).summary['verified'])
        self.assertIsNotNone(solved.result.key)
        self.assertGreater(r.snapshot().recorded_fallback_calls,0)
        self.assertEqual(r.snapshot().strong_calls,0)
        self.assertEqual(r.post_service_snapshot().strong_calls,0)
        consistent(self,r)
        with Recorder():pieces=p.advance((p.initial_piece(),),'a','C')
        before=r.snapshot().calls
        with self.assertRaisesRegex(ValueError,'Recorder context'):r(pieces)
        self.assertEqual(r.snapshot().calls,before)
        self.assertTrue(all(q._family is not None for q in pieces))


class SolverDifferentialTests(unittest.TestCase):
    def test_physical_tiny_S_CS_latest_start_and_both_engines(self):
        variants=[]
        for effects,a,b,d in ((['S'],7,20,1),(['CS'],0,20,1),(['S','CS'],7,7,0),(['S'],0,1,0)):
            q=case();q['sites']['x']=['C']+effects;q['schedule']=dict(a=a,b=b,D=d)
            variants.append(q)
        strong=deleted=0
        for source,hier,pending,post in product(variants,(False,True),(False,True),(False,True)):
            p=Problem(source);r=make_pending_window_reducer(p,enabled=pending,post_service_enabled=post,
                completed_departure_layers=True)
            result=(_solve_hierarchical_problem(p,True,build_regions(p.sites),reducer=r).bounded
                    if hier else _solve_problem(p,True,reducer=r))
            baseline=(_solve_hierarchical_problem(Problem(source),True,build_regions(p.sites)).bounded
                      if hier else _solve_problem(Problem(source),True))
            self.assertEqual(canonical(result),canonical(baseline))
            if result.result.witness is not None:
                self.assertEqual(_replay_problem(Problem(source),result.result.witness),result.result.key)
            strong+=r.snapshot().strong_calls;deleted+=r.snapshot().late_primary_discarded
            consistent(self,r)
        self.assertGreater(strong,0);self.assertGreater(deleted,0)

    def test_frozen_eighteen_synthetic_cases_all_terminal_statuses(self):
        cases=json.loads((ROOT/'tests/fixtures/milestone_5_reference/frozen_cases_v2.json').read_text())
        statuses=set()
        for source,hier in product(cases,(False,True)):
            answers=[]
            for pending in (False,True):
                p=Problem(source);r=make_pending_window_reducer(p,enabled=pending,
                    post_service_enabled=True,completed_departure_layers=True)
                solved=(_solve_hierarchical_problem(p,True,build_regions(p.sites),reducer=r).bounded
                        if hier else _solve_problem(p,True,reducer=r))
                answers.append(canonical(solved));statuses.add(solved.canonical()['result']['status'])
                if solved.result.witness is not None:
                    self.assertEqual(_replay_problem(Problem(source),solved.result.witness),solved.result.key)
                consistent(self,r)
            self.assertEqual(*answers,(source['case_id'],hier))
        self.assertEqual(len(statuses),4)

    def test_five_mock_alias_cases_and_fresh_immutable_replay(self):
        rows=json.loads((ROOT/'tests/fixtures/milestone_5_real_leg_contract/mock_solver_cases.json').read_text())
        for row,hier in product(rows,(False,True)):
            data=json.dumps(row['table'],sort_keys=True,separators=(',',':')).encode()
            table=ImmutableLegTable.from_bytes(data,row['table_sha256']);answers=[]
            for enabled in (False,True):
                p=RealProblem(row['query'],table)
                r=make_pending_window_reducer(p,enabled=enabled,post_service_enabled=True,
                    completed_departure_layers=True)
                solved=(_solve_hierarchical_problem(p,True,build_regions(p.sites),reducer=r).bounded
                        if hier else _solve_problem(p,True,reducer=r))
                answers.append(canonical(solved))
                if solved.result.witness is not None:
                    self.assertEqual(_replay_problem(RealProblem(row['query'],table),solved.result.witness),solved.result.key)
                consistent(self,r)
            self.assertEqual(*answers,row['case_id'])


class NativeAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.terminal_energy import test_energy as fixture
        fixture.EnergyTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        from tests.terminal_energy import test_energy as fixture
        fixture.EnergyTests.tearDownClass.__func__(cls)

    def directory(self):
        from tests.terminal_energy import test_energy as fixture
        return fixture.EnergyTests.directory(self)

    def context(self,**kwargs):
        from tests.terminal_energy import test_combined_target_energy as fixture
        return fixture.CombinedTargetEnergyTests.context(self,**kwargs)

    def make(self,mode='full'):
        from tests.terminal_energy import test_energy as fixture
        from timecut5.real_legs import RealSite
        from timecut5.real_adapter import site_catalog_digest
        from timecut5.remaining_charge_runtime import admit_remaining_charge_runtime
        g=fixture.graph(4,[(a,b,3.25*abs(a-b),abs(a-b)) for a in range(4) for b in range(4) if a!=b])
        context=self.context(mode=mode,g=g)
        query=dict(H_ref=2,start_time_s=0,initial_energy_kwh=2,capacity_kwh=4,
            minimum_energy_kwh=0,reserve_kwh='1/2',consumption_kwh_per_m=1,
            overhead_s=1,lambda_stop_s=1,charging_segments=[[0,4,1,0]],schedule=dict(a=5,b=100,D=1))
        sites={sid:RealSite(sid,anchor,('C','S','CS')) for sid,anchor in (('s','B'),('t','X'),('u','X'))}
        p=context.problem(query,sites,origin_anchor='A',destination_anchor='D',
            site_catalog_sha256=site_catalog_digest(sites))
        runtime=admit_remaining_charge_runtime(p,energy_screen=p._terminal_energy_screen)
        return context,p,runtime,sites

    def test_same_live_runtime_full_target_both_engines_and_fresh_replay(self):
        from timecut5.routing_config import require_full_verifier
        from timecut5.real_adapter import site_catalog_digest
        for mode,hier in product(('full','destination_target'),(False,True)):
            context,p,runtime,sites=self.make(mode)
            with self.assertRaisesRegex(ValueError,'Same live admitted'):policy(p)
            _,other,other_runtime,_=self.make(mode)
            with self.assertRaisesRegex(ValueError,'Same live admitted'):policy(p,runtime=other_runtime)
            answers=[]
            for enabled in (False,True):
                r=make_pending_window_reducer(p,enabled=enabled,post_service_enabled=True,
                    completed_departure_layers=True,runtime=runtime)
                solved=(_solve_hierarchical_problem(p,True,build_regions(p.sites),reducer=r).bounded
                        if hier else _solve_problem(p,True,reducer=r))
                answers.append(canonical(solved));consistent(self,r)
                if enabled:self.assertGreater(r.snapshot().strong_calls,0)
                self.assertEqual(p.bound,runtime.original_hmax)
                self.assertIsNotNone(solved.result.witness)
                fresh_context=self.context(mode='full',role='verification',g=context.provider.graph)
                require_full_verifier(fresh_context.provider,fresh=True)
                fresh=fresh_context.problem(p.case,sites,origin_anchor=p.origin,destination_anchor=p.destination,
                    site_catalog_sha256=site_catalog_digest(sites))
                self.assertIsNot(fresh.provider,p.provider)
                self.assertEqual(_replay_problem(fresh,solved.result.witness),solved.result.key)
            self.assertEqual(*answers,(mode,hier))

    def test_unsupported_fallback_and_owner_changes_fail_closed(self):
        _,p,runtime,_=self.make();r=policy(p,runtime=runtime)
        initial=(p.initial_piece(),)
        with patch.object(runtime,'_check',return_value=('disabled_unsupported',None,None)):
            self.assertEqual(tuple(map(signature,r(initial))),tuple(map(signature,reduce_frontier_skyline(initial))))
        self.assertEqual(r.snapshot().unsupported_fallback_calls,1)
        old=p.provider;p.provider=object()
        try:
            with self.assertRaises((ValueError,AttributeError)):r(initial)
        finally:p.provider=old
        consistent(self,r)


if __name__=='__main__':unittest.main()
