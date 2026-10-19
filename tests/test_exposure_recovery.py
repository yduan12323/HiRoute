import copy
import pytest
from experiments.m6h_selection_v1 import rules
from experiments.exposure_recovery_v1.build import walk_endpoints

G = dict(nodes_sha256='1'*64, edges_sha256='2'*64)
OTHER = dict(nodes_sha256='3'*64, edges_sha256='4'*64)

def ep(sid, node, lat, lon):
    return dict(site_id=sid, access_node=node, lat=lat, lon=lon)

def fixture(graph=OTHER, lat=40):
    r = dict(schema=rules.RECOVERY_SCHEMA, strict_independent_holdout_claim=False,
             coverage=dict(status='incomplete_recovery',known_missing_artifacts=[dict(gap_id='lost',description='Original lost')]),
             sources=[dict(source_id='s',sha256='a'*64)], records=[dict(source_id='s',reason="screened",graph_identity=dict(graph),
             origin=ep('a',1,lat,10),destination=ep('b',2,lat+3,15))], inspected_endpoints=[])
    return r

def admission(r):
    return dict(schema=rules.RECOVERY_SCHEMA,registry_sha256=rules.digest(r),
                gap_list_sha256=rules.digest(r['coverage']['known_missing_artifacts']),
                purpose='new_map_correctness_and_performance_validation',strict_independent_holdout_claim=False)

def select(rows,r):
    return rules.select_od_slate(rows,r,site_catalog_sha256='c'*64,recovery_admission=admission(r),graph_file_identity=G)

def test_strict_default_rejects_recovery():
    with pytest.raises(rules.InvalidInput):
        rules.validate_exposures(fixture())
    with pytest.raises(rules.InvalidInput):
        rules.select_od_slate([],fixture(),site_catalog_sha256='c'*64)

def test_admission_binds_artifact_and_gaps():
    r=fixture(); a=admission(r)
    rules.validate_recovered_exposures(r,a)
    for key in ('registry_sha256','gap_list_sha256','schema','purpose','strict_independent_holdout_claim'):
        bad=copy.deepcopy(a);bad[key]='wrong'
        with pytest.raises(rules.InvalidInput):rules.validate_recovered_exposures(r,bad)
    r['coverage']['known_missing_artifacts'][0]['description']='Changed'
    with pytest.raises(rules.InvalidInput):rules.validate_recovered_exposures(r,a)

def test_local_ids_do_not_cross_graphs():
    rows=[ep('a',1,0,0),ep('b',2,3,3)]
    assert select(rows,fixture())['selected_group_count']==1
    assert select(rows,fixture(G))['selected_group_count']==0
    # Same node hash alone is insufficient: edges are part of graph identity.
    assert select(rows,fixture(dict(nodes_sha256=G['nodes_sha256'],edges_sha256='5'*64)))['selected_group_count']==1

def test_cross_graph_geography_still_excluded():
    rows=[ep('x',11,40,10),ep('y',12,43,15)]
    assert select(rows,fixture())['selected_group_count']==0

def test_inspected_geography_is_cross_source():
    r=fixture();r['inspected_endpoints']=[dict(source_id='s',reason='screen',graph_identity=OTHER,endpoint=ep('old',50,0,0))]
    assert select([ep('a',1,0,0),ep('b',2,3,3)],r)['selected_group_count']==0

def test_complete_graph_required():
    r=fixture();r['records'][0]['graph_identity'].pop('edges_sha256')
    with pytest.raises(rules.InvalidInput):rules.validate_recovered_exposures(r,admission(r))

def test_all_nested_screen_occurrences_are_retained():
    e=ep('a',1,0,0)
    assert len(list(walk_endpoints({'regions':{'one':[e,e]},'extrema':[e]})))==3

