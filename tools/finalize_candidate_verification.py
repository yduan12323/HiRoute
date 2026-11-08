"""Versioned final acceptance for a separately verified candidate."""
import hashlib,json
from fractions import Fraction as F
from pathlib import Path
from exact_physical_adapter import replay,validate
from run_shared_leg_pilot import load,sha
from run_grounded_lookup_consumer import raw_replay,completed_result


def canonical(value):
    # JSON's array representation intentionally normalizes tuple/list round trips.
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')


def finalize(comparison,ad,old,table,parameters,audit,check,verify_final_inputs):
    """No accepted result is returned until every final check succeeds.

    Caller still must publish a successful terminal within its original deadline.
    This function never modifies historical results or calls a solver.
    """
    check();audit=Path(audit);verified=comparison['result'];receipt=comparison['receipt']
    if receipt['file']!='separate-witness.verified.json':raise ValueError('verified output name')
    path=audit/receipt['file'];stored=load(path);raw=canonical(stored['result']);digest=hashlib.sha256(raw).hexdigest()
    if raw!=canonical(verified) or digest!=receipt['result_sha256'] or digest!=stored['result_sha256']:
        raise ValueError('verification receipt mismatch')
    if stored['verification']!='VERIFIED_REPLAY' or stored['requires_successful_consumer_terminal'] is not True:raise ValueError('terminal receipt contract')
    if verified['status']!='VERIFIED_ATTAINED_IMPROVEMENT' or verified['optimality_certified'] is not False or verified['full_key_optimality_certified'] is not False:raise ValueError('verified outcome contract')
    if verified['verification_scope']!='SEPARATE_POST_RUN_VERIFICATION' or verified['original_run_status']!='UNKNOWN' or verified['original_run_completed_in_budget'] is not False:raise ValueError('historical outcome contract')
    expected=ad['expected_import']
    for field in ('original_source','verifier_source','candidate_sha256','audit_sha256'):
        if verified[field]!=expected[field]:raise ValueError('verification provenance mismatch '+field)
    physics=validate(table,parameters);bound=F(ad['bound'])
    if verified['table_sha256']!=table.payload_sha256 or verified['physics_sha256']!=physics.sha256 or F(verified['bound'])!=bound:raise ValueError('verification input identity')
    check();w=verified['witness'];checked=replay(table,parameters,w['plan'],w['charges'],w['initial_wait'])
    if checked['key'][0]!=F(verified['primary_value']) or not checked['key'][0]<bound:raise ValueError('final strict improvement replay')
    check();output=raw_replay(table,old,[(p.source,p.target) for p in table.literal_plan_legs(w['plan'],physics.pending)],check)
    check();verify_final_inputs();check()
    result=dict(mode='optimization',holdout=False,road_selection_certified=False,verification_scope='SEPARATE_POST_RUN_VERIFICATION',original_run_status='UNKNOWN',original_run_completed_in_budget=False)
    completed_result(result,verified,output,ad,old,table)
    result.update(verified_witness_file_sha256=sha(path,check),verified_payload_sha256=digest,attained_improvement_certified=True,optimality_certified=False,full_key_certified=False)
    check();return result
