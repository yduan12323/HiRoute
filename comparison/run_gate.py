"""Two-phase tiny gate: finish/persist independent solves before Core import."""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path

from tiny_smt import solve, replay

ROOT = Path(__file__).resolve().parents[1]


def pack(value):
    if isinstance(value, Fraction):
        return str(value)
    if isinstance(value, dict):
        return {k:pack(v) for k,v in value.items()}
    if isinstance(value, (list,tuple)):
        return [pack(v) for v in value]
    return value


def semantics(result):
    status=result['status']; out=dict(status=status)
    if status=='attained_optimum':
        j,q,h,pi=result['key'];out['key']=[str(Fraction(j)),str(Fraction(q)),h,[list(x) for x in pi]]
    elif status=='primary_unattained':
        out['primary_infimum']=str(result['primary_infimum'])
    elif status=='secondary_unattained':
        for k in ('primary_value','primary_infimum','secondary_infimum'):
            out[k]=str(result[k])
    return out


def run(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    cases_file=ROOT/'comparison/cases.json'
    cases=json.loads(cases_file.read_text())['cases']
    independent=[]
    for case in cases:
        try:
            result=solve(case['snapshot'],output/'queries'/case['id'])
            independent.append(dict(id=case['id'],result=pack(result),
                semantic=semantics(result),analytic_match=semantics(result)==case['expected']))
        except Exception as exc:
            independent.append(dict(id=case['id'],status='GATE_ERROR',error=repr(exc)))
        (output/'independent.json').write_text(json.dumps(independent,indent=2)+'\n')
    # No result/relaxation from HiRoute is available during the independent phase.
    from hiroute.contracts import ProblemSnapshot
    from hiroute.exact.scale import solve_scale
    rows=[]
    for case, external in zip(cases,independent):
        row=dict(external);row['core']=[]
        for method in ('flat_bb_strong','scale'):
            try:
                core=solve_scale(ProblemSnapshot.from_dict(case['snapshot']),method=method,time_limit_s=3)
                summary=dict(method=method,semantic=semantics(core),match=semantics(core)==external.get('semantic'))
                if core['status']=='attained_optimum':
                    trace=core['replay']['trace']
                    charges=[Fraction(x[4])-Fraction(x[2]) for x in trace if x[0] in ('C','CS')]
                    wait=Fraction(trace[0][3])-Fraction(case['snapshot']['departure_time_s'])
                    checked=replay(case['snapshot'],tuple(tuple(x) for x in core['key'][3]),charges,wait)
                    summary['independent_replay_match']=checked['key']==core['key']
                row['core'].append(summary)
            except Exception as exc:
                row['core'].append(dict(method=method,status='GATE_ERROR',error=repr(exc)))
        rows.append(row)
        (output/'results.json').write_text(json.dumps(dict(rows=rows),indent=2)+'\n')
    passed=all(r.get('analytic_match') and all(x.get('match') and x.get('independent_replay_match',True)
        for x in r['core']) for r in rows)
    result=dict(schema='hiroute.independent_tiny_gate.v1',passed=passed,new_real_solver_rows=0,
        independence='All independent results persisted before HiRoute import; no internal solver/bound calls in model',
        case_sha256=hashlib.sha256(cases_file.read_bytes()).hexdigest(),rows=rows)
    (output/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=passed,cases=len(rows),statuses=[
        (r['id'],r.get('semantic',{}).get('status',r.get('status')),r.get('analytic_match')) for r in rows])))
    return passed


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True)
    raise SystemExit(0 if run(p.parse_args().output) else 1)
