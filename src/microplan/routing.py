"""Native bounded sparse views with Python ownership of the original graph arrays."""
import ctypes
import numpy as np
from .models import Gateway, RegionGateways
from .native_artifact import (NativeArtifact, ROLES, build_artifact, canonical,
                              _file_sha, mapped_library, _regular)


def _array_identity(array):
    return (id(array), array.ctypes.data, array.dtype.str, array.shape,
            array.strides, array.nbytes)


_FEGETROUND = None


def _round_to_nearest():
    global _FEGETROUND
    if _FEGETROUND is None:
        try:
            _FEGETROUND = ctypes.CDLL(None).fegetround
        except AttributeError as exc:
            raise ValueError('Native floating-environment verification unavailable') from exc
        _FEGETROUND.restype = ctypes.c_int
    if _FEGETROUND() != 0:
        raise ValueError('Native routing requires round-to-nearest')


class _NativeFacade:
    """Supported direct calls have the same guard as the Python API.

    This owns creation/free; it is not a sandbox against Python reflection.
    """
    def __init__(self, router, native):
        self._name = native._name
        def checked_call(name, original):
            def call(*args):
                router._validate_native_call(name, args)
                if name == 'graph_target_edges':
                    router._target_calls += 1
                elif name in ('graph_full', 'graph_full_edges'):
                    router._full_calls += 1
                return original(*args)
            return call
        for name in ('graph_full', 'graph_full_edges', 'graph_target_edges',
                     'graph_pairs', 'graph_gateways'):
            setattr(self, name, checked_call(name, getattr(native, name)))

    def graph_create(self, *args):
        raise ValueError('Native graph creation is owned by ExactRouter')

    def graph_free(self, *args):
        raise ValueError('Use ExactRouter.close() for owned graph destruction')


