"""Post-hoc B1-E component analysis; no empirical GO/NO-GO threshold."""
import json
import numpy as np
import pandas as pd
from _common import ROOT
from _stopplan4r_common import write_json
from hierarchy4r.diagnosis import CATEGORIES,AUDIT_TOL


def main():
    out=ROOT/'results/milestone_4r_b1e'
    assert json.loads((out/'diagnostic_completion.json').read_text())['cases']==480
    parts=out/'cases'
    def collect(prefix):
        frames=[]
        for c in range(480):
            f=pd.read_parquet(parts/f'{prefix}_{c:03d}.parquet')
            if 'case_id' not in f:f['case_id']=c
            frames.append(f)
        return pd.concat(frames,ignore_index=True)
    cert=collect('certificate');minima=collect('minima');classification=collect('classification')
    minima.to_parquet(out/'perfect_static_minima.parquet',index=False)
    cert.to_parquet(out/'certificate_decomposition.parquet',index=False)
    cert.drop(columns=['G_landmark','G_residual','total_slack','identity_error']).to_parquet(out/'perfect_static_bounds.parquet',index=False)
    collect('ps_bounds').to_parquet(out/'perfect_static_replay_bounds.parquet',index=False)
    classification.to_parquet(out/'leaf_candidate_classification.parquet',index=False)
    semantic=cert[cert.J_sem.notna()]
    assert (semantic.L_PS<=semantic.J_sem+AUDIT_TOL).all()
    assert (cert.L_ALT<=cert.L_PS+AUDIT_TOL).all()
    assert semantic.identity_error.abs().le(AUDIT_TOL).all()
    strata=[]
    for dim in ['depth','bucket','ratio','initial_soc','scenario','instance_id']:
        for value,g in semantic.groupby(dim):
            strata.append(dict(dimension=dim,value=str(value),nodes=len(g),
                median_G_landmark=float(g.G_landmark.median()),p95_G_landmark=float(g.G_landmark.quantile(.95)),
                median_G_residual=float(g.G_residual.median()),p95_G_residual=float(g.G_residual.quantile(.95)),
                sum_landmark_fraction=float(g.G_landmark.sum()/g.total_slack.sum()),
                median_G_cert_old=float(g.G_cert_old.median())))
    pd.DataFrame(strata).to_csv(out/'certificate_decomposition_strata.csv',index=False)
    flat=pd.read_csv(out/'deployable_flat_work.csv');hier=pd.read_csv(out/'deployable_hier_work.csv')
    for method,table in [('flat',flat),('hier',hier)]:table.to_parquet(out/f'deployable_{method}_work.parquet',index=False)
    comparison=flat[['case_id','instance_id','ratio','initial_soc','scenario']].copy()
    micro={};macro={}
    for field in ['N_region','N_bound','N_envelope','N_exact','N_semantic','T_bound','T_envelope','T_exact','T_search','T_e2e']:
        comparison[field+'_flat']=flat[field];comparison[field+'_hier']=hier[field]
        if field in ['N_envelope','N_exact','T_search','T_e2e']:
            label={'N_envelope':'R_envelope','N_exact':'R_exact','T_search':'R_search_historical','T_e2e':'R_e2e_historical'}[field]
            comparison[label]=np.where(flat[field]>0,1-hier[field]/flat[field],np.nan)
            micro[label]=float(1-hier[field].sum()/flat[field].sum())
            macro[label]=dict(defined_cases=int(comparison[label].notna().sum()),median=float(comparison[label].median()),
                p05=float(comparison[label].quantile(.05)),p95=float(comparison[label].quantile(.95)))
    comparison.to_csv(out/'workload_component_comparison.csv',index=False)
    workload=dict(cases=480,micro=micro,macro=macro,
        flat_totals={k:int(flat[k].sum()) for k in flat if k.startswith('N_')},
        hier_totals={k:int(hier[k].sum()) for k in hier if k.startswith('N_')},
        timing_diagnosis='limited; paired aggregate timings retained from frozen B1-D; envelope/exact splits NA',
        no_new_success_threshold=True)
    write_json(out/'workload_micro_summary.json',workload)
    timing=comparison[['case_id','T_bound_flat','T_bound_hier','T_envelope_flat','T_envelope_hier',
        'T_exact_flat','T_exact_hier','T_search_flat','T_search_hier','T_e2e_flat','T_e2e_hier',
        'R_search_historical','R_e2e_historical']]
    timing.to_csv(out/'historical_clean_timing.csv',index=False)
    mapping={'FP1':'envelope','FP2':'energy','FP3':'energy','FP4':'schedule','FP5':'other','FP6':'no_effect','TP':'semantic'}
    totals=classification.category.value_counts().reindex(CATEGORIES,fill_value=0)
    grouped=totals.groupby([mapping[k] for k in totals.index]).sum()
    pd.DataFrame([dict(category=k,count=int(totals[k]),fraction=float(totals[k]/len(classification)),
        aggregate=mapping[k]) for k in CATEGORIES]).to_csv(out/'false_positive_terminal_summary.csv',index=False)
    pd.DataFrame([dict(category=k,count=int(grouped.get(k,0)),fraction=float(grouped.get(k,0)/len(classification)))
        for k in ['envelope','energy','schedule','other','no_effect','semantic']]).to_csv(out/'false_positive_summary.csv',index=False)
    fpstrata=[]
    for dim in ['bucket','scenario','initial_soc','ratio','instance_id','depth']:
        for value,g in classification.groupby(dim):
            counts=g.category.value_counts()
            for category in CATEGORIES:
                n=int(counts.get(category,0))
                fpstrata.append(dict(dimension=dim,value=str(value),category=category,count=n,total=len(g),fraction=n/len(g)))
    pd.DataFrame(fpstrata).to_csv(out/'false_positive_strata.csv',index=False)
    inc=pd.read_csv(out/'incumbent_acquisition.csv')
    acquired=inc[inc.first_site_acquired];nozero=inc[~inc.zero_initialized]
    assert nozero.first_site_acquired.all()
    inc_summary=dict(cases=480,zero_initialized=int(inc.zero_initialized.sum()),
        first_site_acquired=int(inc.first_site_acquired.sum()),no_site_update=int((~inc.first_site_acquired).sum()),
        no_initial_U_cases=len(nozero),median_pops_to_first_site=float(acquired.pops_to_first_site.median()),
        p95_pops_to_first_site=float(acquired.pops_to_first_site.quantile(.95)),
        median_refinement_fraction=float(acquired.fraction_refinements_to_first_site.median()),
        p95_refinement_fraction=float(acquired.fraction_refinements_to_first_site.quantile(.95)),
        no_initial_U_median_refinement_fraction=float(nozero.fraction_refinements_to_first_site.median()),
        no_initial_U_p95_refinement_fraction=float(nozero.fraction_refinements_to_first_site.quantile(.95)),
        no_initial_U_sum_refinements_before=int(nozero.refinements_to_first_site.sum()),
        no_initial_U_sum_total_refinements=int(nozero.total_refinements.sum()),
        median_candidate_checks_to_first_site=float(acquired.candidates_to_first_site.median()),
        median_exact_calls_to_first_site=float(acquired.exact_to_first_site.median()),
        time_to_first_site='NA: not recorded reliably; no inferred timing')
    write_json(out/'incumbent_acquisition_summary.json',inc_summary)
    inc.groupby(['scenario','initial_soc','ratio']).agg(cases=('case_id','size'),zero_initialized=('zero_initialized','sum'),
        site_updates=('first_site_acquired','sum'),median_pops=('pops_to_first_site','median'),
        median_refinement_fraction=('fraction_refinements_to_first_site','median')).reset_index().to_csv(out/'incumbent_acquisition_strata.csv',index=False)
    levels=pd.read_csv(out/'three_level_work_comparison.csv')
    summed=levels.groupby('method')[['regions_created','regions_popped','refinements','leaves','candidate_checks',
        'exact_evaluator_calls','semantic_evaluations','prune_cost','prune_envelope','prune_energy','prune_schedule']].sum()
    summed['median_max_depth']=levels.groupby('method').max_depth.median()
    summed['median_case_depth']=levels.groupby('method').median_depth.median()
    summed.to_csv(out/'three_level_summary.csv')
    fractions=[]
    ps=pd.read_csv(out/'perfect_static_case_work.csv')
    for numerator in ['N_envelope','N_exact','N_semantic']:
        fractions.append(dict(component=numerator,ALT_total=int(hier[numerator].sum()),PS_total=int(ps[numerator].sum()),
            PS_vs_ALT_reduction=float(1-ps[numerator].sum()/hier[numerator].sum())))
    pd.DataFrame(fractions).to_csv(out/'perfect_static_counterfactual_effect.csv',index=False)
    summary=dict(cases=480,audited_ALT_nodes=len(cert),semantic_populated_nodes=len(semantic),
        false_positive_only_nodes=int(cert.J_sem.isna().sum()),
        median_G_landmark=float(semantic.G_landmark.median()),p95_G_landmark=float(semantic.G_landmark.quantile(.95)),
        median_G_residual=float(semantic.G_residual.median()),p95_G_residual=float(semantic.G_residual.quantile(.95)),
        summed_landmark_share=float(semantic.G_landmark.sum()/semantic.total_slack.sum()),
        landmark_larger_node_fraction=float((semantic.G_landmark>semantic.G_residual).mean()),
        historical_old_gap_median=float(semantic.G_cert_old.median()),
        maximum_identity_error=float(semantic.identity_error.abs().max()),
        FP_terminal_counts={k:int(v) for k,v in totals.items()},workload=workload,
        incumbent=inc_summary,counterfactual=fractions,
        historical_outcomes_retained=['B1-O strong GO','B1-D v1 deployable gate failed'],
        diagnostic_only=True)
    write_json(out/'diagnostic_summary.json',summary)
    print(json.dumps({k:v for k,v in summary.items() if k not in ['workload','incumbent']},indent=2))


if __name__=='__main__':main()
