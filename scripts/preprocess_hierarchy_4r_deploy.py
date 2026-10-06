"""Sequential deterministic 8-landmark preprocessing on the frozen hierarchy."""
import json,time
import numpy as np
import pandas as pd
from _common import ROOT,configs,load_graph,read_config,sha256
from _stopplan4r_common import memory_guard,peak_rss_mib,write_json
from stopplan4r.sites import sites_from_table
from hierarchy4r.deploy import select_landmarks,bucket_flags,BUCKETS


def main():
    out=ROOT/'results/milestone_4r_b1d';old=ROOT/'results/milestone_4r_b1'
    assert json.loads((out/'b1_oracle_classification.json').read_text())['classification']!='NO-GO'
    if (out/'preprocessing.json').exists():raise FileExistsError('Frozen preprocessing already exists')
    cfg=read_config('configs/stopplan_4r.yaml');data,routing=configs(cfg['graph_data_config'])
    meta=json.loads((ROOT/data['graph_dir']/'metadata.json').read_text())
    n=meta['node_count'];array_bytes=8*2*2*n*8
    guard=memory_guard(cfg['memory'],projected_additional_gib=8+array_bytes/1024**3)
    write_json(out/'memory_projection.json',dict(array_bytes=array_bytes,projection_gib=8+array_bytes/1024**3,guard=guard,
        strategy='32 float64 arrays, sequential SSSP, memory-mapped storage; no concurrent SSSP'))
    ts=time.perf_counter();graph=load_graph(data,routing)
    scc=graph.largest_strong_component_nodes();landmarks=select_landmarks(graph.nodes,scc)
    assert landmarks==select_landmarks(graph.nodes,scc)
    nodeorder=graph.nodes[['node_id','osm_node_id']].to_numpy(dtype=np.int64)
    import hashlib
    manifest=dict(landmarks=landmarks,osm_ids=[int(graph.nodes.iloc[i].osm_node_id) for i in landmarks],
        largest_scc_nodes=len(scc),centroid_lon=float(graph.nodes.lon.mean()),centroid_lat=float(graph.nodes.lat.mean()),
        selection='normalized fixed 8 directions; equirectangular coordinates; descending score, ascending OSM/node ID; skip previously selected extrema',
        node_order_sha256=hashlib.sha256(nodeorder.tobytes()).hexdigest(),dtype='float64',node_count=n,
        hierarchy_sha256=sha256(old/'hierarchy.json'),
        inputs={str(ROOT/data['graph_dir']/name):sha256(ROOT/data['graph_dir']/name) for name in ['nodes.parquet','edges.parquet','metadata.json']},
        config_sha256=sha256(ROOT/'configs/routing.yaml'))
    write_json(out/'landmark_manifest.json',manifest)
    arrays=out/'landmarks';arrays.mkdir(exist_ok=True);logs=[]
    for metric in ['travel_time','distance']:
        for l,node in enumerate(landmarks):
            for direction in ['out','in']:
                memory_guard(cfg['memory'],projected_additional_gib=1)
                start=time.perf_counter();values=graph.single_source_distances(node,metric,direction)
                path=arrays/f'{metric}_{l}_{direction}.npy';np.save(path,values,allow_pickle=False)
                # One deterministic full-array repeat per metric/direction; all
                # remaining arrays use the identical deterministic primitive.
                if l==0:assert np.array_equal(values,graph.single_source_distances(node,metric,direction))
                logs.append(dict(metric=metric,landmark=l,direction=direction,seconds=time.perf_counter()-start,
                    bytes=path.stat().st_size,sha256=sha256(path),peak_rss_mib=peak_rss_mib()))
                del values
            print(f'{metric}: landmark {l+1}/8 complete',flush=True)
    pd.DataFrame(logs).to_csv(out/'landmark_runtime.csv',index=False)
    start=time.perf_counter();tree=json.loads((old/'hierarchy.json').read_text())
    sites={s.site_id:s for s in sites_from_table(pd.read_parquet(ROOT/'results/milestone_4r/stop_sites.parquet'))}
    flags=np.array([bucket_flags(sites[s]) for s in tree['site_ids']]);access=np.array([sites[s].access_node for s in tree['site_ids']],dtype=np.int64)
    counts=np.zeros((len(tree['regions']),3),dtype=np.int64)
    summary=np.full((len(counts),3,2,8,4),np.inf);finite=np.zeros((len(counts),3,2,8,2),dtype=np.int64)
    children=np.array([r['children'] if r['children'] else [-1,-1] for r in tree['regions']],dtype=np.int64)
    leafdir=out/'leaf_buckets';leafdir.mkdir(exist_ok=True)
    members={}
    for r,region in enumerate(tree['regions']):
        ids=np.array(region['members'],dtype=np.int64)
        for b in range(3):
            members[r,b]=ids[flags[ids,b]];counts[r,b]=len(members[r,b])
        if not region['children']:
            write_json(leafdir/f'{r}.json',{BUCKETS[b]:[tree['site_ids'][i] for i in members[r,b]] for b in range(3)})
    for mi,metric in enumerate(['travel_time','distance']):
        for l in range(8):
            for di,direction in enumerate(['out','in']):
                array=np.load(arrays/f'{metric}_{l}_{direction}.npy',mmap_mode='r')
                for (r,b),ids in members.items():
                    if not len(ids):continue
                    v=array[access[ids]]
                    summary[r,b,mi,l,di*2:di*2+2]=[v.min(),v.max()]
                    finite[r,b,mi,l,di]=np.isfinite(v).sum()
    rows=[]
    for (r,b),ids in members.items():
        for mi,metric in enumerate(['travel_time','distance']):
            for l in range(8):
                v=summary[r,b,mi,l]
                rows.append(dict(region=r,bucket=BUCKETS[b],metric=metric,landmark=l,count=int(counts[r,b]),empty=not len(ids),
                    min_from=v[0],max_from=v[1],min_to=v[2],max_to=v[3],
                    finite_from=int(finite[r,b,mi,l,0]),finite_to=int(finite[r,b,mi,l,1])))
    table=pd.DataFrame(rows);table.to_parquet(out/'region_landmark_summaries.parquet',index=False)
    # Fast fixed-size query representation, equivalent to the explicit table.
    np.save(out/'summaries.npy',summary);np.save(out/'counts.npy',counts);np.save(out/'children.npy',children)
    pd.DataFrame([dict(region=r,bucket=BUCKETS[b],count=int(counts[r,b])) for r,b in members]).to_csv(out/'bucket_counts.csv',index=False)
    # Independent bottom-up reconstruction of min/max/counts (no rereading Sites).
    rebuilt=summary.copy()
    for r in reversed(range(len(counts))):
        if children[r,0]<0:continue
        a,b=children[r]
        assert np.array_equal(counts[r],counts[a]+counts[b])
        for bi in range(3):
            active=[c for c in [a,b] if counts[c,bi]]
            if active:
                rebuilt[r,bi,...,0]=np.min(rebuilt[active,bi,...,0],axis=0)
                rebuilt[r,bi,...,1]=np.max(rebuilt[active,bi,...,1],axis=0)
                rebuilt[r,bi,...,2]=np.min(rebuilt[active,bi,...,2],axis=0)
                rebuilt[r,bi,...,3]=np.max(rebuilt[active,bi,...,3],axis=0)
    assert np.array_equal(summary,rebuilt)
    write_json(out/'preprocessing.json',dict(runtime_seconds=time.perf_counter()-ts,summary_seconds=time.perf_counter()-start,
        peak_rss_mib=peak_rss_mib(),array_disk_bytes=sum(p.stat().st_size for p in arrays.glob('*.npy')),
        summary_disk_bytes=(out/'region_landmark_summaries.parquet').stat().st_size,
        summary_reconstruction_equal=True,landmark_manifest_sha256=sha256(out/'landmark_manifest.json'),
        summary_sha256=sha256(out/'region_landmark_summaries.parquet'),hierarchy_sha256=sha256(old/'hierarchy.json'),
        schema={c:str(t) for c,t in table.dtypes.items()}))
    print('Preprocessing complete',flush=True)


if __name__=='__main__':main()
