"""Independent continuous EV/activity model on an exact supplied leg table.

No production optimizer is imported. Optimality is conditional on this declared
input table; schema validation does not certify road selection. Finite selectors
are shared by a closure point and a strict-support point in each affine fiber.
"""
from dataclasses import dataclass, replace
from contextlib import contextmanager
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import time

import z3
from .exact_leg_table import ExactLegTable,GroundedLookup,number,sequence

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


def table_relevant_depth(table,parameters,witness):
    """Complete depth conditional on the validated directed selected-time table.

    Its parser checks T(s,t)<=T(s,m)+T(m,t) at every Site anchor.
    Induction covers every repeated-Site walk. Exactly one pending S/CS adds
    at least D, including CS overlap; every stop additionally adds h+lambda.
    Thus J>=T(O,D)+pending*D+H*(h+lambda), retaining the integer equality.
    This is not an independent proof of raw-road selection.
    """
    checked=replay(table,parameters,witness['plan'],witness['charges'],witness.get('initial_wait',0))
    p=validate(table,parameters);direct=table.pairs[table.origin_anchor,table.destination_anchor]
    if not direct.reachable:raise ValueError('feasible upper walk contradicts validated table reachability')
    duration=p.schedule[2] if p.pending else F(0)
    depth=int((checked['key'][0]-direct.time-duration)//(p.get('stop_overhead_s')+p.get('stop_penalty_s')))
    if depth<len(witness['plan']):raise ValueError('depth inequality contradicts replayed upper')
    return depth,checked


class Encoding:
    def __init__(self,table,parameters,depth,upper,check=lambda:None,share_lookup=True,finite_lookup=False):
        self.p=validate(table,parameters);self.lookup=GroundedLookup(table,check)
        self.trace=self.lookup.trace(depth,self.p.pending,prefix='physical_action',check=check)
        # Keep the original expression trace for solver-free grounding/replay.
        self.ground_trace=self.trace
        self.lookup_definitions=()
        if finite_lookup:
            from .finite_leg_lookup import FiniteGroundedLookup
            self.finite_lookup=FiniteGroundedLookup(self.lookup,check)
            finite=self.finite_lookup.trace(depth,self.p.pending,prefix='finite_action',check=check)
            bindings=tuple(zip(finite.choices,self.ground_trace.choices))
            def subst(e):return z3.substitute(e,*bindings) if bindings else e
            def leg(e):return replace(e,guard=subst(e.guard),time=subst(e.time),length=subst(e.length))
            self.trace=replace(finite,choices=self.ground_trace.choices,
                constraints=tuple(subst(e) for e in finite.constraints),
                legs=tuple(leg(e) for e in finite.legs),terminal=leg(finite.terminal),
                charging=tuple(subst(e) for e in finite.charging),service=tuple(subst(e) for e in finite.service),
                stop_count=subst(finite.stop_count))
        elif share_lookup:
            originals=tuple(getattr(self.lookup,k) for k in ('T','L','R','AS','AT','C','S'))
            names=tuple(z3.FreshConst(a.sort(),'leg_'+k) for k,a in zip(('T','L','R','AS','AT','C','S'),originals))
            bindings=tuple(zip(originals,names))
            def shared(e):return z3.substitute(e,*bindings)
            def leg(e):return replace(e,guard=shared(e.guard),time=shared(e.time),length=shared(e.length))
            self.lookup_definitions=tuple(n==a for n,a in zip(names,originals))
            self.trace=replace(self.trace,
                constraints=self.lookup_definitions+tuple(shared(e) for e in self.trace.constraints),
                legs=tuple(leg(e) for e in self.trace.legs),terminal=leg(self.trace.terminal),
                charging=tuple(shared(e) for e in self.trace.charging),service=tuple(shared(e) for e in self.trace.service))
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
        wait=z3.FreshReal('initial_wait');P=[wait>=0];strict=[];qs=[];state_symbols=[];energy,time=real(e0),real(t0)+wait
        for i,leg in enumerate(self.trace.legs):
            check();active,C,S=self.active[i],self.charging[i],self.service[i]
            incoming,arrival=energy-real(rate)*leg.length,time+leg.time
            out,finish=z3.FreshReal('energy'),z3.FreshReal('time')
            state_symbols.append((out,finish))
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
        return dict(P=P,strict=strict,J=J,Q=total(qs),qs=qs,wait=wait,state_symbols=tuple(state_symbols),encoding_owner=self)


class Engine:
    def __init__(self,deadline,audit_dir=None,max_check_ms=2000,dag_audit=False):
        if type(max_check_ms) is not int or not 0<max_check_ms<=120000:raise ValueError('bounded per-check timeout')
        self.dag_audit=dag_audit
        if dag_audit:
            from .dag_formula_export import AssertionDAGCache
            self.audit_cache=AssertionDAGCache()
        if dag_audit and audit_dir is None:raise Unknown('DAG audit requires a persistent output directory')
        self.max_check_ms=max_check_ms
        self.deadline=deadline;self.audit=[];self.phases=[];self.directory=None if audit_dir is None else Path(audit_dir)
        if self.directory:self.directory.mkdir(parents=True,exist_ok=False)
    def remaining(self):
        remain=self.deadline-time.monotonic()
        if remain<=0:raise Unknown('query deadline; no infeasibility/optimality conclusion')
        return max(1,min(self.max_check_ms,int(remain*1000)))
    @staticmethod
    def memory_sample():
        """Observational process RSS only; never modifies external guards."""
        try:
            import psutil
            return dict(process_RSS_bytes=psutil.Process().memory_info().rss)
        except Exception:
            # Telemetry must not change the mathematical or guard outcome.
            return dict(process_RSS_bytes=None)

    @contextmanager
    def phase(self,name):
        wall,cpu=time.monotonic(),time.process_time()
        item=dict(name=name,status='started',memory_start=self.memory_sample());self.phases.append(item)
        if self.directory:atomic(self.directory/'phases.json',self.phases)
        try:
            yield
        except BaseException:
            item['status']='interrupted'
            raise
        else:item['status']='completed'
        finally:
            item.update(elapsed_wall_s=time.monotonic()-wall,process_CPU_s=time.process_time()-cpu,
                        memory_end=self.memory_sample())
            if self.directory:atomic(self.directory/'phases.json',self.phases)

    def check(self,solver,kind,objectives=()):
        if self.dag_audit:return self.check_dag(solver,kind,objectives)
        self.remaining()
        with self.phase(kind+':serialize'):
            text=solver.sexpr()
        with self.phase(kind+':audit-write'):
            item=dict(kind=kind,status='started',sha256=hashlib.sha256(text.encode()).hexdigest())
            self.audit.append(item)
            if self.directory:
                (self.directory/f'{len(self.audit):04}-{kind}.smt2').write_text(text+'\n(check-sat)\n')
                atomic(self.directory/'checks.json',self.audit)
        del text
        with self.phase(kind+':solver-check'):
            # Serialization and audit I/O consume the same end-to-end deadline.
            timeout=self.remaining()
            item['effective_solver_timeout_ms']=timeout
            solver.set(timeout=timeout)
            result=solver.check()
        item.update(status='completed',result=str(result))
        if result==z3.unknown:item['reason']=solver.reason_unknown()
        if self.directory:atomic(self.directory/'checks.json',self.audit)
        if result==z3.unknown:raise Unknown(item['reason'])
        self.remaining()
        return result
    def check_dag(self,solver,kind,objectives=()):
        """Audit live assertions/objectives; never parse or replace the formula."""
        from .dag_formula_export import export_dag,verify_export
        self.remaining()
        item=dict(kind=kind,status='preparing',audit_format='typed-dag-v1',
                  objective_count=len(objectives))
        self.audit.append(item)
        path=self.directory/f'{len(self.audit):04}.dag.smt2'
        try:
            atomic(self.directory/'checks.json',self.audit)
            with self.phase(kind+':dag-export'):
                metadata=self.audit_cache.export(list(solver.assertions()),path,self.remaining,objectives=objectives)
            with self.phase(kind+':dag-verification'):
                item.update(expected_payload_sha256=metadata['payload_sha256'],bytes=metadata['bytes'],file=path.name,cache_hit=metadata['cache_hit'])
                atomic(self.directory/'checks.json',self.audit)
                verified=verify_export(path,self.remaining)
                if verified['payload_sha256']!=item['expected_payload_sha256'] or verified['bytes']!=item['bytes']:
                    raise Unknown('DAG audit payload mismatch')
                digest=hashlib.sha256()
                with path.open('rb') as stream:
                    for block in iter(lambda:stream.read(1024*1024),b''):
                        self.remaining();digest.update(block)
                item['sha256']=digest.hexdigest()
            with self.phase(kind+':solver-check'):
                timeout=self.remaining();solver.set(timeout=timeout)
                item.update(status='started',effective_solver_timeout_ms=timeout)
                atomic(self.directory/'checks.json',self.audit)
                self.remaining()  # Receipt I/O is part of the same deadline.
                result=solver.check()
            item.update(status='completed',result=str(result))
            if result==z3.unknown:item['reason']=solver.reason_unknown()
            atomic(self.directory/'checks.json',self.audit)
            if result==z3.unknown:raise Unknown(item['reason'])
            self.remaining();return result
        except (OSError,ValueError,TypeError,TimeoutError,z3.Z3Exception,Unknown) as exc:
            if item['status']!='completed':item.update(status='failed',reason=str(exc))
            try:atomic(self.directory/'checks.json',self.audit)
            except OSError:pass
            raise Unknown('DAG audit/check failed: '+str(exc)) from exc

    def feasible(self,constraints,kind):
        with self.phase(kind+':assertions'):
            solver=z3.Solver();solver.add(*constraints)
        result=self.check(solver,kind)
        return solver.model() if result==z3.sat else None
    def minimum(self,constraints,objective,kind):
        with self.phase(kind+':assertions'):
            solver=z3.Optimize();solver.add(*constraints);handle=solver.minimize(objective)
        if self.check(solver,kind,objectives=(objective,))!=z3.sat:raise Unknown('closed optimization lacks SAT result')
        lower,upper=fraction(handle.lower()),fraction(handle.upper())
        if lower!=upper:raise Unknown('optimization bounds not certified tight')
        if self.feasible([*constraints,objective<real(lower)],kind+'-better') is not None:
            raise Unknown('strictly better point contradicts optimizer')
        if self.feasible([*constraints,objective==real(lower)],kind+'-face') is None:
            raise Unknown('closed optimum face absent')
        return lower


def solve(table,parameters,upper_witness=None,audit_dir=None,time_limit_s=8):
    if type(time_limit_s) not in (int,float) or not 0<time_limit_s<=8:raise ValueError('explicit <=8s tiny-gate deadline')
    return _solve(table,parameters,upper_witness,audit_dir,time_limit_s,False)


def solve_real(table,parameters,upper_witness=None,audit_dir=None,time_limit_s=120):
    """Explicit admitted-real profile; same equations, complete table depth."""
    if type(time_limit_s) not in (int,float) or not 0<time_limit_s<=120:raise ValueError('explicit <=120s real deadline')
    return _solve(table,parameters,upper_witness,audit_dir,time_limit_s,True)


def _solve(table,parameters,upper_witness,audit_dir,time_limit_s,table_depth,share_lookup=True,finite_lookup=False,dag_audit=False,incumbent_certificate=False):
    start=time.monotonic();cpu_start=time.process_time();p=validate(table,parameters)
    if upper_witness is None:return dict(status='unknown_no_attained_bound',reason='no seed is not infeasibility')
    depth,seed=(table_relevant_depth if table_depth else relevant_depth)(table,parameters,upper_witness)
    validated_wall,validated_cpu=time.monotonic()-start,time.process_time()-cpu_start
    engine=Engine(start+time_limit_s,audit_dir,120000 if table_depth else 2000,dag_audit=dag_audit)
    # The caller's on-disk loading remains outside this already-loaded-table API.
    engine.phases.append(dict(name='parameters-upper-and-depth-validation',status='completed',
        elapsed_wall_s=validated_wall,process_CPU_s=validated_cpu))
    metadata=dict(upper_key=seed['key'],upper_witness_independently_replayed=True,derived_depth=depth,
        depth_contract=('complete floor((U_J-T_OD-pending*D)/(h+lambda)); validated table triangle proof'
                        if table_depth else 'complete floor(U_J/(h+lambda)); no H/N or prototype slot cap'),
        solver_check_timeout_cap_ms=engine.max_check_ms,
        table_sha256=table.payload_sha256,physics_sha256=p.sha256,charging_pieces=len(p.curve),
        road_selection_certified=False,scope='Exact optimum/infimum conditional on the supplied leg table and physical contract',
        continuous_copies=2,explicit_plan_enumerations=0,checks=engine.audit,phases=engine.phases,external_solver='Z3 '+z3.get_version_string())
    try:
        with engine.phase('lookup-and-physical-construction'):
            m=Encoding(table,parameters,depth,seed['key'][0],engine.remaining,share_lookup=share_lookup,finite_lookup=finite_lookup)
        with engine.phase('continuous-state-construction'):
            x,y=m.state_copy(engine.remaining),m.state_copy(engine.remaining)
        base=m.G+x['P']+y['P']+y['strict'];metadata.update(constraints=len(base),selector_count=4*depth)
        if incumbent_certificate:
            from .incumbent_model_certificate import certify
            try:
                with engine.phase('exact-incumbent-model-certificate'):
                    certificate=certify(m,x,y,table,parameters,upper_witness,base,engine.remaining)
                    if engine.directory:atomic(engine.directory/'incumbent-certificate.json',certificate)
                metadata['incumbent_certificate']=certificate
            except (ValueError,TypeError,KeyError,TimeoutError,OSError) as exc:
                raise Unknown('incumbent certificate rejected: '+str(exc)) from exc
        elif engine.feasible(base,'supported-disjunction') is None:raise Unknown('replayed attained bound missing from model')
        j=engine.minimum(base,x['J'],'supported-J')
        actual=m.G+x['P']+x['strict']+[x['J']==real(j)]
        if engine.feasible(actual,'primary-attainment') is None:
            engine.remaining()
            return dict(status='primary_unattained',primary_infimum=j,**metadata)
        primary_supported=base+[x['J']==real(j),y['J']==real(j)]
        Q=engine.minimum(primary_supported,x['Q'],'supported-primary-face-Q')
        joint=actual+[x['Q']==real(Q)]
        if engine.feasible(joint,'joint-attainment') is None:
            engine.remaining()
            return dict(status='secondary_unattained',primary_value=j,primary_infimum=j,secondary_infimum=Q,**metadata)
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
        wait=fraction(model.eval(x['wait'],model_completion=True))
        with engine.phase('returned-plan-replay'):
            checked=replay(table,parameters,plan,charges,wait)
        if checked['key']!=(j,Q,int(H),plan):raise Unknown('concrete exact replay disagrees with full K')
        engine.remaining()
        return dict(status='attained_optimum',key=checked['key'],witness=dict(plan=plan,charges=charges,initial_wait=wait),
                    independent_replay=checked,**metadata)
    except Unknown as exc:return dict(status='unknown_resource_or_solver',reason=str(exc),**metadata)
