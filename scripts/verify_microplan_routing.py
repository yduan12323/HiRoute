"""Independent cold local-cost reproduction and real route cost checks."""
import argparse
import json
import resource
import time
import numpy as np
import pandas as pd
from _common import ROOT,configs,read_config,load_graph,sha256
from _microplan_common import read_opportunities,prepare_pairs
from microplan.routing import ExactRouter


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cold',action='store_true',help='Rebuild all sparse exact time/length costs in a fresh M4B cache')
    args=parser.parse_args();cfg=read_config('configs/microplan.yaml');root=ROOT/cfg['results_dir']
    data,routing=configs(cfg['graph_data_config']);graph=load_graph(data,routing)
    rebuild=ROOT/cfg['cache_dir']/'verification';rebuild.mkdir(exist_ok=True)
    router=ExactRouter(graph,cfg,rebuild);catalogue,opportunities,lookup=read_opportunities(cfg)
    started=time.perf_counter()
    if args.cold:
        output=root/'routing_rebuild';output.mkdir(exist_ok=True)
        if (output/'local_costs.json').exists():raise ValueError('Cold verification requires a fresh routing_rebuild directory; archive the previous one')
        _,meta=prepare_pairs(cfg,router,opportunities,lookup,output)
        original=json.loads((root/'local_costs.json').read_text())
        assert meta['sha256']==original['sha256']
        del _
    costs=pd.read_parquet(root/'local_costs.parquet')
    rng=np.random.default_rng(cfg['seed']);sample=rng.choice(len(costs),size=64,replace=False)
    checked=0;max_time_error=0.;max_length_difference=0.
    for row in costs.iloc[sample].itertuples():
        for first,second,expected_t,expected_d in [
            (row.first,row.second,row.time_forward_s,row.fastest_length_forward_m),
            (row.second,row.first,row.time_reverse_s,row.fastest_length_reverse_m)]:
            if not np.isfinite(expected_t):continue
            a=int(opportunities.access_nodes[first]);b=int(opportunities.access_nodes[second])
            actual=graph.shortest_path(a,b)
            error=abs(actual.travel_time_s-expected_t);max_time_error=max(max_time_error,error)
            assert error<1e-7
            # igraph may pick another equal-time path. Native shortest length
            # tie-break must be no longer, without claiming identical path ties.
            max_length_difference=max(max_length_difference,abs(actual.distance_m-expected_d))
            assert expected_d<=actual.distance_m+1e-6
            checked+=1
    # Reconstruct recorded flat winners from each OD's primary practical budget,
    # checking actual concatenated directed time independently of the table.
    selected=pd.read_parquet(root/'abstraction_regret.parquet',filters=[('method','==','flat'),('ratio','==',1.1),
        ('theta_id','==','balanced'),('access_scenario','==','all_attached'),('dwell_scenario','==','without_dwell')])
    od=pd.read_parquet(ROOT/'results/milestone_3a/od_remapping.parquet').set_index('instance_id')
    for row in selected.drop_duplicates('instance_id').itertuples():
        if row.oracle_first_index<0:continue
        visits=[int(catalogue.iloc[row.oracle_first_index].access_node)]
        if row.oracle_second_index>=0:visits.append(int(catalogue.iloc[row.oracle_second_index].access_node))
        endpoints=[int(od.loc[row.instance_id].origin_node),*visits,int(od.loc[row.instance_id].destination_node)]
        time_s=sum(graph.shortest_path_cost(a,b) for a,b in zip(endpoints[:-1],endpoints[1:]))
        partition=pd.read_parquet(root/'microplans_flat'/f'od_{row.instance_id:02d}_{row.task}.parquet')
        plan=partition[(partition.first_index==row.oracle_first_index)&(partition.second_index==row.oracle_second_index)].iloc[0]
        assert abs(time_s-plan.total_route_time_s)<1e-6
        checked+=1
    record={'passed':True,'cold_pair_byte_identical':bool(args.cold),'independent_directed_cost_checks':checked,
        'maximum_time_difference_s':max_time_error,'maximum_igraph_equal_time_length_difference_m':max_length_difference,
        'seconds_including_cold_routing_if_requested':time.perf_counter()-started,
        'peak_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024}
    (root/'routing_reproducibility.json').write_text(json.dumps(record,indent=2)+'\n');router.close();print(json.dumps(record,indent=2))

if __name__=='__main__':main()
