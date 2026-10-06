"""Deployable bounds: this module imports no oracle tables or oracle bounds."""
import math
import numpy as np

BUCKETS=('Ccap','S0cap','SCcap')
ALT_ABS=1e-6
ALT_REL=2e-8
COST_SAFETY=1e-5


def select_landmarks(nodes,scc_nodes):
    """Coordinates only; directed SCC is candidate domain, never query domain."""
    if len(scc_nodes)<8:raise ValueError('Eight unique SCC landmarks required')
    lon=nodes.lon.to_numpy();lat=nodes.lat.to_numpy()
    x=np.radians(lon-lon.mean())*np.cos(np.radians(lat.mean()))*6371008.8
    y=np.radians(lat-lat.mean())*6371008.8
    ids=nodes.osm_node_id.to_numpy();chosen=[]
    for dx,dy in [(1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)]:
        norm=math.hypot(dx,dy);score=(dx*x[scc_nodes]+dy*y[scc_nodes])/norm
        order=np.lexsort((scc_nodes,ids[scc_nodes],-score))
        chosen.append(next(int(scc_nodes[i]) for i in order if int(scc_nodes[i]) not in chosen))
    return chosen


def bucket_flags(site):
    c='charge' in site.transport_capabilities;s=site.support.meal_count>=1
    return (c,s and not c,s and c)


def alt(summary,point,outbound=False):
    """summary [landmarks, min_from,max_from,min_to,max_to]; point [2,L].

    Each finite difference is adjusted outward by 1e-6 + 2e-8*(|a|+|b|)
    in metric units, followed by nextafter(-inf). Never subtract infinities.
    """
    pairs=((point[0],summary[:,1]),(summary[:,2],point[1])) if outbound else ((summary[:,0],point[0]),(point[1],summary[:,3]))
    result=0.
    for a,b in pairs:
        valid=np.isfinite(a)&np.isfinite(b)
        if valid.any():
            aa=a[valid];bb=b[valid]
            values=np.nextafter(aa-bb-(ALT_ABS+ALT_REL*(abs(aa)+abs(bb))),-np.inf)
            result=max(result,float(values.max()))
    return result


def cost_bound(metric_bounds,bucket,trip,ev,schedule,config,parent=-math.inf):
    tm,tp,dm,dp=metric_bounds;k=ev.consumption_kwh_km/1000
    reason=None
    envelope_tol=max(1e-7,1e-8+(trip.mobility_budget_s or 0)*1e-10)
    if trip.mobility_budget_s is not None and tm+tp>trip.mobility_budget_s+envelope_tol:reason='envelope'
    elif trip.initial_energy_kwh-k*dm<ev.minimum_energy_kwh-1e-8:reason='inbound_energy'
    elif bucket!=1 and ev.capacity_kwh-k*dp<ev.terminal_floor-1e-8:reason='outbound_energy'
    elif bucket==1 and trip.initial_energy_kwh-k*(dm+dp)<ev.terminal_floor-1e-8:reason='noncharger_energy'
    ready=trip.start_time_s+tm+config.overhead_s
    y=max(schedule.window_start_s,ready) if schedule else None
    if schedule and y>schedule.window_end_s+1e-8 and reason is None:reason='schedule'
    q=max(0.,ev.terminal_floor+k*(dm+dp)-trip.initial_energy_kwh) if bucket!=1 else 0.
    charge=3600*q/100.
    completion=ready+charge if bucket==0 else y+schedule.duration_s if bucket==1 else max(ready+charge,y+schedule.duration_s)
    raw=completion-trip.start_time_s+tp+config.lambda_stop_s
    safe=np.nextafter(raw-COST_SAFETY,-np.inf)
    return dict(tm=tm,tp=tp,dm=dm,dp=dp,q_lower=q,charging_lower=charge,
                raw_cost=raw,raw_safe_cost=float(safe),lower=max(float(safe),parent),infeasible=reason)


def reduction(numerator,denominator):
    return None if denominator==0 else 1-numerator/denominator


def micro_reduction(numerators,denominators):
    return reduction(sum(numerators),sum(denominators))
