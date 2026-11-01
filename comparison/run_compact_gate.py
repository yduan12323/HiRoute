"""Persist compact independent results before importing joint Core for parity."""
import argparse
import hashlib
import json
from pathlib import Path
from compact_smt import solve
from run_gate import pack, semantics
from tiny_smt import Unknown

ROOT=Path(__file__).resolve().parents[1]


def run(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    source=ROOT/'comparison/compact_cases.json';cases=json.loads(source.read_text())['cases']
    rows=[];stopped=False
    for case in cases:
        row=dict(id=case['id'])
        if stopped:row['status']='not_run_after_gate_error'
        else:
            try:
                result=solve(case['snapshot'],case['upper_witness'],output/'queries'/case['id'])
                row.update(result=pack(result),semantic=semantics(result),analytic_match=semantics(result)==case['expected'])
                if not row['analytic_match']:stopped=True
            except Exception as exc:
                row.update(status='unknown_backend' if isinstance(exc,Unknown) else 'GATE_ERROR',error=repr(exc));stopped=True
        rows.append(row)
        (output/'independent.json').write_text(json.dumps(rows,indent=2)+'\n')
    # The independent phase is now complete, including every error/unrun cell.
    if not stopped:
        from hiroute.contracts import ProblemSnapshot
        from hiroute.exact.scale import solve_scale
        for case,row in zip(cases,rows):
            row['core']=[]
            for method in ('flat_bb_strong','scale'):
                core=solve_scale(ProblemSnapshot.from_dict(case['snapshot']),method=method,time_limit_s=5)
                row['core'].append(dict(method=method,semantic=semantics(core),match=semantics(core)==row['semantic']))
    passed=not stopped and all(all(c['match'] for c in row['core']) for row in rows)
    result=dict(schema='hiroute.compact_gate.v1',passed=passed,new_real_rows=0,
        case_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),rows=rows)
    (output/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=passed,cases=len(rows),outcomes=[(r['id'],r.get('semantic'),r.get('error')) for r in rows])))
    return passed


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True)
    raise SystemExit(0 if run(p.parse_args().output) else 1)
