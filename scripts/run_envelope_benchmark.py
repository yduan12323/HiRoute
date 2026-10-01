"""Milestone 2: all 30 frozen ODs, reusable distances, containment and diagnostics."""
from __future__ import annotations

import argparse
import json
import resource
import time

import numpy as np
import pandas as pd

from _common import ROOT, load_graph, sha256, verified_dataset
from _envelope_common import envelope_config, envelope_run, fingerprints
from envelope import NumericalTolerance, build_envelope_from_precomputed, iter_progressive_envelopes, precompute_detour_distances
from envelope.boundary import boundary_node_risk, read_poly
from envelope.sampling import sample_waypoint_paths


def distribution(values):
    values = np.asarray(values, dtype=float)
    return {"median": float(np.median(values)), "p95": float(np.quantile(values,.95)), "mean": float(np.mean(values))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/envelope.yaml")
    args = parser.parse_args()
    config = envelope_config(args.config)
    data, routing, run = envelope_run("envelope_benchmark", config)
    verified_dataset(data)
    provenance = fingerprints(data)
    out = ROOT / config["results_dir"]
    out.mkdir(parents=True, exist_ok=True)
    boundary_file = ROOT / config["boundary"]["path"]
    if sha256(boundary_file) != config["boundary"]["sha256"]:
        raise ValueError("Frozen boundary fingerprint mismatch")
    boundary_metadata = json.loads(boundary_file.with_suffix(".metadata.json").read_text())
    load_start = time.perf_counter()
    graph = load_graph(data,routing)
    load_seconds = time.perf_counter()-load_start
    loaded_peak_rss_mib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
    instances_file = ROOT/data["instances_path"]
    instances = pd.read_parquet(instances_file)
    instance_metadata = json.loads(instances_file.with_suffix(".metadata.json").read_text())
    if sha256(instances_file) != instance_metadata["sha256"] or len(instances) != 30:
        raise ValueError("Expected unchanged, checksum-verified 30-instance Milestone 1 benchmark")
    if not instances.dataset_sha256.eq(provenance["dataset_sha256"]).all() or not instances.graph_edges_sha256.eq(provenance["graph_edges_sha256"]).all():
        raise ValueError("OD fingerprints do not match frozen graph")
    boundary_start = time.perf_counter()
    near_boundary,x,y = boundary_node_risk(graph.nodes.lat.to_numpy(),graph.nodes.lon.to_numpy(),
                                          read_poly(boundary_file),config["boundary"]["projection"],
                                          config["boundary"]["interior_margin_m"])
    boundary_seconds = time.perf_counter()-boundary_start
    tolerance = NumericalTolerance(**config["numerical_tolerance"])
    stats, benchmarks, checks, boundaries = [], [], [], []
    maximum_cached_bytes, maximum_mask_bytes = 0,0
    start_total = time.perf_counter()
    reproducibility = []
    for row in instances.itertuples():
        od_seed = config["seed"] + int(row.instance_id)
        distances = precompute_detour_distances(graph,int(row.origin_node),int(row.destination_node),config["cost"])
        expected = row.shortest_path_travel_time_s if config["cost"] == "travel_time" else row.shortest_path_distance_m
        if abs(distances.baseline_cost-expected) > tolerance.allowance(expected):
            raise RuntimeError("Baseline changed from Milestone 1")
        if abs(distances.reverse_distances[row.origin_node]-distances.baseline_cost) > tolerance.allowance(distances.baseline_cost):
            raise RuntimeError("Forward/reverse baseline costs disagree")
        sample_start = time.perf_counter()
        paths = sample_waypoint_paths(graph,distances,od_seed,config["sampling"]["waypoint_count"],config["sampling"]["waypoint_ratios"])
        sampling_seconds = time.perf_counter()-sample_start
        if row.instance_id in config["sampling"]["reproducibility_od_ids"]:
            repeated = sample_waypoint_paths(graph,distances,od_seed,config["sampling"]["waypoint_count"],config["sampling"]["waypoint_ratios"])
            stable = [p.fingerprint for p in paths] == [p.fingerprint for p in repeated]
            reproducibility.append({"instance_id":int(row.instance_id),"path_fingerprints_identical":stable})
            if not stable:
                raise RuntimeError("Seeded path sampling is not reproducible")
        maximum_cached_bytes = max(maximum_cached_bytes,distances.storage_bytes)
        benchmarks.append({"instance_id":row.instance_id,"cost":distances.cost,"unit":distances.unit,
            "baseline_cost":distances.baseline_cost,"forward_seconds":distances.forward_seconds,
            "reverse_seconds":distances.reverse_seconds,"lower_bound_seconds":distances.lower_bound_seconds,
            "sampling_seconds":sampling_seconds,"precomputed_bytes":distances.storage_bytes,
            "process_peak_rss_mib":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,**provenance})
        previous = None
        repeat = None
        ratios = config["detour_ratios"]
        iterator = iter_progressive_envelopes(distances,[ratio*distances.baseline_cost for ratio in ratios],tolerance)
        for ratio in ratios:
            timing_start = time.perf_counter()
            envelope = next(iterator)
            timings = [time.perf_counter()-timing_start]
            for _ in range(config["benchmark"]["mask_repeats"]-1):
                timing_start = time.perf_counter()
                repeat = build_envelope_from_precomputed(distances,envelope.budget,tolerance)
                timings.append(time.perf_counter()-timing_start)
                if not np.array_equal(repeat.node_mask,envelope.node_mask) or not np.array_equal(repeat.edge_mask,envelope.edge_mask):
                    raise RuntimeError("Envelope masks are not deterministic")
            if previous is not None and ((previous.node_mask & ~envelope.node_mask).any() or (previous.edge_mask & ~envelope.edge_mask).any()):
                raise RuntimeError("Envelope nesting violation")
            if (envelope.edge_mask & ~(envelope.node_mask[graph.source] & envelope.node_mask[graph.target])).any():
                raise RuntimeError("Retained edge endpoint outside node envelope")
            if not envelope.node_mask[paths[0].nodes].all() or not envelope.edge_mask[paths[0].edges].all():
                raise RuntimeError("Baseline path omitted")
            for path in paths:
                within = path.base_cost <= envelope.budget
                within_tolerance = path.base_cost <= envelope.budget+tolerance.allowance(envelope.budget)
                nodes_ok = bool(envelope.node_mask[path.nodes].all())
                edges_ok = bool(envelope.edge_mask[path.edges].all())
                violated = within_tolerance and not (nodes_ok and edges_ok)
                checks.append({"instance_id":row.instance_id,"ratio":ratio,"cost":distances.cost,"unit":distances.unit,
                    "sample_id":path.sample_id,"method":path.method,"waypoint":path.waypoint,"seed":od_seed,
                    "path_cost":path.base_cost,"budget":envelope.budget,"path_cost_ratio":path.base_cost/distances.baseline_cost,
                    "within_budget":within,"within_numerical_tolerance":within_tolerance,
                    "nodes_contained":nodes_ok,"edges_contained":edges_ok,"violation":violated,
                    "path_node_count":len(path.nodes),"path_edge_count":len(path.edges),"path_sha256":path.fingerprint,**provenance})
                if violated:
                    raise RuntimeError(f"Critical containment violation OD={row.instance_id}, ratio={ratio}, sample={path.sample_id}")
            nodes = int(envelope.node_mask.sum())
            edges = int(envelope.edge_mask.sum())
            near = int(np.count_nonzero(envelope.node_mask & near_boundary))
            max_x,min_x = x[envelope.node_mask].max(),x[envelope.node_mask].min()
            max_y,min_y = y[envelope.node_mask].max(),y[envelope.node_mask].min()
            maximum_mask_bytes = max(maximum_mask_bytes,envelope.mask_bytes)
            stats.append({"instance_id":row.instance_id,"origin_city":row.origin_city,"destination_city":row.destination_city,
                "ratio":ratio,"cost":distances.cost,"unit":distances.unit,"baseline_cost":distances.baseline_cost,
                "budget":envelope.budget,"tolerance_allowance":tolerance.allowance(envelope.budget),
                "nodes":nodes,"node_percent":100*nodes/graph.node_count,"edges":edges,"edge_percent":100*edges/graph.edge_count,
                "build_ms":float(np.median(timings)*1000),"build_p95_ms":float(np.quantile(timings,.95)*1000),
                "mask_bytes":envelope.mask_bytes,"precomputed_bytes":distances.storage_bytes,
                "bbox_area_km2":float((max_x-min_x)*(max_y-min_y)/1e6),"boundary_risk":near>0,**provenance})
            boundaries.append({"instance_id":row.instance_id,"ratio":ratio,"boundary_risk":near>0,
                "near_or_outside_boundary_nodes":near,"node_count":nodes,
                "interior_margin_m":config["boundary"]["interior_margin_m"],"boundary_sha256":config["boundary"]["sha256"],
                "diagnostic":"Any envelope vertex outside the inward-buffered polygon; approximate proxy only.",**provenance})
            previous = envelope
        print(f"OD {row.instance_id:02d}: forward {distances.forward_seconds:.3f}s, reverse {distances.reverse_seconds:.3f}s; max envelope {nodes:,} nodes ({100*nodes/graph.node_count:.1f}%), boundary_risk={near>0}",flush=True)
        # Do not accumulate distance arrays or masks for all ODs.
        del distances, previous, envelope, repeat, iterator
    frames = {"envelope_stats":pd.DataFrame(stats),"distance_benchmark":pd.DataFrame(benchmarks),
              "path_containment_tests":pd.DataFrame(checks),"boundary_diagnostics":pd.DataFrame(boundaries)}
    for name,frame in frames.items():
        frame.to_parquet(out/f"{name}.parquet",index=False,compression="zstd")
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
    table = frames["envelope_stats"]
    largest = table.loc[table.ratio.eq(ratios[-1])]
    clean_ids = largest.loc[~largest.boundary_risk,"instance_id"].tolist()
    pd.DataFrame({"instance_id":clean_ids},dtype="int64").to_parquet(out/"boundary_safe_subset.parquet",index=False)
    growth = table.groupby("ratio").agg(node_percent_median=("node_percent","median"),node_percent_min=("node_percent","min"),
        node_percent_max=("node_percent","max"),edge_percent_median=("edge_percent","median"),boundary_risk_cases=("boundary_risk","sum")).reset_index()
    growth.to_parquet(out/"envelope_growth.parquet",index=False)
    path_table = frames["path_containment_tests"]
    max_checks = path_table.loc[path_table.ratio.eq(ratios[-1])]
    missing_over = [int(od) for od,group in max_checks.groupby("instance_id") if not ((~group.within_numerical_tolerance) & ~(group.nodes_contained & group.edges_contained)).any()]
    if missing_over:
        raise RuntimeError(f"No excluded over-cap witness for ODs {missing_over}; increase configured samples")
    result = {"run":run,"provenance":provenance,"cost":config["cost"],"unit":table.unit.iloc[0],
        "node_count":graph.node_count,"edge_count":graph.edge_count,"od_count":len(instances),"ratios":ratios,
        "forward_seconds":distribution(frames["distance_benchmark"].forward_seconds),
        "reverse_seconds":distribution(frames["distance_benchmark"].reverse_seconds),
        "lower_bound_seconds":distribution(frames["distance_benchmark"].lower_bound_seconds),
        "envelope_build_ms":distribution(table.build_ms),"verified_graph_load_seconds":load_seconds,
        "boundary_preparation_seconds":boundary_seconds,"loaded_graph_peak_rss_mib":loaded_peak_rss_mib,
        "peak_rss_mib":peak,"maximum_precomputed_bytes":maximum_cached_bytes,"maximum_mask_bytes":maximum_mask_bytes,
        "envelope_count":len(table),"containment_check_count":len(path_table),
        "strict_within_budget_checks":int(path_table.within_budget.sum()),
        "tolerated_within_budget_checks":int(path_table.within_numerical_tolerance.sum()),
        "containment_violations":int(path_table.violation.sum()),
        "over_budget_checks":int((~path_table.within_numerical_tolerance).sum()),
        "over_budget_not_contained":int(((~path_table.within_numerical_tolerance) & ~(path_table.nodes_contained & path_table.edges_contained)).sum()),
        "over_budget_still_contained":int(((~path_table.within_numerical_tolerance) & path_table.nodes_contained & path_table.edges_contained).sum()),
        "boundary_safe_subset_ids":clean_ids,"boundary_safe_subset_rule":f"No envelope vertex within {config['boundary']['interior_margin_m']}m of or outside the frozen polygon at the largest scheduled ratio; proxy only.",
        "excessive_envelope_node_fraction_threshold":config["diagnostics"]["excessive_node_fraction"],
        "excessive_envelope_od_ids":largest.loc[largest.node_percent.ge(100*config["diagnostics"]["excessive_node_fraction"]),"instance_id"].tolist(),
        "boundary_risk_od_ids_at_max_ratio":largest.loc[largest.boundary_risk,"instance_id"].tolist(),
        "growth":growth.to_dict("records"),"path_sampling_reproducibility":reproducibility,
        "boundary_metadata":boundary_metadata,"experiment_seconds":time.perf_counter()-start_total,
        "files":{f"{name}.parquet":sha256(out/f"{name}.parquet") for name in frames}}
    (out/"benchmark.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({key:result[key] for key in ["forward_seconds","reverse_seconds","envelope_build_ms","peak_rss_mib","containment_violations","boundary_safe_subset_ids"]},indent=2))


if __name__ == "__main__":
    main()
