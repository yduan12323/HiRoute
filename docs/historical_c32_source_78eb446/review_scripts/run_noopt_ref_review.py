"""Adapted C32 certificate-only verifier. Historical math functions are unmodified."""
import gzip, hashlib, json, resource, signal, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
STAGE=ROOT/'ref_review_stage'
SEED=STAGE/'results/milestone_5_reference/real_seed_v1'
FINAL=STAGE/'results/milestone_5_reference/real_completion_v1'
EXPORT=Path('/home/dy/HiRoute/project/results/milestone_5_real_export')
BASE=Path('/home/dy/HiRoute/project')
def sha(p):
    digest=hashlib.sha256()
    with p.open("rb") as stream:
        while block:=stream.read(8*1024*1024):digest.update(block)
    return digest.hexdigest()
def read(p):return json.loads(p.read_text())
def require(x,msg):
    if not x:raise ValueError(msg)
def timeout(*_):raise TimeoutError('180-second REF review cap')
signal.signal(signal.SIGALRM,timeout);signal.alarm(180)
resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
started=time.monotonic();sys.path.insert(0,str(ROOT))
from validation.reference5 import lp,solver
from validation.reference5.real_input import IndependentLegTable
from validation.reference5.real_solver import query_from_resolved_state
from validation.reference5.potential_reference import verify_potential_plan,solve_optimized_real_reference,verify_optimized_report,result_signature
from validation.reference5.solver import jsonable
calls=[]
def forbidden(*args,**kwargs):
    calls.append(1);raise RuntimeError('NoOptimization: LP entrypoint called')
lp.linprog=lp.exact_lp=solver.exact_lp=forbidden
freeze=read(SEED/'freeze_manifest.json');source_hashes=freeze['module_sha256']
for name,h in source_hashes.items():require(sha(ROOT/'validation/reference5'/name)==h,'source changed: '+name)
index=read(SEED/'raw_plans_integrity.json');summary=read(FINAL/'summary.json')
require(sha(EXPORT/'selection_manifest.json')=='0e39ad906c01e05b4a4b764b3270360e309c24d1ae67d7a2e3533b6dca8af06a','selection')
require(sha(EXPORT/'export_manifest.json')==freeze['export_manifest_sha256']==summary['export_manifest_sha256'],'export')
manifest=read(EXPORT/'export_manifest.json');require(sha(EXPORT/'query_states_resolved.json')==freeze['query_states_sha256']==manifest['query_states_resolved_sha256'],'queries')
selection=read(EXPORT/'selection_manifest.json')
for x in selection['sources']:
    p=BASE/x['repository_target_path']
    require(p.stat().st_size==x['size_bytes'] and sha(p)==x['sha256'],'selection source: '+x['name'])
states=read(EXPORT/'query_states_resolved.json')
require(len(states)==32 and [x['state_id'] for x in states]==[f'C{i:02}' for i in range(1,33)],'32 states/order')
require(len(selection['pools'])==16,'16 selected pools')
ref={x['state_id']:x for x in summary['states']};rows={x['state_id']:x for x in index['plans']}
require(len(ref)==len(rows)==32,'report/certificate population')
tables={};verified=[];seed_total=excluded_total=physical_total=family_total=0
for state in states:
    ident=state['state_id'];pool=state['pool_id'];info=manifest['tables'][pool]
    if pool not in tables:
        tables[pool]=IndependentLegTable.from_bytes((EXPORT/info['path']).read_bytes(),info['sha256'])
    table=tables[pool];q=query_from_resolved_state(state,table)
    require(state['H_ref']==4 and len(table.sites)==8,'H4/eight sites')
    item=rows[ident];b=(SEED/item['compressed_path']).read_bytes();raw=gzip.decompress(b)
    require(len(b)==item['compressed_bytes'] and sha(SEED/item['compressed_path'])==item['compressed_sha256'] and len(raw)==item['raw_bytes'] and hashlib.sha256(raw).hexdigest()==item['raw_sha256'],'raw seed bytes')
    owner=json.loads(raw);plan=owner['plan']
    require(owner['state_id']==ident and owner['pool_id']==pool,'plan identity')
    require(json.dumps(jsonable(owner['query']),sort_keys=True)==json.dumps(jsonable(q),sort_keys=True),'plan query')
    require(verify_potential_plan(q,table,plan),'plan verification')
    require(plan['residual_regime_count']==0 and plan['planned_lp_regime_count']==plan['seed_regime_count'],'zero residual')
    require(len(plan['depth_ledger'])==5 and all(x['role']=='excluded_by_strict_primary_bound' for x in plan['depth_ledger'][2:]),'strict family')
    complete=solve_optimized_real_reference(q,table,max_lp_regimes=plan['seed_regime_count'],plan=plan)
    require(verify_optimized_report(q,table,complete),'completed verification')
    file=FINAL/ref[ident]['report_path'];require(sha(file)==ref[ident]['report_sha256'],'final report hash')
    saved=read(file)
    require(result_signature(complete['result'])==result_signature(saved['result']),'final optimum')
    require(complete['certified_lp_regime_count']==saved['certified_lp_regime_count'] and complete['bound_excluded_regime_count']==saved['bound_excluded_regime_count'],'final counts')
    seed_total+=complete['certified_lp_regime_count'];excluded_total+=complete['bound_excluded_regime_count'];physical_total+=complete['original_physical_admissible_regime_count'];family_total+=3
    verified.append({'state_id':ident,'raw_seed_sha256':item['raw_sha256'],'report_sha256':sha(file),'seed_regimes':complete['certified_lp_regime_count'],'strict_excluded_regimes':complete['bound_excluded_regime_count']})
require((seed_total,excluded_total,physical_total,family_total)==(1958,455505408,455507366,96),'aggregate counts')
require(not calls,'LP call')
out={'schema':'c32-adapted-noopt-ref-review-v1','status':'passed','states':32,'certified_lp_regimes':seed_total,'strict_bound_families':family_total,'strict_excluded_regimes':excluded_total,'physical_admissible_regimes':physical_total,'optimizer_calls':len(calls),'elapsed_seconds':time.monotonic()-started,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'source_sha256':source_hashes,'selection_manifest_sha256':sha(EXPORT/'selection_manifest.json'),'export_manifest_sha256':sha(EXPORT/'export_manifest.json'),'seed_integrity_sha256':sha(SEED/'raw_plans_integrity.json'),'reference_summary_sha256':sha(FINAL/'summary.json'),'verified':verified,'selection_audit_scope':'frozen selection manifest, six original source hashes and resolved-state/table binding; full historical ranked-pool replay unavailable'}
with (ROOT/'ref_review_result.json').open('x') as f:json.dump(out,f,indent=2,sort_keys=True);f.write('\n')
print(json.dumps({k:out[k] for k in ('status','states','certified_lp_regimes','strict_bound_families','strict_excluded_regimes','optimizer_calls','elapsed_seconds','peak_rss_kib')},sort_keys=True))
