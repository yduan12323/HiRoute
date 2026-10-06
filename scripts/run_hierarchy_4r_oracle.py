"""Frozen B1-O experiment, exact primary first, then declared epsilon grid."""
import json
import time
from dataclasses import fields
import numpy as np
import pandas as pd
from _common import ROOT, sha256, read_config
from _stopplan4r_common import write_json, memory_guard, peak_rss_mib
from stopplan4r.models import EVModel, PiecewiseChargingCurve, PlannerConfig, ScheduledStop, Trip, TravelLeg
from stopplan4r.sites import sites_from_table
from stopplan4r.evaluation import plan_key
from hierarchy4r.domain import require_h0, action_id, ROLES
from hierarchy4r.tree import validate_tree, tree_hash
from hierarchy4r.search import search
from hierarchy4r.bounds import SAFE_TAU, CHECK_TIME_TOL, CHECK_ENERGY_TOL


class ReferenceTravel:
    """Verified H0 native fastest-leg labels. Shared routing already paid in H0."""
    def __init__(self, meta, frame):
        self.trip=Trip(**meta['trip']);self.baseline=TravelLeg(**meta['baseline'])
        self.labels={int(r.access_node):(TravelLeg(r.tm,r.lm),TravelLeg(r.tp,r.lp)) for r in frame.itertuples()}

    def leg(self, source, target):
        if source==self.trip.origin and target==self.trip.destination:return self.baseline
        if source==self.trip.origin:return self.labels[target][0]
        if target==self.trip.destination:return self.labels[source][1]
        raise ValueError('Outside declared one-stop domain')


def key_from_record(p):
    return (round(p['generalized_cost_s'],7),sum(e['charged_kwh'] for e in p['stops']),
            len(p['stops']),tuple(e['site_id'] for e in p['stops']))


def check_semantic_coverage(tree, frame):
    lookup=dict(zip(frame.site_id,frame.role))
    membership=np.array([ROLES.index(lookup[s])+1 if lookup.get(s) in ROLES else 0 for s in tree['site_ids']])
    counts=[]
    for n in tree['regions']:
        counts.append(np.bincount(membership[n['members']],minlength=4)[1:])
    lost=duplicates=0
    for n,own in zip(tree['regions'],counts):
        if n['children']:
            combined=sum((counts[c] for c in n['children']))
            lost+=int(np.maximum(own-combined,0).sum())
            duplicates+=int(np.maximum(combined-own,0).sum())
    assert int(counts[0].sum())==int(frame.role.isin(ROLES).sum())
    return lost,duplicates


