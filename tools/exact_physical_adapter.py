"""Independent continuous EV/activity model on an exact supplied leg table.

No production optimizer is imported. Optimality is conditional on this declared
input table; schema validation does not certify road selection. Finite selectors
are shared by a closure point and a strict-support point in each affine fiber.
"""
from dataclasses import dataclass
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import time

import z3
from exact_leg_table import ExactLegTable,GroundedLookup,number,sequence

z3.set_param('parallel.enable',False)
SCHEMA='hiroute.exact_physical_model.v1'
FIELDS=('departure_time_s','initial_energy_kwh','capacity_kwh','minimum_energy_kwh',
        'destination_reserve_kwh','stop_overhead_s','stop_penalty_s','consumption_kwh_per_m')


class Unknown(RuntimeError):pass


def q(value):return value if type(value) is F else number(value)
def real(value):return z3.RealVal(str(q(value)))
def total(items):return z3.Sum(items) if items else real(0)
def fraction(value):
    value=z3.simplify(value)
    if z3.is_int_value(value):return F(value.as_long())
    if not z3.is_rational_value(value):raise Unknown('nonrational/nonfinite optimizer bound')
    return F(value.numerator_as_long(),value.denominator_as_long())
def atomic(path,value):
    path=Path(path);tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2)+'\n');tmp.replace(path)


@dataclass(frozen=True)
class Physics:
    values: tuple
    curve: tuple
    schedule: tuple | None
    pending: int
    sha256: str
    def get(self,key):return self.values[FIELDS.index(key)]


