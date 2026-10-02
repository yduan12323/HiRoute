"""Sequential frozen-region structural Go-1 experiment. Writes only Milestone 4B."""
from __future__ import annotations
import argparse
import hashlib
import json
import resource
import time
from collections import Counter
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from _common import ROOT,configs,read_config,sha256,load_graph,record_run
from _microplan_common import read_opportunities,prepare_pairs,identity_keys,TableWriter
from opportunity.regions import fingerprint
from envelope import NumericalTolerance,precompute_detour_distances
from microplan.models import Task,LocalPairs,PlanBatch
from microplan.routing import ExactRouter
from microplan.generation import generate_plans
from microplan.compression import (load_grouped_pareto,grouped_epsilon_cover,random_representatives)
from microplan.evaluation import normalize_objectives,utility_family


def stable_seed(seed, *parts):
    return int(hashlib.sha256(json.dumps([seed,*parts],sort_keys=True).encode()).hexdigest()[:16],16)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',default='configs/microplan.yaml')
    parser.add_argument('--prepare-only',action='store_true')
    parser.add_argument('--od',type=int,nargs='*',help='Diagnostic subset; complete acceptance requires all 30')
    args=parser.parse_args();cfg=read_config(args.config);result=ROOT/cfg['results_dir'];result.mkdir(parents=True,exist_ok=True)
    cache=ROOT/cfg['cache_dir'];cache.mkdir(parents=True,exist_ok=True)
    if cfg['pareto_dimensions']!=['detour_time_s','detour_distance_m','stop_count','dwell_time_s','access_penalty']:
        raise ValueError('This native kernel implements the documented five dimensions in fixed order')
    if cfg['gateways']['deduplication']!='identical_inside_boundary_node' or cfg['access']['risk_penalty']!={'low_access_risk':0,'uncertain_access':1}:
        raise ValueError('Unsupported gateway deduplication/access ordinal contract')
    data,routing=configs(cfg['graph_data_config']);data=dict(data,results_dir=cfg['results_dir'])
    run=record_run('microplan-benchmark',data,routing,cfg['seed']);run['microplan_configuration']=cfg
    old=ROOT/cfg['frozen_region_dir'];envcfg=read_config(cfg['envelope_config'])
    tol=NumericalTolerance(**envcfg['numerical_tolerance']);perf=[]
    def measured(stage,start,od=-1,ratio=0.,task='',access='',dwell='',count=0):
        perf.append({'stage':stage,'seconds':time.perf_counter()-start,'instance_id':od,'ratio':float(ratio),
                     'task':task,'access_scenario':access,'dwell_scenario':dwell,'count':int(count),
                     'peak_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024})
    start=time.perf_counter();graph=load_graph(data,routing);measured('graph_load',start)
    start=time.perf_counter();router=ExactRouter(graph,cfg,cache);kernel=load_grouped_pareto(cfg,cache);measured('native_index_build',start)
    start=time.perf_counter();inventory,opportunities,lookup=read_opportunities(cfg)
    inventory.to_parquet(result/'opportunity_index.parquet',index=False);measured('opportunity_parse',start)
    pairs,pairmeta=prepare_pairs(cfg,router,opportunities,lookup,result)
    if args.prepare_only:
        print(json.dumps(pairmeta,indent=2));router.close();return
    names,weights=utility_family(cfg['evaluation'],cfg['seed'])
    pd.DataFrame({'theta_id':names,**{name:weights[:,j] for j,name in enumerate(cfg['pareto_dimensions'])}}).to_parquet(result/'utility_weights.parquet',index=False)
    instances=pd.read_parquet(ROOT/data['instances_path'])
    if args.od is not None:instances=instances[instances.instance_id.isin(args.od)]
    boundary=pd.read_parquet(ROOT/'results/milestone_3a/envelope_stats.parquet',columns=['instance_id','ratio','boundary_risk'])
    graph_fp=fingerprint(json.loads((ROOT/data['graph_dir']/'metadata.json').read_text())['files'])
    feasibility_fp=fingerprint({'config':cfg,'graph':graph_fp,'local_costs_sha256':pairmeta['sha256'],
        'inventory_sha256':sha256(old/'opportunity_inventory.parquet'),'region_membership_sha256':sha256(old/'region_membership.parquet')})
    outputs=['gateways','region_gateway_stats','gateway_bindings','candidate_counts','pareto_stats','epsilon_cover_stats',
             'abstraction_regret','topk_regret','epsilon_optimal_coverage','failure_analysis','gateway_expansion_stability','gateway_microplan_usage']
    writers={name:TableWriter(result/(name+'.parquet')) for name in outputs}
    flat_dir=result/'microplans_flat';flat_dir.mkdir(exist_ok=True)
    total_start=time.perf_counter();max_bound_excess=0.;saved_files={};empty_flat=empty_region=0
    for od in instances.itertuples():
        odstart=time.perf_counter();instance=int(od.instance_id)
        start=time.perf_counter();dist=precompute_detour_distances(graph,int(od.origin_node),int(od.destination_node),'travel_time')
        measured('envelope_precomputation',start,instance)
        start=time.perf_counter();native_ds,pl,parents=router.full(int(od.origin_node))
        native_dd,sl,next_nodes=router.full(int(od.destination_node),True)
        if not np.allclose(native_ds,dist.forward_distances,atol=1e-7,rtol=1e-12) or not np.allclose(native_dd,dist.reverse_distances,atol=1e-7,rtol=1e-12):
            raise ValueError('Native fastest paths differ from frozen envelope cost contract')
        measured('exact_fastest_path_lengths',start,instance)
        del native_ds,native_dd
        baseline=dist.baseline_cost;baseline_length=float(pl[int(od.destination_node)])
        maxbudget=max(envcfg['detour_ratios'])*baseline
        h=dist.node_lower_bounds[opportunities.access_nodes]
        localmask=(h[pairs.first]<=maxbudget+tol.allowance(maxbudget))&(h[pairs.second]<=maxbudget+tol.allowance(maxbudget))
        localpairs=LocalPairs(*(getattr(pairs,name)[localmask] for name in pairs.__dataclass_fields__))
        membership=pd.read_parquet(old/'region_membership.parquet',filters=[('instance_id','==',instance)])
        regions=pd.read_parquet(old/'regions.parquet',filters=[('instance_id','==',instance),('construction_method','==','decision-aware')],columns=['ratio','region_id','access_nodes'])
        maxplans={}
        for taskname,taskcfg in cfg['tasks'].items():
            task=Task(taskname,frozenset(taskcfg['required_capabilities']),taskcfg['primary'])
            start=time.perf_counter()
            plans=generate_plans(opportunities,localpairs,task,dist.forward_distances,dist.reverse_distances,
                                 pl,sl,baseline,baseline_length,maxbudget,cfg,tolerance=tol)
            measured('flat_generation_and_exact_feasibility',start,instance,2.,taskname,count=len(plans))
            maxplans[taskname]=plans
            # Save each unique plan once at max budget; smaller budgets are exact
            # total-time filters, region partitions remain the frozen 4A table.
            frame=pd.DataFrame({'first_index':plans.first,'second_index':plans.second,
                'total_route_time_s':plans.total_time_s,'total_route_distance_m':plans.total_distance_m,
                'detour_time_s':plans.objectives[:,0],'detour_distance_m':plans.objectives[:,1],
                'stop_count':plans.objectives[:,2].astype(np.int8),'access_penalty':plans.objectives[:,4].astype(np.int8),
                'concurrency_code':plans.concurrency})
            path=flat_dir/f'od_{instance:02d}_{taskname}.parquet';frame.to_parquet(path,index=False,compression='zstd')
            saved_files[str(path.relative_to(result))]={'sha256':sha256(path),'row_count':len(plans),'feasibility_fingerprint':feasibility_fp}
        previous_gateway_sets={}
        for ratio in envcfg['detour_ratios']:
            budget=ratio*baseline;threshold=budget+tol.allowance(budget)
            base={'instance_id':instance,'ratio':float(ratio),'budget_s':float(budget),'baseline_time_s':float(baseline),
                  'boundary_risk':bool(boundary.query('instance_id==@instance and ratio==@ratio').boundary_risk.iloc[0]),
                  'feasibility_fingerprint':feasibility_fp}
            start=time.perf_counter();labels={};region_ids={}
            for method in ['geographic baseline','decision-aware']:
                part=membership[(membership.ratio==ratio)&(membership.method==method)]
                keys=lookup.get_indexer(identity_keys(part.osm_type,part.osm_id));assert(keys>=0).all()
                values,unique=pd.factorize(part.region_id,sort=True)
                label=np.full(len(opportunities.identities),-1,dtype=np.int64);label[keys]=values
                labels[method]=label;region_ids[method]=list(unique)
            measured('region_restriction_index',start,instance,ratio)
            # Gateway member bindings indexed by opportunity, using canonical
            # fastest origin prefix / destination suffix. All alternative feasible
            # interfaces are retained in gateways.parquet; no gateway pruning.
            ingress=np.full(len(opportunities.identities),-1,dtype=np.int64)
            egress=ingress.copy();gateway_rows=[];gateway_stats=[];binding_rows=[];gateway_sets={}
            selected_regions=regions[regions.ratio==ratio]
            region_index={r:i for i,r in enumerate(region_ids['decision-aware'])}
            member_order=np.argsort(labels['decision-aware'],kind='stable')
            member_groups=labels['decision-aware'][member_order]
            member_slices={int(group):(int(np.searchsorted(member_groups,group,'left')),int(np.searchsorted(member_groups,group,'right'))) for group in np.unique(member_groups) if group>=0}
            start=time.perf_counter()
            for region in selected_regions.itertuples():
                nodes=np.asarray(region.access_nodes,dtype=np.int64)
                gt=router.gateways(nodes,dist.forward_distances,dist.reverse_distances,parents,next_nodes,threshold,
                                   cfg['gateways']['local_radius_m'])
                for g in gt.gateways:
                    gateway_rows.append({**base,'region_id':region.region_id,'gateway_node':g.node,'ingress':g.ingress,
                        'egress':g.egress,'boundary_edge_count':g.boundary_edge_count,'graph_fingerprint':graph_fp})
                gateway_sets[region.region_id]={(g.node,g.ingress,g.egress) for g in gt.gateways}
                index=region_index[region.region_id]
                lo,hi=member_slices[index];members=member_order[lo:hi]
                binding={n:(i,e) for n,i,e in zip(gt.member_nodes,gt.member_ingress,gt.member_egress)}
                for member in members:
                    i,e=binding[int(opportunities.access_nodes[member])]
                    ingress[member]=-1 if i is None else i;egress[member]=-1 if e is None else e
                    binding_rows.append({**base,'region_id':region.region_id,'opportunity_index':int(member),
                        'access_node':int(opportunities.access_nodes[member]),'ingress_gateway':int(ingress[member]),'egress_gateway':int(egress[member])})
                ni=sum(g.ingress for g in gt.gateways);ne=sum(g.egress for g in gt.gateways)
                gateway_stats.append({**base,'region_id':region.region_id,'member_access_nodes':len(nodes),
                    'local_node_count':gt.local_node_count,'local_edge_count':gt.local_edge_count,'gateway_count':len(gt.gateways),
                    'ingress_count':ni,'egress_count':ne,'possible_interface_pairs':ni*ne,
                    'unreachable_member_count':gt.unreachable_member_count,'local_build_seconds':gt.local_build_seconds,
                    'interface_seconds':gt.interface_seconds,'routing_computations_avoided':0})
            measured('gateway_extraction',start,instance,ratio,count=len(gateway_rows))
            writers['gateways'].write(gateway_rows);writers['region_gateway_stats'].write(gateway_stats);writers['gateway_bindings'].write(binding_rows)
            if previous_gateway_sets:
                shared=set(previous_gateway_sets)&set(gateway_sets)
                writers['gateway_expansion_stability'].write([{'instance_id':instance,'to_ratio':float(ratio),
                    'same_member_regions':len(shared),'identical_gateway_fraction':float(np.mean([previous_gateway_sets[r]==gateway_sets[r] for r in shared])) if shared else float('nan'),
                    'mean_gateway_jaccard':float(np.mean([len(previous_gateway_sets[r]&gateway_sets[r])/len(previous_gateway_sets[r]|gateway_sets[r]) if previous_gateway_sets[r]|gateway_sets[r] else 1 for r in shared])) if shared else float('nan')}])
            previous_gateway_sets=gateway_sets
            for taskname,fullplans in maxplans.items():
                feasible=fullplans.total_time_s<=threshold
                at_budget=fullplans.subset(feasible)
                for access in cfg['access']['scenarios']:
                    plans=at_budget if access=='all_attached' else at_budget.subset(at_budget.objectives[:,4]==0)
                    for dwell in cfg['dwell_scenarios']:
                        z=plans.objectives.copy()
                        if dwell=='structural_concurrency':
                            durations=[cfg['activity_duration_s'][c] for c in cfg['tasks'][taskname]['required_capabilities']]
                            z[:,3]=sum(durations);z[plans.concurrency>0,3]=max(durations)
                        normalized=normalize_objectives(z,cfg['normalization_scales'])
                        context={**base,'task':taskname,'primary_task':bool(cfg['tasks'][taskname]['primary']),
                                 'access_scenario':access,'dwell_scenario':dwell}
                        start=time.perf_counter()
                        flat_frontier=kernel(normalized,np.zeros(len(plans),dtype=np.int64))
                        geographic=np.flatnonzero(plans.region_mask(labels['geographic baseline']))
                        decision=np.flatnonzero(plans.region_mask(labels['decision-aware']))
                        groups=labels['decision-aware'][plans.first]
                        if len(plans) and (groups<0).any():raise ValueError('Eligible plan missing frozen region')
                        pareto=decision[kernel(normalized[decision],groups[decision])]
                        measured('pareto_pruning',start,instance,ratio,taskname,access,dwell,len(pareto))
                        sets={'flat':flat_frontier,'geographic':geographic,'decision':decision,'exact_pareto':pareto}
                        counts={'flat':len(plans),'geographic':len(geographic),'decision':len(decision),'exact_pareto':len(pareto)}
                        # Scoring exact geographic/decision frontiers is safe for
                        # positive linear evaluation; counts still record all plans.
                        score_sets={'flat':flat_frontier,'geographic':geographic[kernel(normalized[geographic],np.zeros(len(geographic),dtype=np.int64))],
                                    'decision':decision[kernel(normalized[decision],np.zeros(len(decision),dtype=np.int64))],
                                    'exact_pareto':pareto}
                        pareto_rows={**context,'flat_count':len(plans),'region_count':len(decision),'pareto_count':len(pareto),
                            'flat_to_region_reduction':float(1-len(decision)/len(plans)) if len(plans) else float('nan'),
                            'region_to_pareto_reduction':float(1-len(pareto)/len(decision)) if len(decision) else float('nan')}
                        writers['pareto_stats'].write([pareto_rows])
                        if access=='all_attached' and dwell=='without_dwell' and len(decision):
                            gfirst=ingress[plans.first[decision]]
                            glast=egress[np.where(plans.second[decision]<0,plans.first[decision],plans.second[decision])]
                            usage=pd.DataFrame({'region_label':groups[decision],'ingress_gateway':gfirst,'egress_gateway':glast})
                            usage=usage.value_counts(sort=False).reset_index(name='exact_plan_count')
                            usage['region_id']=usage.region_label.map(dict(enumerate(region_ids['decision-aware'])))
                            usage=usage.drop(columns='region_label')
                            for key,value in context.items():usage[key]=value
                            writers['gateway_microplan_usage'].write(usage)
                        cover_rows=[];start=time.perf_counter()
                        for covername,eps in cfg['epsilon_covers'].items():
                            retained,witness=grouped_epsilon_cover(normalized[pareto],groups[pareto],eps)
                            covered=pareto[retained]
                            if len(pareto) and not np.all(normalized[pareto[witness]]<=normalized[pareto]+np.asarray(eps)+1e-12):
                                raise ValueError('Invalid componentwise cover witness')
                            sets['epsilon_'+covername]=covered;score_sets['epsilon_'+covername]=covered;counts['epsilon_'+covername]=len(covered)
                            # Random same count in EACH region is a stronger spatial
                            # control than arbitrary global sampling.
                            random=[]
                            random_order=decision[np.argsort(groups[decision],kind='stable')]
                            random_groups=groups[random_order]
                            unique_cover_groups,cover_group_counts=np.unique(groups[covered],return_counts=True)
                            for group,count in zip(unique_cover_groups,cover_group_counts):
                                candidates=random_order[np.searchsorted(random_groups,group,'left'):np.searchsorted(random_groups,group,'right')]
                                count=int(count)
                                indices=random_representatives(len(candidates),count,stable_seed(cfg['seed'],instance,ratio,taskname,access,dwell,covername,int(group)))
                                random.extend(candidates[indices])
                            random=np.array(sorted(random),dtype=np.int64)
                            method='random_'+covername;sets[method]=random;score_sets[method]=random;counts[method]=len(random)
                            cover_rows.append({**context,'cover':covername,'pareto_count':len(pareto),'retained_count':len(covered),
                                'pareto_to_cover_reduction':float(1-len(covered)/len(pareto)) if len(pareto) else float('nan'),
                                'flat_to_final_reduction':float(1-len(covered)/len(plans)) if len(plans) else float('nan'),
                                'componentwise_cover_verified':True})
                        measured('epsilon_cover_and_random',start,instance,ratio,taskname,access,dwell,sum(len(s) for s in sets.values()))
                        writers['epsilon_cover_stats'].write(cover_rows)
                        countrows=[];regretrows=[];toprows=[];coveragerows=[];failures=[];start=time.perf_counter()
                        flatcost=normalized[flat_frontier]@weights.T
                        flatbest=np.min(flatcost,axis=0) if len(flat_frontier) else np.full(len(names),np.nan)
                        flatarg=flat_frontier[np.argmin(flatcost,axis=0)] if len(flat_frontier) else np.full(len(names),-1,dtype=np.int64)
                        methodbest={}
                        for method,ids in score_sets.items():
                            count=counts[method];costs=normalized[ids]@weights.T
                            selected=ids[np.argmin(costs,axis=0)] if len(ids) else np.full(len(names),-1,dtype=np.int64)
                            best=np.min(costs,axis=0) if len(ids) else np.full(len(names),np.inf)
                            methodbest[method]=best
                            absolute=np.maximum(0,best-flatbest)
                            norm=absolute/(np.abs(flatbest)+cfg['evaluation']['normalized_regret_eta'])
                            if not len(plans):absolute[:]=np.nan;norm[:]=np.nan
                            countrows.append({**context,'method':method,'flat_count':len(plans),'candidate_count':count,
                                'retained_fraction':float(count/len(plans)) if len(plans) else float('nan'),
                                'no_feasible_flat_plan':len(plans)==0,'no_feasible_method_plan':count==0})
                            for theta_id,a,rn,fb,sb,oracle,chosen in zip(names,absolute,norm,flatbest,best,flatarg,selected):
                                first=-1 if chosen<0 else int(plans.first[chosen]);second=-1 if chosen<0 else int(plans.second[chosen])
                                oracle_first=-1 if oracle<0 else int(plans.first[oracle]);oracle_second=-1 if oracle<0 else int(plans.second[oracle])
                                row={**context,'method':method,'theta_id':theta_id,'flat_count':len(plans),'retained_count':count,
                                    'absolute_regret':float(a),'normalized_regret':float(rn),'flat_best_cost':float(fb),'selected_cost':float(sb),
                                    'oracle_first_index':oracle_first,'oracle_second_index':oracle_second,
                                    'selected_first_index':first,'selected_second_index':second,
                                    'selected_ingress_gateway':-1 if first<0 else int(ingress[first]),
                                    'selected_egress_gateway':-1 if first<0 else int(egress[second if second>=0 else first]),
                                    'selected_identity_changed':(first,second)!=(oracle_first,oracle_second)}
                                regretrows.append(row)
                                for k in cfg['evaluation']['top_k']:
                                    toprows.append({**context,'method':method,'theta_id':theta_id,'k':k,'absolute_regret':float(a),
                                                   'normalized_regret':float(rn),'returned_count':min(k,count)})
                                if method in ['geographic','decision'] and np.isfinite(fb) and a>cfg['evaluation']['bound_check_tolerance']:
                                    cross=oracle_second>=0 and labels['decision-aware' if method=='decision' else 'geographic baseline'][oracle_first]!=labels['decision-aware' if method=='decision' else 'geographic baseline'][oracle_second]
                                    failures.append({**context,'method':method,'theta_id':theta_id,'absolute_regret':float(a),
                                        'cause':'cross-region bundle required' if cross else 'other',
                                        'oracle_first_index':oracle_first,'oracle_second_index':oracle_second,
                                        'selected_first_index':first,'selected_second_index':second,
                                        'cause_is_structurally_verified':bool(cross),'gateway_pruning_applied':False})
                            for k in cfg['evaluation']['top_k']:
                                for tau in cfg['evaluation']['absolute_regret_tolerances']:
                                    valid=~np.isnan(absolute)
                                    coveragerows.append({**context,'method':method,'k':k,'absolute_tolerance':float(tau),
                                        'valid_evaluations':int(valid.sum()),'within_tolerance':int(np.sum(absolute[valid]<=tau+cfg['evaluation']['bound_check_tolerance'])),
                                        'coverage':float(np.mean(absolute[valid]<=tau+cfg['evaluation']['bound_check_tolerance'])) if valid.any() else float('nan'),
                                        'no_feasible_flat_plan':not valid.any()})
                        # Exact Pareto never changes a positive-linear optimum;
                        # epsilon loss ABOVE region optimum has conditional bound.
                        if len(decision):
                            if not np.allclose(methodbest['decision'],methodbest['exact_pareto'],atol=1e-10):raise ValueError('Exact Pareto changed optimum')
                            for covername,eps in cfg['epsilon_covers'].items():
                                excess=methodbest['epsilon_'+covername]-methodbest['decision']-weights@np.asarray(eps)
                                max_bound_excess=max(max_bound_excess,float(excess.max()))
                                if np.any(excess>cfg['evaluation']['bound_check_tolerance']):raise ValueError('Positive linear epsilon bound violated')
                        measured('scalar_regret_evaluation',start,instance,ratio,taskname,access,dwell,len(regretrows))
                        for name,rows in [('candidate_counts',countrows),('abstraction_regret',regretrows),('topk_regret',toprows),
                                          ('epsilon_optimal_coverage',coveragerows),('failure_analysis',failures)]:writers[name].write(rows)
                        empty_flat+=int(len(plans)==0);empty_region+=int(len(plans)>0 and len(decision)==0)
        measured('od_total',odstart,instance,count=sum(len(p) for p in maxplans.values()))
        print(json.dumps({'od':instance,'seconds':perf[-1]['seconds'],'max_budget_candidates':perf[-1]['count'],
                          'rss_mib':perf[-1]['peak_rss_mib']}),flush=True)
        del maxplans,membership,regions,localpairs,dist,pl,sl,parents,next_nodes
    for writer in writers.values():writer.close()
    router.close()
    pd.DataFrame(perf).to_parquet(result/'performance.parquet',index=False)
    benchmark={'run':run,'configuration':cfg,'native':{**router.provenance,'pareto_source_sha256':sha256(ROOT/'src/microplan/pareto.cpp')},'graph_fingerprint':graph_fp,
               'feasibility_fingerprint':feasibility_fp,'sequential_experiment_seconds':time.perf_counter()-total_start,
               'peak_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
               'processed_od_ids':instances.instance_id.tolist(),'ratios':envcfg['detour_ratios'],
               'empty_flat_groups':empty_flat,'nonempty_flat_empty_decision_groups':empty_region,
               'maximum_epsilon_bound_excess':max_bound_excess,'local_costs':pairmeta,
               'candidate_partition_files':saved_files,
               'result_files':{p.name:sha256(p) for p in result.glob('*.parquet')
                   if p.stem in outputs or p.stem in ['performance','opportunity_index','local_costs','utility_weights','candidate_estimates']}}
    (result/'benchmark.json').write_text(json.dumps(benchmark,indent=2)+'\n')
    print(json.dumps({k:benchmark[k] for k in ['sequential_experiment_seconds','peak_rss_mib','empty_flat_groups','maximum_epsilon_bound_excess']},indent=2))

if __name__=='__main__':main()