class ExactRouter:
    def __init__(self, graph, config, cache, *, role=None, mode='full', artifact=None):
        if (type(mode) is not str or mode not in ('full', 'destination_target') or
                (role is not None and (type(role) is not str or role not in ROLES))):
            raise ValueError('Explicit valid routing role and mode required')
        if mode == 'destination_target' and role != 'search':
            raise ValueError('Destination target routing is search-only and opt-in')
        self._role, self._mode = role, mode
        self._role_mode = (role, mode)
        self.handle = None
        self._owned_handle = None
        self.graph = self._graph_owner = graph
        self._graph_dimensions = (graph.node_count, graph.edge_count)
        self._graph_arrays = (graph.source, graph.target,
                             graph.weights['travel_time'], graph.weights['distance'])
        self._validate_graph()
        self._graph_array_identities = tuple(map(_array_identity, self._graph_arrays))
        if artifact is not None and not isinstance(artifact, NativeArtifact):
            raise ValueError('Artifact must come from build_artifact')
        self._artifact_object = artifact if artifact is not None else build_artifact(config, cache)
        receipt = self._artifact_object.authenticate(config)
        if role is not None:
            if not receipt['build_spec']['strict_binary64']:
                raise ValueError('Explicit routing roles require audited binary64 compiler flags')
            _round_to_nearest()
        self._artifact_bytes = canonical(receipt)
        self.binary_path = str(self._artifact_object.load_copy(cache))
        native = self._native_lib = ctypes.CDLL(self.binary_path)
        self._mapped_identity = mapped_library(native, self.binary_path)
        ints = np.ctypeslib.ndpointer(dtype=np.int64, flags='C_CONTIGUOUS')
        doubles = np.ctypeslib.ndpointer(dtype=np.float64, flags='C_CONTIGUOUS')
        pointer = ctypes.c_void_p; integer = ctypes.c_int64
        native.graph_create.argtypes = [integer, integer, ints, ints, doubles, doubles]
        native.graph_create.restype = pointer
        native.graph_free.argtypes = [pointer]
        native.graph_free.restype = None
        native.graph_full.argtypes = [pointer, integer, ctypes.c_int, doubles, doubles, ints]
        native.graph_full_edges.argtypes = [pointer, integer, ctypes.c_int, doubles, doubles, ints, ints]
        native.graph_target_edges.argtypes = [pointer, integer, integer, doubles, doubles, ints, ints]
        native.graph_pairs.argtypes = [pointer, integer, ints, ints, ctypes.c_double, doubles, doubles]
        native.graph_gateways.argtypes = [pointer, ints, integer, ctypes.c_double, doubles, doubles, ints, ints,
                                          ctypes.c_double, doubles, ctypes.POINTER(integer)]
        native.graph_gateways.restype = ctypes.POINTER(integer)
        for name in ('graph_full', 'graph_full_edges', 'graph_target_edges', 'graph_pairs'):
            getattr(native, name).restype = None
        self.provenance = dict(source_sha256=receipt['source_sha256'],
            compiler_command=receipt['compiler_command'],
            compiler_version=receipt['build_spec']['compiler_version'],
            wrapper_sha256=receipt['wrapper_sha256'],
            artifact_sha256=receipt['artifact_sha256'],
            artifact_identity_sha256=receipt['artifact_identity_sha256'])
        self._provenance_bytes = canonical(self.provenance)
        self._full_calls = self._target_calls = 0
        self.handle = native.graph_create(*self._graph_dimensions, *self._graph_arrays)
        self._owned_handle = self.handle
        if not self.handle:
            raise ValueError('Native graph exceeds supported index domain')
        self.lib = _NativeFacade(self, native)

    @property
    def role(self):
        return self._role

    @property
    def mode(self):
        return self._mode

    @property
    def full_calls(self):
        return self._full_calls

    @property
    def target_calls(self):
        return self._target_calls

    @property
    def artifact(self):
        import json
        return json.loads(self._artifact_bytes)

    def _validate_graph(self):
        n, m = self._graph_dimensions
        if type(n) is not int or type(m) is not int or not 0 < n <= 2**32 - 1 or not 0 <= m <= 2**32 - 1:
            raise ValueError('Invalid native graph dimensions')
        for array, dtype in zip(self._graph_arrays, (np.int64, np.int64, np.float64, np.float64)):
            if (not isinstance(array, np.ndarray) or array.dtype != dtype or array.shape != (m,) or
                    not array.flags.c_contiguous or not array.flags.aligned or
                    (self.role is not None and array.flags.writeable)):
                raise ValueError('Exact contiguous graph arrays required; explicit roles require immutable arrays')
        for array in self._graph_arrays[:2]:
            if (array < 0).any() or (array >= n).any():
                raise ValueError('Graph endpoint outside native range')
        if self.role is not None:
            for array in self._graph_arrays[2:]:
                if not np.isfinite(array).all() or (array < 0).any():
                    raise ValueError('Finite nonnegative graph weights required')
                if m and float(array.max()) > np.finfo(np.float64).max / max(1, n):
                    raise ValueError('Graph simple-path sums may overflow')

    def validate_binding(self):
        """Cheap cache-hit guard; does not hash or open package/artifact files."""
        graph = self.graph
        if (not self.handle or self.handle != self._owned_handle or graph is not self._graph_owner or
                (self.role, self.mode) != self._role_mode or
                (graph.node_count, graph.edge_count) != self._graph_dimensions):
            raise ValueError('Closed or changed native graph/role binding')
        current = (graph.source, graph.target, graph.weights['travel_time'], graph.weights['distance'])
        if any(a is not b for a, b in zip(current, self._graph_arrays)):
            raise ValueError('Native graph array owners changed')
        if any(_array_identity(a) != identity or not a.flags.c_contiguous or
               (self.role is not None and a.flags.writeable)
               for a, identity in zip(self._graph_arrays, self._graph_array_identities)):
            raise ValueError('Native graph buffer identity or immutability changed')
        if canonical(self.provenance) != self._provenance_bytes:
            raise ValueError('Native provenance changed')
        return True

    def verify_artifact(self):
        """Reauthenticate at trust/replay boundaries, independently of cache hits."""
        self.validate_binding()
        _regular(self.binary_path)
        if (canonical(self._artifact_object.authenticate()) != self._artifact_bytes or
                _file_sha(self.binary_path) != self.artifact['artifact_sha256'] or
                mapped_library(self._native_lib, self.binary_path) != self._mapped_identity):
            raise ValueError('Loaded native artifact identity changed')
        if self.mode == 'full' and self.target_calls:
            raise ValueError('Target call observed in full-only context')
        if self.role is not None:
            _round_to_nearest()
        return self.artifact

    def _validate_native_call(self, name, args):
        self.validate_binding()
        if self.role is not None:
            _round_to_nearest()
        if not args or type(args[0]) is not int or args[0] != self.handle:
            raise ValueError('Owned live native handle required')
        n = self._graph_dimensions[0]
        def integer(value, upper):
            if type(value) is not int or not 0 <= value < upper:
                raise ValueError('Invalid native index')
        def array(value, dtype, count, writable=False):
            if (not isinstance(value, np.ndarray) or value.dtype != dtype or value.shape != (count,) or
                    not value.flags.c_contiguous or not value.flags.aligned or
                    (writable and not value.flags.writeable)):
                raise ValueError('Exact-sized native array required')
        inputs, outputs = (), ()
        if name in ('graph_full', 'graph_full_edges', 'graph_target_edges'):
            if len(args) != (6 if name == 'graph_full' else 7):
                raise ValueError('Invalid native routing argument count')
            integer(args[1], n)
            if name == 'graph_target_edges':
                if self.role != 'search' or self.mode != 'destination_target':
                    raise ValueError('Target native call forbidden for role/mode')
                integer(args[2], n)
            elif type(args[2]) not in (bool, int) or args[2] not in (0, 1):
                raise ValueError('Explicit native reverse flag required')
            outputs = args[3:]
            for value, dtype in zip(outputs, (np.float64, np.float64, np.int64, np.int64)):
                array(value, dtype, n, True)
        elif name == 'graph_pairs':
            if len(args) != 7 or type(args[1]) is not int or args[1] < 0:
                raise ValueError('Invalid native pair request')
            count = args[1]
            inputs, outputs = args[2:4], args[5:7]
            for value in inputs:
                array(value, np.int64, count)
                if (value < 0).any() or (value >= n).any():
                    raise ValueError('Invalid native pair endpoint')
            if not np.isfinite(args[4]) or args[4] < 0:
                raise ValueError('Invalid native pair cutoff')
            for value in outputs:
                array(value, np.float64, count, True)
        elif name == 'graph_gateways':
            if len(args) != 11 or type(args[2]) is not int or args[2] < 1:
                raise ValueError('Invalid native gateway request')
            array(args[1], np.int64, args[2])
            if (args[1] < 0).any() or (args[1] >= n).any():
                raise ValueError('Invalid native gateway member')
            if not np.isfinite(args[3]) or args[3] <= 0 or not np.isfinite(args[8]):
                raise ValueError('Invalid native gateway limits')
            for value, dtype in zip(args[4:8], (np.float64, np.float64, np.int64, np.int64)):
                array(value, dtype, n)
            for value in args[6:8]:
                if (value < -1).any() or (value >= n).any():
                    raise ValueError('Invalid native gateway predecessor')
            array(args[9], np.float64, 2, True)
            size = getattr(args[10], '_obj', None)
            if (type(size) is not ctypes.c_int64 or
                    ctypes.cast(args[10], ctypes.c_void_p).value != ctypes.addressof(size)):
                raise ValueError('Owned int64 output-size buffer required')
            inputs, outputs = (args[1], *args[4:8]), (args[9],)
            start, end = ctypes.addressof(size), ctypes.addressof(size) + ctypes.sizeof(size)
            if any(start < owner.ctypes.data + owner.nbytes and owner.ctypes.data < end
                   for owner in (*self._graph_arrays, *inputs, *outputs)):
                raise ValueError('Native output-size buffer aliases another array')
        for value in outputs:
            if any(np.shares_memory(value, owner) for owner in (*self._graph_arrays, *inputs)):
                raise ValueError('Native output aliases an input')
        if any(np.shares_memory(a, b) for i, a in enumerate(outputs) for b in outputs[i + 1:]):
            raise ValueError('Native output arrays must not alias')

    def close(self):
        if self._owned_handle:
            self._native_lib.graph_free(self._owned_handle)
            self._owned_handle = self.handle = None

    def full(self, root, reverse=False):
        self.validate_binding()
        if self.role is None and isinstance(root, np.integer):
            root = int(root)
        if not 0 <= root < self.graph.node_count:
            raise ValueError('Invalid root')
        n = self.graph.node_count
        cost, length, parent = np.empty(n), np.empty(n), np.empty(n, dtype=np.int64)
        self.lib.graph_full(self.handle, root, reverse, cost, length, parent)
        return cost, length, parent

    def full_edges(self, root, reverse=False):
        """Return selected labels and their exact predecessor edge identities."""
        self.validate_binding()
        if self.role is None and isinstance(root, np.integer):
            root = int(root)
        if not 0 <= root < self.graph.node_count:
            raise ValueError('Invalid root')
        n = self.graph.node_count
        cost, length = np.empty(n), np.empty(n)
        parent, parent_edge = np.empty(n, dtype=np.int64), np.empty(n, dtype=np.int64)
        self.lib.graph_full_edges(self.handle, root, reverse, cost, length, parent, parent_edge)
        return cost, length, parent, parent_edge

    def target_edges(self, root, target):
        """Only target and its predecessor chain are final; never cache as full labels."""
        self.validate_binding()
        if self.role != 'search' or self.mode != 'destination_target':
            raise ValueError('Target routing is search-only and opt-in')
        n = self._graph_dimensions[0]
        if (type(root) is not int or type(target) is not int or
                not 0 <= root < n or not 0 <= target < n):
            raise ValueError('Invalid root or target')
        cost, length = np.empty(n), np.empty(n)
        parent, parent_edge = np.empty(n, dtype=np.int64), np.empty(n, dtype=np.int64)
        self.lib.graph_target_edges(self.handle, root, target, cost, length, parent, parent_edge)
        return cost, length, parent, parent_edge

    def pairs(self, first_nodes, second_nodes, cutoff):
        self.validate_binding()
        first, second = [np.ascontiguousarray(a, dtype=np.int64) for a in (first_nodes, second_nodes)]
        if first.shape != second.shape or first.ndim != 1 or not np.isfinite(cutoff) or cutoff < 0:
            raise ValueError('Invalid sparse routing request')
        if len(first) and (min(first.min(),second.min()) < 0 or max(first.max(),second.max()) >= self.graph.node_count):
            raise ValueError('Invalid access node')
        costs, lengths = np.empty(len(first)), np.empty(len(first))
        self.lib.graph_pairs(self.handle, len(first), first, second, cutoff, costs, lengths)
        return costs, lengths

    def gateways(self, members, ds, dd, parents, next_nodes, budget, radius):
        self.validate_binding()
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
