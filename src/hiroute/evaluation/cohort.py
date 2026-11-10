"""Pure N64 receipt statistics. No solver, process launch or implicit repository I/O."""
import json
from collections import Counter
from pathlib import Path
import statistics
import math

COMPLETE={'attained_optimum','infeasible','primary_unattained','secondary_unattained'}
METHODS=('flat_bb_strong','scale')

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


def summarize_rows(cells, raw, *, terminal=False):
    """Retain missing, failed and reused slots in the fixed 48/96 denominator."""
    if len(cells)!=48 or len({(c["query_id"],c["initial_energy_kwh"],c["scenario"],c["N"]) for c in cells})!=48:
        raise ValueError("N64 query denominator changed")
    if terminal and len(raw)!=96:
        raise ValueError("terminal execution cohort lost method slots")
    expected={identity({**c,"method":m}) for c in cells for m in METHODS}
    indexed={identity(r):r for r in raw}
    if len(indexed)!=len(raw) or not set(indexed)<=expected:
        raise ValueError("duplicate or foreign method slots")
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
    return dict(summary=summaries, rows=rows, common_exact_pairs=len(paired),
        paired_exact_only_Strong_over_Scale_ratio_median=statistics.median(paired) if paired else None)
