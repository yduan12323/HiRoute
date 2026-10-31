"""Reusable exact road index and a distinct frozen selected-leg provider.

Road weights are exact rationals.  Selected legs minimize
``(time, node tuple, edge-ID tuple)``; their actual lengths are attributes,
not the shortest-distance metric used for energy relaxations.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from fractions import Fraction
import heapq
import time
from types import MappingProxyType

from .scalar import exact


@dataclass(frozen=True)
class IndexedLeg:
    source: str
    target: str
    time_s: Fraction
    length_m: Fraction
    edges: tuple


def _identifier(value, label):
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a nonempty string")
    return value


def _weight(weight):
    if weight not in ("time_s", "length_m"):
        raise ValueError("weight must be time_s or length_m")
    return weight


class RoadIndex:
    """Build adjacency once; cache bounded scalar trees and selected legs.

    Reverse scalar Dijkstra supplies distances to a target.  Greedy traversal
    of its strictly decreasing shortest-time DAG chooses the lexicographically
    smallest next node at each step, hence the smallest complete node tuple.
    Among parallel edges to that node, all shortest edges have the same time,
    so the smallest edge ID supplies the final edge-tuple tie break.  No full
    path tuple is stored at every road vertex.

    ``distances_from/to`` return exact *road* metric distances.  In particular
    shortest road distance lower-bounds the lengths of selected-fastest legs
    and every concatenated continuation even when those lengths are not a
    metric.  Returned distance maps cannot be mutated by callers. Selected-leg queries
    stop their reverse tree once the source is settled; a retained tree resumes
    for later sources rather than restarting.  Eviction only recomputes
    queries; it never removes a candidate or changes the mathematical domain.
    ``check`` is called during construction and every bounded batch of graph
    work so a supervisor can enforce deadline/memory limits.
    """

    def __init__(self, directed_edges, *, distance_cache_size=2,
                 leg_cache_size=4096, check=None):
        if type(distance_cache_size) is not int or distance_cache_size < 0:
            raise ValueError("distance_cache_size must be a nonnegative integer")
        if type(leg_cache_size) is not int or leg_cache_size < 0:
            raise ValueError("leg_cache_size must be a nonnegative integer")
        started = time.monotonic()
        self.check = check
        self.distance_cache_size = distance_cache_size
        self.leg_cache_size = leg_cache_size
        self._forward = {}
        self._reverse = {}
        self._distance_cache = OrderedDict()
        self._leg_cache = OrderedDict()
        self._metrics = dict(index_builds=1, edges=0, nodes=0,
                             scalar_queries=0, scalar_cache_hits=0,
                             scalar_settled_vertices=0,
                             selected_leg_queries=0, selected_leg_cache_hits=0,
                             scalar_time_s=0.0, selected_leg_time_s=0.0)
        identities = set()
        rows = getattr(directed_edges, "directed_edges", directed_edges)
        for i, raw in enumerate(rows):
            if i % 1024 == 0:
                self._check()
            source = _identifier(raw.get("source"), "edge source")
            target = _identifier(raw.get("target"), "edge target")
            identity = _identifier(raw.get("edge_id", f"input:{i:08d}"), "edge_id")
            if identity in identities:
                raise ValueError("Directed edge IDs must be unique")
            identities.add(identity)
            duration = exact(raw["time_s"])
            length = exact(raw["length_m"])
            if duration <= 0 or length <= 0:
                raise ValueError("Directed edge time and length must be positive")
            row = MappingProxyType(dict(source=source, target=target,
                                        edge_id=identity, time_s=duration,
                                        length_m=length))
            self._forward.setdefault(source, []).append(row)
            self._forward.setdefault(target, [])
            self._reverse.setdefault(target, []).append(row)
            self._reverse.setdefault(source, [])
            self._metrics["edges"] += 1
        self._forward = {k: tuple(v) for k, v in self._forward.items()}
        self._reverse = {k: tuple(v) for k, v in self._reverse.items()}
        self.nodes = tuple(sorted(self._forward))
        self._metrics["nodes"] = len(self.nodes)
        self._metrics["build_time_s"] = time.monotonic() - started
        self._check()

    def _check(self):
        if self.check is not None:
            try:
                self.check()
            except BaseException:
                # A stopped expansion may have settled its vertex before all
                # outgoing arcs were relaxed. Discard workspaces on abort.
                self._distance_cache.clear()
                raise

    def _distances(self, anchor, weight, reverse, stop_at=None):
        _identifier(anchor, "anchor")
        _weight(weight)
        self._check()
        self._metrics["scalar_queries"] += 1
        cache_key = (reverse, weight, anchor)
        if cache_key in self._distance_cache:
            self._metrics["scalar_cache_hits"] += 1
            self._distance_cache.move_to_end(cache_key)
            distance, queue, settled_values = self._distance_cache[cache_key]
        else:
            distance = {anchor: Fraction(0)}
            queue = [(Fraction(0), anchor)]
            settled_values = {}
            if self.distance_cache_size:
                self._distance_cache[cache_key] = (distance, queue, settled_values)
                while len(self._distance_cache) > self.distance_cache_size:
                    self._distance_cache.popitem(last=False)
        if stop_at is not None and stop_at in settled_values:
            return MappingProxyType(settled_values)
        started = time.monotonic()
        adjacency = self._reverse if reverse else self._forward
        settled = work = 0
        while queue:
            value, node = heapq.heappop(queue)
            if distance[node] != value or node in settled_values:
                continue
            settled_values[node] = value
            settled += 1
            if settled % 256 == 0:
                self._check()
            for edge in adjacency.get(node, ()):
                work += 1
                if work % 1024 == 0:
                    self._check()
                nxt = edge["source"] if reverse else edge["target"]
                candidate = value + edge[weight]
                if nxt not in distance or candidate < distance[nxt]:
                    distance[nxt] = candidate
                    heapq.heappush(queue, (candidate, nxt))
            # Process outgoing reverse arcs before stopping so a cached tree
            # can resume correctly for another source in a later query.
            if node == stop_at:
                break
        result = MappingProxyType(settled_values)
        self._metrics["scalar_settled_vertices"] += settled
        self._metrics["scalar_time_s"] += time.monotonic() - started
        self._check()
        return result

    def distances_from(self, source, weight="time_s"):
        return self._distances(source, weight, False)

    def distances_to(self, target, weight="time_s"):
        return self._distances(target, weight, True)

    def lower_bound(self, source, target, weight="time_s"):
        """Exact directed road-metric value, or None for unreachable."""
        return self.distances_to(target, weight).get(source)

    def selected_leg(self, source, target):
        _identifier(source, "source")
        _identifier(target, "target")
        self._check()
        self._metrics["selected_leg_queries"] += 1
        pair = (source, target)
        if pair in self._leg_cache:
            self._metrics["selected_leg_cache_hits"] += 1
            self._leg_cache.move_to_end(pair)
            return self._leg_cache[pair]
        started = time.monotonic()
        if source == target:
            result = IndexedLeg(source, target, Fraction(0), Fraction(0), ())
        else:
            distances = self._distances(target, "time_s", True, stop_at=source)
            if source not in distances:
                result = None
            else:
                node = source
                edges = []
                length = Fraction(0)
                while node != target:
                    self._check()
                    choices = (edge for edge in self._forward[node]
                               if edge["target"] in distances and
                               edge["time_s"] + distances[edge["target"]] == distances[node])
                    edge = min(choices, key=lambda e: (e["target"], e["edge_id"]))
                    edges.append(edge)
                    length += edge["length_m"]
                    node = edge["target"]
                result = IndexedLeg(source, target, distances[source], length, tuple(edges))
        self._metrics["selected_leg_time_s"] += time.monotonic() - started
        if self.leg_cache_size:
            self._leg_cache[pair] = result
            while len(self._leg_cache) > self.leg_cache_size:
                self._leg_cache.popitem(last=False)
        return result

    def metrics(self):
        return {**self._metrics, "distance_cache_entries": len(self._distance_cache),
                "distance_cache_values": sum(len(x[0]) for x in self._distance_cache.values()),
                "leg_cache_entries": len(self._leg_cache),
                "cached_path_edges": sum(len(x.edges) for x in self._leg_cache.values() if x is not None)}


class FrozenLegProvider:
    """Immutable pair lookup, deliberately not a graph of routable legs.

    The producer owns the selected-leg contract and can supply preselected
    road witnesses.  Missing pairs remain unreachable even if other supplied
    legs concatenate.  Safe zero relaxations are used by default.  Optional
    ``relaxations[(source,target,weight)]`` are a trusted producer contract:
    they must lower-bound *every continuation*, not merely the direct frozen
    leg; this class checks type/nonnegativity, not that external mathematical
    premise.  Do not populate them using selected-fastest lengths as a metric.
    """

    def __init__(self, legs, *, relaxations=None, check=None):
        started = time.monotonic()
        self.check = check
        pairs = {}
        nodes = set()
        for (source, target), leg in legs.items():
            _identifier(source, "source")
            _identifier(target, "target")
            nodes.update((source, target))
            if leg is None:
                pairs[source, target] = None
                continue
            if (leg.source, leg.target) != (source, target):
                raise ValueError("Frozen leg endpoints differ from its pair")
            duration, length = exact(leg.time_s), exact(leg.length_m)
            if duration < 0 or length < 0 or (source != target and (duration == 0 or length == 0)):
                raise ValueError("Frozen nontrivial legs need positive time and length")
            if source == target and (duration or length):
                raise ValueError("Frozen self legs must have zero time and length")
            edges = tuple(MappingProxyType(dict(e)) for e in leg.edges)
            if edges:
                anchor = source
                times = lengths = Fraction(0)
                for edge in edges:
                    if edge["source"] != anchor:
                        raise ValueError("Frozen leg road witness is not contiguous")
                    anchor = edge["target"]
                    times += exact(edge["time_s"])
                    lengths += exact(edge["length_m"])
                if anchor != target or times != duration or lengths != length:
                    raise ValueError("Frozen leg attributes differ from road witness")
            pairs[source, target] = IndexedLeg(source, target, duration, length, edges)
        self._legs = MappingProxyType(pairs)
        values = {}
        for (source, target, weight), value in (relaxations or {}).items():
            _identifier(source, "source")
            _identifier(target, "target")
            _weight(weight)
            value = exact(value)
            if value < 0:
                raise ValueError("Relaxation distances must be nonnegative")
            values[source, target, weight] = value
        self._relaxations = MappingProxyType(values)
        self.nodes = tuple(sorted(nodes))
        self._metrics = dict(index_builds=1, build_time_s=time.monotonic() - started,
                             selected_leg_queries=0, scalar_queries=0)

    def selected_leg(self, source, target):
        if self.check is not None:
            self.check()
        self._metrics["selected_leg_queries"] += 1
        if source == target:
            return IndexedLeg(source, target, Fraction(0), Fraction(0), ())
        return self._legs.get((source, target))

    def lower_bound(self, source, target, weight="time_s"):
        _weight(weight)
        self._metrics["scalar_queries"] += 1
        return self._relaxations.get((source, target, weight), Fraction(0))

    def distances_from(self, source, weight="time_s"):
        return MappingProxyType({node: self.lower_bound(source, node, weight) for node in self.nodes})

    def distances_to(self, target, weight="time_s"):
        return MappingProxyType({node: self.lower_bound(node, target, weight) for node in self.nodes})

    def metrics(self):
        return {**self._metrics, "nodes": len(self.nodes), "frozen_pairs": len(self._legs)}


_NATIVE_LIBRARIES = {}


def _current_rss_bytes():
    """Current process RSS on Linux; peak fallback for portable diagnostics."""
    import os
    import resource
    import sys
    try:
        with open('/proc/self/statm') as stream:
            return int(stream.read().split()[1]) * os.sysconf('SC_PAGE_SIZE')
    except (OSError, IndexError, ValueError):
        try:
            import psutil
            return psutil.Process().memory_info().rss
        except ImportError:
            return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == 'darwin' else 1024)


def _load_native_library(cache_directory):
    import ctypes
    from pathlib import Path
    import shutil
    import subprocess
    import tempfile
    source = Path(__file__).with_name('road_index_native.cpp')
    compiler = shutil.which('c++') or shutil.which('g++')
    if compiler is None:
        raise RuntimeError('Exact native road index requires a C++17 compiler and Boost headers')
    key = (str(source), source.stat().st_mtime_ns, source.stat().st_size, compiler)
    if key in _NATIVE_LIBRARIES:
        return _NATIVE_LIBRARIES[key]
    root = Path(cache_directory)
    root.mkdir(parents=True, exist_ok=True)
    build = Path(tempfile.mkdtemp(prefix='exact-road-native-', dir=root))
    binary = build / 'road_index.so'
    result = subprocess.run([compiler, '-O3', '-std=c++17', '-shared', '-fPIC',
                             str(source), '-o', str(binary)],
                            capture_output=True, text=True, timeout=45)
    if result.returncode:
        raise RuntimeError('Exact native road index compilation failed: ' + result.stderr[-4000:])
    lib = ctypes.CDLL(str(binary))
    callback_type = ctypes.CFUNCTYPE(ctypes.c_int)
    lib.hiroute_road_create.argtypes = [ctypes.c_char_p, ctypes.c_int, callback_type]
    lib.hiroute_road_create.restype = ctypes.c_void_p
    lib.hiroute_road_free.argtypes = [ctypes.c_void_p]
    lib.hiroute_road_free.restype = None
    lib.hiroute_road_error.argtypes = []
    lib.hiroute_road_error.restype = ctypes.c_char_p
    lib.hiroute_road_query.argtypes = [ctypes.c_void_p, ctypes.c_char_p,
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, callback_type]
    lib.hiroute_road_query.restype = ctypes.c_char_p
    _NATIVE_LIBRARIES[key] = (lib, callback_type)
    return lib, callback_type


class NativeRoadIndex:
    """Compact exact backend for the same index and selected-leg algorithm.

    ``graph_tsv`` has one edge per line with five tab-separated fields:
    source, target, edge_id, time_s, length_m. Weights are positive canonical
    integer or numerator/denominator strings. Export and loading are measured
    preprocessing work, never a free N-squared leg table.

    Each metric is multiplied by the LCM of all input denominators, giving
    exact integer Dijkstra with arbitrary precision. No rounding or speed/length
    tie break is introduced. Selected-leg reconstruction uses the same exact
    shortest-time DAG and lexicographic node/edge rule as ``RoadIndex``.

    The C++ index contains the full road graph. Python scalar maps expose only
    ``exposed_nodes`` (OD/candidate/landmark road anchors), so queries need not
    materialize millions of Python Fraction objects. Unknown/unreachable nodes
    are absent. ``lower_bound`` also accepts a source outside that exposed set.
    The graph and up to ``distance_cache_size`` scalar workspaces remain native;
    their residency and build time are reported separately from query deltas.
    """

    def __init__(self, graph_tsv, exposed_nodes, *, cache_directory,
                 distance_cache_size=2, leg_cache_size=4096, check=None):
        import ctypes
        if type(distance_cache_size) is not int or not 0 <= distance_cache_size <= 2**31 - 1:
            raise ValueError('distance_cache_size must be a nonnegative integer')
        if type(leg_cache_size) is not int or leg_cache_size < 0:
            raise ValueError('leg_cache_size must be a nonnegative integer')
        self.nodes = tuple(sorted(set(_identifier(n, 'exposed node') for n in exposed_nodes)))
        if any('\n' in node or '\r' in node for node in self.nodes):
            raise ValueError('Exposed road identifiers cannot contain line breaks')
        self._node_set = frozenset(self.nodes)
        self._exposed = '\n'.join(self.nodes)
        self.check = check
        self._pending = None
        self._handle = None
        self._leg_cache = OrderedDict()
        self._scalar_cache = OrderedDict()
        self.leg_cache_size = leg_cache_size
        self.distance_cache_size = distance_cache_size
        self._python_queries = self._python_hits = 0
        rss_before = _current_rss_bytes()
        started = time.monotonic()
        self._lib, callback_type = _load_native_library(cache_directory)
        self._compile_load_seconds = time.monotonic() - started
        def callback():
            try:
                if self.check is not None:
                    self.check()
                return 1
            except BaseException as exc:
                self._pending = exc
                return 0
        self._callback = callback_type(callback)
        self._handle = self._lib.hiroute_road_create(str(graph_tsv).encode(), distance_cache_size, self._callback)
        if not self._handle:
            self._raise_error()
        self._constructor_seconds = time.monotonic() - started
        self._index_rss_increment = max(0, _current_rss_bytes() - rss_before)

    def _raise_error(self):
        if self._pending is not None:
            error, self._pending = self._pending, None
            raise error
        message = self._lib.hiroute_road_error().decode('utf-8', errors='replace')
        if 'bad_alloc' in message or 'bad allocation' in message:
            raise MemoryError(message)
        raise RuntimeError(message)

    def _query(self, kind, anchor='', target='', weight='time_s', exposed=None):
        import json
        if self._handle is None:
            raise ValueError('Closed exact road index')
        self._pending = None
        raw = self._lib.hiroute_road_query(self._handle, kind.encode(), anchor.encode(),
            target.encode(), weight.encode(), (self._exposed if exposed is None else exposed).encode(),
            self._callback)
        if raw is None:
            self._raise_error()
        return json.loads(raw)

    def selected_leg(self, source, target):
        _identifier(source, 'source')
        _identifier(target, 'target')
        if self.check is not None:
            self.check()
        self._python_queries += 1
        pair = (source, target)
        if pair in self._leg_cache:
            self._python_hits += 1
            self._leg_cache.move_to_end(pair)
            return self._leg_cache[pair]
        raw = self._query('leg', source, target)
        leg = None if raw is None else IndexedLeg(source, target, exact(raw['time_s']),
            exact(raw['length_m']), tuple(MappingProxyType({**row,
                'time_s': exact(row['time_s']), 'length_m': exact(row['length_m'])}) for row in raw['edges']))
        if self.leg_cache_size:
            self._leg_cache[pair] = leg
            while len(self._leg_cache) > self.leg_cache_size:
                self._leg_cache.popitem(last=False)
        return leg

    def _distances(self, anchor, weight, reverse):
        _identifier(anchor, 'anchor')
        _weight(weight)
        if self.check is not None:
            self.check()
        key = (reverse, weight, anchor)
        if key in self._scalar_cache:
            self._scalar_cache.move_to_end(key)
            return self._scalar_cache[key]
        result = MappingProxyType({node: exact(value) for node, value in
            self._query('to' if reverse else 'from', anchor, weight=weight).items()})
        if self.distance_cache_size:
            self._scalar_cache[key] = result
            while len(self._scalar_cache) > self.distance_cache_size:
                self._scalar_cache.popitem(last=False)
        return result

    def distances_from(self, source, weight='time_s'):
        return self._distances(source, weight, False)

    def distances_to(self, target, weight='time_s'):
        return self._distances(target, weight, True)

    def lower_bound(self, source, target, weight='time_s'):
        _identifier(source, 'source')
        _identifier(target, 'target')
        _weight(weight)
        if source in self._node_set:
            return self.distances_to(target, weight).get(source)
        raw = self._query('to', target, weight=weight, exposed=source)
        return None if source not in raw else exact(raw[source])

    def metrics(self):
        native = self._query('metrics')
        return {**native, 'backend': 'exact_integer_scaled_cpp',
                'constructor_time_s': self._constructor_seconds,
                'compile_load_time_s': self._compile_load_seconds,
                'index_rss_increment_bytes': self._index_rss_increment,
                'process_current_rss_bytes': _current_rss_bytes(),
                'selected_leg_queries': self._python_queries,
                'selected_leg_cache_hits': self._python_hits,
                'leg_cache_entries': len(self._leg_cache),
                'cached_path_edges': sum(len(x.edges) for x in self._leg_cache.values() if x is not None)}

    def close(self):
        if self._handle is not None:
            self._lib.hiroute_road_free(self._handle)
            self._handle = None
            self._leg_cache.clear()
            self._scalar_cache.clear()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def __del__(self):
        if getattr(self, '_handle', None) is not None:
            self.close()
