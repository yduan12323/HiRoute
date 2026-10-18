"""Freeze nested 8/16/32/128 charging Site candidates for fixed OD00.

Selection uses only attached Site identity/capability and geographic progress
along the already frozen OD chord. It does not inspect route or solver output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import time

import pandas as pd
import numpy as np


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def vdc(index: int) -> float:
    out, scale = 0.0, 0.5
    while index:
        out += (index & 1) * scale
        index >>= 1
        scale *= 0.5
    return out


def run(slate_path: Path, slate_sha256: str, geographic_path: Path,
        geographic_sha256: str, sites_path: Path):
    started = time.monotonic_ns()
    for path, digest in ((slate_path, slate_sha256),
                         (geographic_path, geographic_sha256)):
        if sha(path) != digest:
            raise ValueError("Frozen OD or geographic input changed")
    slate = json.loads(slate_path.read_text())
    geographic = json.loads(geographic_path.read_text())
    if (slate.get("schema") != "hiroute.m5d.fixed_12od_candidate_slate.v1" or
            geographic.get("schema") != "hiroute.m5d.geographic_screen.v1" or
            sha(sites_path) != geographic["sites_sha256"]):
        raise ValueError("Fixed OD or Site catalog source binding failed")
    od = slate["od"][0]
    if od["od_id"] != "OD00":
        raise ValueError("Only the prespecified first OD is selected")
    locations = {row["site_id"]: row for row in geographic["fixed_grid_candidates"]}
    origin, destination = locations[od["origin_site"]], locations[od["destination_site"]]
    if (int(origin["access_node"]) != od["origin_anchor"] or
            int(destination["access_node"]) != od["destination_anchor"]):
        raise ValueError("OD road anchors differ from fixed geographic source")
    sites = pd.read_parquet(sites_path,
        columns=["site_id", "access_node", "lat", "lon", "transport_capabilities",
                 "meal_count", "toilet_count"])
    lat0 = (float(origin["lat"]) + float(destination["lat"])) / 2
    scale_x = 111320 * math.cos(math.radians(lat0))
    scale_y = 111320
    dx = (float(destination["lon"]) - float(origin["lon"])) * scale_x
    dy = (float(destination["lat"]) - float(origin["lat"])) * scale_y
    squared = dx * dx + dy * dy
    if squared <= 0:
        raise ValueError("Frozen OD has no geographic chord")
    segment_m = math.sqrt(squared)
    choices = []
    for row in sites.itertuples(index=False):
        if (pd.isna(row.access_node) or not isinstance(row.transport_capabilities,
                                                       (list, tuple, np.ndarray))
                or "charge" not in row.transport_capabilities or
                row.site_id in (od["origin_site"], od["destination_site"]) or
                int(row.access_node) in (od["origin_anchor"], od["destination_anchor"])):
            continue
        x = (float(row.lon) - float(origin["lon"])) * scale_x
        y = (float(row.lat) - float(origin["lat"])) * scale_y
        progress = (x * dx + y * dy) / squared
        if not 0 < progress < 1:
            continue
        perpendicular = abs(x * dy - y * dx) / segment_m
        choices.append((str(row.site_id), int(row.access_node), progress,
                        perpendicular, bool((row.meal_count or 0) > 0 or
                                            (row.toilet_count or 0) > 0)))
    radius = next((r for r in (25000, 50000, 100000, 200000)
                   if sum(row[3] <= r for row in choices) >= 128), None)
    if radius is None:
        raise ValueError("Fixed OD lacks 128 corridor charging Sites")
    eligible = [row for row in choices if row[3] <= radius]
    selected = []
    used = set()
    for ordinal in range(1, 129):
        target = vdc(ordinal)
        row = min((row for row in eligible if row[0] not in used),
                  key=lambda item: (abs(item[2] - target) + item[3] / segment_m,
                                    item[3], item[0]))
        used.add(row[0])
        selected.append(dict(site_id=row[0], anchor_id=f"road:{row[1]}",
            access_node=row[1], progress=row[2], perpendicular_m=row[3],
            schedule_support=row[4], effects=["C"]))
    return dict(schema="hiroute.m5d.fixed_od00_nested_pool.v1",
        role="geographic_input_selection_no_route_or_optimizer_result",
        slate_sha256=slate_sha256, geographic_sha256=geographic_sha256,
        site_catalog_sha256=geographic["sites_sha256"], od_id="OD00",
        origin_anchor=od["origin_anchor"], destination_anchor=od["destination_anchor"],
        radius_m=radius, eligible_charging_site_count=len(eligible),
        selection_rule="van_der_Corput_progress_1_to_128_then_min_progress_error_plus_normalized_perpendicular_distance_with_site_id_tie",
        pool_prefix_sizes=[8, 16, 32, 128], sites=selected,
        first_32_schedule_support_count=sum(row["schedule_support"] for row in selected[:32]),
        elapsed_ns=time.monotonic_ns() - started,
        qualified_multi_charge_query_count=0,
        qualification="candidate_pools_only_seed_and_schedule_pending")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slate", type=Path, required=True)
    parser.add_argument("--slate-sha256", required=True)
    parser.add_argument("--geographic", type=Path, required=True)
    parser.add_argument("--geographic-sha256", required=True)
    parser.add_argument("--sites", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    result = run(args.slate, args.slate_sha256, args.geographic,
                 args.geographic_sha256, args.sites)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True,
                                      allow_nan=False) + "\n")
    print(args.output, sha(args.output))


if __name__ == "__main__":
    main()
