import hashlib
import json
from dataclasses import replace
from pathlib import Path
import numpy as np
import pandas as pd
from hierarchy4r.deploy_search import deploy_search
from stopplan4r.evaluation import plan_key
from test_hierarchy4r_boundary import toy_index
from test_hierarchy4r_domain import fixture

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/milestone_4r_b1d2'


def test_equal_cost_site_ties_keep_full_deterministic_key(monkeypatch):
    a,_,_,args=fixture(8);b=replace(a,site_id='4r:node/2',osm_id=2)
    trip,_,travel,ev,curve,schedule,config=args
    results=[]
    for order in [[a.site_id,b.site_id],[b.site_id,a.site_id]]:
        idx=toy_index(monkeypatch,leaf=True);idx.leaf_ids=lambda *unused:order
        result,*_=deploy_search(idx,trip,{a.site_id:a,b.site_id:b},travel,ev,curve,schedule,config)
        results.append(result)
    assert plan_key(results[0])==plan_key(results[1]) and results[0].stops[0].site_id==a.site_id


def test_every_case_exact_and_all_bound_gates():
    f=pd.read_csv(OUT/'f5_exact_preservation.csv');a=pd.read_parquet(OUT/'alt_ba_ps_bound_audit.parquet')
    assert len(f)==480 and f.full_key_equal.all() and f.objective_equal.all() and f.static_action_coverage_preserved.all()
    assert not a[['F2_violations','F3_violations','F4_violations','F6_violations']].any().any()
    assert (a.L_ALT<=a.L_BA+2e-6).all() and (a.L_BA<=a.L_PS+2e-6).all()
    sem=a[a.J_sem.notna()];assert (sem.L_BA<=sem.J_sem+2e-6).all()
    assert a.loc[a.J_sem.isna(),'H_bound'].isna().all()


def test_boundary_reads_and_no_hidden_scans_reconcile():
    a=pd.read_parquet(OUT/'alt_ba_ps_bound_audit.parquet');w=pd.read_csv(OUT/'b1d2_case_work.csv')
    for field in ['ingress_reads','egress_reads']:
        actual=a.groupby('case_id')[field].sum().reindex(w.case_id)
        np.testing.assert_array_equal(actual,w[field])
    assert not a[['site_ids_read_for_bound','site_evaluator_calls_for_bound','oracle_per_site_reads','additional_sssp_calls']].any().any()
    assert a.loc[a.boundary_cache_hit,['ingress_reads','egress_reads']].eq(0).all().all()


def test_envelope_migration_exact_reconciliation():
    m=pd.read_csv(OUT/'envelope_pruning_migration.csv');p=pd.read_parquet(OUT/'envelope_pruning_migration_witnesses.parquet')
    assert (m.former_ALT_FP1_avoided+m.former_ALT_FP1_retained==m.ALT_leaf_envelope_rejects).all()
    assert (m.former_ALT_FP1_retained+m.new_BA_FP1==m.BA_leaf_envelope_rejects).all()
    assert len(p)==m.former_ALT_FP1_avoided.sum() and not p.duplicated(['case_id','site_id']).any()
    assert (p.BA_terminal_depth<=p.ALT_depth).all()


def test_boundary_artifact_freeze_and_all_region_coverage():
    m=json.loads((OUT/'boundary_manifest.json').read_text())
    assert m['regions']==2047 and m['F1_violations']==0 and m['deterministic_reconstruction']
    for p,h in m['artifact_sha256'].items():assert hashlib.sha256((OUT/p).read_bytes()).hexdigest()==h,p
    f=pd.read_parquet(OUT/'region_boundaries.parquet')
    assert len(f)==2047 and not f.region.duplicated().any()
    assert sum(map(len,f.ingress))==m['ingress_references']
    assert sum(map(len,f.egress))==m['egress_references']
