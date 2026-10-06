"""Tiny accepted-router calibration; no real graph input or optimization.

Run from the repository root with its NumPy/compiler environment:
  PYTHONPATH=src python experiments/time_cut_v2/check_native_pair_contract.py

The maximum finite cutoff does not truncate any finite binary64 time label.
This is not proof of real-data readiness; repeat a selected real subset after
the graph/memory and provenance gates have passed.
"""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

import numpy as np
import yaml

from microplan.routing import ExactRouter


def run():
    root=Path(__file__).resolve().parents[2]
    config=yaml.safe_load((root/'configs/microplan.yaml').read_text())
    graphs=[
        ('equal_time_different_length',5,[(0,1,1.,9.),(0,2,1.,1.),(1,3,1.,1.),
                                         (2,3,1.,2.),(3,0,2.,1.),(0,2,1.,5.)]),
        ('directional_binary64_accumulation',4,[(0,1,1e16,1.),(1,2,1.,1.),(2,3,1.,1.)]),
    ]
    reports=[]
    for name,n,edges in graphs:
        graph=SimpleNamespace(node_count=n,edge_count=len(edges),
            source=np.ascontiguousarray([e[0] for e in edges],dtype=np.int64),
            target=np.ascontiguousarray([e[1] for e in edges],dtype=np.int64),
            weights={'travel_time':np.ascontiguousarray([e[2] for e in edges],dtype=np.float64),
                     'distance':np.ascontiguousarray([e[3] for e in edges],dtype=np.float64)})
        with tempfile.TemporaryDirectory(prefix='hiroute-router-mock-') as cache:
            router=ExactRouter(graph,config,cache)
            try:
                count=0;direction_differences=[]
                for source in range(n):
                    cost,length,parent=router.full(source)
                    targets=np.arange(n,dtype=np.int64)[::-1]
                    pair_cost,pair_length=router.pairs(np.full(n,source,dtype=np.int64),targets,sys.float_info.max)
                    # Compare the binary64 bit patterns, not a tolerance.
                    assert np.array_equal(pair_cost.view(np.uint64),cost[targets].view(np.uint64))
                    assert np.array_equal(pair_length.view(np.uint64),length[targets].view(np.uint64))
                    count+=n
                    if name=='equal_time_different_length' and source==0:
                        assert cost[3]==2 and length[3]==3
                    for target in range(n):
                        reverse_cost,reverse_length,_=router.full(target,True)
                        if float(cost[target]).hex()!=float(reverse_cost[source]).hex():
                            direction_differences.append(dict(source=source,target=target,
                                forward_hex=float(cost[target]).hex(),reverse_hex=float(reverse_cost[source]).hex()))
                if name=='directional_binary64_accumulation':
                    assert any(d['source']==0 and d['target']==3 for d in direction_differences)
                reports.append(dict(case=name,node_count=n,pair_count=count,
                    pair_full_bitwise_equal=True,forward_reverse_differences=direction_differences,
                    native_source_sha256=router.provenance['source_sha256']))
            finally:router.close()
    return dict(scope='two_mock_graphs_only_no_real_graph_load',
                direction='forward_from_source',cutoff_hex=sys.float_info.max.hex(),
                cutoff_meaning='largest finite binary64; no finite label excluded',
                compiler=config['compiler'],compiler_flags=config['compiler_flags'],
                router_py_sha256=hashlib.sha256((root/'src/microplan/routing.py').read_bytes()).hexdigest(),
                results=reports)


if __name__=='__main__':print(json.dumps(run(),indent=2))
