"""Freeze the primary B1 topology tree only after H0 passes."""
import json
import subprocess
import time
from pathlib import Path
import numpy as np
import pandas as pd
from _common import ROOT, sha256, read_config
from _stopplan4r_common import memory_guard, peak_rss_mib, write_json
from hierarchy4r.domain import require_h0
from hierarchy4r.tree import tree_bytes, tree_hash, validate_tree


def main():
    out=ROOT/'results/milestone_4r_b1'
    require_h0(json.loads((out/'h0_summary.json').read_text()))
    if (out/'hierarchy_preregistration.json').exists():
        raise FileExistsError('Primary hierarchy is already frozen')
    cfg=read_config('configs/stopplan_4r.yaml')
    memory_guard(cfg['memory'],projected_additional_gib=7)
    started=time.perf_counter()
    work=out/'hierarchy_build';work.mkdir(exist_ok=True)
    audit={
        'available':'igraph 1.0.0, networkit 11.2, networkx 3.6.1, scipy 1.17.1; no metis/pymetis',
        'inspected':'igraph Graph community methods; networkit public namespaces; NetworkX kernighan_lin_bisection source',
        'choice':'deterministic recursive unweighted topology BFS bisection',
        'reason':'No installed native reproducible balanced recursive road-cell partitioner. NetworkX KL is available and seedable, but duplicates Python adjacency into edge_info and performs Python heap sweeps over 5,892,498 nodes and 11,561,067 directed edges per recursive level. Its default ten improvement passes have billions of Python graph/heap operations at this size; rejected on runtime/memory feasibility without comparative trials. igraph community objectives do not implement balanced recursive road-cell partitioning. Use the allowed topology-only fallback.',
        'no_partition_performance_trials':True,
        'rule':'Use weak undirected adjacency only for static partition; routing remains directed. BFS forest seeds and neighbors follow increasing OSM road-node identity. Choose earliest BFS prefix minimizing absolute Site-count imbalance with both sides nonempty; never split co-attached Sites. Recurse in left/right order. Early leaf only if capacity satisfied or all Sites share one road anchor.',
        'branch_factor':2,'leaf_capacity':64,'seed':None}
    write_json(work/'partition_choice.json',audit)
    base=ROOT/'data/processed/graphs/slovenia_extended'
    nodes=pd.read_parquet(base/'nodes.parquet',columns=['node_id','osm_node_id']).sort_values('node_id')
    assert np.array_equal(nodes.node_id,np.arange(len(nodes)))
    rank=np.empty(len(nodes),dtype=np.int32)
    rank[np.argsort(nodes.osm_node_id.to_numpy(),kind='stable')]=np.arange(len(nodes),dtype=np.int32)
    sites=pd.read_parquet(ROOT/'results/milestone_4r/stop_sites.parquet')
    sites=sites[sites.attachment_status.eq('attached') & sites.access_node.notna()].sort_values('site_id').reset_index(drop=True)
    access=rank[sites.access_node.to_numpy(dtype=np.int64)]
    edges=pd.read_parquet(base/'edges.parquet',columns=['source','target'])
    with (work/'topology.bin').open('wb') as stream:
        np.array([len(nodes),len(edges),len(sites)],dtype=np.int64).tofile(stream)
        np.column_stack([rank[edges.source.to_numpy()],rank[edges.target.to_numpy()]]).astype(np.int32).tofile(stream)
        access.tofile(stream)
    del edges,nodes
    source=ROOT/'src/hierarchy4r/bisection.cpp'
    command=['g++','-O3','-std=c++17',str(source),'-o',str(work/'bisection')]
    subprocess.run(command,check=True)
    for suffix in ['primary','rebuild']:
        subprocess.run([str(work/'bisection'),str(work/'topology.bin'),str(work/f'{suffix}_cells.bin'),str(work/f'{suffix}_regions.csv'),'64'],check=True)
    assert sha256(work/'primary_cells.bin')==sha256(work/'rebuild_cells.bin')
    assert sha256(work/'primary_regions.csv')==sha256(work/'rebuild_regions.csv')
    leaf=np.fromfile(work/'primary_cells.bin',dtype=np.int32)[access]
    regions=pd.read_csv(work/'primary_regions.csv')
    result=[]
    for r in regions.itertuples():
        result.append(dict(parent=int(r.parent),depth=int(r.depth),children=[] if r.left<0 else [int(r.left),int(r.right)],
            members=[],road_node_count=int(r.nodes),early_leaf_reason='coattached_at_one_road_anchor' if r.reason else None))
    for i,l in enumerate(leaf):result[l]['members'].append(i)
    for i in reversed(range(len(result))):
        n=result[i]
        if n['children']:n['members']=sorted(j for c in n['children'] for j in result[c]['members'])
    tree=dict(site_ids=list(sites.site_id),regions=result,capacity=64,branch_factor=2,mechanism=audit['choice'])
    validate_tree(tree)
    (out/'hierarchy.json').write_bytes(tree_bytes(tree))
    sites[['site_id','access_node']].assign(leaf_region=leaf).to_parquet(out/'site_membership.parquet',index=False)
    regions.to_csv(out/'region_parent_child.csv',index=False)
    manifest={**audit,'frozen_before_comparative_run':True,'hierarchy_sha256':tree_hash(tree),
        'implementation_sha256':{str(p.relative_to(ROOT)):sha256(p) for p in [source,Path(__file__),ROOT/'src/hierarchy4r/tree.py']},
        'input_sha256':{str(p.relative_to(ROOT)):sha256(p) for p in [base/'nodes.parquet',base/'edges.parquet',ROOT/'results/milestone_4r/stop_sites.parquet',out/'h0_summary.json']},
        'region_count_by_depth':{str(k):int(v) for k,v in regions.groupby('depth').size().items()},
        'leaf_size_distribution':{str(k):int(v) for k,v in pd.Series([len(n['members']) for n in result if not n['children']]).value_counts().sort_index().items()},
        'coverage_checks_passed':True,'byte_identical_rebuild':True,'road_cell_sha256':sha256(work/'primary_cells.bin'),
        'runtime_seconds':time.perf_counter()-started,'peak_rss_mib':peak_rss_mib(),'compiler_command':command,
        'timestamp_utc':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()}
    with (out/'hierarchy_preregistration.json').open('x') as stream:json.dump(manifest,stream,indent=2)
    print(json.dumps({k:manifest[k] for k in ['hierarchy_sha256','runtime_seconds','peak_rss_mib','region_count_by_depth']},indent=2))


if __name__=='__main__':main()
