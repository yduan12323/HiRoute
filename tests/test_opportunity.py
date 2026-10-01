"""Milestone 4A evidence/identity contracts and adversarial decision-region cases."""
from dataclasses import replace
import json
import subprocess
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
import shapely
from shapely.geometry import Polygon
from _common import ROOT,read_config,sha256
from _regional_common import polygon_bytes
from envelope import precompute_detour_distances,build_envelope_from_precomputed,NumericalTolerance
from graph.road_graph import IgraphRoadGraph
from opportunity import (OpportunityId,Opportunity,Provenance,DecisionOpportunity,ODContext,
                         decision_features,eligible_opportunities,attach_opportunities,
                         GeographicRegionBuilder,DecisionRegionBuilder)
from opportunity.regions import NeighborPair
from opportunity.metrics import region_statistics,expansion_stability
from opportunity.network import validate_network_pairs
from opportunity.taxonomy import classify_tags,filter_expressions
from prepare_opportunity_data import object_catalogue,parse_geometry,export_identity

CFG=read_config('configs/opportunity.yaml')


def opportunity(i,lat=46.,lon=14.,node=0,capabilities=('meal',)):
    return Opportunity(OpportunityId('node',i),lat,lon,frozenset(capabilities),'amenity=restaurant',{},
                       Provenance(('toy-260929',),'2026-09-29T20:22:51Z','OSM node'),node,node,0.,'attached')


def graph():
    nodes=pd.DataFrame({'node_id':range(5),'osm_node_id':range(101,106),'lat':[46.]*5,'lon':[14.,14.001,14.002,14.003,14.02]})
    edges=pd.DataFrame({'edge_id':range(6),'source':[0,1,0,2,1,3],'target':[1,3,2,3,0,1],
                        'length_m':[100.,100.,100.,100.,100.,100.], 'travel_time_s':[50.,50.,200.,200.,50.,50.]})
    return IgraphRoadGraph(nodes,edges)


@pytest.mark.parametrize('tags,capabilities',[
    ({'amenity':'charging_station'},{'charge'}),({'amenity':'restaurant'},{'meal'}),({'amenity':'cafe'},{'meal'}),
    ({'tourism':'hotel'},{'sleep'}),({'shop':'supermarket'},{'groceries'}),({'amenity':'pharmacy'},{'pharmacy'}),
    ({'highway':'services'},{'services','rest'}),({'highway':'rest_area'},{'rest'}),({'amenity':'toilets'},{'toilets'}),
    ({'amenity':'parking'},{'parking'}),({'amenity':'parking_space'},set()),({'amenity':'parking','capacity':'2'},set()),
    ({'amenity':'parking','capacity':'unknown'},{'parking'}),({'shop':'clothes'},set()),({'tourism':'museum'},set()),
    ({'amenity':'restaurant','access':'private'},set()),({'tourism':'hotel','amenity':'charging_station'},{'sleep','charge'})])
def test_taxonomy_explicit_only(tags,capabilities):
    assert classify_tags(tags,CFG['extraction'])[0]==frozenset(capabilities)
    assert tags==dict(tags) # Classification never modifies evidence.


def test_typed_identity_and_unknown_tags():
    objects=[OpportunityId(t,7) for t in ['node','way','relation']]
    assert len(set(objects))==3
    with pytest.raises(ValueError):OpportunityId('area',7)
    tags={'name':'Original','socket:type2':'unknown'}
    o=replace(opportunity(1),original_tags=tags);tags['name']='Changed'
    assert o.original_tags['name']=='Original'
    with pytest.raises(TypeError):o.original_tags['quality']='good'


def test_candidate_attachment_and_excessive_rejection():
    g=graph();config=CFG['attachment']
    rows=attach_opportunities([opportunity(1,lon=14.001),opportunity(2,lat=47.)],g,np.array(['residential']*6),config)
    assert rows[0].access_node==1 and rows[0].access_osm_node_id==102 and rows[0].attachment_status=='attached'
    assert rows[1].access_distance_m>1000 and rows[1].attachment_status=='excessive_snap'
    rows=attach_opportunities([opportunity(1)],g,np.array(['motorway']*6),config)
    assert rows[0].attachment_status=='no_candidate'


