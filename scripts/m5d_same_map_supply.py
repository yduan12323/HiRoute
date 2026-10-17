"""Count existing-map OD/Site supply; do not select queries or optimize."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

import pandas as pd


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--sites", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    started = time.monotonic()
    features = pd.read_parquet(args.features, columns=["instance_id", "osm_type", "osm_id", "progress", "access_node"])
    sites = pd.read_parquet(args.sites, columns=["osm_type", "osm_id", "access_node", "transport_capabilities", "meal_count", "toilet_count"])
    attached = sites[sites.access_node.notna()]
    joined = features.merge(attached, on=["osm_type", "osm_id", "access_node"], how="inner")
    joined = joined[joined.progress.notna() & joined.progress.between(0, 1)]
    joined["charging"] = joined.transport_capabilities.astype(str).str.contains("charge", regex=False)
    joined["schedule_support"] = (joined.meal_count.fillna(0) >= 1) | (joined.toilet_count.fillna(0) >= 1)
    counts = joined.groupby("instance_id").agg(rows=("osm_id", "size"),
                                                charging=("charging", "sum"),
                                                schedule_support=("schedule_support", "sum"))
    by_od = [{"instance_id": int(index), **{key: int(value) for key, value in row.items()}}
             for index, row in counts.iterrows()]
    result = {"schema": "hiroute.m5d.same_map_supply.v1",
              "tool_sha256": sha(Path(__file__)), "features_sha256": sha(args.features),
              "sites_sha256": sha(args.sites), "feature_od_count": int(features.instance_id.nunique()),
              "static_site_count": len(sites), "attached_site_count": len(attached),
              "od_count": len(by_od), "all_30_support_32_charging_candidates":
              len(by_od) == 30 and all(row["charging"] >= 32 for row in by_od),
              "od_count_supporting_128_charging_candidates": sum(row["charging"] >= 128 for row in by_od),
              "elapsed_seconds": time.monotonic() - started, "no_route_or_optimizer_calls": True,
              "scope_note": "Supply screen only; Site semantics, final eligibility and OD sampling remain unfrozen.",
              "od": by_od}
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
