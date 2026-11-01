"""Read-only Site/geometry assessment; never load roads, route or call a solver."""
from __future__ import annotations
import argparse,copy,hashlib,json,resource,time
from collections import Counter
from fractions import Fraction
from pathlib import Path
from real_scale_inputs import great_circle,select_domains,write_new


def assess(input_root,base):
    started,cpu=time.monotonic(),time.process_time()
    sites_path=input_root/'shared-sites.json';bindings_path=input_root/'site-bindings.json'
    sites=json.loads(sites_path.read_text());bindings=json.loads(bindings_path.read_text())
    access=bindings['site_access_nodes'];attached=[s for s in sites if s['site_id'] in access]
    qualified=[s for s in attached if s['capabilities']]
    chargers=[s for s in attached if 'C' in s['capabilities']]
    global_c=len({access[s['site_id']] for s in chargers})
    global_any=len({access[s['site_id']] for s in qualified})
    def nearest(target):
        return min(attached,key=lambda s:(great_circle(target,s),s['site_id']))
    old=base['selection']['ods']
    origins=[copy.deepcopy(old[i]['origin']) for i in (0,1,2)]
    destinations=[copy.deepcopy(old[i]['destination']) for i in (0,1,3)]
    old_anchors={access[nearest(x)['site_id']] for x in origins+destinations}
    bound_origins=[nearest(x) for x in origins]
    pool=[s for s in chargers if s['lon']<=116.5 and access[s['site_id']] not in old_anchors
          and min(great_circle(s,nearest(d)) for d in destinations)>=400000]
    ranked=sorted(pool,key=lambda s:(-min(great_circle(s,o) for o in bound_origins),s['site_id']))
    fourth=next(s for s in ranked if access[nearest(s)['site_id']] not in old_anchors)
    origins.append(dict(name='Western_maximin_attached_C_Site',site_id=fourth['site_id'],
                        lon=fourth['lon'],lat=fourth['lat']))
    ods=[dict(query_id=f'WD{i*3+j+1:02}',origin=o,destination=d)
         for i,o in enumerate(origins) for j,d in enumerate(destinations)]
    endpoint_rule=('Existing Heze/Liaocheng/Dezhou targets plus one attached C Site at lon<=116.5, '
        'maximizing minimum geographic separation from those three bound origins; all eastern '
        'destinations >=400km geodesic, existing anchor excluded, Site ID tie. Cross with the existing '
        'Rongcheng/Weihai/Yantai targets. Geography/data only; no solver outcomes or road searches.')
    proposal=copy.deepcopy(base)
    proposal.update(schema='hiroute.wider_validation_design.draft.v1',scope=(
        'UNAPPROVED DRAFT: 12 OD x two proposed initial SOC x energy/schedule =48 query recipes. '
        'Data geometry only, not launched, not a holdout. Domain policy/budget/solver eligibility '
        'must be decided before wider solves. No permission or resources are created by this file.'))
    proposal['selection'].update(ods=ods,corridor_km=60,candidate_counts=[64,128,256],
        endpoint_rule=endpoint_rule,candidate_rule=(
        'Existing capability/attachment/unique-anchor/progress policy; declared corridor restriction, '
        'not a safe full-province filter. Proposed60km policy pending decision;126km is assessed '
        'only as an existing-policy alternative, not selected to fill N.'))
    proposal['proposed_initial_energy_kwh']=['18','48']
    proposal['proposed_soc_fractions']=['3/10','4/5']
    proposal['decision_boundary']=dict(launch=False,domain_policy='pending',budget='pending',
        algorithm_and_statistics_freeze='required before independent holdout',
        holdout='>=8 genuinely new OD groups later; no holdout selected or run here',
        schedule='existing2/5..7/10 direct selected-time recipe,2700s duration; actual times uncomputed',
        methods=['flat_bb_strong','scale'],main_solver_cap_s='pending; current gate120s not automatically a wider budget')
    data=[]
    for width in (60,126):
        cfg=copy.deepcopy(proposal);cfg['selection']['corridor_km']=width
        cfg['selection']['candidate_counts']=[64,128,256,global_any]
        pre=select_domains(cfg,sites,bindings)
        for q in pre['queries']:
            row=dict(query_id=q['query_id'],corridor_km=width,endpoints=q['endpoints'],
                geographic_distance_m=q['great_circle_m'],scenarios={})
            for scenario in ('energy_only','schedule'):
                counts=q['scenario_eligible_counts'][scenario]
                assert len(q['scenario_candidate_domains'][scenario][str(global_any)])==counts
                def digest(n):
                    value=dict(endpoints=q['endpoints'],candidates=q['scenario_candidate_domains'][scenario][str(n)])
                    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
                row['scenarios'][scenario]=dict(qualified_count=counts,
                    available={str(n):counts>=n for n in (64,128,256)},
                    fingerprints={str(n):digest(n) for n in (64,128,256) if counts>=n},
                    full_qualified_fingerprint=digest(global_any),routing_assessed=False,seed_assessed=False)
            data.append(row)
    assert len({(r['endpoints']['origin']['access_node'],r['endpoints']['destination']['access_node'])
                for r in data if r['corridor_km']==60})==12
    assert min(r['geographic_distance_m'] for r in data)>=400000
    summary=[]
    for width in (60,126):
        rs=[r for r in data if r['corridor_km']==width]
        by={scenario:{str(n):sum(r['scenarios'][scenario]['available'][str(n)] for r in rs)
              for n in (64,128,256)} for scenario in ('energy_only','schedule')}
        available=sum(x for s in by.values() for x in s.values())*2
        summary.append(dict(corridor_km=width,available_od_counts=by,
            proposed_query_N_cells=144,candidate_available_query_N_cells=available,
            candidate_unavailable_query_N_cells=144-available,proposed_method_rows=288,
            candidate_available_method_rows=2*available,
            query_slot_upper_s_at_current120s=2*available*120,
            full_qualified_counts={s:[r['scenarios'][s]['qualified_count'] for r in rs]
                                   for s in ('energy_only','schedule')}))
    inventory=[];verified=[]
    historical=['docs/real_scale_results.jsonl','docs/road_seed_dev_results.jsonl',
                'docs/source_time_reuse_results.json','docs/inbound_energy_results.json',
                'docs/enqueue_pruning_results.json']
    for filename in historical:
        path=Path(filename)
        rows=([json.loads(x) for x in path.read_text().splitlines()] if path.suffix=='.jsonl'
              else json.loads(path.read_text())['rows'])
        replayed=[r for r in rows if (r.get('witness') or {}).get('physical_verified')]
        verified.extend(replayed)
        inventory.append(dict(file=filename,records=len(rows),replayed_records=len(replayed),
            charge_status_counts=dict(Counter(f"{r['status']}:{r['witness']['positive_charge_count']}" for r in replayed))))
    model=proposal['model'];span=Fraction(model['capacity_kwh'])-Fraction(model['minimum_energy_kwh'])
    threshold={e:str((Fraction(e)+3*span-Fraction(model['destination_reserve_kwh']))
                     /Fraction(model['consumption_kwh_per_m'])) for e in proposal['proposed_initial_energy_kwh']}
    result=dict(schema='hiroute.wider_validation_readonly.v1',solver_called=False,
        road_index_built=False,road_queries_called=False,selection_uses_solver_results=False,
        proposed_ods=12,proposed_queries=48,selection_rule=endpoint_rule,
        source=dict(sites_sha256=hashlib.sha256(sites_path.read_bytes()).hexdigest(),
            bindings_sha256=hashlib.sha256(bindings_path.read_bytes()).hexdigest(),
            graph_tsv_bytes=(input_root/'real-scale-road.tsv').stat().st_size,
            raw_sites=len(sites),attached_sites=len(attached),raw_C_sites=sum('C' in s['capabilities'] for s in sites),
            attached_C_sites=len(chargers),unique_attached_C_anchors=global_c,
            unique_attached_any_capability_anchors=global_any,
            unattached_C_sites=sum('C' in s['capabilities'] for s in sites)-len(chargers),
            attachment_rules=bindings['audit'].get('max_distance_m'),
            raw_capabilities=dict(Counter(','.join(s['capabilities']) for s in sites))),
        energy_N256_global_shortfall=max(0,256-global_c),
        capacity_only_four_charge_shortest_road_threshold_m=threshold,
        threshold_rule='A capacity-only lower bound >=4 requires exact shortest-road length strictly greater than this threshold; it does not predict optimal charge count.',
        historical_record_inventory=inventory,
        inventory_is_not_an_independent_query_denominator=True,
        historical_max_replayed_positive_charges=max(r['witness']['positive_charge_count'] for r in verified),
        historical_replayed_four_plus_records=sum(r['witness']['positive_charge_count']>=4 for r in verified),
        proposed_full_domain_subset_rule='Minimum and maximum qualified counts per scenario, query ID tie, initial18 only, both methods; after domain-policy decision. At most8 supplemental method rows, deduplicate exact input/profile matches.',
        cautions=['Counts precede directed reachability/energy/schedule/seed checks; availability is not feasibility.',
            'Geodesic separation is a proxy, not a certified shortest-road metric or charge-count proof.',
            'Full qualified corridor sets remain geographic workload restrictions, not province-optimal safe filters.',
            'New12-OD recipes are DEV design candidates, not an independent holdout or performance sample.'],
        alternatives=summary,rows=data,assessment_cpu_s=time.process_time()-cpu,
        assessment_wall_s=time.monotonic()-started,
        peak_rss_platform_units=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return proposal,result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input-root',type=Path,required=True)
    p.add_argument('--draft',type=Path,required=True);p.add_argument('--summary',type=Path,required=True)
    args=p.parse_args();base=json.loads(Path('configs/real_scale_dev.json').read_text())
    proposal,result=assess(args.input_root,base)
    write_new(args.draft,proposal);write_new(args.summary,result)
    print(json.dumps({k:result[k] for k in ('solver_called','proposed_ods','proposed_queries','source',
                                         'alternatives','assessment_cpu_s','assessment_wall_s')},indent=2))

if __name__=='__main__':main()
