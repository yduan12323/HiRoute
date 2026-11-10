"""Tiny-development exact SAT witness extraction; never calls a solver."""
import hashlib,json,os,tempfile
from pathlib import Path
from fractions import Fraction as F
import z3
from .exact_physical_adapter import real,replay,validate,fraction
from .incumbent_model_certificate import evaluate_assertions,digest


def constants(roots,check):
    seen=set();symbols={};stack=list(roots)
    while stack:
        check();e=stack.pop()
        if e.get_id() in seen:continue
        seen.add(e.get_id())
        if not z3.is_app(e):raise ValueError('unsupported AST')
        if e.decl().kind()==z3.Z3_OP_UNINTERPRETED:
            if e.num_args():raise ValueError('uninterpreted function')
            symbols[e.get_id()]=e
        stack.extend(e.children())
    return tuple(symbols.values())


def exact_value(value,sort):
    if sort.kind()==z3.Z3_BOOL_SORT:
        if z3.is_true(value):return True
        if z3.is_false(value):return False
    elif sort.kind()==z3.Z3_INT_SORT and z3.is_int_value(value):return value.as_long()
    elif sort.kind()==z3.Z3_REAL_SORT and z3.is_rational_value(value):return F(value.numerator_as_long(),value.denominator_as_long())
    raise ValueError('unbound/nonrational/unsupported model value')


def publish_unverified(path,payload,check):
    """Exclusive complete file publication; candidate is never a certificate."""
    path=Path(path);raw=json.dumps(payload,sort_keys=True,separators=(',',':')).encode()
    wrapper=dict(status='UNVERIFIED_CANDIDATE',payload=payload,payload_sha256=hashlib.sha256(raw).hexdigest())
    fd,name=tempfile.mkstemp(prefix='.candidate-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as stream:
            json.dump(wrapper,stream,sort_keys=True);stream.write('\n');stream.flush();os.fsync(stream.fileno())
        check();os.link(name,path)
    finally:Path(name).unlink()
    check()


def certificate(m,x,y,table,parameters,bound,roots,bindings,check=lambda:None):
    if type(bound) not in (int,F) or F(bound)!=m.upper:raise ValueError('midpoint requires bound equal original upper')
    if m.lookup.table is not table or validate(table,parameters).sha256!=m.p.sha256:raise ValueError('input identity')
    if x is y or any(s.get('encoding_owner') is not m for s in (x,y)):raise ValueError('owned distinct states required')
    expected=m.G+x['P']+y['P']+y['strict']+[x['J']<real(bound)]
    if len(roots)!=len(expected) or any(not z3.eq(a,b) for a,b in zip(roots,expected)):raise ValueError('original bound roots changed')
    verified=evaluate_assertions(roots,bindings,check)
    values={s.get_id():v for s,v in bindings}
    def evaluate(expr,bs):
        check();pairs=[(s,z3.BoolVal(v) if type(v) is bool else z3.IntVal(v) if s.sort().kind()==z3.Z3_INT_SORT else real(v)) for s,v in bs]
        return exact_value(z3.simplify(z3.substitute(expr,*pairs)),expr.sort())
    jx,jy=evaluate(x['J'],bindings),evaluate(y['J'],bindings)
    if not jx<bound or not jy<=bound:raise ValueError('interpolation objective assumptions')
    # Shared discrete choices select a common affine fiber. Copy all continuous
    # coordinates, including inactive suffixes and initial wait, at weight1/2.
    mixed=dict(values)
    pairs=[(x['wait'],y['wait'])]
    for xs,ys in zip(x['state_symbols'],y['state_symbols']):pairs.extend(zip(xs,ys))
    for a,b in pairs:
        check();v=(F(values[a.get_id()])+F(values[b.get_id()]))/2
        mixed[a.get_id()]=mixed[b.get_id()]=v
    bs=[(s,mixed[s.get_id()]) for s,_ in bindings]
    # Re-evaluation checks the construction, not only the convexity argument.
    checked=evaluate_assertions([*roots,*x['strict']],bs,check)
    H=evaluate(m.H,bs)
    if type(H) is not int or not 0<=H<=len(m.choices):raise ValueError('invalid stop count')
    ranks=[evaluate(c,bs) for c in m.choices]
    if any(type(r) is not int or not 1<=r<=len(m.actions) for r in ranks[:H]) or any(r!=0 for r in ranks[H:]):raise ValueError('invalid active prefix')
    plan=tuple(m.actions[r-1] for r in ranks[:H]);m.lookup.resolve(m.ground_trace,plan)
    charges=[evaluate(x['qs'][i],bs) for i,(_,effect) in enumerate(plan) if effect in ('C','CS')]
    wait=evaluate(x['wait'],bs);replayed=replay(table,parameters,plan,charges,wait)
    j,q=evaluate(x['J'],bs),evaluate(x['Q'],bs)
    if replayed['key']!=(j,q,H,plan) or not j<bound:raise ValueError('independent replay discrepancy')
    check()
    return dict(status='VERIFIED_ATTAINED_IMPROVEMENT',optimality_certified=False,full_key_optimality_certified=False,
                bound=str(bound),primary_value=str(j),weight='1/2',witness=dict(plan=plan,charges=[str(v) for v in charges],initial_wait=str(wait)),
                original_assignment_sha256=verified['assignment_sha256'],mixed_assignment_sha256=checked['assignment_sha256'],
                formula_sha256=verified['formula_sha256'],table_sha256=table.payload_sha256,physics_sha256=m.p.sha256)


def extract(m,x,y,table,parameters,bound,roots,model,path,check=lambda:None):
    symbols=constants(roots,check);bindings=[]
    for symbol in symbols:
        check();bindings.append((symbol,exact_value(model.eval(symbol,model_completion=False),symbol.sort())))
    payload=dict(bound=str(bound),table_sha256=table.payload_sha256,physics_sha256=m.p.sha256,
                 assignment=[dict(name=str(s.decl().name()),sort=str(s.sort()),value=str(v)) for s,v in bindings])
    publish_unverified(path,payload,check)
    return certificate(m,x,y,table,parameters,bound,roots,bindings,check)


def publish_verified_result(path,result,check):
    """Publish only a replay-verified result; outer admission must still complete.

    A hard-killed consumer has no successful terminal receipt, even if this
    file survived. Late ordinary exceptions remove only this newly linked file.
    """
    if result.get('status')!='VERIFIED_ATTAINED_IMPROVEMENT' or result.get('optimality_certified') is not False:
        raise ValueError('verified replay result required')
    path=Path(path);check();raw=json.dumps(result,sort_keys=True,separators=(',',':')).encode()
    digest=hashlib.sha256(raw).hexdigest()
    payload=dict(verification='VERIFIED_REPLAY',requires_successful_consumer_terminal=True,
                 result=result,result_sha256=digest)
    fd,name=tempfile.mkstemp(prefix='.verified-witness-',dir=path.parent);published=False
    try:
        with os.fdopen(fd,'w') as stream:
            json.dump(payload,stream,sort_keys=True);stream.write('\n');stream.flush();os.fsync(stream.fileno())
        check();os.link(name,path);published=True;check()
        return dict(file=path.name,result_sha256=digest)
    except BaseException:
        if published:path.unlink()
        raise
    finally:Path(name).unlink()
