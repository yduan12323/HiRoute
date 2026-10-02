"""Native bounded sparse views with Python ownership of the original graph arrays."""
import ctypes
import hashlib
from pathlib import Path
import subprocess
import time
import numpy as np
from .models import Gateway, RegionGateways


class ExactRouter:
    def __init__(self, graph, config, cache):
        self.graph = graph  # Retain pointer-backed arrays throughout native lifetime.
        cache = Path(cache); cache.mkdir(parents=True, exist_ok=True)
        source = Path(__file__).with_suffix('.cpp')
        binary = cache/'routing.so'
        command = [config['compiler'], *config['compiler_flags'], '-shared', '-fPIC', str(source), '-o', str(binary)]
        subprocess.run(command, check=True)
        self.provenance = {'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                           'compiler_command': command,
                           'compiler_version': subprocess.check_output([config['compiler'], '--version'], text=True)}
        self.lib = ctypes.CDLL(str(binary))
        ints = np.ctypeslib.ndpointer(dtype=np.int64, flags='C_CONTIGUOUS')
        doubles = np.ctypeslib.ndpointer(dtype=np.float64, flags='C_CONTIGUOUS')
        pointer = ctypes.c_void_p; integer = ctypes.c_int64
        self.lib.graph_create.argtypes = [integer, integer, ints, ints, doubles, doubles]
        self.lib.graph_create.restype = pointer
        self.lib.graph_free.argtypes = [pointer]
        self.lib.graph_full.argtypes = [pointer, integer, ctypes.c_int, doubles, doubles, ints]
        self.lib.graph_pairs.argtypes = [pointer, integer, ints, ints, ctypes.c_double, doubles, doubles]
        self.lib.graph_gateways.argtypes = [pointer, ints, integer, ctypes.c_double, doubles, doubles, ints, ints,
                                          ctypes.c_double, doubles, ctypes.POINTER(integer)]
        self.lib.graph_gateways.restype = ctypes.POINTER(integer)
        if any(not a.flags.c_contiguous for a in [graph.source, graph.target, *graph.weights.values()]):
            raise ValueError('Native graph arrays must be contiguous')
        self.handle = self.lib.graph_create(graph.node_count, graph.edge_count, graph.source, graph.target,
                                           graph.weights['travel_time'], graph.weights['distance'])
        if not self.handle:
            raise ValueError('Native graph exceeds supported index domain')

    def close(self):
        if self.handle:
            self.lib.graph_free(self.handle); self.handle = None

    def full(self, root, reverse=False):
        if not 0 <= root < self.graph.node_count:
            raise ValueError('Invalid root')
        n = self.graph.node_count
        cost, length, parent = np.empty(n), np.empty(n), np.empty(n, dtype=np.int64)
        self.lib.graph_full(self.handle, root, reverse, cost, length, parent)
        return cost, length, parent

    def pairs(self, first_nodes, second_nodes, cutoff):
        first, second = [np.ascontiguousarray(a, dtype=np.int64) for a in (first_nodes, second_nodes)]
        if first.shape != second.shape or first.ndim != 1 or not np.isfinite(cutoff) or cutoff < 0:
            raise ValueError('Invalid sparse routing request')
        if len(first) and (min(first.min(),second.min()) < 0 or max(first.max(),second.max()) >= self.graph.node_count):
            raise ValueError('Invalid access node')
        costs, lengths = np.empty(len(first)), np.empty(len(first))
        self.lib.graph_pairs(self.handle, len(first), first, second, cutoff, costs, lengths)
        return costs, lengths

    def gateways(self, members, ds, dd, parents, next_nodes, budget, radius):
        members = np.unique(np.asarray(members, dtype=np.int64))
        if not len(members) or radius <= 0 or not np.isfinite(radius):
            raise ValueError('Gateway view requires members and a positive radius')
        times = np.empty(2); size = ctypes.c_int64()
        data = self.lib.graph_gateways(self.handle, members, len(members), radius, ds, dd, parents, next_nodes,
                                      budget, times, ctypes.byref(size))
        values = np.ctypeslib.as_array(data, shape=(size.value,)).copy()
        local_nodes, local_edges, unreachable, count, member_count = values[:5]
        gateways = tuple(Gateway(int(v),bool(role&1),bool(role&2),int(edges))
                         for v,role,edges in values[5:5+3*count].reshape(-1,3))
        bindings = values[5+3*count:].reshape(-1,3)
        if (bindings[:,1:] == -2).any():
            raise ValueError('Shortest-path parent cycle')
        return RegionGateways(gateways,tuple(map(int,bindings[:,0])),
            tuple(None if v<0 else int(v) for v in bindings[:,1]),
            tuple(None if v<0 else int(v) for v in bindings[:,2]),
            int(local_nodes),int(local_edges),int(unreachable),float(times[0]),float(times[1]))
