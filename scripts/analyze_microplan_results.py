"""Measured Go-1 summaries, paired stage loss, and early-expansion diagnostics."""
import json
import numpy as np
import pandas as pd
from _common import ROOT,read_config,sha256
from _microplan_common import identity_keys


def distribution(values):
    a=np.asarray(values,float);a=a[~np.isnan(a)]
    finite=a[np.isfinite(a)]
    # Infinite loss (flat feasible, method empty) stays in coverage and is
    # explicitly counted; finite summaries are labelled, never silently pooled.
    return {'evaluations':len(a),'finite_evaluations':len(finite),'infinite_evaluations':int(np.isinf(a).sum()),
            'median':float(np.median(finite)) if len(finite) else None,
            'p90':float(np.quantile(finite,.9)) if len(finite) else None,
            'p95':float(np.quantile(finite,.95)) if len(finite) else None,
            'worst_finite':float(np.max(finite)) if len(finite) else None,
            'worst':float(np.max(a)) if len(a) else None}


def json_safe(value):
    if isinstance(value, dict):return {k:json_safe(v) for k,v in value.items()}
    if isinstance(value, list):return [json_safe(v) for v in value]
    if isinstance(value, float) and not np.isfinite(value):
        return 'infinity' if np.isposinf(value) else '-infinity' if np.isneginf(value) else None
    return value


