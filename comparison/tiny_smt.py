"""Independent bounded-domain rational linear model; no HiRoute imports.

Only tiny snapshots (<=2 Sites, <=6 road nodes, <=2 stops) are supported.
Each charging-segment/max-expression branch is a closed linear polyhedron.
Strict feasibility is tested before optimizing its closure, and again on each
successive objective face. Z3's mathematical Reals are used, never FP sorts.
"""
from fractions import Fraction as F
from itertools import product
import hashlib
from pathlib import Path

import z3

z3.set_param('parallel.enable', False)


class Unsupported(ValueError):
    pass


class Unknown(RuntimeError):
    pass


def exact(x):
    if isinstance(x, F):
        return x
    if type(x) not in (str, int):
        raise TypeError('exact integer/rational strings required')
    return F(x)


def real(x):
    return z3.RealVal(str(exact(x)))


def fraction(x):
    x = z3.simplify(x)
    if z3.is_int_value(x):
        return F(x.as_long())
    if not z3.is_rational_value(x):
        raise Unknown('nonrational/nonfinite optimization bound: '+str(x))
    return F(x.numerator_as_long(), x.denominator_as_long())


def canonical_legs(snapshot):
    """Independent exhaustive simple road paths, only on <=6-node fixtures.

    Positive time implies a shortest-time path has no cycle. Full node tuples,
    then edge-ID tuples break ties; selected length is summed on that path.
    """
    edges = snapshot['directed_edges']
    if len(edges) > 12:
        raise Unsupported('more than twelve road edges')
    nodes = {snapshot['origin'], snapshot['destination'], *snapshot['candidate_order']}
    adjacency, identities = {}, set()
    for e in edges:
        if e['edge_id'] in identities:
            raise ValueError('duplicate edge identity')
        identities.add(e['edge_id'])
        if min(exact(e['time_s']), exact(e['length_m'])) <= 0:
            raise ValueError('road weights must be positive')
        nodes.update((e['source'], e['target']))
        adjacency.setdefault(e['source'], []).append(e)
    if len(nodes) > 6:
        raise Unsupported('more than six road nodes')
    legs = {}
    for source, target in product(sorted(nodes), repeat=2):
        paths = []
        def walk(node, visited, ids, duration, length):
            if node == target:
                paths.append((duration, visited, ids, length))
                if len(paths) > 128:
                    raise Unsupported('road path enumeration limit')
                return
            for e in adjacency.get(node, ()):
                if e['target'] not in visited:
                    walk(e['target'], visited+(e['target'],), ids+(e['edge_id'],),
                         duration+exact(e['time_s']), length+exact(e['length_m']))
        walk(source, (source,), (), F(0), F(0))
        if paths:
            t, ns, es, length = min(paths, key=lambda p:p[:3])
            legs[source, target] = (t, length, ns, es)
    return legs


def plans(snapshot):
    H = snapshot['depth_limit']
    if snapshot['depth_mode'] != 'diagnostic_cap' or type(H) is not int or not 0 <= H <= 2:
        raise Unsupported('requires explicit finite domain H<=2')
    if len(snapshot['candidate_order']) > 2:
        raise Unsupported('more than two Sites')
    actions = sorted((s, effect) for s in snapshot['candidate_order']
                     for effect in snapshot['site_capabilities'][s])
    def visit(prefix, remaining):
        if not remaining:
            yield prefix
        if len(prefix) < H:
            for site, effect in actions:
                if effect not in ('C', 'S', 'CS'):
                    raise Unsupported('unknown effect')
                if effect != 'C' and not remaining:
                    continue
                yield from visit(prefix+((site, effect),), 0 if effect != 'C' else remaining)
    return visit((), snapshot['initial_remaining_schedule'])


class Engine:
    def __init__(self, audit_dir=None):
        self.audit, self.audit_dir = [], None if audit_dir is None else Path(audit_dir)
        if self.audit_dir:
            self.audit_dir.mkdir(parents=True, exist_ok=True)

    def record(self, kind, solver, result):
        text = solver.sexpr()
        item = dict(kind=kind, result=str(result), sha256=hashlib.sha256(text.encode()).hexdigest())
        self.audit.append(item)
        if self.audit_dir:
            (self.audit_dir/f'{len(self.audit):04}-{kind}.smt2').write_text(text+'\n(check-sat)\n')

    def feasible(self, constraints, kind):
        s = z3.SolverFor('QF_LRA'); s.set(timeout=2000)
        s.add(*constraints); result = s.check(); self.record(kind, s, result)
        if result == z3.unknown:
            raise Unknown(s.reason_unknown())
        return s.model() if result == z3.sat else None

    def minimum(self, constraints, objective, kind):
        o = z3.Optimize(); o.set(timeout=2000)
        o.add(*constraints); handle = o.minimize(objective)
        result = o.check(); self.record(kind, o, result)
        if result != z3.sat:
            raise Unknown('closed optimization '+str(result))
        lower, upper = fraction(handle.lower()), fraction(handle.upper())
        if lower != upper:
            raise Unknown('optimization bound is not certified tight')
        if self.feasible([*constraints, objective < real(lower)], kind+'-better') is not None:
            raise Unknown('strictly better point contradicts bound')
        if self.feasible([*constraints, objective == real(lower)], kind+'-face') is None:
            raise Unknown('closed optimum is not attained')
        return lower


