"""Separate exact budget and frozen-region filter timings on persisted plans."""
import json
import resource
import time
import numpy as np
import pandas as pd
from _common import ROOT,read_config,sha256
from _microplan_common import identity_keys


def main():
    cfg=read_config('configs/microplan.yaml');root=ROOT/cfg['results_dir'];old=ROOT/cfg['frozen_region_dir']
    catalogue=pd.read_parquet(root/'opportunity_index.parquet')
    lookup=pd.Index(identity_keys(catalogue.osm_type,catalogue.osm_id))
    counts=pd.read_parquet(root/'candidate_counts.parquet')
    counts=counts[(counts.method=='decision')&(counts.access_scenario=='all_attached')&(counts.dwell_scenario=='without_dwell')]
    env=read_config(cfg['envelope_config']);tol=env['numerical_tolerance'];rows=[]
    for instance in range(30):
        membership=pd.read_parquet(old/'region_membership.parquet',filters=[('instance_id','==',instance),('method','==','decision-aware')])
        for task in cfg['tasks']:
            plans=pd.read_parquet(root/'microplans_flat'/f'od_{instance:02d}_{task}.parquet',columns=['first_index','second_index','total_route_time_s'])
            for ratio in env['detour_ratios']:
                part=counts[(counts.instance_id==instance)&(counts.task==task)&(counts.ratio==ratio)].iloc[0]
                start=time.perf_counter();valid=plans.total_route_time_s.to_numpy()<=part.budget_s+tol['absolute']+tol['relative']*part.budget_s
                first=plans.first_index.to_numpy()[valid];second=plans.second_index.to_numpy()[valid]
                seconds=time.perf_counter()-start
                rows.append({'stage':'exact_budget_feasibility_filter','seconds':seconds,'instance_id':instance,'ratio':float(ratio),
                    'task':task,'access_scenario':'all_attached','dwell_scenario':'without_dwell','count':len(first),
                    'peak_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024})
                m=membership[membership.ratio==ratio]
                ids=lookup.get_indexer(identity_keys(m.osm_type,m.osm_id));labels=np.full(len(catalogue),-1,dtype=np.int64)
                labels[ids]=pd.factorize(m.region_id,sort=True)[0]
                start=time.perf_counter();region=(second<0)|(labels[first]==labels[np.maximum(second,0)])
                exact=int(region.sum());seconds=time.perf_counter()-start
                assert exact==part.candidate_count
                rows.append({'stage':'region_candidate_filter','seconds':seconds,'instance_id':instance,'ratio':float(ratio),
                    'task':task,'access_scenario':'all_attached','dwell_scenario':'without_dwell','count':exact,
                    'peak_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024})
    pd.DataFrame(rows).to_parquet(root/'filter_performance.parquet',index=False)
    stats=pd.read_parquet(root/'region_gateway_stats.parquet')
    native=stats.groupby(['instance_id','ratio'])[['local_build_seconds','interface_seconds']].sum().reset_index()
    native.to_parquet(root/'gateway_stage_performance.parquet',index=False)
    benchmark=json.loads((root/'benchmark.json').read_text());benchmark['analysis_files'].update({
        p.name:sha256(p) for p in [root/'filter_performance.parquet',root/'gateway_stage_performance.parquet']})
    (root/'benchmark.json').write_text(json.dumps(benchmark,indent=2)+'\n')
    print(pd.DataFrame(rows).groupby('stage').seconds.agg(['median',lambda s:s.quantile(.95)]).to_string())

if __name__=='__main__':main()
