"""Action-subset adapters and original-model replay for frozen DEV policies."""
from dataclasses import replace
from fractions import Fraction as F
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'comparison'))
from planning_policies import action_mask, choose_activity, charging_activity_overlap


class PolicyNoEligibleActivity(Exception):
    pass


def adapt_snapshot(original, policy, provider):
    """No joint result/seed input; physical fields and provider stay unchanged."""
    if original.schedule is None or original.initial_remaining_schedule != 1:
        raise ValueError('planning-value policies require one pending activity')
    activity = None
    features = {}
    if policy == 'activity_first_fixed_site':
        outbound = provider.distances_from(original.origin, 'time_s')
        inbound = provider.distances_to(original.destination, 'time_s')
        features = {s: (outbound.get(s), inbound.get(s))
                    for s in original.candidate_order
                    if set(original.site_capabilities[s]) & {'S', 'CS'}}
        activity = choose_activity(original.site_capabilities, features,
            start_time=original.departure_time_s, overhead=original.stop_overhead_s,
            penalty=original.stop_penalty_s, a=original.schedule['a'],
            b=original.schedule['b'], duration=original.schedule['D'])
        mask = None if activity is None else action_mask(original.site_capabilities, policy, activity)
    else:
        mask = action_mask(original.site_capabilities, policy)
    info = dict(policy=policy, original_candidate_count=len(original.candidate_order),
                original_action_count=sum(map(len, original.site_capabilities.values())),
                original_semantic_problem_id=original.semantic_problem_id,
                selected_activity_site=activity, time_features=features,
                selection_uses_energy_or_solver_results=False)
    if mask is None:
        info.update(effective_candidate_count=0, effective_action_count=0,
                    reason='no reachable activity satisfying the necessary time screen')
        return None, info
    # Preserve the original order of Sites and effects; never iterate a set to
    # construct the solver input. Empty Sites are a policy restriction only.
    caps = {s: tuple(e for e in original.site_capabilities[s] if (s, e) in mask)
            for s in original.candidate_order}
    caps = {s: effects for s, effects in caps.items() if effects}
    info.update(effective_candidate_count=len(caps), effective_action_count=sum(map(len, caps.values())))
    if not any(set(effects) & {'S', 'CS'} for effects in caps.values()):
        info['reason'] = 'policy mask retains no legal activity action'
        return None, info
    restricted = replace(original, candidate_order=tuple(caps), site_capabilities=caps)
    info['policy_semantic_problem_id'] = restricted.semantic_problem_id
    return restricted, info


def verify_policy_witness(original, restricted, record, *, site_to_road=None,
                          direct_length_m=None):
    from hiroute.exact.scale_replay import verify_scale_witness
    verified = verify_scale_witness(restricted, record, site_to_road=site_to_road)
    joint = verify_scale_witness(original, record, site_to_road=site_to_road)
    if verified != joint:
        raise ValueError('policy/original physical replay disagree')
    curve = [tuple(map(F, segment)) for segment in original.charging_curve]
    def clock(energy):
        values = [slope*energy+intercept for lo, hi, slope, intercept in curve if lo <= energy <= hi]
        if not values or len(set(values)) != 1:raise ValueError('invalid charge endpoint')
        return values[0]
    charge_time = overlap = F(0)
    for event in record['replay']['trace']:
        effect = event[0]
        if effect not in ('C', 'CS'):continue
        duration = clock(F(event[4]))-clock(F(event[2]))
        charge_time += duration
        if effect == 'CS':
            overlap += charging_activity_overlap(arrival=event[3], overhead=original.stop_overhead_s,
                charge_duration=duration, a=original.schedule['a'], service_duration=original.schedule['D'])
    verified.update(policy_verified=True, original_joint_model_verified=True,
                    charging_duration_s=charge_time, charging_activity_overlap_s=overlap,
                    stop_count=len(record['plan']),
                    activity_duration_s=F(original.schedule['D']),
                    signed_distance_delta_from_direct_fastest_m=None if direct_length_m is None
                    else verified['total_distance_m']-F(direct_length_m))
    return verified
