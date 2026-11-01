"""Opt-in compact exact comparator with fiber-wise strict-support witnesses.

No plans or linear branches are enumerated. Two continuous state copies share
all finite action/segment/max selectors. No HiRoute optimizer/bound is imported.
Only tiny road inputs and an independently replayable attained upper bound are
accepted. Exceeding a guard returns unsupported, never a truncated optimum.
"""
from fractions import Fraction as F
import re
import z3

from tiny_smt import Engine, Unknown, Unsupported, canonical_legs, exact, fraction, real, replay

MAX_SLOTS = 6


class MixedEngine(Engine):
    def feasible(self, constraints, kind):
        solver = z3.Solver(); solver.set(timeout=2000)
        solver.add(*constraints); result = solver.check(); self.record(kind,solver,result)
        if result == z3.unknown:
            raise Unknown(solver.reason_unknown())
        return solver.model() if result == z3.sat else None


def validate(snapshot):
    if (snapshot.get('schema')!='hiroute.problem_snapshot.v1'
            or snapshot.get('model_contract_id')!='hiroute.time_cut_v2.bounded'
            or snapshot.get('numerical_contract_id')!='exact_rational_inputs_v1'):
        raise Unsupported('snapshot/model/numerical contract version')
    numbers=[snapshot[k] for k in ('departure_time_s','minimum_energy_kwh','capacity_kwh',
        'initial_energy_kwh','destination_reserve_kwh','stop_overhead_s','stop_penalty_s','consumption_kwh_per_m')]
    numbers += [v for row in snapshot['charging_curve'] for v in row]
    numbers += [edge[k] for edge in snapshot['directed_edges'] for k in ('time_s','length_m')]
    if snapshot['schedule'] is not None:numbers += list(snapshot['schedule'].values())
    for value in numbers:
        if type(value) is int:continue
        if type(value) is not str or re.fullmatch(r'-?(?:0|[1-9][0-9]*)(?:/[1-9][0-9]*)?',value) is None:
            raise TypeError('canonical exact snapshot numerals required')
    identities=[snapshot['origin'],snapshot['destination'],*snapshot['candidate_order']]
    identities += [edge[k] for edge in snapshot['directed_edges'] for k in ('source','target','edge_id')]
    if any(type(value) is not str or not value for value in identities):raise ValueError('literal string identities')
    if snapshot['depth_mode'] != 'unrestricted':
        raise Unsupported('compact global comparator requires unrestricted input')
    if type(snapshot['depth_limit']) is not int or snapshot['depth_limit']<0:
        raise ValueError('invalid depth metadata')
    sites = snapshot['candidate_order']
    if len(sites)>2 or len(set(sites))!=len(sites) or set(sites)!=set(snapshot['site_capabilities']):
        raise Unsupported('requires <=2 distinct literal Site/road anchors')
    if set(sites)&{snapshot['origin'],snapshot['destination']}:
        raise Unsupported('Site aliases/endpoints are outside this prototype')
    if snapshot['selected_leg_contract']!='positive_time_node_path_edge_path_tie_v1':
        raise Unsupported('selected-leg contract')
    for effects in snapshot['site_capabilities'].values():
        if not effects or len(effects)!=len(set(effects)) or not set(effects)<={'C','S','CS'}:
            raise ValueError('capability set')
    floor,capacity,initial,reserve,h,penalty,rate = [exact(snapshot[k]) for k in (
        'minimum_energy_kwh','capacity_kwh','initial_energy_kwh','destination_reserve_kwh',
        'stop_overhead_s','stop_penalty_s','consumption_kwh_per_m')]
    if not 0<=floor<=initial<=capacity or capacity<=0 or not floor<=reserve<=capacity or h<=0 or min(rate,penalty)<0:
        raise ValueError('physical scalar bounds')
    curve = [tuple(map(exact,row)) for row in snapshot['charging_curve']]
    if len(curve)>2:raise Unsupported('at most two charging segments')
    if any(set(e)&{'C','CS'} for e in snapshot['site_capabilities'].values()) and not curve:
        raise ValueError('missing charging curve')
    if curve:
        if curve[0][0]!=0 or curve[-1][1]!=capacity:
            raise ValueError('curve coverage')
        if any(lo>=hi or slope<=0 for lo,hi,slope,_ in curve):raise ValueError('curve slope/domain')
        for x,y in zip(curve,curve[1:]):
            if x[1]!=y[0] or x[2]*x[1]+x[3]!=y[2]*y[0]+y[3]:raise ValueError('curve continuity')
    rem = snapshot['initial_remaining_schedule']
    if type(rem) is not int or rem not in (0,1):raise ValueError('activity state')
    if rem and snapshot['schedule'] is None:raise ValueError('missing activity')
    if snapshot['schedule'] is not None:
        a,b,D = (exact(snapshot['schedule'][k]) for k in ('a','b','D'))
        if a>b or D<0:raise ValueError('activity parameters')
    return curve


def total(items, zero):
    return z3.Sum(items) if items else zero


