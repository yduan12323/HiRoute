import json

import numpy as np
import pandas as pd
import pytest

from _common import ROOT
from _envelope_common import envelope_config
from envelope import NumericalTolerance, iter_progressive_envelopes, precompute_detour_distances
from envelope.sampling import sample_waypoint_paths

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("cost",["travel_time","distance"])
def test_real_costs_containment_and_reproducibility(real_data,cost):
    graph,_,instances,_,_ = real_data
    config = envelope_config()
    tolerance = NumericalTolerance(**config["numerical_tolerance"])
    row = instances.iloc[0]
    distances = precompute_detour_distances(graph,int(row.origin_node),int(row.destination_node),cost)
    # A separate scalar API check establishes d(v,d), never d(d,v).
    witness = int(instances.iloc[2].origin_node)
    scalar = graph.shortest_path_cost(witness,int(row.destination_node),cost)
    assert np.isclose(distances.reverse_distances[witness],scalar,rtol=tolerance.relative,atol=tolerance.absolute)
    paths = sample_waypoint_paths(graph,distances,config["seed"],4,[1.1,1.4,2.2])
    repeated = sample_waypoint_paths(graph,distances,config["seed"],4,[1.1,1.4,2.2])
    assert [p.fingerprint for p in paths] == [p.fingerprint for p in repeated]
    previous = None
    for envelope in iter_progressive_envelopes(distances,distances.baseline_cost*np.array(config["detour_ratios"]),tolerance):
        assert envelope.node_mask[paths[0].nodes].all()
        assert envelope.edge_mask[paths[0].edges].all()
        assert envelope.distances is distances
        if previous:
            assert not (previous.node_mask & ~envelope.node_mask).any()
            assert not (previous.edge_mask & ~envelope.edge_mask).any()
        for path in paths:
            if path.base_cost <= envelope.budget+tolerance.allowance(envelope.budget):
                assert envelope.node_mask[path.nodes].all()
                assert envelope.edge_mask[path.edges].all()
        previous = envelope


def test_all_real_envelope_artifacts(real_data,request):
    graph,_,instances,data,_ = real_data
    config = envelope_config()
    directory = ROOT/config["results_dir"]
    if not (directory/"benchmark.json").exists():
        if request.config.getoption("--require-envelope-results"):
            pytest.fail("Run scripts/run_envelope_benchmark.py before Milestone 2 acceptance tests")
        pytest.skip("Envelope experiment artifacts absent")
    summary = json.loads((directory/"benchmark.json").read_text())
    stats = pd.read_parquet(directory/"envelope_stats.parquet")
    checks = pd.read_parquet(directory/"path_containment_tests.parquet")
    timings = pd.read_parquet(directory/"distance_benchmark.parquet")
    boundary = pd.read_parquet(directory/"boundary_diagnostics.parquet")
    assert len(stats) == len(instances)*len(config["detour_ratios"])
    assert len(timings) == len(instances)  # vectors recorded once per OD
    assert len(boundary) == len(stats)
    assert stats.groupby("instance_id").size().eq(len(config["detour_ratios"])).all()
    assert checks.groupby("instance_id").sample_id.nunique().ge(config["sampling"]["waypoint_count"]+1).all()
    assert not checks.violation.any()
    assert checks.loc[checks.within_budget,["nodes_contained","edges_contained"]].all().all()
    assert checks.loc[checks.method.eq("baseline"),["nodes_contained","edges_contained"]].all().all()
    assert (~checks.within_numerical_tolerance).any()
    assert ((~checks.within_numerical_tolerance) & ~(checks.nodes_contained & checks.edges_contained)).any()
    assert summary["containment_violations"] == 0
    assert stats.graph_edges_sha256.eq(instances.graph_edges_sha256.iloc[0]).all()
    assert summary["provenance"]["dataset_sha256"] == data["dataset"]["sha256"]
    for _, group in stats.groupby("instance_id"):
        group=group.sort_values("ratio")
        assert group.nodes.is_monotonic_increasing and group.edges.is_monotonic_increasing
        assert group.nodes.le(graph.node_count).all() and group.edges.le(graph.edge_count).all()
