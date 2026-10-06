"""B0 component-minimum bound and physical-unit oracle RCC.

Times seconds; lengths metres; energies kWh. Safe lower bounds subtract 1e-6 s
(larger than the accepted 1e-7 cost bin). Margin tests do NOT add tolerance:
an equality passes, a negative slack is inconclusive. Verification tolerances
are 1e-8 kWh and 2e-6 s, not additional pruning permission.
"""
import numpy as np

SAFE_TAU = 1e-6
CHECK_TIME_TOL = 2e-6
CHECK_ENERGY_TOL = 1e-8


def oracle_bound(frame, role, trip, ev, curve, schedule, config):
    if not len(frame):
        raise ValueError('Empty role View has no RCC')
    if role not in ('C','S','CS') or not frame.role.eq(role).all():
        raise ValueError('View must have one exact performed role')
    if config.distance_penalty_s_per_km or (schedule and (not schedule.hard or not schedule.compatible_with_charging)):
        raise ValueError('Outside B0 primary theorem domain')
    lo=frame[['tm','tp','lm','lp']].min().to_numpy(float)
    omega=frame[['tm','tp','lm','lp']].max().to_numpy(float)-lo
    tm,tp,lm,lp=lo; wt,wp,wl,wr=omega
    k=ev.consumption_kwh_km/1000
    arr=trip.initial_energy_kwh-k*lm; req=ev.terminal_floor+k*lp
    q=max(0.,req-arr)
    charging='C' in role; scheduled='S' in role
    c=curve.duration_s(max(0.,arr), min(ev.capacity_kwh,max(arr,req)),ev.capacity_kwh) if charging else 0.
    ready=trip.start_time_s+tm+config.overhead_s
    y=max(schedule.window_start_s,ready) if scheduled else None
    completion=max(ready+c, schedule.window_start_s+schedule.duration_s,ready+schedule.duration_s) if scheduled else ready+c
    lower=completion-trip.start_time_s+tp+config.lambda_stop_s
    gamma=3600*k*(wl+wr)/30 if charging else 0.
    mar=arr-ev.minimum_energy_kwh; cap=ev.capacity_kwh-req
    nocharge=arr-req; deadline=schedule.window_end_s-y if scheduled else None
    slacks=[mar-k*wl,cap-k*wr]
    if scheduled:slacks.append(deadline-wt)
    if not charging:slacks.append(nocharge-k*(wl+wr))
    certified=bool(min(slacks)>=0)
    costs=frame.cost.to_numpy(float)
    arrivals=frame.arrival_energy.to_numpy(float); required=frame.required_energy.to_numpy(float)
    charges=np.maximum(0,required-arrivals)
    energy_errors=[float(np.max(arr-arrivals-k*wl)),float(np.max(required-req-k*wr)),
                   float(np.max(charges-q-k*(wl+wr)))]
    charge_error=float(np.max(frame.charge_s.to_numpy(float)-c-3600*k*(wl+wr)/30)) if charging else 0.
    schedule_error=0.
    if scheduled:
        ys=np.maximum(schedule.window_start_s,trip.start_time_s+frame.tm.to_numpy(float)+config.overhead_s)
        schedule_error=float(np.max(ys-y-wt))
    bound=wt+wp+gamma
    gap=float(costs.min()-lower)
    maxgap=float(costs.max()-lower)
    h1=bool(lower-SAFE_TAU>costs.min()+CHECK_TIME_TOL)
    hard=bool(np.min(arrivals)<ev.minimum_energy_kwh-CHECK_ENERGY_TOL or np.max(required)>ev.capacity_kwh+CHECK_ENERGY_TOL)
    if scheduled:hard=hard or bool(np.max(ys)>schedule.window_end_s+1e-8)
    if not charging:hard=hard or bool(np.max(required-arrivals)>CHECK_ENERGY_TOL)
    h3=bool(certified and (hard or gap < -CHECK_TIME_TOL or maxgap>bound+CHECK_TIME_TOL))
    perturb=bool(max(energy_errors)>CHECK_ENERGY_TOL or charge_error>CHECK_TIME_TOL or schedule_error>CHECK_TIME_TOL)
    return dict(lower=float(lower),safe_lower=float(lower-SAFE_TAU),
        tm_min=float(tm),tp_min=float(tp),lm_min=float(lm),lp_min=float(lp),
        omega_tm=float(wt),omega_tp=float(wp),omega_lm=float(wl),omega_lp=float(wr),
        arrival_hat=float(arr),required_hat=float(req),charge_hat=float(c),charge_q_hat=float(q),
        scheduled_start_hat=None if y is None else float(y),completion_hat=float(completion),
        margin_arrival=float(mar),margin_capacity=float(cap),margin_nocharge=float(nocharge),
        margin_deadline=None if deadline is None else float(deadline),minimum_margin_slack=float(min(slacks)),
        certified=certified,gamma_charge=float(gamma),gap_bound=float(bound),
        region_optimum=float(costs.min()),G_model=0.,G_agg=gap,G_cert=None,
        max_concrete_gap=maxgap,bound_slack=float(bound-gap),
        energy_error_max=max(energy_errors),charge_error_max=charge_error,schedule_error_max=schedule_error,
        H1_violation=h1,H3_violation=h3,perturbation_violation=perturb)


def directed_time_check(tm,tp,pairs):
    """Exact diagnostic diameter, +inf if any directed pair is unreachable."""
    tm,tp,pairs=np.asarray(tm),np.asarray(tp),np.asarray(pairs)
    delta=float(np.max(pairs))
    gap=float(np.min(tm+tp)-np.min(tm)-np.min(tp))
    return dict(diameter=delta,omega_tm=float(np.ptp(tm)),omega_tp=float(np.ptp(tp)),gap=gap,
                passed=bool(np.ptp(tm)<=delta+CHECK_TIME_TOL and np.ptp(tp)<=delta+CHECK_TIME_TOL
                            and -CHECK_TIME_TOL<=gap<=delta+CHECK_TIME_TOL))


def can_prune(safe_lower, incumbent_cost, epsilon):
    return bool(np.isfinite(incumbent_cost) and safe_lower >= incumbent_cost-epsilon)
