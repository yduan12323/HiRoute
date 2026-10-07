"""Candidate LP execution and exact strict/lexicographic certificate stages.

Frozen TRACE01 execution is not enabled here by default. The independent
checker, not a floating solver status, decides every acceptance claim.
"""
from fractions import Fraction as F
import math,resource,time
from threading import Lock
_solver_lock=Lock()
from .model import plain


class BudgetExceeded(RuntimeError):pass


class UnresolvedRegime(ArithmeticError):
    def __init__(self,message,model,stages):
        super().__init__(message)
        self.partial_record=dict(model=model,stages=plain(stages),status='unresolved',reason=message)



class SolveBudget:
    def __init__(self,max_passes=760,wall_seconds=120,rss_mib=256,rss_reader=None):
        if type(max_passes) is not int or max_passes<1:raise ValueError('Invalid pass cap')
        for name,value in [('wall_seconds',wall_seconds),('rss_mib',rss_mib)]:
            if type(value) not in (int,float) or not math.isfinite(value) or value<=0:
                raise ValueError('Invalid positive finite budget '+name)
        if rss_reader is not None and not callable(rss_reader):raise ValueError('Invalid RSS byte reader')
        self.max_passes=max_passes;self.wall_seconds=wall_seconds;self.rss_mib=rss_mib;self.rss_reader=rss_reader
        self.started=time.monotonic();self.passes=0
    def check(self):
        if self.passes>self.max_passes:raise BudgetExceeded('LP candidate pass cap exhausted')
        if time.monotonic()-self.started>self.wall_seconds:raise BudgetExceeded('LP wall-time cap exhausted')
        peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024 if self.rss_reader is None else self.rss_reader()
        if type(peak) is not int or peak<0:raise BudgetExceeded('Invalid LP peak RSS byte observation')
        if peak>self.rss_mib*1024**2:raise BudgetExceeded('LP peak RSS cap exhausted')
    def tick(self):
        self.check()
        if self.passes>=self.max_passes:raise BudgetExceeded('LP candidate pass cap exhausted')
        self.passes+=1
    def remaining_seconds(self):
        self.check();return max(0.000001,self.wall_seconds-(time.monotonic()-self.started))


def closed_task(model,objective,faces=()):
    lp=model['lp']
    return dict(c=list(lp[objective]['coefficients']),A=[r['coefficients'] for r in lp['rows']],
                b=[r['rhs'] for r in lp['rows']],equalities=plain(faces))


def strict_task(model,faces=()):
    rows=model['lp']['rows'];n=len(model['lp']['variables'])
    A=[r['coefficients']+['1' if r['strict'] else '0'] for r in rows]
    A.extend([['0']*n+['-1'],['0']*n+['1']])
    return dict(c=['0']*n+['-1'],A=A,b=[r['rhs'] for r in rows]+['0','1'],
                equalities=[[list(row)+['0'],rhs] for row,rhs in plain(faces)])


def _margin(certificate):
    return None if certificate['status']=='infeasible' else -F(certificate['objective'])


