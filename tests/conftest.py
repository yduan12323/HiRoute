from pathlib import Path
import sys
import runpy

# Receipt-epoch tests audit source-directory identity while importing modules.
# Default local collection must not mutate that identity through bytecode writes.
sys.dont_write_bytecode = True

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def pytest_addoption(parser):
    parser.addoption("--include-artifact-tests", action="store_true",
                     help="Collect legacy/full research tests; generate required research inputs and outputs first (see ci/README.md)")
    parser.addoption("--require-microplan-results", action="store_true", help="Require completed Milestone 4B Go-1 evidence")
    parser.addoption("--require-opportunity-results", action="store_true", help="Require completed Milestone 4A experiment artifacts")
    parser.addoption("--require-real-data", action="store_true", help="Fail rather than skip if Milestone 1 data is absent")
    parser.addoption("--require-envelope-results", action="store_true", help="Require completed Milestone 2 experiment artifacts")
    parser.addoption("--require-regional-results", action="store_true", help="Require completed Milestone 3A regional experiment")


@pytest.fixture(scope="session")
def real_data(request):
    from _common import configs, load_graph
    data, routing = configs()
    required = [ROOT / data["graph_dir"] / "metadata.json", ROOT / data["instances_path"]]
    if not all(path.exists() for path in required):
        if request.config.getoption("--require-real-data"):
            pytest.fail("Build real graph and OD instances before acceptance tests")
        pytest.skip("Real dataset not built; use --require-real-data for acceptance")
    graph = load_graph(data, routing)
    edges = pd.read_parquet(ROOT / data["graph_dir"] / "edges.parquet")
    instances = pd.read_parquet(ROOT / data["instances_path"])
    return graph, edges, instances, data, routing


_SELECTION = runpy.run_path(str(ROOT / "tests/code_only_manifest.py"))

def _code_only_path(path):
    relative = path.resolve().relative_to(ROOT).as_posix()
    return (relative in _SELECTION["CODE_ONLY_MODULES"]
            or relative in _SELECTION["CODE_GATE_MODULES"]
            or relative.startswith("validation/")
            or any(relative.startswith(directory + "/")
                   for directory in _SELECTION["CODE_ONLY_DIRECTORIES"]))

def pytest_configure(config):
    if config.getoption("--include-artifact-tests"):
        if not (ROOT / "results").is_dir() or not any((ROOT / "results").rglob("*.json")):
            raise pytest.UsageError(
                "Artifact tests require generated research inputs and outputs under results/ "
                "and their processed data/dependencies. See ci/README.md. "
                "Omit --include-artifact-tests for the code-only suite.")
    else:
        for argument in config.args:
            path = Path(str(argument).split("::", 1)[0])
            if path.is_file() and path.name.startswith("test_") and not _code_only_path(path):
                raise pytest.UsageError(
                    f"{path} is outside the documented code-only allowlist. "
                    "Use --include-artifact-tests after generating its research inputs; see ci/README.md.")

def pytest_ignore_collect(collection_path, config):
    if collection_path.is_file() and collection_path.name.startswith("test_"):
        relative = collection_path.resolve().relative_to(ROOT).as_posix()
        if not _code_only_path(collection_path) and relative not in _SELECTION["LEGACY_MODULES"]:
            raise pytest.UsageError(
                f"Unclassified test module: {relative}. Register it in tests/code_only_manifest.py "
                "as a main code test, isolated code gate, or legacy research test before collection.")
    if config.getoption("--include-artifact-tests"):
        return None
    relative = collection_path.resolve().relative_to(ROOT).as_posix()
    extended = (relative in _SELECTION["CODE_GATE_MODULES"]
                or any(relative == directory or relative.startswith(directory + "/")
                       for directory in _SELECTION["CODE_ONLY_DIRECTORIES"]))
    if extended:
        explicit = False
        for argument in config.args:
            selected = Path(str(argument).split("::", 1)[0]).resolve()
            if selected in (ROOT, ROOT / "tests"):
                continue
            if collection_path.resolve().is_relative_to(selected):
                explicit = True
        if not explicit:
            return True
    if collection_path.is_file() and collection_path.name.startswith("test_"):
        return not _code_only_path(collection_path)
    return None

def pytest_report_header(config):
    if not config.getoption("--include-artifact-tests"):
        return "HiRoute main code-only cohort (extended gates run separately); legacy research suite requires --include-artifact-tests (ci/README.md)"
