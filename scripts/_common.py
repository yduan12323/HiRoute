"""Shared command configuration, checksums and reproducibility records."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_config(path: str) -> dict:
    with (ROOT / path).open() as stream:
        return yaml.safe_load(stream)


def configs(data_path="configs/data.yaml", routing_path="configs/routing.yaml") -> tuple[dict, dict]:
    return read_config(data_path), read_config(routing_path)


def verified_dataset(data: dict) -> dict:
    dataset = data["dataset"]
    manifest = read_config(dataset["manifest_path"])
    digest = sha256(ROOT / dataset["raw_path"])
    if digest != manifest["dataset"]["sha256"] or digest != dataset["sha256"]:
        raise ValueError("Raw PBF checksum differs from frozen configuration/manifest")
    if manifest["dataset"]["source_url"] != dataset["source_url"]:
        raise ValueError("Dataset URL differs from manifest")
    return manifest["dataset"]


def record_run(command: str, data: dict, routing: dict | None, seed: int) -> dict:
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True))
    except subprocess.CalledProcessError:
        commit, dirty = None, None
    packages = {d.metadata["Name"]: d.version for d in importlib.metadata.distributions()}
    dataset = data["dataset"]
    run = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(), "command": command,
        "argv": sys.argv, "git_commit": commit, "git_dirty": dirty,
        "configuration": {"data": data, "routing": routing}, "seed": seed,
        "dataset_sha256": dataset.get("sha256"),
        "python": sys.version, "platform": platform.platform(), "packages": dict(sorted(packages.items())),
        "research_spec_sha256": sha256(ROOT / "RESEARCH_SPEC.md"),
        "source_sha256": {str(path.relative_to(ROOT)): sha256(path)
                          for base in [ROOT / "src", ROOT / "scripts", ROOT / "tests"]
                          for path in sorted(base.rglob("*.py"))},
    }
    manifest_path = ROOT / dataset["manifest_path"]
    if manifest_path.exists():
        run["dataset_metadata"] = yaml.safe_load(manifest_path.read_text())["dataset"]
    log_dir = ROOT / data["results_dir"] / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    log_path = log_dir / f"{command}-{stamp}.json"
    log_path.write_text(json.dumps(run, indent=2) + "\n")
    print(json.dumps({"command": command, "log": str(log_path.relative_to(ROOT)), "seed": seed,
                      "dataset_sha256": run["dataset_sha256"], "git_commit": commit}), flush=True)
    return run


def load_graph(data: dict, routing: dict):
    from graph.road_graph import IgraphRoadGraph
    directory = ROOT / data["graph_dir"]
    metadata = json.loads((directory / "metadata.json").read_text())
    if metadata["dataset"]["sha256"] != data["dataset"]["sha256"]:
        raise ValueError("Processed graph belongs to a different PBF")
    if metadata["run"]["configuration"]["routing"] != routing:
        raise ValueError("Routing configuration changed; rebuild graph first")
    for name, info in metadata["files"].items():
        if sha256(directory / name) != info["sha256"]:
            raise ValueError(f"Processed graph checksum mismatch: {name}")
    return IgraphRoadGraph.load(directory)
