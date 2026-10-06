"""Read-only contract audit; outputs only to the new B1 namespace.

Run with the accepted hiroute Python from the repository root.
This is not a hierarchy or a comparative experiment.
"""
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from _common import configs, load_graph
from _stopplan4r_common import memory_guard, read_config, peak_rss_mib
from microplan.routing import ExactRouter
from run_stopplan_4r_diagnostic import ODTravel
from stopplan4r.sites import sites_from_table
from stopplan4r.models import EVModel, PiecewiseChargingCurve, PlannerConfig, Trip
import stopplan4r.evaluation as evaluation

out = Path(__file__).resolve().parent
cfg = read_config('configs/stopplan_4r.yaml')
started = time.perf_counter()
guard = memory_guard(cfg['memory'], projected_additional_gib=7)
sites = sites_from_table(pd.read_parquet(ROOT / 'results/milestone_4r/stop_sites.parquet'))
neutral = [s for s in sites if s.attachment_status == 'attached'
           and s.access_node is not None and 'charge' not in s.transport_capabilities
           and s.support.meal_count == 0]
# OD 0 was checked first and yielded no witness (76% energy is insufficient).
# Choose the first accepted 1.05 / 76% energy-only case with zero stops.
# This selection diagnoses coverage only; no hierarchy pruning is measured.
accepted = pd.read_parquet(ROOT / 'results/milestone_4r/one_stop_diagnostics.parquet')
case = accepted[(accepted.ratio == 1.05) & (accepted.initial_soc == 0.76)
                & (accepted.scenario == 'energy_only') & (accepted.stop_count == 0)]
instance_id = int(case.instance_id.min())
ods = pd.read_parquet(ROOT / cfg['development_ods'])
od = ods[ods.instance_id == instance_id].iloc[0]
data, routing = configs(cfg['graph_data_config'])
graph = load_graph(data, routing)
router = ExactRouter(graph, cfg, out / 'native_cache')
o, z = int(od.origin_node), int(od.destination_node)
ft, fl, _ = router.full(o)
rt, rl, _ = router.full(z, reverse=True)
travel = ODTravel(o, z, ft, fl, rt, rl)
ev = EVModel(**cfg['ev'])
curve = PiecewiseChargingCurve(tuple(map(tuple, cfg['charging']['bands'])))
pc = PlannerConfig(**cfg['planner'])
budget = float(1.05 * ft[z])
trip = Trip(o, z, 0.76 * ev.capacity_kwh, mobility_budget_s=budget)
eligible = [s for s in neutral if np.isfinite(ft[s.access_node] + rt[s.access_node])
            and ft[s.access_node] + rt[s.access_node] <= budget + 1e-8 + budget * 1e-10]
captured = []
original = evaluation.assemble_plan


def capture(*args, **kwargs):
    plan = original(*args, **kwargs)
    if plan.stops:
        captured.append(plan)
    return plan


with patch.object(evaluation, 'assemble_plan', side_effect=capture):
    optimum = evaluation.best_one_stop(trip, eligible, travel, ev, curve, None, pc)
assert captured, 'No witness: audit inconclusive'
p = min(captured, key=evaluation.plan_key)
s = next(s for s in eligible if s.site_id == p.stops[0].site_id)
record = {
    'kind': 'preimplementation_action_coverage_counterexample',
    'instance_id': instance_id, 'ratio': 1.05, 'initial_soc': 0.76,
    'scenario': 'energy_only', 'prior_check': 'OD 0: no feasible neutral witness',
    'attached_sites_without_any_allowed_role': len(neutral),
    'eligible_sites_without_any_allowed_role': len(eligible),
    'feasible_one_stop_actions_without_any_allowed_role': len(captured),
    'witness_site_id': s.site_id,
    'transport_capabilities': sorted(s.transport_capabilities),
    'meal_count': s.support.meal_count, 'roles': [],
    'trip': asdict(trip), 'baseline': asdict(travel.leg(o, z)),
    'inbound': asdict(travel.leg(o, s.access_node)),
    'outbound': asdict(travel.leg(s.access_node, z)),
    'witness_plan': asdict(p), 'best_over_zero_and_neutral_subset': asdict(optimum),
    'method': 'Unchanged best_one_stop; assemble_plan wrapper records constructed plans and returns original objects unchanged.',
    'runtime_seconds': time.perf_counter() - started,
    'peak_rss_mib': peak_rss_mib(), 'memory_guard': guard,
    'native_provenance': router.provenance,
}
(out / 'role_coverage_counterexample.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps({k: record[k] for k in ['instance_id', 'witness_site_id',
    'eligible_sites_without_any_allowed_role', 'feasible_one_stop_actions_without_any_allowed_role']}, indent=2))
router.close()
