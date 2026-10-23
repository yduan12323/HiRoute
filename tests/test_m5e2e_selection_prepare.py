"""Pure code-only tests; never download or prepare a real graph."""
import hashlib
import pytest
from experiments.m5e2e_v1.selection import select_slots
from experiments.m5e2e_v1.prepare import preflight


def fixture():
    rows=[]
    for i in range(8):
        rows.append(dict(site_id=f's{i}',attachment_status='attached',access_node=i,
                         lat=36.0,lon=118+i*.01,transport_capabilities=['charge'] if i%3!=1 else [],
                         meal_count=int(i%3!=0)))
    queries=[dict(query_id=f'q{i}',origin_site_id='s0',destination_site_id='s7',
                  exposure_class='DEV',source_sha256='0'*64) for i in range(3)]
    cfg=dict(selection=dict(case_ids=['E01','E02','E03'],candidate_limit=4,H_ref=3))
    return rows,queries,cfg


def test_selector_order_independent_and_no_outcome_input():
    rows,queries,cfg=fixture()
    first=select_slots(rows,queries,cfg)
    second=select_slots(rows[::-1],queries[::-1],cfg)
    # Metadata hash records byte-order identity; semantic selection is canonical.
    assert first['cases']==second['cases']
    assert all(r['status']=='SELECTED' and len(r['candidates'])==4 for r in first['cases'])
    assert all(r['solver_outputs_read'] is False and r['replacement'] is False for r in first['cases'])
    assert [r['intent'] for r in first['cases']]==['energy_only','scheduled','multicharge_target']


def test_missing_metadata_retains_all_slots():
    rows,queries,cfg=fixture()
    cases=select_slots(rows,[],cfg)['cases']
    assert [r['case_id'] for r in cases]==['E01','E02','E03']
    assert all(r['status']=='NOT_RUN_MISSING_EXPOSED_QUERY_METADATA' for r in cases)


def test_shortage_does_not_replace_query():
    rows,queries,cfg=fixture()
    cases=select_slots([rows[0],rows[1],rows[-1]],queries,cfg)['cases']
    assert all(r['status']=='NOT_RUN_CANDIDATE_SHORTAGE' for r in cases)
    assert [r['parent_query']['query_id'] for r in cases]==['q0','q1','q2']


def test_missing_endpoint_no_nearby_substitution():
    rows,queries,cfg=fixture(); queries[0]['origin_site_id']='absent'
    cases=select_slots(rows,queries,cfg)['cases']
    assert cases[0]['status']=='NOT_RUN_ENDPOINT_IDENTITY_MISMATCH'
    assert cases[1]['parent_query']['query_id']=='q1'


def test_holdout_and_unbound_exposure_rejected():
    rows,queries,cfg=fixture(); queries[0]['exposure_class']='HOLDOUT'
    with pytest.raises(ValueError,match='exposed query provenance'): select_slots(rows,queries,cfg)


def test_diagnostic_cap_not_silently_changed():
    rows,queries,cfg=fixture(); cfg['selection']['H_ref']=4
    with pytest.raises(ValueError,match='scope changed'): select_slots(rows,queries,cfg)


def test_raw_missing_is_not_synthetic_fallback(tmp_path):
    config={'source':{'expected_size_bytes':3,'sha256':hashlib.sha256(b'raw').hexdigest(),
                       'polygon_sha256':hashlib.sha256(b'poly').hexdigest(),'publisher_md5':'abc'}}
    before=list(tmp_path.iterdir())
    result=preflight(config,tmp_path)
    assert result['status']=='NEEDS_ACQUISITION'
    assert list(tmp_path.iterdir())==before
    (tmp_path/'shandong-261016.osm.pbf').write_bytes(b'bad')
    assert preflight(config,tmp_path)['status']=='IDENTITY_MISMATCH'


def test_raw_symlink_rejected(tmp_path):
    config={'source':{'expected_size_bytes':3,'sha256':hashlib.sha256(b'raw').hexdigest(),
                       'polygon_sha256':hashlib.sha256(b'poly').hexdigest(),'publisher_md5':'abc'}}
    (tmp_path/'elsewhere').write_bytes(b'raw')
    (tmp_path/'shandong-261016.osm.pbf').symlink_to(tmp_path/'elsewhere')
    assert preflight(config,tmp_path)['status']=='IDENTITY_MISMATCH'


def test_empty_md5_is_invalid_not_index_error(tmp_path):
    config={'source':{'expected_size_bytes':3,'sha256':hashlib.sha256(b'raw').hexdigest(),
                       'polygon_sha256':hashlib.sha256(b'poly').hexdigest(),'publisher_md5':'abc'}}
    (tmp_path/'publisher.md5').write_text('')
    assert preflight(config,tmp_path)['status']=='IDENTITY_MISMATCH'


