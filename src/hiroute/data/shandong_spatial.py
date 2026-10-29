"""Spatial primitives for the bounded Shandong raw producer.

All distances used for attachment/scoring are ellipsoidal WGS84 geodesics.
Projection is confined to topology-preserving polygon clipping diagnostics;
the caller must freeze the projection and all thresholds in its contract.
"""
from __future__ import annotations

from pathlib import Path
from heapq import nsmallest
from math import isfinite
from hashlib import sha256
from dataclasses import dataclass


def read_osm_poly(path):
    """Read an OSM .poly boundary into a validated Shapely geometry."""
    p = Path(path)
    raw = p.read_bytes()
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    lines = raw.decode("utf-8").splitlines()
    rings = []
    current = None
    sign = None
    for line in lines[1:]:
        s = line.strip()
        if not s:
            continue
        if s == "END":
            if current is None:
                break
            if len(current) < 4:
                raise ValueError("polygon ring has fewer than four coordinates")
            rings.append((sign, current))
            current, sign = None, None
            continue
        if current is None:
            if s.startswith("!"):
                sign = -1
            else:
                sign = 1
            current = []
            continue
        fields = s.split()
        if len(fields) != 2:
            raise ValueError("invalid .poly coordinate row")
        lon, lat = map(float, fields)
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise ValueError(".poly coordinate outside WGS84 bounds")
        current.append((lon, lat))
    if current is not None:
        raise ValueError("unterminated .poly ring")
    exteriors = [Polygon(r) for sign, r in rings if sign > 0]
    holes = [Polygon(r) for sign, r in rings if sign < 0]
    if not exteriors:
        raise ValueError(".poly has no exterior rings")
    geom = unary_union(exteriors)
    if holes:
        geom = geom.difference(unary_union(holes))
    if geom.is_empty or not geom.is_valid:
        raise ValueError("invalid .poly geometry")
    return geom


def clip_lines_to_boundary(lines, boundary_wgs84, projection: str):
    """Clip WGS84 line geometries against a frozen projected boundary.

    Returns projected clipped geometries. This primitive intentionally does
    not invent graph node IDs at newly created clip intersections.
    """
    from pyproj import CRS, Transformer
    from shapely.ops import transform
    crs = CRS.from_user_input(projection)
    forward = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform
    projected_boundary = transform(forward, boundary_wgs84)
    out = []
    for line in lines:
        projected_line = transform(forward, line)
        clipped = projected_line.intersection(projected_boundary)
        if not clipped.is_empty:
            out.append(clipped)
    return tuple(out)


def _prefilter_site_nodes(indexed, center, candidate_count, finite_index):
    """Return the exact legacy prefilter prefix, using bounded top-k if finite."""
    def key(item):
        xyz, node = item
        tie = (0, int(node["node_id"])) if str(node["node_id"]).isdigit() else (1, str(node["node_id"]))
        return (sum((a-b)**2 for a,b in zip(center,xyz)), tie)
    if finite_index and all(isfinite(value) for value in center):
        # Include input position explicitly to preserve sorted()'s stable order
        # if duplicate rows have identical distance and node ID keys.
        return [row for _, row in nsmallest(candidate_count, enumerate(indexed),
            key=lambda pair:(key(pair[1]),pair[0]))]
    # Floating NaN keys do not define a total order; retain Python's historical
    # stable-sort behavior for those inputs rather than changing their semantics.
    return sorted(indexed,key=key)[:candidate_count]


def _snap_indexed_sites(sites, indexed, geod, max_distance_m, candidate_count, finite_index):
    from math import cos, radians, sin
    result = {}
    for site in sites:
        lat, lon = radians(float(site.lat)), radians(float(site.lon))
        center = (cos(lat)*cos(lon), cos(lat)*sin(lon), sin(lat))
        prefiltered = _prefilter_site_nodes(indexed, center, candidate_count, finite_index)
        choices = []
        for _, node in prefiltered:
            _, _, distance = geod.inv(site.lon, site.lat, node["lon"], node["lat"])
            nid = node["node_id"]
            tie = (0, int(nid)) if str(nid).isdigit() else (1, str(nid))
            choices.append((distance, tie, str(nid)))
        if not choices:
            continue
        distance, _, node_id = min(choices)
        if distance <= max_distance_m:
            result[site.site_id] = {"node_id": node_id, "distance_m": distance}
    return result


