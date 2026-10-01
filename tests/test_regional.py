"""Regional infrastructure contracts; reuse M2's mathematical tests."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest
import shapely
from shapely.geometry import Polygon

from _common import ROOT, configs, read_config, sha256, verified_dataset
from _regional_common import measured_command, polygon_bytes, region_polygon, remap_osm_nodes
from prepare_regional_data import immutable_install
from prepare_regional_model_input import unsupported_candidates
from envelope import NumericalTolerance, build_envelope_from_precomputed, precompute_detour_distances
from envelope.boundary import boundary_node_risk
from envelope.expansion import EnvelopeExpansionPolicy, FixedSchedulePolicy, iter_policy_envelopes
from graph.road_graph import IgraphRoadGraph
from run_regional_benchmark import validate_comparison_schema


def test_polygon_hash_reproduction_and_input_guard():
    config = read_config('configs/regional.yaml')
    polygon, projected, _ = region_polygon(config)
    contents = polygon_bytes(polygon)
    assert contents == (ROOT/config['polygon_path']).read_bytes()
    digest = hashlib.sha256(contents).hexdigest()
    assert digest == json.loads((ROOT/config['results_dir']/'region_design.json').read_text())['polygon_sha256']
    design=json.loads((ROOT/config['results_dir']/'region_design.json').read_text())
    candidate=next(r for r in design['candidates'] if r['margin_km']==config['buffer_km'])
    assert np.isclose(projected.area/1e6,candidate['area_km2'])
    assert polygon_bytes(region_polygon(config,config['buffer_km']+25)[0]) != contents
    with pytest.raises(ValueError,match='checksum'):
        region_polygon({**config,'base_polygon_sha256':'bad'})


def test_original_osm_identity_remapping():
    old = pd.DataFrame({'node_id':[0,1],'osm_node_id':[40,90], 'lat':[46.,46.1], 'lon':[14.,14.1]})
    new = pd.DataFrame({'node_id':[0,1,2],'osm_node_id':[10,40,90], 'lat':[45.,46.,46.1], 'lon':[13.,14.,14.1]})
    mapped = remap_osm_nodes(old,new,[0,1,0],0.5)
    assert [r['extended_node_id'] for r in mapped] == [1,2]
    assert all(r['coordinate_delta_m']==0 for r in mapped)
    with pytest.raises(ValueError,match='Missing OSM'):
        remap_osm_nodes(old,new.iloc[:2],[1],0.5)
    moved = new.copy(); moved.loc[2,'lat']+=0.01
    with pytest.raises(ValueError,match='Coordinate drift'):
        remap_osm_nodes(old,moved,[1],0.5)
    with pytest.raises(ValueError,match='Duplicate'):
        remap_osm_nodes(old,pd.concat([new,new.iloc[:1]]),[0],0.5)


def small_graph():
    nodes = pd.DataFrame({'node_id':[0,1,2], 'osm_node_id':[1,2,3], 'lat':[46.]*3,'lon':[14.,14.01,14.02]})
    edges = pd.DataFrame({'edge_id':[0,1,2], 'source':[0,1,0],'target':[1,2,2],
                          'length_m':[1.,1.,3.], 'travel_time_s':[1.,1.,3.]})
    return IgraphRoadGraph(nodes,edges)


def test_expansion_protocol_schedule_cap_and_manual_stop():
    distances = precompute_detour_distances(small_graph(),0,2)
    policy = FixedSchedulePolicy((1.,1.1,1.4,2.),2.)
    assert isinstance(policy,EnvelopeExpansionPolicy)
    envelopes = list(iter_policy_envelopes(distances,policy,4.))
    assert [e.budget for e in envelopes]==[2.,2.2,2.8,4.]
    assert envelopes[-1].edge_mask.all()
    for ratios,cap in [((1.,1.),2.),((1.,2.1),2.),((float('nan'),),2.)]:
        with pytest.raises(ValueError):FixedSchedulePolicy(ratios,cap)
    class ManualStop:
        def next_budget(self,baseline_cost,current):return baseline_cost if current is None else 2*baseline_cost
        def should_stop(self,current):return True
    assert len(list(iter_policy_envelopes(distances,ManualStop(),4.)))==1
    with pytest.raises(ValueError,match='cap'):
        list(iter_policy_envelopes(distances,policy,2.5))
    class Repeating:
        def next_budget(self,baseline_cost,current):return baseline_cost
        def should_stop(self,current):return False
    with pytest.raises(ValueError,match='increase'):
        list(iter_policy_envelopes(distances,Repeating(),4.))


def test_equivalent_boundary_diagnostic():
    small=Polygon([(13.,45.),(15.,45.),(15.,47.),(13.,47.)])
    large=small.buffer(1)
    lat,lon=np.array([46.,46.,46.]),np.array([14.,13.00001,12.9])
    a,_,_=boundary_node_risk(lat,lon,small,'EPSG:3035',1000)
    b,_,_=boundary_node_risk(lat,lon,large,'EPSG:3035',1000)
    assert a.tolist()==[False,True,True]
    assert not b.any()


def test_cross_dataset_schema_guard():
    row={'instance_id':0,'ratio':1.1,'si_nodes':3,'ext_nodes':4,'si_edges':3,'ext_edges':4,
         'si_budget_s':2.2,'ext_budget_s':2.1,'si_boundary_risk':True,'ext_boundary_risk':False,
         'si_dataset_sha256':'a','ext_dataset_sha256':'b','routing_config_sha256':'c',
         'od_instances_sha256':'d','boundary_sha256':'e'}
    validate_comparison_schema(pd.DataFrame([row]))
    with pytest.raises(ValueError,match='Missing'):
        validate_comparison_schema(pd.DataFrame([{k:v for k,v in row.items() if k!='ext_budget_s'}]))
    with pytest.raises(ValueError,match='Duplicate'):
        validate_comparison_schema(pd.DataFrame([row,row]))


def test_model_domain_quarantine_preserves_supported_classes():
    _,routing=configs()
    histogram={'residential':10,'motorway':3,'via_ferrata':2,'footway':5,
               'platform;bus_stop':1,'crossing':1,'yes':1}
    assert unsupported_candidates(histogram,routing)==['crossing','yes']


def test_raw_freeze_never_replaces_an_existing_artifact(tmp_path):
    source=tmp_path/'source.partial';destination=tmp_path/'frozen.pbf'
    source.write_bytes(b'original immutable content')
    immutable_install(source,destination)
    assert not source.exists() and destination.read_bytes()==b'original immutable content'
    assert destination.stat().st_mode & 0o222 == 0
    source.write_bytes(b'changed content')
    with pytest.raises(FileExistsError):immutable_install(source,destination)
    assert destination.read_bytes()==b'original immutable content'
    assert source.read_bytes()==b'changed content'


def test_memory_monitor_terminates_before_an_unsafe_run(tmp_path):
    output=tmp_path/'monitor.json'
    with pytest.raises(RuntimeError,match='RSS limit'):
        measured_command([sys.executable,'-c','import time; time.sleep(5)'],output,
                         rss_limit_gib=0.00001,reserve_gib=0,interval=0.01)
    result=json.loads(output.read_text())
    assert result['aborted']=='RSS limit' and result['exit_code'] != 0


def osmium_binary(request):
    path=os.environ.get('HIROUTE_OSMIUM') or shutil.which('osmium') or '/home/dy/HiRoute/osmium-env/bin/osmium'
    if not Path(path).exists():
        if request.config.getoption('--require-regional-results'):
            pytest.fail('Pinned osmium-tool 1.18.0 required; set HIROUTE_OSMIUM')
        pytest.skip('Regional streaming tool absent; M1–M2 remain independently reproducible')
    return path


def test_streaming_extraction_reproducibility_and_complete_ways(tmp_path,request):
    osmium=osmium_binary(request)
    source=tmp_path/'toy.osm'
    source.write_text('''<?xml version="1.0"?><osm version="0.6">
<node id="1" version="1" lat="46" lon="14"/>
<node id="2" version="1" lat="46" lon="14.01"/>
<node id="3" version="1" lat="46" lon="14.1"/>
<way id="10" version="1"><nd ref="1"/><nd ref="2"/><nd ref="3"/><tag k="highway" v="primary"/></way>
</osm>''')
    polygon=tmp_path/'region.geojson'
    polygon.write_bytes(polygon_bytes(Polygon([(13.99,45.99),(14.02,45.99),(14.02,46.01),(13.99,46.01)])))
    outputs=[]
    for suffix in ['a','b']:
        crop=tmp_path/(suffix+'.crop.pbf'); roads=tmp_path/(suffix+'.roads.pbf')
        for command in [[osmium,'extract','-p',str(polygon),'-s','complete_ways',str(source),'-o',str(crop)],
                        [osmium,'tags-filter',str(crop),'w/highway','-o',str(roads)],
                        [osmium,'check-refs',str(roads)]]:
            subprocess.run(command,check=True,capture_output=True,env={**os.environ,'OSMIUM_POOL_THREADS':'1'})
        outputs.append(roads)
    assert sha256(outputs[0])==sha256(outputs[1])
    xml=subprocess.check_output([osmium,'cat',str(outputs[0]),'-f','osm'],text=True)
    assert 'id="3"' in xml # Entire crossing way, including its out-of-polygon node.


@pytest.mark.integration
def test_extended_construction_od_preservation_and_containment(request):
    required=[ROOT/'configs/data_extended.yaml',ROOT/'results/milestone_3a/benchmark.json']
    if not all(p.exists() for p in required):
        if request.config.getoption('--require-regional-results'):
            pytest.fail('Build and benchmark the frozen extended graph first')
        pytest.skip('Extended experiment absent')
    config=read_config('configs/regional.yaml')
    data,routing=configs('configs/data_extended.yaml')
    verified_dataset(data)
    metadata=json.loads((ROOT/data['graph_dir']/'metadata.json').read_text())
    assert metadata['run']['configuration']['routing']==routing
    for name,record in metadata['files'].items():assert sha256(ROOT/data['graph_dir']/name)==record['sha256']
    calibration=json.loads((ROOT/'results/milestone_3a/calibration.json').read_text())
    assert calibration['parquet_byte_identical']
    assert json.loads((ROOT/'results/milestone_3a/extraction_reproducibility.json').read_text())['byte_identical']
    assert json.loads((ROOT/'results/milestone_3a/model_input_reproducibility.json').read_text())['byte_identical']
    assert json.loads((ROOT/'results/milestone_3a/model_calibration.json').read_text())['parquet_byte_identical']
    model=json.loads((ROOT/'results/milestone_3a/model_input_provenance.json').read_text())
    assert model['resulting_pbf_sha256']==data['dataset']['sha256']
    assert sum(model['quarantined_parsed_segments'].values())==125
    assert model['quarantined_way_count']==21
    assert not set(model['quarantined_highway_classes']) & set(routing['speed_model']['class_kph'])
    result=json.loads((ROOT/'results/milestone_3a/benchmark.json').read_text())
    design=json.loads((ROOT/'results/milestone_3a/region_design.json').read_text())
    selected=next(r for r in design['candidates'] if r['margin_km']==config['buffer_km'])
    assert np.isclose(result['source_gap_area_km2'],selected['source_proxy_uncovered_area_km2'],rtol=1e-7)
    from _common import load_graph
    graph=load_graph(data,routing)
    original=pd.read_parquet(ROOT/'data/processed/od_instances.parquet')
    remapped=pd.read_parquet(ROOT/'results/milestone_3a/od_remapping.parquet')
    assert remapped.instance_id.tolist()==original.instance_id.tolist()
    assert len(remapped)==30
    assert (remapped.origin_snap_delta_m.abs()<=config['coordinate_tolerance_m']).all()
    assert (remapped.destination_snap_delta_m.abs()<=config['coordinate_tolerance_m']).all()
    for side in ['origin','destination']:
        assert np.array_equal(graph.nodes.iloc[remapped[side+'_node']].osm_node_id,remapped[side+'_osm_node_id'])
    # Independent real route checks on all preserved ODs; no new sampling suite.
    for row in remapped.itertuples():
        edges=list(row.path_edges);nodes=list(row.path_nodes)
        assert np.array_equal(graph.source[edges],nodes[:-1])
        assert np.array_equal(graph.target[edges],nodes[1:])
        assert np.isclose(graph.weights['travel_time'][edges].sum(),row.ext_baseline_time_s)
    checks=pd.read_parquet(ROOT/'results/milestone_3a/path_containment_tests.parquet')
    assert not checks.violation.any() and checks.within_budget.any()
    assert checks.instance_id.nunique()==30 and checks.ratio.nunique()==7
    table=pd.read_parquet(ROOT/'results/milestone_3a/envelope_stats.parquet')
    assert len(table)==210
    for _,group in table.groupby('instance_id'):
        group=group.sort_values('ratio')
        assert (group.nodes.diff().dropna()>=0).all() and (group.edges.diff().dropna()>=0).all()
        assert group.ratio.max()==2.
    # Recompute one extended OD independently of saved membership diagnostics.
    od=remapped.iloc[0]
    distances=precompute_detour_distances(graph,int(od.origin_node),int(od.destination_node))
    for expected in table.loc[table.instance_id.eq(int(od.instance_id))].itertuples():
        envelope=build_envelope_from_precomputed(distances,float(expected.ratio)*distances.baseline_cost)
        assert int(envelope.node_mask.sum())==expected.nodes
        assert int(envelope.edge_mask.sum())==expected.edges
        assert envelope.node_mask[list(od.path_nodes)].all()
        assert envelope.edge_mask[list(od.path_edges)].all()
    validate_comparison_schema(pd.read_parquet(ROOT/'results/milestone_3a/envelope_comparison.parquet'))