def test_canonical_parquet_content_not_compression(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq
    from experiments.m5e2e_v1.prepare import canonical_parquet_digest
    table=pa.table({'node_id':[0,1],'lat':[36.0,36.1],'tags':[None,'x']})
    a=tmp_path/'a.parquet'; b=tmp_path/'b.parquet'
    pq.write_table(table,a,compression='NONE',row_group_size=1)
    pq.write_table(table,b,compression='snappy',row_group_size=2)
    assert canonical_parquet_digest(a)==canonical_parquet_digest(b)


def test_graph_edge_replay_and_disconnected_path_rejected(tmp_path):
    import json
    import pandas as pd
    from experiments.m5e2e_v1.selection import canonical, file_hash, replay_graph_legs
    pd.DataFrame({'node_id':[0,1]}).to_parquet(tmp_path/'nodes.parquet')
    pd.DataFrame({'edge_id':[0,1],'source':[0,1],'target':[1,0],
                  'travel_time_s':[2.0,3.0],'length_m':[5.0,7.0]}).to_parquet(tmp_path/'edges.parquet')
    def number(x):
        x=float(x); n,d=x.as_integer_ratio(); return {'hex':x.hex(),'ratio':[str(n),str(d)]}
    rows=[]
    for a in range(2):
        for b in range(2):
            rows.append(dict(source_anchor=f'road:{a}',target_anchor=f'road:{b}',reachable=True,
                             label_direction='identity' if a==b else 'forward_from_source',
                             selected_edge_indices=[] if a==b else [a],
                             time_s=number(0 if a==b else 2+a),
                             actual_length_m=number(0 if a==b else 5+2*a)))
    hashes={k:file_hash(tmp_path/(k+'.parquet')) for k in ('nodes','edges')}
    payload=dict(schema='hiroute.immutable_selected_legs.v1',numerical_contract='binary64_totals_as_exact_rationals_v1',
                 anchors=['road:0','road:1'],origin_anchor='road:0',destination_anchor='road:1',sites=[],legs=rows,
                 source_sha256=hashes,selection_certificate_sha256='0'*64,hierarchy_sha256='1'*64,
                 backend=dict(name='synthetic_test_only',tie_policy='min_time_then_actual_length_then_first_discovery',
                              direction_policy='forward_per_source_v1',source_sha256=hashes))
    legs=tmp_path/'legs.json'; casepath=tmp_path/'case.json'
    case=dict(case_id='SYNTHETIC',legs_path=str(legs),
              domain_binding={'graph_identity':{k+'_sha256':v for k,v in hashes.items()}})
    def write():
        legs.write_bytes(canonical(payload)); case['legs_sha256']=file_hash(legs);casepath.write_bytes(canonical(case))
    write()
    report=replay_graph_legs({'graph_directory':str(tmp_path)},casepath)
    assert report['reachable_paths_checked']==4
    rows[1]['selected_edge_indices']=[1]; write()
    with pytest.raises(ValueError,match='Disconnected'): replay_graph_legs({'graph_directory':str(tmp_path)},casepath)


def test_activity_slots_missing_capability_remain_explicit():
    rows,queries,cfg=fixture()
    for row in rows: row.update(transport_capabilities=['charge'],meal_count=0)
    cases=select_slots(rows,queries,cfg)['cases']
    assert cases[0]['status']=='SELECTED'
    assert cases[1]['status']==cases[2]['status']=='NOT_RUN_ACTIVITY_UNSUPPORTED'


def test_frozen_model_window_and_source_drift_rejected():
    import json
    from pathlib import Path
    from experiments.m5e2e_v1.selection import validate_frozen_model
    config=json.loads((Path(__file__).resolve().parents[1]/'configs/m5e2e/dev_real_micro_v1.json').read_text())
    assert validate_frozen_model(config)['D']=='2700'
    config['selection']['window']['D']='2701'
    with pytest.raises(ValueError,match='window convention'):validate_frozen_model(config)
    config['selection']['window']['D']='2700'; config['physical']['reserve_kwh']='0'
    with pytest.raises(ValueError,match='physical model'):validate_frozen_model(config)
    config['physical']['reserve_kwh']='6'
    config['provenance']['model_source_sha256']['experiments/m6h_manifest_v1/physical.py']='0'*64
    with pytest.raises(ValueError,match='physical source changed'):validate_frozen_model(config)


@pytest.fixture(scope='module')
def source_osmium_version_gate():
    import importlib
    import sys
    from pathlib import Path

    module = importlib.import_module('experiments.shandong_preprocessing_v1.phases')
    module_path = Path(module.__file__).resolve()
    prefix = Path(sys.prefix).resolve()
    assert module_path.is_relative_to(prefix), (
        f'expected installed phases module under {prefix}, got {module_path}'
    )
    return module._require_osmium_version


@pytest.mark.parametrize(
    'version_line',
    [
        'osmium version 1.18.0',
        'osmium version 1.18.0 (v1.18.0)',
    ],
)
def test_osmium_version_gate_accepts_exact_pinned_lines(version_line, source_osmium_version_gate):
    assert source_osmium_version_gate(version_line + '\nlibosmium version 2.23.0\n') is None


@pytest.mark.parametrize(
    'output',
    [
        '',
        'osmium version 1.18.0',
        'osmium version 1.18.01\n',
        'osmium version 1.19.0\n',
        'osmium version 1.18.0 (v1.18.01)\n',
        'osmium version 1.18.0 (v1.19.0)\n',
        'osmium version 1.18.0 (v1.18.0-dirty)\n',
        'osmium version 1.18.0 (arbitrary suffix)\n',
        'osmium version 1.18.0 unrecognized\n',
    ],
)
def test_osmium_version_gate_rejects_unpinned_or_malformed_output(output, source_osmium_version_gate):
    with pytest.raises(RuntimeError, match='^Pinned osmium version mismatch$'):
        source_osmium_version_gate(output)
