"""480 deployable queries, clean flat control, then isolated offline D1–D5 audit."""
import json,sys,time
from pathlib import Path
import numpy as np
import pandas as pd
from _common import ROOT,configs,load_graph,read_config,sha256
from _stopplan4r_common import write_json,memory_guard,peak_rss_mib
from microplan.routing import ExactRouter
from run_stopplan_4r_diagnostic import ODTravel
from stopplan4r.models import EVModel,PiecewiseChargingCurve,PlannerConfig,ScheduledStop,Trip
from stopplan4r.sites import sites_from_table
from stopplan4r.evaluation import best_one_stop,plan_key
from hierarchy4r.domain import effects,flat_actions,best,action_id
from hierarchy4r.deploy import BUCKETS,bucket_flags,reduction,ALT_REL,ALT_ABS,COST_SAFETY
from hierarchy4r.deploy_search import DeployIndex,deploy_search,exact_leaf
from hierarchy4r.bounds import oracle_bound

ONLINE=False
ORACLE_ACCESS_ATTEMPTS=0


def io_guard(event,args):
    global ORACLE_ACCESS_ATTEMPTS
    if ONLINE and event=='open' and isinstance(args[0],(str,bytes)) and '/milestone_4r_b1/' in str(args[0]):
        ORACLE_ACCESS_ATTEMPTS+=1
        raise RuntimeError('Deployable query attempted to open oracle evidence')


