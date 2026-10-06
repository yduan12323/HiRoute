import json
from pathlib import Path
import numpy as np
import pandas as pd
from _common import sha256
from hierarchy4r.tree import validate_tree, tree_hash

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/milestone_4r_b1'


def test_frozen_hierarchy_exact_static_coverage():
    tree=json.loads((OUT/'hierarchy.json').read_text())
    manifest=json.loads((OUT/'hierarchy_preregistration.json').read_text())
    assert validate_tree(tree)
    assert tree_hash(tree)==manifest['hierarchy_sha256']
    sites=pd.read_parquet(ROOT/'results/milestone_4r/stop_sites.parquet')
    attached=sites[sites.attachment_status.eq('attached') & sites.access_node.notna()]
    assert set(tree['site_ids'])==set(attached.site_id)
    assert tree['capacity']==64 and tree['branch_factor']==2
    for suffix in ['cells.bin','regions.csv']:
        assert sha256(OUT/'hierarchy_build'/f'primary_{suffix}')==sha256(OUT/'hierarchy_build'/f'rebuild_{suffix}')


def test_h0_all_cases_and_disjoint_roles():
    h0=json.loads((OUT/'h0_summary.json').read_text())
    assert h0['passed'] and h0['cases_evaluated']==480 and h0['cost_mismatches']==0
    for path in sorted((OUT/'flat_reference').glob('*.parquet')):
        f=pd.read_parquet(path)
        assert f.site_id.is_unique
        assert set(f.role)<={'','C','S','CS'}
        assert f.loc[f.role.ne(''),'feasible'].all()
        assert (f.loc[f.role.isin(['C','CS']),'charge_kwh']>1e-8).all()
        assert (f.loc[f.role.eq('S'),'charge_kwh']<=1e-8).all()


def test_archived_blocker_and_accepted_hashes_unchanged():
    before=json.loads((OUT/'resume_preservation_before.json').read_text())
    for p,h in before['archived_hashes'].items():assert sha256(ROOT/p)==h
    checkpoint=json.loads((OUT/'preservation_checkpoint.json').read_text())
    for p,r in checkpoint['files'].items():assert sha256(ROOT/p)==r['sha256']


def test_native_topology_disconnected_and_coattached_early_leaf(tmp_path):
    import subprocess
    executable=OUT/'hierarchy_build/bisection'
    edges=np.array([[0,1],[1,2],[2,3],[4,5],[5,6],[6,7]],dtype=np.int32)
    access=np.array([0,2,2,2,4,7],dtype=np.int32)
    for suffix,es in [('a',edges),('b',edges[::-1])]:
        with (tmp_path/f'{suffix}.bin').open('wb') as f:
            np.array([8,len(edges),len(access)],dtype=np.int64).tofile(f)
            es.tofile(f);access.tofile(f)
        subprocess.run([str(executable),str(tmp_path/f'{suffix}.bin'),str(tmp_path/f'{suffix}.cells'),
                        str(tmp_path/f'{suffix}.csv'),'2'],check=True)
    assert (tmp_path/'a.cells').read_bytes()==(tmp_path/'b.cells').read_bytes()
    assert (tmp_path/'a.csv').read_bytes()==(tmp_path/'b.csv').read_bytes()
    cells=np.fromfile(tmp_path/'a.cells',dtype=np.int32)
    regions=pd.read_csv(tmp_path/'a.csv')
    assert regions.iloc[0].sites==len(access)
    assert regions[regions.reason.eq(1)].sites.tolist()==[3]
    assert len(set(cells[access[1:4]]))==1


def test_semantic_leaf_membership_exact():
    tree=json.loads((OUT/'hierarchy.json').read_text())
    ids=set(tree['site_ids'])
    members=pd.read_parquet(OUT/'site_membership.parquet')
    assert members.site_id.is_unique and set(members.site_id)==ids
    for r in members.itertuples():
        assert not tree['regions'][r.leaf_region]['children']
    # Role filtering never edits any of these serialized static fields.
    manifest=json.loads((OUT/'hierarchy_preregistration.json').read_text())
    assert sha256(OUT/'hierarchy.json')==manifest['hierarchy_sha256']


def test_complete_primary_gates_and_all_recorded_bounds():
    gate=json.loads((OUT/'primary_gates.json').read_text())
    assert gate['passed'] and gate['cases']==480
    for name in ['H0','H1','H2','H3','H4','H5']:assert gate[name]
    compare=pd.read_csv(OUT/'H2_all_comparisons.csv')
    primary=compare[compare.epsilon.eq(0)]
    assert len(primary)==480 and primary.passed.all() and primary.identity_match.all()
    total=0
    for path in sorted((OUT/'oracle_epsilon_0').glob('views_*.parquet')):
        f=pd.read_parquet(path)
        if not len(f):continue
        total+=len(f)
        assert not f[['H1_violation','H3_violation','perturbation_violation']].any().any()
        assert (f.safe_lower<=f.region_optimum+2e-6).all()
        certified=f[f.certified]
        assert (certified.max_concrete_gap<=certified.gap_bound+2e-6).all()
    assert total>0
    h4=pd.read_csv(OUT/'H4_coverage.csv');assert not h4[['lost','duplicates']].any().any()
    h5=pd.read_csv(OUT/'H5_stability.csv');assert not h5.mutated.any()
    diameter=pd.read_csv(OUT/'diameter_populated/directed_time_theorem_checks.csv')
    assert len(diameter)>0 and diameter.passed.all()
