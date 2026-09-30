import json

import numpy as np
import pytest

from _common import ROOT, sha256
from graph.road_graph import Route
from graph.validation import validate_geometry

pytestmark = pytest.mark.integration


def test_frozen_dataset_and_graph(real_data):
    graph, edges, instances, data, routing = real_data
    manifest_path = ROOT / data["dataset"]["raw_path"]
    assert sha256(manifest_path) == data["dataset"]["sha256"]
    metadata = json.loads((ROOT / data["graph_dir"] / "metadata.json").read_text())
    assert graph.node_count == metadata["node_count"]
    assert graph.edge_count == metadata["edge_count"]
    assert metadata["all_components_retained"]
    assert np.isfinite(edges[["length_m", "travel_time_s"]]).all().all()
    assert (edges[["length_m", "travel_time_s"]] >= 0).all().all()
    assert instances.dataset_sha256.eq(data["dataset"]["sha256"]).all()
    assert instances.graph_edges_sha256.eq(metadata["files"]["edges.parquet"]["sha256"]).all()


def test_all_real_od_paths_and_bands(real_data):
    graph, edges, instances, data, routing = real_data
    assert 20 <= len(instances) <= 50
    assert not instances[["origin_node", "destination_node"]].duplicated().any()
    assert (instances.origin_node != instances.destination_node).all()
    geometry = edges.geometry_wkb.to_numpy()
    for row in instances.itertuples():
        route = graph.shortest_path(int(row.origin_node), int(row.destination_node))
        assert route.nodes[0] == row.origin_node and route.nodes[-1] == row.destination_node
        assert np.isclose(route.travel_time_s, row.shortest_path_travel_time_s)
        assert np.isclose(route.distance_m, row.fastest_path_distance_m)
        assert np.isclose(graph.shortest_path_cost(int(row.origin_node), int(row.destination_node)), route.travel_time_s)
        validate_geometry(graph, route, geometry)
        stored = Route(tuple(row.path_nodes), tuple(row.path_edges), row.fastest_path_distance_m, row.shortest_path_travel_time_s, "travel_time")
        validate_geometry(graph, stored, geometry)
        assert graph.nearest_graph_node(row.origin_lat, row.origin_lon) == row.origin_node
        assert graph.nearest_graph_node(row.destination_lat, row.destination_lon) == row.destination_node
        lower, upper = map(int, row.distance_band_km.split("-"))
        assert lower * 1000 <= row.shortest_path_distance_m < upper * 1000
    assert instances.groupby("distance_band_km").size().tolist() == [routing["instances"]["per_band"]]*3
