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
    "tests/test_raw_way_policy_logic.py",
    "tests/test_node_domain_batch.py",
    "tests/test_m5d_aggregate_screen.py",
    "tests/test_regional_source_pins.py",
    "tests/test_code_only_collection.py",
    "tests/test_time_cut_v2.py",
    "tests/test_time_cut_pwa_v2.py",
    "tests/test_frontier_skyline.py",
    "tests/test_projection_support_prefilter.py",
    "tests/test_envelope_sweep.py",
    "tests/test_analytic_charge.py",
    "tests/test_post_service_dominance.py",
    "tests/test_pending_window_dominance.py",
    "tests/test_charge_count_bound.py",
    "tests/test_remaining_charge_bound.py",
    "tests/test_time_cut_bounded_v2.py",
    "tests/test_time_cut_hierarchy_v2.py",
    "tests/test_time_cut_optimized_replay.py",
    "tests/test_time_cut_coalescing.py",
    "tests/test_coalesced_solver.py",
    "tests/test_real_leg_contract.py",
    "tests/test_real_solver_adapter.py",
    "tests/test_real_export_input.py",
    "tests/test_m5d_charge_gate.py",
    "tests/test_m5d_deployable_contract.py",
    "tests/test_m5d_road_provider.py",
    "tests/test_road_provider_telemetry.py",
    "tests/test_m5d_main_batch.py",
    "tests/test_m5d_parallel_continuation.py",
    "tests/test_m5d_supplement.py",
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
HIROUTE_TESTS = (
    "tests/r0/test_contracts.py",
    "tests/r0/test_cli_supported_matrix.py",
    "tests/r0/test_shandong_input_contract.py",
    "tests/test_r3_runtime.py",
    "tests/test_r3_os_supervisor.py",
    "tests/test_exact_search.py",
    "tests/test_semantic_fixes.py",
    "tests/test_prefix_reuse.py",
    "tests/test_flat_bb.py",
    "tests/test_scale_bounds.py",
    "tests/test_scale_road_index.py",
    "tests/test_scale_search.py",
    "tests/test_real_scale_inputs.py",
    "tests/test_scale_pilot_control.py",
    "tests/test_c_operator.py",
    "tests/test_exact_pipeline.py",
    "tests/test_exact_terminal.py",
    "tests/test_data_producer.py",
    "tests/r0/test_ref_supported_matrix.py",
)

HIROUTE_FIXTURES = (
    "tests/r0/c01_zero_stop_snapshot.json",
    "tests/r0/fixtures/c18_c20_c24_expected.json",
    "configs/rebuild/r1_flat.json",
    "tests/fixtures/synthetic_c07_c13_c04_c14_v1.json",
)

