"""Directed boundary and frozen-search contracts for B1-D2."""
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from hierarchy4r.boundary import (directed_boundary_pairs,boundary_min,depth_labels,
    subtree_ends,BoundaryIndex,BOUNDARY_ABS,BOUNDARY_REL)
from hierarchy4r.deploy import cost_bound
from hierarchy4r.deploy_search import DeployIndex,deploy_search
from stopplan4r.evaluation import plan_key
from stopplan4r.models import ScheduledStop
from test_hierarchy4r_domain import fixture

LABELS=np.array([1,1,2,2])
SOURCE=np.array([0,2,1,3]);TARGET=np.array([2,1,0,2])


def pairs(source=SOURCE,target=TARGET):
    a,b=directed_boundary_pairs(LABELS,source,target)
    return {(int(x//4),int(x%4)) for x in a},{(int(x//4),int(x%4)) for x in b}


def test_ingress():assert pairs()[0]=={(2,2),(1,1)}
def test_egress():assert pairs()[1]=={(1,0),(2,2)}
def test_directed_asymmetry():assert pairs()[0]!=pairs()[1]
def test_both_boundaries():assert pairs()[0]&pairs()[1]=={(2,2)}
def test_no_ingress():assert pairs(np.array([0]),np.array([2]))[0]=={(2,2)}
def test_no_egress():assert pairs(np.array([0]),np.array([2]))[1]=={(1,0)}


@pytest.mark.parametrize('kind',['origin','destination'])
def test_inside_short_circuit(kind):
    class NoRead:
        def __getitem__(self,key):raise AssertionError('Inside Region must not scan')
    assert boundary_min(np.array([0,1]),NoRead(),True)==(0.,0.,0)


@pytest.mark.parametrize('values',[[],[np.inf],[np.inf,np.nan]])
def test_empty_unreachable_conservative(values):
    assert boundary_min(np.arange(len(values)),np.array(values),False)==(0.,0.,len(values))


def test_hand_directed_shortest_paths_and_static_minimum():
    # 0 -> 1 -> 2 -> 3, and 3 -> 1; cell {1,2}; inbound 1, outbound 2.
    labels=np.array([0,1,1,2]);src=np.array([0,1,2,3]);dst=np.array([1,2,3,1])
    i,o=directed_boundary_pairs(labels,src,dst)
    assert list(i[(i//4)==1]%4)==[1] and list(o[(o//4)==1]%4)==[2]
    forward=np.array([0,3,7,12.]);reverse=np.array([12,9,5,0.])
    assert boundary_min(np.array([1]),forward,False)[1]<=forward[[1,2]].min()
    assert boundary_min(np.array([2]),reverse,False)[1]<=reverse[[1,2]].min()


def toy_index(monkeypatch,leaf=False):
    index=BoundaryIndex.__new__(BoundaryIndex)
    index.cells=np.array([0,1,2]);index.ends=np.array([2,1,2]);index.offsets=np.array([[0,0,0,0],[0,1,0,1],[1,1,1,1]])
    index.ingress=np.array([1]);index.egress=np.array([1]);index.bind(np.array([0,100,200.]),np.array([200,100,0.]))
    index.site_ids_read=index.evaluator_calls=index.oracle_reads=index.internal_scans=0
    index.children=np.full((3,2),-1);index.counts=np.ones((3,3),int)
    index.arrays=[[[np.zeros(3) for _ in range(8)] for _ in range(2)] for _ in range(2)]
    def bound(self,r,b,p,trip,ev,sched,pc,parent):
        return dict(region=r,bucket=['Ccap','S0cap','SCcap'][b],internal=not leaf,
            site_ids_read=0,evaluator_calls=0,oracle_table_reads=0,**cost_bound((1.,2.,0.,0.),b,trip,ev,sched,pc,parent))
    monkeypatch.setattr(DeployIndex,'bound',bound)
    index.points(0,2)
    return index


@pytest.mark.parametrize('bucket',[0,1,2])
def test_combination_admissible_and_energy_unchanged(monkeypatch,bucket):
    sched=None if bucket==0 else ScheduledStop(0,1000)
    site,_,plans,args=fixture(8 if bucket!=1 else 45.6,sched,charger=bucket!=1)
    trip,_,travel,ev,curve,schedule,pc=args;index=toy_index(monkeypatch)
    r=index.bound(1,bucket,None,trip,ev,schedule,pc,-np.inf)
    assert r['ALT_tm']<=r['tm']<=100 and r['ALT_tp']<=r['tp']<=100
    assert r['dm']==r['dp']==0
    assert r['lower']<=plans[site.site_id].generalized_cost_s
    assert (r['ingress_reads'],r['egress_reads'])==(1,1)


def test_parent_monotone(monkeypatch):
    _,_,_,args=fixture();trip,_,_,ev,_,sched,pc=args;idx=toy_index(monkeypatch)
    r=idx.bound(1,0,None,trip,ev,sched,pc,2000.)
    assert r['lower']==2000 and r['raw_safe_cost']<2000


def test_numerical_equality_boundary():
    raw,safe,reads=boundary_min(np.array([0]),np.array([100.]),False)
    assert raw==100 and safe<100 and reads==1
    assert safe==np.nextafter(100-(BOUNDARY_ABS+BOUNDARY_REL*100),-np.inf)


def test_no_site_access_and_per_case_boundary_cache(monkeypatch):
    idx=toy_index(monkeypatch);_,_,_,args=fixture();trip,_,_,ev,_,sched,pc=args
    idx.leaf_ids=lambda *args:pytest.fail('Site access in internal bound')
    a=idx.bound(1,0,None,trip,ev,sched,pc,-np.inf)
    b=idx.bound(1,0,None,trip,ev,sched,pc,-np.inf)
    for k in ['site_ids_read_for_bound','site_evaluator_calls_for_bound','oracle_per_site_reads','additional_sssp_calls']:
        assert a[k]==b[k]==0
    assert a['ingress_reads']+a['egress_reads']==2 and b['ingress_reads']+b['egress_reads']==0
    idx.points(0,2)
    assert idx.bound(1,0,None,trip,ev,sched,pc,-np.inf)['ingress_reads']==1


def test_deterministic_serialization(tmp_path):
    a=directed_boundary_pairs(LABELS,SOURCE,TARGET)
    b=directed_boundary_pairs(LABELS,SOURCE[::-1],TARGET[::-1])
    for name,arrays in [('a',a),('b',b)]:
        pd.DataFrame([dict(ingress=arrays[0],egress=arrays[1])]).to_parquet(tmp_path/f'{name}.parquet',index=False)
    assert (tmp_path/'a.parquet').read_bytes()==(tmp_path/'b.parquet').read_bytes()


def test_completeness_exhaustive_directed_cross_edges():
    src,dst=np.indices((4,4));i,o=pairs(src.ravel(),dst.ravel())
    assert i==o=={(1,0),(1,1),(2,2),(2,3)}


def test_depth_cells_and_membership_interval():
    regions=[dict(parent=-1,children=[1,2],depth=0),dict(parent=0,children=[],depth=1),dict(parent=0,children=[],depth=1)]
    assert list(subtree_ends(regions))==[2,1,2]
    assert list(depth_labels(LABELS,regions,0))==[0]*4
    assert list(depth_labels(LABELS,regions,1))==list(LABELS)


def test_frozen_search_full_key_preserved(monkeypatch):
    site,legacy,plans,args=fixture(8);trip,_,travel,ev,curve,sched,pc=args
    idx=toy_index(monkeypatch,leaf=True)
    idx.leaf_ids=lambda *args:[site.site_id]
    result,_,_,_,_=deploy_search(idx,trip,{site.site_id:site},travel,ev,curve,sched,pc)
    assert plan_key(result)==plan_key(legacy)


def test_frozen_components_and_boundary_identity():
    root=Path(__file__).resolve().parents[1];out=root/'results/milestone_4r_b1d2'
    before=json.loads((out/'preservation_before.json').read_text())
    # Verify all frozen source/config files and key static identities; full input verification is also an experiment gate.
    selected={p:h for p,h in before['files'].items() if p.startswith(('src/','configs/')) or p.endswith(('hierarchy.json','landmark_manifest.json'))}
    assert selected
    for p,h in selected.items():assert hashlib.sha256((root/p).read_bytes()).hexdigest()==h,p
    m=json.loads((out/'boundary_manifest.json').read_text())
    for p,h in m['extraction_code_sha256'].items():assert hashlib.sha256((root/p).read_bytes()).hexdigest()==h,p
