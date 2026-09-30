"""Deterministic conversion of Pyrosm segments to directed Parquet tables."""
from __future__ import annotations

import re
from collections import Counter

import numpy as np
import pandas as pd
import shapely


ATTRIBUTES = ["highway", "name", "ref", "oneway", "junction", "maxspeed", "maxspeed:forward", "maxspeed:backward",
              "toll", "access", "vehicle", "motor_vehicle", "motorcar", "access:conditional",
              "vehicle:conditional", "motor_vehicle:conditional", "motorcar:conditional", "oneway:conditional",
              "oneway:motorcar", "oneway:motor_vehicle", "surface", "maxheight", "maxweight"]


def tag(value) -> str | None:
    if value is None or (not isinstance(value, (list, dict)) and pd.isna(value)):
        return None
    return str(value).strip() or None


def posted_speed(value: str | None, model: dict) -> float | None:
    if not value:
        return None
    value = value.strip()
    if value in model["symbolic_maxspeed_kph"]:
        return float(model["symbolic_maxspeed_kph"][value])
    speeds = []
    for part in value.split(";"):
        match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(mph|km/h|kmh|kph)?", part.strip(), re.IGNORECASE)
        if not match:
            return None
        speed = float(match[1])
        if match[2] and match[2].lower() == "mph":
            speed *= model["mph_to_kph"]
        if speed <= 0 or speed > 300:
            return None
        speeds.append(speed)
    return min(speeds)


