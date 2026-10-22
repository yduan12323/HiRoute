"""Outcome-blind DEV selection and explicit immutable microdomain generation.

The only geographic inputs are the generated Site table and source-bound,
previously exposed query metadata. No solver/REF result is a selector input.
"""
from __future__ import annotations
from copy import deepcopy
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def _write(path, value):
    with Path(path).open('xb') as stream:
        stream.write(canonical(value))


def _distance(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a['lat'], a['lon'], b['lat'], b['lon']))
    q = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 2 * 6371008.8 * math.asin(min(1, math.sqrt(q)))


def _effects(row):
    charge = 'charge' in row['transport_capabilities']
    service = row['meal_count'] > 0
    return ['C', 'S', 'CS'] if charge and service else ['C'] if charge else ['S'] if service else []


def validate_frozen_model(config):
    """Reject model/window drift before opening generated or raw inputs."""
    from experiments.m6h_manifest_v1.physical_inputs import PHYSICAL
    paths = ('experiments/m6h_manifest_v1/physical_inputs.py',
             'experiments/m6h_manifest_v1/generation.py',
             'experiments/m6h_manifest_v1/physical.py')
    pins=config['provenance'].get('model_source_sha256', {})
    if set(pins)!=set(paths): raise ValueError('Explicit model source pins required')
    root=Path(__file__).resolve().parents[2]
    for name in paths:
        if file_hash(root/name)!=pins[name]: raise ValueError('Frozen physical source changed: '+name)
    if config['physical']!=PHYSICAL or config['initial_energy_kwh']!='18':
        raise ValueError('Original physical model or SOC3/10 changed')
    # These exact published constants are source-pinned above, not tuneable
    # acceptance knobs. Query construction below consumes the frozen config.
    expected={'a_direct_time_ratio':'2/5','b_direct_time_ratio':'7/10','D':'2700'}
    if config['selection']['window']!=expected:
        raise ValueError('Original scheduled-window convention changed')
    return config['selection']['window']


def select_slots(site_rows, exposed_query_metadata, config):
    """One fixed query ordinal per slot; retain every shortage without replacement."""
    if config['selection']['case_ids'] != ['E01', 'E02', 'E03']:
        raise ValueError('Exactly three predeclared slots required')
    if config['selection']['candidate_limit'] != 4 or config['selection']['H_ref'] != 3:
        raise ValueError('Microdomain scope changed')
    catalog = {}
    for row in site_rows:
        sid = row['site_id']
        if sid in catalog:
            raise ValueError('Duplicate Site identity')
        if row['attachment_status'] != 'attached' or row['access_node'] is None:
            continue
        if not all(math.isfinite(float(row[k])) for k in ('lat', 'lon')):
            raise ValueError('Invalid geographic coordinates')
        catalog[sid] = row
    if not isinstance(exposed_query_metadata, list):
        raise ValueError('Explicit exposed metadata list required')
    queries = sorted(exposed_query_metadata, key=lambda q: q['query_id'])
    if len({q['query_id'] for q in queries}) != len(queries):
        raise ValueError('Duplicate exposed query ID')
    records = []
    for ordinal, case_id in enumerate(config['selection']['case_ids']):
        result = dict(case_id=case_id, status='NOT_RUN_MISSING_EXPOSED_QUERY_METADATA', replacement=False,
                      exposure_class='DEV_E2E', solver_outputs_read=False, query_ordinal=ordinal)
        if ordinal >= len(queries):
            records.append(result); continue
        query = queries[ordinal]
        if query.get('exposure_class') not in ('DEV', 'DEV_E2E') or not query.get('source_sha256'):
            raise ValueError('Previously exposed query provenance required')
        result['parent_query'] = query
        origin, destination = (catalog.get(query[k]) for k in ('origin_site_id', 'destination_site_id'))
        if origin is None or destination is None or origin['access_node'] == destination['access_node']:
            result['status'] = 'NOT_RUN_ENDPOINT_IDENTITY_MISMATCH'; records.append(result); continue
        direct = _distance(origin, destination)
        eligible = []
        for sid, row in catalog.items():
            effects = _effects(row)
            if not effects or row['access_node'] in (origin['access_node'], destination['access_node']):
                continue
            rank = (_distance(origin,row)+_distance(row,destination)-direct, sid)
            eligible.append((rank, row, effects))
        eligible.sort(key=lambda item: item[0])
        selected = []
        # Original physical capability class, with an explicit stable class order.
        for effects in (['C'], ['S'], ['C','S','CS']):
            representative = next((r for _,r,e in eligible if e == effects), None)
            if representative is not None:
                selected.append(representative)
        for _, row, _ in eligible:
            if len(selected) == 4: break
            if row['site_id'] not in {r['site_id'] for r in selected}: selected.append(row)
        result.update(status='SELECTED' if len(selected)==4 else 'NOT_RUN_CANDIDATE_SHORTAGE',
            origin=dict(site_id=origin['site_id'],anchor_id=f"road:{int(origin['access_node'])}"),
            destination=dict(site_id=destination['site_id'],anchor_id=f"road:{int(destination['access_node'])}"),
            candidates=[dict(site_id=r['site_id'],anchor_id=f"road:{int(r['access_node'])}",effects=_effects(r)) for r in selected],
            considered=[dict(site_id=r['site_id'],rank=[rank[0],rank[1]],effects=e) for rank,r,e in eligible],
            selection_reason='fixed exposed query ordinal; C/S/CS class representatives then geographic detour rank and Site ID',
            necessary_charge_lower_bound_or_unknown='UNKNOWN',
            intent='energy_only' if ordinal==0 else 'scheduled' if ordinal==1 else 'multicharge_target')
        if result['status']=='SELECTED' and ordinal in (1,2) and not any(
                'S' in row['effects'] or 'CS' in row['effects'] for row in result['candidates']):
            result['status']='NOT_RUN_ACTIVITY_UNSUPPORTED'
        records.append(result)
    return dict(schema='hiroute.m5e2e.selection.v1', config_sha256=digest(config),
                query_metadata_sha256=digest(exposed_query_metadata), cases=records,
                selection_before_solver=True, replacement=False)


