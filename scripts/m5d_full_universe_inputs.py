"""Materialize the six prespecified complete eligible Site universes."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
import pandas as pd


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canon(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode()


def run(slate_path: Path, geo_path: Path, pool_path: Path,
        sites_path: Path, query_path: Path, out: Path):
    slate, geo, pools, queries = (json.loads(path.read_bytes()) for path in
        (slate_path, geo_path, pool_path, query_path))
    if (pools["slate_sha256"] != sha(slate_path) or
            pools["geographic_sha256"] != sha(geo_path) or
            pools["site_catalog_sha256"] != sha(sites_path) or
            queries["query_count"] != 48):
        raise ValueError("Complete-universe source closure differs")
    targets = [item["query_id"] for item in queries["queries"][:6]]
    target_ods = {item["od_id"] for item in queries["queries"][:6]}
    locations = {row["site_id"]: row for row in geo["fixed_grid_candidates"]}
    frame = pd.read_parquet(sites_path, columns=["site_id", "access_node", "lat", "lon",
        "transport_capabilities", "meal_count"])
    all_sites = []
    for row in frame.itertuples(index=False):
        if pd.isna(row.access_node):
            continue
        charge = (isinstance(row.transport_capabilities, (list, tuple, np.ndarray))
                  and "charge" in row.transport_capabilities)
        meal = pd.notna(row.meal_count) and row.meal_count >= 1
        if charge or meal:
            effects = (["C"] if charge else []) + (["S"] if meal else []) + (
                ["CS"] if charge and meal else [])
            all_sites.append((str(row.site_id), int(row.access_node),
                              float(row.lat), float(row.lon), effects))
    pool_by_id = {row["od_id"]: row for row in pools["pools"]}
    universes = {}
    for od in slate["od"]:
        if od["od_id"] not in target_ods:
            continue
        pool = pool_by_id[od["od_id"]]
        origin, dest = locations[od["origin_site"]], locations[od["destination_site"]]
        lat0 = (float(origin["lat"]) + float(dest["lat"])) / 2
        sx, sy = 111320 * math.cos(math.radians(lat0)), 111320
        dx, dy = ((float(dest["lon"]) - float(origin["lon"])) * sx,
                  (float(dest["lat"]) - float(origin["lat"])) * sy)
        squared = dx * dx + dy * dy
        segment = math.sqrt(squared)
        if squared <= 0:
            raise ValueError("Zero OD chord")
        eligible = []
        for site_id, node, lat, lon, effects in all_sites:
            if (site_id in (od["origin_site"], od["destination_site"]) or
                    node in (od["origin_anchor"], od["destination_anchor"])):
                continue
            x, y = (lon - float(origin["lon"])) * sx, (lat - float(origin["lat"])) * sy
            progress = (x * dx + y * dy) / squared
            if not 0 < progress < 1:
                continue
            perpendicular = abs(x * dy - y * dx) / segment
            if perpendicular <= pool["radius_m"]:
                eligible.append({"site_id": site_id, "anchor_id": f"road:{node}",
                                 "effects": effects})
        eligible.sort(key=lambda row: row["site_id"])
        if (len(eligible) != pool["eligible_capable_site_count"] or
                len({row["site_id"] for row in eligible}) != len(eligible) or
                not {row["site_id"] for row in pool["sites"]} <=
                    {row["site_id"] for row in eligible}):
            raise ValueError("Full eligible universe differs from frozen pool")
        universes[od["od_id"]] = {"site_count": len(eligible),
            "site_rows_sha256": hashlib.sha256(canon(eligible)).hexdigest(),
            "sites": eligible}
    if target_ods != set(universes):
        raise ValueError("Six complete-universe query targets are missing")
    result = {"schema": "hiroute.m5d.six_full_universe_inputs.v1",
        "source_sha256": {"slate": sha(slate_path), "geographic": sha(geo_path),
            "pools": sha(pool_path), "site_catalog": sha(sites_path),
            "queries": sha(query_path)},
        "target_query_ids": targets, "universes_by_od": universes,
        "numerical_models_run": 0,
        "status": "frozen_inputs_only_no_full_universe_solver_run"}
    with out.open("x") as stream:
        json.dump(result, stream, sort_keys=True, separators=(",", ":"))
        stream.write("\n")


if __name__ == "__main__":
    run(*(Path(value) for value in sys.argv[1:7]))
