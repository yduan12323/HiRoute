"""Descriptive B1-D2 analysis after all online correctness checks succeed."""
import json
import time
from pathlib import Path
import numpy as np
import pandas as pd
from _common import ROOT,sha256
from _stopplan4r_common import write_json
from hierarchy4r.deploy import BUCKETS,alt
from hierarchy4r.deploy_search import DeployIndex

CONTEXT=['case_id','instance_id','ratio','initial_soc','scenario']
COMPONENTS=['regions_created','regions_popped','refinements','leaves','candidate_checks','exact_evaluator_calls','semantic_evaluations']


def describe(values):
    v=pd.Series(values,dtype=float).dropna()
    return dict(defined=len(v),median=None if v.empty else float(v.median()),p25=None if v.empty else float(v.quantile(.25)),
        p75=None if v.empty else float(v.quantile(.75)),p95=None if v.empty else float(v.quantile(.95)),
        minimum=None if v.empty else float(v.min()),maximum=None if v.empty else float(v.max()))


def strata(frame,fields):
    rows=[]
    for dim in ['all','depth','bucket','scenario','instance_id','ratio','initial_soc']:
        groups=[('all',frame)] if dim=='all' else frame.groupby(dim)
        for value,g in groups:
            for field in fields:rows.append(dict(dimension=dim,value=str(value),metric=field,nodes=len(g),**describe(g[field])))
    return pd.DataFrame(rows)


