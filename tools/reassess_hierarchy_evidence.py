"""Read-only reduction of existing evidence; imports no solver or road provider."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from fractions import Fraction
import hashlib
import json
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
METHODS = ('flat_bb_strong', 'scale')


def ratio_summary(pairs, value):
    a = [value(x) for _, x, _ in pairs]
    b = [value(y) for _, _, y in pairs]
    return dict(n=len(pairs), strong_sum=sum(a), scale_sum=sum(b),
        median_scale_over_strong=median(y/x for x, y in zip(a, b) if x) if any(a) else None,
        scale_less=sum(y<x for x, y in zip(a, b)),
        equal=sum(y==x for x, y in zip(a, b)), scale_more=sum(y>x for x, y in zip(a, b)))


def reduce_evidence(source, matrix, coverage):
    frame = {(c['query_id'], c['initial_energy_kwh'], c['scenario']): c
             for c in matrix['cells'] if c['N'] == 64}
    groups = defaultdict(dict)
    for row in source['rows']:
        if row['N'] != 64:
            raise ValueError('non-N64 row in frozen cohort')
        key = (row['query_id'], row['initial_energy_kwh'], row['scenario'])
        if row['method'] in groups[key]:
            raise ValueError('duplicate method slot')
        groups[key][row['method']] = row
    if len(frame)!=48 or set(groups)!=set(frame) or any(set(v)!=set(METHODS) for v in groups.values()):
        raise ValueError('frozen48-cell denominator lost')
    supported, common, timeouts = [], [], []
    for key, group in sorted(groups.items()):
        a, b = (group[m] for m in METHODS)
        for row in (a, b):
            available = frame[key]['input_status'] == 'available'
            if available == (row['status'] == 'input_domain_unavailable'):
                raise ValueError('frozen input support changed')
            if available and row['candidate_domain_sha256'] != frame[key]['candidate_domain_sha256']:
                raise ValueError('frozen candidate domain changed')
        if (a['status']=='input_domain_unavailable') != (b['status']=='input_domain_unavailable'):
            raise ValueError('input support mismatch')
        if a['status']=='input_domain_unavailable':
            continue
        if a['candidate_domain_sha256']!=b['candidate_domain_sha256'] or a['implementation']!=b['implementation']:
            raise ValueError('paired domain/profile mismatch')
        supported.append((key, a, b))
        if a['status']==b['status']=='attained_optimum':
            if a['key']!=b['key']:
                raise ValueError('common exact full-key mismatch')
            common.append((key, a, b))
        if a['status']==b['status']=='time_limit':
            timeouts.append((key, a, b))
    values = dict(bound_queries=lambda r:r['metrics']['summary_queries']+r['metrics']['singleton_queries'],
                  heap_pushes=lambda r:r['metrics']['heap_pushes'], peak_open=lambda r:r['metrics']['peak_open'],
                  query_extra_bytes=lambda r:r['query_extra_peak_bytes'], loaded_s=lambda r:r['query_loaded_total_s'])
    metrics = ('transitions', 'terminal_attempts', 'leaf_routes', 'transition_input_pieces',
               'transition_output_pieces', 'max_depth')
    populations = {}
    for name, pairs in [('supported44', supported), ('common_exact', common), ('common_timeouts', timeouts)]:
        populations[name] = {k:ratio_summary(pairs, f) for k, f in values.items()}
    quality, outcomes = {}, {}
    for method in METHODS:
        rows = [r for r in source['rows'] if r['method']==method]
        exact = [r for r in rows if r['status']=='attained_optimum']
        with_seed = [r for r in exact if r.get('seed_key')]
        gaps = [(Fraction(r['seed_key'][0])-Fraction(r['key'][0]))/Fraction(r['key'][0]) for r in with_seed]
        if any(g<0 for g in gaps):
            raise ValueError('seed primary cost below exact optimum')
        quality[method] = dict(exact_rows=len(exact), exact_with_seed=len(with_seed),
            exact_seed_missing=[r['query_id']+'-E'+r['initial_energy_kwh']+'-'+r['scenario'] for r in exact if not r.get('seed_key')],
            exact_primary_improved_over_seed=sum(g>0 for g in gaps),
            median_seed_relative_primary_gap=float(median(gaps)), max_seed_relative_primary_gap=float(max(gaps)),
            meaning='Seed-quality diagnostic on attained subset, not a separated-planning or overlap-value baseline')
        outcomes[method] = dict(status_counts=dict(Counter(r['status'] for r in rows)),
            exact_within60=sum(r['status']=='attained_optimum' and r['query_loaded_total_s']<=60 for r in rows),
            full_denominator=len(rows), supported_denominator=sum(r['status']!='input_domain_unavailable' for r in rows))
    bottlenecks = {}
    for name, pairs in [('common_exact', common), ('common_timeouts', timeouts)]:
        bottlenecks[name] = {}
        for index, method in enumerate(METHODS, 1):
            rr = [pair[index] for pair in pairs]
            bottlenecks[name][method] = dict(n=len(rr),
                median_transition_share=median(r['seconds']['transitions']/r['query_loaded_total_s'] for r in rr),
                median_selected_leg_share=median(r['routing_metrics']['selected_leg_time_s']/r['query_loaded_total_s'] for r in rr),
                meaning='Nested timers, not additive exclusive shares; no C/S/CS split')
    availability = {}
    for n in (64, 128, 256):
        availability[str(n)] = {scenario:dict(
            denominator=sum(c['N']==n and c['scenario']==scenario for c in matrix['cells']),
            candidate_available=sum(c['N']==n and c['scenario']==scenario and c['input_status']=='available' for c in matrix['cells']))
            for scenario in ('energy_only', 'schedule')}
    return dict(schema='hiroute.research_route_reassessment.v1', new_real_solver_rows=0,
        solver_or_road_provider_imported=False, outcomes=outcomes, populations=populations,
        common_exact_metric_equality={m:sum(a['metrics'][m]==b['metrics'][m] for _, a, b in common) for m in metrics},
        common_exact_pairs=[dict(query_id=k[0],initial_energy_kwh=k[1],scenario=k[2],
            bound_queries_strong=values['bound_queries'](a),bound_queries_scale=values['bound_queries'](b),
            heap_pushes_strong=a['metrics']['heap_pushes'],heap_pushes_scale=b['metrics']['heap_pushes'],
            peak_open_strong=a['metrics']['peak_open'],peak_open_scale=b['metrics']['peak_open']) for k,a,b in common],
        seed_quality=quality,bottlenecks=bottlenecks,candidate_availability=availability,
        global_qualified_C_anchors=coverage['summary']['supplemented_unique_C_anchors'],
        caveats=['One observation per method/cell, Strong first; no balanced-order or repeated-run timing inference',
                 'Common-exact subset is conditional; retain full48 and supported44 population outcomes',
                 'Equal aggregate work counters do not establish identical histories or incumbent trajectories',
                 'OPEN entries are not bytes; query-extra RSS is not OPEN-only memory',
                 'Censored work prefixes are not complete-work or time-to-optimum comparisons'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',default=str(ROOT/'docs/hierarchy_reassessment_evidence.json'))
    args=p.parse_args()
    inputs = dict(cohort=ROOT/'docs/n64_coverage_stage_results.json',
        matrix=ROOT/'configs/charging_coverage_dev_matrix.json',coverage=ROOT/'docs/shandong_charging_coverage_results.json')
    loaded={k:json.loads(v.read_text()) for k,v in inputs.items()}
    result=reduce_evidence(loaded['cohort'],loaded['matrix'],loaded['coverage'])
    result['input_sha256']={str(v.relative_to(ROOT)):hashlib.sha256(v.read_bytes()).hexdigest() for v in inputs.values()}
    Path(args.output).write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(output=args.output,common_exact=len(result['common_exact_pairs']),new_real_solver_rows=0)))


if __name__=='__main__':
    main()
