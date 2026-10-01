"""Sequential 30-OD × seven-budget Milestone 4A experiment, with prior data read-only."""
from __future__ import annotations
import argparse
from dataclasses import replace
import json
from pathlib import Path
import resource
import time
from collections import Counter
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pyproj import Transformer
import yaml
from _common import ROOT, configs, read_config, sha256, load_graph, record_run
from envelope import NumericalTolerance, precompute_detour_distances, build_envelope_from_precomputed
from opportunity import (Opportunity, OpportunityId, Provenance, ODContext, decision_features,
                         eligible_opportunities, attach_opportunities, GeographicRegionBuilder, DecisionRegionBuilder)
from opportunity.regions import NeighborPair, fingerprint
from opportunity.metrics import region_statistics, expansion_stability
from opportunity.network import validate_network_pairs
from opportunity.sparse import NeighborIndex,load_union_kernel


class TableStream:
    def __init__(self,path):self.path=path;self.writer=None
    def append(self,rows):
        if not rows:return
        table=pa.Table.from_pylist(rows)
        for key in ['local_network_valid_fraction']:
            if key in table.column_names and pa.types.is_null(table.schema.field(key).type):
                index = table.column_names.index(key)
                table = table.set_column(index, key, table[key].cast(pa.float64()))
        if self.writer is None:self.writer=pq.ParquetWriter(self.path,table.schema,compression='zstd')
        self.writer.write_table(table.cast(self.writer.schema))
    def close(self):
        if self.writer:self.writer.close()


def inventory_objects(table):
    return [Opportunity(OpportunityId(r.osm_type,int(r.osm_id)),float(r.lat),float(r.lon),
        frozenset(r.capabilities),r.subtype,json.loads(r.original_tags),
        Provenance(tuple(r.source_datasets),r.snapshot_timestamp,r.geometry_method)) for r in table.itertuples()]


