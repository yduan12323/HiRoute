"""Persist compact independent results before importing joint Core for parity."""
import argparse
import hashlib
import json
from pathlib import Path
from compact_smt import solve
from run_gate import pack, semantics
from tiny_smt import Unknown
from parity_receipts import atomic_json, run_parity

ROOT=Path(__file__).resolve().parents[1]


def run(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    if any((output/name).exists() for name in ('independent.json','results.json')):
        raise FileExistsError('preserve existing gate receipts; use a fresh output directory')
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
        atomic_json(output/'independent.json',rows)
    # The independent phase is now complete, including every error/unrun cell.
    def solve_core(case,method):
        # Import failures also occur inside a pre-recorded Core slot.
        from hiroute.contracts import ProblemSnapshot
        from hiroute.exact.scale import solve_scale
        return solve_scale(ProblemSnapshot.from_dict(case['snapshot']),method=method,time_limit_s=5)
    result=run_parity(cases,rows,output,solve_core,semantics,
        case_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),independent_ok=not stopped)
    passed=result['passed']
    print(json.dumps(dict(passed=passed,cases=len(rows),outcomes=[(r['id'],r.get('semantic'),r.get('error')) for r in rows])))
    return passed


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True)
    raise SystemExit(0 if run(p.parse_args().output) else 1)
