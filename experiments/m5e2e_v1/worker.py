"""Fresh supervised method/check processes; no REF result is an optimizer input."""
import argparse
import os
import sys
from pathlib import Path
from .common import load, write_new, file_hash


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--case', required=True, type=Path)
    p.add_argument('--method', required=True, choices=('REF','FLAT','HIER','CHECK','ROAD_CHECK'))
    p.add_argument('--ref-evidence', type=Path)
    p.add_argument('--prepared', type=Path)
    args = p.parse_args()
    case = load(args.case)
    binding = case['domain_binding']
    query = load(case['query_path'])
    legs = Path(case['legs_path']).read_bytes()
    out = Path(os.environ['HIROUTE_OUTPUT_DIR'])
    if args.method in ('FLAT','HIER'):
        # No result is passed to production. Additionally deny Python file access
        # to every other stage's output under this run root; this is an audit
        # invariant, not an OS sandbox against hostile native code.
        run_root=args.case.resolve().parents[3]
        allowed={args.case.resolve(),Path(case['query_path']).resolve(),
                 Path(case['legs_path']).resolve(),Path(case['hierarchy_path']).resolve()}
        def no_other_results(event, values):
            if event=='open' and isinstance(values[0],(str,bytes,os.PathLike)):
                path=Path(os.fsdecode(values[0])).resolve()
                if path.is_relative_to(run_root) and not path.is_relative_to(out.resolve()) and path not in allowed:
                    raise PermissionError('Production worker cannot read other run artifacts')
        sys.addaudithook(no_other_results)
    if args.method == 'ROAD_CHECK':
        if not args.prepared: raise ValueError('Graph replay requires same-build prepared receipt')
        from .selection import replay_graph_legs
        result = replay_graph_legs(load(args.prepared), args.case)
    elif args.method == 'CHECK':
        if not args.ref_evidence:
            raise ValueError('Cold checker requires explicit REF evidence')
        from .solve import check_reference_evidence
        result = check_reference_evidence(query, legs, binding['legs_sha256'], load(args.ref_evidence))
    else:
        if args.ref_evidence:
            raise ValueError('Method solver cannot consume REF output')
        from .solve import solve_method
        result = solve_method(args.method, query, legs, legs_sha256=binding['legs_sha256'],
            hierarchy_bytes=Path(case['hierarchy_path']).read_bytes(),
            hierarchy_sha256=binding['hierarchy_sha256'], domain_binding=binding)
    if result.get('reference_evidence') is not None:
        write_new(out/'reference_evidence.json', result.pop('reference_evidence'))
        result['reference_evidence_path'] = str(out/'reference_evidence.json')
    result['case_manifest_sha256'] = file_hash(args.case)
    write_new(out/'result.json', result)
    write_new(os.environ['HIROUTE_WORKER_RECEIPT'],
              dict(status='COMPLETED', result_sha256=file_hash(out/'result.json')))


if __name__ == '__main__':
    main()