def branches(snapshot, legs):
    if snapshot['selected_leg_contract'] != 'positive_time_node_path_edge_path_tie_v1':
        raise Unsupported('unrecognized selected-leg contract')
    if (len(set(snapshot['candidate_order'])) != len(snapshot['candidate_order'])
            or set(snapshot['candidate_order']) != set(snapshot['site_capabilities'])):
        raise ValueError('candidate identities')
    for effects in snapshot['site_capabilities'].values():
        if not effects or len(effects)!=len(set(effects)) or not set(effects)<={'C','S','CS'}:
            raise ValueError('capability set')
    if type(snapshot['initial_remaining_schedule']) is not int or snapshot['initial_remaining_schedule'] not in (0,1):
        raise ValueError('remaining activity state')
    if snapshot['initial_remaining_schedule'] and snapshot['schedule'] is None:
        raise ValueError('missing activity')
    if snapshot['schedule'] is not None:
        a,b,D=(exact(snapshot['schedule'][x]) for x in ('a','b','D'))
        if a>b or D<0:raise ValueError('activity parameters')
    B, emin, e0, reserve, h, penalty, rate, t0 = [exact(snapshot[k]) for k in (
        'capacity_kwh', 'minimum_energy_kwh', 'initial_energy_kwh',
        'destination_reserve_kwh', 'stop_overhead_s', 'stop_penalty_s',
        'consumption_kwh_per_m', 'departure_time_s')]
    if not 0 <= emin <= e0 <= B or not emin <= reserve <= B or h <= 0 or min(penalty, rate) < 0:
        raise ValueError('invalid physical scalars')
    curve = [tuple(map(exact, row)) for row in snapshot['charging_curve']]
    if len(curve)>2:raise Unsupported('more than two charging segments')
    if any(set(effects)&{'C','CS'} for effects in snapshot['site_capabilities'].values()) and not curve:
        raise Unsupported('charging capability requires a curve')
    if any(lo >= hi or slope <= 0 for lo, hi, slope, _ in curve):
        raise ValueError('invalid charging segments')
    if curve and (curve[0][0] != 0 or curve[-1][1] != B):
        raise Unsupported('curve must cover zero through capacity')
    for x, y in zip(curve, curve[1:]):
        if x[1] != y[0] or x[2]*x[1]+x[3] != y[2]*y[0]+y[3]:
            raise Unsupported('curve must be continuous and adjacent')
    number = 0
    for plan in plans(snapshot):
        anchors = (snapshot['origin'],)+tuple(s for s,_ in plan)+(snapshot['destination'],)
        if any((a,b) not in legs for a,b in zip(anchors, anchors[1:])):
            continue
        choices = []
        for _, effect in plan:
            pieces = tuple(product(range(len(curve)), repeat=2)) if effect != 'S' else ((None,None),)
            choices.append(tuple((i,j,m) for i,j in pieces
                                 for m in range({'C':1,'S':2,'CS':3}[effect])))
        for selection in product(*choices):
            number += 1
            if number > 128:
                raise Unsupported('linear branch limit')
            wait = z3.Real('initial_wait')
            constraints, qs = [wait >= 0], []
            energy, time = real(e0), real(t0)+wait
            for k, ((site,effect),(i,j,m)) in enumerate(zip(plan, selection)):
                leg = legs[anchors[k], site]
                arrival, incoming = time+real(leg[0]), energy-real(rate*leg[1])
                constraints += [incoming >= real(emin), incoming <= real(B)]
                if effect != 'S':
                    energy = z3.Real(f'energy_{k}')
                    lo, hi, slope, intercept = curve[i]
                    a, b, slope2, intercept2 = curve[j]
                    constraints += [incoming >= real(lo),incoming <= real(hi),
                        energy >= real(a),energy <= real(b),energy >= incoming,
                        energy >= real(emin),energy <= real(B)]
                    delta = real(slope2)*energy+real(intercept2)-real(slope)*incoming-real(intercept)
                    qs.append(energy-incoming)
                else:
                    energy = incoming
                if effect == 'C':
                    forms = [arrival+real(h)+delta]
                else:
                    schedule = snapshot['schedule']
                    a,b,D = (exact(schedule[x]) for x in ('a','b','D'))
                    constraints += [arrival <= real(b-h)]
                    forms = [real(a+D), arrival+real(h+D)]
                    if effect == 'CS':
                        forms.append(arrival+real(h)+delta)
                time = z3.Real(f'time_{k}')
                constraints += [time == forms[m], *[time >= v for v in forms]]
            last = legs[anchors[-2], anchors[-1]]
            constraints += [energy-real(rate*last[1]) >= real(reserve)]
            J = time+real(last[0]-t0+penalty*len(plan))
            Q = z3.Sum(qs) if qs else real(0)
            yield dict(plan=plan,P=constraints,strict=[q>0 for q in qs],J=J,Q=Q,wait=wait,charges=qs)