def validate(table,parameters):
    if not isinstance(table,ExactLegTable) or not table._validated:raise TypeError('parser-owned exact leg input required')
    if type(parameters) is not dict or parameters.get('schema')!=SCHEMA:raise ValueError('physical model schema')
    values=tuple(number(parameters[k]) for k in FIELDS)
    t0,e0,B,floor,reserve,h,penalty,rate=values
    if not 0<=floor<=e0<=B or B<=0 or not floor<=reserve<=B or h<=0 or min(penalty,rate)<0:
        raise ValueError('physical scalar bounds')
    curve=tuple(tuple(number(v) for v in sequence(row,'charging row'))
                for row in sequence(parameters['charging_curve'],'charging curve'))
    if any(len(row)!=4 for row in curve):raise ValueError('four entries per charging piece')
    if any({'C','CS'}&set(e) for e in table.capabilities.values()) and not curve:raise ValueError('charging curve missing')
    if curve:
        if curve[0][0]!=0 or curve[-1][1]!=B:raise ValueError('curve coverage')
        if any(lo>=hi or slope<=0 for lo,hi,slope,_ in curve):raise ValueError('curve domains/slopes')
        for a,b in zip(curve,curve[1:]):
            if a[1]!=b[0] or a[2]*a[1]+a[3]!=b[2]*b[0]+b[3]:raise ValueError('curve continuity')
    pending=parameters['initial_remaining_schedule']
    if type(pending) is not int or pending not in (0,1):raise ValueError('pending activity state')
    schedule=parameters['schedule']
    if schedule is not None:
        if type(schedule) is not dict or set(schedule)!={'a','b','D'}:raise ValueError('activity fields')
        schedule=tuple(number(schedule[k]) for k in ('a','b','D'))
        if schedule[0]>schedule[1] or schedule[2]<0:raise ValueError('activity parameters')
    if pending and schedule is None:raise ValueError('pending activity missing')
    digest=hashlib.sha256(json.dumps(parameters,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    return Physics(values,curve,schedule,pending,digest)


def literal_plan(plan):
    result=[]
    for action in sequence(plan,'plan'):
        pair=sequence(action,'literal Site/effect action')
        if len(pair)!=2 or any(type(x) is not str for x in pair):raise ValueError('literal action pair')
        result.append(pair)
    return tuple(result)


def replay(table,parameters,plan,charges,initial_wait=0):
    """Concrete Fraction equations; no SMT terms or optimization kernel."""
    p=validate(table,parameters);plan=literal_plan(plan);charges=sequence(charges,'charges')
    legs=table.literal_plan_legs(plan,p.pending)
    t0,e0,B,floor,reserve,h,penalty,rate=p.values;wait=q(initial_wait)
    if wait<0:raise ValueError('negative initial wait')
    energy,time=e0,t0+wait;qi=0;Q=F(0);trace=[]
    def phi(e):
        for lo,hi,slope,intercept in p.curve:
            if lo<=e<=hi:return slope*e+intercept
        raise ValueError('energy outside charging curve')
    for (site,effect),leg in zip(plan,legs):
        energy-=rate*leg.length;time+=leg.time;incoming,arrival=energy,time
        if not floor<=energy<=B:raise ValueError('arrival energy')
        delta=F(0)
        if effect in ('C','CS'):
            if qi>=len(charges):raise ValueError('missing charge')
            amount=q(charges[qi]);qi+=1
            if amount<=0 or energy+amount>B:raise ValueError('strict positive charge/capacity')
            delta=phi(energy+amount)-phi(energy);energy+=amount;Q+=amount
        if effect=='C':time=arrival+h+delta
        else:
            a,b,D=p.schedule
            if arrival>b-h:raise ValueError('latest activity start')
            time=max(a+D,arrival+h+D,arrival+h+delta if effect=='CS' else arrival+h+D)
        trace.append(dict(site=site,effect=effect,incoming=incoming,arrival=arrival,outgoing=energy,finish=time,
                          selected_nodes=leg.nodes,selected_edges=leg.edges))
    terminal=legs[-1];energy-=rate*terminal.length;time+=terminal.time
    if energy<reserve or qi!=len(charges):raise ValueError('terminal energy/charge count')
    return dict(key=(time-t0+penalty*len(plan),Q,len(plan),plan),final_energy=energy,trace=trace)


def relevant_depth(table,parameters,witness):
    checked=replay(table,parameters,witness['plan'],witness['charges'],witness.get('initial_wait',0))
    p=validate(table,parameters);U=checked['key'][0]
    return int(U//(p.get('stop_overhead_s')+p.get('stop_penalty_s'))),checked


class Encoding:
    def __init__(self,table,parameters,depth,upper,check=lambda:None):
        self.p=validate(table,parameters);self.lookup=GroundedLookup(table,check)
        self.trace=self.lookup.trace(depth,self.p.pending,prefix='physical_action',check=check)
        self.choices=self.trace.choices;self.actions=self.lookup.actions;self.H=self.trace.stop_count
        self.G=list(self.trace.constraints);self.active=[c>0 for c in self.choices]
        self.charging=self.trace.charging;self.service=self.trace.service;self.upper=q(upper)
        self.ins=tuple(z3.FreshInt('segment_in') for _ in self.choices)
        self.outs=tuple(z3.FreshInt('segment_out') for _ in self.choices)
        self.maxima=tuple(z3.FreshInt('maximum') for _ in self.choices)
        for i,active in enumerate(self.active):
            check();C,S=self.charging[i],self.service[i]
            self.G.extend((self.maxima[i]>=0,
                z3.Implies(z3.Not(active),self.maxima[i]==0),
                z3.Implies(z3.And(active,z3.Not(S)),self.maxima[i]==0),
                z3.Implies(z3.And(active,S,z3.Not(C)),self.maxima[i]<2),
                z3.Implies(z3.And(active,S,C),self.maxima[i]<3),
                z3.Implies(C,z3.And(self.ins[i]>=0,self.ins[i]<len(self.p.curve),
                                    self.outs[i]>=0,self.outs[i]<len(self.p.curve))),
                z3.Implies(z3.Not(C),z3.And(self.ins[i]==0,self.outs[i]==0))))

    def state_copy(self,check=lambda:None):
        t0,e0,B,floor,reserve,h,penalty,rate=self.p.values
        wait=z3.FreshReal('initial_wait');P=[wait>=0];strict=[];qs=[];energy,time=real(e0),real(t0)+wait
        for i,leg in enumerate(self.trace.legs):
            check();active,C,S=self.active[i],self.charging[i],self.service[i]
            incoming,arrival=energy-real(rate)*leg.length,time+leg.time
            out,finish=z3.FreshReal('energy'),z3.FreshReal('time')
            P.extend((z3.Implies(z3.Not(active),z3.And(out==energy,finish==time)),
                z3.Implies(active,z3.And(incoming>=real(floor),incoming<=real(B),out>=real(floor),out<=real(B))),
                z3.Implies(z3.And(active,z3.Not(C)),out==incoming),z3.Implies(C,out>=incoming)))
            strict.append(z3.Implies(C,out>incoming));left=[];right=[]
            for k,(lo,hi,slope,intercept) in enumerate(self.p.curve):
                P.extend((z3.Implies(z3.And(C,self.ins[i]==k),z3.And(incoming>=real(lo),incoming<=real(hi))),
                          z3.Implies(z3.And(C,self.outs[i]==k),z3.And(out>=real(lo),out<=real(hi)))))
                left.append(z3.If(self.ins[i]==k,real(slope)*incoming+real(intercept),real(0)))
                right.append(z3.If(self.outs[i]==k,real(slope)*out+real(intercept),real(0)))
            delta=total(right)-total(left);qs.append(z3.If(C,out-incoming,real(0)))
            a,b,D=self.p.schedule if self.p.schedule is not None else (F(0),F(0),F(0))
            P.append(z3.Implies(S,arrival<=real(b-h)))
            for mask,forms in ((z3.And(active,C,z3.Not(S)),[arrival+real(h)+delta]),
                               (z3.And(active,S,z3.Not(C)),[real(a+D),arrival+real(h+D)]),
                               (z3.And(active,C,S),[real(a+D),arrival+real(h+D),arrival+real(h)+delta])):
                for m,value in enumerate(forms):P.append(z3.Implies(z3.And(mask,self.maxima[i]==m),finish==value))
                P.append(z3.Implies(mask,z3.And(*[finish>=v for v in forms])))
            energy,time=out,finish
        terminal=self.trace.terminal;P.append(energy-real(rate)*terminal.length>=real(reserve))
        J=time+terminal.time-real(t0)+real(penalty)*self.H;P.append(J<=real(self.upper))
        return dict(P=P,strict=strict,J=J,Q=total(qs),qs=qs,wait=wait)


class Engine:
    def __init__(self,deadline,audit_dir=None):
        self.deadline=deadline;self.audit=[];self.directory=None if audit_dir is None else Path(audit_dir)
        if self.directory:self.directory.mkdir(parents=True,exist_ok=False)
    def remaining(self):
        remain=self.deadline-time.monotonic()
        if remain<=0:raise Unknown('query deadline; no infeasibility/optimality conclusion')
        return max(1,min(2000,int(remain*1000)))
    def check(self,solver,kind):
        solver.set(timeout=self.remaining());text=solver.sexpr()
        item=dict(kind=kind,status='started',sha256=hashlib.sha256(text.encode()).hexdigest())
        self.audit.append(item)
        if self.directory:
            (self.directory/f'{len(self.audit):04}-{kind}.smt2').write_text(text+'\n(check-sat)\n')
            atomic(self.directory/'checks.json',self.audit)
        result=solver.check();item.update(status='completed',result=str(result))
        if result==z3.unknown:item['reason']=solver.reason_unknown()
        if self.directory:atomic(self.directory/'checks.json',self.audit)
        if result==z3.unknown:raise Unknown(item['reason'])
        return result
    def feasible(self,constraints,kind):
        solver=z3.Solver();solver.add(*constraints);result=self.check(solver,kind)
        return solver.model() if result==z3.sat else None
    def minimum(self,constraints,objective,kind):
        solver=z3.Optimize();solver.add(*constraints);handle=solver.minimize(objective)
        if self.check(solver,kind)!=z3.sat:raise Unknown('closed optimization lacks SAT result')
        lower,upper=fraction(handle.lower()),fraction(handle.upper())
        if lower!=upper:raise Unknown('optimization bounds not certified tight')
        if self.feasible([*constraints,objective<real(lower)],kind+'-better') is not None:
            raise Unknown('strictly better point contradicts optimizer')
        if self.feasible([*constraints,objective==real(lower)],kind+'-face') is None:
            raise Unknown('closed optimum face absent')
        return lower


def solve(table,parameters,upper_witness=None,audit_dir=None,time_limit_s=8):
    if type(time_limit_s) not in (int,float) or not 0<time_limit_s<=8:raise ValueError('explicit <=8s tiny-gate deadline')
    start=time.monotonic();p=validate(table,parameters)
    if upper_witness is None:return dict(status='unknown_no_attained_bound',reason='no seed is not infeasibility')
    depth,seed=relevant_depth(table,parameters,upper_witness);engine=Engine(start+time_limit_s,audit_dir)
    metadata=dict(upper_key=seed['key'],upper_witness_independently_replayed=True,derived_depth=depth,
        depth_contract='complete floor(U_J/(h+lambda)); no H/N or prototype slot cap',
        table_sha256=table.payload_sha256,physics_sha256=p.sha256,charging_pieces=len(p.curve),
        road_selection_certified=False,scope='Exact optimum/infimum conditional on the supplied leg table and physical contract',
        continuous_copies=2,explicit_plan_enumerations=0,checks=engine.audit,external_solver='Z3 '+z3.get_version_string())
    try:
        m=Encoding(table,parameters,depth,seed['key'][0],engine.remaining)
        x,y=m.state_copy(engine.remaining),m.state_copy(engine.remaining)
        base=m.G+x['P']+y['P']+y['strict'];metadata.update(constraints=len(base),selector_count=4*depth)
        if engine.feasible(base,'supported-disjunction') is None:raise Unknown('replayed attained bound missing from model')
        j=engine.minimum(base,x['J'],'supported-J')
        actual=m.G+x['P']+x['strict']+[x['J']==real(j)]
        if engine.feasible(actual,'primary-attainment') is None:return dict(status='primary_unattained',primary_infimum=j,**metadata)
        primary_supported=base+[x['J']==real(j),y['J']==real(j)]
        Q=engine.minimum(primary_supported,x['Q'],'supported-primary-face-Q')
        joint=actual+[x['Q']==real(Q)]
        if engine.feasible(joint,'joint-attainment') is None:return dict(status='secondary_unattained',primary_value=j,
            primary_infimum=j,secondary_infimum=Q,**metadata)
        H=engine.minimum(joint,m.H,'attained-H')
        if H.denominator!=1:raise Unknown('nonintegral H')
        joint.append(m.H==int(H))
        for i in range(int(H)):
            rank=engine.minimum(joint,m.choices[i],f'attained-Pi-{i}')
            if rank.denominator!=1:raise Unknown('nonintegral action rank')
            joint.append(m.choices[i]==int(rank))
        model=engine.feasible(joint,'attained-full-key')
        if model is None:raise Unknown('jointly attained face lost')
        plan=tuple(m.actions[model.eval(m.choices[i]).as_long()-1] for i in range(int(H)))
        charges=[fraction(model.eval(x['qs'][i],model_completion=True)) for i,(_,effect) in enumerate(plan) if effect in ('C','CS')]
        wait=fraction(model.eval(x['wait'],model_completion=True));checked=replay(table,parameters,plan,charges,wait)
        if checked['key']!=(j,Q,int(H),plan):raise Unknown('concrete exact replay disagrees with full K')
        engine.remaining()
        return dict(status='attained_optimum',key=checked['key'],witness=dict(plan=plan,charges=charges,initial_wait=wait),
                    independent_replay=checked,**metadata)
    except Unknown as exc:return dict(status='unknown_resource_or_solver',reason=str(exc),**metadata)
