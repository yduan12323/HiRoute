"""Pure planning-value policy definitions. No optimizer or result input."""
from fractions import Fraction


def number(value):
    if type(value) not in (str,int) and not isinstance(value,Fraction):
        raise TypeError('exact values required')
    return Fraction(value)


def action_mask(capabilities,policy,activity_site=None):
    legal={(site,effect) for site,effects in capabilities.items() for effect in effects}
    if any(effect not in ('C','S','CS') for _,effect in legal):raise ValueError('capability')
    if policy=='separated_no_overlap':
        return frozenset((s,e) for s,e in legal if e!='CS')
    if policy=='activity_first_fixed_site':
        if not any(s==activity_site and e in ('S','CS') for s,e in legal):
            raise ValueError('selected Site has no legal activity effect')
        return frozenset((s,e) for s,e in legal if e=='C' or s==activity_site)
    raise ValueError('unknown policy')


def choose_activity(capabilities,time_features,*,start_time,overhead,penalty,a,b,duration):
    """Energy-relaxed time ranking, not an executable plan or an incumbent.

    None in an explicit feature record means proved directed unreachability;
    missing records are errors. No energy/charge/solver outcome is accepted.
    """
    t0,h,lam,a,b,D=map(number,(start_time,overhead,penalty,a,b,duration))
    if h<=0 or lam<0 or D<0 or a>b:raise ValueError('time parameters')
    ranked=[]
    for site,effects in capabilities.items():
        if not set(effects)&{'S','CS'}:continue
        if site not in time_features:raise ValueError('missing directed time features')
        tos,tsd=time_features[site]
        if tos is None or tsd is None:continue
        tos,tsd=map(number,(tos,tsd))
        if min(tos,tsd)<0:raise ValueError('negative time feature')
        if t0+tos>b-h:continue
        ranked.append((max(a+D,t0+tos+h+D)+tsd+lam,site))
    return None if not ranked else min(ranked)[1]


def charging_activity_overlap(*,arrival,overhead,charge_duration,a,service_duration):
    arrival,h,delta,a,D=map(number,(arrival,overhead,charge_duration,a,service_duration))
    if min(h,delta,D)<0:raise ValueError('negative duration')
    charge_start=arrival+h;service_start=max(a,charge_start)
    return max(Fraction(0),min(charge_start+delta,service_start+D)-max(charge_start,service_start))