def snap_sites_wgs84(sites, nodes, *, max_distance_m: float, excluded_node_ids=(), candidate_count=4):
    """Attach each site to its nearest eligible graph node using WGS84 Geod.

    Ties resolve by numeric node ID when possible, then lexical ID. A radius is
    mandatory and is not chosen by this helper.
    """
    if not isinstance(max_distance_m, (int, float)) or max_distance_m < 0:
        raise ValueError("max_distance_m must be a nonnegative frozen value")
    from pyproj import Geod
    from math import cos, radians, sin
    if type(candidate_count) is not int or candidate_count < 1:
        raise ValueError("candidate_count must be a positive integer")
    geod = Geod(ellps="WGS84")
    excluded = set(excluded_node_ids)
    eligible = [n for n in nodes if n["node_id"] not in excluded]
    if not eligible:
        return {}
    def sphere(row):
        lat,lon=radians(float(row["lat"])),radians(float(row["lon"]))
        return (cos(lat)*cos(lon),cos(lat)*sin(lon),sin(lat))
    indexed=[(sphere(node),node) for node in eligible]
    # Non-finite coordinates can make floating-point sort keys non-total. Keep
    # the historical stable full-sort behavior for those inputs; use bounded
    # top-k selection only when the ordering is a total finite ordering.
    finite_index = all(all(isfinite(value) for value in xyz) for xyz, _ in indexed)
    return _snap_indexed_sites(sites, indexed, geod, max_distance_m,
                               candidate_count, finite_index)


# Isolated opt-in candidate: each forked child receives inherited read-only
# site/index objects and only a contiguous range; no global start method changes.
def _snap_sites_fork_chunk(bounds, sites, indexed, max_distance_m,
                           candidate_count, finite_index, sender):
    import os
    import pickle
    import time
    from pyproj import Geod
    from math import cos, radians, sin
    started = time.process_time()
    status = None
    try:
        # Create the PROJ Geod object in the child after fork.
        geod = Geod(ellps="WGS84")
        result = _snap_indexed_sites(
            sites[bounds[0]:bounds[1]], indexed, geod,
            max_distance_m, candidate_count, finite_index)
        status = ("ok", result)
    except BaseException as exc:
        try:
            status = ("exception", pickle.dumps(exc, protocol=pickle.HIGHEST_PROTOCOL))
        except BaseException as serialization_error:
            # Arbitrary custom exception instances are not always transferable
            # across processes. Such exceptions are outside the equivalence
            # guarantee and are reported explicitly in the parent.
            status = ("unserializable_exception",
                      type(exc).__module__, type(exc).__qualname__,
                      str(exc), repr(exc),
                      type(serialization_error).__module__,
                      type(serialization_error).__qualname__)
    record = (status, os.getpid(), time.process_time() - started, time.monotonic())
    try:
        sender.send(record)
    finally:
        sender.close()


class UnserializableWorkerException(TypeError):
    """A worker exception could not be transferred with its original type."""


def _current_rss_bytes():
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) * 1024
    raise RuntimeError("cannot read current process RSS")


def _select_site_workers(requested_workers, parent_rss_bytes, max_group_rss_bytes,
                         memory_margin_bytes):
    """Conservative fork envelope: parent RSS*(children+parent)+margin."""
    values = (requested_workers, parent_rss_bytes, max_group_rss_bytes, memory_margin_bytes)
    if type(requested_workers) is not int or not 1 <= requested_workers <= 6:
        raise ValueError("requested workers must be an integer from 1 through 6")
    if type(parent_rss_bytes) is not int or parent_rss_bytes < 1:
        raise ValueError("parent RSS must be a positive integer")
    if type(max_group_rss_bytes) is not int or max_group_rss_bytes < 1:
        raise ValueError("group RSS cap must be a positive integer")
    if type(memory_margin_bytes) is not int or memory_margin_bytes < 0:
        raise ValueError("memory margin must be a nonnegative integer")
    serial_estimate = parent_rss_bytes + memory_margin_bytes
    if serial_estimate > max_group_rss_bytes:
        raise MemoryError("serial parent RSS plus margin exceeds group RSS cap")
    for count in range(requested_workers, 1, -1):
        estimate = parent_rss_bytes * (count + 1) + memory_margin_bytes
        if estimate <= max_group_rss_bytes:
            return count, estimate
    return 1, serial_estimate