class Encoding:
    """A finite selector vector d; fixing d makes each state copy affine."""
    def __init__(self,snapshot,depth,upper,legs):
        self.s,self.depth,self.upper,self.legs = snapshot,depth,upper,legs
        self.curve = validate(snapshot)
        if not 0<=depth<=MAX_SLOTS:raise Unsupported('relevant depth exceeds prototype guard')
        self.actions = tuple(sorted((site,effect) for site in snapshot['candidate_order']
                                    for effect in snapshot['site_capabilities'][site]))
        self.anchors = (snapshot['origin'],)+tuple(snapshot['candidate_order'])
        self.choices = [z3.Int(f'action_{i}') for i in range(depth)]
        self.ins = [z3.Int(f'segment_in_{i}') for i in range(depth)]
        self.outs = [z3.Int(f'segment_out_{i}') for i in range(depth)]
        self.maxima = [z3.Int(f'maximum_{i}') for i in range(depth)]
        self.G,self.moves,self.active,self.charging,self.service = [],[],[],[],[]
        previous = z3.IntVal(0); remaining = z3.BoolVal(bool(snapshot['initial_remaining_schedule']))
        for i,choice in enumerate(self.choices):
            active = choice>0
            charging = z3.Or(*[choice==j for j,(_,e) in enumerate(self.actions,1) if e in ('C','CS')])
            service = z3.Or(*[choice==j for j,(_,e) in enumerate(self.actions,1) if e in ('S','CS')])
            self.active.append(active);self.charging.append(charging);self.service.append(service)
            self.G += [choice>=0,choice<=len(self.actions),self.maxima[i]>=0]
            if i:self.G.append(z3.Implies(self.choices[i-1]==0,choice==0))
            self.G += [z3.Implies(service,remaining),
                z3.Implies(z3.Not(active),z3.And(self.ins[i]==0,self.outs[i]==0,self.maxima[i]==0)),
                z3.Implies(z3.Not(charging),z3.And(self.ins[i]==0,self.outs[i]==0))]
            remaining = z3.And(remaining,z3.Not(service))
            times,lengths=[],[];target=previous
            for j,(site,effect) in enumerate(self.actions,1):
                self.G.append(z3.Implies(choice==j,self.maxima[i]<{'C':1,'S':2,'CS':3}[effect]))
                target=z3.If(choice==j,self.anchors.index(site),target)
                for p,anchor in enumerate(self.anchors):
                    selected=z3.And(previous==p,choice==j)
                    leg=legs.get((anchor,site))
                    if leg is None:self.G.append(z3.Not(selected))
                    else:
                        times.append(z3.If(selected,real(leg[0]),real(0)))
                        lengths.append(z3.If(selected,real(leg[1]),real(0)))
            self.G += [z3.Implies(charging,z3.And(self.ins[i]>=0,self.ins[i]<len(self.curve),
                self.outs[i]>=0,self.outs[i]<len(self.curve)))]
            self.moves.append((total(times,real(0)),total(lengths,real(0))))
            previous=target
        self.G.append(z3.Not(remaining))
        final_times,final_lengths=[],[]
        for p,anchor in enumerate(self.anchors):
            leg=legs.get((anchor,snapshot['destination']))
            if leg is None:self.G.append(previous!=p)
            else:
                final_times.append(z3.If(previous==p,real(leg[0]),real(0)))
                final_lengths.append(z3.If(previous==p,real(leg[1]),real(0)))
        self.final_move=(total(final_times,real(0)),total(final_lengths,real(0)))
        self.H=total([z3.If(a,1,0) for a in self.active],z3.IntVal(0))

    def state_copy(self,name):
        s=self.s
        floor,B,h,penalty,rate,t0,e0,reserve = [exact(s[k]) for k in (
            'minimum_energy_kwh','capacity_kwh','stop_overhead_s','stop_penalty_s',
            'consumption_kwh_per_m','departure_time_s','initial_energy_kwh','destination_reserve_kwh')]
        wait=z3.Real(name+'_wait');P=[wait>=0];strict=[];qs=[]
        energy,time=real(e0),real(t0)+wait
        for i,(choice,(dt,ds)) in enumerate(zip(self.choices,self.moves)):
            incoming,arrival=energy-real(rate)*ds,time+dt
            out,finish=z3.Real(f'{name}_energy_{i}'),z3.Real(f'{name}_time_{i}')
            active,charging=self.active[i],self.charging[i]
            P += [z3.Implies(z3.Not(active),z3.And(out==energy,finish==time)),
                  z3.Implies(active,z3.And(incoming>=real(floor),incoming<=real(B),out>=real(floor),out<=real(B))),
                  z3.Implies(z3.And(active,z3.Not(charging)),out==incoming),
                  z3.Implies(charging,out>=incoming)]
            strict.append(z3.Implies(charging,out>incoming))
            phi_in,phi_out=[],[]
            for k,(lo,hi,slope,intercept) in enumerate(self.curve):
                P += [z3.Implies(z3.And(charging,self.ins[i]==k),z3.And(incoming>=real(lo),incoming<=real(hi))),
                      z3.Implies(z3.And(charging,self.outs[i]==k),z3.And(out>=real(lo),out<=real(hi)))]
                phi_in.append(z3.If(self.ins[i]==k,real(slope)*incoming+real(intercept),real(0)))
                phi_out.append(z3.If(self.outs[i]==k,real(slope)*out+real(intercept),real(0)))
            delta=total(phi_out,real(0))-total(phi_in,real(0))
            qs.append(z3.If(charging,out-incoming,real(0)))
            for j,(_,effect) in enumerate(self.actions,1):
                if effect=='C':forms=[arrival+real(h)+delta]
                else:
                    a,b,D=(exact(s['schedule'][k]) for k in ('a','b','D')) if s['schedule'] else (F(0),F(0),F(0))
                    P.append(z3.Implies(choice==j,arrival<=real(b-h)))
                    forms=[real(a+D),arrival+real(h+D)]
                    if effect=='CS':forms.append(arrival+real(h)+delta)
                for m,value in enumerate(forms):
                    P.append(z3.Implies(z3.And(choice==j,self.maxima[i]==m),finish==value))
                P.append(z3.Implies(choice==j,z3.And(*[finish>=v for v in forms])))
            energy,time=out,finish
        dt,ds=self.final_move
        P.append(energy-real(rate)*ds>=real(reserve))
        J=time+dt-real(t0)+real(penalty)*self.H
        P.append(J<=real(self.upper))
        return dict(P=P,strict=strict,J=J,Q=total(qs,real(0)),qs=qs,wait=wait)


