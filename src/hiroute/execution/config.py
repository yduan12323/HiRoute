"""Versioned research configuration, separate from strict SolverConfig v1."""
from copy import deepcopy
import math
from pathlib import Path

from ..data.artifacts import digest, read_json

METHODS = ('flat_bb_strong', 'scale')
N64_PROFILE = dict(pair_query_mode='landmark_astar', source_tree_reuse=True,
                   seed_beam_pruning=True, inbound_energy_bound=True,
                   eager_incumbent_pruning=True, pending_activity_screen=False)
RESOURCE_FIELDS = {'loaded_limit_s', 'cold_allowance_s', 'process_memory_bytes',
                   'stage_cpu_s', 'worker_reservation_cpu_s', 'controller_reservation_cpu_s',
                   'development_reporting_cpu_s'}


def n64_cells(matrix):
    cells = [cell for cell in matrix['cells'] if cell['N'] == 64]
    expected = [(f'WD{i:02d}', e, s) for i in range(1, 13)
                for e in ('18', '48') for s in ('energy_only', 'schedule')]
    if [(c['query_id'], c['initial_energy_kwh'], c['scenario']) for c in cells] != expected:
        raise ValueError('frozen N64 denominator/order changed')
    if matrix['methods'] != list(METHODS):
        raise ValueError('paired methods/order changed')
    return cells


def load_config(path):
    path = Path(path).resolve()
    config = read_json(path)
    fields = {'schema', 'profile', 'base_config', 'matrix', 'matrix_sha256', 'graph_sha256', 'resources'}
    if set(config) != fields or config['schema'] != 'hiroute.research_run.v1' or config['profile'] != 'n64_dev':
        raise ValueError('strict research_run.v1 fields and n64_dev profile required')
    matrix_path, base_path = (path.parent / config[k] for k in ('matrix', 'base_config'))
    if not isinstance(config['graph_sha256'], str) or len(config['graph_sha256']) != 64 or any(c not in '0123456789abcdef' for c in config['graph_sha256']):
        raise ValueError('an explicit historical graph SHA256 is required')
    if digest(matrix_path) != config['matrix_sha256']:
        raise ValueError('frozen matrix integrity mismatch')
    matrix, base = read_json(matrix_path), read_json(base_path)
    n64_cells(matrix)
    effective_profile = {**matrix['implementation_profile']}
    effective_profile.setdefault('pending_activity_screen', False)
    if any(type(effective_profile.get(k)) is not type(v) or effective_profile.get(k) != v for k, v in N64_PROFILE.items()):
        raise ValueError('N64 implementation profile mismatch')
    if base['model'] != matrix['model']:
        raise ValueError('frozen physical model changed')
    resources = config['resources']
    if set(resources) != RESOURCE_FIELDS or any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in resources.values()):
        raise ValueError('invalid explicit research resources')
    if (type(resources['process_memory_bytes']) is not int or
            resources['loaded_limit_s'] != 120 or resources['cold_allowance_s'] != 180 or
            resources['process_memory_bytes'] != 8 * 1024**3 or
            resources['worker_reservation_cpu_s'] < 310 or resources['controller_reservation_cpu_s'] < 310):
        raise ValueError('N64 per-slot resource contract changed')
    if matrix['resources']['query_loaded_limit_s'] != resources['loaded_limit_s']:
        raise ValueError('matrix loaded limit mismatch')
    configs = {}
    for energy in ('18', '48'):
        cfg = deepcopy(base)
        # Explicit adaptation of the historical pilot schema. No inherited ledger.
        cfg['model']['initial_energy_kwh'] = energy
        cfg['selection'] = deepcopy(matrix['endpoint_and_selection_policy'])
        cfg['selection']['candidate_counts'] = [64]
        cfg['implementation'] = effective_profile
        cfg['resources']['new_solve_and_finite_ref_cpu_budget_s'] = resources['stage_cpu_s']
        cfg['pilot_matrix'] = [dict(N=64, query_ids=[c['query_id']], scenarios=[c['scenario']])
                               for c in n64_cells(matrix) if c['initial_energy_kwh'] == energy]
        if cfg.get('cost_diagnostic') or cfg.get('planning_policy'):
            raise ValueError('historical diagnostic/policy adapters are outside the N64 profile')
        configs[energy] = cfg
    return dict(config=config, matrix=matrix, configs=configs,
                input_config_sha256=digest(path), base_config_sha256=digest(base_path))
