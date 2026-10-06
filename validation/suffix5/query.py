"""Candidate query ledger; failures preserve partial evidence as unresolved."""
from fractions import Fraction as F
from validation.family5.checker import digest
from .model import query_models
from .solver import solve_model,SolveBudget,UnresolvedRegime


class UnresolvedQuery(ArithmeticError):
    def __init__(self,message,query_seq,failed_slot,models,partial_records,failed_regime):
        super().__init__(message)
        self.query_seq=query_seq;self.failed_slot=failed_slot
        self.planned_models=models;self.partial_records=partial_records;self.failed_regime=failed_regime


def aggregate(records):
    values=[r['result'] for r in records]
    active=[r for r in values if r['status'] not in ('graph_unreachable','closed_infeasible','strict_infeasible')]
    if not active:return dict(status='empty_restricted_family')
    def J(r):return F(r['primary_infimum'] if r['status']=='primary_unattained' else r['J'])
    first=min(map(J,active));face=[r for r in active if J(r)==first and r['status']!='primary_unattained']
    if not face:return dict(status='primary_unattained',primary_infimum=str(first))
    def Q(r):return F(r['secondary_infimum'] if r['status']=='secondary_unattained' else r['Q_total'])
    second=min(map(Q,face));attained=[r for r in face if Q(r)==second and r['status']=='attained_optimum']
    if not attained:return dict(status='secondary_unattained',J=str(first),secondary_infimum=str(second))
    return min(attained,key=lambda r:(r['H'],tuple(map(tuple,r['site_action_tuple'])))).copy()


def solve_query(checked_trace,query_seq,budget=None,on_record=None,on_stage=None):
    budget=budget or SolveBudget();query,models=query_models(checked_trace,query_seq);records=[]
    def indexed_stage(index,stage):on_stage(index,stage)
    for index,model in enumerate(models):
        try:record=solve_model(model,budget,on_stage=(lambda stage:indexed_stage(index,stage)) if on_stage is not None else None)
        except UnresolvedRegime as error:
            raise UnresolvedQuery(str(error),query_seq,index,models,records,error.partial_record) from error
        records.append(record)
        if on_record is not None:on_record(index,record)
    return dict(schema='family5-suffix-query-ledger-v1',query_seq=query_seq,query_sha256=digest(query),
                trace_sha256=checked_trace.summary['trace_sha256'],models=records,result=aggregate(records))