def solve(snapshot,upper_witness=None,audit_dir=None):
    validate(snapshot)
    if upper_witness is None:
        return dict(status='unknown_no_attained_bound',reason='no seed is not infeasibility')
    plan=tuple(tuple(p) for p in upper_witness['plan'])
    if len(plan)>MAX_SLOTS:return dict(status='unsupported_seed_size')
    seed=replay(snapshot,plan,upper_witness['charges'],upper_witness.get('initial_wait',0))
    upper=seed['key'][0]
    depth=int(upper//(exact(snapshot['stop_overhead_s'])+exact(snapshot['stop_penalty_s'])))
    if depth>MAX_SLOTS:return dict(status='unsupported_relevant_depth',derived_depth=depth,upper_key=seed['key'])
    encoding=Encoding(snapshot,depth,upper,canonical_legs(snapshot))
    x,y=encoding.state_copy('objective'),encoding.state_copy('support')
    engine=MixedEngine(audit_dir)
    base=encoding.G+x['P']+y['P']+y['strict']
    metadata=dict(upper_key=seed['key'],upper_witness_independently_replayed=True,
        derived_depth=depth,depth_contract='complete floor(U_J/(h+lambda)); unsupported beyond guard',
        selector_count=4*depth,continuous_copies=2,explicit_plan_enumerations=0,
        constraints=len(base),checks=engine.audit,external_solver='Z3 '+z3.get_version_string())
    if engine.feasible(base,'supported-disjunction') is None:
        raise Unknown('verified attained upper bound missing from supported model')
    j=engine.minimum(base,x['J'],'supported-J')
    actual=encoding.G+x['P']+x['strict']+[x['J']==real(j)]
    if engine.feasible(actual,'primary-attainment') is None:
        return dict(status='primary_unattained',primary_infimum=j,**metadata)
    primary_supported=base+[x['J']==real(j),y['J']==real(j)]
    q=engine.minimum(primary_supported,x['Q'],'supported-primary-face-Q')
    joint=actual+[x['Q']==real(q)]
    if engine.feasible(joint,'joint-attainment') is None:
        return dict(status='secondary_unattained',primary_value=j,primary_infimum=j,secondary_infimum=q,**metadata)
    h=engine.minimum(joint,encoding.H,'attained-H')
    if h.denominator!=1:raise Unknown('nonintegral stop count')
    joint.append(encoding.H==int(h))
    for i in range(int(h)):
        rank=engine.minimum(joint,encoding.choices[i],f'attained-Pi-{i}')
        if rank.denominator!=1:raise Unknown('nonintegral action rank')
        joint.append(encoding.choices[i]==int(rank))
    witness=engine.feasible(joint,'attained-full-key')
    if witness is None:raise Unknown('lost jointly attained face')
    chosen=tuple(encoding.actions[witness.eval(encoding.choices[i]).as_long()-1] for i in range(int(h)))
    charges=[fraction(witness.eval(x['qs'][i],model_completion=True)) for i,(_,effect) in enumerate(chosen) if effect in ('C','CS')]
    wait=fraction(witness.eval(x['wait'],model_completion=True))
    checked=replay(snapshot,chosen,charges,wait)
    if checked['key']!=(j,q,int(h),chosen):raise Unknown('independent concrete replay mismatch')
    return dict(status='attained_optimum',key=checked['key'],witness=dict(plan=chosen,charges=charges,initial_wait=wait),
        independent_replay=checked,**metadata)
