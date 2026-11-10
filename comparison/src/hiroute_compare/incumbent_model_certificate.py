"""Exact total-assignment certificate for the original supported-disjunction.

Never calls a solver/tactic, adds a constraint, or reuses a solver result.
Unsupported operators (including arrays) and unbound constants fail closed.
"""
from fractions import Fraction as F
import hashlib
import json
import z3


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def evaluate_assertions(assertions,bindings,check=lambda:None,max_nodes=2000000):
    if type(max_nodes) is not int or max_nodes<1:raise ValueError('positive node quota required')
    roots=tuple(assertions)
    if not roots or any(not z3.is_bool(e) for e in roots):raise ValueError('Boolean assertion roots required')
    ctx=roots[0].ctx
    if any(e.ctx!=ctx for e in roots):raise ValueError('mixed contexts')
    assigned={};assignment=[]
    for symbol,value in bindings:
        check()
        if not z3.is_const(symbol) or symbol.ctx!=ctx or symbol.decl().kind()!=z3.Z3_OP_UNINTERPRETED:raise ValueError('free constant binding required')
        kind=symbol.sort().kind()
        if kind==z3.Z3_INT_SORT:
            if type(value) is not int:raise ValueError('exact integer binding required')
        elif kind==z3.Z3_REAL_SORT:
            if type(value) not in (int,F):raise ValueError('exact rational binding required')
            value=F(value)
        elif kind==z3.Z3_BOOL_SORT:
            if type(value) is not bool:raise ValueError('Boolean binding required')
        else:raise ValueError('unsupported binding sort')
        key=symbol.get_id()
        if key in assigned:raise ValueError('duplicate binding')
        assigned[key]=value;assignment.append(dict(name=str(symbol.decl().name()),sort=str(symbol.sort()),value=str(value)))
    values={};hashes={};used=set()
    for root in roots:
        stack=[(root,False)]
        while stack:
            check();e,ready=stack.pop();key=e.get_id()
            if key in values:continue
            if not z3.is_app(e) or e.sort().kind() not in (z3.Z3_BOOL_SORT,z3.Z3_INT_SORT,z3.Z3_REAL_SORT):raise ValueError('unsupported AST/sort')
            if not ready:
                stack.append((e,True));stack.extend((c,False) for c in reversed(e.children()));continue
            kind=e.decl().kind();args=[values[c.get_id()] for c in e.children()];token=None
            if kind==z3.Z3_OP_UNINTERPRETED:
                if e.num_args() or key not in assigned:raise ValueError('unbound/unsupported constant or function')
                value=assigned[key];used.add(key);token=str(e.decl().name())
            elif z3.is_int_value(e):value=e.as_long();token=str(value)
            elif z3.is_rational_value(e):value=F(e.numerator_as_long(),e.denominator_as_long());token=str(value)
            elif z3.is_true(e):value=True
            elif z3.is_false(e):value=False
            elif kind==z3.Z3_OP_ITE:value=args[1] if args[0] else args[2]
            elif kind==z3.Z3_OP_AND:value=all(args)
            elif kind==z3.Z3_OP_OR:value=any(args)
            elif kind==z3.Z3_OP_NOT:value=not args[0]
            elif kind==z3.Z3_OP_IMPLIES:value=not args[0] or args[1]
            elif kind==z3.Z3_OP_XOR:value=sum(args)%2==1
            elif kind==z3.Z3_OP_EQ:value=args[0]==args[1]
            elif kind==z3.Z3_OP_DISTINCT:value=len(set(args))==len(args)
            elif kind==z3.Z3_OP_LE:value=args[0]<=args[1]
            elif kind==z3.Z3_OP_GE:value=args[0]>=args[1]
            elif kind==z3.Z3_OP_LT:value=args[0]<args[1]
            elif kind==z3.Z3_OP_GT:value=args[0]>args[1]
            elif kind==z3.Z3_OP_ADD:value=sum(args)
            elif kind==z3.Z3_OP_SUB:value=args[0]-sum(args[1:])
            elif kind==z3.Z3_OP_UMINUS:value=-args[0]
            elif kind==z3.Z3_OP_MUL:
                value=1
                for a in args:value*=a
            elif kind==z3.Z3_OP_DIV:
                if args[1]==0:raise ValueError('undefined division')
                value=F(args[0])/F(args[1])
            elif kind==z3.Z3_OP_TO_REAL:value=F(args[0])
            else:raise ValueError('unsupported operator')
            values[key]=value;hashes[key]=digest([kind,str(e.sort()),token,[hashes[c.get_id()] for c in e.children()]])
            if len(values)>max_nodes:raise ValueError('certificate node quota')
    if used!=set(assigned):raise ValueError('unused bindings')
    if any(type(values[e.get_id()]) is not bool or not values[e.get_id()] for e in roots):raise ValueError('false original assertion')
    assignment.sort(key=lambda x:(x['name'],x['sort']))
    return dict(assertions=len(roots),unique_nodes=len(values),formula_sha256=digest([hashes[e.get_id()] for e in roots]),
                assignment=assignment,assignment_sha256=digest(assignment),all_assertions_exactly_true=True)


