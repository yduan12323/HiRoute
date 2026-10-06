"""Sequential bounded mock-only differential review. --ref adds independent REF."""
from pathlib import Path
import hashlib,json,sys,time
sys.path.insert(0,str(Path(__file__).resolve().parent))
from adversarial_checks import inputs,OUT
from timecut5.real_adapter import solve_bounded_real,solve_hierarchical_real

def signature(result):
    keys={'attained_optimum':('status','J','Q_total','H','site_action_tuple','lex_key'), 'primary_unattained':('status','primary_infimum'), 'secondary_unattained':('status','J','secondary_infimum'), 'infeasible_within_H_ref':('status',)}[result['status']]
    return {k:result[k] for k in keys}

def plain(x):
    if isinstance(x,dict):return {k:plain(v) for k,v in x.items()}
    if isinstance(x,(tuple,list)):return [plain(v) for v in x]
    if isinstance(x,(str,int,float,bool)) or x is None:return x
    return str(x)

use_ref='--ref' in sys.argv
if use_ref:
    sys.path.insert(0,'/workspace/shared/navigation_audit/ref5_work')
    from validation.reference5.real_input import IndependentLegTable
    from validation.reference5.real_solver import solve_real_case,estimate_real_regimes
path=OUT/'adversarial_mock_cases.json'
assert hashlib.sha256(path.read_bytes()).hexdigest()==json.loads((OUT/'adversarial_mock_freeze.json').read_text())['sha256']
cases=json.loads(path.read_text());report=[]
for c in cases:
    start=time.monotonic();q,t,tr=inputs(c);outputs=[]
    for dom in (False,True):
        f=solve_bounded_real(q,t,tr,dominance=dom);h=solve_hierarchical_real(q,t,tr,dominance=dom)
        outputs.extend((signature(f.canonical()['result']),signature(h.canonical()['result'])))
        if f.inner.result.witness is not None:
            seeded=solve_hierarchical_real(q,t,tr,dominance=dom,incumbent=f.inner.result.witness)
            outputs.append(signature(seeded.canonical()['result']))
    assert all(x==outputs[0] for x in outputs), (c['case_id'],outputs)
    row=dict(case_id=c['case_id'],production_variants=len(outputs),signature=outputs[0])
    if use_ref:
        data=json.dumps(c['table'],sort_keys=True,separators=(',',':')).encode()
        independent=IndependentLegTable.from_bytes(data,hashlib.sha256(data).hexdigest())
        preflight=estimate_real_regimes(q,independent)
        row['ref_regimes']=preflight['counts']['continuous_regimes']
        assert row['ref_regimes']<=256
        ref=solve_real_case(q,independent,regime_limit=256)
        row['ref_all_regimes_certified']=ref['all_regimes_certified']
        assert ref['all_regimes_certified'],(c['case_id'],ref)
        assert signature(ref['result'])==outputs[0],(c['case_id'],ref['result'],outputs[0])
    row['seconds']=round(time.monotonic()-start,4);report.append(plain(row))
    print(json.dumps(plain(row)),flush=True)
(OUT/('differential_with_ref_results.json' if use_ref else 'differential_production_results.json')).write_text(json.dumps(report,indent=2)+'\n')
