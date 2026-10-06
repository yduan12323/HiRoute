"""Regression checks on completed B1-D evidence; no online oracle access."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from _common import sha256

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/milestone_4r_b1d'


def test_deploy_preserves_all_protected_b1_evidence():
    manifest=json.loads((OUT/'preservation_before.json').read_text())
    for key in ['files','source_sha256']:
        for path,digest in manifest[key].items():
            assert sha256(ROOT/path)==digest,path
    frozen=json.loads((OUT/'query_preregistration.json').read_text())
    for path,digest in frozen['source_sha256'].items():
        assert sha256(ROOT/path)==digest,path


def test_all_static_buckets_and_root_to_leaf_paths_preserved():
    audit=json.loads((OUT/'static_audit.json').read_text())
    assert audit['sites']==60498 and audit['regions']==2047 and audit['violations']==0
    assert audit['full_array_hashes_verified']==32 and audit['all_site_root_to_leaf_paths_preserved']
    assert not pd.read_csv(OUT/'D1_static_paths.csv').violations.any()
    coverage=pd.read_csv(OUT/'D1_coverage.csv')
    assert len(coverage)==480 and (coverage.covered==coverage.semantic_actions).all()


def test_real_shortest_distance_is_below_fastest_actual_length():
    audit=pd.read_csv(OUT/'distance_vs_fastest_length.csv')
    assert len(audit)==60 and audit.checked.gt(0).all() and not audit.violations.any()
    assert set(audit.direction)=={'inbound','outbound'}


def test_all_deploy_correctness_and_full_tie_preservation():
    gates=json.loads((OUT/'correctness_gates.json').read_text())
    assert gates['cases']==480 and gates['passed']
    assert all(n==0 for n in gates['violations'].values())
    ref=pd.read_csv(OUT/'D4_preservation.csv')
    assert len(ref)==480 and ref.passed.all()
    audit=pd.read_parquet(OUT/'visited_region_audit.parquet')
    assert len(audit)>480 and not audit[['D2_violation','D3_violation']].any().any()
    assert not audit[['site_ids_read','evaluator_calls','oracle_table_reads']].any().any()
    assert audit.landmark_count.eq(8).all() and audit.summary_rows_read.eq(16).all()
    assert (audit.lower>=audit.raw_safe_cost).all()
    populated=audit[audit.semantic_count.gt(0)]
    assert (populated.lower<=populated.semantic_minimum+2e-6).all()


def test_exact_work_includes_all_false_positives_and_na_cases():
    work=pd.read_parquet(OUT/'work.parquet')
    leaf=pd.read_csv(OUT/'leaf_false_positives.csv')
    assert (work.deploy_exact_site_evaluations==work.deploy_semantic_site_evaluations+work.false_positive_count).all()
    total=leaf.groupby('case_id').candidates.sum().reindex(work.case_id,fill_value=0)
    assert np.array_equal(total,work.deploy_exact_site_evaluations)
    zero=work[work.semantic_flat_sites.eq(0)]
    assert len(zero)==93 and zero.reduction.isna().all()
    assert zero.metric_status.eq('no_semantic_site_pruning_opportunity').all()
    stats=json.loads((OUT/'analysis.json').read_text())
    assert np.isclose(stats['micro_workload_reduction'],1-work.deploy_exact_site_evaluations.sum()/work.semantic_flat_sites.sum())
    assert stats['metric_defined_cases']==387


def test_clean_avoided_timing_partition_matches_actual_search():
    timing=pd.read_csv(OUT/'avoided_timing.csv');work=pd.read_csv(OUT/'work.csv')
    assert len(timing)==480 and timing.avoided_site_seconds.ge(0).all()
    assert np.array_equal(timing.avoided_candidates+work.deploy_exact_site_evaluations,work.flat_static_candidates)
    assert np.array_equal(timing.avoided_semantic+work.deploy_semantic_site_evaluations,work.semantic_flat_sites)