def test_od_detour_progress_eligibility_and_unreachable():
    d=precompute_detour_distances(graph(),0,3)
    features=decision_features([opportunity(1,node=1),opportunity(2,node=2),opportunity(3,node=4)],d,[(0,0)]*3)
    assert len(features)==2
    a,b=features
    assert a.progress==.5 and a.detour_cost==0 and a.detour_ratio==1
    assert b.progress==.5 and b.detour_cost==300 and b.detour_ratio==4
    assert len(eligible_opportunities(features,100))==1
    assert len(eligible_opportunities(features,400))==2
    assert len(eligible_opportunities(features,400-1e-7,NumericalTolerance(1e-6,0)))==2
    assert len(eligible_opportunities(features,400-1e-7,NumericalTolerance(0,0)))==1
    with pytest.raises(ValueError):decision_features([],replace(d,baseline_cost=0),[])


def context():
    d=precompute_detour_distances(graph(),0,3)
    return ODContext(0,d),build_envelope_from_precomputed(d,400)


def decision(i,x=0,r=.5,detour=0,node=1):
    return DecisionOpportunity(opportunity(i,node=node),100+detour,detour,(100+detour)/100,r,x,0)


def test_case_a_geographically_close_different_detour():
    a,b=decision(1),decision(2,x=20,detour=300,node=2)
    pairs=[NeighborPair(a.identity,b.identity,20,100)]
    ctx,envelope=context()
    assert len(GeographicRegionBuilder({'local_radius_m':100},pairs).build_regions([a,b],ctx,envelope))==1
    assert len(DecisionRegionBuilder(CFG['regions']['decision_aware'],pairs).build_regions([a,b],ctx,envelope))==2


def test_case_b_moderate_separation_same_stage():
    a,b=decision(1),decision(2,x=1000,r=.51,detour=60)
    pairs=[NeighborPair(a.identity,b.identity,1000,1500)]
    ctx,envelope=context()
    assert len(DecisionRegionBuilder(CFG['regions']['decision_aware'],pairs).build_regions([a,b],ctx,envelope))==1
    assert len(GeographicRegionBuilder({'local_radius_m':500},pairs).build_regions([a,b],ctx,envelope))==2


def test_case_c_river_network_separation_native(tmp_path):
    g=graph()
    # Disconnected road node 4 placed nearby; geographic projection alone misleads.
    ops=[opportunity(1,node=1),opportunity(2,node=4),opportunity(3,node=3)]
    pairs,distances,indices,meta=validate_network_pairs(g,ops,np.array([[0.,0.],[10.,0.],[20.,0.]]),CFG['network'],tmp_path)
    assert any(np.isinf(p.network_m) for p in pairs if p.first.osm_id==1 and p.second.osm_id==2)
    connected=next(p for p in pairs if p.first.osm_id==1 and p.second.osm_id==3)
    assert connected.network_m==100
    for p,ds in zip(pairs,distances,strict=True):assert p.network_m==max(ds)
    # Identical route features are still separated if local network validation fails.
    a,b=decision(1),decision(2,x=10)
    ctx,envelope=context()
    barrier=[NeighborPair(a.identity,b.identity,10,np.inf)]
    assert len(GeographicRegionBuilder({'local_radius_m':100},barrier).build_regions([a,b],ctx,envelope))==1
    assert len(DecisionRegionBuilder(CFG['regions']['decision_aware'],barrier).build_regions([a,b],ctx,envelope))==2


def test_determinism_range_constraints_statistics_and_capabilities():
    ops=[decision(i,x=i*10,r=.5+i*.014,detour=i*80) for i in range(1,4)]
    ops[0]=replace(ops[0],opportunity=replace(ops[0].opportunity,capabilities=frozenset({'charge'})))
    pairs=[NeighborPair(ops[i].identity,ops[j].identity,10,100) for i,j in [(0,1),(1,2)]]
    ctx,envelope=context();builder=DecisionRegionBuilder(CFG['regions']['decision_aware'],pairs)
    a=builder.build_regions(ops,ctx,envelope);b=builder.build_regions(list(reversed(ops)),ctx,envelope)
    assert a==b and len(a)==2
    assert all(r.progress_max-r.progress_min<=.025 for r in a)
    records,summary=region_statistics(a,ops,pairs,CFG["regions"]["decision_aware"]["network_radius_m"])
    assert summary['eligible_opportunities']==3 and summary['region_count']==2
    assert summary['compression_ratio']==pytest.approx(1/3)
    assert summary['network_disconnected_region_fraction']==0
    assert summary['charge+meal_regions']==1
    assert all(r.access_nodes==(1,) for r in a)


