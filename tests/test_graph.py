import numpy as np
import pandas as pd
import pytest

from graph.road_graph import IgraphRoadGraph, NoPathError, Route


@pytest.fixture
def toy():
    nodes = pd.DataFrame({"node_id": range(5), "osm_node_id": range(100, 105), "lat": [46]*5,
                          "lon": [14, 14.01, 14.02, 14.03, 14.04]})
    edges = pd.DataFrame({"edge_id": range(6), "source": [0, 0, 1, 0, 2, 3], "target": [1, 1, 3, 2, 3, 0],
                          "length_m": [10, 8, 10, 3, 3, 50], "travel_time_s": [1, 9, 1, 8, 8, 7]})
    return IgraphRoadGraph(nodes, edges)


def test_fastest_distance_and_parallel_edges(toy):
    fastest = toy.shortest_path(0, 3)
    assert fastest.nodes == (0, 1, 3)
    assert fastest.edge_ids == (0, 2)
    assert fastest.travel_time_s == 2
    assert fastest.distance_m == 20
    distance = toy.shortest_path(0, 3, cost="distance")
    assert distance.nodes == (0, 2, 3)
    assert distance.distance_m == 6
    assert toy.shortest_path_cost(0, 3) == 2
    toy.validate_route(fastest)
    with pytest.raises(ValueError):
        toy.validate_route(Route((0, 2, 3), (0, 2), 20, 2, "travel_time"))


def test_direction_disconnected_and_identity(toy):
    assert toy.shortest_path_cost(3, 0) == 7
    assert np.isinf(toy.shortest_path_cost(0, 4))
    with pytest.raises(NoPathError):
        toy.shortest_path(0, 4)
    assert toy.shortest_path(2, 2).nodes == (2,)
    assert toy.shortest_path(2, 2).travel_time_s == 0


def test_distances_reverse_and_multi_source(toy):
    assert toy.single_source_distances(3, direction="in")[0] == 2
    assert toy.single_source_distances(3, direction="out")[0] == 7
    distances = toy.multi_source_distances([0, 3])
    np.testing.assert_allclose(distances, [0, 1, 8, 0, np.inf])
    assert np.isinf(toy.multi_source_distances([])).all()
    with pytest.raises(ValueError):
        toy.single_source_distances(0, direction="both")


def test_nearest_node_and_invalid_inputs(toy):
    assert toy.nearest_graph_node(46, 14.0199) == 2
    with pytest.raises(ValueError):
        toy.nearest_graph_node(float("nan"), 14)
    with pytest.raises(ValueError):
        toy.shortest_path(99, 0)
    with pytest.raises(ValueError):
        toy.shortest_path(0, 1, cost="unknown")


def test_loading_and_bad_costs(toy, tmp_path):
    toy.nodes.to_parquet(tmp_path / "nodes.parquet", index=False)
    edges = pd.DataFrame({"edge_id": range(6), "source": toy.source, "target": toy.target,
                          "length_m": toy.weights["distance"], "travel_time_s": toy.weights["travel_time"]})
    edges.to_parquet(tmp_path / "edges.parquet", index=False)
    assert IgraphRoadGraph.load(tmp_path).shortest_path(0, 3) == toy.shortest_path(0, 3)
    for value in [-1, np.nan, np.inf]:
        edges.loc[0, "travel_time_s"] = value
        with pytest.raises(ValueError, match="nonnegative"):
            IgraphRoadGraph(toy.nodes, edges)
