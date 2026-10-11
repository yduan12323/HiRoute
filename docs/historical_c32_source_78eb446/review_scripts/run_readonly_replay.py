"""Independent bounded C32 selected-leg replay; no optimizer entrypoint is allowed."""
import hashlib, importlib.util, json, resource, signal, sys, time
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
STAGE=ROOT/'physical_replay_stage'
EXPORT=Path('/home/dy/HiRoute/project/results/milestone_5_real_export')
LIMIT_SECONDS=180
LIMIT_BYTES=2*1024**3

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())

def alarm(*_):raise TimeoutError('C32 physical replay exceeded 180 seconds')
signal.signal(signal.SIGALRM,alarm)
signal.alarm(LIMIT_SECONDS)
resource.setrlimit(resource.RLIMIT_AS,(LIMIT_BYTES,LIMIT_BYTES))
start=time.monotonic()
sys.path.insert(0,str(ROOT))
from validation.reference5 import lp,solver
calls=[]
def forbidden(*args,**kwargs):
    calls.append(1)
    raise RuntimeError('NoOptimization guard: LP call refused')
lp.linprog=lp.exact_lp=solver.exact_lp=forbidden
source=STAGE/'experiments/time_cut_v2/real_export/compare_production_result.py'
assert sha(source)=='9f732a40ed186d5c0cebecc26ccf6bfeea2ea7375a0a6a5276a8843c484e99f4'
spec=importlib.util.spec_from_file_location('c32_compare_frozen',source)
compare=importlib.util.module_from_spec(spec);spec.loader.exec_module(compare)
assert sha(EXPORT/'selection_manifest.json')=='0e39ad906c01e05b4a4b764b3270360e309c24d1ae67d7a2e3533b6dca8af06a'
assert sha(EXPORT/'export_manifest.json')=='f846eb37219a34dea74aa9a79e7673b8cdae03ae281de189cb9b602a98ac380d'
manifest=read(EXPORT/'export_manifest.json');assert sha(EXPORT/'query_states_resolved.json')==manifest['query_states_resolved_sha256']
refroot=STAGE/'results/milestone_5_reference/real_completion_v1'
assert sha(refroot/'summary.json')=='4435c9fa5e0b4f0f0d666a5db7b3172fc0a66e13a84d1bbc8a7304143d403354'
summary=read(refroot/'summary.json');refs={x['state_id']:x for x in summary['states']}
states={x['state_id']:x for x in read(EXPORT/'query_states_resolved.json')}
assert len(states)==len(refs)==32
from validation.reference5.real_input import IndependentLegTable
from validation.reference5.real_solver import query_from_resolved_state
files=sorted((STAGE/'results/milestone_5_real_coalesced_c32/jobs').glob('*/attempt_*/*/result.json'))
assert len(files)==128
rows=[];tables={}
for f in files:
    prod=read(f);state=states[prod['state_id']];pool=state['pool_id']
    if pool not in tables:
        info=manifest['tables'][pool]
        tables[pool]=IndependentLegTable.from_bytes((EXPORT/info['path']).read_bytes(),info['sha256'])
    refinfo=refs[prod['state_id']];refpath=refroot/refinfo['report_path']
    assert sha(refpath)==refinfo['report_sha256']
    reference=read(refpath)['result']
    result=compare.verify_completed(prod,query_from_resolved_state(state,tables[pool]),tables[pool],reference)
    assert result['reference_match'] is True and result['attained_witness_replayed'] is True
    rows.append({'state_id':prod['state_id'],'mode':prod['mode'],'production_sha256':sha(f),'reference_report_sha256':sha(refpath)})
assert len({(r['state_id'],r['mode']) for r in rows})==128
assert not calls
out={'schema':'c32-readonly-physical-replay-v1','status':'passed','rows':rows,'count':len(rows),'optimizer_calls':len(calls),'elapsed_seconds':time.monotonic()-start,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'source_sha256':sha(source),'export_manifest_sha256':sha(EXPORT/'export_manifest.json'),'reference_summary_sha256':sha(refroot/'summary.json')}
result=ROOT/'physical_replay_result.json'
with result.open('x') as stream:json.dump(out,stream,indent=2,sort_keys=True);stream.write('\n')
print(json.dumps({k:out[k] for k in ('status','count','optimizer_calls','elapsed_seconds','peak_rss_kib')},sort_keys=True))
