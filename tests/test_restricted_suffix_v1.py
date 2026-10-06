"""Tiny numerical unit cases; never runs the frozen TRACE01 query pilot."""
from copy import deepcopy
from fractions import Fraction as F
from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from timecut5.bounded import Problem
from timecut5.probe import Interval
from timecut5.provenance import Recorder,restrict
from validation.family5 import verify_bundle
from validation.suffix5.model import build_model
from validation.suffix5.solver import solve_model,solution_point,SolveBudget
from validation.suffix5.witness import lift_point,result_contract
from validation.suffix5.checker import check_regime
from validation.suffix5.witness_checker import verify_witness
from validation.suffix5.evidence import check_result_witness,check_query_witness


def tiny_case(name='attained'):
    case=dict(case_id='UNIT_SUFFIX_'+name,H_ref=1,origin='o',destination='z',start_time_s=0,
              initial_energy_kwh=1,capacity_kwh=4,minimum_energy_kwh=0,reserve_kwh=0,
              consumption_kwh_per_m=1,overhead_s=1,lambda_stop_s=0,schedule=None,
              sites={'c':['C']},charging_segments=[[0,4,2,0]],
              edges=[dict(source='o',target='c',time_s=1,length_m=1),
                     dict(source='c',target='z',time_s=1,length_m=2)])
    if name in ('primary_open','secondary_open','inverted_window'):
        case.update(initial_energy_kwh=4,capacity_kwh=5,charging_segments=[[0,5,2,0]])
        case['edges'][1]['length_m']=1
    if name in ('secondary_open','inverted_window'):
        case.update(schedule={'a':10,'b':9 if name=='inverted_window' else 10,'D':1},sites={'c':['C','S','CS']})
    if name=='closed_empty':case['edges'][0]['length_m']=6
    if name=='strict_empty':
        case.update(origin='c',initial_energy_kwh=4)
        case['edges']=[dict(source='c',target='z',time_s=1,length_m=1)]
    if name=='graph_empty':
        case['edges']=[dict(source='o',target='z',time_s=1,length_m=1),dict(source='c',target='z',time_s=1,length_m=1)]
    return case


def initial_context(case):
    with Recorder() as recorder:
        piece=Problem(case).initial_piece();bundle=recorder.export((piece,))
    return verify_bundle(bundle,case),piece._family.node_id


def inherited_context(kind):
    case=tiny_case('inherited_'+kind)
    case.update(H_ref=4,initial_energy_kwh=2,capacity_kwh=5,charging_segments=[[0,5,1,0]],
                sites={'c':['C','S','CS']},schedule={'a':10,'b':10,'D':1},reserve_kwh=4 if kind=='time_open' else 0)
    case['edges'][1]['length_m']=1
    with Recorder() as recorder:
        problem=Problem(case);pieces=problem.advance((problem.initial_piece(),),'c','C')
        if kind=='time_open':
            pieces=problem.advance(pieces,'c','S');pieces=problem.advance(pieces,'c','C')
            piece=next(p for p in pieces if p.domain.contains(F(3)))
            piece=restrict(piece,Interval(3,3),'physical open-time test')
            if piece.chi:raise RuntimeError('physical open-time fixture did not produce an open cut')
        else:
            piece=next(p for p in pieces if p.domain.contains(F(3,2)))
            piece=restrict(piece,Interval(1,2,False,True),'physical open-energy test')
        bundle=recorder.export((piece,))
    return verify_bundle(bundle,case),piece._family.node_id


def foreign_context():
    case=tiny_case('foreign_ancestry');case.update(H_ref=4,initial_energy_kwh=2,capacity_kwh=5,charging_segments=[[0,5,1,0]])
    case['edges'][1]['length_m']=1
    with Recorder() as recorder:
        p=Problem(case);first=p.advance((p.initial_piece(),),'c','C');roots=[]
        for domain in (Interval(1,F(3,2),False,False),Interval(2,F(5,2),False,False)):
            selected=tuple(restrict(x,d,'ancestral charge guard') for x in first if (d:=x.domain.intersect(domain)) is not None)
            second=p.advance(selected,'c','C');source=next(x for x in second if x.domain.contains(F(3)))
            roots.append(restrict(source,Interval(3,3),'fixed common final energy'))
        bundle=recorder.export(roots)
    return verify_bundle(bundle,case),[p._family.node_id for p in roots]


