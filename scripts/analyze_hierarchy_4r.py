"""Summarize complete B1 evidence; never invent a zero-denominator convention."""
import json
import pandas as pd
from _common import ROOT,sha256
from _stopplan4r_common import write_json


def main():
    out=ROOT/'results/milestone_4r_b1'
    summary=json.loads((out/'oracle_summary.json').read_text())
    m=pd.read_csv(out/'logical_work.csv');primary=m[m.epsilon.eq(0)]
    roles=pd.read_csv(out/'role_work.csv');roles=roles[roles.epsilon.eq(0)]
    strata=[]
    for col in ['ratio','initial_soc','scenario','instance_id']:
        for value,g in primary.groupby(col):
            strata.append(dict(dimension=col,value=str(value),cases=len(g),defined_cases=int(g.reduction.notna().sum()),
                zero_semantic_cases=int(g.reduction.isna().sum()),defined_case_median_reduction=g.reduction.median(),
                median_semantic_sites=g.semantic_flat_sites.median(),median_logical_evaluations=g.logical_site_evaluations.median(),
                median_bounds=g.bounds_computed.median()))
    for value,g in roles.groupby('role'):
        strata.append(dict(dimension='role',value=value,cases=len(g),defined_cases=int(g.reduction.notna().sum()),
            zero_semantic_cases=int(g.reduction.isna().sum()),defined_case_median_reduction=g.reduction.median(),
            median_semantic_sites=g.semantic_sites.median(),median_logical_evaluations=g.logical_evaluations.median()))
    pd.DataFrame(strata).to_csv(out/'stratified_work.csv',index=False)
    records=[]
    context=primary.set_index('case_id')
    for path in sorted((out/'oracle_epsilon_0').glob('views_*.parquet')):
        f=pd.read_parquet(path)
        if not len(f):continue
        case=int(path.stem.split('_')[1]);f['case_id']=case
        for col in ['instance_id','ratio','initial_soc','scenario']:f[col]=context.loc[case,col]
        records.append(f)
    views=pd.concat(records,ignore_index=True)
    views.to_parquet(out/'primary_region_diagnostics.parquet',index=False)
    gaps=[]
    for col in ['role','depth','ratio','initial_soc','scenario','instance_id']:
        for value,g in views.groupby(col):
            gaps.append(dict(dimension=col,value=str(value),views=len(g),median_G_model=g.G_model.median(),
                median_G_agg=g.G_agg.median(),p95_G_agg=g.G_agg.quantile(.95),max_G_agg=g.G_agg.max(),
                G_cert='unavailable: no deployable bound',certified_fraction=g.certified.mean(),
                median_bound_slack=g.bound_slack.median()))
    pd.DataFrame(gaps).to_csv(out/'gap_decomposition.csv',index=False)
    views.groupby(['role','depth']).agg(views=('region','size'),median_G_agg=('G_agg','median'),
        p95_G_agg=('G_agg',lambda x:x.quantile(.95)),certified_fraction=('certified','mean')).reset_index().to_csv(out/'role_depth_gaps.csv',index=False)
    epsilon=m.groupby('epsilon').agg(cases=('case_id','size'),defined_cases=('reduction','count'),
        conditional_median_reduction=('reduction','median'),median_logical_evaluations=('logical_site_evaluations','median'),
        max_observed_gap=('cost_gap','max'),median_hierarchy_seconds=('hierarchy_seconds','median')).reset_index()
    epsilon.to_csv(out/'epsilon_sensitivity.csv',index=False)
    # A user-provided convention must be recorded explicitly before classification.
    policy=out/'zero_denominator_policy.json'
    if policy.exists():
        p=json.loads(policy.read_text())
        if p['policy']=='zero_reduction':values=primary.reduction.fillna(0.)
        elif p['policy']=='defined_cases_only':values=primary.reduction.dropna()
        else:raise ValueError('Unknown explicitly authorized policy')
        median=float(values.median());p50=float(values.ge(.5).mean());p25=float(values.ge(.25).mean())
        classification='strong GO' if median>=.7 and p50>=.75 else 'NO-GO' if median<.5 or p25<.75 else 'gray zone'
        summary.update(classification=classification,median_reduction=median,
            fraction_at_least_50_percent=p50,fraction_at_least_25_percent=p25,
            classification_cases=len(values),zero_denominator_policy_sha256=sha256(policy))
    summary.update(primary_views=len(views),certified_views=int(views.certified.sum()),
        H1_violations=int(views.H1_violation.sum()),H3_violations=int(views.H3_violation.sum()),
        perturbation_violations=int(views.perturbation_violation.sum()),
        median_aggregation_gap=float(views.G_agg.median()),p95_aggregation_gap=float(views.G_agg.quantile(.95)),
        total_semantic_site_actions=int(primary.semantic_flat_sites.sum()),
        total_logical_leaf_evaluations=int(primary.logical_site_evaluations.sum()))
    write_json(out/'oracle_analysis.json',summary)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
