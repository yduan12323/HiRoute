"""Candidate v2 physical lift; replay uses the original charging primitive."""
from fractions import Fraction as F
from validation.family5 import reconstruct
from validation.family5.checker import require
from .convex_model import checked_word,build_model
from .model import plain


def _event(effect,site,t,u,x,y):
    return dict(effect=effect,site=site,arrival_time=str(t),departure_time=str(u),
                arrival_energy=str(x),departure_energy=str(y))


def lift_point(ctx,model,point):
    require(model==build_model(ctx,model['family_id'],model['word'],model['arrival_bands']),
            'v2 point model differs from original family and band assignment')
    p,ph,word=checked_word(ctx,model['family_id'],model['word'])
    require(all(type(x) not in (bool,float) for x in point),'suffix point must be exact')
    point=tuple(map(F,point));require(len(point)==2+2*len(word),'wrong suffix LP point dimension')
    for row in model['lp']['rows']:
        value=sum((F(c)*x for c,x in zip(row['coefficients'],point)),F(0));rhs=F(row['rhs'])
        require(value<rhs if row['strict'] else value<=rhs,'LP point violates original strict row',row=row['label'])
    prefix=reconstruct(ctx,model['family_id'],str(point[0]),str(point[1]))
    w=prefix['witness'];time=F(w['time']);energy=F(w['energy']);rho=F(w['rho'])
    anchor=w['state'][0];remaining=w['state'][1];pi=[list(a) for a in w['pi']];events=[]
    for i,(site,effect) in enumerate(word):
        target=ph.anchors[site];leg=ph.legs[anchor,target]
        arrived_time=time+leg[0];arrived_energy=energy-leg[1]
        require(arrived_energy>=ph.floor,'suffix selected leg violates energy floor')
        events.append(_event('D',target,time,arrived_time,energy,arrived_energy));rho+=leg[1]
        q=point[2+2*i];departed_energy=arrived_energy+q
        release=arrived_time+ph.overhead
        if effect=='S':
            require(q==0,'S charges energy');charge_done=release
        else:
            require(q>0,'charge is not strictly positive')
            charge_done=release+ph.primitive(departed_energy)-ph.primitive(arrived_energy)
        if effect in ('S','CS'):
            a,b,D=ph.schedule;service_start=max(a,release)
            require(remaining==1 and service_start<=b,'actual scheduled suffix infeasible')
            service_done=service_start+D;remaining=0
        else:service_done=release
        finished=max(charge_done,service_done)
        require(departed_energy<=ph.capacity and finished<=point[3+2*i],'actual stop exceeds energy/time budget')
        events.append(_event(effect,site,arrived_time,finished,arrived_energy,departed_energy))
        time,energy,anchor=finished,departed_energy,target;pi.append([site,effect])
    leg=ph.legs[anchor,ph.destination]
    events.append(_event('D',ph.destination,time,time+leg[0],energy,energy-leg[1]))
    time+=leg[0];energy-=leg[1];rho+=leg[1]
    require(remaining==0 and energy>=ph.reserve,'terminal suffix requirements unmet')
    full=dict(time=str(time),energy=str(energy),rho=str(rho),pi=pi,
              state=[ph.destination,0,len(pi)],events=plain(w['events'])+events)
    return dict(prefix=prefix,suffix_events=events,witness=full)


def result_contract(result,epsilon='1/1000000'):
    status=result['status']
    if status=='attained_optimum':
        return dict(kind='minimum',J=result['J'],Q_total=result['Q_total'],H=result['H'],pi=result['site_action_tuple'])
    if type(epsilon) in (bool,float):raise ValueError('Approach epsilon must be exact')
    epsilon=F(epsilon)
    if epsilon<=0:raise ValueError('Approach epsilon must be positive')
    if status=='primary_unattained':return dict(kind='primary_approach',J_inf=result['primary_infimum'],epsilon=str(F(epsilon)))
    if status=='secondary_unattained':return dict(kind='secondary_approach',J=result['J'],Q_inf=result['secondary_infimum'],epsilon=str(F(epsilon)))
    raise ValueError('Empty regime has no physical witness contract')
