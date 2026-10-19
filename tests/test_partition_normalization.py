import pandas as pd
import pytest
from shapely.geometry import LineString

from _common import read_config
from graph.preprocessing import normalize_network, posted_speed


@pytest.fixture
def config():
    return read_config("configs/routing.yaml")


def sample():
    nodes = pd.DataFrame({"id": [10, 20, 30], "lat": [46]*3, "lon": [14, 14.01, 14.02]})
    edges = pd.DataFrame([
        {"id": 1, "u": 10, "v": 20, "length": 100, "highway": "primary", "oneway": "-1", "maxspeed": "30 mph", "geometry": LineString([(14, 46), (14.01, 46)])},
        {"id": 2, "u": 20, "v": 30, "length": 200, "highway": "residential", "maxspeed:forward": "10", "geometry": LineString([(14.01, 46), (14.02, 46)])},
        {"id": 3, "u": 10, "v": 30, "length": 300, "highway": "primary", "access": "private", "geometry": LineString([(14, 46), (14.02, 46)])},
        {"id": 4, "u": 10, "v": 30, "length": 300, "highway": "primary", "access:conditional": "no @ (Mo-Fr)", "geometry": LineString([(14, 46), (14.02, 46)])},
    ])
    return nodes, edges



def test_allow_empty_keeps_unknown_policy_errors(config):
    nodes, edges = sample()
    edges = edges.iloc[[0]].copy()
    edges['highway'] = 'unknown_class'
    edges['access'] = 'private'
    with pytest.raises(ValueError, match='fallback'):
        normalize_network(nodes, edges, config, allow_empty=True)


def test_allow_empty_retains_exclusion_and_invalid_length_audit(config):
    nodes, edges = sample()
    edges = edges.iloc[[2, 3]].copy()
    edges.loc[edges.index[0], 'length'] = 0
    with pytest.raises(ValueError, match='No driving edges'):
        normalize_network(nodes, edges, config)
    n, e, audit = normalize_network(nodes, edges, config, allow_empty=True)
    assert n.empty and e.empty
    assert audit['parsed_segments'] == 2
    assert audit['excluded_restricted_or_unknown_access'] == 1
    assert audit['excluded_conditional_access'] == 1
    assert audit['excluded_zero_or_invalid_length'] == 1
    assert audit['speed_class_fallback'] == audit['speed_posted_cap'] == 0


def test_worker_cli_requires_capability_before_reading():
    from pathlib import Path
    import subprocess
    import sys
    script = Path(__file__).resolve().parents[1] / 'experiments/shandong_preprocessing_v1/way_partition.py'
    run = subprocess.run([sys.executable, str(script), '--chunk', '/missing/pbf', '/missing/out', '/missing/routing'], capture_output=True, text=True)
    assert run.returncode != 0
    assert 'Internal whole-way parser worker only' in run.stderr
    assert 'FileNotFound' not in run.stderr


def test_worker_capability_rejects_parent_path_before_reading():
    from pathlib import Path
    import os
    import json
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'experiments/shandong_preprocessing_v1'))
    from way_partition import verify_chunk_capability
    r, w = os.pipe()
    os.write(w, json.dumps(dict(parent_pid=-1, pbf='/missing/pbf', pbf_sha256='0'*64,
                              routing='/missing/routing', routing_sha256='0'*64)).encode())
    os.close(w)
    with pytest.raises(PermissionError, match='parent/path'):
        verify_chunk_capability(r, Path('/missing/pbf'), Path('/missing/routing'))
