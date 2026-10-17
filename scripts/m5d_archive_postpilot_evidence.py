"""Archive new and comparator Pilot receipts without changing their originals."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tarfile


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main(root: Path, archive: Path):
    if archive.exists() or (root / "postpilot_evidence_manifest.json").exists():
        raise ValueError("Post-Pilot evidence archive already exists")
    prefixes = ("postpilot_seed_validation_OD02_", "postpilot_payload_audit_OD02_",
                "postpilot_benchmark_v2_OD02_", "postpilot_benchmark_OD02_",
                "pilot_exact_v2_OD02_")
    directories = sorted(path for path in root.iterdir() if path.is_dir() and
                         path.name.startswith(prefixes))
    if sum(path.name.startswith("postpilot_seed_validation_OD02_") for path in directories) != 6 or \
       sum(path.name.startswith("postpilot_payload_audit_OD02_") for path in directories) != 6 or \
       sum(path.name.startswith("postpilot_benchmark_v2_OD02_") for path in directories) != 12:
        raise ValueError("Frozen validation, audit or benchmark directory coverage is incomplete")
    files = [path for directory in directories for path in directory.rglob("*") if path.is_file()]
    fixed = (
        "postpilot_frozen_comparison_summary_v2.json",
        "postpilot_frozen_comparison_summary.json",
        "postpilot_wrong_runner_abort.json",
        "pilot_six_input_manifest.json",
        "preflight_20261011_alt_gate/landmark_certificate.json",
        "formal_pools_20261011_v2/pools.json",
        "results/milestone_5d/continuation_20261011/fixed_12od_candidate_slate.json",
        "results/milestone_5d/continuation_20261011/fixed_pilot_summary_20261011.json",
        "src/timecut5/deployable.py", "src/timecut5/real_adapter.py",
        "src/timecut5/road_provider.py",
        "scripts/m5d_pilot_exact_row_v2.py", "scripts/m5d_pilot_exact_row.py",
        "scripts/m5d_seed_revalidate.py", "scripts/m5d_seed_revalidate_batch.py",
        "scripts/m5d_payload_provenance_audit.py", "scripts/m5d_payload_provenance_batch.py",
        "scripts/m5d_postpilot_benchmark_batch.py", "scripts/m5d_postpilot_summarize.py",
    )
    files.extend(root / relative for relative in fixed)
    if any(not path.is_file() or path.is_symlink() for path in files):
        raise ValueError("Post-Pilot evidence includes a missing or linked file")
    rows = [{"path": str(path.relative_to(root)), "size": path.stat().st_size,
             "sha256": digest(path)} for path in sorted(set(files))]
    manifest = {"schema": "hiroute.m5d.postpilot_evidence_archive.v1",
                "comparison_summary_sha256": digest(root / fixed[0]),
                "files": rows}
    manifest_path = root / "postpilot_evidence_manifest.json"
    with manifest_path.open("x") as stream:
        json.dump(manifest, stream, sort_keys=True, indent=2)
        stream.write("\n")
    with tarfile.open(archive, "x:gz") as stream:
        for path in sorted(set(files)):
            stream.add(path, arcname=str(path.relative_to(root)), recursive=False)
        stream.add(manifest_path, arcname=manifest_path.name, recursive=False)
    print(json.dumps({"archive": str(archive), "sha256": digest(archive),
                      "manifest_sha256": digest(manifest_path), "file_count": len(rows)}))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