def incumbent_bindings(m,x,y,table,parameters,witness,check=lambda:None):
    from .exact_physical_adapter import replay,validate,q
    if m.lookup.table is not table or validate(table,parameters).sha256!=m.p.sha256:raise ValueError('model/input/physics identity')
    if x.get('encoding_owner') is not m or y.get('encoding_owner') is not m or x is y:raise ValueError('two owned continuous copies required')
    checked=replay(table,parameters,witness['plan'],witness['charges'],witness.get('initial_wait',0))
    m.lookup.resolve(m.ground_trace,witness['plan'])
    plan=tuple(tuple(a) for a in witness['plan']);ranks={a:i for i,a in enumerate(m.actions,1)}
    if len(plan)>len(m.choices):raise ValueError('witness exceeds complete slots')
    wait=q(witness.get('initial_wait',0));bindings=[(x['wait'],wait),(y['wait'],wait)]
    energy=m.p.get('initial_energy_kwh');time=m.p.get('departure_time_s')+wait
    h=m.p.get('stop_overhead_s')
    def piece(e):
        for i,(lo,hi,slope,intercept) in enumerate(m.p.curve):
            if lo<=e<=hi:return i
        raise ValueError('charging piece missing')
    def phi(e):
        lo,hi,slope,intercept=m.p.curve[piece(e)];return slope*e+intercept
    for i,choice in enumerate(m.choices):
        check();rank=0;incoming_piece=outgoing_piece=maximum=0
        if i<len(plan):
            rank=ranks[plan[i]];effect=plan[i][1];row=checked['trace'][i]
            energy,time=row['outgoing'],row['finish']
            if effect in ('C','CS'):
                incoming_piece=piece(row['incoming']);outgoing_piece=piece(row['outgoing'])
            if effect in ('S','CS'):
                a,b,D=m.p.schedule;forms=[a+D,row['arrival']+h+D]
                if effect=='CS':forms.append(row['arrival']+h+phi(row['outgoing'])-phi(row['incoming']))
                maximum=forms.index(time)
        bindings.extend(((choice,rank),(m.ins[i],incoming_piece),(m.outs[i],outgoing_piece),(m.maxima[i],maximum)))
        for state in (x,y):
            out,finish=state['state_symbols'][i];bindings.extend(((out,energy),(finish,time)))
    return bindings,checked


def certify(m,x,y,table,parameters,witness,assertions,check=lambda:None):
    expected=m.G+x['P']+y['P']+y['strict'];roots=tuple(assertions)
    if len(roots)!=len(expected) or any(not z3.eq(a,b) for a,b in zip(roots,expected)):raise ValueError('original supported assertions changed')
    bindings,replayed=incumbent_bindings(m,x,y,table,parameters,witness,check)
    checked=evaluate_assertions(roots,bindings,check)
    return dict(schema='hiroute.exact_incumbent_certificate.v1',status='VERIFIED_NONEMPTY_ONLY',
                table_sha256=table.payload_sha256,physics_sha256=m.p.sha256,complete_slots=len(m.choices),
                replayed_key=str(replayed['key']),**checked)