def main():
    out=ROOT/'results/milestone_4r_b1d2';d=ROOT/'results/milestone_4r_b1d';e=ROOT/'results/milestone_4r_b1e';old=ROOT/'results/milestone_4r_b1'
    assert json.loads((out/'experiment_completion.json').read_text())['cases']==480
    ba=pd.read_csv(out/'b1d2_case_work.csv');assert len(ba)==480
    ba['outside_envelope']=ba.outside_envelope.fillna(0)
    audit=pd.concat([pd.read_parquet(out/'b1d2_search_traces'/f'audit_{c:03d}.parquet') for c in range(480)],ignore_index=True)
    assert not audit[['F2_violations','F3_violations','F4_violations','F6_violations']].any().any()
    audit.to_parquet(out/'alt_ba_ps_bound_audit.parquet',index=False)
    audit[CONTEXT+['region','bucket','depth','semantic_count','J_sem','L_ALT','L_BA','L_PS','H_bound']].to_parquet(out/'bound_headroom_recovery.parquet',index=False)
    semantic=audit[audit.J_sem.notna()].copy()
    strata(semantic,['H_bound']).to_csv(out/'bound_headroom_strata.csv',index=False)
    audit[CONTEXT+['region','bucket','depth','semantic_count','J_sem','L_ALT','L_BA','L_PS','G_ALT','G_BA','G_PS']].to_parquet(out/'ba_residual_gap.parquet',index=False)
    strata(semantic,['G_ALT','G_BA','G_PS']).to_csv(out/'ba_residual_gap_strata.csv',index=False)
    oldlevels=pd.read_csv(e/'three_level_work_comparison.csv');oldlevels=oldlevels[oldlevels.method.isin(['ALT8','perfect_static'])].copy()
    levels=pd.concat([oldlevels[CONTEXT+['method']+COMPONENTS+['prune_envelope','prune_cost']],ba[CONTEXT+['method']+COMPONENTS+['prune_envelope','prune_cost']]],ignore_index=True).sort_values(['case_id','method'])
    levels.to_csv(out/'three_level_work_comparison.csv',index=False)
    totals=levels.groupby('method')[COMPONENTS+['prune_envelope','prune_cost']].sum().astype(int)
    totals.to_csv(out/'three_level_work_totals.csv')
    work=[];work_summary={}
    for field in ['candidate_checks','exact_evaluator_calls','refinements']:
        p=levels.pivot(index='case_id',columns='method',values=field)
        denominator=p.ALT8-p.perfect_static
        h=(p.ALT8-p.BA)/denominator.where(denominator>0)
        for case,v in p.iterrows():work.append(dict(case_id=int(case),component=field,ALT=int(v.ALT8),BA=int(v.BA),PS=int(v.perfect_static),H_work=h.loc[case]))
        den=int(totals.loc['ALT8',field]-totals.loc['perfect_static',field])
        work_summary[field]=dict(**describe(h),micro=None if den<=0 else float((totals.loc['ALT8',field]-totals.loc['BA',field])/den))
    pd.DataFrame(work).merge(ba[CONTEXT],on='case_id').to_csv(out/'work_headroom_recovery.csv',index=False)
    # Exact candidate-ID reconciliation. Only frozen ALT FP1 checks are the denominator.
    fp=pd.read_parquet(e/'leaf_candidate_classification.parquet');fp=fp[fp.category.eq('FP1')]
    leaf_ids={int(p.stem):json.loads(p.read_text()) for p in (d/'leaf_buckets').glob('*.json')}
    regions=json.loads((old/'hierarchy.json').read_text())['regions'];parents=[r['parent'] for r in regions]
    witnesses=[];migration=[];new_rejects=[]
    for c in range(480):
        b=ba[ba.case_id.eq(c)].iloc[0];context={k:b[k] for k in CONTEXT}
        bounds=audit[audit.case_id.eq(c)];decisions={(a.region,a.bucket):(a.decision,a.depth) for a in bounds.itertuples()}
        leaves=pd.read_parquet(out/'b1d2_search_traces'/f'leaves_{c:03d}.parquet')
        paid={s for leaf in leaves.itertuples() for s in leaf_ids[leaf.region][leaf.bucket]}
        oldfp=fp[fp.case_id.eq(c)];oldset=set(oldfp.site_id)
        avoided=0
        for f in oldfp.itertuples():
            if f.site_id in paid:continue
            avoided+=1;r=f.region
            while (r,f.bucket) not in decisions:
                r=parents[r];assert r>=0
            reason,depth=decisions[r,f.bucket]
            assert reason not in ['leaf','refined','open'],'Candidate missing without terminal ancestor'
            witnesses.append(dict(**context,site_id=f.site_id,bucket=f.bucket,ALT_leaf=f.region,ALT_depth=f.depth,
                BA_terminal_region=r,BA_terminal_depth=depth,BA_reason=reason,upward_depth=f.depth-depth))
        # Direct envelope recheck of BA-paid IDs, purely offline and from frozen H0 membership:
        # H0 frame enumerates every envelope-eligible attached Site, including concrete infeasible ones.
        eligible=set(pd.read_parquet(old/'flat_reference'/f'case_{c:03d}.parquet',columns=['site_id']).site_id)
        ba_fp1=paid-eligible
        assert len(ba_fp1)==int(b.get('outside_envelope',0) or 0)
        added=len(ba_fp1-oldset);retained=len(ba_fp1&oldset)
        assert retained+avoided==len(oldfp)
        for s in sorted(ba_fp1-oldset):new_rejects.append(dict(**context,site_id=s))
        al=levels[(levels.case_id==c)&(levels.method=='ALT8')].iloc[0]
        migration.append(dict(**context,ALT_region_envelope_prunes=int(al.prune_envelope),BA_region_envelope_prunes=int(b.prune_envelope),
            ALT_leaf_envelope_rejects=len(oldfp),BA_leaf_envelope_rejects=len(ba_fp1),former_ALT_FP1_avoided=avoided,
            former_ALT_FP1_retained=retained,new_BA_FP1=added,fraction_avoided=None if not len(oldfp) else avoided/len(oldfp)))
    witness=pd.DataFrame(witnesses);witness.to_parquet(out/'envelope_pruning_migration_witnesses.parquet',index=False)
    pd.DataFrame(new_rejects,columns=CONTEXT+['site_id']).to_parquet(out/'new_BA_envelope_rejects.parquet',index=False)
    migration=pd.DataFrame(migration);migration.to_csv(out/'envelope_pruning_migration.csv',index=False)
    ms=[];countcols=['ALT_region_envelope_prunes','BA_region_envelope_prunes','ALT_leaf_envelope_rejects','BA_leaf_envelope_rejects','former_ALT_FP1_avoided','former_ALT_FP1_retained','new_BA_FP1']
    for dim in ['all','instance_id','initial_soc','ratio','scenario']:
        for value,g in ([('all',migration)] if dim=='all' else migration.groupby(dim)):
            sums={k:int(g[k].sum()) for k in countcols};den=sums['ALT_leaf_envelope_rejects']
            ms.append(dict(dimension=dim,value=str(value),**sums,fraction_avoided=None if not den else sums['former_ALT_FP1_avoided']/den))
    pd.DataFrame(ms).to_csv(out/'envelope_pruning_migration_strata.csv',index=False)
    witness.groupby(['BA_terminal_depth','BA_reason','upward_depth']).size().rename('avoided_ALT_FP1_checks').reset_index().to_csv(out/'envelope_pruning_depth_distribution.csv',index=False)
    # Work remains componentwise. One boundary read is never equated to a Site check.
    reads=audit.groupby(['case_id','region'])[['ingress_reads','egress_reads']].sum();reads['total']=reads.sum(axis=1)
    manifest=json.loads((out/'boundary_manifest.json').read_text())
    accounting=ba[CONTEXT+['ingress_reads','egress_reads','boundary_seconds','bound_seconds','candidate_checks','exact_evaluator_calls']].copy()
    accounting['boundary_reads']=accounting.ingress_reads+accounting.egress_reads
    altwork=levels[levels.method.eq('ALT8')].set_index('case_id')
    for field,label in [('candidate_checks','envelope'),('exact_evaluator_calls','exact')]:
        accounting[label+'_avoided']=accounting.case_id.map(altwork[field])-accounting[field]
        accounting['reads_per_'+label+'_avoided']=accounting.boundary_reads/accounting[label+'_avoided'].where(accounting[label+'_avoided']>0)
    accounting['boundary_fraction_of_bound_time']=accounting.boundary_seconds/accounting.bound_seconds
    accounting.to_csv(out/'boundary_work_accounting.csv',index=False)
    boundaries=dict(ingress_reads=int(audit.ingress_reads.sum()),egress_reads=int(audit.egress_reads.sum()),total_reads=int(reads.total.sum()),
        reads_per_visited_region=describe(reads.total),boundary_lookup_seconds=float(audit.boundary_seconds.sum()),
        fraction_bound_time=float(audit.boundary_seconds.sum()/ba.bound_seconds.sum()),artifact_storage_bytes=manifest['storage_bytes'],
        preprocessing_seconds=manifest['seconds'],preprocessing_peak_rss_mib=manifest['peak_rss_mib'])
    for field,label in [('candidate_checks','envelope'),('exact_evaluator_calls','exact')]:
        den=int(totals.loc['ALT8',field]-totals.loc['BA',field]);boundaries['reads_per_'+label+'_avoided']=None if den<=0 else boundaries['total_reads']/den
    write_json(out/'boundary_work_accounting.json',boundaries)
    # Separate isolated metric-lookup replay. This is a descriptive microprofile, not inserted into paired search timing.
    # Both methods call the same four ALT functions with their own visited Region/bucket population.
    profile=[];index=DeployIndex(d)
    write_json(out/'lookup_profile_protocol.json',dict(policy='Single isolated lookup replay; alternate ALT8/BA order by case; four frozen alt() calls per visited node; no SSSP, cost formula or search. Microprofile separate from uninstrumented paired totals.',
        source_sha256=sha256(Path(__file__))))
    for c in range(480):
        meta=json.loads((old/'flat_reference'/f'case_{c:03d}.json').read_text());trip=meta['trip']
        points=index.points(trip['origin'],trip['destination']);o,z=points
        own={'ALT8':pd.read_parquet(d/'queries'/f'audit_{c:03d}.parquet',columns=['region','bucket']),
             'BA':audit.loc[audit.case_id.eq(c),['region','bucket']]}
        for method in (['ALT8','BA'] if c%2==0 else ['BA','ALT8']):
            nodes=[(int(a.region),BUCKETS.index(a.bucket)) for a in own[method].itertuples()]
            start=time.perf_counter()
            for r,b in nodes:
                s=index.summary[r,b]
                alt(s[0],o[0]);alt(s[0],z[0],True);alt(s[1],o[1]);alt(s[1],z[1],True)
            profile.append(dict(case_id=c,method=method,ALT_metric_lookup_replay_seconds=time.perf_counter()-start,metric_calls=4*len(nodes)))
    pd.DataFrame(profile).to_csv(out/'alt_lookup_microprofile.csv',index=False)
    timing=pd.read_csv(out/'timing.csv');timing=timing.merge(pd.DataFrame(profile),on=['case_id','method'])
    timing.to_csv(out/'timing.csv',index=False)
    tsummary={}
    for method,g in timing.groupby('method'):
        tsummary[method]={k:dict(total=float(g[k].sum()),**describe(g[k])) for k in g.columns if k.endswith('_seconds')}
    paired=timing.pivot(index='case_id',columns='method',values='search_seconds')
    tsummary['search_ratio_BA_over_ALT']=dict(aggregate=float(paired.BA.sum()/paired.ALT8.sum()),**describe(paired.BA/paired.ALT8))
    # Per-case e2e charges the full OD routing time to each query. Unique OD route total is separately reported.
    tsummary['unique_OD_shared_routing_seconds']=float(timing.drop_duplicates('instance_id').shared_routing_seconds.sum())
    tsummary['preprocessing']=dict(boundary_seconds=manifest['seconds'],peak_rss_mib=manifest['peak_rss_mib'],**json.loads((out/'load_timing.json').read_text()))
    tsummary['limitations']='One alternating paired pass, no cold-cache enforcement; routing shared across 16 cases per OD. ALT metric lookup microprofile is isolated replay and must not be subtracted from paired bound time. PS runtime excluded.'
    write_json(out/'timing_summary.json',tsummary)
    summary=dict(cases=480,audited_BA_nodes=len(audit),semantic_populated_nodes=len(semantic),false_positive_only_nodes=len(audit)-len(semantic),
        work_totals={m:{k:int(v) for k,v in row.items()} for m,row in totals.to_dict('index').items()},
        H_bound=describe(semantic.H_bound),H_work=work_summary,boundary=boundaries,
        residual={k:describe(semantic[k]) for k in ['G_ALT','G_BA','G_PS']},
        envelope=ms[0],upward_depth=describe(witness.upward_depth),timing=tsummary)
    write_json(out/'descriptive_summary.json',summary)
    print(json.dumps({k:summary[k] for k in ['cases','audited_BA_nodes','work_totals','H_bound','H_work','envelope']},indent=2))

if __name__=='__main__':main()
