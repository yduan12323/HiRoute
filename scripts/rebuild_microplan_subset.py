"""Reconstruct any region/Pareto/cover subset from stored flat plan partitions.

This sufficient representation avoids duplicating millions of plans per budget.
Optional verification checks all candidate counts and exact selected decisions
for configured diagnostic cases; no road graph or previous output is modified.
"""
import argparse
import json
import time
import numpy as np
import pandas as pd
from _common import ROOT,read_config
from _microplan_common import identity_keys
from microplan.models import PlanBatch
from microplan.compression import load_grouped_pareto,grouped_epsilon_cover,random_representatives
from microplan.evaluation import normalize_objectives,utility_family
from run_microplan_benchmark import stable_seed


def load_case(cfg,instance,ratio,task,access,dwell,kernel=None):
    root=ROOT/cfg['results_dir'];old=ROOT/cfg['frozen_region_dir']
    catalogue=pd.read_parquet(root/'opportunity_index.parquet')
    raw=pd.read_parquet(root/'microplans_flat'/f'od_{instance:02d}_{task}.parquet')
    od=pd.read_parquet(ROOT/'results/milestone_3a/od_remapping.parquet')
    baseline=float(od.loc[od.instance_id==instance,'ext_baseline_time_s'].iloc[0]);budget=baseline*ratio
    env=read_config(cfg['envelope_config']);tol=env['numerical_tolerance'];threshold=budget+tol['absolute']+tol['relative']*budget
    raw=raw[raw.total_route_time_s<=threshold]
    if access=='conservative':raw=raw[raw.access_penalty==0]
    z=raw[['detour_time_s','detour_distance_m','stop_count']].to_numpy(float)
    duration=np.zeros(len(raw));concurrency=raw.concurrency_code.to_numpy()
    if dwell=='structural_concurrency':
        values=[cfg['activity_duration_s'][c] for c in cfg['tasks'][task]['required_capabilities']]
        duration[:]=sum(values);duration[concurrency>0]=max(values)
    z=np.column_stack([z,duration,raw.access_penalty.to_numpy(float)])
    plans=PlanBatch(raw.first_index.to_numpy(np.int64),raw.second_index.to_numpy(np.int64),
                   raw.total_route_time_s.to_numpy(),raw.total_route_distance_m.to_numpy(),z,concurrency)
    normalized=normalize_objectives(z,cfg['normalization_scales'])
    membership=pd.read_parquet(old/'region_membership.parquet',filters=[('instance_id','==',instance),('ratio','==',ratio)])
    lookup=pd.Index(identity_keys(catalogue.osm_type,catalogue.osm_id));labels={}
    for method in ['geographic baseline','decision-aware']:
        part=membership[membership.method==method]
        ids=lookup.get_indexer(identity_keys(part.osm_type,part.osm_id));assert(ids>=0).all()
        label=np.full(len(catalogue),-1,dtype=np.int64);label[ids]=pd.factorize(part.region_id,sort=True)[0];labels[method]=label
    if kernel is None:kernel=load_grouped_pareto(cfg,ROOT/cfg['cache_dir'])
    groups=labels['decision-aware'][plans.first]
    geo=np.flatnonzero(plans.region_mask(labels['geographic baseline']))
    region=np.flatnonzero(plans.region_mask(labels['decision-aware']))
    pareto=region[kernel(normalized[region],groups[region])]
    subsets={'flat':np.arange(len(plans)),'geographic':geo,'decision':region,'exact_pareto':pareto}
    for name,eps in cfg['epsilon_covers'].items():
        kept,witness=grouped_epsilon_cover(normalized[pareto],groups[pareto],eps)
        cover=pareto[kept];subsets['epsilon_'+name]=cover
        random=[]
        order=region[np.argsort(groups[region],kind='stable')];rg=groups[order]
        unique,counts=np.unique(groups[cover],return_counts=True)
        for group,count in zip(unique,counts):
            candidates=order[np.searchsorted(rg,group,'left'):np.searchsorted(rg,group,'right')]
            chosen=random_representatives(len(candidates),int(count),stable_seed(cfg['seed'],instance,ratio,task,access,dwell,name,int(group)))
            random.extend(candidates[chosen])
        subsets['random_'+name]=np.array(sorted(random),dtype=np.int64)
    return plans,normalized,subsets


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--od',type=int,default=14);parser.add_argument('--ratio',type=float,default=1.05)
    parser.add_argument('--task',default='charge_meal');parser.add_argument('--method',default='epsilon_medium')
    parser.add_argument('--access',default='all_attached');parser.add_argument('--dwell',default='without_dwell')
    parser.add_argument('--output',help='Optional reconstructed compact candidate table')
    parser.add_argument('--verify',action='store_true')
    args=parser.parse_args();cfg=read_config('configs/microplan.yaml');root=ROOT/cfg['results_dir']
    start=time.perf_counter();kernel=load_grouped_pareto(cfg,ROOT/cfg['cache_dir'])
    if args.verify:
        counts=pd.read_parquet(root/'candidate_counts.parquet')
        regret=pd.read_parquet(root/'abstraction_regret.parquet')
        names,weights=utility_family(cfg['evaluation'],cfg['seed']);checked=0
        for od in [0,7,14,16,29]:
            for ratio in [1.05,1.4,2.0]:
                for task in ['charge_meal','sleep_charge','meal_parking']:
                    plans,z,sets=load_case(cfg,od,ratio,task,'all_attached','without_dwell',kernel)
                    context=(counts.instance_id==od)&(counts.ratio==ratio)&(counts.task==task)&(counts.access_scenario=='all_attached')&(counts.dwell_scenario=='without_dwell')
                    expected=counts[context].set_index('method').candidate_count.to_dict()
                    assert {m:len(ids) for m,ids in sets.items()}==expected
                    for method,ids in sets.items():
                        actual=np.min(z[ids]@weights.T,axis=0) if len(ids) else np.full(len(names),np.inf)
                        rows=regret[(regret.instance_id==od)&(regret.ratio==ratio)&(regret.task==task)&
                            (regret.access_scenario=='all_attached')&(regret.dwell_scenario=='without_dwell')&(regret.method==method)].set_index('theta_id')
                        assert np.allclose(actual,rows.loc[names,'selected_cost'].to_numpy(),atol=1e-10)
                        checked+=len(names)
        record={'passed':True,'contexts':45,'method_utility_evaluations':checked,'seconds':time.perf_counter()-start,
                'scope':'Independent subsets regenerated from stored flat partitions, including worst/early unstable ODs; complete count and all sixteen utility checks in these contexts.'}
        (root/'subset_reproducibility.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record,indent=2));return
    plans,z,sets=load_case(cfg,args.od,args.ratio,args.task,args.access,args.dwell,kernel);ids=sets[args.method]
    print(json.dumps({'flat':len(plans),'retained':len(ids),'method':args.method}))
    if args.output:
        table=pd.DataFrame({'first_index':plans.first[ids],'second_index':plans.second[ids],
                            'total_route_time_s':plans.total_time_s[ids],'total_route_distance_m':plans.total_distance_m[ids],
                            **{name:plans.objectives[ids,j] for j,name in enumerate(cfg['pareto_dimensions'])}})
        table.to_parquet(ROOT/args.output,index=False)

if __name__=='__main__':main()
