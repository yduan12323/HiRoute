"""Exposed tiny fixtures only. No real map, holdout OD, compiler or server."""
from fractions import Fraction as F
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from experiments.m6h_manifest_v1 import reference as ref

spec = importlib.util.spec_from_file_location('exposed_ref_fixture', Path(__file__).with_name('test_reference5_real_adapter.py'))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


def seed(h=9):
    return dict(max_depth=h, key_bytes=json.dumps(['9','3',2,[['A','C'],['B','S']]]),
        witness_bytes=json.dumps(dict(pi=[['A','C'],['B','S']], events=[
            dict(site='A',effect='C',arrival_energy='1',departure_energy='4'),
            dict(site='B',effect='S',arrival_energy='4',departure_energy='4')])))


def test_depth_uses_seed_not_fixture_h4_or_cap():
    query = fixture.query(); query['H_ref'] = 4
    assert ref.reference_query(query,seed())['H_ref'] == 9
    for bad in (4,0,True,-1,None):
        with pytest.raises(ValueError):ref.reference_query(query,seed(bad))


def service_case():
    # One service only makes deep enumeration tiny, yet its optimum needs H=1.
    p=fixture.payload();p['sites']=[dict(site_id='B',anchor_id='x',effects=['S'])]
    q=fixture.query();q.update(initial_energy_kwh=10, H_ref=4)
    s=dict(max_depth=5,key_bytes=json.dumps(['5','0',1,[['B','S']]]),
        witness_bytes=json.dumps(dict(pi=[['B','S']],events=[
            dict(site='o',effect='initial',arrival_energy='10',departure_energy='10'),
            dict(site='x',effect='D',arrival_energy='10',departure_energy='9'),
            dict(site='B',effect='S',arrival_energy='9',departure_energy='9'),
            dict(site='z',effect='D',arrival_energy='9',departure_energy='8')])))
    # The direct route costs 20 energy and is infeasible; service path is valid.
    return q, s, fixture.load(p)


def test_genuine_independent_full_depth_and_fresh_attained_replay(monkeypatch):
    q, s, table = service_case()
    seen = []
    replay = ref.replay_real_witness
    def checked_replay(query, fresh, sequence, charges):
        seen.append(fresh)
        return replay(query, fresh, sequence, charges)
    monkeypatch.setattr(ref, 'replay_real_witness', checked_replay)
    result=ref.solve_independent(q,s,table)
    assert result['status']=='SUCCESS' and result['independent_exact']
    assert result['canonical_outcome']==dict(status='attained_optimum',lex_key=['5','0',1,[['B','S']]])
    assert result['witness_replayed'] is True
    assert len(seen) == 2 and all(fresh is not table for fresh in seen)
    assert seen[0] is not seen[1] and all(fresh.raw_bytes == table.raw_bytes for fresh in seen)
    certificate = result['depth_certificate']
    assert certificate == dict(schema='hiroute.adapter_seed_depth_bound.v1',
        issuer='experiments.m6h_manifest_v1.reference', backend_supplied=False,
        seed_independently_replayed=True, seed_objective='5',
        per_stop_objective_lower_bound='1', H_ref=5,
        first_excluded_depth=6, first_excluded_lower_bound='6',
        excluded_depths_strictly_worse_than_seed=True, table_sha256=table.payload_sha256,
        backend_enumeration='unchanged exhaustive physical sequence enumeration through H_ref',
        incumbent_pruning=False)


def test_supported_backend_api_and_unchanged_enumeration(monkeypatch):
    from validation.reference5.real_solver import solve_real_case
    q, s, table = service_case()
    expected = solve_real_case(ref.reference_query(q, s), table, keep_evidence=False)
    observed = []
    # Exact backend signature: accepting **kwargs would hide the original bug.
    def backend(query, fresh, *, keep_evidence=True, regime_limit=None):
        assert query['H_ref'] == 5 and keep_evidence is False and regime_limit is None
        solved = solve_real_case(query, fresh, keep_evidence=keep_evidence, regime_limit=regime_limit)
        observed.append(solved)
        return solved
    monkeypatch.setattr(ref, 'solve_real_case', backend)
    result = ref.solve_independent(q, s, table)
    assert observed[0]['result'] == expected['result']
    assert observed[0]['preflight'] == expected['preflight']
    assert observed[0]['all_regimes_certified'] == expected['all_regimes_certified'] is True
    assert 'depth_certificate' not in observed[0]['preflight']
    assert result['canonical_outcome'] == ref.canonical_outcome(expected['result'])


