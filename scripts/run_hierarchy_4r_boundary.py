"""B1-D2 epsilon-zero experiment; frozen search, boundary time inputs only."""
import json
import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd
from _common import ROOT,configs,load_graph,read_config,sha256
from _stopplan4r_common import write_json,memory_guard,peak_rss_mib
from microplan.routing import ExactRouter
from run_stopplan_4r_diagnostic import ODTravel
from stopplan4r.models import EVModel,PiecewiseChargingCurve,PlannerConfig,ScheduledStop,Trip
from stopplan4r.sites import sites_from_table
from stopplan4r.evaluation import plan_key
from hierarchy4r.deploy import BUCKETS,bucket_flags
from hierarchy4r.deploy_search import DeployIndex,deploy_search
from hierarchy4r.boundary import BoundaryIndex
from hierarchy4r.diagnosis import static_minima,normalized_perfect_static

ONLINE=False

def guard(event,args):
    if ONLINE and event=='open' and isinstance(args[0],(str,bytes)):
        p=str(args[0])
        if any(x in p for x in ['/milestone_4r_b1/','/milestone_4r_b1e/','/milestone_4r_b1d/queries/']):
            raise RuntimeError('Oracle evidence accessed during deployable search: '+p)


def main():
    global ONLINE
    out=ROOT/'results/milestone_4r_b1d2';old=ROOT/'results/milestone_4r_b1';d=ROOT/'results/milestone_4r_b1d'
    assert (out/'preservation_before.json').exists()
    assert '207 passed' in (out/'preexisting_tests.log').read_text()
    assert 'passed' in (out/'boundary_unit_tests.log').read_text() and 'failed' not in (out/'boundary_unit_tests.log').read_text()
    if (out/'experiment_protocol.json').exists():raise FileExistsError('Experiment already started')
    manifest=json.loads((out/'boundary_manifest.json').read_text())
    for p,h in manifest['extraction_code_sha256'].items():assert sha256(ROOT/p)==h
    for p,h in manifest['artifact_sha256'].items():assert sha256(out/p)==h
    assert manifest['F1_violations']==0
    cfg=read_config('configs/stopplan_4r.yaml');mem=memory_guard(cfg['memory'],projected_additional_gib=10)
    write_json(out/'experiment_protocol.json',dict(epsilon=0,cases_expected=480,cost_tolerance=2e-6,metric_tolerance=1e-5,
        boundary_manifest_sha256=sha256(out/'boundary_manifest.json'),numerical_safety_sha256=sha256(out/'numerical_safety.json'),
        timing='One paired pass, same shared OD routing arrays; alternate ALT-first (even case) and BA-first (odd case). No explicit cache flush or warm-up; both indices loaded before pairs. Diagnostic I/O and offline minima excluded.',
        routing='Exactly two shared time/actual-length SSSP calls per OD. Two distance SSSP calls per OD only in offline audit, never exposed to online boundary index.',
        audit_population='Every BA-created nonempty Region/static bucket, including nodes rejected at creation; independently normalized ALT and PS ancestors.',
        no_performance_threshold=True,memory_guard=mem,
        source_sha256={str(p.relative_to(ROOT)):sha256(p) for p in [Path(__file__),ROOT/'src/hierarchy4r/boundary.py',ROOT/'tests/test_hierarchy4r_boundary.py']}))
    graph=load_graph(*configs(cfg['graph_data_config']));router=ExactRouter(graph,cfg,out/'native_cache')
    ev=EVModel(**cfg['ev']);curve=PiecewiseChargingCurve(tuple(map(tuple,cfg['charging']['bands'])));pc=PlannerConfig(**cfg['planner'])
    sites={s.site_id:s for s in sites_from_table(pd.read_parquet(ROOT/'results/milestone_4r/stop_sites.parquet'))}
    tree=json.loads((old/'hierarchy.json').read_text());ids=tree['site_ids'];regions=tree['regions'];parents=[r['parent'] for r in regions]
    access=np.array([sites[s].access_node for s in ids]);flags=np.array([bucket_flags(sites[s]) for s in ids])
    members={(r,b):np.array([i for i in region['members'] if flags[i,b]],int) for r,region in enumerate(regions) for b in range(3)}
    frozen=pd.read_csv(d/'work.csv');leaf_ids={int(p.stem):json.loads(p.read_text()) for p in (d/'leaf_buckets').glob('*.json')}
    # Static refinement preserves exactly the frozen root candidate superset; no case-specific membership enters search.
    for b in range(3):
        root=sorted(ids[i] for i in members[0,b]);leaves=sorted(s for leaf in leaf_ids.values() for s in leaf[BUCKETS[b]])
        assert root==leaves and len(set(leaves))==len(leaves),'Frozen static action coverage failure'
    t=time.perf_counter();alt_index=DeployIndex(d);alt_load=time.perf_counter()-t
    t=time.perf_counter();ba_index=BoundaryIndex(d,out);ba_load=time.perf_counter()-t
    write_json(out/'load_timing.json',dict(ALT_index_load_seconds=alt_load,BA_index_load_seconds=ba_load,boundary_load_seconds=ba_index.boundary_load_seconds))
    parts=out/'b1d2_search_traces';parts.mkdir(exist_ok=True)
    rows=[];timings=[];gates=[];f2s=[];f3s=[];f4s=[];f6s=[]
    sys.addaudithook(guard)
    ods=pd.read_parquet(ROOT/cfg['development_ods']).sort_values('instance_id')
    for od in ods.itertuples():
        memory_guard(cfg['memory'],projected_additional_gib=2)
        t=time.perf_counter();ft,fl,_=router.full(int(od.origin_node));rt,rl,_=router.full(int(od.destination_node),True);routing=time.perf_counter()-t
        travel=ODTravel(int(od.origin_node),int(od.destination_node),ft,fl,rt,rl);baseline=travel.leg(travel.origin,travel.destination)
        ba_index.bind(ft,rt)
        # Separate offline audit preprocessing; these arrays never enter either deployable index.
        df=graph.single_source_distances(travel.origin,'distance');dr=graph.single_source_distances(travel.destination,'distance','in')
        minima,finite=static_minima([ft,rt,df,dr],access,members)
        for c in frozen[frozen.instance_id.eq(od.instance_id)].itertuples():
            context=dict(case_id=c.case_id,instance_id=c.instance_id,ratio=c.ratio,initial_soc=c.initial_soc,scenario=c.scenario)
            sched=None if c.scenario=='energy_only' else ScheduledStop(.4*baseline.time_s,.7*baseline.time_s)
            trip=Trip(travel.origin,travel.destination,c.initial_soc*ev.capacity_kwh,mobility_budget_s=c.ratio*baseline.time_s)
            run={};ONLINE=True
            try:
                for name,index in ([('ALT8',alt_index),('BA',ba_index)] if c.case_id%2==0 else [('BA',ba_index),('ALT8',alt_index)]):
                    run[name]=deploy_search(index,trip,sites,travel,ev,curve,sched,pc,epsilon=0)
            finally:ONLINE=False
            result,stats,records,traces,leaves=run['BA'];alt_result,alt_stats,alt_records,_,_=run['ALT8']
            # Oracle/reference evidence only after both timed deployable calls return.
            ref=json.loads((old/'flat_reference'/f'case_{c.case_id:03d}.json').read_text())['semantic']
            key=(round(ref['generalized_cost_s'],7),sum(s['charged_kwh'] for s in ref['stops']),len(ref['stops']),tuple(s['site_id'] for s in ref['stops']))
            match=result is not None and plan_key(result)==key and abs(result.generalized_cost_s-ref['generalized_cost_s'])<=2e-6
            alt_match=alt_result is not None and plan_key(alt_result)==key
            for k,v in [('bounds',c.bounds),('popped',c.popped),('exact_site_evaluations',c.deploy_exact_site_evaluations),('objective_site_calls',c.objective_site_calls),('semantic_site_evaluations',c.deploy_semantic_site_evaluations)]:
                assert alt_stats.get(k,0)==(0 if pd.isna(v) else v),'Frozen ALT reproduction mismatch: '+k
            gates.append(dict(**context,objective=result.generalized_cost_s if result else None,reference_objective=ref['generalized_cost_s'],
                plan_key=json.dumps(plan_key(result)) if result else None,reference_plan_key=json.dumps(key),objective_equal=match,full_key_equal=match,
                static_action_coverage_preserved=True,F5_mismatches=int(not match),ALT_reproduction_equal=alt_match))
            if not match or not alt_match:
                pd.DataFrame(gates).to_csv(out/'f5_exact_preservation.csv',index=False)
                raise AssertionError('F5 fundamental optimum/tie mismatch; stop')
            frame=pd.read_parquet(old/'flat_reference'/f'case_{c.case_id:03d}.parquet').set_index('site_id')
            costs=frame.loc[frame.role.ne(''),'cost'].reindex(ids).to_numpy();costs=np.where(np.isfinite(costs),costs,np.inf)
            alt_cache={};ps_cache={};points=alt_index.points(trip.origin,trip.destination)
            def normalized_alt(r,b):
                if (r,b) not in alt_cache:
                    parent=-np.inf if parents[r]<0 else normalized_alt(parents[r],b)['lower']
                    alt_cache[r,b]=alt_index.bound(r,b,points,trip,ev,sched,pc,parent)
                return alt_cache[r,b]
            audit=[];counts=dict(F2=0,F3=0,F4=0,F6=0);semnodes=0
            for a in records:
                r=a['region'];b=BUCKETS.index(a['bucket']);exact=minima[r,b]
                al=normalized_alt(r,b);ps=normalized_perfect_static(minima,parents,r,b,trip,ev,sched,pc,ps_cache)
                j=float(costs[members[r,b]].min());target=j if np.isfinite(j) else None;semcount=int(np.isfinite(costs[members[r,b]]).sum())
                f2=int(a['delta_tm']>exact[0]+1e-5 or a['delta_tp']>exact[1]+1e-5 or
                    a['ALT_tm']>a['tm']+1e-5 or a['ALT_tp']>a['tp']+1e-5 or a['tm']>exact[0]+1e-5 or a['tp']>exact[1]+1e-5)
                f3=int(al['lower']>a['lower']+2e-6 or a['lower']>ps['lower']+2e-6)
                f4=int(target is not None and (a['lower']>target+2e-6 or a['infeasible'] is not None))
                f6=int(any(a[k] for k in ['site_ids_read_for_bound','site_evaluator_calls_for_bound','oracle_per_site_reads','additional_sssp_calls']))
                for k,v in zip(counts,[f2,f3,f4,f6]):counts[k]+=v
                semnodes+=int(target is not None)
                den=ps['lower']-al['lower']
                audit.append(dict(**context,**a,depth=regions[r]['depth'],bucket_size=len(members[r,b]),
                    exact_tm=exact[0],exact_tp=exact[1],exact_dm=exact[2],exact_dp=exact[3],
                    L_ALT=al['lower'],L_ALT_raw=al['raw_safe_cost'],L_BA=a['lower'],L_BA_raw=a['raw_safe_cost'],L_PS=ps['lower'],L_PS_raw=ps['raw_safe_cost'],
                    J_sem=target,semantic_count=semcount,H_bound=(a['lower']-al['lower'])/den if target is not None and den>0 else None,
                    G_ALT=None if target is None else target-al['lower'],G_BA=None if target is None else target-a['lower'],G_PS=None if target is None else target-ps['lower'],
                    F2_violations=f2,F3_violations=f3,F4_violations=f4,F6_violations=f6))
            pd.DataFrame(audit).to_parquet(parts/f'audit_{c.case_id:03d}.parquet',index=False)
            pd.DataFrame(traces).to_parquet(parts/f'trace_{c.case_id:03d}.parquet',index=False)
            pd.DataFrame(leaves,columns=['region','bucket','candidates','semantic','false_positives','outside_envelope','objective_site_calls']).to_parquet(parts/f'leaves_{c.case_id:03d}.parquet',index=False)
            for gate,items in [('F2',f2s),('F3',f3s),('F4',f4s),('F6',f6s)]:
                items.append(dict(**context,audited_nodes=len(audit),semantic_nodes=semnodes,false_positive_only_nodes=len(audit)-semnodes,violations=counts[gate]))
            if any(counts.values()):
                write_json(out/'audit_failure.json',dict(**context,**counts))
                raise AssertionError('F2/F3/F4/F6 failed; no performance interpretation')
            decisions=pd.Series([a['decision'] for a in records]).value_counts()
            rows.append(dict(**context,method='BA',regions_created=len(records),regions_popped=stats.get('popped',0),refinements=int(decisions.get('refined',0)),
                leaves=int(decisions.get('leaf',0)),candidate_checks=stats.get('exact_site_evaluations',0),exact_evaluator_calls=stats.get('objective_site_calls',0),
                semantic_evaluations=stats.get('semantic_site_evaluations',0),prune_envelope=int(decisions.get('infeasible_envelope',0)),
                prune_cost=int(decisions.get('cost',0)),
                ingress_reads=sum(a['ingress_reads'] for a in records),egress_reads=sum(a['egress_reads'] for a in records),
                boundary_seconds=sum(a['boundary_seconds'] for a in records),**stats))
            for name in ['ALT8','BA']:
                st=run[name][1]
                timings.append(dict(**context,method=name,pair_position=(0 if (c.case_id%2==0)==(name=='ALT8') else 1),
                    shared_routing_seconds=routing,end_to_end_seconds=routing+st['search_seconds'],
                    boundary_seconds=0. if name=='ALT8' else sum(a['boundary_seconds'] for a in records),
                    **{k:st[k] for k in ['lookup_seconds','bound_seconds','leaf_seconds','refinement_overhead_seconds','search_seconds']}))
        for name,data in [('b1d2_case_work',rows),('timing',timings),('f5_exact_preservation',gates),('f2_boundary_lb_audit',f2s),
            ('f3_alt_ba_ps_ordering',f3s),('f4_ba_cost_admissibility',f4s),('f6_no_hidden_scan',f6s)]:pd.DataFrame(data).to_csv(out/f'{name}.csv',index=False)
        print(f'B1-D2 OD {od.instance_id}: {len(rows)}/480; F2–F6 zero violations',flush=True)
    pd.DataFrame(rows).to_parquet(out/'b1d2_case_work.parquet',index=False)
    for gate in ['f2','f3','f4','f5','f6']:pd.DataFrame(columns=['case_id','region','bucket','violation']).to_csv(out/f'{gate}_violations.csv',index=False)
    write_json(out/'experiment_completion.json',dict(cases=len(rows),F2_F6_violations=0,peak_rss_mib=peak_rss_mib(),shared_time_sssp_calls=60,offline_distance_sssp_calls=60))
    router.close()

if __name__=='__main__':main()
