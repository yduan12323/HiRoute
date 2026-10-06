"""Offline analysis; never imported by deployable bound/search code."""
import json
import numpy as np
import pandas as pd
from _common import ROOT
from _stopplan4r_common import write_json
from hierarchy4r.deploy import micro_reduction


def main():
    out=ROOT/'results/milestone_4r_b1d'
    assert json.loads((out/'query_completion.json').read_text())['cases']==480
    static=json.loads((out/'static_audit.json').read_text())
    assert static['violations']==0
    work=pd.read_csv(out/'work.csv')
    assert len(work)==480 and work.case_id.is_unique
    context=['case_id','instance_id','ratio','initial_soc','scenario']
    audits=[];leaves=[]
    for c in range(480):
        a=pd.read_parquet(out/'queries'/f'audit_{c:03d}.parquet');a['case_id']=c;audits.append(a)
        leaf=pd.read_parquet(out/'queries'/f'leaves_{c:03d}.parquet');leaf['case_id']=c;leaves.append(leaf)
    audit=pd.concat(audits,ignore_index=True).merge(work[context],on='case_id',validate='many_to_one')
    leaf=pd.concat(leaves,ignore_index=True).merge(work[context],on='case_id',validate='many_to_one')
    audit.to_parquet(out/'visited_region_audit.parquet',index=False)
    leaf.to_csv(out/'leaf_false_positives.csv',index=False)
    d1=pd.read_csv(out/'D1_coverage.csv');d4=pd.read_csv(out/'D4_preservation.csv');d5=pd.read_csv(out/'D5_instrumentation.csv')
    d2=int(audit.D2_violation.sum());d3=int(audit.D3_violation.sum())
    hidden=int(audit[['site_ids_read','evaluator_calls','oracle_table_reads']].sum().sum())
    gates=dict(D1=int(d1.violations.sum()+static['violations']),D2=d2,D3=d3,
               D4=int((~d4.passed).sum()),D5=int(d5.violations.sum()+hidden))
    write_json(out/'correctness_gates.json',dict(cases=480,violations=gates,passed=not any(gates.values()),
        visited_region_buckets=len(audit),internal_region_buckets=int(audit.internal.sum()),
        semantic_populated_buckets=int(audit.semantic_count.gt(0).sum()),
        false_positive_only_buckets=int(audit.semantic_count.eq(0).sum()),
        coverage_semantic_actions=int(d1.semantic_actions.sum()),static_paths_preserved=True,
        precomparison_D2=json.loads((out/'precomparison_D2.json').read_text())))
    assert not any(gates.values()),'Scientific interpretation forbidden after a correctness violation'
    for name,col in [('D2','D2_violation'),('D3','D3_violation')]:
        audit.groupby('case_id').agg(audited=('region','size'),violations=(col,'sum')).reset_index().to_csv(out/f'{name}_audit.csv',index=False)
        columns=context+['region','bucket','depth',col]
        columns+=['tm','tp','dm','dp','exact_tm','exact_tp','exact_dm','exact_dp'] if name=='D2' else ['lower','semantic_count','semantic_minimum','infeasible']
        audit[columns].to_parquet(out/f'{name}_audit.parquet',index=False)
    audit[context+['region','bucket','depth','internal','landmark_count','summary_rows_read','site_ids_read','evaluator_calls','oracle_table_reads']].to_parquet(out/'D5_bound_instrumentation.parquet',index=False)
    reasons=audit.groupby('decision').size().rename('count').reset_index()
    reasons['fraction']=reasons['count']/len(audit);reasons.to_csv(out/'prune_reasons.csv',index=False)
    audit[context+['region','bucket','depth','decision','raw_cost','raw_safe_cost','lower']].to_parquet(out/'region_prune_reasons.parquet',index=False)
    gaps=audit[audit.G_cert.notna()]
    strat=[]
    for dim in ['depth','bucket','ratio','initial_soc','scenario','instance_id']:
        for value,g in gaps.groupby(dim):
            strat.append(dict(dimension=dim,value=str(value),views=len(g),median_G_cert=float(g.G_cert.median()),
                p95_G_cert=float(g.G_cert.quantile(.95)),mean_G_cert=float(g.G_cert.mean()),
                min_G_cert=float(g.G_cert.min()),max_G_cert=float(g.G_cert.max())))
    pd.DataFrame(strat).to_csv(out/'certificate_gap_strata.csv',index=False)
    slack=[]
    for dim in ['depth','bucket']:
        for value,g in audit.groupby(dim):
            for metric in ['tm','tp','dm','dp']:
                delta=g['exact_'+metric]-g[metric]
                delta=delta[np.isfinite(delta)]
                slack.append(dict(dimension=dim,value=str(value),metric=metric,views=len(delta),
                    median_slack=float(delta.median()),p95_slack=float(delta.quantile(.95))))
    pd.DataFrame(slack).to_csv(out/'landmark_slack_strata.csv',index=False)
    gaps[context+['region','bucket','depth','oracle_lower','lower','G_cert']].to_parquet(out/'certificate_gaps.parquet',index=False)
    # Ratio measures only use the approved positive semantic population.
    defined=work[work.semantic_flat_sites.gt(0)]
    assert len(defined)==387 and work.loc[work.semantic_flat_sites.eq(0),'reduction'].isna().all()
    oracle=json.loads((out/'b1_oracle_classification.json').read_text())
    median=float(defined.reduction.median());retention=median/oracle['macro_conditional_median_reduction']
    count_gate=median>=.5 and retention>=.7
    strata=[]
    for dim in ['scenario','ratio','initial_soc','instance_id']:
        for value,g in work.groupby(dim):
            pos=g[g.semantic_flat_sites.gt(0)]
            strata.append(dict(dimension=dim,value=str(value),cases=len(g),defined_cases=len(pos),
                median_reduction=None if pos.empty else float(pos.reduction.median()),
                micro_reduction=micro_reduction(g.deploy_exact_site_evaluations,g.semantic_flat_sites),
                operational_micro=micro_reduction(g.deploy_exact_site_evaluations,g.flat_static_candidates)))
    pd.DataFrame(strata).to_csv(out/'work_strata.csv',index=False)
    work['metric_status']=np.where(work.semantic_flat_sites.gt(0),'defined','no_semantic_site_pruning_opportunity')
    work.to_parquet(out/'work.parquet',index=False)
    timing=[]
    for col in ['lookup_seconds','bound_seconds','refinement_overhead_seconds','leaf_seconds','search_seconds',
                'shared_routing_seconds','flat_seconds','end_to_end_seconds','flat_end_to_end_seconds']:
        timing.append(dict(component=col,cases=480,median_seconds=float(work[col].median()),
            p95_seconds=float(work[col].quantile(.95)),sum_seconds=float(work[col].sum())))
    timing_gate=None;avoided=None
    if (out/'avoided_timing.csv').exists():
        avoided=pd.read_csv(out/'avoided_timing.csv')
        assert len(avoided)==480
        assert np.array_equal(avoided.avoided_candidates.to_numpy()+work.deploy_exact_site_evaluations.to_numpy(),work.flat_static_candidates.to_numpy())
        timing_gate=bool(avoided.bound_refinement_seconds.median()<=avoided.avoided_site_seconds.median())
        for col in ['bound_refinement_seconds','avoided_site_seconds']:
            timing.append(dict(component=col,cases=480,median_seconds=float(avoided[col].median()),
                p95_seconds=float(avoided[col].quantile(.95)),sum_seconds=float(avoided[col].sum())))
    pd.DataFrame(timing).to_csv(out/'timing_summary.csv',index=False)
    summary=dict(all_cases=480,metric_defined_cases=len(defined),zero_semantic_cases=480-len(defined),
        correctness_passed=True,macro_conditional_median_reduction=median,oracle_median=oracle['macro_conditional_median_reduction'],
        oracle_retention=retention,median_threshold=.5,retention_threshold=.7,workload_gate_passed=count_gate,
        timing_gate_passed=timing_gate,timing_qualifier=None if timing_gate is not None else 'B1-D timing break-even unresolved',
        classification='B1-D deployable gate passed' if count_gate and timing_gate is not False else 'B1-D deployable gate failed',
        micro_workload_reduction=micro_reduction(work.deploy_exact_site_evaluations,work.semantic_flat_sites),
        operational_median_reduction=float(work.operational_reduction.median()),
        operational_micro_reduction=micro_reduction(work.deploy_exact_site_evaluations,work.flat_static_candidates),
        flat_semantic_total=int(work.semantic_flat_sites.sum()),deploy_exact_total=int(work.deploy_exact_site_evaluations.sum()),
        deploy_semantic_total=int(work.deploy_semantic_site_evaluations.sum()),
        deploy_objective_calls=int(work.objective_site_calls.fillna(0).sum()),
        outside_envelope_checks=int(work.outside_envelope.fillna(0).sum()),
        flat_static_candidate_total=int(work.flat_static_candidates.sum()),
        false_positive_total=int(work.false_positive_count.sum()),
        leaf_false_positive_rate=float(work.false_positive_count.sum()/work.deploy_exact_site_evaluations.sum()),
        zero_semantic_leaf_work=int(work.loc[work.semantic_flat_sites.eq(0),'deploy_exact_site_evaluations'].sum()),
        exact_zero_stop_selected=int(d4.selected_action.eq('zero').sum()),
        G_cert_median=float(gaps.G_cert.median()),G_cert_p95=float(gaps.G_cert.quantile(.95)),
        gap_views=len(gaps),false_positive_only_views=int(audit.semantic_count.eq(0).sum()),
        visited_bounds=len(audit),query_peak_rss_mib=float(work.peak_rss_mib.max()),
        all_case_query_seconds=float(work.search_seconds.sum()),all_case_clean_flat_seconds=float(work.flat_seconds.sum()),
        optional_epsilon='not run; exact primary only')
    write_json(out/'analysis.json',summary)
    print(json.dumps(summary,indent=2),flush=True)


if __name__=='__main__':main()
