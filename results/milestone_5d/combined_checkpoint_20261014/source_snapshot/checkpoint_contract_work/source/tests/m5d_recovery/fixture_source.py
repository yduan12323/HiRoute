"""Tiny JSON-source-loaded Python router; no native/production provenance claim."""
import hashlib
import heapq
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from timecut5.real_legs import RealSite
from timecut5.real_adapter import site_catalog_digest
from timecut5.road_provider import TableFreeRoadSelectedLegProvider
from timecut5.sparse_seed import SparseSeedCatalog
from timecut5.feasible_incumbent import canonical,sha

class Router:
    def __init__(self,g):
        self.g=g;self.closed=False
        self.provenance={'source_sha256':sha(Path(__file__).read_bytes()),
                         'implementation_kind':'synthetic_python_fixture_v1'}
    def _labels(self,source,reverse=False):
        g=self.g;n=g.node_count
        cost=np.full(n,np.inf);length=np.full(n,np.inf)
        parent=np.full(n,-1,dtype=np.int64);edges=np.full(n,-1,dtype=np.int64)
        cost[source]=length[source]=0;queue=[(0.,0.,source)]
        while queue:
            t,d,a=heapq.heappop(queue)
            if (t,d)!=(cost[a],length[a]):continue
            for e,(u,v) in enumerate(zip(g.source,g.target)):
                if reverse:u,v=v,u
                if u!=a:continue
                candidate=(t+float(g.weights['travel_time'][e]),d+float(g.weights['distance'][e]))
                if candidate<(cost[v],length[v]):
                    cost[v],length[v]=candidate;parent[v]=u;edges[v]=e
                    heapq.heappush(queue,(*candidate,int(v)))
        return cost,length,parent,edges
    def full_edges(self,source):return self._labels(source)
    def full(self,source,reverse=False):return self._labels(source,reverse)[:3]
    def close(self):self.closed=True


def fixture(root,case='nonbest'):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    positions=[0,1,3,2]
    nodes=canonical(dict(anchors={'A':0,'B':1,'D':2,'X':3},node_count=4))
    edges=canonical([[a,b,abs(positions[a]-positions[b]),abs(positions[a]-positions[b])]
                     for a in range(4) for b in range(4) if a!=b])
    npth,epth=root/'nodes.json',root/'edges.json';npth.write_bytes(nodes);epth.write_bytes(edges)
    # The graph used by the router is reconstructed from these exact bytes.
    n=json.loads(npth.read_bytes());rows=json.loads(epth.read_bytes())
    arrays=[np.ascontiguousarray([row[i] for row in rows],dtype=np.int64 if i<2 else np.float64) for i in range(4)]
    for array in arrays:array.flags.writeable=False
    graph=SimpleNamespace(node_count=n['node_count'],edge_count=len(rows),source=arrays[0],target=arrays[1],
                          weights={'travel_time':arrays[2],'distance':arrays[3]})
    router=Router(graph)
    provider=TableFreeRoadSelectedLegProvider(graph,router,n['anchors'],nodes_sha256=sha(nodes),edges_sha256=sha(edges),
        router_sha256=router.provenance['source_sha256'],anchor_catalog_sha256=sha(canonical(n['anchors'])),
        source_cache_max_bytes=0)
    sites={'s':RealSite('s','B',('S',) if case=='equality' else ('C',)),
           't':RealSite('t','X',('C',))}
    hierarchy=sha(b'unavailable original hierarchy reference; sorted-ID experimental tree instead')
    catalog=SparseSeedCatalog(provider,sites,origin_anchor='A',destination_anchor='D',nodes_path=npth,edges_path=epth,
        site_catalog_sha256=site_catalog_digest(sites),hierarchy_sha256=hierarchy,
        candidate_sha256=sha(canonical(sorted(sites))))
    query=dict(origin='A',destination='D',hierarchy_sha256=hierarchy,sparse_domain_sha256=catalog.domain_sha256,
        H_ref=1,start_time_s=0,initial_energy_kwh=2 if case=='charge_required' else 10,
        capacity_kwh=20,minimum_energy_kwh=0,reserve_kwh=1,consumption_kwh_per_m=1,
        overhead_s=10 if case=='equality' else 2,lambda_stop_s=0 if case=='equality' else 1,
        charging_segments=[[0,20,1,0]],schedule=dict(a=0,b=100,D=0) if case=='equality' else None)
    return query,catalog,dict(nodes_path=npth,edges_path=epth,router_source_path=Path(__file__))