def test_explicit_backend_regime_limit_remains_unknown(monkeypatch):
    from validation.reference5.real_solver import solve_real_case
    q, s, table = service_case()
    def limited(query, fresh, *, keep_evidence=True, regime_limit=None):
        return solve_real_case(query, fresh, keep_evidence=keep_evidence, regime_limit=0)
    monkeypatch.setattr(ref, 'solve_real_case', limited)
    result = ref.solve_independent(q, s, table)
    assert result['status'] == 'UNKNOWN' and result['reference_status'] == 'unresolved'
    assert result['independent_exact'] is False and result['canonical_outcome'] is None
    assert 'depth_certificate' not in result


@pytest.mark.parametrize('field,value', [('overhead_s', 0), ('lambda_stop_s', -1)])
def test_seed_depth_bound_rejects_invalid_stop_costs(field, value):
    q, s, table = service_case()
    q[field] = value
    with pytest.raises(ValueError):
        ref.solve_independent(q, s, table)


@pytest.mark.parametrize('h', [4, 6, True, -1])
def test_adapter_bound_independently_checks_replayed_horizon(h):
    q, s, table = service_case()
    replay = ref.replay_real_witness(dict(q, H_ref=5), table, [('B', 'S')], [])
    with pytest.raises(ValueError):
        ref.seed_depth_certificate(dict(q, H_ref=h), replay, table)


@pytest.mark.parametrize('preflight', [None, {}, {'table_sha256': '0'*64,
    'scope': 'exact_physical_exclusions_before_continuous_regime_expansion'}])
def test_exact_outcome_requires_matching_backend_preflight(monkeypatch, preflight):
    q, s, table = service_case()
    monkeypatch.setattr(ref, 'solve_real_case', lambda *a, **kw: dict(H_ref=5,
        all_regimes_certified=True, preflight=preflight,
        result=dict(status='primary_unattained', primary_infimum=F(4))))
    with pytest.raises(ValueError, match='preflight'):
        ref.solve_independent(q, s, table)


@pytest.mark.parametrize('status', ['primary_unattained', 'secondary_unattained'])
def test_certified_unattainment_keeps_exact_components_and_adapter_provenance(monkeypatch, status):
    q, s, table = service_case()
    outcome = (dict(status=status, primary_infimum=F(4)) if status == 'primary_unattained'
               else dict(status=status, J=F(4), secondary_infimum=F(1, 3)))
    monkeypatch.setattr(ref, 'solve_real_case', lambda *a, **kw: dict(H_ref=5,
        all_regimes_certified=True, result=outcome, preflight=dict(
            table_sha256=table.payload_sha256,
            scope='exact_physical_exclusions_before_continuous_regime_expansion')))
    result = ref.solve_independent(q, s, table)
    assert result['canonical_outcome'] == ref.canonical_outcome(outcome)
    assert result['witness'] is None and result['witness_replayed'] is False
    assert result['depth_certificate']['backend_supplied'] is False


def test_seed_full_key_and_event_mismatch_fails_closed():
    s=seed();s['key_bytes']=json.dumps(['9','4',2,[['A','C'],['B','S']]])
    with pytest.raises(ValueError,match='full key'):
        ref.solve_independent(fixture.query(),s,fixture.load(fixture.payload()))
    s=seed();w=json.loads(s['witness_bytes']);w['events'][0]['site']='B';s['witness_bytes']=json.dumps(w)
    with pytest.raises(ValueError,match='events'):
        ref.solve_independent(fixture.query(),s,fixture.load(fixture.payload()))


