"""B1-D2 directed road-cell boundary extraction and time-only augmentation."""
import time
import numpy as np
from .deploy import cost_bound
from .deploy_search import DeployIndex

BOUNDARY_ABS=1e-6
BOUNDARY_REL=2e-8


def subtree_ends(regions):
    ends=np.arange(len(regions),dtype=np.int32)
    for r in reversed(range(len(regions))):
        if regions[r]['children']:ends[r]=max(ends[c] for c in regions[r]['children'])
    return ends


def depth_labels(leaf_cells,regions,depth):
    lookup=np.full(len(regions),-1,np.int32)
    for i,r in enumerate(regions):
        if r['children'] or r['depth']<depth:continue
        a=i
        while regions[a]['depth']>depth:a=regions[a]['parent']
        lookup[i]=a
    return lookup[leaf_cells]


def directed_boundary_pairs(labels,source,target):
    """Sorted unique (Region,node) encoded pairs, preserving directed edges."""
    n=len(labels);a=labels[source];b=labels[target];cross=a!=b
    inbound=cross&(b>=0);outbound=cross&(a>=0)
    ingress=np.unique(b[inbound].astype(np.int64)*n+target[inbound])
    egress=np.unique(a[outbound].astype(np.int64)*n+source[outbound])
    return ingress,egress


def boundary_min(ids,times,inside):
    """Return raw min, conservative min, and actual array reads. No routing."""
    if inside or not len(ids):return 0.,0.,0
    values=times[ids];finite=values[np.isfinite(values)]
    if not len(finite):return 0.,0.,len(ids)
    raw=float(finite.min())
    safe=max(0.,float(np.nextafter(raw-(BOUNDARY_ABS+BOUNDARY_REL*abs(raw)),-np.inf)))
    return raw,safe,len(ids)


class BoundaryIndex(DeployIndex):
    def __init__(self,frozen_directory,boundary_directory):
        super().__init__(frozen_directory)
        self.boundary_load_start=time.perf_counter()
        self.cells=np.load(boundary_directory/'road_leaf_cells.npy',mmap_mode='r')
        self.ends=np.load(boundary_directory/'subtree_ends.npy',mmap_mode='r')
        self.ingress=np.load(boundary_directory/'ingress.npy',mmap_mode='r')
        self.egress=np.load(boundary_directory/'egress.npy',mmap_mode='r')
        self.offsets=np.load(boundary_directory/'boundary_offsets.npy',mmap_mode='r')
        self.boundary_load_seconds=time.perf_counter()-self.boundary_load_start

    def bind(self,forward_times,reverse_times):
        self.forward_times=forward_times;self.reverse_times=reverse_times

    def points(self,origin,destination):
        self.origin_cell=int(self.cells[origin]);self.destination_cell=int(self.cells[destination])
        self.boundary_cache={}
        return super().points(origin,destination)

    def bound(self,region,bucket,points,trip,ev,schedule,config,parent):
        before=(self.site_ids_read,self.evaluator_calls,self.oracle_reads)
        base=super().bound(region,bucket,points,trip,ev,schedule,config,-np.inf)
        self.phase='bound';start=time.perf_counter();hit=region in self.boundary_cache
        if not hit:
            i,j,k,l=self.offsets[region]
            inbound=boundary_min(self.ingress[i:j],self.forward_times,region<=self.origin_cell<=self.ends[region])
            outbound=boundary_min(self.egress[k:l],self.reverse_times,region<=self.destination_cell<=self.ends[region])
            self.boundary_cache[region]=(inbound,outbound)
        inbound,outbound=self.boundary_cache[region]
        seconds=time.perf_counter()-start
        tm=max(base['tm'],inbound[1]);tp=max(base['tp'],outbound[1])
        result=cost_bound((tm,tp,base['dm'],base['dp']),bucket,trip,ev,schedule,config,parent)
        after=(self.site_ids_read,self.evaluator_calls,self.oracle_reads);self.phase='idle'
        return dict(**{k:v for k,v in base.items() if k not in result},**result,
            ALT_tm=base['tm'],ALT_tp=base['tp'],ALT_raw_cost=base['raw_safe_cost'],
            boundary_raw_tm=inbound[0],boundary_raw_tp=outbound[0],delta_tm=inbound[1],delta_tp=outbound[1],
            ingress_reads=0 if hit else inbound[2],egress_reads=0 if hit else outbound[2],
            boundary_cache_hit=hit,boundary_seconds=seconds,
            site_ids_read_for_bound=after[0]-before[0],site_evaluator_calls_for_bound=after[1]-before[1],
            oracle_per_site_reads=after[2]-before[2],additional_sssp_calls=0)