def main():
    global ONLINE
    out=ROOT/'results/milestone_4r_b1d';old=ROOT/'results/milestone_4r_b1'
    assert json.loads((out/'precomparison_D2.json').read_text())['violations']==0
    if (out/'query_preregistration.json').exists():raise FileExistsError('Comparative run already started')
    cfg=read_config('configs/stopplan_4r.yaml');memory_guard(cfg['memory'],projected_additional_gib=10)
    ev=EVModel(**cfg['ev']);curve=PiecewiseChargingCurve(tuple(map(tuple,cfg['charging']['bands'])));pc=PlannerConfig(**cfg['planner'])
    graph=load_graph(*configs(cfg['graph_data_config']));router=ExactRouter(graph,cfg,out/'native_cache')
    ts=time.perf_counter();index=DeployIndex(out);load_seconds=time.perf_counter()-ts
    sites={s.site_id:s for s in sites_from_table(pd.read_parquet(ROOT/'results/milestone_4r/stop_sites.parquet'))}
    # Offline audit structures are not arguments to deploy_search/DeployIndex.
    tree=json.loads((old/'hierarchy.json').read_text());site_ids=tree['site_ids']
    access=np.array([sites[s].access_node for s in site_ids]);flags=np.array([bucket_flags(sites[s]) for s in site_ids])
    members={(r,b):np.array([i for i in region['members'] if flags[i,b]],dtype=int)
             for r,region in enumerate(tree['regions']) for b in range(3)}
    root_ids={b:[site_ids[i] for i in members[0,b]] for b in range(3)}
    write_json(out/'query_preregistration.json',dict(epsilon=0,landmarks=8,hierarchy_sha256=sha256(old/'hierarchy.json'),
        summary_sha256=sha256(out/'summaries.npy'),ALT_ABS=ALT_ABS,ALT_REL=ALT_REL,cost_safety_s=COST_SAFETY,
        rounding_justification='2e-8 exceeds 8*n*float64 epsilon for the 5,892,498-node nonnegative graph; per-difference absolute plus relative outward adjustment, nextafter toward -infinity. Accepted feasibility tolerances also retained.',
        primary_work='All reached leaf candidate Site checks including envelope-only rejects; objective calls also separately counted. Conservative against semantic flat denominator.',
        flat_control='All appropriate static bucket Site candidates, same exact leaf routine and shared routing, no oracle records/serialization inside timing',
        source_sha256={str(p.relative_to(ROOT)):sha256(p) for p in [ROOT/'src/hierarchy4r/deploy.py',ROOT/'src/hierarchy4r/deploy_search.py',Path(__file__)]}))
    sys.addaudithook(io_guard)
    ods=pd.read_parquet(ROOT/cfg['development_ods']).sort_values('instance_id')
    metrics=[];coverage=[];comparisons=[];instrument=[];routing_log=[];distance_checks=[]
    qdir=out/'queries';qdir.mkdir(exist_ok=True);case_id=0
    for od in ods.itertuples():
        memory_guard(cfg['memory'],projected_additional_gib=2)
        ts=time.perf_counter();ft,fl,_=router.full(int(od.origin_node));rt,rl,_=router.full(int(od.destination_node),True)
        shared_seconds=time.perf_counter()-ts
        travel=ODTravel(int(od.origin_node),int(od.destination_node),ft,fl,rt,rl)
        baseline=travel.leg(travel.origin,travel.destination)
        # Offline distance audit work, explicitly excluded from deploy query timings.
        ts=time.perf_counter();df=graph.single_source_distances(travel.origin,'distance');dr=graph.single_source_distances(travel.destination,'distance','in')
        distance_audit_seconds=time.perf_counter()-ts
        for d,l,direction in [(df,fl,'inbound'),(dr,rl,'outbound')]:
            finite=np.isfinite(l[access]);viol=int(np.sum(d[access][finite]>l[access][finite]+1e-5))
            distance_checks.append(dict(instance_id=int(od.instance_id),direction=direction,checked=int(finite.sum()),violations=viol))
            assert viol==0
        exact_min={}
        for key,ids in members.items():
            if len(ids):exact_min[key]=[float(v[access[ids]].min()) for v in [ft,rt,df,dr]]
        for ratio in cfg['diagnostics']['envelope_ratios']:
            for soc in cfg['diagnostics']['initial_soc']:
                for scenario in ['energy_only','energy_and_scheduled']:
                    schedule=None if scenario=='energy_only' else ScheduledStop(.4*baseline.time_s,.7*baseline.time_s)
                    trip=Trip(travel.origin,travel.destination,soc*60,mobility_budget_s=ratio*baseline.time_s)
                    context=dict(case_id=case_id,instance_id=int(od.instance_id),ratio=ratio,initial_soc=soc,scenario=scenario)
                    ONLINE=True
                    try:
                        incumbent,stats,records,traces,leaves=deploy_search(index,trip,sites,travel,ev,curve,schedule,pc)
                    finally:ONLINE=False
                    d5=index.internal_scans+index.oracle_reads+ORACLE_ACCESS_ATTEMPTS+sum(r['site_ids_read']+r['evaluator_calls']+r['oracle_table_reads'] for r in records)
                    assert d5==0
                    instrument.append(dict(**context,internal_scans=index.internal_scans,oracle_access_attempts=ORACLE_ACCESS_ATTEMPTS,violations=d5))
                    # Clean operational flat comparison, separate from H0 serialization.
                    buckets=[0] if schedule is None else [1,2]
                    all_ids=[s for b in buckets for s in root_ids[b]]
                    flat_start=time.perf_counter()
                    zero=best_one_stop(trip,[],travel,ev,curve,schedule,pc)
                    flat,flat_sem,flat_outside,flat_calls=exact_leaf(all_ids,index,trip,sites,travel,ev,curve,schedule,pc)
                    flat=best(p for p in [zero,flat] if p is not None)
                    flat_seconds=time.perf_counter()-flat_start
                    assert plan_key(flat)==plan_key(incumbent)
                    # All oracle access starts AFTER the online query and timed control.
                    frame=pd.read_parquet(old/'flat_reference'/f'case_{case_id:03d}.parquet')
                    meta=json.loads((old/'flat_reference'/f'case_{case_id:03d}.json').read_text())
                    ref=meta['semantic'];expected=(round(ref['generalized_cost_s'],7),sum(e['charged_kwh'] for e in ref['stops']),len(ref['stops']),tuple(e['site_id'] for e in ref['stops']))
                    match=plan_key(incumbent)==expected
                    comparisons.append(dict(**context,passed=match,cost=incumbent.generalized_cost_s,reference_cost=ref['generalized_cost_s'],selected_action=action_id(incumbent)))
                    if not match:
                        write_json(out/'correctness_failure.json',comparisons[-1]);raise AssertionError('D4 mismatch')
                    semantic=frame[frame.role.ne('')].set_index('site_id',drop=False)
                    assert len(semantic)==flat_sem
                    covered=0
                    for s in semantic.itertuples():
                        membership=[b for b in buckets if bucket_flags(sites[s.site_id])[b]]
                        assert len(membership)==1
                        covered+=1
                    coverage.append(dict(**context,semantic_actions=len(semantic),covered=covered,violations=len(semantic)-covered))
                    # Static child membership equality is audited during preprocessing
                    # and again by acceptance; D1 root coverage thus extends to leaf.
                    audits=[]
                    for r in records:
                        region=r['region'];b=BUCKETS.index(r['bucket']);mins=exact_min[region,b]
                        d2=any(r[k]>v+1e-5 for k,v in zip(['tm','tp','dm','dp'],mins))
                        ids=[site_ids[i] for i in members[region,b] if site_ids[i] in semantic.index]
                        g=semantic.loc[ids]
                        optimum=None if not ids else float(g.cost.min())
                        d3=bool(ids and (r['infeasible'] is not None or r['lower']>optimum+2e-6))
                        oracle=None
                        if ids:
                            oracle=min(oracle_bound(gr,role,trip,ev,curve,schedule,pc)['lower'] for role,gr in g.groupby('role'))
                        audits.append(dict(**r,depth=tree['regions'][region]['depth'],D2_violation=d2,D3_violation=d3,
                            exact_tm=mins[0],exact_tp=mins[1],exact_dm=mins[2],exact_dp=mins[3],semantic_count=len(ids),
                            semantic_minimum=optimum,oracle_lower=oracle,G_cert=None if oracle is None else oracle-r['lower']))
                    adf=pd.DataFrame(audits);adf.to_parquet(qdir/f'audit_{case_id:03d}.parquet',index=False)
                    if adf[['D2_violation','D3_violation']].any().any():
                        adf[adf.D2_violation|adf.D3_violation].to_csv(out/'correctness_failure.csv',index=False)
                        raise AssertionError('D2/D3 violation; interpretation stopped')
                    pd.DataFrame(traces).to_parquet(qdir/f'trace_{case_id:03d}.parquet',index=False)
                    pd.DataFrame(leaves,columns=['region','bucket','candidates','semantic','false_positives','outside_envelope','objective_site_calls']).to_parquet(qdir/f'leaves_{case_id:03d}.parquet',index=False)
                    n=stats.get('exact_site_evaluations',0);ns=stats.get('semantic_site_evaluations',0)
                    metrics.append(dict(**context,**stats,deploy_exact_site_evaluations=n,deploy_semantic_site_evaluations=ns,
                        semantic_flat_sites=len(semantic),flat_static_candidates=len(all_ids),flat_objective_calls=flat_calls,
                        reduction=reduction(n,len(semantic)),semantic_only_reduction=reduction(ns,len(semantic)),
                        operational_reduction=reduction(n,len(all_ids)),false_positive_count=n-ns,
                        shared_routing_seconds=shared_seconds,flat_seconds=flat_seconds,
                        end_to_end_seconds=shared_seconds+stats['search_seconds'],flat_end_to_end_seconds=shared_seconds+flat_seconds,
                        peak_rss_mib=peak_rss_mib()))
                    case_id+=1
        routing_log.append(dict(instance_id=int(od.instance_id),shared_routing_seconds=shared_seconds,distance_offline_audit_seconds=distance_audit_seconds))
        print(f'B1-D OD {od.instance_id}: {case_id}/480, D1–D5 passed',flush=True)
        for name,rows in [('work',metrics),('D1_coverage',coverage),('D4_preservation',comparisons),('D5_instrumentation',instrument)]:
            pd.DataFrame(rows).to_csv(out/f'{name}.csv',index=False)
    pd.DataFrame(routing_log).to_csv(out/'shared_routing.csv',index=False)
    pd.DataFrame(distance_checks).to_csv(out/'distance_vs_fastest_length.csv',index=False)
    write_json(out/'query_completion.json',dict(cases=case_id,passed=True,summary_load_seconds=load_seconds,
        peak_rss_mib=peak_rss_mib(),optional_epsilon_runs='not run',native_routing=router.provenance))
    router.close()


if __name__=='__main__':main()