def test_unknown_non_action_event_is_not_silently_ignored():
    s=seed();w=json.loads(s['witness_bytes']);w['events'].insert(0,dict(site='o',effect='unknown'))
    s['witness_bytes']=json.dumps(w)
    with pytest.raises(ValueError,match='unknown event'):
        ref.solve_independent(fixture.query(),s,fixture.load(fixture.payload()))


def test_unattainment_preserves_proper_components():
    assert ref.canonical_outcome(dict(status='primary_unattained',primary_infimum=F(1,3))) == dict(status='primary_unattained',primary_infimum='1/3')
    assert ref.canonical_outcome(dict(status='secondary_unattained',J=F(2),secondary_infimum=F(1,3))) == dict(status='secondary_unattained',J='2',secondary_infimum='1/3')
    assert ref.canonical_outcome(dict(status='unresolved')) is None


def test_materialization_preserves_shared_anchor_and_selected_constants():
    original=fixture.load(fixture.payload())
    def leg(a,b):
        v=original.pair(a,b)
        return SimpleNamespace(source_anchor=a,target_anchor=b,reachable=v.reachable,time=v.time,
            actual_length=v.actual_length,label_direction=v.label_direction,time_hex=v.time_hex,length_hex=v.length_hex)
    provider=SimpleNamespace(source_sha256={'router':'a'*64},leg=leg)
    table=ref.materialize_table(fixture.query(),original.sites,provider,source_sha256={'graph':'b'*64},selection_sha256='c'*64,hierarchy_sha256='d'*64)
    assert table.anchors==('o','x','z') and len(table.sites)==2
    assert table.pair('o','z').actual_length==20
    assert table.sites['A'].anchor_id==table.sites['B'].anchor_id
    provider.leg=lambda a,b:SimpleNamespace(**dict(vars(leg(a,b)),time=F(0),time_hex=0.0.hex()))
    with pytest.raises(ref.ReferenceUnsupported,match='zero totals'):
        ref.materialize_table(fixture.query(),original.sites,provider,source_sha256={'graph':'b'*64},selection_sha256='c'*64,hierarchy_sha256='d'*64)


def test_timeout_unwinds_reference_exception_catch_and_restores_timers(monkeypatch):
    import signal
    monkeypatch.setattr(ref,'BUDGET_SECONDS',0.01)
    with pytest.raises(ref.ReferenceBudgetExceeded):
        with ref.bounded_reference():
            while True:pass
    assert signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0)
    assert signal.getitimer(signal.ITIMER_PROF)==(0.0,0.0)


def test_physical_entry_is_still_held(tmp_path):
    with pytest.raises(PermissionError,match='held'):
        ref.run_reference({},'none',{},tmp_path/'out')
    assert not (tmp_path/'out').exists()


@pytest.mark.parametrize('outcome',[
    dict(status='attained_optimum',lex_key=['1','0',1,[['A','C']]]),
    dict(status='primary_unattained',primary_infimum='1/3'),
    dict(status='secondary_unattained',J='1',secondary_infimum='0'),
])
def test_outcome_validator(outcome):
    assert ref.validate_outcome(outcome,9)==outcome
    bad=dict(outcome,extra=True)
    with pytest.raises(ValueError):ref.validate_outcome(bad,9)


@pytest.mark.parametrize('key',[
    ['1','0',True,[['A','C']]], ['1','0',10,[['A','C']]*10],
    ['1','0',1,[['A','Q']]], ['1.0','0',1,[['A','C']]],
    ['1','0',1,[]], ['1','-1',1,[['A','C']]],
])
def test_outcome_full_key_fail_closed(key):
    with pytest.raises(ValueError):ref.validate_outcome(dict(status='attained_optimum',lex_key=key),9)


@pytest.mark.parametrize('status',['invalid_input','invented_status'])
def test_reference_input_and_unknown_status_are_integrity_failures(monkeypatch,status):
    monkeypatch.setattr(ref,'solve_real_case',lambda *a,**kw:dict(result=dict(status=status,reason='test'),H_ref=9))
    with pytest.raises(ValueError):ref.solve_independent(fixture.query(),seed(),fixture.load(fixture.payload()))


