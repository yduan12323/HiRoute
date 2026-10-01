"""Capture or verify hashes without rebuilding or changing Milestone 1 data."""
import argparse
from datetime import datetime, timezone
import json
import subprocess

from _common import ROOT, sha256, verified_dataset
from _envelope_common import envelope_config, envelope_run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture",action="store_true")
    parser.add_argument("--checkpoint",default="results/milestone_2/preservation_before.json")
    args = parser.parse_args()
    config = envelope_config()
    data,_,run = envelope_run("milestone_1_preservation",config)
    dataset = verified_dataset(data)
    checkpoint = ROOT/args.checkpoint
    if args.capture:
        directory = ROOT/data["graph_dir"]
        metadata = json.loads((directory/"metadata.json").read_text())
        for name,info in metadata["files"].items():
            if sha256(directory/name) != info["sha256"]:
                raise ValueError(f"Processed graph fingerprint mismatch: {name}")
        paths = [ROOT/"RESEARCH_SPEC.md",ROOT/"docs/MILESTONE_1_REPORT.md",ROOT/"configs/routing.yaml",
                 ROOT/"configs/data.yaml",ROOT/data["instances_path"],ROOT/data["dataset"]["manifest_path"],
                 *directory.glob("*"),*(ROOT/"src/graph").glob("*.py"),*(ROOT/"results/milestone_1").rglob("*")]
        snapshot = {"timestamp_utc":datetime.now(timezone.utc).isoformat(),"dataset":dataset,
            "git_commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
            "git_status":subprocess.check_output(["git","status","--porcelain"],cwd=ROOT,text=True),
            "preserved_files":{str(path.relative_to(ROOT)):sha256(path) for path in paths if path.is_file()},
            "graph_files":metadata["files"]}
        checkpoint.parent.mkdir(parents=True,exist_ok=True)
        with checkpoint.open("x") as stream:
            json.dump(snapshot,stream,indent=2)
        print(f"Captured {len(snapshot['preserved_files'])} Milestone 1 fingerprints")
        return
    snapshot = json.loads(checkpoint.read_text())
    changed = [name for name,digest in snapshot["preserved_files"].items()
               if not (ROOT/name).exists() or sha256(ROOT/name) != digest]
    if snapshot["dataset"]["sha256"] != dataset["sha256"]:
        changed.append(data["dataset"]["raw_path"])
    result = {"run":run,"checkpoint":args.checkpoint,"passed":not changed,
              "changed_files":changed,"verified_file_count":len(snapshot["preserved_files"]),
              "raw_dataset_sha256":dataset["sha256"]}
    (ROOT/config["results_dir"]/"preservation_after.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({key:value for key,value in result.items() if key!="run"},indent=2))
    if changed:
        raise RuntimeError("Milestone 1 preservation check failed")


if __name__ == "__main__":
    main()
