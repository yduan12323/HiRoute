"""Small pure-Python fixture; no production graph, binary, or experiment."""
import hashlib, heapq, json, random, sys, tempfile
from pathlib import Path
from types import SimpleNamespace
from timecut5.real_legs import RealSite
from timecut5.real_adapter import site_catalog_digest
from timecut5.road_provider import TableFreeRoadSelectedLegProvider
from timecut5.sparse_seed import SparseSeedCatalog, admit_sparse_seed
from timecut5.deployable import constructive_seed_candidates

MODE=sys.argv[1]
SHA='0'*64
canon=lambda x:json.dumps(x,sort_keys=True,separators=(',',':'),default=str)
hash_bytes=lambda b:hashlib.sha256(b).hexdigest()

class Router:
    provenance={'source_sha256':SHA}
    def __init__(self,g,fail=False,corrupt=False):self.g,self.calls,self.fail,self.corrupt=g,[],fail,corrupt
    def full_edges(self,source):
        self.calls.append(source)
        if self.fail: raise RuntimeError('fixture native failure')
        g=self.g;n=g.node_count
        costs=[float('inf')]*n; lengths=[float('inf')]*n; parents=[-1]*n;edges=[-1]*n
        costs[source]=lengths[source]=0.;q=[(0.,0.,source)]
        while q:
            cost,length,node=heapq.heappop(q)
            if (cost,length)!=(costs[node],lengths[node]):continue
            for e,(a,b) in enumerate(zip(g.source,g.target)):
                if a!=node:continue
                candidate=cost+g.weights['travel_time'][e],length+g.weights['distance'][e]
                if candidate<(costs[b],lengths[b]):
                    costs[b],lengths[b]=candidate;parents[b]=a;edges[b]=e
                    heapq.heappush(q,(*candidate,b))
        if self.corrupt:costs[4]=12345.
        return costs,lengths,parents,edges

def fixture(index,root):
    rng=random.Random(index);n=5;src=[];dst=[];weights=[]
    for a in range(n):
        for b in range(n):
            if a!=b and rng.random()<.65:
                src.append(a);dst.append(b);weights.append(float(rng.randint(1,5)))
    graph=SimpleNamespace(node_count=n,edge_count=len(src),source=src,target=dst,
        weights={'travel_time':weights,'distance':weights})
    router=Router(graph,fail=index==101,corrupt=index==102)
    anchors={str(i):i for i in range(n)}
    nodes=root/'nodes.fixture';edges=root/'edges.fixture'
    nodes.write_bytes(b'fixture nodes');edges.write_bytes(b'fixture edges')
    provider=TableFreeRoadSelectedLegProvider(graph,router,anchors,
        nodes_sha256=hash_bytes(nodes.read_bytes()),edges_sha256=hash_bytes(edges.read_bytes()),
        router_sha256=SHA,anchor_catalog_sha256=hash_bytes(canon(anchors).encode()))
    sites={str(i):RealSite(str(i),str(i),('C','S','CS') if index%2 else ('C',)) for i in range(1,5)}
    catalog=SparseSeedCatalog(provider,sites,origin_anchor='0',destination_anchor='4',
        nodes_path=nodes,edges_path=edges,site_catalog_sha256=site_catalog_digest(sites),
        hierarchy_sha256=SHA,candidate_sha256=hash_bytes(json.dumps(sorted(sites),separators=(',',':')).encode()))
    query=dict(origin='0',destination='4',hierarchy_sha256=SHA,sparse_domain_sha256=catalog.domain_sha256,
        H_ref=index%4,start_time_s=0,initial_energy_kwh=index%7,capacity_kwh=8,minimum_energy_kwh=0,
        reserve_kwh=1,consumption_kwh_per_m=1,overhead_s=1,lambda_stop_s=1,
        charging_segments=[[0,8,1,0]],schedule={'a':0,'b':index%8,'D':2} if index%2 else None)
    if index==100:query['initial_energy_kwh']=1.25
    return query,catalog,router

results=[]
with tempfile.TemporaryDirectory() as temp:
    root=Path(temp)
    for index in [*range(48),100,101,102]:
        query,catalog,router=fixture(index,root)
        try:
            if MODE=='enabled':
                from timecut5.seed_diagnostic import observe_seed
                out=root/f'diagnostic-{index}'
                seed=observe_seed(query,catalog,output_dir=out,provenance={'fixture':index})
                summary=json.loads((out/'summary.json').read_text())
                assert summary['proposal_count']==seed['proposal_count']
                assert summary['accepted_count']==seed.get('accepted_count',0)
                assert summary['provider_metrics']['source_run_count']==catalog.provider.source_run_count
                assert summary['counts'].get('leg_cache_miss',0)==len(router.calls)
                assert summary['unique_sources']==len(set(router.calls))
                assert summary['inflight'] is None
                assert summary['denominator_included'] is False
                assert summary['solver_started'] is False
                assert summary['diagnostic_io_wall_ns']>0
                assert all(json.loads(line)['event'] for line in (out/'progress.jsonl').read_text().splitlines())
            else: seed=admit_sparse_seed(query,catalog)
            outcome={'seed':seed}
        except (ValueError,RuntimeError) as error:
            outcome={'exception':type(error).__name__,'message':str(error)}
            if MODE=='enabled':
                summary=json.loads((out/'summary.json').read_text())
                assert summary['exception']['type']==type(error).__name__
                if index in (101,102):
                    state=json.loads((out/'route_inflight.json').read_text())
                    assert state['state']=='started'
                    assert state['stage']==('native_full_edges' if index==101 else 'witness_reconstruction')
        outcome['routes']=list(router.calls)
        try:
            proposals=constructive_seed_candidates(query,catalog)
            outcome['proposals']=proposals
            if MODE=='enabled' and 'seed' in outcome:
                assert summary['ordered_proposal_sha256']==hash_bytes(canon(proposals).encode())
        except (ValueError,RuntimeError) as error:
            outcome['proposal_exception']=[type(error).__name__,str(error)]
        results.append(outcome)
print(canon(results))
