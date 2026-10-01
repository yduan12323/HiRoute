"""Spatial screening and bounded native directed road-distance validation.

The native process builds one transient adjacency index, with no graph or all-pairs
matrix saved to disk. Only sparse POI-pair distances survive. Fixed cutoff keeps
work local; the original graph (including directions and parallel edges) is used.
"""
import hashlib
import json
from pathlib import Path
import resource
import subprocess
import time
import numpy as np
from scipy.spatial import cKDTree
from .sparse import NeighborIndex


def validate_network_pairs(graph, opportunities, xy, config, cache):
    cache=Path(cache);cache.mkdir(parents=True,exist_ok=True)
    start=time.perf_counter()
    pairs=cKDTree(xy).query_pairs(config['maximum_candidate_radius_m'],output_type='ndarray')
    spatial_seconds=time.perf_counter()-start
    geo=np.linalg.norm(xy[pairs[:,0]]-xy[pairs[:,1]],axis=1)
    endpoints=np.array([o.access_node for o in opportunities],dtype=np.uint64)[pairs]
    source=Path(__file__).with_name('local_network.cpp')
    binary=cache/'local_network'
    compiler=[config['compiler'],*config['compiler_flags'],str(source),'-o',str(binary)]
    subprocess.run(compiler,check=True)
    output=cache/'network_distances.bin';log=cache/'network.stderr.txt';timing=cache/'network.time.txt'
    started=time.perf_counter()
    with output.open('wb') as out,log.open('w') as err:
        process=subprocess.Popen(['/usr/bin/time','-v','-o',str(timing),str(binary),str(config['maximum_search_distance_m'])],
                                 stdin=subprocess.PIPE,stdout=out,stderr=err)
        try:
            for array in [np.array([graph.node_count,graph.edge_count,len(pairs)],dtype=np.uint64),
                          graph.source.astype(np.uint64,copy=False),graph.target.astype(np.uint64,copy=False),
                          graph.weights['distance'],endpoints.astype(np.uint64)]:
                # Buffer view avoids another full graph byte copy.
                process.stdin.write(memoryview(np.ascontiguousarray(array)).cast('B'))
            process.stdin.close()
            code=process.wait()
        except BaseException:
            process.kill();process.wait();raise
    if code:raise RuntimeError(f'Local network validation failed: {log.read_text()}')
    distances=np.fromfile(output,dtype=np.float64).reshape(-1,2)
    if len(distances)!=len(pairs):raise ValueError('Native pair output mismatch')
    result=NeighborIndex(tuple(o.identity for o in opportunities),pairs[:,0].copy(),pairs[:,1].copy(),geo,distances.max(axis=1))
    native_seconds=time.perf_counter()-started
    peak=next(int(line.rsplit(':',1)[1])/1024 for line in timing.read_text().splitlines() if 'Maximum resident set size' in line)
    metadata={'spatial_seconds':spatial_seconds,'network_seconds':native_seconds,'pair_count':len(pairs),
              'validated_pair_count':int(np.isfinite(distances).all(axis=1).sum()),
              'native_peak_rss_mib':peak,'native_source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
              'compiler_command':compiler,'compiler_version':subprocess.check_output([config['compiler'],'--version'],text=True),
              'search_counts':log.read_text()}
    return result,distances,pairs,metadata
