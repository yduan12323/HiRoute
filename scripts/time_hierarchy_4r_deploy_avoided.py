"""Clean measurement of the flat Site checks replaced by the frozen search.

This is a control experiment after D1–D5, never an input to online pruning.
Routing and selection of the omitted Site set are outside the timed section.
"""
import json
import time
from pathlib import Path
from types import SimpleNamespace
import pandas as pd
from _common import ROOT, configs, load_graph, read_config, sha256
from _stopplan4r_common import write_json, memory_guard, peak_rss_mib
from microplan.routing import ExactRouter
from run_stopplan_4r_diagnostic import ODTravel
from stopplan4r.models import EVModel, PiecewiseChargingCurve, PlannerConfig, ScheduledStop, Trip
from stopplan4r.sites import sites_from_table
from hierarchy4r.deploy import BUCKETS
from hierarchy4r.deploy_search import exact_leaf


def main():
    out=ROOT/'results/milestone_4r_b1d'
    assert json.loads((out/'query_completion.json').read_text())['cases']==480
    if (out/'avoided_timing.csv').exists():
        raise FileExistsError('Timing control already exists')
    cfg=read_config('configs/stopplan_4r.yaml')
    memory_guard(cfg['memory'],projected_additional_gib=8)
    graph=load_graph(*configs(cfg['graph_data_config']))
    router=ExactRouter(graph,cfg,out/'native_cache')
    sites={s.site_id:s for s in sites_from_table(pd.read_parquet(ROOT/'results/milestone_4r/stop_sites.parquet'))}
    leaf_ids={int(p.stem):json.loads(p.read_text()) for p in sorted((out/'leaf_buckets').glob('*.json'))}
    roots={b:sorted(s for leaf in leaf_ids.values() for s in leaf[b]) for b in BUCKETS}
    ev=EVModel(**cfg['ev']);curve=PiecewiseChargingCurve(tuple(map(tuple,cfg['charging']['bands'])))
    pc=PlannerConfig(**cfg['planner']);work=pd.read_csv(out/'work.csv');rows=[]
    ods=pd.read_parquet(ROOT/cfg['development_ods']).sort_values('instance_id')
    write_json(out/'timing_control_protocol.json',dict(
        method='Single fixed-order pass; same exact_leaf and routing semantics; only the complement of reached leaf candidates is timed. Candidate-set construction and routing excluded.',
        excluded='No H0 serialization, oracle reads, summary construction, or Region scans in timed section',
        limitations='Separate process/pass; Python and filesystem cache effects are uncontrolled; timings are descriptive development measurements.',
        source_sha256=sha256(Path(__file__)),work_sha256=sha256(out/'work.csv')))
    for od in ods.itertuples():
        memory_guard(cfg['memory'],projected_additional_gib=1)
        ft,fl,_=router.full(int(od.origin_node));rt,rl,_=router.full(int(od.destination_node),True)
        travel=ODTravel(int(od.origin_node),int(od.destination_node),ft,fl,rt,rl)
        baseline=travel.leg(travel.origin,travel.destination)
        for c in work[work.instance_id.eq(od.instance_id)].itertuples():
            schedule=None if c.scenario=='energy_only' else ScheduledStop(.4*baseline.time_s,.7*baseline.time_s)
            trip=Trip(travel.origin,travel.destination,c.initial_soc*60,mobility_budget_s=c.ratio*baseline.time_s)
            buckets=['Ccap'] if schedule is None else ['S0cap','SCcap']
            reached=pd.read_parquet(out/'queries'/f'leaves_{c.case_id:03d}.parquet')
            used=[s for r in reached.itertuples() for s in leaf_ids[r.region][r.bucket]]
            assert len(used)==len(set(used))==c.deploy_exact_site_evaluations
            used=set(used)
            avoided=[s for b in buckets for s in roots[b] if s not in used]
            assert len(avoided)+len(used)==c.flat_static_candidates
            counter=SimpleNamespace(evaluator_calls=0)
            start=time.perf_counter()
            _,semantic,outside,calls=exact_leaf(avoided,counter,trip,sites,travel,ev,curve,schedule,pc)
            seconds=time.perf_counter()-start
            rows.append(dict(case_id=c.case_id,avoided_candidates=len(avoided),avoided_semantic=semantic,
                avoided_objective_calls=calls,avoided_outside_envelope=outside,avoided_site_seconds=seconds,
                bound_refinement_seconds=c.bound_seconds+c.refinement_overhead_seconds))
        print(f'Avoided-work timing OD {od.instance_id}',flush=True)
    pd.DataFrame(rows).to_csv(out/'avoided_timing.csv',index=False)
    write_json(out/'timing_control_completion.json',dict(cases=len(rows),peak_rss_mib=peak_rss_mib()))
    router.close()


if __name__=='__main__':main()