def test_expansion_stability_detects_growth_merge_and_split():
    ctx,envelope=context();ops=[decision(i,x=i*10) for i in range(1,5)]
    geo=GeographicRegionBuilder({'local_radius_m':1})
    singleton=geo.build_regions(ops[:2],ctx,envelope)
    pairs=[NeighborPair(ops[0].identity,ops[1].identity,1,1)]
    merged=GeographicRegionBuilder({'local_radius_m':10},pairs).build_regions(ops,ctx,envelope)
    result=expansion_stability(singleton,merged)
    assert result['new_opportunity_count']==2 and result['merged_current_regions']==1
    assert result['new_regions_without_old_members']==2 and result['adjusted_rand_common']==0
    assert expansion_stability(merged,singleton)['split_old_regions']==1
    assert expansion_stability(merged,merged)['adjusted_rand_common']==1
    assert expansion_stability(merged,merged)['mean_best_full_member_jaccard']==1


def test_streaming_node_way_relation_identity_and_source_overlap(tmp_path):
    osmium=str(ROOT.parent/'osmium-env/bin/osmium')
    source=tmp_path/'toy.osm'
    source.write_text('''<osm version="0.6">
<node id="1" version="1" lat="46" lon="14"><tag k="amenity" v="cafe"/></node>
<node id="2" version="1" lat="46" lon="14.001"/><node id="3" version="1" lat="46.001" lon="14.001"/>
<node id="4" version="1" lat="46.001" lon="14"/>
<way id="10" version="1"><nd ref="1"/><nd ref="2"/><nd ref="3"/><nd ref="4"/><nd ref="1"/><tag k="amenity" v="parking"/></way>
<relation id="20" version="1"><member type="way" ref="10" role="outer"/><tag k="type" v="multipolygon"/><tag k="tourism" v="hotel"/></relation>
</osm>''')
    pbf=tmp_path/'source.pbf';subprocess.run([osmium,'cat',str(source),'-o',str(pbf)],check=True,capture_output=True)
    filtered=tmp_path/'filtered.pbf';subprocess.run([osmium,'tags-filter',str(pbf),*filter_expressions(CFG['extraction']),'-o',str(filtered)],check=True,capture_output=True)
    merged=tmp_path/'merged.pbf';subprocess.run([osmium,'merge',str(filtered),str(filtered),'-o',str(merged)],check=True,capture_output=True)
    catalogue=object_catalogue(osmium,merged,CFG['extraction'])
    assert set(catalogue)=={('node',1),('way',10),('relation',20)}
    assert object_catalogue(osmium,filtered,CFG['extraction'])==catalogue
    out=tmp_path/'geometry.geojsonseq'
    subprocess.run([osmium,'export',str(merged),'-u','type_id','-f','geojsonseq','-o',str(out)],check=True,capture_output=True)
    rows,excluded,_=parse_geometry(out,catalogue,Polygon([(13.9,45.9),(14.1,45.9),(14.1,46.1),(13.9,46.1)]))
    assert len(rows)==3 and not excluded
    for row in rows:
        if row['osm_type'] in ('way','relation'):
            assert 'point-on-surface' in row['geometry_method']
            assert shapely.from_wkb(row['geometry_wkb']).covers(shapely.Point(row['lon'],row['lat']))
    missing={**catalogue,('relation',99):catalogue[('relation',20)]}
    assert parse_geometry(out,missing,Polygon([(13.9,45.9),(14.1,45.9),(14.1,46.1),(13.9,46.1)]))[1][0]['reason']=='no_exportable_geometry'


