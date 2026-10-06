"""Candidate-side exact epigraph model for one checked prefix and suffix word.

Supports one affine charging segment only. There is no LP execution here.
The independent checker reconstructs this mathematics in separate code.
"""
from fractions import Fraction as F
from validation.family5 import CheckedBundle
from validation.family5.checker import require,canonical


def plain(value):
    import json
    return json.loads(canonical(value))


def checked_word(ctx,family_id,word):
    require(isinstance(ctx,CheckedBundle),'checked family bundle required')
    require(type(family_id) is str and family_id in ctx._pieces,'unknown original prefix family')
    p=ctx._pieces[family_id];ph=ctx._physics
    require(len(ph.curve)==1 and ph.curve[0][0]==0 and ph.curve[0][1]==ph.capacity,'only one full affine charging segment is supported')
    require(type(word) in (list,tuple) and 1<=len(word)<=ph.bound-p.state[2],'invalid suffix stop count')
    require(p.state[0]!=ph.destination,'no continuation from terminal prefix')
    expected_anchor=ph.origin if p.state[2]==0 else ph.anchors[p.pi[-1][0]]
    require(p.state[0]==expected_anchor,'prefix must be initial or post-stop physical anchor')
    remaining=p.state[1];normalized=[]
    for action in word:
        require(type(action) in (list,tuple) and len(action)==2,'invalid suffix action')
        site,effect=action
        require(type(site) is str and type(effect) is str and effect in ph.sites.get(site,()),'unavailable suffix action')
        require(ph.anchors[site]!=ph.destination,'terminal Site action forbidden')
        if effect in ('S','CS'):
            require(remaining==1 and ph.schedule is not None,'service already fulfilled or missing')
            remaining=0
        normalized.append((site,effect))
    require(remaining==0,'suffix has not fulfilled required service')
    return p,ph,tuple(normalized)


def legal_words(ctx,family_id,first_actions):
    p=ctx._pieces[family_id];ph=ctx._physics
    remaining_bound=ph.bound-p.state[2]
    require(remaining_bound>=1,'no remaining suffix stop slot')
    first=[tuple(a) for a in first_actions]
    require(len(first)==len(set(first)),'duplicate mandatory first actions')
    words=[]
    def actions(remaining):
        return sorted((site,effect) for site,effects in ph.sites.items()
                      if ph.anchors[site]!=ph.destination for effect in set(effects)
                      if effect=='C' or remaining==1)
    def visit(prefix,remaining):
        choices=first if not prefix else actions(remaining)
        for site,effect in choices:
            require((site,effect) in actions(remaining),'illegal first action restriction')
            next_remaining=remaining if effect=='C' else 0
            word=prefix+((site,effect),)
            if next_remaining==0:words.append(word)
            if len(word)<remaining_bound:visit(word,next_remaining)
    visit((),p.state[1])
    return tuple(words)


def build_model(ctx,family_id,word):
    p,ph,word=checked_word(ctx,family_id,word)
    meta=dict(schema='family5-suffix-model-v1',family_id=family_id,word=plain(word),
              case_sha256=ctx.summary['case_sha256'],family_bundle_sha256=ctx.summary['bundle_sha256'],
              H=p.state[2]+len(word),pi=plain(p.pi+word),exclusion=None,lp=None)
    anchor=p.state[0];legs=[]
    for i,target in enumerate([ph.anchors[site] for site,_ in word]+[ph.destination]):
        leg=ph.legs.get((anchor,target))
        if leg is None:
            meta['exclusion']=dict(kind='unreachable_selected_leg',leg_index=i,source=anchor,target=target)
            return meta
        legs.append(leg);anchor=target
    m=len(word);n=2+2*m
    names=['E_prefix','T_prefix']
    for i in range(m):names.extend((f'q_{i}',f'T_{i+1}'))
    rows=[]
    def row(label,coefficients,rhs,strict=False):
        require(type(strict) is bool,'strict flag must be boolean')
        vector=[F(0)]*n
        for index,value in coefficients.items():vector[index]+=F(value)
        rows.append(dict(label=label,coefficients=list(map(str,vector)),rhs=str(F(rhs)),strict=strict))
    row('prefix_energy_lower',{0:-1},-p.lo,not p.lc)
    row('prefix_energy_upper',{0:1},p.hi,not p.rc)
    row('prefix_time',{0:p.m,1:-1},-p.b,not p.chi)
    energy=F(0);charge_indices=[];curve_slope=ph.curve[0][2]
    for i,((site,effect),leg) in enumerate(zip(word,legs)):
        dt,consumption=leg[:2];energy+=consumption
        qi=2+2*i;ti=qi+1;previous=1 if i==0 else ti-2
        row(f'arrival_floor:{i}',{0:-1,**{j:-1 for j in charge_indices}},-ph.floor-energy)
        charge_indices.append(qi)
        row(f'departure_capacity:{i}',{0:1,**{j:1 for j in charge_indices}},ph.capacity+energy)
        if effect in ('C','CS'):
            row(f'charge_positive:{i}',{qi:-1},0,True)
            row(f'charge_completion:{i}',{previous:1,ti:-1,qi:curve_slope},-dt-ph.overhead)
        else:
            row(f'service_charge_zero_upper:{i}',{qi:1},0)
            row(f'service_charge_zero_lower:{i}',{qi:-1},0)
        if effect in ('S','CS'):
            a,b,D=ph.schedule
            row(f'service_window_nonempty:{i}',{},b-a)
            row(f'latest_service_start:{i}',{previous:1},b-dt-ph.overhead)
            row(f'service_release_completion:{i}',{ti:-1},-a-D)
            row(f'service_own_completion:{i}',{previous:1,ti:-1},-dt-ph.overhead-D)
    energy+=legs[-1][1]
    row('terminal_reserve',{0:-1,**{j:-1 for j in charge_indices}},-ph.reserve-energy)
    J=[F(0)]*n;J[-1]=F(1)
    Q=[F(0)]*n;Q[0]=F(1)
    for j in charge_indices:Q[j]=F(1)
    penalty=F(ph.case['lambda_stop_s'])
    meta['lp']=dict(variables=names,rows=rows,
                   J=dict(coefficients=list(map(str,J)),constant=str(legs[-1][0]-ph.start+penalty*meta['H'])),
                   Q=dict(coefficients=list(map(str,Q)),constant=str(p.rho)))
    return meta


def query_models(checked_trace,query_seq):
    require(type(query_seq) is int,'query occurrence must be an exact integer')
    queries=checked_trace.export_queries()
    matches=[q for q in queries if q['query_seq']==query_seq]
    require(len(matches)==1,'query occurrence missing or ambiguous')
    query=matches[0];models=[]
    for family_id in query['family_ids']:
        for word in legal_words(checked_trace.bundle,family_id,query['actions']):
            models.append(build_model(checked_trace.bundle,family_id,word))
    return query,models
