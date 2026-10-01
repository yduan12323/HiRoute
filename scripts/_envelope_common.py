"""Milestone 2 configuration/logging without writing Milestone 1 outputs."""
import copy
import json

import numpy as np

from _common import ROOT, configs, read_config, record_run, sha256


def envelope_config(path="configs/envelope.yaml"):
    config = read_config(path)
    ratios = np.asarray(config["detour_ratios"], dtype=float)
    maximum = config["max_ratio"]
    if not len(ratios) or not np.isfinite(ratios).all() or (ratios < 1).any() or (np.diff(ratios) <= 0).any():
        raise ValueError("Detour ratios must be finite, strictly increasing and >= 1")
    if not np.isfinite(maximum) or ratios[-1] > maximum:
        raise ValueError("Detour schedule exceeds the configured experimental cap")
    if config["cost"] not in ("travel_time", "distance"):
        raise ValueError("Unsupported envelope cost")
    if not isinstance(config["benchmark"]["mask_repeats"],int) or config["benchmark"]["mask_repeats"] < 1:
        raise ValueError("At least one mask-build measurement is required")
    return config


def envelope_run(command, envelope):
    data, routing = configs()
    log_data = copy.deepcopy(data)
    log_data["results_dir"] = envelope["results_dir"]
    # The M1 logging helper accepts arbitrary configuration contents.
    run = record_run(command, log_data, {"routing": routing, "envelope": envelope}, envelope["seed"])
    return data, routing, run


def fingerprints(data):
    directory = ROOT / data["graph_dir"]
    metadata = json.loads((directory / "metadata.json").read_text())
    return {"dataset_sha256": data["dataset"]["sha256"],
            "graph_nodes_sha256": metadata["files"]["nodes.parquet"]["sha256"],
            "graph_edges_sha256": metadata["files"]["edges.parquet"]["sha256"],
            "routing_config_sha256": sha256(ROOT / "configs/routing.yaml"),
            "od_instances_sha256": sha256(ROOT / data["instances_path"])}