@pytest.mark.integration
def test_frozen_opportunity_reproducibility_and_full_experiment(request):
    result=ROOT/CFG['results_dir'];path=result/'benchmark.json'
    if not path.exists():
        if request.config.getoption('--require-opportunity-results'):pytest.fail('Run Milestone 4A benchmark first')
        pytest.skip('Milestone 4A benchmark absent')
    import yaml
    raw=ROOT/CFG['raw_dir'];manifest=yaml.safe_load((raw/'MANIFEST.yaml').read_text())
    for name,digest in manifest['files'].items():assert sha256(raw/name)==digest
    reproduced=json.loads((result/'extraction_reproducibility.json').read_text())
    assert reproduced['byte_identical'] and reproduced['files']==manifest['files']
    assert json.loads((result/'network_compact_reproducibility.json').read_text())['byte_identical']
    assert manifest['snapshot_timestamp']=='2026-09-29T20:22:51Z'
    assert manifest['raw_candidate_count']-manifest['duplicate_count']==manifest['unique_candidate_count']
    benchmark=json.loads(path.read_text());assert benchmark['od_count']==30 and benchmark['ratio_count']==7
    for name,digest in benchmark['result_files'].items():assert sha256(result/name)==digest
    stats=pd.read_parquet(result/'region_stats.parquet');assert len(stats)==420
    assert stats.groupby(['instance_id','method']).size().eq(7).all()
    assert stats[stats.ratio==2].groupby('method').boundary_risk.sum().eq(9).all()
    membership=pd.read_parquet(result/'region_membership.parquet')
    assert not membership.duplicated(['instance_id','ratio','method','osm_type','osm_id']).any()
    sizes=membership.groupby(['instance_id','ratio','method']).size()
    for row in stats.itertuples():assert sizes.get((row.instance_id,row.ratio,row.method),0)==row.eligible_opportunities
    features=pd.read_parquet(result/'od_features.parquet')
    merged=membership.merge(features,on=['instance_id','osm_type','osm_id'],validate='many_to_one')
    assert (merged.through_cost_s<=merged.budget_s+1e-8+1e-10*merged.budget_s).all()
    assert features.progress.between(0,1).all()
    regions=pd.read_parquet(result/'regions.parquet')
    decision=regions[regions.construction_method=='decision-aware']
    assert (decision.progress_spread<=CFG['regions']['decision_aware']['progress_tolerance']+1e-12).all()
    assert (decision.detour_spread_s<=CFG['regions']['decision_aware']['detour_tolerance_s']+1e-8).all()
    assert decision.local_network_components.eq(1).all()
    stability=pd.read_parquet(result/'expansion_stability.parquet');assert len(stability)==360
    assert stability.removed_opportunity_count.eq(0).all()
    sensitivity=pd.read_parquet(result/'parameter_sensitivity.parquet');assert len(sensitivity)==30*4*7


def test_compact_sparse_and_native_kernel_match_python_reference(tmp_path):
    from opportunity.sparse import NeighborIndex,load_union_kernel
    kernel=load_union_kernel(CFG['network'],tmp_path)
    rng=np.random.default_rng(20261001);ctx,envelope=context()
    for count in [0,1,2,12,40]:
        ops=[decision(i+1,x=float(rng.uniform(0,3500)),r=float(rng.uniform(.1,.2)),detour=float(rng.uniform(0,600))) for i in range(count)]
        candidate=[(i,j) for i in range(count) for j in range(i+1,count)]
        pairs=[NeighborPair(ops[i].identity,ops[j].identity,abs(ops[i].x_m-ops[j].x_m),float(rng.choice([100,1000,np.inf]))) for i,j in candidate]
        order=sorted(range(len(pairs)),key=lambda k:(pairs[k].geographic_m,pairs[k].first,pairs[k].second))
        index=NeighborIndex(tuple(o.identity for o in ops),np.array([candidate[k][0] for k in order],dtype=np.int64),
            np.array([candidate[k][1] for k in order],dtype=np.int64),np.array([pairs[k].geographic_m for k in order]),
            np.array([pairs[k].network_m for k in order]))
        for builder in [GeographicRegionBuilder(CFG['regions']['geographic_baseline'],pairs),DecisionRegionBuilder(CFG['regions']['decision_aware'],pairs)]:
            reference=builder.build_regions(ops,ctx,envelope)
            native=(GeographicRegionBuilder(builder.config,index) if builder.method=='geographic baseline'
                    else DecisionRegionBuilder(builder.config,index,kernel)).build_regions(list(reversed(ops)),ctx,envelope)
            assert native==reference
            assert region_statistics(native,ops,index,CFG["regions"]["decision_aware"]["network_radius_m"])==region_statistics(reference,ops,pairs,CFG["regions"]["decision_aware"]["network_radius_m"])
