import numpy as np
import pandas as pd
import pytest
from scipy.sparse.csgraph import floyd_warshall

from envelope import (NumericalTolerance, build_envelope_from_precomputed,
                      compute_safe_detour_envelope, iter_progressive_envelopes,
                      precompute_detour_distances)
from envelope.boundary import boundary_node_risk, read_poly
from envelope.sampling import sample_waypoint_paths
from graph.road_graph import IgraphRoadGraph, NoPathError


def graph_from_edges(n, source, target, times, lengths=None):
    nodes = pd.DataFrame({"node_id": range(n), "osm_node_id": range(n), "lat": np.full(n, 46.),
                          "lon": np.linspace(14., 14.1, n)})
    edges = pd.DataFrame({"edge_id": range(len(source)), "source": source, "target": target,
                          "length_m": times if lengths is None else lengths, "travel_time_s": times})
    return IgraphRoadGraph(nodes, edges)


@pytest.fixture
def corridors():
    # Four alternatives of cost 10, 11, 14, 21; parallel edge 8 has route cost 14.
    # Node 4 lies near the straight s-d line but its corridor exceeds B=20.
    return graph_from_edges(9, [0,1,0,2,0,3,0,4,0,5,0,8], [1,5,2,5,3,5,4,5,1,0,7,5],
                            [5,5,5,6,7,7,10,11,9,100,1,1],
                            [50,50,55,55,70,70,10,10,20,1000,10,10])


def test_asymmetric_distances_and_definitions(corridors):
    distances = precompute_detour_distances(corridors, 0, 5)
    assert distances.baseline_cost == 10
    assert distances.forward_distances[5] == 10
    assert distances.reverse_distances[0] == 10
    assert corridors.single_source_distances(5, direction="out")[0] == 100
    assert distances.reverse_distances[2] == 6
    envelope = build_envelope_from_precomputed(distances, 14, NumericalTolerance(0, 0))
    expected_nodes = distances.forward_distances + distances.reverse_distances <= 14
    expected_edges = distances.forward_distances[corridors.source] + corridors.weights["travel_time"] + distances.reverse_distances[corridors.target] <= 14
    np.testing.assert_array_equal(envelope.node_mask, expected_nodes)
    np.testing.assert_array_equal(envelope.edge_mask, expected_edges)
    assert not envelope.node_mask[[6, 7, 8]].any()
    assert not envelope.edge_mask[[9, 10, 11]].any()
    assert not envelope.node_mask.flags.writeable
    assert not distances.forward_distances.flags.writeable


def test_corridors_parallel_edges_and_nesting(corridors):
    distances = precompute_detour_distances(corridors, 0, 5)
    envelopes = list(iter_progressive_envelopes(distances, [10, 11, 14, 20, 21]))
    for index, expected in enumerate([[1], [1,2], [1,2,3], [1,2,3], [1,2,3,4]]):
        assert np.flatnonzero(envelopes[index].node_mask[:5]).tolist() == [0, *expected]
        assert envelopes[index].edge_mask[[0, 1]].all()
        assert envelopes[index].forward_distances is distances.forward_distances
    assert not envelopes[1].edge_mask[8] and envelopes[2].edge_mask[8]
    assert not envelopes[3].node_mask[4]  # geometrically direct but over-budget
    for left, right in zip(envelopes, envelopes[1:]):
        assert not (left.node_mask & ~right.node_mask).any()
        assert not (left.edge_mask & ~right.edge_mask).any()
    with pytest.raises(ValueError, match="nondecreasing"):
        list(iter_progressive_envelopes(distances, [14, 11]))


def test_cost_units_and_invalid_budgets(corridors):
    distance = precompute_detour_distances(corridors, 0, 5, cost="distance")
    assert distance.unit == "metres" and distance.baseline_cost == 20
    assert compute_safe_detour_envelope(corridors, 0, 5, 20, cost="distance").node_mask[4]
    time = precompute_detour_distances(corridors, 0, 5)
    assert time.unit == "seconds"
    for budget in [9.99, np.inf, np.nan, -1]:
        with pytest.raises(ValueError):
            build_envelope_from_precomputed(time, budget)
    with pytest.raises(NoPathError):
        precompute_detour_distances(corridors, 0, 6)
    with pytest.raises(ValueError):
        precompute_detour_distances(corridors, 0, 5, "utility")


