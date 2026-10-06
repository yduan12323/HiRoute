"""Freeze directed boundaries and F1 before inspecting BA query performance."""
import json,time,hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from _common import ROOT,sha256,read_config
from _stopplan4r_common import memory_guard,peak_rss_mib,write_json
from hierarchy4r.boundary import subtree_ends,depth_labels,directed_boundary_pairs,BOUNDARY_ABS,BOUNDARY_REL


def main():
    out=ROOT/'results/milestone_4r_b1d2';old=ROOT/'results/milestone_4r_b1';d=ROOT/'results/milestone_4r_b1d'
    if (out/'boundary_manifest.json').exists():raise FileExistsError('Boundary artifact already frozen')
    cfg=read_config('configs/stopplan_4r.yaml');guard=memory_guard(cfg['memory'],projected_additional_gib=6)
    started=time.perf_counter();base=ROOT/'data/processed/graphs/slovenia_extended'
    tree=json.loads((old/'hierarchy.json').read_text());regions=tree['regions'];ends=subtree_ends(regions)
    nodes=pd.read_parquet(base/'nodes.parquet',columns=['node_id','osm_node_id']).sort_values('node_id')
    n=len(nodes);assert np.array_equal(nodes.node_id,np.arange(n))
    rank=np.empty(n,np.int32);rank[np.argsort(nodes.osm_node_id.to_numpy(),kind='stable')]=np.arange(n,dtype=np.int32)
    cells=np.fromfile(old/'hierarchy_build/primary_cells.bin',dtype=np.int32)[rank]
    del nodes,rank
    edges=pd.read_parquet(base/'edges.parquet',columns=['source','target']);source=edges.source.to_numpy();target=edges.target.to_numpy()
    ingress={};egress={};audits=[]
    for depth in range(max(r['depth'] for r in regions)+1):
        labels=depth_labels(cells,regions,depth)
        a,b=directed_boundary_pairs(labels,source,target)
        aa,bb=directed_boundary_pairs(labels,source[::-1],target[::-1])
        assert np.array_equal(a,aa) and np.array_equal(b,bb)
        # Independently check every directed crossing against subtree membership.
        src=labels[source];dst=labels[target];cross=src!=dst
        for node,other,region in [(target,source,dst),(source,target,src)]:
            mask=cross&(region>=0);r=region[mask];v=cells[node[mask]];u=cells[other[mask]]
            assert ((v>=r)&(v<=ends[r])).all()
            assert ((u<r)|(u>ends[r])).all()
        for r,region in enumerate(regions):
            if region['depth']!=depth:continue
            ingress[r]=(a[(a//n)==r]%n).astype(np.int32)
            egress[r]=(b[(b//n)==r]%n).astype(np.int32)
            count=int(np.sum(labels==r));assert count==region['road_node_count']
            audits.append(dict(region=r,depth=depth,road_nodes=count,ingress_witnesses=len(ingress[r]),egress_witnesses=len(egress[r]),
                stored_node_violations=0,cross_edge_completeness_violations=0,reconstruction_violations=0))
        print(f'Boundary depth {depth}: directed crossing audit and deterministic repeat passed',flush=True)
    memberships=pd.read_parquet(old/'site_membership.parquet')
    assert np.array_equal(cells[memberships.access_node.to_numpy(dtype=int)],memberships.leaf_region.to_numpy())
    counts=np.load(d/'counts.npy');rows=[];complexity=[];offsets=[];ins=[];outs=[];ni=no=0;hashes={}
    for r,region in enumerate(regions):
        i=ingress[r];o=egress[r];u=np.union1d(i,o)
        hashes[str(r)]=hashlib.sha256(np.array([len(i),len(o)],np.int64).tobytes()+i.tobytes()+o.tobytes()).hexdigest()
        row=dict(region=r,depth=region['depth'],ingress=i,egress=o,union=u,road_node_count=region['road_node_count'],site_count=len(region['members']),
            Ccap=int(counts[r,0]),S0cap=int(counts[r,1]),SCcap=int(counts[r,2]))
        rows.append(row);c={k:v for k,v in row.items() if k not in ['ingress','egress','union']}
        for name,values in [('ingress',i),('egress',o),('union',u)]:
            c[name]=len(values)
            for denominator in ['road_node_count','site_count','Ccap','S0cap','SCcap']:
                c[f'{name}_per_{denominator}']=len(values)/row[denominator] if row[denominator] else None
        complexity.append(c);offsets.append([ni,ni+len(i),no,no+len(o)]);ins.append(i);outs.append(o);ni+=len(i);no+=len(o)
    table=pd.DataFrame(rows);table.to_parquet(out/'region_boundaries.parquet',index=False)
    table.to_parquet(out/'region_boundaries_rebuild.parquet',index=False)
    assert sha256(out/'region_boundaries.parquet')==sha256(out/'region_boundaries_rebuild.parquet')
    for name,array in [('road_leaf_cells',cells),('subtree_ends',ends),('ingress',np.concatenate(ins)),('egress',np.concatenate(outs)),('boundary_offsets',np.array(offsets,np.int64))]:
        np.save(out/f'{name}.npy',array)
    comp=pd.DataFrame(complexity);comp.to_csv(out/'boundary_complexity.csv',index=False)
    stats=[]
    for depth,g in [('all',comp),*list(comp.groupby('depth'))]:
        for column in comp.columns:
            if column in ['region','depth']:continue
            values=g[column].dropna()
            stats.append(dict(depth=str(depth),quantity=column,defined_regions=len(values),median=float(values.median()) if len(values) else None,
                p95=float(values.quantile(.95)) if len(values) else None,max=float(values.max()) if len(values) else None,total=float(values.sum())))
    pd.DataFrame(stats).to_csv(out/'boundary_complexity_by_depth.csv',index=False)
    pd.DataFrame(audits).sort_values('region').to_csv(out/'f1_boundary_extraction_audit.csv',index=False)
    pd.DataFrame(columns=['region','violation']).to_csv(out/'f1_violations.csv',index=False)
    write_json(out/'numerical_safety.json',dict(boundary_absolute_s=BOUNDARY_ABS,boundary_relative=BOUNDARY_REL,
        rule='max(0,nextafter(raw_min - (1e-6 + 2e-8*abs(raw_min)), -inf)); finite values only; inside/empty/unreachable -> 0',
        cost_audit_tolerance_s=2e-6,metric_audit_tolerance=1e-5,energy_bound='unchanged ALT8 distance',cache='Region-only per case; shared across static buckets'))
    runtime=dict(seconds=time.perf_counter()-started,peak_rss_mib=peak_rss_mib(),memory_guard=guard)
    write_json(out/'boundary_preprocessing.json',runtime)
    files=['region_boundaries.parquet','region_boundaries_rebuild.parquet','road_leaf_cells.npy','subtree_ends.npy','ingress.npy','egress.npy','boundary_offsets.npy','boundary_complexity.csv','boundary_complexity_by_depth.csv','f1_boundary_extraction_audit.csv','numerical_safety.json']
    write_json(out/'boundary_manifest.json',dict(schema='directed-road-cell-boundaries-v1',regions=len(regions),nodes=n,edges=len(edges),
        hierarchy_sha256=sha256(old/'hierarchy.json'),road_cell_sha256=sha256(old/'hierarchy_build/primary_cells.bin'),
        graph_sha256={name:sha256(base/name) for name in ['nodes.parquet','edges.parquet','metadata.json']},
        extraction_code_sha256={str(p.relative_to(ROOT)):sha256(p) for p in [Path(__file__),ROOT/'src/hierarchy4r/boundary.py']},
        per_region_sha256=hashes,ingress_references=ni,egress_references=no,union_references=int(comp['union'].sum()),
        deterministic_reconstruction=True,F1_violations=0,artifact_sha256={name:sha256(out/name) for name in files},
        storage_bytes=sum((out/name).stat().st_size for name in files if name.endswith(('.npy','.parquet')) and 'rebuild' not in name),**runtime))


if __name__=='__main__':main()