def normalize_network(nodes, edges, routing: dict) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Retain all components; never simplify, prune corridors, or merge parallel edges."""
    if routing["network_type"] != "driving" or routing["simplify"] or not routing["retain_all_components"]:
        raise ValueError("This pipeline requires unsimplified driving data with all components retained")
    audit = Counter(parsed_segments=len(edges))
    model, policy = routing["speed_model"], routing["access"]
    uncovered = set(edges.highway.dropna().unique()) - set(model["class_kph"]) - set(policy["excluded_highway"])
    if uncovered:
        raise ValueError(f"No documented speed fallback or exclusion policy for highway={sorted(uncovered)!r}")
    records = []
    # OSM tags are shared across a way's geometric segments. Materialize only
    # one policy record per way, then join/expand directions with column arrays.
    present_attributes = [key for key in ATTRIBUTES if key in edges.columns]
    ways = edges.drop_duplicates("id")[["id", *present_attributes]]
    for raw in ways.to_dict("records"):
        way_id = int(raw["id"])
        values = {key: tag(raw.get(key)) for key in ATTRIBUTES}
        access = next((values[k] for k in policy["hierarchy"] if values[k] is not None), None)
        reason = None
        if access and access not in policy["allowed"]:
            reason = "restricted_or_unknown_access"
        if policy["exclude_conditional_access"] and any(values[k] for k in ATTRIBUTES if k.endswith(":conditional") and k != "oneway:conditional"):
            reason = "conditional_access"
        if policy["exclude_conditional_oneway"] and values["oneway:conditional"]:
            reason = "conditional_oneway"
        highway = values["highway"]
        if highway in policy["excluded_highway"]:
            reason = "highway_class"
        elif highway not in model["class_kph"]:
            raise ValueError(f"No documented speed fallback for highway={highway!r}")
        oneway = values["oneway:motorcar"] or values["oneway:motor_vehicle"] or values["oneway"]
        if oneway is None:
            oneway = "yes" if values["junction"] == "roundabout" or highway == "motorway" else "no"
        if oneway in ("yes", "true", "1"):
            directions = [1]
        elif oneway in ("-1", "reverse"):
            directions = [-1]
        elif oneway in ("no", "false", "0"):
            directions = [1, -1]
        else:
            directions, reason = [], "unsupported_oneway"
        if reason:
            records.append({"osm_way_id": way_id, "excluded_reason": reason, "direction": 0})
            continue
        for direction in directions:
            reverse = direction == -1
            speed_tag = values["maxspeed:backward" if reverse else "maxspeed:forward"] or values["maxspeed"]
            maximum = posted_speed(speed_tag, model)
            estimate = float(model["class_kph"][values["highway"]])
            speed = estimate if maximum is None else min(estimate, maximum)
            speed = float(np.clip(speed, model["min_kph"], model["max_kph"]))
            audit["speed_class_fallback" if maximum is None else "speed_posted_cap"] += 1
            records.append({"osm_way_id": way_id, "excluded_reason": None, "direction": direction,
                            "speed_kph": speed,
                            "maxspeed_used": speed_tag, "posted_maxspeed_kph": maximum,
                            "speed_source": "road_class_fallback" if maximum is None else "posted_cap",
                            "oneway_effective": oneway, "access_effective": access,
                            **values})
    if not records:
        raise ValueError("No driving edges survive preprocessing")
    way_policy = pd.DataFrame.from_records(records)
    sizes = edges["id"].value_counts()
    for reason, group in way_policy.loc[way_policy.excluded_reason.notna()].groupby("excluded_reason"):
        audit[f"excluded_{reason}"] = int(sizes.reindex(group.osm_way_id).sum())
    valid_length = np.isfinite(edges["length"]) & (edges["length"] > 0)
    audit["excluded_zero_or_invalid_length"] = int((~valid_length).sum())
    segments = pd.DataFrame(edges.loc[valid_length, ["id", "u", "v", "length", "geometry"]]).rename(
        columns={"id": "osm_way_id", "length": "length_m"})
    edge_table = segments.merge(way_policy.loc[way_policy.excluded_reason.isna()].drop(columns="excluded_reason"),
                                on="osm_way_id", how="inner", sort=False)
    if edge_table.empty:
        raise ValueError("No driving edges survive preprocessing")
    del segments, way_policy, records
    reverse = edge_table.direction == -1
    edge_table["source_osm"] = np.where(reverse, edge_table.v, edge_table.u).astype(np.int64)
    edge_table["target_osm"] = np.where(reverse, edge_table.u, edge_table.v).astype(np.int64)
    geometries = edge_table.geometry.to_numpy().copy()
    geometries[reverse] = shapely.reverse(geometries[reverse])
    edge_table["geometry_wkb"] = shapely.to_wkb(geometries)
    edge_table = edge_table.drop(columns=["u", "v", "geometry"])
    edge_table["travel_time_s"] = edge_table.length_m * 3.6 / edge_table.speed_kph
    # Directional speed-source counts above were per way, so report edge counts.
    audit["speed_class_fallback"] = int(edge_table.speed_source.eq("road_class_fallback").sum())
    audit["speed_posted_cap"] = int(edge_table.speed_source.eq("posted_cap").sum())
    edge_table = edge_table.sort_values(
        ["osm_way_id", "source_osm", "target_osm", "direction"], kind="stable").reset_index(drop=True)
    used = np.unique(edge_table[["source_osm", "target_osm"]].to_numpy())
    node_table = nodes.loc[nodes["id"].isin(used), ["id", "lat", "lon"]].rename(columns={"id": "osm_node_id"})
    node_table = node_table.sort_values("osm_node_id", kind="stable").reset_index(drop=True)
    if not node_table.osm_node_id.is_unique or len(node_table) != len(used):
        raise ValueError("Missing or duplicate OSM node IDs")
    node_table.insert(0, "node_id", np.arange(len(node_table), dtype=np.int64))
    edge_table.insert(0, "edge_id", np.arange(len(edge_table), dtype=np.int64))
    edge_table.insert(1, "source", np.searchsorted(used, edge_table.source_osm.to_numpy()))
    edge_table.insert(2, "target", np.searchsorted(used, edge_table.target_osm.to_numpy()))
    audit["nodes"] = len(node_table)
    audit["directed_edges"] = len(edge_table)
    audit["unused_parser_nodes"] = len(nodes) - len(node_table)
    return node_table, edge_table, dict(audit)