def _load_graph(directory):
    import numpy as np
    import pandas as pd
    from types import SimpleNamespace
    directory = Path(directory)
    nodes = pd.read_parquet(directory/'nodes.parquet', columns=['node_id'])
    if not np.array_equal(nodes.node_id.to_numpy(), np.arange(len(nodes))):
        raise ValueError('Noncontiguous graph node identity')
    edges = pd.read_parquet(directory/'edges.parquet', columns=['source','target','travel_time_s','length_m'])
    arrays = [np.ascontiguousarray(edges[k].to_numpy(dtype=np.int64 if i<2 else np.float64))
              for i,k in enumerate(('source','target','travel_time_s','length_m'))]
    if any((a<0).any() or (a>=len(nodes)).any() for a in arrays[:2]):
        raise ValueError('Graph endpoint out of range')
    if any(not np.isfinite(a).all() or (a<0).any() for a in arrays[2:]):
        raise ValueError('Invalid graph constants')
    for array in arrays: array.flags.writeable = False
    return SimpleNamespace(node_count=len(nodes), edge_count=len(edges), source=arrays[0], target=arrays[1],
                           weights=dict(travel_time=arrays[2], distance=arrays[3]))


def freeze_cases(prepared, output_root, config, exposed_query_metadata=None, compiler=None):
    """Create new query/leg inputs from this build only, never from old results."""
    window=validate_frozen_model(config)
    import pandas as pd
    from timecut5.real_legs import RealSite
    from experiments.mechanism_recovery_v1.run import NativeDomain, original_tree, CACHE_POLICY
    from experiments.m6h_manifest_v1.reference import materialize_table
    root = Path(output_root).resolve(); root.mkdir(parents=True, exist_ok=False)
    graph_root = Path(prepared['graph_directory'])
    site_file = Path(prepared['sites_path'])
    for path, identity in prepared['consumed_files'].items():
        if file_hash(path) != identity['sha256']: raise ValueError('Prepared input changed')
    rows = pd.read_parquet(site_file).to_dict('records')
    metadata = config['exposed_queries'] if exposed_query_metadata is None else exposed_query_metadata
    selection = select_slots(rows, metadata, config)
    _write(root/'selection.json', selection)  # Persist before graph routing or optimization.
    hierarchy_path = Path(prepared['hierarchy_path'])
    hierarchy_bytes = hierarchy_path.read_bytes(); hierarchy_sha = hashlib.sha256(hierarchy_bytes).hexdigest()
    graph = None; cases = []
    graph_hashes = {name:file_hash(graph_root/(name+'.parquet')) for name in ('nodes','edges')}
    for record in selection['cases']:
        case = dict(case_id=record['case_id'], status=record['status'])
        if record['status'] != 'SELECTED':
            case['reason'] = record['status']; cases.append(case); continue
        if graph is None: graph = _load_graph(graph_root)
        sites = {r['site_id']:RealSite(r['site_id'],r['anchor_id'],tuple(r['effects'])) for r in record['candidates']}
        tree = original_tree(hierarchy_bytes,hierarchy_sha,list(sites))
        query = dict(deepcopy(config['physical']), case_id=record['case_id'],
                     origin=record['origin']['anchor_id'],destination=record['destination']['anchor_id'],H_ref=3,
                     initial_energy_kwh=config['initial_energy_kwh'],schedule=None)
        domain = NativeDomain(graph_factory=lambda:graph, query=query, sites=sites, tree=tree,
                              source_hashes=graph_hashes, cache=root/(record['case_id']+'-native'),
                              compiler=compiler, cache_policy=CACHE_POLICY)
        with domain.context('generation') as context:
            direct = context.provider.leg(query['origin'],query['destination'])
            if not direct.reachable:
                case.update(status='NOT_RUN_UNREACHABLE_DIRECT',reason='no finite baseline for exposed window'); cases.append(case); continue
            if record['intent'] != 'energy_only':
                T = F(float.fromhex(direct.time_hex))
                query['schedule'] = dict(a=str(F(window['a_direct_time_ratio'])*T),
                                         b=str(F(window['b_direct_time_ratio'])*T),D=window['D'])
            table = materialize_table(query,sites,context.provider,source_sha256=graph_hashes,
                                     selection_sha256=digest(selection),hierarchy_sha256=hierarchy_sha)
        legs_path = root/(record['case_id']+'-legs.json')
        with legs_path.open('xb') as stream: stream.write(table.raw_bytes)
        binding = dict(validation_domain='real_map_microdomain_v1', depth_mode='declared_diagnostic_cap',
                       H_ref=3,candidate_count=len(sites),exposure_class='DEV_E2E',query_sha256=digest(query),
                       graph_identity={k+'_sha256':v for k,v in graph_hashes.items()},
                       case_id=record['case_id'],candidate_site_ids=list(sites),
                       candidate_sha256=digest(list(sites)),legs_sha256=table.payload_sha256,hierarchy_sha256=hierarchy_sha)
        query_path=root/(record['case_id']+'-query.json')
        _write(query_path,query)
        case.update(status='READY',query=query,query_path=str(query_path),query_sha256=digest(query),legs_path=str(legs_path),
                    legs_sha256=table.payload_sha256,hierarchy_path=str(hierarchy_path),hierarchy_sha256=hierarchy_sha,
                    domain_binding=binding,necessary_charge_lower_bound_or_unknown='UNKNOWN')
        case_path=root/(record['case_id']+'-case.json')
        _write(case_path,case)
        case['case_path']=str(case_path)
        cases.append(case)
    receipt = dict(schema='hiroute.m5e2e.freeze.v1',config_sha256=digest(config),prepared_sha256=digest(prepared),
                   selection_sha256=digest(selection),cases=cases,cases_path=str(root/'cases.json'))
    _write(root/'freeze.json',receipt)
    _write(root/'cases.json',dict(cases=cases))
    return receipt


