"""Sealed built-in source producer tests; no outside datasets or network."""
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

import pytest
from experiments.m6h_manifest_v1 import generation as g
from experiments.m6h_manifest_v1 import launcher
from experiments.m6h_manifest_v1.resources import Budget
from experiments.m6h_manifest_v1.contract import plan


def test_real_entries_hold_before_any_io():
    with patch.object(Path,'read_bytes',side_effect=AssertionError('unexpected read')):
        with pytest.raises(PermissionError):g.generate_preprocessed('/no/input')
        with pytest.raises(PermissionError):launcher.launch_real('/no/input')


def test_enclosing_budget_is_required_and_never_reset():
    with pytest.raises(ValueError):g._check_budget(None)
    budget=Budget(cpu_seconds=1,wall_seconds=1)
    with patch.object(budget,'remaining',return_value=(0,1)):
        with pytest.raises(RuntimeError):g._check_budget(budget)


def test_sealed_fixture_actual_six_files_and_all_thirty_domains(tmp_path):
    budget=Budget();origin=(budget.cpu_start,budget.wall_start)
    result=g.make_synthetic_fixture(tmp_path/'fixture',budget=budget)
    assert (budget.cpu_start,budget.wall_start)==origin
    assert result['status']=='FROZEN' and len(result['bindings'])==30
    assert result['declaration']==plan(6)
    records=[json.loads(Path(b['path']).read_bytes()) for b in result['bindings'].values()]
    assert sum(r['status']=='FAILED_INPUT' for r in records)==25
    assert {r['reason_code'] for r in records if r['status']=='FAILED_INPUT'}=={'INSUFFICIENT_CAPABLE_SITES'}
    good=[r for r in records if r['status']!='FAILED_INPUT']
    assert len(good)==5 and {r['candidate_count'] for r in good}=={8,32,128}
    for r in good:
        query=r['case_binding']['original_binding']['query']
        assert query['schedule']==dict(a='800',b='1400',D='2700')
        assert query['H_ref']==4 and query['overhead_s']=='300'
    binding=next(iter(result['bindings'].values()))
    g.verify_synthetic_fixture(**dict(manifest_path=binding['path'],manifest_sha256=binding['sha256']))
    # A cache hit must still read all six actual files and the complete grid.
    path=tmp_path/'fixture'/'inputs'/'metadata.json';path.write_bytes(b'{}')
    with pytest.raises(ValueError,match='Input bytes'):g.verify_synthetic_fixture(binding['path'],binding['sha256'])


def test_fixture_source_override_is_not_accepted(tmp_path):
    with pytest.raises(ValueError,match='own frozen repository'):
        g.make_synthetic_fixture(tmp_path/'out',repo=tmp_path)


def test_original_nullable_site_anchors_are_preserved():
    import pandas as pd
    table=pd.DataFrame(dict(site_id=['a','b'],access_node=pd.array([1,None],dtype='Int64'),
        lat=[.1,.2],lon=[.1,.2],transport_capabilities=[['charge'],[]],meal_count=[1,0]))
    rows=g._normalize_site_catalog(table)
    assert rows[0]['access_node']==1 and type(rows[0]['access_node']) is int
    assert rows[1]['access_node'] is None
    for bad in ([1.0,float('nan')],[1.5,float('nan')],[True,None]):
        changed=table.copy();changed['access_node']=bad
        with pytest.raises(ValueError,match='Raw Site anchor'):
            g._normalize_site_catalog(changed)


def test_every_real_generation_entry_holds_before_io():
    with patch.object(Path,'read_bytes',side_effect=AssertionError('unexpected read')):
        with pytest.raises(PermissionError):g._real_worker('/not-read','0'*64)
        with pytest.raises(PermissionError):
            g.produce_preprocessing_artifacts('/not-created',artifacts={},exposure_binding={},
                protocol_sha256='0'*64,repo='/not-read',compiler={},source={},budget=None,preprocessing_identity={})


def test_stage_consumption_checks_actual_bytes_and_manifest(tmp_path):
    from hashlib import sha256
    content=b'known synthetic bytes';(tmp_path/'x').write_bytes(content)
    manifest={'files':{'x':{'size_bytes':len(content),'sha256':sha256(content).hexdigest()}}}
    raw=g.canonical(manifest);(tmp_path/'artifact_manifest.json').write_bytes(raw)
    identity=dict(path=str(tmp_path),manifest_sha256=sha256(raw).hexdigest())
    parsed=g._bound_stage_manifest(identity)
    assert g._bound_stage_bytes(identity,parsed,'x')==content
    (tmp_path/'x').write_bytes(b'drift')
    with pytest.raises(ValueError,match='Consumed stage bytes'):
        g._bound_stage_bytes(identity,parsed,'x')
    (tmp_path/'artifact_manifest.json').write_bytes(b'{}')
    with pytest.raises(ValueError,match='Stage manifest changed'):
        g._bound_stage_manifest(identity)


