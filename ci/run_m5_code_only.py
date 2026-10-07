"""Fast synthetic regression gate; no real-population or M5 acceptance claim."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]

# Explicit selection: never silently substitute the legacy full-suite result.
TESTS = (
    "tests/test_time_cut_v2.py",
    "tests/test_time_cut_pwa_v2.py",
    "tests/test_time_cut_bounded_v2.py",
    "tests/test_time_cut_hierarchy_v2.py",
    "tests/test_time_cut_optimized_replay.py",
    "tests/test_time_cut_coalescing.py",
    "tests/test_coalesced_solver.py",
    "tests/test_real_leg_contract.py",
    "tests/test_real_solver_adapter.py",
    "tests/test_real_export_input.py",
    "tests/test_reference5_real_adapter.py",
    "tests/test_family_checker_v1.py",
    "tests/test_family_optimized_validation_v2.py",
    "tests/test_family_provenance_v1.py",
    "tests/test_family_receipt_stream_v1.py",
    "tests/test_invocation_trace_v1.py",
    "tests/test_restricted_suffix_v1.py",
    "tests/test_restricted_suffix_v2.py",
    "tests/test_trace_coalescing_integration.py",
    "tests/test_capture5_reader.py",
    "tests/test_capture5_containers.py",
    "tests/test_recorded_coalescing_recovery.py",
    "tests/test_recovered_coalesced_trace.py",
    "tests/test_recovered_real_family.py",
    "tests/test_recovered_real_coalesced.py",
    "tests/test_recovered_shared_replay.py",
    "validation/family5/test_checker_units.py",
    "validation/trace5/test_checker_units.py",
    "validation/suffix5/test_certificate_checker.py",
    "validation/suffix5/test_witness_checker.py",
    "validation/suffix5/test_convex_checker.py",
)

# Only hand-built synthetic cases and mock legs are staged. No result directory
# is copied recursively; missing fixtures fail instead of falling back to data.
FIXTURES = (
    "tests/fixtures/invocation_trace_pilot_v1.json",
    "tests/fixtures/invocation_trace_A06_regression.json",
    "results/milestone_4r_b2_b21/hand_cases.json",
    "results/milestone_4r_b2_b21/case_construction_manifest.json",
    "results/milestone_5_reference/frozen_cases_v2.json",
    "results/milestone_5_reference/audit_regression_cases.json",
    "results/milestone_5_real_leg_contract/mock_solver_cases.json",
    "results/milestone_5_real_leg_contract/mock_solver_freeze.json",
    "experiments/time_cut_v2/solver_audit/targeted_attainment_cases_v1.json",
)


def copy_file(relative: str | Path, target: Path) -> None:
    source = ROOT / relative
    if source.is_symlink() or not source.is_file():
        raise RuntimeError(f"Missing or symlinked CI input: {relative}")
    destination = target / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def run(arguments: list[str], cwd: Path, env: dict[str, str]) -> None:
    print("+", " ".join(arguments), flush=True)
    subprocess.run(arguments, cwd=cwd, env=env, check=True, timeout=300)


def main() -> None:
    if sys.version_info[:2] != (3, 11) or sys.prefix == sys.base_prefix:
        raise RuntimeError("Use a fresh Python 3.11 virtual environment")
    env = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1",
               MKL_NUM_THREADS="1", PYTHONDONTWRITEBYTECODE="1",
               PYTHONNOUSERSITE="1", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
               PIP_DISABLE_PIP_VERSION_CHECK="1", PIP_NO_CACHE_DIR="1")
    for key in ("PYTHONPATH", "PYTHONHOME", "PYTEST_ADDOPTS", "PYTHONOPTIMIZE"):
        env.pop(key, None)
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="hiroute-m5-ci-") as temporary:
        work = Path(temporary)
        build_source, tooling = work / "build-source", work / "tooling"
        for source in (ROOT / "src").rglob("*"):
            if source.is_file() and source.suffix in (".py", ".cpp"):
                copy_file(source.relative_to(ROOT), build_source)
        copy_file("pyproject.toml", build_source)
        run([sys.executable, "-m", "build", "--wheel", "--no-isolation",
             "--outdir", str(work / "wheels"), str(build_source)], work, env)
        wheels = list((work / "wheels").glob("*.whl"))
        if len(wheels) != 1:
            raise RuntimeError("Expected exactly one freshly built wheel")
        with zipfile.ZipFile(wheels[0]) as archive:
            names = set(archive.namelist())
            required = {"timecut5/provenance.py", "timecut5/invocation_trace.py",
                        "timecut5/coalesce.py", "timecut5/real_adapter.py"}
            if not required <= names or any(name.startswith(("validation/", "tests/", "experiments/")) for name in names):
                raise RuntimeError("Unexpected production wheel contents")
        run([sys.executable, "-m", "pip", "--isolated", "--disable-pip-version-check",
             "install", "--no-index", "--no-deps", "--no-cache-dir",
             "--force-reinstall", str(wheels[0])], work, env)
        # Source-only validators are a separate repository tool, not a wheel package.
        for directory in ("validation", "experiments/time_cut_v2/family_faithfulness",
                          "experiments/time_cut_v2/invocation_trace",
                          "experiments/time_cut_v2/restricted_suffix"):
            for source in (ROOT / directory).rglob("*.py"):
                copy_file(source.relative_to(ROOT), tooling)
        for relative in (*TESTS, *FIXTURES, "tests/conftest.py"):
            copy_file(relative, tooling)
        (tooling / "pytest.ini").write_text("[pytest]\naddopts = -ra\n")
        env["PYTHONPATH"] = str(tooling)
        origin_check = """
from pathlib import Path
import sys
import timecut5.probe, timecut5.bounded, timecut5.hierarchy
import timecut5.coalesced_solver, timecut5.real_adapter
import timecut5.provenance, timecut5.invocation_trace
import validation.family5, validation.trace5, validation.suffix5.checker
for name, module in tuple(sys.modules.items()):
    if name == 'timecut5' or name.startswith('timecut5.'):
        origin = Path(module.__file__).resolve()
        if not origin.is_relative_to(Path(sys.prefix).resolve()):
            raise RuntimeError(f'Production import escaped installed wheel: {name}: {origin}')
if Path('src').exists():
    raise RuntimeError('Source tree leaked into isolated test directory')
print('Production imports verified inside installed-wheel environment')
"""
        run([sys.executable, "-c", origin_check], tooling, env)
        for flags, label in (([], "normal"), (["-OO"], "optimized")):
            report = work / f"{label}.xml"
            run([sys.executable, *flags, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                 "-c", str(tooling / "pytest.ini"), f"--junitxml={report}", *TESTS], tooling, env)
            suites = list(ET.parse(report).getroot().iter("testsuite"))
            if not suites or sum(int(suite.get("tests", "0")) for suite in suites) == 0:
                raise RuntimeError(f"{label}: no tests were recorded")
            if any(int(suite.get(key, "0")) for suite in suites for key in ("skipped", "errors", "failures")):
                raise RuntimeError(f"{label}: skipped or unsuccessful tests are not accepted")
    print(f"M5 code-only gate passed in {time.monotonic() - started:.1f}s; milestone acceptance remains separate.")


if __name__ == "__main__":
    main()
