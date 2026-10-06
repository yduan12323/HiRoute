"""New hand-arithmetic secondary-open mock, frozen before optimization."""
from copy import deepcopy
from pathlib import Path
from fractions import Fraction as R
import hashlib,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from adversarial_checks import BASE,OUT,blob,inputs
from timecut5.real_legs import encode_binary64
from timecut5.real_adapter import solve_bounded_real,solve_hierarchical_real
sys.path.insert(0,'/workspace/shared/navigation_audit/ref5_work')
from validation.reference5.real_input import IndependentLegTable
from validation.reference5.real_solver import solve_real_case
c=deepcopy(BASE[1]);c['case_id']='hand_secondary_open_direct_energy_trap'
c['table']['sites'][1]['effects']=['S']
for row in c['table']['legs']:
    if (row['source_anchor'],row['target_anchor'])==('road:o','road:b'):
        row['actual_length_m']=encode_binary64(100.)
c['query'].update(initial_energy_kwh=3,lambda_stop_s=1,schedule={'a':10,'b':10,'D':1})
c['independent_expected']={'status':'secondary_unattained','J':'14','secondary_infimum':'0'}
c['hand_derivation']='The only feasible schedule route is A:C then B:S; three unit-energy/unit-time legs consume initial energy exactly. Strict C requires q>0. Arrival at B is 3+q, release 4+q, and for small positive q service completes 11. Final arrival12 plus two stop penalties is14. Q has infimum0, unattained. Other two-stop action orders cannot reach/satisfy B.'
data=blob(c)+b'\n';(OUT/'secondary_attainment_mock.json').write_bytes(data)
(OUT/'secondary_attainment_freeze.json').write_text(json.dumps({'sha256':hashlib.sha256(data).hexdigest(),'expected_before_run':c['independent_expected']},indent=2)+'\n')
q,t,tr=inputs(c);outputs=[]
for solver in (solve_bounded_real,solve_hierarchical_real):
    for dom in (False,True):
        result=solver(q,t,tr,dominance=dom).canonical()['result']
        assert result=={'status':'secondary_unattained','J':R(14),'secondary_infimum':R(0)}
        outputs.append(dict(solver=solver.__name__,dominance=dom,result={k:str(v) for k,v in result.items()}))
raw=blob(c['table']);ref=solve_real_case(q,IndependentLegTable.from_bytes(raw,hashlib.sha256(raw).hexdigest()),regime_limit=32)
assert ref['all_regimes_certified']
assert ref['result']['status']=='secondary_unattained' and ref['result']['J']==14 and ref['result']['secondary_infimum']==0
outputs.append(dict(solver='independent_REF',status=ref['result']['status'],J='14',secondary_infimum='0',all_regimes_certified=True))
(OUT/'secondary_attainment_results.json').write_text(json.dumps(outputs,indent=2)+'\n')
print(json.dumps(outputs,indent=2))
