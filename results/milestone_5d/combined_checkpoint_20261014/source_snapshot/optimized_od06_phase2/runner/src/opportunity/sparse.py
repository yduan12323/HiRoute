"""Typed compact sparse opportunity-neighbor arrays; no full graph duplication."""
from dataclasses import dataclass
import ctypes
from pathlib import Path
import subprocess
import numpy as np
import pandas as pd
from .regions import NeighborPair
from .models import OpportunityId


@dataclass(frozen=True)
class NeighborIndex:
    identities: tuple[OpportunityId, ...]
    first: np.ndarray
    second: np.ndarray
    geographic_m: np.ndarray
    network_m: np.ndarray

    def __post_init__(self):
        arrays = [self.first,self.second,self.geographic_m,self.network_m]
        if any(a.ndim != 1 or len(a) != len(self.first) for a in arrays):
            raise ValueError('Sparse neighbor arrays must align')
        if len(self.first) and (min(self.first.min(),self.second.min()) < 0 or max(self.first.max(),self.second.max()) >= len(self.identities)):
            raise ValueError('Sparse neighbor identity index out of range')
        if not np.isfinite(self.geographic_m).all() or (self.geographic_m < 0).any() or np.isnan(self.network_m).any() or (self.network_m < 0).any():
            raise ValueError('Invalid sparse neighbor distances')
        for array in arrays: array.setflags(write=False)

    def __len__(self):return len(self.first)

    def __iter__(self):
        for i,j,g,n in zip(self.first,self.second,self.geographic_m,self.network_m,strict=True):
            yield NeighborPair(self.identities[i],self.identities[j],float(g),float(n))

    def select(self,opportunities):
        identities=tuple(o.identity for o in sorted(opportunities,key=lambda o:o.identity))
        lookup={key:i for i,key in enumerate(identities)}
        mapping=np.array([lookup.get(key,-1) for key in self.identities],dtype=np.int64)
        first,second=mapping[self.first],mapping[self.second]
        mask=(first>=0)&(second>=0)
        return NeighborIndex(identities,first[mask],second[mask],self.geographic_m[mask],self.network_m[mask])

    @classmethod
    def from_table(cls,table,opportunities):
        identities=tuple(o.identity for o in opportunities)
        types={'node':0,'way':1,'relation':2}
        key=pd.Index([i.osm_id*4+types[i.osm_type] for i in identities])
        first=key.get_indexer(table.first_id.to_numpy()*4+table.first_type.map(types).to_numpy())
        second=key.get_indexer(table.second_id.to_numpy()*4+table.second_type.map(types).to_numpy())
        if (first<0).any() or (second<0).any():raise ValueError('Cached neighbor identity missing')
        # Same ordering as geographic-distance / typed identity reference union.
        ranks={identity:i for i,identity in enumerate(sorted(identities))}
        rank=np.array([ranks[i] for i in identities])
        geographic=table.geographic_m.to_numpy();network=table.network_m.to_numpy()
        order=np.lexsort((rank[second],rank[first],geographic))
        return cls(identities,first[order],second[order],geographic[order],network[order])


def load_union_kernel(config,cache):
    source=Path(__file__).with_name('region_union.cpp');cache=Path(cache);cache.mkdir(parents=True,exist_ok=True)
    binary=cache/'region_union.so'
    subprocess.run([config['compiler'],*config['compiler_flags'],'-shared','-fPIC',str(source),'-o',str(binary)],check=True)
    library=ctypes.CDLL(str(binary));function=library.constrained_union
    array_int=np.ctypeslib.ndpointer(dtype=np.int64,flags='C_CONTIGUOUS')
    array_double=np.ctypeslib.ndpointer(dtype=np.float64,flags='C_CONTIGUOUS')
    function.argtypes=[ctypes.c_int64,ctypes.c_int64,array_int,array_double,ctypes.c_double,ctypes.c_double,ctypes.c_double,array_int]
    function.restype=ctypes.c_int
    def union(bounds,edges,cfg):
        labels=np.empty(len(bounds),dtype=np.int64)
        code=function(len(bounds),len(edges),np.ascontiguousarray(edges,dtype=np.int64),
                      np.ascontiguousarray(bounds,dtype=np.float64),cfg['progress_tolerance'],
                      cfg['detour_tolerance_s'],cfg['max_geographic_diameter_m'],labels)
        if code:raise RuntimeError('Native constrained union failed')
        return labels
    union.library=library
    return union
