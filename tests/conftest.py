from pathlib import Path
import sys

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def pytest_addoption(parser):
    parser.addoption("--require-real-data", action="store_true", help="Fail rather than skip if Milestone 1 data is absent")


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
