"""Read-only postprocessing of stage receipts; never launches a worker."""
import json
from collections import Counter
from pathlib import Path
import statistics
import argparse
import math

from hiroute.evaluation.cohort import identity, completion_interval_quantile, subgroup_summary, summarize_rows

ROOT=Path(__file__).resolve().parents[1]
COMPLETE={'attained_optimum','infeasible','primary_unattained','secondary_unattained'}
METHODS=('flat_bb_strong','scale')


def read(path):return json.loads(path.read_text())








def generate_report(input_root,output_root=None,repo_root=ROOT):
    HERE=Path(input_root).resolve()
    REPO=Path(repo_root).resolve()
    OUT=Path(output_root).resolve() if output_root is not None else HERE
    OUT.mkdir(parents=True,exist_ok=True)
    prep=read(HERE/'preparation.json');status=read(HERE/'status.json')
    if status['state']=='running':raise RuntimeError('cohort still running; no final summary')
    matrix=read(REPO/'configs/charging_coverage_dev_matrix.json')
    cells=[c for c in matrix['cells'] if c['N']==64]
    raw=read(HERE/'results.json')['rows']
    if status['state'] in ('complete','budget_stopped') and len(raw)!=96:
        raise ValueError('terminal execution cohort lost method slots')
    indexed={identity(r):r for r in raw}
    if len(indexed)!=len(raw):raise ValueError('duplicate method slots')
    reduced=summarize_rows(cells,raw,terminal=status['state'] in ('complete','budget_stopped'))
    rows,summaries=reduced['rows'],reduced['summary']
    inclusive_final= dict(status)
    controller_bound=math.ceil(status['total_controller_cpu_s'])+2
    inclusive_final.update(controller_cpu_final_conservative_s=controller_bound,
        stage_final_conservative_cpu_s=status['worker_and_development_cpu_s']+controller_bound,
        original_final_conservative_cpu_s=5226.078454329+status['worker_and_development_cpu_s']+controller_bound,
        note='Raw status retained; final closed controller rounded up plus2CPU seconds for terminal/startup tails.')
    if inclusive_final['stage_final_conservative_cpu_s']>12000 or inclusive_final['original_final_conservative_cpu_s']>28800:
        raise ValueError('final conservative cap exceeded')
    result=dict(schema='hiroute.n64_coverage_stage_results.v1',scope='Limited frozen N64 DEV, not main experiment or holdout',
        numerical_source_commit=prep['source']['commit'],preparation=prep,analysis_plan=read(HERE/'analysis-plan.json') if (HERE/'analysis-plan.json').exists() else dict(primary_method='scale',baseline='flat_bb_strong',note='Fixed DEV protocol; original standalone pre-run plan not present in this directory.'),
        accounting=inclusive_final,raw_terminal_status=status,accounting_revision=read(HERE/'accounting-resume.json') if (HERE/'accounting-resume.json').exists() else None,
        accounting_admission_pause=read(HERE/'admission-pause.json') if (HERE/'admission-pause.json').exists() else None,
        verification={name:read(HERE/name) if (HERE/name).exists() else None for name in ('terminal-verification.json','main-ci.json','stage-source-ci.json','accounting-source-ci.json')},
        summary=summaries,rows=rows,common_exact_pairs=reduced['common_exact_pairs'],
        paired_exact_only_Strong_over_Scale_ratio_median=reduced['paired_exact_only_Strong_over_Scale_ratio_median'],
        limits=['All48 query cells retained; runtime denominator44 supported cells per method includes all failures/unrun.',
          'Full48 pipeline rates and prospective supported44 runtime rates both reported; input unavailability never dropped.',
          'Population median/p95 use order-statistic interval bounds with120-second right censoring; solved-only medians explicitly descriptive.',
          'Reused2 rows are historical valid observations, not new repetitions.',
          'Completion agreement is not independent full-real-graph REF.',
          'Positive charges are observed feasible-witness counts; necessity lower bounds do not prove exact minimum counts.',
          'N128/N256/full domains, external comparison/trip value, representative attribution and independent holdout remain outstanding.'])
    (OUT/'cohort-results.json').write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n')
    lines=['| Query | Initial kWh | Scenario | Qualified | Strong status / loaded s | Scale status / loaded s | Scale positive charges / capacity LB |',
           '| --- | ---: | --- | ---: | --- | --- | --- |']
    for c in cells:
        pair=[next(r for r in rows if identity(r)==identity({**c,'method':m})) for m in METHODS]
        descriptions=[]
        for r in pair:
            time=r.get('query_loaded_total_s')
            descriptions.append(r['status']+(' / '+format(time,'.3f') if time is not None else '')+
                                (' (reused)' if r['execution']=='reused' else ''))
        primary=pair[1];witness=primary.get('witness')
        charges=('A' if primary['status']=='attained_optimum' else 'F')+str(witness['positive_charge_count']) if isinstance(witness,dict) and witness.get('physical_verified') else '—'
        lower=primary.get('necessary_charge_count_lower_bound')
        evidence=charges+' / '+('>='+str(lower) if lower is not None else '—')
        lines.append('| '+ ' | '.join([c['query_id'],c['initial_energy_kwh'],c['scenario'],str(c['qualified_count']),*descriptions,evidence])+' |')
    (OUT/'cohort-table.md').write_text('\n'.join(lines)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-root',required=True)
    parser.add_argument('--output-root')
    args=parser.parse_args()
    result=generate_report(args.input_root,args.output_root)
    print(json.dumps(dict(accounting=result['accounting'],summary=result['summary']),sort_keys=True,allow_nan=False))
