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


def test_speeds_and_explicit_fallback(config):
    model = config["speed_model"]
    assert posted_speed("30 mph", model) == pytest.approx(48.28032)
    assert posted_speed("80;50", model) == 50
    assert posted_speed("SI:urban", model) == 50
    for unknown in [None, "signals", "none", "-1", "0", "80 garbage", "999"]:
        assert posted_speed(unknown, model) is None
    nodes, edges = sample()
    _, result, _ = normalize_network(nodes, edges, config)
    assert result.speed_kph.tolist() == pytest.approx([48.28032, 10, 30])
    assert result.speed_source.tolist() == ["posted_cap", "posted_cap", "road_class_fallback"]


def test_oneway_access_and_deterministic_tables(config):
    nodes, edges = sample()
    node_table, edge_table, audit = normalize_network(nodes, edges, config)
    assert edge_table[["source_osm", "target_osm"]].values.tolist() == [[20, 10], [20, 30], [30, 20]]
    assert audit["excluded_restricted_or_unknown_access"] == 1
    assert audit["excluded_conditional_access"] == 1
    other_nodes, other_edges, other_audit = normalize_network(nodes.sample(frac=1, random_state=1), edges.sample(frac=1, random_state=2), config)
    pd.testing.assert_frame_equal(node_table, other_nodes)
    pd.testing.assert_frame_equal(edge_table, other_edges)
    assert audit == other_audit


def test_unspecified_highway_stops(config):
    nodes, edges = sample()
    edges.loc[0, "highway"] = "unmodeled_class"
    with pytest.raises(ValueError, match="fallback"):
        normalize_network(nodes, edges, config)


def test_bus_only_highway_excluded(config):
    nodes, edges = sample()
    edges.loc[0, "highway"] = "busway"
    _, result, audit = normalize_network(nodes, edges, config)
    assert "busway" not in result.highway.tolist()
    assert audit["excluded_highway_class"] == 1