def test_uncertified_reference_is_unknown_not_match(monkeypatch):
    monkeypatch.setattr(ref,'solve_real_case',lambda *a,**kw:dict(result=dict(status='unresolved'),H_ref=9,all_regimes_certified=False))
    result=ref.solve_independent(fixture.query(),seed(),fixture.load(fixture.payload()))
    assert result['status']=='UNKNOWN' and result['independent_exact'] is False and result['canonical_outcome'] is None


def test_queue_compares_each_exact_method_and_keeps_unknown(monkeypatch):
    outcome=dict(status='attained_optimum',lex_key=['1','0',1,[['A','S']]])
    good=dict(status='SUCCESS',independent_exact=True,canonical_outcome=outcome)
    monkeypatch.setattr(ref,'load_worker_result',lambda *a,**kw:dict(good))
    common=dict(seed=dict(max_depth=9))
    result=ref.admit_queue_reference({},'x',common,{},'.',dict(flat=dict(canonical_outcome=outcome),hier=dict(canonical_outcome=outcome)))
    assert result['matched_exact_methods']==['flat','hier']
    bad=dict(status='attained_optimum',lex_key=['2','0',1,[['A','S']]])
    with pytest.raises(ValueError,match='contradict'):
        ref.admit_queue_reference({},'x',common,{},'.',dict(flat=dict(canonical_outcome=outcome),hier=dict(canonical_outcome=bad)))
    good.update(status='UNKNOWN',independent_exact=False,canonical_outcome=None)
    result=ref.admit_queue_reference({},'x',common,{},'.',dict(flat=dict(canonical_outcome=outcome)))
    assert result['matched_exact_methods']==[] and result['canonical_outcome'] is None


def test_authenticated_loader_rejects_tamper_and_wrong_hmax(tmp_path):
    common=dict(query=fixture.query(),seed=seed());manifest=dict(frozen='synthetic')
    value=dict(schema=ref.SCHEMA,case_id='tiny',Hmax=9,common_sha256=ref.digest(common),
        manifest_sha256=ref.digest(manifest),query_sha256=ref.digest(common['query']),
        production_optimizer_used=False,optimizer='validation.reference5.real_solver.solve_real_case',
        budget_seconds=120,status='UNKNOWN',independent_exact=False,canonical_outcome=None)
    root=tmp_path/'artifacts';path=root/ref.RESULT_PATH;path.parent.mkdir(parents=True)
    def write():
        path.write_bytes(ref.canonical(value))
        return dict(status='SUCCESS',cleanup_verified=True,worker_receipt=dict(result=ref.result_envelope(root,'tiny')))
    receipt=write()
    assert ref.load_worker_result(tmp_path,receipt,'tiny',common=common,manifest=manifest)==value
    path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(ValueError):ref.load_worker_result(tmp_path,receipt,'tiny',common=common,manifest=manifest)
    value['Hmax']=4;receipt=write()
    with pytest.raises(ValueError,match='identity'):
        ref.load_worker_result(tmp_path,receipt,'tiny',common=common,manifest=manifest)


def test_authenticated_loader_rejects_unsupported_fake_exact(tmp_path):
    common=dict(query=fixture.query(),seed=seed());manifest={}
    value=dict(schema=ref.SCHEMA,case_id='tiny',Hmax=9,common_sha256=ref.digest(common),
        manifest_sha256=ref.digest(manifest),query_sha256=ref.digest(common['query']),
        production_optimizer_used=False,optimizer='validation.reference5.real_solver.solve_real_case',
        budget_seconds=120,status='UNKNOWN',independent_exact=True,canonical_outcome=dict(status='primary_unattained',primary_infimum='1'))
    root=tmp_path/'artifacts';path=root/ref.RESULT_PATH;path.parent.mkdir(parents=True);path.write_bytes(ref.canonical(value))
    receipt=dict(status='SUCCESS',cleanup_verified=True,worker_receipt=dict(result=ref.result_envelope(root,'tiny')))
    with pytest.raises(ValueError,match='Unknown REF'):
        ref.load_worker_result(tmp_path,receipt,'tiny',common=common,manifest=manifest)
