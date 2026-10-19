"""Opt-in real pinned-parser qualification; generated synthetic OSM only.
Run: HIROUTE_PYROSM_QUALIFICATION=1 OSMIUM_BINARY=/path/osmium pytest -q tests/test_way_partition_semantics.py
"""
from pathlib import Path
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import pytest
import pandas as pd
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'experiments/shandong_preprocessing_v1'))
pytestmark=pytest.mark.skipif(os.getenv('HIROUTE_PYROSM_QUALIFICATION')!='1', reason='Opt-in pinned pyrosm/osmium integration')
WAYS=[(10,[1,2,3],{'highway':'residential'}),
 (11,[1,2],{'highway':'residential','maxspeed':'20','maxspeed:forward':'10','maxspeed:backward':'15'}),
 (12,[3,4],{'highway':'primary','oneway':'-1','maxspeed:forward':'5','maxspeed:backward':'25'}),
 (13,[4,5],{'highway':'secondary','oneway':'reverse'}),
 (14,[1,2,3,1,2],{'highway':'residential'}),
 (15,[6,6,7],{'highway':'tertiary'}),
 (16,[7,8],{'highway':'residential','access':'yes;permissive'}),
 (17,[8,9],{'highway':'residential','maxspeed':'30;20'}),
 (18,[9,10],{'highway':'residential','oneway':'no;yes'}),
 (19,[10,11,12,10],{'highway':'yes','building':'yes','amenity':'shelter'}),
 (20,[12,13],{'highway':'street_lamp'}),
 (21,[13,14],{'highway':'residential','access:conditional':'no @ (Mo-Fr)'}),
 (22,[14,15],{'highway':'residential','oneway':'yes'}),
 (23,[15,16],{'highway':'residential','highway:note':'fixture','name':'Unicode 路','maxspeed':'10 mph'}),
 (24,[16,17],{'highway':'residential','oneway:motorcar':'-1','oneway':'yes'})]

@pytest.fixture
def native():
    pytest.importorskip('pyrosm'); pytest.importorskip('osmium')
    assert importlib.metadata.version('pyrosm')=='0.13.1'
    path=os.getenv('OSMIUM_BINARY') or shutil.which('osmium')
    if not path: pytest.skip('Native osmium required')
    return path

@pytest.fixture
def routing():
    return yaml.safe_load((ROOT/'configs/routing.yaml').read_text())

def fixture_pbf(tmp_path, native, ways, missing=()):
    root=ET.Element('osm',version='0.6',generator='hiroute-semantics-test')
    for n in sorted({n for _,refs,_ in ways for n in refs}-set(missing)):
        ET.SubElement(root,'node',id=str(n),version='1',lat=str(36+n/10000),lon=str(117+n/10000))
    for wid,refs,tags in ways:
        w=ET.SubElement(root,'way',id=str(wid),version='1')
        for n in refs: ET.SubElement(w,'nd',ref=str(n))
        for k,v in tags.items(): ET.SubElement(w,'tag',k=k,v=v)
    xml=tmp_path/'fixture.osm'; pbf=tmp_path/'fixture.pbf'
    ET.ElementTree(root).write(xml,encoding='utf-8',xml_declaration=True)
    subprocess.run([native,'cat',str(xml),'-o',str(pbf)],check=True)
    return pbf

def partition(tmp_path,native,pbf,routing,**kw):
    from way_partition import build_partitioned_graph
    scratch=tmp_path/'scratch';out=tmp_path/'out';scratch.mkdir();out.mkdir()
    audit=build_partitioned_graph(pbf,scratch,out,routing,native,tmp_path/'progress.json',**kw)
    return pd.read_parquet(out/'nodes.parquet'),pd.read_parquet(out/'edges.parquet'),audit

