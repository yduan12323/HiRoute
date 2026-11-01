"""Read-only postprocessing of stage receipts; never launches a worker."""
import json
from collections import Counter
from pathlib import Path
import statistics
import argparse
import math

ROOT=Path(__file__).resolve().parents[1]
COMPLETE={'attained_optimum','infeasible','primary_unattained','secondary_unattained'}
METHODS=('flat_bb_strong','scale')


def read(path):return json.loads(path.read_text())


def identity(r):return (r['query_id'],r['initial_energy_kwh'],r['scenario'],r['N'],r['method'])


def completion_interval_quantile(rows,q):
    """Order-statistic bounds, retaining120s right censoring and unrun cells."""
    lower=[];upper=[]
    for row in rows:
        if row['status'] in COMPLETE:
            lo=hi=row['query_loaded_total_s']
        else:
            lo=min(120,row.get('query_loaded_total_s') or 0) if row['status']=='time_limit' else 0
            hi=float('inf')
        lower.append(lo);upper.append(hi)
    lower.sort();upper.sort()
    if q==.5:
        lo,hi=statistics.median(lower),statistics.median(upper)
    else:
        rank=math.ceil(q*len(rows))-1;lo,hi=lower[rank],upper[rank]
    return dict(identified=lo==hi,value_s=lo if lo==hi else None,
                lower_bound_s=lo,upper_bound_s=hi if math.isfinite(hi) else None)


def subgroup_summary(selected):
    supported=[r for r in selected if r['status']!='input_domain_unavailable']
    completed=[r for r in supported if r['status'] in COMPLETE]
    return dict(full_query_cells=len(selected),supported_query_cells=len(supported),
        statuses=dict(Counter(r['status'] for r in selected)),
        exact_completions=len(completed),attained_optima=sum(r['status']=='attained_optimum' for r in completed),
        exact_counts_by_loaded_threshold={str(t):sum(r.get('query_loaded_total_s',float('inf'))<=t for r in completed) for t in (10,30,60,120)},
        exact_CDF_full={str(t):sum(r.get('query_loaded_total_s',float('inf'))<=t for r in completed)/len(selected) for t in (10,30,60,120)},
        exact_CDF_supported={str(t):sum(r.get('query_loaded_total_s',float('inf'))<=t for r in completed)/len(supported) for t in (10,30,60,120)} if supported else None,
        supported_median_completion_s=completion_interval_quantile(supported,.5) if supported else None,
        supported_p95_completion_s=completion_interval_quantile(supported,.95) if supported else None)


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
    rows=[]
    for c in cells:
        for m in METHODS:
            stub={**c,'method':m}
            row=indexed.get(identity(stub))
            if row is None:
                row={**stub,'status':'input_domain_unavailable' if c['input_status']!='available' else
                     'not_attempted_stage_paused','mathematical_status':'unknown','execution':'not_attempted',
                     'stage_charged_cpu_s':0}
            rows.append(row)
    if len(rows)!=96:raise ValueError('denominator changed')
    summaries={}
    for method in METHODS:
        selected=[r for r in rows if r['method']==method]
        supported=[r for r in selected if r['status']!='input_domain_unavailable']
        completed=[r for r in supported if r['status'] in COMPLETE]
        observed=[r for r in supported if r.get('query_loaded_total_s') is not None]
        summaries[method]=dict(query_cells=len(selected),supported_cells=len(supported),
            statuses=dict(Counter(r['status'] for r in selected)),
            executions=dict(Counter(r['execution'] for r in selected)),
            exact_completions=len(completed),attained_optima=sum(r['status']=='attained_optimum' for r in completed),
            completion_CDF_supported={str(t):sum(r.get('query_loaded_total_s',float('inf'))<=t for r in completed)/len(supported)
                                      for t in (10,30,60,120)},
            completed_loaded_median_descriptive_s=statistics.median(r['query_loaded_total_s'] for r in completed) if completed else None,
            physical_feasible_replays=sum(r.get('witness',{}).get('physical_verified') is True for r in selected if isinstance(r.get('witness'),dict)),
            attempted_with_loaded_timer=len(observed),
            observed_positive_charge_counts=dict(Counter(str(r['witness']['positive_charge_count']) for r in selected
                if isinstance(r.get('witness'),dict) and r['witness'].get('physical_verified'))))
        summaries[method].update(subgroup_summary(selected))
        summaries[method]['by_scenario']={scenario:subgroup_summary([r for r in selected if r['scenario']==scenario]) for scenario in ('energy_only','schedule')}
        summaries[method]['by_initial_energy']={energy:subgroup_summary([r for r in selected if r['initial_energy_kwh']==energy]) for energy in ('18','48')}
        summaries[method]['attained_positive_charge_counts']=dict(Counter(str(r['witness']['positive_charge_count']) for r in selected
            if r['status']=='attained_optimum' and isinstance(r.get('witness'),dict)))
        summaries[method]['unknown_feasible_positive_charge_counts']=dict(Counter(str(r['witness']['positive_charge_count']) for r in selected
            if r['status'] not in COMPLETE and isinstance(r.get('witness'),dict) and r['witness'].get('physical_verified')))
        first=[r['time_to_first_feasible_s'] for r in supported if r.get('time_to_first_feasible_s') is not None and isinstance(r.get('witness'),dict) and r['witness'].get('physical_verified')]
        summaries[method]['first_physical_feasible_median_s']=statistics.median(first) if first else None
        summaries[method]['first_physical_feasible_max_s']=max(first) if first else None
        summaries[method]['physical_feasible_by_threshold_counts']={str(t):sum(x<=t for x in first) for t in (10,30,60,120)}
        summaries[method]['max_query_extra_peak_bytes']=max((r.get('query_extra_peak_bytes') or 0 for r in supported),default=0)
        summaries[method]['max_process_group_peak_rss_bytes']=max((r.get('process_group_peak_rss_bytes') or 0 for r in supported),default=0)
        summaries[method]['min_host_available_bytes']=min((r['host_available_min_bytes'] for r in supported if r.get('host_available_min_bytes') is not None),default=None)
    paired=[]
    for a,b in zip(rows[::2],rows[1::2]):
        if a['status'] in COMPLETE and b['status'] in COMPLETE:
            fields=('status','key','primary_value','primary_infimum','secondary_infimum')
            if tuple(a.get(k) for k in fields)!=tuple(b.get(k) for k in fields):raise ValueError('full-key/attainment disagreement')
            paired.append(a['query_loaded_total_s']/b['query_loaded_total_s'])
        for r in (a,b):
            witness=r.get('witness')
            if isinstance(witness,dict) and witness.get('physical_verified'):
                if witness['independent_key']!=r['feasible_key']:raise ValueError('replay key inconsistent')
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
        summary=summaries,rows=rows,common_exact_pairs=len(paired),
        paired_exact_only_Strong_over_Scale_ratio_median=statistics.median(paired) if paired else None,
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