def main():
    cfg=read_config('configs/microplan.yaml');root=ROOT/cfg['results_dir']
    columns=['instance_id','ratio','task','primary_task','access_scenario','dwell_scenario','method','theta_id',
             'absolute_regret','normalized_regret','flat_best_cost','selected_cost','oracle_first_index','oracle_second_index',
             'selected_first_index','selected_second_index','flat_count','retained_count','selected_identity_changed','boundary_risk']
    regret=pd.read_parquet(root/'abstraction_regret.parquet',columns=columns)
    primary=regret[(regret.primary_task)&(regret.ratio.isin([1.05,1.1,1.2,1.4]))&
                   (regret.access_scenario=='all_attached')&(regret.dwell_scenario=='without_dwell')]
    groups=[]
    for (method,task,access,dwell),table in regret[regret.ratio.isin([1.05,1.1,1.2,1.4])].groupby(['method','task','access_scenario','dwell_scenario']):
        d=distribution(table.absolute_regret)
        groups.append({'method':method,'task':task,'access_scenario':access,'dwell_scenario':dwell,**d,
                       'identity_changed_fraction':float(table.selected_identity_changed.mean()),
                       'no_flat_oracle_evaluations':int(table.absolute_regret.isna().sum()),
                       'coverage_tau_0':float(np.mean(table.loc[table.absolute_regret.notna(),'absolute_regret']<=1e-10)) if table.absolute_regret.notna().any() else float('nan'),
                       'coverage_tau_001':float(np.mean(table.loc[table.absolute_regret.notna(),'absolute_regret']<=.01+1e-10)) if table.absolute_regret.notna().any() else float('nan'),
                       'coverage_tau_005':float(np.mean(table.loc[table.absolute_regret.notna(),'absolute_regret']<=.05+1e-10)) if table.absolute_regret.notna().any() else float('nan')})
    pd.DataFrame(groups).to_parquet(root/'task_regret_summary.parquet',index=False)
    context=['instance_id','ratio','task','access_scenario','dwell_scenario','theta_id']
    # Paired additive scalar loss is exact for the fixed minimization objective.
    costs=regret.pivot(index=context,columns='method',values='selected_cost')
    paired=pd.DataFrame(index=costs.index)
    paired['region_loss']=costs.decision-costs.flat
    paired['pareto_loss']=costs.exact_pareto-costs.decision
    for name in cfg['epsilon_covers']:
        paired[name+'_cover_loss']=costs['epsilon_'+name]-costs.exact_pareto
        paired[name+'_total_loss']=costs['epsilon_'+name]-costs.flat
    paired=paired.reset_index();paired.to_parquet(root/'stage_regret.parquet',index=False)
    # Report budget evolution and associate (rather than assert causal identity)
    # decision loss with the frozen region partition's common-member ARI.
    decision=regret[regret.method=='decision'].copy()
    keys=['instance_id','task','access_scenario','dwell_scenario','theta_id']
    decision=decision.sort_values(keys+['ratio'])
    g=decision.groupby(keys)
    for column in ['ratio','absolute_regret','oracle_first_index','oracle_second_index','selected_first_index','selected_second_index']:
        decision['previous_'+column]=g[column].shift()
    decision['regret_change']=decision.absolute_regret-decision.previous_absolute_regret
    decision['oracle_identity_changed_expansion']=(decision.oracle_first_index!=decision.previous_oracle_first_index)|(decision.oracle_second_index!=decision.previous_oracle_second_index)
    decision['selected_identity_changed_expansion']=(decision.selected_first_index!=decision.previous_selected_first_index)|(decision.selected_second_index!=decision.previous_selected_second_index)
    stability=pd.read_parquet(ROOT/cfg['frozen_region_dir']/'expansion_stability.parquet')
    print('Stability columns',stability.columns.tolist())
    # Column names are explicitly mapped below after inspecting the frozen schema.
    stability=stability[stability.method=='decision-aware']
    to_column='to_ratio' if 'to_ratio' in stability else 'ratio'
    if to_column not in stability:
        to_column='ratio_to'
    decision=decision[decision.previous_ratio.notna()]
    decision=decision.merge(stability,how='left',left_on=['instance_id','ratio'],right_on=['instance_id',to_column],suffixes=('','_4a'))
    decision['both_flat_oracles_available']=(decision.oracle_first_index>=0)&(decision.previous_oracle_first_index>=0)
    for name in ['previous_oracle_region_valid_before','previous_oracle_region_valid_now','previous_oracle_newly_excluded','previous_selected_newly_excluded']:
        decision[name]=False
    catalogue=pd.read_parquet(root/'opportunity_index.parquet',columns=['osm_type','osm_id'])
    lookup=pd.Index(identity_keys(catalogue.osm_type,catalogue.osm_id))
    for instance,odrows in decision.groupby('instance_id'):
        member=pd.read_parquet(ROOT/cfg['frozen_region_dir']/'region_membership.parquet',
            filters=[('instance_id','==',int(instance)),('method','==','decision-aware')],columns=['ratio','osm_type','osm_id','region_id'])
        partitions={}
        for ratio,part in member.groupby('ratio'):
            label=np.full(len(catalogue),-1,dtype=np.int64)
            ids=lookup.get_indexer(identity_keys(part.osm_type,part.osm_id));assert (ids>=0).all()
            label[ids]=pd.factorize(part.region_id,sort=True)[0];partitions[ratio]=label
        for ratio,rows in odrows.groupby('ratio'):
            old=partitions[float(rows.previous_ratio.iloc[0])];new=partitions[ratio]
            first=rows.previous_oracle_first_index.to_numpy(np.int64);second=rows.previous_oracle_second_index.to_numpy(np.int64)
            available=first>=0
            before=available&((second<0)|(old[np.maximum(first,0)]==old[np.maximum(second,0)]))
            now=available&((second<0)|(new[np.maximum(first,0)]==new[np.maximum(second,0)]))
            decision.loc[rows.index,'previous_oracle_region_valid_before']=before
            decision.loc[rows.index,'previous_oracle_region_valid_now']=now
            decision.loc[rows.index,'previous_oracle_newly_excluded']=before&~now
            first=rows.previous_selected_first_index.to_numpy(np.int64);second=rows.previous_selected_second_index.to_numpy(np.int64)
            decision.loc[rows.index,'previous_selected_newly_excluded']=(first>=0)&(second>=0)&(new[np.maximum(first,0)]!=new[np.maximum(second,0)])
    decision.to_parquet(root/'decision_expansion.parquet',index=False)
    counts=pd.read_parquet(root/'candidate_counts.parquet')
    counts=counts[(counts.access_scenario=='all_attached')&(counts.dwell_scenario=='without_dwell')]
    estimates=pd.read_parquet(root/'candidate_estimates.parquet')
    feasibility=counts[counts.method=='flat'].merge(estimates,on=['instance_id','ratio','task'])
    feasibility['exact_feasibility_rate']=np.where(feasibility.candidate_upper_count>0,
                                                   feasibility.flat_count/feasibility.candidate_upper_count,np.nan)
    feasibility.to_parquet(root/'microplan_feasibility.parquet',index=False)
    summary={'primary_definition':'All 30 ODs x practical budgets x seven tasks x sixteen fixed theta; all attached, without dwell; equal scenario observations',
             'methods':{m:distribution(t.absolute_regret) for m,t in primary.groupby('method')},
             'task_methods':groups,'primary_worst_examples':primary.sort_values('absolute_regret',ascending=False).head(20).replace({np.nan:None}).to_dict('records')}
    (root/'summary.json').write_text(json.dumps(json_safe(summary),indent=2,allow_nan=False)+'\n')
    benchmark=json.loads((root/'benchmark.json').read_text())
    derived=['task_regret_summary.parquet','stage_regret.parquet','decision_expansion.parquet','microplan_feasibility.parquet','filter_performance.parquet','gateway_stage_performance.parquet']
    # A repeated run may already have derived outputs: they belong to the
    # analysis phase, never stale core-phase fingerprints.
    for name in derived:benchmark['result_files'].pop(name,None)
    benchmark['analysis_files']={name:sha256(root/name) for name in derived if (root/name).exists()}
    (root/'benchmark.json').write_text(json.dumps(benchmark,indent=2)+'\n')
    print(json.dumps(summary['methods'],indent=2))

if __name__=='__main__':main()