def main():
    out=ROOT/'results/milestone_4r_b1'
    h0=json.loads((out/'h0_summary.json').read_text());require_h0(h0)
    if (out/'oracle_preregistration.json').exists():
        raise FileExistsError('Comparative run already started; preserve previous evidence')
    manifest=json.loads((out/'hierarchy_preregistration.json').read_text())
    tree=json.loads((out/'hierarchy.json').read_text());validate_tree(tree)
    assert tree_hash(tree)==manifest['hierarchy_sha256']
    for p,h in h0['reference_sha256'].items():assert sha256(out/p)==h,p
    cfg=read_config('configs/stopplan_4r.yaml')
    ev=EVModel(**cfg['ev']);curve=PiecewiseChargingCurve(tuple(map(tuple,cfg['charging']['bands'])))
    pc=PlannerConfig(**cfg['planner'])
    sites={s.site_id:s for s in sites_from_table(pd.read_parquet(ROOT/'results/milestone_4r/stop_sites.parquet'))}
    migration=pd.read_parquet(out/'h0_domain_migration.parquet')
    assert len(migration)==480
    prereg=dict(hierarchy_sha256=tree_hash(tree),epsilon_grid=[0,30,60,120],safe_lower_adjustment_s=SAFE_TAU,
        verification_energy_tolerance_kwh=CHECK_ENERGY_TOL,verification_time_tolerance_s=CHECK_TIME_TOL,
        effect_tolerance_kwh=1e-8,cost_ties='accepted round(cost,7), then charge/count/identity',
        margin_comparison='no added margin tolerance; negative slack is inconclusive',
        no_semantic_sites='reduction undefined; would stop classification for clarification (never use legacy counts)',
        scope='oracle logical Site-evaluation reduction potential only; all role/feasibility/summary work was prepaid',
        source_sha256={str(p.relative_to(ROOT)):sha256(p) for p in [*sorted((ROOT/'src/hierarchy4r').glob('*.py')),__import__('pathlib').Path(__file__)]})
    write_json(out/'oracle_preregistration.json',prereg)
    metrics=[];role_metrics=[];stability=[];h4=[];h2=[];all_runtime=[]
    for eps in prereg['epsilon_grid']:
        if eps and not json.loads((out/'primary_gates.json').read_text())['passed']:
            raise RuntimeError('Exact primary gates required before epsilon sensitivity')
        stage=out/f'oracle_epsilon_{eps}';stage.mkdir(exist_ok=False)
        start=time.perf_counter()
        for c in migration.itertuples():
            memory_guard(cfg['memory'],projected_additional_gib=1)
            frame=pd.read_parquet(out/'flat_reference'/f'case_{c.case_id:03d}.parquet')
            meta=json.loads((out/'flat_reference'/f'case_{c.case_id:03d}.json').read_text())
            travel=ReferenceTravel(meta,frame);trip=travel.trip
            schedule=None if meta['schedule'] is None else ScheduledStop(**meta['schedule'])
            ts=time.perf_counter()
            incumbent,work,diagnostics,traces,coverage,roles=search(tree,frame,trip,sites,travel,ev,curve,schedule,pc,eps)
            search_time=time.perf_counter()-ts
            context=dict(case_id=int(c.case_id),instance_id=int(c.instance_id),ratio=c.ratio,
                initial_soc=c.initial_soc,scenario=c.scenario,epsilon=eps)
            delta=incumbent.generalized_cost_s-c.semantic_cost
            exact=round(incumbent.generalized_cost_s,7)==round(c.semantic_cost,7)
            tie=plan_key(incumbent)==key_from_record(meta['semantic'])
            passed=exact and tie if eps==0 else delta<=eps+1e-7
            h2.append(dict(**context,passed=bool(passed),cost_difference=delta,identity_match=action_id(incumbent)==c.semantic_action))
            pd.DataFrame(diagnostics).to_parquet(stage/f'views_{c.case_id:03d}.parquet',index=False)
            pd.DataFrame(traces).to_parquet(stage/f'trace_{c.case_id:03d}.parquet',index=False)
            lost,dups=check_semantic_coverage(tree,frame)
            h4.append(dict(**context,lost=lost,duplicates=dups))
            stable=tree_hash(tree)==manifest['hierarchy_sha256']
            stability.append(dict(**context,hierarchy_sha256=tree_hash(tree),mutated=not stable))
            if not passed or lost or dups or not stable:
                write_json(out/'correctness_failure.json',dict(**context,H2=passed,lost=lost,duplicates=dups,stable=stable))
                raise RuntimeError('B1 correctness failed; no scientific interpretation')
            metrics.append(dict(**context,**work,legacy_eligible_sites=c.legacy_eligible_site_count,
                legacy_effect_free_actions=c.effect_free_feasible_actions,cost=incumbent.generalized_cost_s,
                flat_cost=c.semantic_cost,cost_gap=delta,selected_action=action_id(incumbent),
                hierarchy_seconds=search_time,flat_seconds=meta['flat_evaluation_seconds']))
            for role in ROLES:
                nr=int(frame.role.eq(role).sum());nev=roles[role]['site_evaluations']
                role_metrics.append(dict(**context,role=role,semantic_sites=nr,logical_evaluations=nev,
                    reduction=None if nr==0 else 1-nev/nr,**{k:v for k,v in roles[role].items() if k!='site_evaluations'}))
            if c.case_id%32==31:print(f'B1-O epsilon={eps}: {c.case_id+1}/480 cases passed',flush=True)
        primary=pd.DataFrame(h2);primary=primary[primary.epsilon.eq(0)]
        if eps==0:
            write_json(out/'primary_gates.json',dict(passed=True,cases=480,H0=True,H1=True,H2=True,H3=True,H4=True,H5=True,
                H1_violations=0,H2_mismatches=int((~primary.passed).sum()),H3_violations=0,H4_lost_duplicated=0,H5_mutations=0))
        all_runtime.append(dict(epsilon=eps,seconds=time.perf_counter()-start,peak_rss_mib=peak_rss_mib()))
        pd.DataFrame(metrics).to_csv(out/'logical_work.csv',index=False)
        pd.DataFrame(role_metrics).to_csv(out/'role_work.csv',index=False)
        pd.DataFrame(h2).to_csv(out/'H2_all_comparisons.csv',index=False)
        pd.DataFrame(h4).to_csv(out/'H4_coverage.csv',index=False)
        pd.DataFrame(stability).to_csv(out/'H5_stability.csv',index=False)
    pd.DataFrame(all_runtime).to_csv(out/'oracle_runtime.csv',index=False)
    for name,columns in [('H1_violations',['case_id','region','role','lower','region_optimum']),
                         ('H2_mismatches',['case_id','cost_difference']),
                         ('H3_violations',['case_id','region','role','violation']),
                         ('perturbation_violations',['case_id','region','role','violation'])]:
        pd.DataFrame(columns=columns).to_csv(out/f'{name}.csv',index=False)
    m=pd.DataFrame(metrics);primary=m[m.epsilon.eq(0)]
    undefined=int(primary.reduction.isna().sum())
    # Do not silently pick a denominator convention. Preserve correctness work
    # while the explicit user clarification is pending.
    if undefined:
        median=p50=p25=None
        classification='unresolved: zero semantic denominator requires explicit statistical convention'
    else:
        median=float(primary.reduction.median());p50=float(primary.reduction.ge(.5).mean());p25=float(primary.reduction.ge(.25).mean())
        classification='strong GO' if median>=.7 and p50>=.75 else 'NO-GO' if median<.5 or p25<.75 else 'gray zone'
    write_json(out/'oracle_summary.json',dict(classification=classification,median_reduction=median,
        fraction_at_least_50_percent=p50,fraction_at_least_25_percent=p25,cases=480,zero_semantic_denominator_cases=undefined,
        B1_D='unresolved: no proven non-enumerative deployable certificate implemented',
        accounting='Logical Site-evaluation reduction potential only; no online compute or routing savings'))
    print(classification,median,p50,p25,flush=True)


if __name__=='__main__':main()
