"""Verify a separately rebuilt graph has byte-identical node/edge Parquet."""
import argparse
import json

from _common import ROOT, configs, record_run, sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rebuild_dir")
    args = parser.parse_args()
    data, routing = configs()
    run = record_run("verify_rebuild", data, routing, data["seed"])
    original = ROOT / data["graph_dir"]
    rebuilt = ROOT / args.rebuild_dir
    comparisons = {}
    for name in ["nodes.parquet", "edges.parquet"]:
        before, after = sha256(original / name), sha256(rebuilt / name)
        comparisons[name] = {"original_sha256": before, "rebuilt_sha256": after, "identical": before == after}
    result = {"run": run, "comparisons": comparisons, "passed": all(row["identical"] for row in comparisons.values())}
    output = ROOT / data["results_dir"] / "deterministic_rebuild.json"
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(comparisons, indent=2))
    if not result["passed"]:
        raise RuntimeError("Processed graph rebuild is not byte identical")


if __name__ == "__main__":
    main()