class RestrictedSuffixNumerics(unittest.TestCase):
    def solve(self,ctx,ident,word):
        model=build_model(ctx,ident,word);budget=SolveBudget(max_passes=12,wall_seconds=30,rss_mib=256)
        record=solve_model(model,budget)
        self.assertLessEqual(budget.passes,6)
        self.assertEqual(check_regime(ctx,record),record['result'])
        if record['result']['status'] in ('attained_optimum','primary_unattained','secondary_unattained'):
            epsilon=F(1,10**30)
            evidence=lift_point(ctx,record['model'],solution_point(record,epsilon))
            check_result_witness(ctx,record,evidence,result_contract(record['result'],epsilon))
        return record

    def test_attained_primary_secondary_and_full_key(self):
        ctx,ident=initial_context(tiny_case())
        record=self.solve(ctx,ident,[['c','C']]);result=record['result']
        self.assertEqual(result,dict(status='attained_optimum',J='7',Q_total='2',H=1,site_action_tuple=[['c','C']],lex_key=['7','2',1,[['c','C']]]))
        evidence=lift_point(ctx,record['model'],solution_point(record))
        self.assertEqual(evidence['witness']['time'],'7')

    def test_primary_and_secondary_nonattainment(self):
        for name,effect,expected in [('primary_open','C',dict(status='primary_unattained',primary_infimum='3')),
                                     ('secondary_open','CS',dict(status='secondary_unattained',J='12',secondary_infimum='0'))]:
            with self.subTest(name=name):
                ctx,ident=initial_context(tiny_case(name));record=self.solve(ctx,ident,[['c',effect]])
                self.assertEqual(record['result'],expected)
                evidence=lift_point(ctx,record['model'],solution_point(record,F(1,10**40)))
                if name=='primary_open':self.assertTrue(3<F(evidence['witness']['time'])<3+F(1,10**40))
                else:
                    self.assertEqual(evidence['witness']['time'],'12')
                    q=F(evidence['witness']['energy'])+F(evidence['witness']['rho'])
                    self.assertTrue(0<q<F(1,10**40))

    def test_graph_closed_and_strict_empty_are_distinct(self):
        for name,status in [('graph_empty','graph_unreachable'),('closed_empty','closed_infeasible'),('strict_empty','strict_infeasible'),('inverted_window','closed_infeasible')]:
            with self.subTest(name=name):
                ctx,ident=initial_context(tiny_case(name));effect='S' if name=='inverted_window' else 'C'
                record=self.solve(ctx,ident,[['c',effect]])
                self.assertEqual(record['result'],dict(status=status))
                if name=='graph_empty':self.assertEqual(record['stages'],[])
                with self.assertRaises(ValueError):solution_point(record)

    def test_physical_open_energy_controls_secondary_attainment(self):
        ctx,ident=inherited_context('energy_open');record=self.solve(ctx,ident,[['c','S']])
        self.assertEqual(record['result'],dict(status='secondary_unattained',J='12',secondary_infimum='0'))
        evidence=lift_point(ctx,record['model'],solution_point(record,F(1,10**30)))
        self.assertTrue(F(evidence['prefix']['witness']['energy'])>1)
        self.assertEqual(evidence['witness']['time'],'12')

    def test_physical_open_time_controls_primary_attainment(self):
        ctx,ident=inherited_context('time_open');record=self.solve(ctx,ident,[['c','C']])
        self.assertEqual(record['result'],dict(status='primary_unattained',primary_infimum='16'))
        evidence=lift_point(ctx,record['model'],solution_point(record,F(1,10**30)))
        self.assertTrue(12<F(evidence['prefix']['witness']['time'])<12+F(1,10**30))
        self.assertTrue(16<F(evidence['witness']['time'])<16+F(1,10**30))

    def test_same_scalar_cut_keeps_original_prefix_family(self):
        ctx,ids=foreign_context();observed=[]
        for ident in ids:
            record=self.solve(ctx,ident,[['c','C']]);self.assertEqual(record['result'],dict(status='primary_unattained',primary_infimum='7'))
            observed.append(lift_point(ctx,record['model'],solution_point(record,F(1,100))))
        ea=F(observed[0]['prefix']['witness']['events'][2]['departure_energy'])
        eb=F(observed[1]['prefix']['witness']['events'][2]['departure_energy'])
        self.assertTrue(1<ea<F(3,2));self.assertTrue(2<eb<F(5,2))




