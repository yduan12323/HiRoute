"""Independent offline static coverage audit, including every root-to-leaf path."""
import json
import numpy as np
import pandas as pd
from _common import ROOT,sha256
from _stopplan4r_common import write_json
from hierarchy4r.deploy import bucket_flags,BUCKETS
from stopplan4r.sites import sites_from_table


def main():
    out=ROOT/'results/milestone_4r_b1d'
    tree=json.loads((ROOT/'results/milestone_4r_b1/hierarchy.json').read_text())
    sites={s.site_id:s for s in sites_from_table(pd.read_parquet(ROOT/'results/milestone_4r/stop_sites.parquet'))}
    flags=np.array([bucket_flags(sites[s]) for s in tree['site_ids']])
    counts=np.load(out/'counts.npy');children=np.load(out/'children.npy')
    memberships={};rows=[];leaves={b:[] for b in BUCKETS}
    for r,region in enumerate(tree['regions']):
        for b,bucket in enumerate(BUCKETS):
            memberships[r,b]={tree['site_ids'][i] for i in region['members'] if flags[i,b]}
    for r,region in enumerate(tree['regions']):
        leaf=None if region['children'] else json.loads((out/'leaf_buckets'/f'{r}.json').read_text())
        for b,bucket in enumerate(BUCKETS):
            members=memberships[r,b];viol=int(len(members)!=counts[r,b])
            if region['children']:
                a,c=region['children'];left=memberships[a,b];right=memberships[c,b]
                viol+=int(bool(left&right) or (left|right)!=members)
                viol+=int(list(children[r])!=region['children'])
            else:
                ids=leaf[bucket]
                viol+=int(set(ids)!=members or len(ids)!=len(members))
                leaves[bucket].extend(ids)
            rows.append(dict(region=r,bucket=bucket,count=len(members),violations=viol))
    for b,bucket in enumerate(BUCKETS):
        assert len(leaves[bucket])==len(set(leaves[bucket]))==counts[0,b]
        assert set(leaves[bucket])==memberships[0,b]
    assert not (memberships[0,1]&memberships[0,2])
    supported={s for s in tree['site_ids'] if sites[s].support.meal_count>=1}
    assert memberships[0,1]|memberships[0,2]==supported
    table=pd.DataFrame(rows);table.to_csv(out/'D1_static_paths.csv',index=False)
    assert table.violations.sum()==0
    runtime=pd.read_csv(out/'landmark_runtime.csv')
    for r in runtime.itertuples():
        path=out/'landmarks'/f'{r.metric}_{r.landmark}_{r.direction}.npy'
        assert sha256(path)==r.sha256
        a=np.load(path,mmap_mode='r');assert a.dtype==np.float64 and a.ndim==1
    write_json(out/'static_audit.json',dict(regions=len(tree['regions']),sites=len(tree['site_ids']),
        bucket_views=len(rows),violations=0,root_counts={b:len(leaves[b]) for b in BUCKETS},
        full_array_hashes_verified=len(runtime),all_site_root_to_leaf_paths_preserved=True,
        frozen_hierarchy_sha256=sha256(ROOT/'results/milestone_4r_b1/hierarchy.json')))


if __name__=='__main__':main()
