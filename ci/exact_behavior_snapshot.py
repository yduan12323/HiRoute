"""Record/compare exact behavior for the small frozen attainment boundary cases."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from test_scale_search import frozen_snapshot
from hiroute.contracts import ProblemSnapshot
from hiroute.exact.scale import solve_scale
from hiroute.exact.scale_replay import verify_scale_witness

CASES = {'cs_primary_unattained_positive_v2', 'cs_secondary_unattained_positive_v2',
         'c_primary_unattained_with_repeat_positive_v2', 'c_s_secondary_unattained_with_repeat_positive_v2',
         'deterministic_site_tuple_tie_positive_v2'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--expected', type=Path)
    args = p.parse_args()
    cases = json.loads((ROOT / 'tests/fixtures/milestone_5_reference/frozen_cases_v2.json').read_text())
    if isinstance(cases, dict):
        cases = cases['cases']
    rows = []
    for case in cases:
        name = case.get('case_id', case.get('id'))
        if name not in CASES:
            continue
        snapshot = ProblemSnapshot.from_dict(frozen_snapshot(case))
        for method in ('flat_bb_strong', 'scale'):
            result = solve_scale(snapshot, method=method, time_limit_s=5, seed_beam_pruning=True,
                                 inbound_energy_bound=True, eager_incumbent_pruning=True, pending_activity_screen=False)
            row = {k: result.get(k) for k in ('status', 'key', 'primary_value', 'primary_infimum', 'secondary_infimum', 'depth_contract')}
            if result['status'] == 'attained_optimum':
                row['physical'] = verify_scale_witness(snapshot, result)
            row.update(case=name, method=method)
            rows.append(row)
    if {r['case'] for r in rows} != CASES:
        raise ValueError('missing required behavioral cases')
    data = json.dumps(rows, sort_keys=True, default=str)
    if args.expected and json.loads(data) != json.loads(args.expected.read_text()):
        raise ValueError('exact behavioral snapshot differs; no floating tolerance is used')
    with args.output.open('x') as stream:
        stream.write(data + '\n')
    print(f'{len(rows)} exact method/case records verified')


if __name__ == '__main__':
    main()
