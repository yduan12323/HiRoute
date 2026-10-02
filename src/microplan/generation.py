"""Exact oracle for the explicit single/pair local-task formulation."""
import numpy as np
from envelope import NumericalTolerance
from .models import PlanBatch

CAPABILITY_BITS = {'charge': 1, 'meal': 2, 'sleep': 4, 'parking': 8}


def task_mask(task):
    return sum(CAPABILITY_BITS[c] for c in task.required_capabilities)


def generate_plans(opportunities, pairs, task, ds, dd, prefix_length, suffix_length,
                   baseline_time, baseline_length, budget, config,
                   access_scenario='all_attached', dwell_scenario='without_dwell',
                   tolerance=NumericalTolerance()):
    """Exact directed fastest segment concatenations, no region lookup.

    The sparse list must include every pair within the configured geographic
    radius. Finite frozen distance cutoff results certify the local task's
    distance condition; exact time queries certify its time condition. These
    conditions DEFINE local bundles; they are not inferred OD feasibility.
    """
    if config['maximum_stops'] != 2:
        raise ValueError('This verified local oracle supports maximum_stops=2')
    required = task_mask(task)
    caps, nodes, risk = opportunities.capability_masks, opportunities.access_nodes, opportunities.risk
    threshold = budget + tolerance.allowance(budget)
    single = np.flatnonzero((caps & required) == required)
    first_parts, second_parts, time_parts, length_parts, concurrent_parts = [], [], [], [], []
    first_parts.append(single); second_parts.append(np.full(len(single), -1, dtype=np.int64))
    time_parts.append(ds[nodes[single]] + dd[nodes[single]])
    length_parts.append(prefix_length[nodes[single]] + suffix_length[nodes[single]])
    concurrent_parts.append(np.full(len(single), 2 if len(task.required_capabilities) > 1 else 0, dtype=np.int8))
    if len(task.required_capabilities) > 1:
        a, b = pairs.first, pairs.second
        local = (pairs.geographic_m <= config['bundles']['geographic_radius_m'])
        complementary = ((caps[a] | caps[b]) & required) == required
        complementary &= ((caps[a] & required) != 0) & ((caps[b] & required) != 0)
        for i, j, dist, time, length in [
            (a,b,pairs.distance_forward_m,pairs.time_forward_s,pairs.fastest_length_forward_m),
            (b,a,pairs.distance_reverse_m,pairs.time_reverse_s,pairs.fastest_length_reverse_m)]:
            mask = local & complementary & np.isfinite(time) & (time <= config['bundles']['directed_shortest_time_cutoff_s'])
            mask &= dist <= config['bundles']['directed_shortest_distance_cutoff_m']
            i, j = i[mask], j[mask]
            first_parts.append(i); second_parts.append(j)
            time_parts.append(ds[nodes[i]] + time[mask] + dd[nodes[j]])
            length_parts.append(prefix_length[nodes[i]] + length[mask] + suffix_length[nodes[j]])
            proxy = (np.maximum if config['concurrency']['require_both_directions'] else np.minimum)(pairs.distance_forward_m[mask], pairs.distance_reverse_m[mask])
            concurrent_parts.append((proxy <= config['concurrency']['potential_network_distance_m']).astype(np.int8))
    first, second, total_t, total_d, concurrent = [np.concatenate(parts) for parts in
        [first_parts, second_parts, time_parts, length_parts, concurrent_parts]]
    access = np.maximum(risk[first], np.where(second < 0, 0, risk[np.maximum(second, 0)]))
    feasible = np.isfinite(total_t) & np.isfinite(total_d) & (total_t <= threshold)
    if access_scenario == 'conservative':
        feasible &= access == 0
    elif access_scenario != 'all_attached':
        raise ValueError('Unknown access scenario')
    first, second, total_t, total_d, concurrent, access = [a[feasible] for a in
        (first, second, total_t, total_d, concurrent, access)]
    duration = [config['activity_duration_s'][c] for c in task.required_capabilities]
    dwell = np.zeros(len(first))
    if dwell_scenario == 'structural_concurrency':
        dwell[:] = sum(duration)
        dwell[concurrent > 0] = max(duration)
    elif dwell_scenario != 'without_dwell':
        raise ValueError('Unknown dwell scenario')
    stops = np.where(second < 0, 1, 2)
    z = np.column_stack((total_t - baseline_time, total_d - baseline_length, stops, dwell, access))
    order = np.lexsort((second, first))
    return PlanBatch(first[order], second[order], total_t[order], total_d[order], z[order], concurrent[order])