def solve_model(model,budget=None,on_stage=None):
    if model['exclusion'] is not None:
        return dict(model=model,stages=[],result=dict(status='graph_unreachable'))
    from . import vendor_lp
    budget=budget or SolveBudget()
    stages=[]
    def execute(name,task):
        if not _solver_lock.acquire(blocking=False):raise BudgetExceeded('Concurrent candidate LP execution is unsupported')
        original=vendor_lp.linprog
        def counted(*args,**kwargs):
            budget.tick()
            options=dict(kwargs.get('options',{}));options['time_limit']=budget.remaining_seconds()
            kwargs['options']=options
            result=original(*args,**kwargs);budget.check();return result
        vendor_lp.linprog=counted
        try:
            cert=vendor_lp.exact_lp(tuple(map(F,task['c'])),[tuple(map(F,row)) for row in task['A']],
                list(map(F,task['b'])),[(tuple(map(F,row)),F(rhs)) for row,rhs in task['equalities']])
        finally:
            vendor_lp.linprog=original;_solver_lock.release()
        budget.check()
        value=plain(cert);stage=dict(name=name,task=task,certificate=value);stages.append(stage)
        if on_stage is not None:on_stage(plain(stage))
        return value
    def result(status,**values):return dict(model=model,stages=stages,result=dict(status=status,**values))
    def run():
        feasible=execute('feasibility',strict_task(model))
        if feasible['status']=='infeasible':return result('closed_infeasible')
        if _margin(feasible)==0:return result('strict_infeasible')
        primary=execute('primary',closed_task(model,'J'))
        if primary['status']!='optimal':raise vendor_lp.UncertifiedLP('Nonempty strict model has no certified primary optimum')
        J=F(primary['objective'])+F(model['lp']['J']['constant'])
        faces=[(model['lp']['J']['coefficients'],primary['objective'])]
        primary_face=execute('primary_attainment',strict_task(model,faces))
        if primary_face['status']!='optimal':raise vendor_lp.UncertifiedLP('Certified primary point is absent from its closed face')
        if _margin(primary_face)==0:return result('primary_unattained',primary_infimum=str(J))
        secondary=execute('secondary',closed_task(model,'Q',faces))
        if secondary['status']!='optimal':raise vendor_lp.UncertifiedLP('Nonempty attained-primary face has no certified Q optimum')
        Q=F(secondary['objective'])+F(model['lp']['Q']['constant'])
        faces.append((model['lp']['Q']['coefficients'],secondary['objective']))
        secondary_face=execute('secondary_attainment',strict_task(model,faces))
        if secondary_face['status']!='optimal':raise vendor_lp.UncertifiedLP('Certified Q point is absent from its closed face')
        if _margin(secondary_face)==0:return result('secondary_unattained',J=str(J),secondary_infimum=str(Q))
        return result('attained_optimum',J=str(J),Q_total=str(Q),H=model['H'],
                      site_action_tuple=model['pi'],lex_key=[str(J),str(Q),model['H'],model['pi']])
    try:return run()
    except (vendor_lp.UncertifiedLP,BudgetExceeded) as error:
        raise UnresolvedRegime(str(error),model,stages) from error


def _dot(c,x):return sum((F(a)*F(b) for a,b in zip(c,x)),F(0))


def solution_point(record,epsilon=F(1,10**30)):
    """Select a strict point; approach infima by exact convex mixtures."""
    status=record['result']['status'];model=record['model'];lp=model['lp']
    stages={s['name']:s['certificate'] for s in record['stages']}
    if status=='attained_optimum':
        return tuple(map(F,stages['secondary_attainment']['x'][:-1]))
    if type(epsilon) in (bool,float):raise ValueError('Approach epsilon must be exact')
    epsilon=F(epsilon)
    if epsilon<=0:raise ValueError('Approach epsilon must be positive')
    if status=='primary_unattained':
        left=tuple(map(F,stages['primary']['x']));right=tuple(map(F,stages['feasibility']['x'][:-1]));c=lp['J']['coefficients']
    elif status=='secondary_unattained':
        left=tuple(map(F,stages['secondary']['x']));right=tuple(map(F,stages['primary_attainment']['x'][:-1]));c=lp['Q']['coefficients']
    else:raise ValueError('An empty regime has no witness')
    gap=_dot(c,right)-_dot(c,left)
    if gap<=0:raise ValueError('Nonattained face lacks a strict positive objective gap')
    weight=min(F(1,2),epsilon/(2*gap))
    point=tuple((1-weight)*a+weight*b for a,b in zip(left,right))
    for row in lp['rows']:
        value=_dot(row['coefficients'],point);rhs=F(row['rhs'])
        if not (value<rhs if row['strict'] else value<=rhs):raise ValueError('Approach mixture left the strict model')
    return point
