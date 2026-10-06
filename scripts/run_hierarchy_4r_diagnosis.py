"""B1-E offline diagnosis of frozen B1-D v1. No algorithm edits or tuning."""
import json
import sys
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
from hierarchy4r.deploy import BUCKETS,bucket_flags
from hierarchy4r.deploy_search import deploy_search
from hierarchy4r.diagnosis import (AUDIT_TOL,CATEGORIES,flat_baseline,static_minima,PerfectStaticIndex,
    normalized_perfect_static,decompose,terminal_category,incumbent_diagnosis,pop_order)

IN_FLAT=False


def guard(event,args):
    if IN_FLAT and event=='open' and isinstance(args[0],(str,bytes)):
        path=str(args[0])
        if '/milestone_4r_b1/' in path or '/milestone_4r_b1d/queries/' in path:
            raise RuntimeError('Oracle input accessed during flat baseline')


def main():
    global IN_FLAT
    out=ROOT/'results/milestone_4r_b1e';old=ROOT/'results/milestone_4r_b1';d=ROOT/'results/milestone_4r_b1d'
    assert (out/'preservation_before.json').exists()
    if (out/'diagnostic_protocol.json').exists():raise FileExistsError('Diagnostic run already started')
    cfg=read_config('configs/stopplan_4r.yaml')
    mem=memory_guard(cfg['memory'],projected_additional_gib=10)
    write_json(out/'diagnostic_protocol.json',dict(epsilon=0,cost_audit_tolerance=AUDIT_TOL,
        gap_identity_tolerance=AUDIT_TOL,metric_reproduction_tolerance=1e-5,
        population='All 480 cases; all frozen ALT8 visited Region/buckets, plus all PS replay nodes for admissibility',
        timing='No new deployable timing claims. Retain original paired B1-D timings; unrecorded envelope/exact splits and time-to-incumbent are NA.',
        incumbent_counts='Through the first successful leaf batch, including that pop and all batch checks; no Site update remains NA. Zero-stop finite U distinguished from first Site improvement.',
        region_count='N_region = popped Region/bucket nodes; created nonempty nodes and bounds also reported',
        memory_guard=mem,source_sha256={str(p.relative_to(ROOT)):sha256(p) for p in [Path(__file__),ROOT/'src/hierarchy4r/diagnosis.py']}))
    graph=load_graph(*configs(cfg['graph_data_config']));router=ExactRouter(graph,cfg,out/'native_cache')
    ev=EVModel(**cfg['ev']);curve=PiecewiseChargingCurve(tuple(map(tuple,cfg['charging']['bands'])))
    pc=PlannerConfig(**cfg['planner'])
    sites={s.site_id:s for s in sites_from_table(pd.read_parquet(ROOT/'results/milestone_4r/stop_sites.parquet'))}
    tree=json.loads((old/'hierarchy.json').read_text());ids=tree['site_ids'];regions=tree['regions']
    access=np.array([sites[s].access_node for s in ids]);flags=np.array([bucket_flags(sites[s]) for s in ids])
    parents=[r['parent'] for r in regions];children=np.load(d/'children.npy');counts=np.load(d/'counts.npy')
    members={(r,b):np.array([i for i in region['members'] if flags[i,b]],int)
        for r,region in enumerate(regions) for b in range(3)}
    root={b:[ids[i] for i in members[0,b]] for b in range(3)}
    leaf_ids={int(p.stem):json.loads(p.read_text()) for p in (d/'leaf_buckets').glob('*.json')}
    frozen_work=pd.read_csv(d/'work.csv');oracle_work=pd.read_csv(old/'logical_work.csv').query('epsilon == 0').set_index('case_id')
    ods=pd.read_parquet(ROOT/cfg['development_ods']).sort_values('instance_id')
    parts=out/'cases';parts.mkdir(exist_ok=True)
    flat_rows=[];hier_rows=[];ps_rows=[];levels=[];incumbents=[];gate_rows=[];fp_counts=[]
    sys.addaudithook(guard)
    for od in ods.itertuples():
        memory_guard(cfg['memory'],projected_additional_gib=2)
        ft,fl,_=router.full(int(od.origin_node));rt,rl,_=router.full(int(od.destination_node),True)
        travel=ODTravel(int(od.origin_node),int(od.destination_node),ft,fl,rt,rl)
        baseline=travel.leg(travel.origin,travel.destination)
        df=graph.single_source_distances(travel.origin,'distance');dr=graph.single_source_distances(travel.destination,'distance','in')
        minima,finite=static_minima([ft,rt,df,dr],access,members)
        for c in frozen_work[frozen_work.instance_id.eq(od.instance_id)].itertuples():
            context=dict(case_id=c.case_id,instance_id=c.instance_id,ratio=c.ratio,initial_soc=c.initial_soc,scenario=c.scenario)
            sched=None if c.scenario=='energy_only' else ScheduledStop(.4*baseline.time_s,.7*baseline.time_s)
            trip=Trip(travel.origin,travel.destination,c.initial_soc*ev.capacity_kwh,mobility_budget_s=c.ratio*baseline.time_s)
            buckets=[0] if sched is None else [1,2];candidates=[s for b in buckets for s in root[b]]
            IN_FLAT=True
            try:flat,w=flat_baseline(candidates,trip,sites,travel,ev,curve,sched,pc)
            finally:IN_FLAT=False
            # Oracle evidence is accessed only after the deployable flat call.
            meta=json.loads((old/'flat_reference'/f'case_{c.case_id:03d}.json').read_text())
            ref=meta['semantic']
            key=(round(ref['generalized_cost_s'],7),sum(s['charged_kwh'] for s in ref['stops']),len(ref['stops']),tuple(s['site_id'] for s in ref['stops']))
            assert plan_key(flat)==key,'E1 flat optimum/tie discrepancy'
            assert (w['N_envelope'],w['N_exact'],w['N_semantic'])==(c.flat_static_candidates,c.flat_objective_calls,c.semantic_flat_sites),'E1 workload discrepancy'
            flat_rows.append(dict(**context,**w,T_bound=0.,T_envelope=None,T_exact=None,T_search=c.flat_seconds,T_e2e=c.flat_end_to_end_seconds,
                timing_source='frozen_B1D_paired_control',E1_discrepancies=0))
            hier_rows.append(dict(**context,N_region=c.popped,N_bound=c.bounds,N_envelope=c.deploy_exact_site_evaluations,
                N_exact=0 if pd.isna(c.objective_site_calls) else int(c.objective_site_calls),N_semantic=c.deploy_semantic_site_evaluations,
                T_bound=c.bound_seconds,T_envelope=None,T_exact=None,T_search=c.search_seconds,T_e2e=c.end_to_end_seconds,
                T_lookup=c.lookup_seconds,T_refinement=c.refinement_overhead_seconds,T_leaf_combined=c.leaf_seconds,
                timing_source='frozen_B1D_primary'))
            frame=pd.read_parquet(old/'flat_reference'/f'case_{c.case_id:03d}.parquet').set_index('site_id')
            costs=frame.loc[frame.role.ne(''),'cost'].reindex(ids).to_numpy()
            costs=np.where(np.isfinite(costs),costs,np.inf)
            cache={};aud=pd.read_parquet(d/'queries'/f'audit_{c.case_id:03d}.parquet')
            certificate=[];metric_rows=[];e2=e3=e4=0
            for a in aud.itertuples():
                r=a.region;b=BUCKETS.index(a.bucket)
                ps=normalized_perfect_static(minima,parents,r,b,trip,ev,sched,pc,cache)
                j=float(costs[members[r,b]].min())
                target=j if np.isfinite(j) else None
                assert (target is None)==pd.isna(a.semantic_minimum)
                if target is not None:assert abs(target-a.semantic_minimum)<=AUDIT_TOL
                e2+=int(target is not None and (ps['lower']>target+AUDIT_TOL or ps['infeasible'] is not None))
                e3+=int(a.lower>ps['lower']+AUDIT_TOL)
                gaps=decompose(a.lower,ps['lower'],target)
                e4+=int(target is not None and abs(gaps['identity_error'])>AUDIT_TOL)
                certificate.append(dict(**context,region=r,bucket=a.bucket,depth=a.depth,bucket_size=int(counts[r,b]),
                    L_ALT=a.lower,L_ALT_raw=a.raw_safe_cost,L_PS=ps['lower'],L_PS_raw=ps['raw_safe_cost'],
                    PS_infeasible=ps['infeasible'],J_sem=target,semantic_count=a.semantic_count,
                    G_cert_old=a.G_cert,oracle_lower_old=a.oracle_lower,**gaps))
                row=dict(**context,region=r,bucket=a.bucket,depth=a.depth,bucket_size=int(counts[r,b]))
                for i,k in enumerate(['tm','tp','dm','dp']):
                    assert np.isclose(minima[r,b,i],getattr(a,'exact_'+k),rtol=0,atol=1e-5)
                    row['exact_'+k]=minima[r,b,i];row['ALT_'+k]=getattr(a,k)
                    row['finite_'+k]=int(finite[r,b,i]);row['unreachable_'+k]=int(counts[r,b]-finite[r,b,i])
                metric_rows.append(row)
            if e2 or e3 or e4:
                write_json(out/'audit_failure.json',dict(**context,E2=e2,E3=e3,E4=e4))
                raise AssertionError('Certificate gate failed; no interpretation')
            pd.DataFrame(certificate).to_parquet(parts/f'certificate_{c.case_id:03d}.parquet',index=False)
            pd.DataFrame(metric_rows).to_parquet(parts/f'minima_{c.case_id:03d}.parquet',index=False)
            # Exact same frozen search and leaf functions, different diagnostic index only.
            ps_index=PerfectStaticIndex(d,minima)
            result,stats,records,traces,leaves=deploy_search(ps_index,trip,sites,travel,ev,curve,sched,pc)
            assert plan_key(result)==key,'Perfect-static replay optimum/tie mismatch'
            for r in records:
                b=BUCKETS.index(r['bucket']);i=r['region'];j=costs[members[i,b]].min()
                p=normalized_perfect_static(minima,parents,i,b,trip,ev,sched,pc,cache)
                assert r['lower']==p['lower'],'Inconsistent monotone normalization'
                if np.isfinite(j):
                    assert r['infeasible'] is None and r['lower']<=j+AUDIT_TOL,'E2 replay bound inadmissible'
            pd.DataFrame(records).to_parquet(parts/f'ps_bounds_{c.case_id:03d}.parquet',index=False)
            pd.DataFrame(traces).to_parquet(parts/f'ps_trace_{c.case_id:03d}.parquet',index=False)
            pd.DataFrame(leaves).to_parquet(parts/f'ps_leaves_{c.case_id:03d}.parquet',index=False)
            ps_rows.append(dict(**context,N_region=stats.get('popped',0),N_bound=stats.get('bounds',0),
                N_envelope=stats.get('exact_site_evaluations',0),N_exact=stats.get('objective_site_calls',0),
                N_semantic=stats.get('semantic_site_evaluations',0),cost=result.generalized_cost_s,diagnostic_only=True,optimum_match=True))
            paid=pd.read_parquet(d/'queries'/f'leaves_{c.case_id:03d}.parquet')
            categories=[]
            for leaf in paid.itertuples():
                for site_id in leaf_ids[leaf.region][leaf.bucket]:
                    f=frame.loc[site_id] if site_id in frame.index else None
                    feasible=False if f is None else bool(f.feasible);role='' if f is None else f.role
                    category,reason=terminal_category(sites[site_id],trip,travel,ev,curve,sched,pc,feasible,role)
                    categories.append(dict(**context,site_id=site_id,region=leaf.region,bucket=leaf.bucket,
                        depth=regions[leaf.region]['depth'],category=category,reason=reason))
            cats=pd.DataFrame(categories,columns=list(context)+['site_id','region','bucket','depth','category','reason'])
            assert not cats.site_id.duplicated().any()
            totals={k:int(cats.category.eq(k).sum()) for k in CATEGORIES}
            assert sum(totals.values())==c.deploy_exact_site_evaluations,'E5 candidate mismatch'
            assert totals['TP']==c.deploy_semantic_site_evaluations,'E5 semantic mismatch'
            assert totals['FP1']==(0 if pd.isna(c.outside_envelope) else c.outside_envelope),'E5 envelope mismatch'
            cats.to_parquet(parts/f'classification_{c.case_id:03d}.parquet',index=False)
            fp_counts.append(dict(**context,**totals,total=sum(totals.values()),E5_discrepancies=0))
            trace=pd.read_parquet(d/'queries'/f'trace_{c.case_id:03d}.parquet').to_dict('records')
            zero=best_one_stop(trip,[],travel,ev,curve,sched,pc)
            inc=incumbent_diagnosis(aud.to_dict('records'),trace,paid.to_dict('records'),children,
                None if zero is None else zero.generalized_cost_s,flat.generalized_cost_s)
            incumbents.append(dict(**context,**inc))
            # Comparable nonempty created nodes; oracle work is logical, not paid online work.
            for name,rec,st,checks,exact,semantic in [
                ('ALT8',aud.to_dict('records'),dict(popped=c.popped),c.deploy_exact_site_evaluations,
                 0 if pd.isna(c.objective_site_calls) else c.objective_site_calls,c.deploy_semantic_site_evaluations),
                ('perfect_static',records,stats,stats.get('exact_site_evaluations',0),stats.get('objective_site_calls',0),stats.get('semantic_site_evaluations',0))]:
                decisions=pd.Series([r['decision'] for r in rec],dtype=str).value_counts()
                depth=[regions[r['region']]['depth'] for r in rec]
                levels.append(dict(**context,method=name,regions_created=len(rec),regions_popped=st.get('popped',0),
                    refinements=int(decisions.get('refined',0)),leaves=int(decisions.get('leaf',0)),candidate_checks=checks,
                    exact_evaluator_calls=exact,semantic_evaluations=semantic,max_depth=max(depth,default=0),
                    median_depth=None if not depth else float(np.median(depth)),work_basis='paid' if name=='ALT8' else 'offline_counterfactual',
                    prune_cost=int(decisions.get('cost',0)),prune_envelope=int(decisions.get('infeasible_envelope',0)),
                    prune_energy=sum(int(v) for k,v in decisions.items() if 'energy' in k),
                    prune_schedule=int(decisions.get('infeasible_schedule',0))))
            o=oracle_work.loc[c.case_id];views=pd.read_parquet(old/'oracle_epsilon_0'/f'views_{c.case_id:03d}.parquet')
            levels.append(dict(**context,method='B1O',regions_created=o.bounds_computed,regions_popped=o.views_popped,
                creation_attempts_including_empty=o.views_created,refinements=o.refined,leaves=o.leaves,
                candidate_checks=o.logical_site_evaluations,exact_evaluator_calls=o.logical_site_evaluations,
                semantic_evaluations=o.logical_site_evaluations,max_depth=0 if views.empty else int(views.depth.max()),
                median_depth=None if views.empty else float(views.depth.median()),work_basis='logical_oracle_excludes_summary_scan',
                prune_cost=o.pruned,prune_envelope=0,prune_energy=0,prune_schedule=0))
            gate_rows.append(dict(**context,E1=0,E2=e2,E3=e3,E4=e4,E5=0,ALT_nodes=len(aud),PS_nodes=len(records)))
        for name,rows in [('deployable_flat_work',flat_rows),('deployable_hier_work',hier_rows),
            ('perfect_static_case_work',ps_rows),('three_level_work_comparison',levels),
            ('incumbent_acquisition',incumbents),('E1_E5_audit',gate_rows),('false_positive_case_counts',fp_counts)]:
            pd.DataFrame(rows).to_csv(out/f'{name}.csv',index=False)
        print(f'B1-E OD {od.instance_id}: {len(flat_rows)}/480 cases; E1–E5 zero violations',flush=True)
    write_json(out/'diagnostic_completion.json',dict(cases=len(flat_rows),E1_E5_violations=0,
        peak_rss_mib=peak_rss_mib(),timing_diagnosis='limited: historical paired totals only; split times and first-incumbent times NA'))
    router.close()


if __name__=='__main__':main()