def replay(snapshot, plan, charges, initial_wait=0):
    """Concrete Fraction equations, independent of SMT expressions and HiRoute."""
    legs = canonical_legs(snapshot)
    energy, time = exact(snapshot['initial_energy_kwh']), exact(snapshot['departure_time_s'])+exact(initial_wait)
    if exact(initial_wait) < 0:
        raise ValueError('negative initial wait')
    floor, capacity, rate, h = [exact(snapshot[k]) for k in (
        'minimum_energy_kwh','capacity_kwh','consumption_kwh_per_m','stop_overhead_s')]
    remaining, anchor, qi, total, trace = snapshot['initial_remaining_schedule'],snapshot['origin'],0,F(0),[]
    def phi(e):
        for lo,hi,slope,intercept in snapshot['charging_curve']:
            lo,hi,slope,intercept=map(exact,(lo,hi,slope,intercept))
            if lo<=e<=hi:return slope*e+intercept
        raise ValueError('energy outside curve')
    for site,effect in plan:
        if effect not in snapshot['site_capabilities'][site]:raise ValueError('illegal effect')
        leg=legs[anchor,site];time+=leg[0];energy-=rate*leg[1]
        if not floor<=energy<=capacity:raise ValueError('arrival energy')
        incoming,arrival=energy,time
        if effect!='S':
            q=exact(charges[qi]);qi+=1
            if q<=0 or energy+q>capacity:raise ValueError('strict charge/capacity')
            delta=phi(energy+q)-phi(energy);energy+=q;total+=q
        if effect=='C':time+=h+delta
        else:
            if not remaining:raise ValueError('repeated activity')
            a,b,D=(exact(snapshot['schedule'][x]) for x in ('a','b','D'))
            if arrival>b-h:raise ValueError('latest activity start')
            time=max(a+D,arrival+h+D,arrival+h+delta if effect=='CS' else arrival+h+D)
            remaining=0
        trace.append((site,effect,incoming,arrival,energy,time));anchor=site
    leg=legs[anchor,snapshot['destination']];time+=leg[0];energy-=rate*leg[1]
    if remaining or energy<exact(snapshot['destination_reserve_kwh']) or qi!=len(charges):
        raise ValueError('terminal/charge count')
    J=time-exact(snapshot['departure_time_s'])+exact(snapshot['stop_penalty_s'])*len(plan)
    return dict(key=(J,total,len(plan),tuple(plan)),final_energy=energy,trace=trace)


def solve(snapshot, audit_dir=None):
    engine = Engine(audit_dir); candidates=[]; rejected=0
    for branch in branches(snapshot,canonical_legs(snapshot)):
        # Critical: test the whole strict branch before considering its closure.
        sample=engine.feasible(branch['P']+branch['strict'],'strict-branch')
        if sample is None:
            rejected+=1;continue
        branch['primary']=engine.minimum(branch['P'],branch['J'],'closed-J')
        candidates.append(branch)
    metadata=dict(external_solver='Z3 '+z3.get_version_string(),linear_branches=len(candidates)+rejected,
        strict_empty_branches=rejected,checks=engine.audit,depth_limit=snapshot['depth_limit'],domain='explicit finite tiny domain')
    if not candidates:return dict(status='infeasible',**metadata)
    j=min(b['primary'] for b in candidates)
    primary=[]
    for b in candidates:
        if b['primary']!=j:continue
        b['Pj']=b['P']+[b['J']==real(j)]
        if engine.feasible(b['Pj']+b['strict'],'strict-J-face') is not None:
            b['secondary']=engine.minimum(b['Pj'],b['Q'],'closed-Q');primary.append(b)
    if not primary:return dict(status='primary_unattained',primary_infimum=j,**metadata)
    q=min(b['secondary'] for b in primary);attained=[]
    for b in primary:
        if b['secondary']!=q:continue
        model=engine.feasible(b['Pj']+b['strict']+[b['Q']==real(q)],'strict-JQ-face')
        if model is not None:attained.append((len(b['plan']),b['plan'],b,model))
    if not attained:return dict(status='secondary_unattained',primary_value=j,primary_infimum=j,secondary_infimum=q,**metadata)
    _,plan,b,model=min(attained,key=lambda row:row[:2])
    charges=[fraction(model.eval(x,model_completion=True)) for x in b['charges']]
    wait=fraction(model.eval(b['wait'],model_completion=True))
    checked=replay(snapshot,plan,charges,wait)
    if checked['key']!=(j,q,len(plan),plan):raise Unknown('independent replay mismatch')
    return dict(status='attained_optimum',key=checked['key'],witness=dict(plan=plan,charges=charges,initial_wait=wait),replay=checked,**metadata)