@pytest.mark.parametrize('chunk_ways',[2,7])
def test_exact_whole_way_equivalence(tmp_path,native,routing,chunk_ways):
    from pyrosm import OSM
    from graph.preprocessing import ATTRIBUTES,normalize_network
    from graph.raw_way_policy import read_raw_way_policy
    pbf=fixture_pbf(tmp_path,native,WAYS)
    n,e=OSM(str(pbf),workers=1).get_network(network_type='driving',nodes=True,extra_attributes=ATTRIBUTES)
    expected=normalize_network(n,e,routing,raw_way_policy=read_raw_way_policy(pbf))
    actual=partition(tmp_path,native,pbf,routing,max_ways=chunk_ways)
    for a,b in zip(expected[:2],actual[:2]):pd.testing.assert_frame_equal(a,b,check_exact=True)
    assert expected[2]==actual[2]
    nodes,edges,audit=actual
    assert len(nodes)==13 and len(edges)==24 and audit['unused_parser_nodes']==4
    assert sum(edges.osm_way_id.eq(14))==8
    assert set(edges.loc[edges.osm_way_id.eq(12),'speed_kph'])=={25.}
    assert audit['excluded_closed_shelter_contour']==3

@pytest.mark.parametrize('ways,limit,match',[
    ([(1,[1,2,3],{'highway':'residential'})],2,'reference bound'),
    ([(1,[1,2],{'highway':'residential'}),(1,[2,3],{'highway':'residential'})],10,'strictly ordered'),
    ([(2,[1,2],{'highway':'residential'}),(1,[2,3],{'highway':'residential'})],10,'strictly ordered'),
])
def test_partition_bounds_and_order_fail_closed(tmp_path,native,ways,limit,match):
    from way_partition import partition_ids
    pbf=fixture_pbf(tmp_path,native,ways);chunks=tmp_path/'chunks';chunks.mkdir()
    with pytest.raises(ValueError,match=match):partition_ids(pbf,chunks,limit,1)

@pytest.mark.parametrize('ways',[ [WAYS[9],WAYS[10],WAYS[11]], [(50,[1,2],{'highway':'service'})] ])
def test_globally_empty_fails(tmp_path,native,routing,ways):
    pbf=fixture_pbf(tmp_path,native,ways)
    with pytest.raises(ValueError,match='No driving edges survive'):partition(tmp_path,native,pbf,routing,max_ways=1)

def test_unknown_class_still_fails_in_excluded_chunk(tmp_path,native,routing):
    # access destination is retained by pyrosm but excluded by canonical policy.
    ways=[WAYS[0],(50,[1,2],{'highway':'unmodeled_class','access':'destination'})]
    pbf=fixture_pbf(tmp_path,native,ways)
    with pytest.raises(subprocess.CalledProcessError):partition(tmp_path,native,pbf,routing,max_ways=1)

def test_missing_reference_fails_before_parse(tmp_path,native,routing):
    pbf=fixture_pbf(tmp_path,native,[WAYS[0]],missing=[2])
    with pytest.raises(subprocess.CalledProcessError):partition(tmp_path,native,pbf,routing,max_ways=1)

def test_zero_length_policy_still_sets_global_schema(tmp_path,native,routing):
    from pyrosm import OSM
    from graph.preprocessing import ATTRIBUTES,normalize_network
    ways=[(1,[1,2],{'highway':'residential'}),(2,[2,2],{'highway':'residential','name':'Ghost','maxspeed':'20','access':'permissive'})]
    pbf=fixture_pbf(tmp_path,native,ways)
    n,e=OSM(str(pbf),workers=1).get_network(network_type='driving',nodes=True,extra_attributes=ATTRIBUTES)
    expected=normalize_network(n,e,routing)
    actual=partition(tmp_path,native,pbf,routing,max_ways=1)
    assert len(e)==2 and len(expected[1])==2
    assert str(expected[1]['name'].dtype)=='str'
    for a,b in zip(expected[:2],actual[:2]):pd.testing.assert_frame_equal(a,b,check_exact=True)
    assert expected[2]==actual[2]
