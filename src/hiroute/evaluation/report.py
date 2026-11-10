"""Integrity-checked postprocessing. Importing this module cannot run a solver."""
from pathlib import Path

from ..data.artifacts import digest, read_json
from .cohort import summarize_rows


def summarize(input_root):
    root = Path(input_root).resolve()
    terminal = read_json(root / 'terminal.json')
    if terminal['schema'] != 'hiroute.research_terminal.v1' or terminal['state'] not in {'complete', 'budget_stopped', 'failed'}:
        raise ValueError('a closed research terminal is required')
    for name in ('prepared', 'results'):
        if digest(root / (name + '.json')) != terminal[name + '_sha256']:
            raise ValueError('terminal artifact mismatch: ' + name)
    prepared, results = read_json(root / 'prepared.json'), read_json(root / 'results.json')
    if terminal['run_id'] != prepared['run_id'] or terminal['source'] != prepared['source']:
        raise ValueError('terminal run identity mismatch')
    if terminal['conservative_total_cpu_s'] > terminal['cap_cpu_s']:
        raise ValueError('closed run exceeds CPU accounting cap')
    verified = []
    for name, expected in terminal['receipts'].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root) or digest(path) != expected:
            raise ValueError('slot receipt mismatch: ' + name)
        verified.append(read_json(path))
    key = lambda r: (r['query_id'], r['initial_energy_kwh'], r['scenario'], r['N'], r['method'])
    if sorted(verified, key=key) != sorted(results['rows'], key=key):
        raise ValueError('aggregate differs from slot receipts')
    cells = [c for c in prepared['matrix']['cells'] if c['N'] == 64]
    reduced = summarize_rows(cells, results['rows'], terminal=terminal['state'] != 'failed',
                             missing_status='not_attempted_stage_failed')
    return dict(schema='hiroute.research_summary.v1', accounting=terminal, **reduced,
                scope='Frozen N64 DEV; exact completion does not certify independent full-graph optimality')