def snap_sites_wgs84_parallel(sites, nodes, *, max_distance_m: float,
                              excluded_node_ids=(), candidate_count=4,
                              workers=1, max_group_rss_bytes=24*1024**3,
                              memory_margin_bytes=2*1024**3, _profile=None):
    """Opt-in bounded fork candidate; serial remains the default API path.

    workers=1 is a direct pass-through. Parallel semantics are defined for
    ordinary RawSite-like records and exceptions that Python pickle preserves.
    The fork count is reduced using parent_RSS*(children+parent)+margin <= cap.
    Arbitrary stateful iterables/custom exceptions and OS worker termination
    cannot be equivalent to an in-process serial call. Call under the existing
    external supervisor: a live but nonterminating worker has no local timeout.
    """
    import os
    import time
    if type(workers) is int and workers == 1:
        started = time.process_time() if _profile is not None else None
        result = snap_sites_wgs84(
            sites, nodes, max_distance_m=max_distance_m,
            excluded_node_ids=excluded_node_ids, candidate_count=candidate_count)
        if _profile is not None:
            import os
            _profile.append({"pid":os.getpid(),"cpu_seconds":time.process_time()-started,
                             "requested_workers":1,"effective_workers":1,
                             "mode":"serial","estimated_group_rss_bytes":_current_rss_bytes()})
        return result
    if type(workers) is not int or not 2 <= workers <= 6:
        raise ValueError("workers must be an integer from 1 through 6")
    # Lazy iterables can have observable iteration order or raise while being
    # consumed. Keep their exact serial behavior rather than materializing them.
    if type(sites) not in (list, tuple):
        started = time.process_time() if _profile is not None else None
        result = snap_sites_wgs84(
            sites, nodes, max_distance_m=max_distance_m,
            excluded_node_ids=excluded_node_ids, candidate_count=candidate_count)
        if _profile is not None:
            import os
            _profile.append({"pid":os.getpid(),"cpu_seconds":time.process_time()-started,
                             "requested_workers":workers,"effective_workers":1,
                             "mode":"serial_nonmaterialized_input"})
        return result
    if not isinstance(max_distance_m, (int, float)) or max_distance_m < 0:
        raise ValueError("max_distance_m must be a nonnegative frozen value")
    from pyproj import Geod
    from math import cos, radians, sin
    if type(candidate_count) is not int or candidate_count < 1:
        raise ValueError("candidate_count must be a positive integer")
    if type(max_group_rss_bytes) is not int or max_group_rss_bytes < 1:
        raise ValueError("group RSS cap must be a positive integer")
    if type(memory_margin_bytes) is not int or memory_margin_bytes < 0:
        raise ValueError("memory margin must be a nonnegative integer")
    geod = Geod(ellps="WGS84")
    excluded = set(excluded_node_ids)
    eligible = [n for n in nodes if n["node_id"] not in excluded]
    if not eligible:
        return {}
    def sphere(row):
        lat, lon = radians(float(row["lat"])), radians(float(row["lon"]))
        return (cos(lat)*cos(lon), cos(lat)*sin(lon), sin(lat))
    indexed = [(sphere(node), node) for node in eligible]
    finite_index = all(all(isfinite(value) for value in xyz) for xyz, _ in indexed)
    import multiprocessing as mp
    import resource
    children_usage_before = (resource.getrusage(resource.RUSAGE_CHILDREN)
                            if _profile is not None else None)
    if "fork" not in mp.get_all_start_methods():
        raise RuntimeError("bounded site parallelism requires the Linux fork start method")
    materialized_sites = sites if type(sites) is tuple else tuple(sites)
    if not materialized_sites:
        return {}
    requested_children = min(workers, len(materialized_sites))
    reduction_reason = ("site_count" if requested_children < workers else "none")
    parent_rss_bytes = _current_rss_bytes()
    count, estimated_group_rss = _select_site_workers(
        requested_children, parent_rss_bytes, max_group_rss_bytes, memory_margin_bytes)
    if count < requested_children:
        reduction_reason = "memory_envelope"
    if count == 1:
        started = time.process_time() if _profile is not None else None
        result = _snap_indexed_sites(materialized_sites, indexed, geod,
                                     max_distance_m, candidate_count, finite_index)
        if _profile is not None:
            import os
            _profile.append({"pid":os.getpid(),"cpu_seconds":time.process_time()-started,
                             "requested_workers":workers,"effective_workers":1,
                             "mode":("serial_site_count" if reduction_reason == "site_count" else "serial_memory_fallback"),
                             "worker_reduction_reason":reduction_reason,
                             "parent_rss_bytes":parent_rss_bytes,
                             "estimated_group_rss_bytes":estimated_group_rss,
                             "max_group_rss_bytes":max_group_rss_bytes,
                             "memory_margin_bytes":memory_margin_bytes})
        return result
    del geod
    bounds = [(i*len(materialized_sites)//count,
               (i+1)*len(materialized_sites)//count) for i in range(count)]
    ctx = mp.get_context("fork")
    from multiprocessing.connection import wait
    processes = []
    receivers = []
    records = [None] * count
    pending = set(range(count))
    eof = set()
    try:
        for i, bound in enumerate(bounds):
            receiver, sender = ctx.Pipe(duplex=False)
            proc = ctx.Process(
                target=_snap_sites_fork_chunk,
                args=(bound, materialized_sites, indexed, max_distance_m,
                      candidate_count, finite_index, sender))
            try:
                proc.start()
            except BaseException:
                sender.close()
                receiver.close()
                raise
            sender.close()
            processes.append(proc)
            receivers.append(receiver)
        while pending:
            handles = {}
            for i in pending:
                if i not in eof:
                    handles[receivers[i]] = (i, "pipe")
                handles[processes[i].sentinel] = (i, "sentinel")
            for handle in wait(handles):
                i, kind = handles[handle]
                # Pipe and process sentinel can be ready in the same wait()
                # result. A record may remove i before the sentinel is visited.
                if i not in pending:
                    continue
                if kind == "pipe":
                    try:
                        records[i] = receivers[i].recv()
                        pending.remove(i)
                    except EOFError:
                        eof.add(i)
                else:
                    processes[i].join()
                    if records[i] is None:
                        if i not in eof and receivers[i].poll():
                            try:
                                records[i] = receivers[i].recv()
                            except EOFError:
                                pass
                        if records[i] is None:
                            records[i] = (("worker_exit", processes[i].exitcode),
                                          processes[i].pid, None, time.monotonic())
                        pending.remove(i)
        for proc in processes:
            proc.join()
        for i, proc in enumerate(processes):
            if proc.exitcode != 0:
                records[i] = (("worker_exit", proc.exitcode), proc.pid, None, time.monotonic())
    finally:
        for proc in processes:
            if proc.is_alive():
                proc.terminate()
            proc.join()
        for conn in receivers:
            conn.close()
        for proc in processes:
            proc.close()
    if _profile is not None:
        children_usage_after = resource.getrusage(resource.RUSAGE_CHILDREN)
        children_cpu_delta = (
            children_usage_after.ru_utime + children_usage_after.ru_stime
            - children_usage_before.ru_utime - children_usage_before.ru_stime)
        # RUSAGE_CHILDREN is cumulative for waited children. Taking one before /
        # after delta per owned batch charges each reaped worker once. Per-worker
        # self reports remain diagnostics only and must not be summed on top.
        _profile.append({
            "pid": os.getpid(),
            "mode": "fork",
            "requested_workers": workers,
            "effective_workers": count,
            "worker_reduction_reason": reduction_reason,
            "parent_rss_bytes": parent_rss_bytes,
            "estimated_group_rss_bytes": estimated_group_rss,
            "max_group_rss_bytes": max_group_rss_bytes,
            "memory_margin_bytes": memory_margin_bytes,
            "child_cpu_seconds": max(0.0, children_cpu_delta),
            "cpu_accounting": "RUSAGE_CHILDREN before/after delta; worker self reports are diagnostic and not additive",
            "worker_records": [
                {"pid": row[1],
                 "reported_cpu_seconds": row[2] if row[0][0] != "worker_exit" else None,
                 "finished_at": row[3],
                 "status": row[0][0],
                 "exit_code": row[0][1] if row[0][0] == "worker_exit" else None}
                for row in records]})
    # Resolve failures by contiguous input block order, independent of which
    # worker finished first. Each child stops at its own first failing site.
    result = {}
    for record in records:
        status = record[0]
        if status[0] == "exception":
            import pickle
            raise pickle.loads(status[1])
        if status[0] == "unserializable_exception":
            raise UnserializableWorkerException(
                f"cannot transfer worker exception {status[1]}.{status[2]}: {status[3]}")
        if status[0] == "worker_exit":
            raise ChildProcessError(f"site worker exited unexpectedly with code {status[1]}")
        result.update(status[1])
    return result


def geodesic_detour_scores_wgs84(sites, origin, destination):
    """Return site detours d(origin,site)+d(site,dest)-d(origin,dest), metres."""
    from pyproj import Geod
    geod = Geod(ellps="WGS84")
    def distance(a, b):
        return abs(geod.inv(a[0], a[1], b[0], b[1])[2])
    direct = distance(origin, destination)
    return {s.site_id: max(0.0, distance(origin, (s.lon, s.lat)) +
                              distance((s.lon, s.lat), destination) - direct)
            for s in sites}


@dataclass
class LineClipContext:
    """Per-import projection state; never shared between raw runs."""
    boundary_wgs84: object
    projection: str
    forward: object
    inverse: object
    projected_boundary: object | None = None


def make_line_clip_context(boundary_wgs84, projection: str) -> LineClipContext:
    """Prepare immutable boundary projection and transforms for one import."""
    from pyproj import CRS, Transformer
    from shapely.ops import transform
    crs = CRS.from_user_input(projection)
    forward_transformer = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    inverse_transformer = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    forward = forward_transformer.transform
    inverse = inverse_transformer.transform
    return LineClipContext(boundary_wgs84, projection, forward, inverse)


def clip_line_segments(line, boundary_wgs84, projection: str, *, osm_way_id: str,
                       source_node_id: str, target_node_id: str, node_coordinates,
                       full_length_m, context: LineClipContext | None = None):
    """Clip one oriented PBF edge into ordered, provenance-bound segments.

    Segment lengths are allocated proportionally to projected geometry length
    against Pyrosm's original edge length. This is a frozen engineering rule,
    not a claim that projected geometry length is the source's exact road length.
    Synthetic boundary nodes are way-scoped so unrelated ways do not become
    connected merely because their geometries touch the polygon boundary.
    """
    from fractions import Fraction
    from decimal import Decimal
    from pyproj import CRS, Transformer
    from shapely.geometry import Point, LineString, MultiLineString, GeometryCollection
    from shapely.ops import transform
    if context is None:
        crs = CRS.from_user_input(projection)
        forward = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform
        inverse = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform
        projected_line = transform(forward, line)
        projected_boundary = transform(forward, boundary_wgs84)
    else:
        if context.boundary_wgs84 is not boundary_wgs84 or context.projection != projection:
            raise ValueError("clip context does not match this boundary and projection")
        forward = context.forward
        inverse = context.inverse
        projected_line = transform(forward, line)
        projected_boundary = context.projected_boundary
        if projected_boundary is None:
            projected_boundary = transform(forward, boundary_wgs84)
            context.projected_boundary = projected_boundary
    if projected_line.is_empty or projected_line.length <= 0:
        return (), ()
    clipped = projected_line.intersection(projected_boundary)
    def lines(g):
        if isinstance(g, LineString): return [g]
        if isinstance(g, (MultiLineString, GeometryCollection)):
            return [part for child in g.geoms for part in lines(child)]
        return []
    parts = []
    for segment in lines(clipped):
        if segment.length <= 0: continue
        coords = list(segment.coords)
        m0 = projected_line.project(Point(coords[0]))
        m1 = projected_line.project(Point(coords[-1]))
        if m1 < m0: coords.reverse(); m0, m1 = m1, m0
        parts.append((m0, m1, LineString(coords)))
    parts.sort(key=lambda x: (x[0], x[1], x[2].wkb))
    def endpoint_id(xy, measure, is_start):
        if is_start and measure <= 1e-6: return str(source_node_id), None
        if not is_start and abs(measure-projected_line.length) <= 1e-6: return str(target_node_id), None
        lon, lat = inverse(xy[0], xy[1])
        token = sha256((format(xy[0], ".6f")+","+format(xy[1], ".6f")).encode()).hexdigest()[:20]
        nid = f"clip:{osm_way_id}:{token}"
        return nid, {"node_id":nid,"lon":float(lon),"lat":float(lat)}
    out=[]; synthetic={}; total=Fraction(Decimal(str(full_length_m)))
    for index,(m0,m1,segment) in enumerate(parts):
        a,na=endpoint_id(segment.coords[0],m0,True); b,nb=endpoint_id(segment.coords[-1],m1,False)
        if a==b: continue
        if na: synthetic[na["node_id"]]=na
        if nb: synthetic[nb["node_id"]]=nb
        ratio=Fraction(str(segment.length/projected_line.length))
        out.append({"segment_index":index,"source":a,"target":b,"length_m":total*ratio,
                    "fraction":ratio,"source_measure_m":(m0,m1)})
    return tuple(out),tuple(synthetic[k] for k in sorted(synthetic))
