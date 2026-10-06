"""Run REF on a frozen fixture; optionally keep full rational certificates."""
import argparse
import hashlib
import json
from pathlib import Path

from .solver import jsonable, solve_case


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixtures", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--certificates", action="store_true", help="Include all rational primal/dual certificates")
    parser.add_argument("--allow-nonnegative-extension", action="store_true",
                        help="Explicit exploratory domain beyond positive production hypotheses")
    args = parser.parse_args()
    data = args.fixtures.read_bytes()
    cases = json.loads(data)
    if isinstance(cases, dict):
        cases = [cases]
    results = []
    for case in cases:
        result = solve_case(case, keep_evidence=args.certificates,
                            allow_nonnegative_extension=args.allow_nonnegative_extension)
        results.append(result)
        print(case.get("case_id", "unnamed"), result["result"]["status"],
              json.dumps(jsonable({key: value for key, value in result["result"].items()
                                   if key in ("J", "Q_total", "H", "primary_infimum", "secondary_infimum")})), flush=True)
    report = dict(fixture_sha256=hashlib.sha256(data).hexdigest(),
                  fixture_path=str(args.fixtures), oracle="independent_reference5", results=results)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        # Historical or fresh-run results are never silently overwritten.
        with args.output.open("x") as handle:
            json.dump(jsonable(report), handle, indent=2)
            handle.write("\n")
    if any(r["result"]["status"] in ("invalid_input", "unresolved") for r in results):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
