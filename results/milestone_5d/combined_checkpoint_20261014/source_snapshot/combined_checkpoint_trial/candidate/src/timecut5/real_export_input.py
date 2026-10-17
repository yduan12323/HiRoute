"""Read-only import of hash-frozen compact real inputs; never runs a solver.

The caller supplies reviewed manifest/selection digests and the original tree.
This verifies the artifact chain, not the router algorithm or acceptance gates.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction as R
import hashlib
import json
from pathlib import Path

from .real_adapter import RealProblem, original_region_view
from .real_legs import ImmutableLegTable, RestrictedTree, decode_binary64, restrict_frozen_tree


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))


def _read(path, expected):
    data = Path(path).read_bytes()
    _require(hashlib.sha256(data).hexdigest() == expected, f"Artifact hash mismatch: {Path(path).name}")
    return data


def _inside(root, name):
    _require(isinstance(name, str) and name and not Path(name).is_absolute(), "Relative artifact path required")
    path = (root / name).resolve()
    _require(path.is_relative_to(root), "Artifact path escapes export directory")
    return path


def _exact(value):
    _require(isinstance(value, (str, int)) and not isinstance(value, bool), "Exact rational scalar required")
    return R(value)


@dataclass(frozen=True)
class PreparedRealCase:
    state_id: str
    query: dict
    table: ImmutableLegTable
    restriction: RestrictedTree
    export_manifest_sha256: str
    resolved_states_sha256: str


def load_exported_case(export_directory, state_id, expected_manifest_sha256, *,
                       selection_path, expected_selection_sha256, original_hierarchy_path):
    """Validate one frozen state and translate scalars, with no route/search run.

    Original tree bytes are required: a self-consistent fabricated restriction
    cannot replace the accepted tree. Manifest paths cannot escape the bundle.
    Raw graph hashes remain declared provenance; this importer does not reread
    hundreds of MB or imply that those raw files were freshly verified here.
    """
    root = Path(export_directory).resolve()
    manifest = _json(_read(_inside(root, 'export_manifest.json'), expected_manifest_sha256))
    selection = _json(_read(selection_path, expected_selection_sha256))
    _require(manifest['selection_certificate_sha256'] == expected_selection_sha256, "Selection provenance mismatch")
    _require(manifest['hierarchy_sha256'] == selection['original_hierarchy_sha256'], "Original tree provenance mismatch")
    _require(manifest['status'] == 'export_complete_preparation_only' and manifest['no_optimization'] is True,
             "Unsupported export status")
    states = _json(_read(_inside(root, 'query_states_resolved.json'), manifest['query_states_resolved_sha256']))
    _require(isinstance(states, list) and all(isinstance(s, dict) for s in states), "State array required")
    identifiers = [s['state_id'] for s in states]
    _require(len(set(identifiers)) == len(identifiers), "Duplicate state ID")
    _require(state_id in identifiers, "Unknown frozen state ID")
    state = states[identifiers.index(state_id)]
    pool_id = state['pool_id']
    pools = [p for p in selection['pools'] if p['pool_id'] == pool_id]
    _require(len(pools) == 1, "Unknown or duplicate selected pool")
    pool = pools[0]
    _require((state['mode'], state['instance_id']) == (pool['mode'], pool['instance_id']), "State/pool identity mismatch")
    spec = manifest['tables'][pool_id]
    _require(state['immutable_direct_leg_table'] == spec, "State/table manifest mismatch")
    table = ImmutableLegTable.from_bytes(_read(_inside(root, spec['path']), spec['sha256']), spec['sha256'])
    _require(table.selection_certificate_sha256 == expected_selection_sha256 and
             table.hierarchy_sha256 == manifest['hierarchy_sha256'], "Table provenance mismatch")
    chosen = pool['chosen']
    _require(len(chosen) == len(table.sites) and {x['site_id'] for x in chosen} == set(table.sites) == set(pool['selected_site_ids']),
             "Selected Site universe mismatch")
    for row in chosen:
        site = table.site(row['site_id'])
        _require(site.anchor_id == f"road:{row['access_node']}" and list(site.effects) == row['eligible_actions'],
                 "Selected physical anchor or capabilities mismatch")
    _require(table.origin_anchor == f"road:{state['origin_road_anchor']}" and
             table.destination_anchor == f"road:{state['destination_road_anchor']}", "OD anchor mismatch")
    restriction = restrict_frozen_tree(_read(original_hierarchy_path, table.hierarchy_sha256),
                                       table.hierarchy_sha256, list(table.sites))
    r_spec = manifest['restrictions'][pool_id]
    _require(state['original_tree_restriction'] == r_spec, "State/restriction manifest mismatch")
    serialized = _json(_read(_inside(root, r_spec['path']), r_spec['sha256']))
    expected_rows = [dict(region_id=r.region_id, parent_id=r.parent_id,
                          child_ids=list(r.child_ids), site_ids=list(r.site_ids)) for r in restriction.regions]
    _require(serialized['schema'] == 'hiroute.original_tree_restriction.v1' and
             serialized['original_sha256'] == restriction.original_sha256 and
             serialized['selection_certificate_sha256'] == expected_selection_sha256 and
             serialized['pool_id'] == pool_id and serialized['regions'] == expected_rows and
             serialized['selected_site_ids'] == list(restriction.selected_site_ids), "Original tree restriction mismatch")
    original_region_view(table, restriction)
    baseline = table.leg(table.origin_anchor, table.destination_anchor)
    _require(baseline.reachable, "Frozen baseline is unreachable")
    _require(decode_binary64(state['accepted_baseline_time_s']) == baseline.time and
             decode_binary64(state['accepted_baseline_actual_length_m']) == baseline.actual_length,
             "Resolved baseline mismatch")
    query = {k: state[k] for k in ('H_ref', 'start_time_s', 'initial_energy_kwh', 'capacity_kwh',
                                  'overhead_s', 'consumption_kwh_per_m')}
    query.update(origin=table.origin_anchor, destination=table.destination_anchor,
                 minimum_energy_kwh=state['energy_floor_kwh'], reserve_kwh=state['terminal_reserve_kwh'],
                 lambda_stop_s=state['stop_penalty_s'], leg_payload_sha256=table.payload_sha256,
                 selection_certificate_sha256=expected_selection_sha256, hierarchy_sha256=table.hierarchy_sha256)
    _require(_exact(state['initial_soc']) * _exact(state['capacity_kwh']) == _exact(state['initial_energy_kwh']),
             "SOC/energy mismatch")
    primitive = state['charging_primitive']
    breaks, slopes, intercepts = (primitive[k] for k in ('energy_breakpoints_kwh', 'slopes_s_per_kwh', 'intercepts_s'))
    _require(len(breaks) == len(slopes) + 1 == len(intercepts) + 1, "Charging primitive shape mismatch")
    query['charging_segments'] = [[breaks[i], breaks[i+1], slopes[i], intercepts[i]] for i in range(len(slopes))]
    if state['mode'] == 'energy_only':
        _require(state['schedule'] is None, "Energy-only state has a schedule")
        query['schedule'] = None
    else:
        _require(state['mode'] == 'energy_and_scheduled', "Unknown query mode")
        schedule = state['schedule']
        _require(schedule['hard'] is True and schedule['compatible_with_charging'] is True, "Unsupported schedule semantics")
        _require(decode_binary64(schedule['baseline_binary64']) == baseline.time and
                 _exact(schedule['baseline_time_s']) == baseline.time and
                 _exact(schedule['window_start_s']) == R(2, 5)*baseline.time and
                 _exact(schedule['window_end_s']) == R(7, 10)*baseline.time, "Frozen schedule arithmetic mismatch")
        query['schedule'] = dict(a=schedule['window_start_s'], b=schedule['window_end_s'], D=schedule['duration_s'])
    RealProblem(query, table)  # Validate scalar model only; never propagate/search.
    return PreparedRealCase(state_id, query, table, restriction, expected_manifest_sha256,
                            manifest['query_states_resolved_sha256'])
