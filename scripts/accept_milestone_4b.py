"""Record complete M4B acceptance from finished tests and measured evidence."""
import json
from datetime import datetime,timezone
import xml.etree.ElementTree as ET
import pandas as pd
from _common import ROOT,sha256


def main():
    root=ROOT/'results/milestone_4b';benchmark=json.loads((root/'benchmark.json').read_text())
    tests=ET.parse(root/'tests.xml').getroot();suites=list(tests.iter('testsuite'))
    counts={k:sum(int(s.attrib.get(k,0)) for s in suites) for k in ['tests','failures','errors','skipped']}
    preserve=json.loads((root/'preservation_after.json').read_text())
    routing=json.loads((root/'routing_reproducibility.json').read_text())
    subset=json.loads((root/'subset_reproducibility.json').read_text())
    figures=json.loads((root/'figures/source_preflight.json').read_text())
    candidates=pd.read_parquet(root/'candidate_counts.parquet')
    checks={'all_previous_and_new_acceptance_tests':counts['tests']>=84 and not any(counts[k] for k in ['failures','errors','skipped']),
        'all_493_protected_files_and_spec_unchanged':preserve['passed'] and preserve['verified_files']==493,
        'all_30_ods_all_7_ratios':set(candidates.instance_id)==set(range(30)) and len(set(candidates.ratio))==7,
        'all_task_access_dwell_method_scenarios':len(candidates)==30*7*8*2*2*12,
        'directed_gateways_and_exact_single_pair_oracle':(root/'gateways.parquet').exists() and len(benchmark['candidate_partition_files'])==240,
        'geographic_decision_pareto_epsilon_random':len(set(candidates.method))==12,
        'regret_topk_coverage_and_failures':all((root/(n+'.parquet')).exists() for n in ['abstraction_regret','topk_regret','epsilon_optimal_coverage','failure_analysis','stage_regret','decision_expansion']),
        'conditional_cover_bound':benchmark['maximum_epsilon_bound_excess']<=1e-10,
        'cold_cost_byte_reproducibility_and_independent_routes':routing['passed'] and routing['cold_pair_byte_identical'],
        'sufficient_representation_regeneration':subset['passed'],
        'figures_preflight_and_diagnostics':figures['summary']['ready'] and (root/'figures/microplan_diagnostics.png').exists(),
        'scientific_report_and_reproduction_commands':(ROOT/'docs/MILESTONE_4B_REPORT.md').exists() and 'scripts/run_microplan_benchmark.py' in (ROOT/'README.md').read_text()}
    record={'timestamp_utc':datetime.now(timezone.utc).isoformat(),'passed':all(checks.values()),'checks':checks,'tests':counts,
        'scope':'Milestone 4B only; explicit structural local-task Go-1, no uncertainty/semantic/acquisition work',
        'report_sha256':sha256(ROOT/'docs/MILESTONE_4B_REPORT.md'),
        'final_source_sha256':{str(p.relative_to(ROOT)):sha256(p) for base in ['src/microplan','scripts','tests'] for p in (ROOT/base).rglob('*') if p.suffix in ['.py','.cpp']},'initial_git_commit':json.loads((root/'preservation_before.json').read_text())['git_commit']}
    (root/'acceptance.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record,indent=2))
    if not record['passed']:raise ValueError('M4B acceptance incomplete')

if __name__=='__main__':main()
