"""Exact capability/spatial/distance upper counts before time/budget evaluation."""
import json
import time
import numpy as np
import pandas as pd
from _common import ROOT,read_config,sha256
from _microplan_common import read_opportunities,candidate_pairs,identity_keys
from microplan.generation import CAPABILITY_BITS


def main():
    cfg=read_config('configs/microplan.yaml');result=ROOT/cfg['results_dir'];result.mkdir(exist_ok=True)
    t=time.perf_counter();table,o,lookup=read_opportunities(cfg);a,b,geo,df,dr=candidate_pairs(cfg,o,lookup)
    features=pd.read_parquet(ROOT/cfg['frozen_region_dir']/'od_features.parquet',columns=['instance_id','osm_type','osm_id','through_cost_s'])
    od=pd.read_parquet(ROOT/'results/milestone_3a/od_remapping.parquet')
    ratios=read_config(cfg['envelope_config'])['detour_ratios'];rows=[]
    for row in od.itertuples():
        feat=features[features.instance_id==row.instance_id]
        idx=lookup.get_indexer(identity_keys(feat.osm_type,feat.osm_id));assert(idx>=0).all()
        h=np.full(len(o.identities),np.inf);h[idx]=feat.through_cost_s
        for ratio in ratios:
            budget=ratio*row.ext_baseline_time_s;eligible=h<=budget+1e-8+budget*1e-10
            for name,task in cfg['tasks'].items():
                req=sum(CAPABILITY_BITS[c] for c in task['required_capabilities'])
                singles=int(np.sum(eligible&((o.capability_masks&req)==req)))
                pairs=0
                if len(task['required_capabilities'])==2:
                    caps=o.capability_masks
                    valid=eligible[a]&eligible[b]&(((caps[a]|caps[b])&req)==req)&((caps[a]&req)!=0)&((caps[b]&req)!=0)
                    pairs=int(np.sum(valid&(df<=cfg['bundles']['directed_shortest_distance_cutoff_m'])))
                    pairs+=int(np.sum(valid&(dr<=cfg['bundles']['directed_shortest_distance_cutoff_m'])))
                rows.append({'instance_id':row.instance_id,'ratio':ratio,'task':name,'single_count':singles,
                             'ordered_pair_upper_count':pairs,'candidate_upper_count':singles+pairs})
    pd.DataFrame(rows).to_parquet(result/'candidate_estimates.parquet',index=False)
    record={'seconds':time.perf_counter()-t,'attached_objects':len(table),'low_access_risk_objects':int((o.risk==0).sum()),
            'sparse_compound_pairs':len(a),'sum_od_task_max_budget_upper':int(pd.DataFrame(rows).query('ratio==2').candidate_upper_count.sum()),
            'largest_od_task_budget_upper':int(pd.DataFrame(rows).candidate_upper_count.max()),
            'scope':'Complete explicit local-task upper counts; no region restriction, no time-cost pruning yet.'}
    (result/'candidate_estimates.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record,indent=2))

if __name__=='__main__':main()
