import json
from pathlib import Path
import numpy as np
import pandas as pd
from hierarchy4r.diagnosis import AUDIT_TOL,CATEGORIES

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/milestone_4r_b1e'


def test_all_cases_fair_baseline_and_exact_counterfactual():
    flat=pd.read_parquet(OUT/'deployable_flat_work.parquet')
    hier=pd.read_parquet(OUT/'deployable_hier_work.parquet')
    ps=pd.read_csv(OUT/'perfect_static_case_work.csv')
    gates=pd.read_csv(OUT/'E1_E5_audit.csv')
    assert len(flat)==len(hier)==len(ps)==len(gates)==480
    assert not gates[['E1','E2','E3','E4','E5']].any().any()
    assert ps.optimum_match.all() and ps.diagnostic_only.all()
    assert flat.N_region.eq(0).all() and flat.N_bound.eq(0).all()
    assert (flat.N_envelope>=flat.N_exact).all() and (flat.N_exact>=flat.N_semantic).all()
    assert (hier.N_envelope>=hier.N_exact).all() and (hier.N_exact>=hier.N_semantic).all()
    assert flat.T_envelope.isna().all() and hier.T_exact.isna().all()


def test_complete_certificate_identity_and_historical_gap_unchanged():
    cert=pd.read_parquet(OUT/'certificate_decomposition.parquet')
    old=pd.read_parquet(ROOT/'results/milestone_4r_b1d/visited_region_audit.parquet')
    assert len(cert)==len(old)==191849
    merged=cert.merge(old[['case_id','region','bucket','lower','G_cert']],on=['case_id','region','bucket'],validate='one_to_one')
    np.testing.assert_allclose(merged.G_cert_old,merged.G_cert,rtol=0,atol=0,equal_nan=True)
    np.testing.assert_allclose(merged.L_ALT,merged.lower,rtol=0,atol=0)
    assert (cert.L_ALT<=cert.L_PS+AUDIT_TOL).all()
    sem=cert[cert.J_sem.notna()]
    assert len(sem)==52405
    assert (sem.L_PS<=sem.J_sem+AUDIT_TOL).all()
    assert sem.identity_error.abs().le(AUDIT_TOL).all()
    assert cert.loc[cert.J_sem.isna(),'G_residual'].isna().all()


def test_all_paid_checks_reconcile_exactly_by_terminal_category():
    f=pd.read_parquet(OUT/'leaf_candidate_classification.parquet')
    h=pd.read_csv(OUT/'deployable_hier_work.csv').set_index('case_id')
    assert len(f)==706117 and set(f.category)<=set(CATEGORIES)
    assert not f.duplicated(['case_id','site_id']).any()
    counts=f.groupby('case_id').size().reindex(h.index,fill_value=0)
    tp=f[f.category.eq('TP')].groupby('case_id').size().reindex(h.index,fill_value=0)
    non_envelope=f[f.category.ne('FP1')].groupby('case_id').size().reindex(h.index,fill_value=0)
    assert np.array_equal(counts,h.N_envelope) and np.array_equal(tp,h.N_semantic)
    assert np.array_equal(non_envelope,h.N_exact)


def test_incumbent_diagnosis_retains_missing_times_and_zero_seed():
    inc=pd.read_csv(OUT/'incumbent_acquisition.csv')
    assert len(inc)==480 and inc.time_to_first_site_seconds.isna().all()
    assert inc.loc[inc.zero_initialized,'first_finite_U_pops'].eq(0).all()
    assert inc.loc[~inc.zero_initialized,'first_site_acquired'].all()
    found=inc[inc.first_site_acquired]
    assert found.fraction_pops_to_first_site.between(0,1).all()
    assert found.fraction_refinements_to_first_site.between(0,1).all()
    assert (found.first_site_cost>=found.final_optimum_cost-1e-7).all()
