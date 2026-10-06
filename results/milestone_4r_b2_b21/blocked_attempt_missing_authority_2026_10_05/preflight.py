"""Read-only predecessor audit; never runs B21 solvers or changes frozen inputs."""
import hashlib
import json
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True)


def main():
    if (OUT / "preservation_before.json").exists():
        raise FileExistsError("Preflight evidence already exists; do not overwrite")
    started = time.perf_counter()
    initial_git = dict(git_commit=git("rev-parse", "HEAD").strip(),
                       git_status=git("status", "--short"),
                       tracked_diff=git("diff", "HEAD", "--name-only"))
    references = []
    manifests = []
    for directory in ["milestone_4r", "milestone_4r_b1", "milestone_4r_b1d",
                      "milestone_4r_b1e", "milestone_4r_b1d2", "milestone_4b"]:
        base = ROOT / "results" / directory
        for name in ["preservation_before.json", "preservation_checkpoint.json",
                     "resume_preservation_before.json", "acceptance.json",
                     "frozen_input_hash_manifest.json", "query_preregistration.json",
                     "boundary_manifest.json", "landmark_manifest.json",
                     "experiment_protocol.json"]:
            path = base / name
            if not path.is_file():
                continue
            data = json.loads(path.read_text())
            manifests.append(str(path.relative_to(ROOT)))
            groups = [("files", data)] if name == "frozen_input_hash_manifest.json" else [
                (key, data.get(key, {})) for key in ["files", "source_sha256", "archive_sha256",
                "archived_hashes", "artifact_sha256", "final_source_sha256",
                "extraction_code_sha256", "graph_sha256"]]
            for group_name, group in groups:
                for filename, record in group.items():
                    expected = record.get("sha256") if isinstance(record, dict) else record
                    if not isinstance(expected, str) or len(expected) != 64:
                        continue
                    target = ROOT / filename
                    if group_name == "graph_sha256" and name == "boundary_manifest.json":
                        # The frozen boundary builder declares these names relative
                        # to the accepted extended graph directory, not the repo root.
                        target = ROOT / "data/processed/graphs/slovenia_extended" / filename
                    if not target.is_file() and (base / filename).is_file():
                        target = base / filename
                    references.append(dict(manifest=str(path.relative_to(ROOT)),
                        path=str(target.relative_to(ROOT)), expected_sha256=expected))
            report = ROOT / "docs" / (directory.upper() + "_REPORT.md")
            if data.get("report_sha256") and report.is_file():
                references.append(dict(manifest=str(path.relative_to(ROOT)),
                    path=str(report.relative_to(ROOT)), expected_sha256=data["report_sha256"]))
    paths = {r["path"] for r in references} | set(manifests)
    paths.update(git("ls-files").splitlines())
    for base in [ROOT / "src", ROOT / "scripts", ROOT / "tests", ROOT / "docs"]:
        paths.update(str(p.relative_to(ROOT)) for p in base.rglob("*")
                     if p.is_file() and "__pycache__" not in p.parts)
    for directory in ["milestone_4r_b1", "milestone_4r_b1d", "milestone_4r_b1e", "milestone_4r_b1d2"]:
        paths.update(str(p.relative_to(ROOT)) for p in (ROOT / "results" / directory).rglob("*")
                     if p.is_file() and "__pycache__" not in p.parts)
    paths.update(str(p.relative_to(ROOT)) for p in ROOT.glob("MILESTONE_*.md"))
    hashes = {}
    for i, name in enumerate(sorted(paths)):
        path = ROOT / name
        hashes[name] = digest(path) if path.is_file() else None
        if i % 2000 == 0:
            print(f"Hashed {i}/{len(paths)} frozen/current files", flush=True)
    violations = [r | dict(actual_sha256=hashes[r["path"]]) for r in references
                  if hashes[r["path"]] != r["expected_sha256"]]
    missing = [name for name in ["MILESTONE_4R_B2_FORMAL_SPEC.md",
                "MILESTONE_4R_B2_THEORY_AUDIT.md"] if not (ROOT / name).is_file()]
    write("frozen_input_hash_manifest.json", hashes)
    protocol = ROOT / "MILESTONE_4R_B2_B21_EXPERIMENT_PROTOCOL.md"
    (OUT / "protocol_snapshot.md").write_bytes(protocol.read_bytes())
    write("protocol_snapshot_hash.json", dict(source=str(protocol.relative_to(ROOT)),
        sha256=digest(protocol), semantics_read=False,
        reason="Required prior authority documents missing; ordered read stopped"))
    before = dict(**initial_git, files_verified=len(hashes),
        expected_hash_records_verified=len(references), manifests=manifests,
        hash_violations=violations, missing_authority_documents=missing,
        preservation_passed=not violations and not initial_git["tracked_diff"].strip(),
        frozen_input_hash_manifest_sha256=digest(OUT / "frozen_input_hash_manifest.json"),
        hash_audit_seconds=time.perf_counter() - started)
    write("preservation_before.json", before)
    print(f"Preservation: {len(violations)} hash violations; missing authority: {missing}", flush=True)
    command = [sys.executable, "-m", "pytest", "-vv", "--junitxml=" + str(OUT / "preexisting_tests.xml")]
    test_started = time.perf_counter()
    with (OUT / "preexisting_tests.log").open("w") as log:
        code = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT).returncode
    suites = list(ET.parse(OUT / "preexisting_tests.xml").getroot().iter("testsuite"))
    tests = {key: sum(int(s.attrib.get(key, 0)) for s in suites)
             for key in ["tests", "failures", "errors", "skipped"]}
    write("pretest_summary.json", dict(command=command, exit_code=code,
          seconds=time.perf_counter() - test_started, **tests))
    changed = [name for name, value in hashes.items()
               if not (ROOT / name).is_file() or digest(ROOT / name) != value]
    write("preservation_after.json", dict(git_commit=git("rev-parse", "HEAD").strip(),
        git_status=git("status", "--short"), tracked_diff=git("diff", "HEAD", "--name-only"),
        files_verified=len(hashes), changed_files=changed,
        predecessor_hash_violations=violations,
        preservation_passed=not changed and before["preservation_passed"],
        implementation_started=False, full_pretests=tests))
    print(json.dumps(dict(test_exit_code=code, **tests, changed_files=changed)), flush=True)


if __name__ == "__main__":
    main()