FIXTURES = (
    "tests/fixtures/invocation_trace_pilot_v1.json",
    "tests/fixtures/invocation_trace_A06_regression.json",
    "tests/fixtures/milestone_4r_b2_b21/hand_cases.json",
    "tests/fixtures/milestone_4r_b2_b21/case_construction_manifest.json",
    "tests/fixtures/milestone_5_reference/frozen_cases_v2.json",
    "tests/terminal_energy/__init__.py",
    "tests/terminal_energy/test_energy.py",
    "tests/terminal_energy/test_combined_target_energy.py",
    "tests/terminal_energy/test_remaining_charge_runtime.py",
    "tests/terminal_energy/floating_flags.cpp",
    "tests/fixtures/milestone_5_reference/audit_regression_cases.json",
    "tests/fixtures/milestone_5_real_leg_contract/mock_solver_cases.json",
    "tests/fixtures/milestone_5_real_leg_contract/mock_solver_freeze.json",
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
            required = {"hiroute/cli.py", "hiroute/contracts.py", "hiroute/exact/search.py",
                        "hiroute/data/shandong.py"}
            if (not required <= names or any(name.startswith(("validation/", "tests/", "experiments/",
                                                                "timecut5/", "graph/", "microplan/"))
                                             for name in names)):
                raise RuntimeError("Unexpected HiRoute core wheel contents")
        run([sys.executable, "-m", "pip", "--isolated", "--disable-pip-version-check",
             "install", "--no-index", "--no-deps", "--no-cache-dir",
             "--force-reinstall", str(wheels[0])], work, env)
        reference_source = work / "reference-source"
        for source in (ROOT / "reference").rglob("*"):
            if source.is_file() and (source.name == "pyproject.toml" or source.suffix == ".py"):
                relative = source.relative_to(ROOT / "reference")
                destination = reference_source / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
        reference_wheels = work / "reference-wheels"
        run([sys.executable, "-m", "build", "--wheel", "--no-isolation",
             "--outdir", str(reference_wheels), str(reference_source)], work, env)
        reference_wheel, = reference_wheels.glob("*.whl")
        run([sys.executable, "-m", "pip", "--isolated", "--disable-pip-version-check",
             "install", "--no-index", "--no-deps", "--no-cache-dir", str(reference_wheel)], work, env)
        # Legacy packages remain checkout-only for differential regressions; the
        # installed distribution is deliberately the hiroute core package only.
        for source in (ROOT / "src").rglob("*"):
            if source.is_file() and source.suffix in (".py", ".cpp"):
                relative = source.relative_to(ROOT / "src")
                if relative.parts[0] != "hiroute":
                    destination = tooling / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, destination)
        # Source-only validators are a separate repository tool, not a wheel package.
        for directory in ("validation", "experiments/time_cut_v2/family_faithfulness",
                          "experiments/time_cut_v2/invocation_trace",
                          "experiments/time_cut_v2/restricted_suffix"):
            for source in (ROOT / directory).rglob("*.py"):
                copy_file(source.relative_to(ROOT), tooling)
        for relative in (*TESTS, *HIROUTE_TESTS, *FIXTURES, *HIROUTE_FIXTURES,
                         "tests/conftest.py", "tests/code_only_manifest.py",
                         "tools/check_code_publication.py", "tools/verify_artifacts.py",
                         "tools/profile_small_cases.py", "tools/real_scale_inputs.py",
                         "configs/real_scale_dev.json", "tools/run_real_scale_pilot.py"):
            copy_file(relative, tooling)
        for script in ("m5d_aggregate_screen.py", "prepare_regional_data.py", "m5d_charge_gate.py", "m5d_build_main_queries.py",
                       "m5d_freeze_main_phase.py", "m5d_main_batch.py",
                       "m5d_main_row.py", "m5d_one_query_runner.py",
                       "m5d_parallel_continuation.py",
                       "m5d_supplement_alt.py", "m5d_supplement_freeze.py",
                       "m5d_supplement_row.py", "m5d_supplement_batch.py"):
            copy_file("scripts/" + script, tooling)
        copy_file("experiments/time_cut_v2/recorded_real/node_domain_batch.py", tooling)
        copy_file("configs/m5d/fixed_grid14_screen.json", tooling)
        (tooling / "pytest.ini").write_text("[pytest]\naddopts = -ra\n")
        env["PYTHONPATH"] = str(tooling)
        origin_check = """
from pathlib import Path
import sys
import hiroute, hiroute_ref, graph.raw_way_policy
import timecut5.probe, timecut5.bounded, timecut5.hierarchy
import timecut5.coalesced_solver, timecut5.real_adapter
import timecut5.provenance, timecut5.invocation_trace
import validation.family5, validation.trace5, validation.suffix5.checker
core = Path(hiroute.__file__).resolve()
if not core.is_relative_to(Path(sys.prefix).resolve()):
    raise RuntimeError(f'HiRoute core import escaped installed wheel: {core}')
ref = Path(hiroute_ref.__file__).resolve()
if not ref.is_relative_to(Path(sys.prefix).resolve()):
    raise RuntimeError(f'Independent REF import escaped its installed wheel: {ref}')
for name, module in tuple(sys.modules.items()):
    if name == 'graph.raw_way_policy' or name == 'timecut5' or name.startswith('timecut5.'):
        origin = Path(module.__file__).resolve()
        if not origin.is_relative_to(Path.cwd().resolve()):
            raise RuntimeError(f'Legacy regression import did not come from explicit test source: {name}: {origin}')
if Path('src').exists():
    raise RuntimeError('Source tree leaked into isolated test directory')
print('HiRoute core and independent REF imported from separately built wheels; legacy regressions imported from staged source')
"""
        run([sys.executable, "-c", origin_check], tooling, env)
        for flags, label in (([], "normal"), (["-OO"], "optimized")):
            for group, selected in (("hiroute", HIROUTE_TESTS), ("legacy", TESTS)):
                report = work / f"{label}-{group}.xml"
                run([sys.executable, *flags, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                     "-c", str(tooling / "pytest.ini"), f"--junitxml={report}", *selected], tooling, env)
                suites = list(ET.parse(report).getroot().iter("testsuite"))
                if not suites or sum(int(suite.get("tests", "0")) for suite in suites) == 0:
                    raise RuntimeError(f"{label}/{group}: no tests were recorded")
                if any(int(suite.get(key, "0")) for suite in suites for key in ("skipped", "errors", "failures")):
                    raise RuntimeError(f"{label}/{group}: skipped or unsuccessful tests are not accepted")
    print(f"M5 code-only gate passed in {time.monotonic() - started:.1f}s; milestone acceptance remains separate.")


if __name__ == "__main__":
    main()