def test_zero_costs_identity_and_tolerance():
    graph = graph_from_edges(3, [0,1,0], [1,0,0], [0,0,2])
    envelope = compute_safe_detour_envelope(graph, 0, 0, 0, tolerance=NumericalTolerance(0,0))
    assert envelope.node_mask.tolist() == [True,True,False]
    assert envelope.edge_mask.tolist() == [True,True,False]
    graph = graph_from_edges(3, [0,0,2], [1,2,1], [10,5,5 + 5e-9])
    distances = precompute_detour_distances(graph,0,1)
    strict = build_envelope_from_precomputed(distances,10,NumericalTolerance(0,0))
    tolerant = build_envelope_from_precomputed(distances,10,NumericalTolerance(1e-8,1e-10))
    assert not strict.node_mask[2] and tolerant.node_mask[2]
    assert tolerant.tolerance.allowance(10) < 1e-7
    for values in [(-1,0), (0,np.inf), (np.nan,0)]:
        with pytest.raises(ValueError):
            NumericalTolerance(*values)


def test_over_budget_walk_may_still_use_retained_edges():
    graph = graph_from_edges(3,[0,1,1],[1,2,0],[5,5,1])
    envelope = compute_safe_detour_envelope(graph,0,2,16)
    # Two cycles then finish: 5+1+5+1+5+5=22 >16, all edges retained.
    edges = [0,2,0,2,0,1]
    assert graph.weights["travel_time"][edges].sum() == 22
    assert envelope.edge_mask[edges].all()


def test_one_way_does_not_create_reverse_reachability():
    graph = graph_from_edges(2,[0],[1],[5])
    envelope = compute_safe_detour_envelope(graph,0,1,10)
    assert envelope.edge_mask.tolist() == [True]
    assert envelope.node_mask.tolist() == [True,True]
    assert graph.source.tolist() == [0] and graph.target.tolist() == [1]
    with pytest.raises(NoPathError):
        precompute_detour_distances(graph,1,0)


def test_independent_floyd_warshall_and_all_toy_simple_paths():
    rng = np.random.default_rng(7)
    for _ in range(6):
        source, target = np.where(rng.random((7,7)) < .25)
        source = np.append(source, [0,0])
        target = np.append(target, [6,6])
        costs = np.append(rng.integers(1,11,len(source)-2), [8,9])
        graph = graph_from_edges(7,source,target,costs)
        adjacency = np.full((7,7),np.inf)
        np.minimum.at(adjacency,(source,target),costs)
        np.fill_diagonal(adjacency,0)
        oracle = floyd_warshall(adjacency,directed=True)
        distances = precompute_detour_distances(graph,0,6)
        np.testing.assert_allclose(distances.forward_distances,oracle[0])
        np.testing.assert_allclose(distances.reverse_distances,oracle[:,6])
        for envelope in iter_progressive_envelopes(distances, distances.baseline_cost * np.array([1,1.1,1.4,2])):
            def visit(node, visited, edge_ids, total):
                if node == 6:
                    if total <= envelope.budget:
                        assert envelope.node_mask[list(visited)].all()
                        assert envelope.edge_mask[edge_ids].all()
                    return
                for edge in np.flatnonzero(graph.source == node):
                    nxt = int(graph.target[edge])
                    if nxt not in visited:
                        visit(nxt,[*visited,nxt],[*edge_ids,int(edge)],total+costs[edge])
            visit(0,[0],[],0)


def test_waypoint_sampling_determinism_and_directed_walks(corridors):
    distances = precompute_detour_distances(corridors,0,5)
    paths = sample_waypoint_paths(corridors,distances,9,4,[1.1,1.4,2.2])
    repeat = sample_waypoint_paths(corridors,distances,9,4,[1.1,1.4,2.2])
    assert [p.fingerprint for p in paths] == [p.fingerprint for p in repeat]
    assert any(p.base_cost > 20 for p in paths)
    for envelope in iter_progressive_envelopes(distances,[10,11,14,20]):
        for path in paths:
            if path.base_cost <= envelope.budget:
                assert envelope.node_mask[path.nodes].all()
                assert envelope.edge_mask[path.edges].all()


def test_boundary_polygon_holes_and_margin(tmp_path):
    polygon_file = tmp_path/'fixture.poly'
    polygon_file.write_text('fixture\n1\n14 46\n15 46\n15 47\n14 47\nEND\n!1\n14.4 46.4\n14.6 46.4\n14.6 46.6\n14.4 46.6\nEND\nEND\n')
    polygon = read_poly(polygon_file)
    risk,_,_ = boundary_node_risk(np.array([46.2,46.5,46.00001,45.9]),np.array([14.2,14.5,14.2,14.2]),polygon,'EPSG:3035',1000)
    assert risk.tolist() == [False,True,True,True]