def replay_graph_legs(prepared, case_path):
    """Independent directed-edge replay, not a claim to re-prove route optimality.

    Reconstruct each reachable selected path directly from graph edges, with
    binary64 addition in path order. Do not call native router or consume solver
    witnesses/results. This checks physical road adjacency and path totals.
    """
    import pandas as pd
    from validation.reference5.real_input import IndependentLegTable
    case=json.loads(Path(case_path).read_text())
    raw=Path(case['legs_path']).read_bytes()
    table=IndependentLegTable.from_bytes(raw,case['legs_sha256'])
    payload=json.loads(raw)
    directory=Path(prepared['graph_directory'])
    identities=case['domain_binding']['graph_identity']
    for name in ('nodes','edges'):
        if table.source_sha256.get(name)!=identities[name+'_sha256']:
            raise ValueError('Immutable table graph identity differs from case binding')
        if file_hash(directory/(name+'.parquet'))!=identities[name+'_sha256']:
            raise ValueError('Graph differs from frozen selected-leg input')
    edges=pd.read_parquet(directory/'edges.parquet',columns=['edge_id','source','target','travel_time_s','length_m'])
    # Never assume row positions are valid edge identities without checking.
    if list(edges.edge_id)!=list(range(len(edges))): raise ValueError('Graph edge identity order differs')
    columns={k:edges[k].to_numpy() for k in ('source','target','travel_time_s','length_m')}
    checked=0; unreachable=0
    for leg in payload['legs']:
        path=leg.get('selected_edge_indices')
        if not leg['reachable']:
            if path is not None: raise ValueError('Unreachable leg has a selected path')
            unreachable+=1; continue
        if not isinstance(path,list): raise ValueError('Reachable leg lacks physical edge witness')
        current=int(leg['source_anchor'].removeprefix('road:'))
        target=int(leg['target_anchor'].removeprefix('road:'))
        seconds=length=0.0
        for edge in path:
            if type(edge) is not int or not 0<=edge<len(edges): raise ValueError('Invalid selected edge index')
            if int(columns['source'][edge])!=current: raise ValueError('Disconnected selected path')
            current=int(columns['target'][edge])
            seconds+=float(columns['travel_time_s'][edge]); length+=float(columns['length_m'][edge])
        if current!=target: raise ValueError('Selected path ends at wrong road anchor')
        if seconds.hex()!=leg['time_s']['hex'] or length.hex()!=leg['actual_length_m']['hex']:
            raise ValueError('Selected path totals differ from immutable leg constants')
        checked+=1
    return dict(schema='hiroute.m5e2e.graph_edge_replay.v1',status='VERIFIED',case_id=case['case_id'],
                legs_sha256=table.payload_sha256,graph_identity=identities,reachable_paths_checked=checked,
                unreachable_pairs_not_reproved=unreachable,solver_outputs_read=False,
                exactness_scope='directed adjacency and binary64 selected-path totals',
                limitation='Does not independently re-prove shortest-path or tie optimality')