def test_builder_exact_sources_and_rejected_pairs(tmp_path):
    import json
    import subprocess
    from experiments.exposure_recovery_v1.build import build, sha
    repo=tmp_path/'repo';repo.mkdir()
    def git(*args):return subprocess.check_output(['git','-C',str(repo),*args])
    git('init','-q')
    a,b=ep('a',1,0,0),ep('b',2,3,3)
    screen=dict(nodes_sha256=G['nodes_sha256'],fixed_grid_candidates=[a,b])
    path='x/geographic_screen_v5_grid14.json'
    blobs={path:json.dumps(screen).encode()}
    blobs['x/grid14_distance_p0.json']=json.dumps(dict(graph_nodes_sha256=G['nodes_sha256'],
        graph_edges_sha256=G['edges_sha256'],geographic_screen_sha256=sha(blobs[path]),pair_count=1,
        pairs=[dict(origin_site='a',destination_site='b',origin_anchor=1,destination_anchor=2,distance_cost_m=None)])).encode()
    for name,raw in blobs.items():
        target=repo/name;target.parent.mkdir(exist_ok=True);target.write_bytes(raw)
    git('add','.');git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','tiny fixture')
    config=dict(source_revision='HEAD',sources=[dict(path=p,sha256=sha(raw)) for p,raw in blobs.items()],
                known_missing_artifacts=fixture()['coverage']['known_missing_artifacts'])
    r,inventory=build(repo,config)
    assert r['counts']['pair_occurrences']==1
    assert r['counts']['inspected_endpoint_occurrences']==2
    assert len(inventory)==2
    assert r['records'][0]['destination']==b
    rules.validate_recovered_exposures(r,admission(r))
    # Authenticated external inputs: graph-node and Site geometry intentionally differ.
    import pandas as pd
    external=tmp_path/'external';external.mkdir()
    (external/'metadata.json').write_text(json.dumps({'files':{'nodes.parquet':{'sha256':G['nodes_sha256']},
                                                             'edges.parquet':{'sha256':G['edges_sha256']}}}))
    pd.DataFrame([dict(origin_node=10,destination_node=20,graph_nodes_sha256=G['nodes_sha256'],
                       graph_edges_sha256=G['edges_sha256'])]*30).to_parquet(external/'od_remapping.parquet')
    pd.DataFrame([dict(a,lat=0.001),b]).to_parquet(external/'stop_sites.parquet')
    config['external_inputs']=[dict(path=f.name,filename=f.name,sha256=sha(f.read_bytes())) for f in sorted(external.iterdir())]
    manifest={'files':[dict(path=x['path'],expected_sha256=x['sha256']) for x in config['external_inputs']]}
    raw=json.dumps(manifest).encode();(repo/'manifest.json').write_bytes(raw)
    git('add','.');git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','external manifest')
    config['external_input_manifest']='manifest.json'
    config['sources'].append(dict(path='manifest.json',sha256=sha(raw)))
    r,_=build(repo,config,external)
    assert r['counts']['anchor_only_pair_occurrences']==30
    assert r['records'][0]['origin']['lat']==0
    assert r['inspected_endpoints'][-2]['endpoint']['lat']==0.001
    assert r['inspected_endpoints'][-2]['coordinate_role']=='site_geometry_not_access_node'
    rules.validate_recovered_exposures(r,admission(r))
    with pytest.raises(ValueError,match='external input directory'):build(repo,config)
    config['sources'][0]['sha256']='0'*64
    with pytest.raises(ValueError,match='hash mismatch'):build(repo,config,external)

def test_anchor_only_dev_records_are_graph_scoped_without_guessed_coordinates():
    r=fixture();r['anchor_only_exposures']=[dict(source_id='s',reason='coordinates unavailable',graph_identity=G,
                                              origin_anchor=1,destination_anchor=99)]
    rows=[ep('new-a',1,0,0),ep('new-b',2,3,3)]
    assert select(rows,r)['selected_group_count']==0
    r['anchor_only_exposures'][0]['graph_identity']=OTHER
    assert select(rows,r)['selected_group_count']==1
    r['anchor_only_exposures'][0]['origin_anchor']=True
    with pytest.raises(rules.InvalidInput):select(rows,r)
