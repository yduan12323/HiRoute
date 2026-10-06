"""Independent offline real Region ALT audit, before deployable comparisons."""
import json
import numpy as np
import pandas as pd
from _common import ROOT,configs,load_graph,read_config
from _stopplan4r_common import write_json,memory_guard
from hierarchy4r.deploy_search import DeployIndex
from hierarchy4r.deploy import bucket_flags,alt
from stopplan4r.sites import sites_from_table


def main():
    out=ROOT/'results/milestone_4r_b1d';old=ROOT/'results/milestone_4r_b1'
    cfg=read_config('configs/stopplan_4r.yaml');memory_guard(cfg['memory'],projected_additional_gib=8)
    graph=load_graph(*configs(cfg['graph_data_config']))
    od=pd.read_parquet(ROOT/cfg['development_ods']).sort_values('instance_id').iloc[0]
    index=DeployIndex(out);points=index.points(int(od.origin_node),int(od.destination_node))
    exact=[]
    for metric in ['travel_time','distance']:
        exact.append([graph.single_source_distances(int(od.origin_node),metric),
                      graph.single_source_distances(int(od.destination_node),metric,'in')])
    sites={s.site_id:s for s in sites_from_table(pd.read_parquet(ROOT/'results/milestone_4r/stop_sites.parquet'))}
    tree=json.loads((old/'hierarchy.json').read_text());rows=[]
    for r,region in enumerate(tree['regions']):
        if r!=0 and r%17:continue
        for b in range(3):
            ids=[sites[tree['site_ids'][i]].access_node for i in region['members'] if bucket_flags(sites[tree['site_ids'][i]])[b]]
            if not ids:continue
            for metric in range(2):
                for direction in range(2):
                    bound=alt(index.summary[r,b,metric],points[direction][metric],bool(direction))
                    minimum=float(np.min(exact[metric][direction][ids]))
                    rows.append(dict(region=r,bucket=b,metric=metric,direction=direction,bound=bound,exact_minimum=minimum,
                        violation=bound>minimum+1e-6))
    pd.DataFrame(rows).to_csv(out/'precomparison_D2.csv',index=False)
    write_json(out/'precomparison_D2.json',dict(audited=len(rows),violations=sum(r['violation'] for r in rows),
        selection='OD 0, every 17th Region including all root buckets, both metrics/directions',offline_only=True))
    assert not any(r['violation'] for r in rows)
    print(f'{len(rows)} real ALT checks passed',flush=True)


if __name__=='__main__':main()