class RestrictedSuffixLedgerAndTampering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from timecut5.hierarchy import solve_hierarchical
        from timecut5.invocation_trace import InvocationTrace
        from validation.trace5 import verify_trace
        cls.case=tiny_case()
        with Recorder() as recorder,InvocationTrace(recorder) as trace:
            solve_hierarchical(cls.case)
        stream=trace.export();bundle=recorder.export()
        bundle['roots']=stream['events'][-1]['payload']['terminal_families']
        cls.checked=verify_trace(stream,bundle,cls.case)
        cls.sequence=next(q['query_seq'] for q in cls.checked.export_queries() if q['effect']=='C')
        from validation.suffix5.query import solve_query
        cls.ledger=solve_query(cls.checked,cls.sequence)
        cls.record=cls.ledger['models'][0]

    def test_complete_public_query_ledger(self):
        from validation.suffix5.checker import check_query_ledger
        audit=check_query_ledger(self.checked,self.ledger,with_audit=True)
        self.assertEqual(audit['result'],self.ledger['result'])
        self.assertTrue(audit['audit']['bound_valid'])
        self.assertEqual(audit['audit']['regime_count'],1)

    def test_missing_duplicate_foreign_and_wrong_query_ledger(self):
        from validation.suffix5.checker import check_query_ledger
        for mode in ('missing','duplicate','foreign_word','wrong_query','fake_result','bool_query'):
            with self.subTest(mode=mode):
                ledger=deepcopy(self.ledger)
                if mode=='missing':ledger['models']=[]
                elif mode=='duplicate':ledger['models']*=2
                elif mode=='foreign_word':ledger['models'][0]['model']['word']=[['missing','C']]
                elif mode=='wrong_query':ledger['query_sha256']='0'*64
                elif mode=='bool_query':ledger['query_seq']=True
                else:ledger['result']['J']='0'
                with self.assertRaises(ValueError):check_query_ledger(self.checked,ledger)

    def test_matrix_strictness_stage_dual_and_type_mutations(self):
        for mode in ('matrix','strict','objective','dual','stage','result','coefficient_type','verified_bool'):
            with self.subTest(mode=mode):
                record=deepcopy(self.record)
                if mode=='matrix':record['model']['lp']['rows'][0]['rhs']='999'
                elif mode=='strict':record['model']['lp']['rows'][0]['strict']=1
                elif mode=='objective':record['model']['lp']['J']['constant']='999'
                elif mode=='dual':record['stages'][0]['certificate']['inequality_dual'][0]='1'
                elif mode=='stage':record['stages'].pop(2)
                elif mode=='result':record['result']['J']='0'
                elif mode=='coefficient_type':record['stages'][0]['task']['A'][0][0]=-1
                else:record['stages'][0]['certificate']['exact_primal_dual_verified']=1
                with self.assertRaises(ValueError):check_regime(self.checked.bundle,record)

    def test_contract_cannot_relabel_an_approach_as_minimum(self):
        ctx,ident=initial_context(tiny_case('primary_open'))
        record=solve_model(build_model(ctx,ident,[['c','C']]))
        evidence=lift_point(ctx,record['model'],solution_point(record,F(1,100)))
        w=evidence['witness'];Q=F(w['energy'])+F(w['rho'])
        contract=dict(kind='minimum',J=w['time'],Q_total=str(Q),H=1,pi=[['c','C']])
        verify_witness(ctx,ident,[['c','C']],evidence,contract)
        with self.assertRaises(ValueError):check_result_witness(ctx,record,evidence,contract)
        contract=result_contract(record['result'],F(1,100));contract['J_inf']='0'
        with self.assertRaises(ValueError):check_result_witness(ctx,record,evidence,contract)

    def test_query_witness_binds_original_slot_and_result(self):
        record=self.ledger['models'][0]
        evidence=lift_point(self.checked.bundle,record['model'],solution_point(record))
        contract=result_contract(record['result'])
        check_query_witness(self.checked,self.ledger,0,evidence,contract)
        with self.assertRaises(ValueError):check_query_witness(self.checked,self.ledger,False,evidence,contract)
        contract=deepcopy(contract);contract['J']='999'
        with self.assertRaises(ValueError):check_query_witness(self.checked,self.ledger,0,evidence,contract)

    def test_budget_failure_keeps_query_unresolved(self):
        from validation.suffix5.query import solve_query,UnresolvedQuery
        budget=SolveBudget(max_passes=1)
        with self.assertRaises(UnresolvedQuery) as raised:solve_query(self.checked,self.sequence,budget)
        self.assertEqual(raised.exception.failed_slot,0)
        self.assertEqual(raised.exception.partial_records,[])
        self.assertEqual(len(raised.exception.planned_models),1)
        self.assertEqual(raised.exception.failed_regime['status'],'unresolved')
        self.assertEqual([stage['name'] for stage in raised.exception.failed_regime['stages']],['feasibility'])
        self.assertNotIn('empty',str(raised.exception).lower())

    def test_nonfinite_and_boolean_budgets_rejected(self):
        for kwargs in ({'max_passes':True},{'wall_seconds':float('nan')},{'rss_mib':float('inf')},{'wall_seconds':False}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):SolveBudget(**kwargs)

    def test_forced_uncertified_lp_is_unresolved_not_infeasible(self):
        from unittest.mock import patch
        from validation.suffix5.query import solve_query,UnresolvedQuery
        from validation.suffix5.vendor_lp import UncertifiedLP
        with patch('validation.suffix5.vendor_lp.exact_lp',side_effect=UncertifiedLP('deliberately uncertified')):
            with self.assertRaises(UnresolvedQuery) as raised:solve_query(self.checked,self.sequence)
        self.assertEqual(raised.exception.partial_records,[])
        self.assertIn('uncertified',str(raised.exception))

    def test_resource_caps_and_pass_count_are_enforced(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from validation.suffix5.solver import BudgetExceeded
        budget=SolveBudget(max_passes=1)
        budget.tick()
        with self.assertRaises(BudgetExceeded):budget.tick()
        self.assertEqual(budget.passes,1)
        budget=SolveBudget()
        with patch('validation.suffix5.solver.time.monotonic',return_value=budget.started+121):
            with self.assertRaises(BudgetExceeded):budget.check()
        with patch('validation.suffix5.solver.resource.getrusage',return_value=SimpleNamespace(ru_maxrss=257*1024)):
            with self.assertRaises(BudgetExceeded):budget.check()

    def test_candidate_calls_receive_remaining_wall_limit(self):
        from unittest.mock import patch
        from validation.suffix5 import vendor_lp
        original=vendor_lp.linprog;observed=[]
        def observe(*args,**kwargs):
            observed.append(kwargs['options']['time_limit'])
            return original(*args,**kwargs)
        budget=SolveBudget()
        with patch.object(vendor_lp,'linprog',observe):solve_model(self.record['model'],budget)
        self.assertEqual(budget.passes,len(observed))
        self.assertTrue(all(0<limit<=120 for limit in observed))
        self.assertTrue(all(a>=b for a,b in zip(observed,observed[1:])))

if __name__=='__main__':unittest.main()