def quality_audit(opportunities, xy, config, manifest, result):
    counts=Counter(c for o in opportunities for c in o.capabilities)
    snap=np.array([o.access_distance_m if o.access_distance_m is not None else np.inf for o in opportunities])
    attached=sum(o.attachment_status=='attached' for o in opportunities)
    thresholds=[{'threshold_m':t,'attached':int((snap<=t).sum()),'rejected':int((snap>t).sum()),
                 'attached_fraction':float(np.mean(snap<=t))} for t in config['attachment']['diagnostic_thresholds_m']]
    pd.DataFrame(thresholds).to_parquet(result/'attachment_sensitivity.parquet',index=False)
    cells=np.floor(xy/config['diagnostics']['density_grid_m']).astype(int)
    unique,counts_cell=np.unique(cells,axis=0,return_counts=True)
    pd.DataFrame({'x_cell':unique[:,0],'y_cell':unique[:,1],'opportunity_count':counts_cell}).to_parquet(result/'opportunity_density.parquet',index=False)
    sources=Counter(s for o in opportunities for s in o.provenance.source_datasets)
    audit={'total_opportunities':len(opportunities),'capability_counts':dict(sorted(counts.items())),
           'object_type_counts':dict(Counter(o.identity.osm_type for o in opportunities)),
           'missing_name_rate':sum(not o.original_tags.get('name') for o in opportunities)/len(opportunities),
           'attached_count':attached,'rejected_count':len(opportunities)-attached,
           'attachment_status_counts':dict(Counter(o.attachment_status for o in opportunities)),
           'snap_quantiles_m':{str(q):float(np.quantile(snap,q)) for q in [0,.25,.5,.75,.9,.95,.99,1]},
           'threshold_sensitivity':thresholds,'source_membership_counts':dict(sources),
           'country_explicit_tag_counts':dict(Counter(o.original_tags.get('addr:country','unknown') for o in opportunities)),
           'occupied_density_cells':len(unique),'density_cell_area_km2':(config['diagnostics']['density_grid_m']/1000)**2,
           'density_cell_count_quantiles':{str(q):float(np.quantile(counts_cell,q)) for q in [.5,.95,1]},
           'deduplication':{k:manifest[k] for k in ['raw_candidate_count','duplicate_count','unique_candidate_count',
                                               'final_located_in_polygon_count','exclusion_reasons']},
           'selected_threshold_m':config['attachment']['default_threshold_m'],
           'attachment_policy':config['attachment'],
           'interpretation':'Source memberships overlap and are not nationality. Node snapping approximates road access, not entrances.'}
    (result/'quality_audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    print(json.dumps(audit,indent=2),flush=True)
    return audit


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',default='configs/opportunity.yaml')
    args=parser.parse_args(); config=read_config(args.config)
    result=ROOT/config['results_dir'];result.mkdir(parents=True,exist_ok=True)
    raw=ROOT/config['raw_dir'];manifest=yaml.safe_load((raw/'MANIFEST.yaml').read_text())
    for name,digest in manifest['files'].items():
        if sha256(raw/name)!=digest:raise ValueError('Frozen opportunity fingerprint mismatch')
    if manifest['extraction_config_fingerprint']!=fingerprint(config['extraction']):raise ValueError('Taxonomy configuration mismatch')
    data,routing=configs(config['graph_data_config']);data={**data,'results_dir':config['results_dir']}
    run=record_run('milestone_4a',data,routing,config['seed']);run['opportunity_configuration']=config
    env=read_config(config['envelope_config']); tolerance=NumericalTolerance(**env['numerical_tolerance'])
    start=time.perf_counter();graph=load_graph(data,routing);load_seconds=time.perf_counter()-start
    inventory=pd.read_parquet(raw/'inventory.parquet');opportunities=inventory_objects(inventory)
    inventory.to_parquet(result/'opportunity_inventory.parquet',index=False)
    start=time.perf_counter()
    road_classes=pd.read_parquet(ROOT/data['graph_dir']/'edges.parquet',columns=['highway']).highway.to_numpy()
    opportunities=attach_opportunities(opportunities,graph,road_classes,config['attachment']);del road_classes
    attachment_seconds=time.perf_counter()-start
    attachments=pd.DataFrame([{'osm_type':o.identity.osm_type,'osm_id':o.identity.osm_id,
        'access_node':o.access_node,'access_osm_node_id':o.access_osm_node_id,'access_distance_m':o.access_distance_m,
        'attachment_status':o.attachment_status} for o in opportunities])
    attachments.to_parquet(result/'opportunity_attachment.parquet',index=False)
    transform=Transformer.from_crs(4326,3035,always_xy=True)
    xy=np.column_stack(transform.transform([o.lon for o in opportunities],[o.lat for o in opportunities]))
    audit=quality_audit(opportunities,xy,config,manifest,result) # Written BEFORE any clustering.
    attached=[o for o in opportunities if o.attachment_status=='attached']
    attached_xy=xy[[o.attachment_status=='attached' for o in opportunities]]
    network_file=result/'local_neighbor_pairs.parquet'; network_meta=result/'network_benchmark.json'
    contract=fingerprint({'graph':json.loads((ROOT/data['graph_dir']/'metadata.json').read_text())['files'],
                          'inventory':manifest['files'],'attachment':config['attachment'],'network':config['network']})
    if network_file.exists() and network_meta.exists():
        meta=json.loads(network_meta.read_text())
        if meta['contract']!=contract or meta['pair_file_sha256']!=sha256(network_file) or meta['native_source_sha256']!=sha256(ROOT/'src/opportunity/local_network.cpp'):raise ValueError('Cached neighbor provenance mismatch')
        table=pd.read_parquet(network_file)
        pairs = NeighborIndex.from_table(table,attached)
        del table
        print('Reused verified sparse local road-distance cache',flush=True)
    else:
        pairs,directed,indices,meta=validate_network_pairs(graph,attached,attached_xy,config['network'],ROOT/config['cache_dir']/'network')
        osm_types=np.array([o.identity.osm_type for o in attached],dtype=object)
        osm_ids=np.array([o.identity.osm_id for o in attached],dtype=np.int64)
        table=pd.DataFrame({'first_type':osm_types[indices[:,0]],'first_id':osm_ids[indices[:,0]],
            'second_type':osm_types[indices[:,1]],'second_id':osm_ids[indices[:,1]],
            'geographic_m':pairs.geographic_m,'network_m':pairs.network_m,
            'forward_m':directed[:,0],'reverse_m':directed[:,1]})
        table.to_parquet(network_file,index=False)
        meta.update({'contract':contract,'pair_file_sha256':sha256(network_file)})
        network_meta.write_text(json.dumps(meta,indent=2)+'\n')
        pairs=NeighborIndex.from_table(table,attached)
        del table,directed,indices
    if not isinstance(pairs,NeighborIndex):
        pairs=NeighborIndex.from_table(pd.read_parquet(network_file),attached)
    print('Local neighbor pairs:',len(pairs),flush=True)
    performance=[{'stage':'graph_load','seconds':load_seconds,'instance_id':-1,'ratio':0.,'method':''},
                 {'stage':'graph_attachment','seconds':attachment_seconds,'instance_id':-1,'ratio':0.,'method':''},
                 {'stage':'snapshot_extraction','seconds':manifest['extraction_seconds'],'instance_id':-1,'ratio':0.,'method':''},
                 {'stage':'snapshot_parsing','seconds':manifest['parsing_seconds'],'instance_id':-1,'ratio':0.,'method':''},
                 {'stage':'global_spatial_neighbors','seconds':meta['spatial_seconds'],'instance_id':-1,'ratio':0.,'method':''},
                 {'stage':'bounded_network_validation','seconds':meta['network_seconds'],'instance_id':-1,'ratio':0.,'method':''}]
    od=pd.read_parquet(ROOT/data['instances_path']);boundary=pd.read_parquet(ROOT/'results/milestone_3a/envelope_stats.parquet')
    streams={name:TableStream(result/(name+'.parquet')) for name in ['region_membership','regions','od_features']}
    summaries=[];sensitivity=[];stability=[]
    union_kernel = load_union_kernel(config['network'],ROOT/config['cache_dir']/'network')
    experiment_started=time.perf_counter()
    for row in od.itertuples():
        oid=int(row.instance_id)
        start=time.perf_counter();distances=precompute_detour_distances(graph,int(row.origin_node),int(row.destination_node),env['cost'])
        performance.append({'stage':'distance_precomputation','seconds':time.perf_counter()-start,'instance_id':oid,'ratio':0.,'method':''})
        if not np.isclose(distances.baseline_cost,row.ext_baseline_time_s,rtol=1e-12):raise ValueError('Frozen OD baseline changed')
        context=ODContext(oid,distances)
        start=time.perf_counter();features=decision_features(attached,distances,attached_xy)
        performance.append({'stage':'od_features','seconds':time.perf_counter()-start,'instance_id':oid,'ratio':0.,'method':''})
        maximum=eligible_opportunities(features,env['max_ratio']*distances.baseline_cost,tolerance)
        streams['od_features'].append([{'instance_id':oid,'osm_type':o.identity.osm_type,'osm_id':o.identity.osm_id,
            'through_cost_s':o.through_cost,'detour_cost_s':o.detour_cost,'detour_ratio':o.detour_ratio,
            'progress':o.progress,'access_node':o.opportunity.access_node,'x_m':o.x_m,'y_m':o.y_m} for o in maximum])
        start=time.perf_counter();max_ids={o.identity for o in maximum}
        od_pairs=pairs.select(maximum) if isinstance(pairs,NeighborIndex) else [p for p in pairs if p.first in max_ids and p.second in max_ids]
        performance.append({'stage':'od_sparse_neighbors','seconds':time.perf_counter()-start,'instance_id':oid,'ratio':0.,'method':''})
        previous={}
        for ratio in env['detour_ratios']:
            budget=float(ratio)*distances.baseline_cost
            envelope=build_envelope_from_precomputed(distances,budget,tolerance)
            eligible=eligible_opportunities(maximum,budget,tolerance)
            risk=bool(boundary.loc[(boundary.instance_id==oid)&(boundary.ratio==ratio),'boundary_risk'].iloc[0])
            base={'instance_id':oid,'ratio':float(ratio),'budget_s':budget,'baseline_cost_s':distances.baseline_cost,
                  'boundary_risk':risk,'opportunity_snapshot_sha256':manifest['files']['inventory.parquet'],
                  'graph_fingerprint':fingerprint(json.loads((ROOT/data['graph_dir']/'metadata.json').read_text())['files'])}
            eligible_ids = {o.identity for o in eligible}
            budget_pairs = od_pairs.select(eligible) if isinstance(od_pairs,NeighborIndex) else [p for p in od_pairs if p.first in eligible_ids and p.second in eligible_ids]
            for builder in [GeographicRegionBuilder(config['regions']['geographic_baseline'],budget_pairs),
                            DecisionRegionBuilder(config['regions']['decision_aware'],budget_pairs,union_kernel)]:
                start=time.perf_counter();regions=builder.build_regions(eligible,context,envelope)
                duration=time.perf_counter()-start
                performance.append({'stage':'region_clustering','seconds':duration,'instance_id':oid,'ratio':float(ratio),'method':builder.method})
                region_rows,summary=region_statistics(regions,eligible,budget_pairs,config['regions']['decision_aware']['network_radius_m'])
                summaries.append({**base,'method':builder.method,**summary})
                streams['regions'].append([{**base,**r} for r in region_rows])
                streams['region_membership'].append([{**base,'method':builder.method,'region_id':r.region_id,
                    'osm_type':i.osm_type,'osm_id':i.osm_id,'config_fingerprint':r.config_fingerprint} for r in regions for i in r.member_ids])
                if builder.method in previous:
                    prior_ratio,prior_regions=previous[builder.method]
                    stability.append({**base,'method':builder.method,'previous_ratio':prior_ratio,
                                      **expansion_stability(prior_regions,regions)})
                previous[builder.method]=(float(ratio),regions)
            print(f'OD {oid:02d} ratio {ratio:.2f}: {len(eligible)} opportunities',flush=True)
            if ratio in config['regions']['sensitivity_ratios']:
                for variation in [{'name':'default'},*config['regions']['sensitivity']]:
                    cfg={**config['regions']['decision_aware'],**{k:v for k,v in variation.items() if k!='name'}}
                    start=time.perf_counter();regions=DecisionRegionBuilder(cfg,budget_pairs,union_kernel).build_regions(eligible,context,envelope)
                    elapsed=time.perf_counter()-start
                    _,summary=region_statistics(regions,eligible,budget_pairs,cfg['network_radius_m'])
                    sensitivity.append({**base,'configuration':variation['name'],'config_fingerprint':fingerprint(cfg),
                                        **cfg,**summary,'clustering_seconds':elapsed})
            del envelope
        print(f'OD {oid:02d}: {len(maximum)} eligible at 2.00; processed all seven budgets',flush=True)
        del distances,context,features,maximum,od_pairs,previous
    for stream in streams.values():stream.close()
    stats=pd.DataFrame(summaries);stats.to_parquet(result/'region_stats.parquet',index=False)
    geo=stats[stats.method=='geographic baseline'].drop(columns='method');decision=stats[stats.method=='decision-aware'].drop(columns='method')
    comparison=geo.merge(decision,on=['instance_id','ratio'],suffixes=('_geographic','_decision'))
    comparison.to_parquet(result/'region_method_comparison.parquet',index=False)
    pd.DataFrame(stability).to_parquet(result/'expansion_stability.parquet',index=False)
    pd.DataFrame(sensitivity).to_parquet(result/'parameter_sensitivity.parquet',index=False)
    perf=pd.DataFrame(performance);perf.to_parquet(result/'performance.parquet',index=False)
    benchmark={'run':run,'configuration':config,'quality_audit':audit,'network':meta,
        'region_kernel':{'source_sha256':sha256(ROOT/'src/opportunity/region_union.cpp'),'compiler':config['network']['compiler'],'flags':config['network']['compiler_flags'],'parity_reference':'tests/test_opportunity.py::test_compact_sparse_and_native_kernel_match_python_reference'},
        'od_count':len(od),'ratio_count':len(env['detour_ratios']),'method_count':2,
        'region_experiment_seconds':time.perf_counter()-experiment_started,
        'process_peak_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
        'practical_budget_summary':stats[stats.ratio.isin(config['regions']['sensitivity_ratios'])].groupby(['ratio','method']).median(numeric_only=True).reset_index().to_dict('records'),
        'stage_summary':perf.groupby(['stage','method']).seconds.agg(['count','median',lambda x:x.quantile(.95)]).reset_index().rename(columns={'<lambda_0>':'p95'}).to_dict('records'),
        'result_files':{p.name:sha256(p) for p in sorted(result.glob('*.parquet'))}}
    (result/'benchmark.json').write_text(json.dumps(benchmark,indent=2)+'\n')
    print('Completed 30 ODs × 7 budgets × 2 methods',flush=True)

if __name__=='__main__':main()
