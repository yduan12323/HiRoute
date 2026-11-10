"""Freeze data-only wider DEV cells; never launch a solver or routing query."""
from __future__ import annotations
import argparse,copy,hashlib,json,time
from pathlib import Path
from real_scale_inputs import select_domains,write_new
from hiroute.data.identity import domain_digest


def main(a):
    started,cpu=time.monotonic(),time.process_time()
    directory=Path(a.catalog)
    site_file=directory/'shared-sites.json';binding_file=directory/'site-bindings.json'
    sites=json.loads(site_file.read_text());bindings=json.loads(binding_file.read_text())
    cfg=json.loads(Path('configs/wider_validation_design_draft.json').read_text())
    # Keep the previously proposed12 OD targets, not a new maximin origin chosen
    # after seeing supplemented coverage. Endpoints/domain hashes are frozen now.
    cfg['selection']['corridor_km']=60
    cfg['selection']['candidate_counts']=[64,128,256,len(sites)]
    manifest=select_domains(cfg,sites,bindings)
    old=json.loads(Path('configs/existing_domain_transfer_dev.json').read_text())
    current=json.loads(Path('docs/existing_domain_transfer_results.json').read_text())
    cells=[];reused=[]
    for n in (64,128,256):
        for q in manifest['queries']:
            for soc in ('18','48'):
                for scenario in ('energy_only','schedule'):
                    ok=q['scenario_domain_status'][scenario][str(n)]=='available'
                    fingerprint=domain_digest(q,n,scenario) if ok else None
                    reuse=[]
                    for d in old['domains']:
                        if soc=='18' and n==d['N'] and scenario==d['scenario'] and fingerprint==d['candidate_domain_sha256']:
                            reuse=[dict(file='docs/existing_domain_transfer_results.json',domain_id=d['id'],method=r['method'])
                                for r in current['rows'] if r['domain_id']==d['id']]
                    if reuse:reused.extend(reuse)
                    cells.append(dict(query_id=q['query_id'],initial_energy_kwh=soc,scenario=scenario,N=n,
                        input_status='available' if ok else 'input_domain_unavailable',
                        qualified_count=q['scenario_eligible_counts'][scenario],
                        candidate_domain_sha256=fingerprint,execution_status='not_started',reusable_current_profile_rows=reuse))
    full=[]
    for scenario in ('energy_only','schedule'):
        ordered=sorted(manifest['queries'],key=lambda q:(q['scenario_eligible_counts'][scenario],q['query_id']))
        for q in (ordered[0],ordered[-1]):
            n=q['scenario_eligible_counts'][scenario]
            # digest accepts the full-pool key, whose value is the complete
            # declared corridor list even though its nominal bound is larger.
            full.append(dict(query_id=q['query_id'],scenario=scenario,N=n,initial_energy_kwh='18',
                complete_declared_corridor_domain=True,province_safe_filter=False,
                candidate_domain_sha256=domain_digest(q,len(sites),scenario),execution_status='not_started'))
    availability={str(n):dict(available_query_cells=sum(c['N']==n and c['input_status']=='available' for c in cells),
        unavailable_query_cells=sum(c['N']==n and c['input_status']!='available' for c in cells)) for n in (64,128,256)}
    selection=copy.deepcopy(cfg['selection'])
    selection['candidate_counts']=[64,128,256]
    selection['candidate_rule']='Frozen60km corridor, existing capability/unique-anchor/progress ordering; complete-domain supplements separately declared. Geographic restrictions are not safe province-wide reductions.'
    result=dict(schema='hiroute.charging_coverage_dev_matrix.frozen.v1',
        scope='Frozen data/model/profile/denominator; execution and proposed stage allocation still require the next scope decision. No main experiment or holdout.',
        launched=False,solver_called=False,road_queries_called=False,
        catalog_sha256=hashlib.sha256(site_file.read_bytes()).hexdigest(),
        bindings_sha256=hashlib.sha256(binding_file.read_bytes()).hexdigest(),
        catalog_storage='External versioned charging-coverage-artifacts-v1/audit-v1; raw/generated catalogs not in Git',
        model=cfg['model'],initial_energies_kwh=['18','48'],schedule_recipe=cfg['selection']['schedule_recipe'],
        endpoint_and_selection_policy=selection,
        endpoints={q['query_id']:q['endpoints'] for q in manifest['queries']},
        implementation_profile=old['profiles']['current_queue_profile'],methods=['flat_bb_strong','scale'],
        deterministic_order='N64 stage, then scheduleN128, then scheduleN256; query ID, initial18 then48, energy then schedule; Strong then Scale. Explicit unavailable cells retained.',
        planned_query_N_cells=len(cells),planned_method_cells=2*len(cells),availability=availability,
        cells=cells,complete_domain_supplement=full,reusable_rows=reused,
        resources=dict(worker_threads=1,numeric_workers=1,query_loaded_limit_s=120,target_loaded_s=60,
            cold_allowance_s=180,worker_reservation_cpu_s=300,pair_reservation_cpu_s=600,
            process_query_memory_bytes=8589934592,host_headroom_bytes=2147483648),
        accounting=dict(carried_solve_cpu_s=5166.078454329,verification_precharge_cpu_s=60,
            total_after_verification_cpu_s=5226.078454329,total_solve_budget_cpu_s=28800,
            remaining_after_verification_cpu_s=23573.921545671,
            proposed_first_DEV_stage_cap_cpu_s=12000,stage_allocation_authorized=False,
            residual_unallocated_cpu_s=11573.921545671,
            preparation='separately charged within predeclared900CPU cap; no new compute purchase/commitment'),
        stop_policy='Before each fresh pair reserve600CPU seconds from the approved stage and original ledger. If insufficient, mark both not_run_cpu_budget; preserve every denominator cell. No extension/rerun/physics change. Identical valid rows may be reused; changed-domain timing must not be relabeled.',
        unresolved=['EnergyN128/N256 unavailable on this60km policy; energyN256 globally unavailable at172qualified anchors.',
            'No new route/seed/four-charge feasibility or performance evidence; more raw Sites does not prove any.',
            'Main95%/median10s, external comparison, trip value and frozen>=8newOD holdout remain unmet.',
            'The proposed12000CPU first stage is not a guarantee all44availableN64cells finish within budget.'],
        preparation_cpu_s=time.process_time()-cpu,preparation_wall_s=time.monotonic()-started)
    assert len(cells)==144 and sum(x['available_query_cells']+x['unavailable_query_cells'] for x in availability.values())==144
    write_new(a.output,result)
    print(json.dumps(dict(availability=availability,reusable_rows=reused,full_domains=full,
        preparation_cpu_s=result['preparation_cpu_s'],launched=False),sort_keys=True))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--catalog',required=True);p.add_argument('--output',required=True)
    main(p.parse_args())
