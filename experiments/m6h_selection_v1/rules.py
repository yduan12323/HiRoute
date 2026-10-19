"""Frozen, outcome-blind OD and original capability-balanced pool rules.

This module does not read files, load a graph, route, seed, or solve. Callers must
seal the complete OD slate BEFORE invoking build_capability_pool. A pool failure
belongs to that OD and never authorizes replacement. See the normative protocol.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import math
from numbers import Integral, Real

RULE_VERSION = "hiroute.m6h.selection_rules.v1"
MAX_ENDPOINT_CELLS = 512
REQUIRED_GROUPS = 6


class InvalidInput(ValueError):
    pass


class PoolFailure(ValueError):
    """A selected OD's retained failure, never an OD selection predicate."""


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise InvalidInput(f"invalid finite numeric {name}")
    return float(value)


def endpoint(row):
    """Strict identity/coordinates; no capability or route-based endpoint test."""
    sid, node = row.get("site_id"), row.get("access_node")
    if not isinstance(sid, str) or not sid:
        raise InvalidInput("site_id must be a nonempty string")
    lat, lon = _number(row.get("lat"), "lat"), _number(row.get("lon"), "lon")
    if not -90 < lat < 90 or not -180 <= lon < 180:
        raise InvalidInput("coordinate outside nonpolar geographic range")
    if node is not None and (isinstance(node, bool) or not isinstance(node, Integral) or node < 0):
        raise InvalidInput("anchor must be null or a nonnegative integer")
    return dict(site_id=sid, access_node=None if node is None else int(node), lat=lat, lon=lon)


def _catalog(rows):
    result, seen = [], set()
    for raw in rows:
        row = endpoint(raw)
        if row["site_id"] in seen:
            raise InvalidInput("duplicate Site identity")
        seen.add(row["site_id"])
        result.append((row, raw))
    return result


def cell(row):
    """Absolute half-degree cells; no catalog-derived bounds or retuning."""
    return (math.floor(row["lat"] * 2), math.floor(row["lon"] * 2))


def group(a, b):
    return tuple(sorted((cell(a), cell(b))))


def _cell_near(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1])) <= 1


def groups_near(a, b):
    """Orientation-free endpoint-neighborhood overlap, including the same group."""
    return ((_cell_near(a[0], b[0]) and _cell_near(a[1], b[1])) or
            (_cell_near(a[0], b[1]) and _cell_near(a[1], b[0])))


def _has_near_group(g, known):
    # At most 81 hash lookups per prospective pair, independent of DEV pair count.
    for da, db, dc, dd in itertools.product((-1, 0, 1), repeat=4):
        neighbor = tuple(sorted(((g[0][0] + da, g[0][1] + db),
                                 (g[1][0] + dc, g[1][1] + dd))))
        if neighbor in known:
            return True
    return False


def validate_exposures(registry):
    if registry.get("schema") != "hiroute.m6h.exposure_registry.v1":
        raise InvalidInput("exposure registry schema")
    coverage = registry.get("coverage", {})
    if (coverage.get("status") != "complete" or not coverage.get("reviewer") or
            coverage.get("scope") != "recovered_project_development_artifacts" or
            coverage.get("known_missing_artifacts") != []):
        raise InvalidInput("exposure audit incomplete")
    required = {"all_geographic_screens", "all_route_screen_pairs", "all_dev_queries",
                "all_diagnostics", "all_candidate_selection"}
    if set(coverage.get("included_categories", [])) != required:
        raise InvalidInput("exposure categories incomplete")
    sources = registry.get("sources", [])
    if not sources or any(not s.get("source_id") or not _sha(s.get("sha256")) for s in sources):
        raise InvalidInput("exposure sources must be content-bound")
    source_ids = {s["source_id"] for s in sources}
    if len(source_ids) != len(sources):
        raise InvalidInput("duplicate exposure source")
    pairs = []
    records = registry.get("records", [])
    if not records:
        raise InvalidInput("known DEV history cannot have an empty exposure registry")
    for record in records:
        if record.get("source_id") not in source_ids or not record.get("reason"):
            raise InvalidInput("unbound exposure record")
        a, b = endpoint(record["origin"]), endpoint(record["destination"])
        if a["access_node"] is None or b["access_node"] is None:
            raise InvalidInput("exposure pair requires resolved anchors")
        pairs.append((a, b))
    inspected = registry.get("inspected_endpoints", [])
    for record in inspected:
        if record.get("source_id") not in source_ids or not record.get("reason"):
            raise InvalidInput("unbound inspected endpoint")
        endpoint(record["endpoint"])
    return pairs, [endpoint(r["endpoint"]) for r in inspected]


