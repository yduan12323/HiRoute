"""Exact directed-time theorem diagnostic on the first static leaf, all cases.

Leaf choice is stable identity order, never based on a pruning result. Unknown
diameters for other Regions are not fabricated or used by oracle pruning.
"""
import json
import time
import sys
import numpy as np
import pandas as pd
from _common import ROOT,configs,load_graph,read_config
from _stopplan4r_common import memory_guard,write_json,peak_rss_mib
from hierarchy4r.bounds import directed_time_check


def main():
    out=ROOT/'results/milestone_4r_b1'
    tree=json.loads((out/'hierarchy.json').read_text())
    populated='--populated' in sys.argv
    diagnostic=out/'diameter_populated' if populated else out
    diagnostic.mkdir(exist_ok=True)
    eligible=set()
    if populated:
        first=pd.read_parquet(out/'flat_reference/case_000.parquet')
        eligible=set(first[first.role.eq('C')].site_id)
    region=next(i for i,n in enumerate(tree['regions']) if not n['children']
                and (not populated or len({tree['site_ids'][j] for j in n['members']}&eligible)>=2))
    ids={tree['site_ids'][i] for i in tree['regions'][region]['members']}
    sites=pd.read_parquet(out/'site_membership.parquet')
    anchors=sorted(set(sites[sites.site_id.isin(ids)].access_node))
    lookup={n:i for i,n in enumerate(anchors)}
    cfg=read_config('configs/stopplan_4r.yaml');memory_guard(cfg['memory'],projected_additional_gib=7)
    ts=time.perf_counter();data,routing=configs(cfg['graph_data_config']);g=load_graph(data,routing)
    pairs=np.array(g._graph.distances(source=anchors,target=anchors,weights=g._weights('travel_time'),mode='out'))
    np.savez(diagnostic/'directed_diameter_pairs.npz',anchors=anchors,pairs=pairs)
    rows=[]
    for path in sorted((out/'flat_reference').glob('*.parquet')):
        case=int(path.stem.split('_')[1]);f=pd.read_parquet(path)
        f=f[f.site_id.isin(ids)&f.role.ne('')]
        for role,group in f.groupby('role'):
            index=[lookup[n] for n in group.access_node]
            r=directed_time_check(group.tm.to_numpy(),group.tp.to_numpy(),pairs[np.ix_(index,index)])
            rows.append(dict(case_id=case,region=region,role=role,site_count=len(group),**r))
    pd.DataFrame(rows).to_csv(diagnostic/'directed_time_theorem_checks.csv',index=False)
    write_json(diagnostic/'directed_time_diagnostic.json',dict(region=region,anchor_count=len(anchors),
        tested_views=len(rows),violations=sum(not r['passed'] for r in rows),
        unreachable_directed_pairs=int(np.isinf(pairs).sum()),runtime_seconds=time.perf_counter()-ts,
        peak_rss_mib=peak_rss_mib(),selection='first static leaf with at least two C actions in H0 case 0; added because first static leaf had no eligible semantic Views' if populated else 'first static leaf; no comparative outcome used',
        uncomputed_regions='diameter unavailable / +infinity certificate; never used as finite oracle RCC'))
    assert all(r['passed'] for r in rows)
    print(f'Directed theorem: {len(rows)} Views, {len(anchors)} anchors, zero violations',flush=True)


if __name__=='__main__':main()