def test_outer_real_entry_also_holds_before_io():
    with patch.object(Path,'read_bytes',side_effect=AssertionError('unexpected read')):
        with pytest.raises(PermissionError):launcher.supervise_real_round('/not-created',interpreter=None,osmium=None,freeze=None)
        with pytest.raises(PermissionError):launcher._real_launch_worker('/not-read','0'*64)


def test_invalid_graph_retains_slate_but_identity_drift_stops(tmp_path):
    from experiments.m6h_manifest_v1 import physical
    graph,rows,hierarchy,exposures=g._synthetic_sources()
    repo=Path(g.__file__).resolve().parents[2]
    kwargs=dict(graph_files=graph,site_rows=rows,hierarchy_bytes=hierarchy,exposure_registry=exposures,
                repo=repo,compiler=g.compiler_identity(),source=physical.source_identity(repo),budget=Budget())
    with patch.object(physical,'load_bound_graph',side_effect=physical.InvalidGraphInput('Invalid schema')):
        result=g._produce(tmp_path/'invalid',**kwargs)
    records=[json.loads(Path(b['path']).read_bytes()) for b in result['bindings'].values()]
    assert len(records)==30 and all(r['status']=='FAILED_INPUT' and r['reason_code']=='INVALID_INPUT' for r in records)
    with patch.object(physical,'load_bound_graph',side_effect=ValueError('Input byte identity changed')):
        with pytest.raises(ValueError,match='byte identity'):
            g._produce(tmp_path/'drift',**kwargs)


@pytest.mark.parametrize('fault',['runtime','mixed_lineage'])
def test_producer_rejects_other_runtime_or_mixed_valid_stages(tmp_path,monkeypatch,fault):
    from copy import deepcopy
    from experiments.shandong_preprocessing_v1 import phases
    order=('source','graph','inventory','sites','hierarchy')
    artifacts={p:dict(path=str(tmp_path/p),manifest_sha256='1'*64,phase=p,synthetic=False) for p in order}
    frozen=dict(toolchain_identity={'fixture':'known'},config_sha256='2'*64,
                implementation_sha256='3'*64,core_source_contract={'known':'4'*64})
    manifests={p:dict(frozen,prior={q:artifacts[q] for q in order[:order.index(p)]}) for p in order}
    manifests=deepcopy(manifests)
    if fault=='runtime':manifests['source']['toolchain_identity']={'fixture':'other'}
    else:manifests['graph']['prior']['source']['manifest_sha256']='9'*64
    monkeypatch.setattr(g,'require_root_freeze',lambda:{'recovery_admission':{'synthetic':'admission'}})  # unit only; no callable fixture CLI bypass
    monkeypatch.setattr(phases,'verify_stage',lambda *args,**kwargs:tmp_path)
    monkeypatch.setattr(g,'_bound_stage_manifest',lambda identity:manifests[identity['phase']])
    with pytest.raises(ValueError,match='preprocessing freeze|authenticated chain'):
        g.produce_preprocessing_artifacts(tmp_path/'never-created',artifacts=artifacts,exposure_binding={},
            protocol_sha256='0'*64,repo=str(tmp_path),compiler={},source={},budget=Budget(),preprocessing_identity=frozen,recovery_admission={'synthetic':'admission'})
    assert not (tmp_path/'never-created').exists()

def test_hiroute_package_sources_are_discovered_and_recorded_dynamically():
    from experiments.m6h_manifest_v1 import physical
    repo=Path(g.__file__).resolve().parents[2]
    sources=physical._hiroute_source_map(repo)
    assert sources
    assert all(name.startswith('src/hiroute/') and len(value)==64 for name,value in sources.items())
    identity=physical.source_identity(repo)
    assert identity['hiroute_source_entries']==len(sources)
    assert identity['hiroute_source_sha256']==physical.base.digest(sources)
    assert identity['closure']['src/graph/raw_way_policy.py']==identity['raw_way_policy_sha256']
    assert 'historical_production_src_sha256' not in identity


def test_m6_source_identity_keeps_current_package_and_behavior_contract():
    from experiments.m6h_manifest_v1 import physical
    repo=Path(g.__file__).resolve().parents[2]
    identity=physical.source_identity(repo)
    assert identity['production_source_sha256']==physical.base.digest({n:h for n,h in identity['closure'].items()
        if n.startswith('src/') and not n.startswith(('src/hiroute.egg-info/','src/hiroute/'))})
    assert identity['raw_way_policy_sha256']==identity['closure']['src/graph/raw_way_policy.py']
    assert identity['hiroute_source_sha256']==physical.base.digest(physical._hiroute_source_map(repo))
    assert not hasattr(physical,'PRODUCTION_SRC_SHA256')
    assert not hasattr(physical,'APPROVED_RAW_WAY_POLICY_SHA256')