def _sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def select_od_slate(site_rows, registry, *, site_catalog_sha256):
    """One representative/cell; lexicographic unordered pairs; fixed greedy six.

    Failure to find six under THIS bounded enumeration returns DATA_LIMITED and
    forbids partial execution, widening the cells, or selecting alternate reps.
    """
    if not _sha(site_catalog_sha256):
        raise InvalidInput("catalog digest required")
    exposures, inspected = validate_exposures(registry)
    cells = {}
    for row, _ in _catalog(site_rows):
        if row["access_node"] is None:
            continue
        key = cell(row)
        if key not in cells or row["site_id"] < cells[key]["site_id"]:
            cells[key] = row
    if len(cells) > MAX_ENDPOINT_CELLS:
        raise InvalidInput("endpoint cell enumeration exceeds frozen 512-cell bound")
    # Representatives are selected before exposure exclusion: no alternate Site
    # from a contaminated representative's cell may be substituted.
    reps = [cells[key] for key in sorted(cells)]
    excluded_ids = {e["site_id"] for pair in exposures for e in pair} | {e["site_id"] for e in inspected}
    excluded_anchors = {e["access_node"] for pair in exposures for e in pair} | {
        e["access_node"] for e in inspected if e["access_node"] is not None}
    exposure_groups = {group(*pair) for pair in exposures}
    selected, examined = [], 0
    for a, b in itertools.combinations(reps, 2):
        examined += 1
        if a["access_node"] == b["access_node"]:
            continue
        if any(e["site_id"] in excluded_ids or e["access_node"] in excluded_anchors for e in (a, b)):
            continue
        g = group(a, b)
        # Reject geographically neighboring endpoint cells within each OD too.
        if _cell_near(*g) or _has_near_group(g, exposure_groups):
            continue
        if any(groups_near(g, group(s["origin"], s["destination"])) or
               {a["access_node"], b["access_node"]} & {s["origin_anchor"], s["destination_anchor"]}
               for s in selected):
            continue
        selected.append(dict(od_id=f"HOD{len(selected):02d}", geographic_group=[list(c) for c in g],
            origin=a, destination=b, origin_site=a["site_id"], destination_site=b["site_id"],
            origin_anchor=a["access_node"], destination_anchor=b["access_node"]))
        if len(selected) == REQUIRED_GROUPS:
            break
    return dict(schema="hiroute.m6h.od_selection.v1", rule_version=RULE_VERSION,
        status="SELECTED" if len(selected) == REQUIRED_GROUPS else "DATA_LIMITED",
        requested_group_count=REQUIRED_GROUPS, selected_group_count=len(selected),
        site_catalog_sha256=site_catalog_sha256, exposure_registry_sha256=digest(registry),
        representative_cell_count=len(reps), examined_pair_count=examined, od=selected,
        no_replacement=True, statistical_independence_claim=False,
        generalization_scope="unseen_endpoint_region_pairs_on_existing_map_not_cross_region")


def vdc(index):
    out, scale = 0.0, 0.5
    while index:
        out += (index & 1) * scale
        index >>= 1
        scale *= 0.5
    return out


def build_capability_pool(origin, destination, site_rows, *, od_id):
    """Literal original pool arithmetic/order, with strict invalid-input checks."""
    origin, destination = endpoint(origin), endpoint(destination)
    if origin["access_node"] is None or destination["access_node"] is None:
        raise InvalidInput("OD endpoint lacks anchor")
    lat0 = (float(origin["lat"]) + float(destination["lat"])) / 2
    sx = 111320 * math.cos(math.radians(lat0)); sy = 111320
    dx = (float(destination["lon"]) - float(origin["lon"])) * sx
    dy = (float(destination["lat"]) - float(origin["lat"])) * sy
    squared = dx * dx + dy * dy
    segment = math.sqrt(squared)
    if squared <= 0 or not math.isfinite(segment):
        raise InvalidInput("zero or invalid OD chord")
    choices = []
    for row, raw in _catalog(site_rows):
        if row["access_node"] is None:
            continue
        capabilities = raw.get("transport_capabilities")
        if not isinstance(capabilities, (list, tuple)) or any(not isinstance(c, str) for c in capabilities):
            raise InvalidInput("capabilities must be a string sequence")
        meal_count = raw.get("meal_count")
        if meal_count is not None:
            meal_count = _number(meal_count, "meal_count")
            if meal_count < 0 or not meal_count.is_integer():
                raise InvalidInput("meal_count must be a nonnegative integer or null")
        charge, meal = "charge" in capabilities, meal_count is not None and meal_count >= 1
        if not charge and not meal:
            continue
        effects = (["C"] if charge else []) + (["S"] if meal else []) + (["CS"] if charge and meal else [])
        if row["site_id"] in (origin["site_id"], destination["site_id"]) or row["access_node"] in (origin["access_node"], destination["access_node"]):
            continue
        x = (float(row["lon"]) - float(origin["lon"])) * sx
        y = (float(row["lat"]) - float(origin["lat"])) * sy
        progress = (x * dx + y * dy) / squared
        if not 0 < progress < 1:
            continue
        perpendicular = abs(x * dy - y * dx) / segment
        choices.append((row["site_id"], row["access_node"], progress, perpendicular, effects))
    radius = next((r for r in (25000, 50000, 100000, 200000)
                   if sum(row[3] <= r for row in choices) >= 128), None)
    if radius is None:
        raise PoolFailure("INSUFFICIENT_CAPABLE_SITES")
    eligible = [row for row in choices if row[3] <= radius]
    if sum("C" in row[4] for row in eligible) < 64 or sum("S" in row[4] for row in eligible) < 64:
        raise PoolFailure("INSUFFICIENT_CAPABILITY_AT_FIRST_RADIUS")
    chosen, used = [], set()
    for ordinal in range(1, 129):
        target, required = vdc(ordinal), "C" if ordinal % 2 else "S"
        available = [r for r in eligible if r[0] not in used and required in r[4]]
        if not available:
            raise PoolFailure("CAPABILITY_EXHAUSTED")
        row = min(available, key=lambda r: (abs(r[2] - target) + r[3] / segment, r[3], r[0]))
        used.add(row[0])
        chosen.append(dict(site_id=row[0], anchor_id=f"road:{row[1]}", access_node=row[1],
                           effects=row[4], progress=row[2], perpendicular_m=row[3]))
    return dict(od_id=od_id, status="READY", origin_anchor=origin["access_node"],
        destination_anchor=destination["access_node"], radius_m=radius,
        eligible_capable_site_count=len(eligible), sites=chosen, prefix_sizes=[8, 32, 128])
