"""Synthetic, data-free checks of the disclosed road-admission amendment."""
from dataclasses import FrozenInstanceError
from pathlib import Path

import pandas as pd
import pytest
from shapely.geometry import LineString
import yaml

from graph.preprocessing import normalize_network
from graph.raw_way_policy import RawWay, read_raw_way_policy

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def config():
    return yaml.safe_load((ROOT / "configs/routing.yaml").read_text())


def raw(tags=None, refs=(10, 20, 30, 10)):
    return RawWay(tuple((tags or {"highway": "yes", "building": "yes", "amenity": "shelter"}).items()), refs)


def network(highway="yes"):
    nodes = pd.DataFrame({"id": [10, 20, 30], "lat": [46.] * 3, "lon": [14., 14.01, 14.02]})
    # A closed original way was split into three individually OPEN segments.
    edges = pd.DataFrame([
        {"id": 1, "u": u, "v": v, "length": 100., "highway": highway,
         "geometry": LineString([(14., 46.), (14.01, 46.)])}
        for u, v in [(10, 20), (20, 30), (30, 10)]
    ] + [{"id": 2, "u": 10, "v": 20, "length": 100., "highway": "residential",
          "geometry": LineString([(14., 46.), (14.01, 46.)])}])
    return nodes, edges


def test_closed_original_exclusion_counts_and_open_segments(config):
    nodes, edges = network()
    _, result, audit = normalize_network(nodes, edges, config, raw_way_policy={1: raw()})
    assert set(result.osm_way_id) == {2}
    assert len(result) == 2
    assert audit["excluded_closed_shelter_contour"] == 3
    assert audit["excluded_closed_shelter_contour_ways"] == 1
    assert audit["excluded_street_lamp"] == 0
    assert "yes" not in config["speed_model"]["class_kph"]
    assert "yes" not in config["access"]["excluded_highway"]


@pytest.mark.parametrize("highway", ["yes", "unmodeled_class", "YES", " yes", "yes ", "street_lamp "])
def test_unknowns_fail_closed_even_restricted(config, highway):
    nodes, edges = network(highway)
    edges["access"] = "private"
    with pytest.raises(ValueError, match="fallback"):
        normalize_network(nodes, edges, config)


@pytest.mark.parametrize("key,value", [
    ("highway", "YES"), ("highway", " yes"), ("highway", "yes "),
    ("building", None), ("building", "roof"), ("building", "true"),
    ("building", "YES"), ("building", " yes"), ("building", "yes "),
    ("amenity", None), ("amenity", "Shelter"), ("amenity", "shelter "),
    ("amenity", " shelter"), ("amenity", "bus_station"),
])
def test_raw_tags_must_match_exactly(config, key, value):
    tags = {"highway": "yes", "building": "yes", "amenity": "shelter"}
    if value is None:
        tags.pop(key)
    else:
        tags[key] = value
    nodes, edges = network()
    with pytest.raises(ValueError, match="fallback"):
        normalize_network(nodes, edges, config, raw_way_policy={1: raw(tags)})


@pytest.mark.parametrize("refs", [(), (10,), (10, 20), (10, 20, 30, 40)])
def test_missing_or_open_original_refs_fail(config, refs):
    nodes, edges = network()
    # Parsed geometry may look closed, including coincident endpoint coordinates.
    edges["geometry"] = [LineString([(14., 46.), (14.01, 46.), (14., 46.)])] * len(edges)
    with pytest.raises(ValueError, match="fallback"):
        normalize_network(nodes, edges, config, raw_way_policy={1: raw(refs=refs)})


def test_wrong_way_id_or_duplicate_raw_keys_not_proof(config):
    nodes, edges = network()
    for evidence in [{9: raw()}, {1: RawWay(raw().tags + (("building", "yes"),), raw().node_ids)}]:
        with pytest.raises(ValueError, match="fallback"):
            normalize_network(nodes, edges, config, raw_way_policy=evidence)


@pytest.mark.parametrize("missing", [False, True])
def test_policy_off_still_rejects_yes(config, missing):
    if missing:
        config["access"].pop("exclude_closed_shelter_contour")
    else:
        config["access"]["exclude_closed_shelter_contour"] = False
    nodes, edges = network()
    with pytest.raises(ValueError, match="fallback"):
        normalize_network(nodes, edges, config, raw_way_policy={1: raw()})


def test_street_lamp_exact_exclusion_and_audit(config):
    nodes, edges = network("street_lamp")
    edges.loc[edges.id == 1, "oneway"] = "invalid"
    _, result, audit = normalize_network(nodes, edges, config)
    assert set(result.osm_way_id) == {2}
    assert audit["excluded_street_lamp"] == 3
    assert audit["excluded_street_lamp_ways"] == 1
    assert audit["excluded_closed_shelter_contour"] == 0


def test_unrelated_raw_evidence_does_not_change_known_roads(config):
    nodes, edges = network("primary")
    baseline = normalize_network(nodes, edges, config)
    changed = normalize_network(nodes, edges, config, raw_way_policy={1: raw()})
    for left, right in zip(baseline[:2], changed[:2]):
        pd.testing.assert_frame_equal(left, right)
    assert baseline[2] == changed[2]


def test_order_invariance(config):
    nodes, edges = network()
    first = normalize_network(nodes, edges, config, raw_way_policy={1: raw()})
    second = normalize_network(nodes.sample(frac=1, random_state=1), edges.sample(frac=1, random_state=2),
                               config, raw_way_policy={1: raw()})
    for left, right in zip(first[:2], second[:2]):
        pd.testing.assert_frame_equal(left, right)
    assert first[2] == second[2]


def test_all_excluded_remains_failure(config):
    nodes, edges = network()
    with pytest.raises(ValueError, match="No driving edges survive"):
        normalize_network(nodes, edges.loc[edges.id == 1], config, raw_way_policy={1: raw()})


def test_pbf_raw_tags_and_node_order_survive_scan(tmp_path):
    import osmium
    path = tmp_path / "synthetic.osm.pbf"
    tags = {"highway": "yes", "building": "yes", "amenity": "shelter", "name": " keep spaces "}
    with osmium.SimpleWriter(str(path)) as writer:
        for id_, refs, way_tags in [(1, [10, 20, 30, 10], tags),
                                    (2, [10, 20, 30, 40], tags),
                                    (3, [10, 20], {"highway": "residential"})]:
            writer.add_way(osmium.osm.mutable.Way(id=id_, nodes=refs, tags=way_tags))
    records = read_raw_way_policy(path)
    assert set(records) == {1, 2}
    assert dict(records[1].tags) == tags
    assert records[1].node_ids == (10, 20, 30, 10)
    assert records[1].is_closed_shelter_contour()
    assert not records[2].is_closed_shelter_contour()
    with pytest.raises(FrozenInstanceError):
        records[1].node_ids = (10, 20)


def test_duplicate_candidate_way_ids_fail(tmp_path):
    import osmium
    path = tmp_path / "duplicate.osm.pbf"
    with osmium.SimpleWriter(str(path)) as writer:
        for _ in range(2):
            writer.add_way(osmium.osm.mutable.Way(id=1, nodes=[10, 20, 10], tags={"highway": "yes"}))
    with pytest.raises(ValueError, match="Duplicate"):
        read_raw_way_policy(path)


def test_unknown_not_hidden_by_duplicate_way_record(config):
    nodes, edges = network("primary")
    edges.loc[1, "highway"] = "unmodeled_class"
    with pytest.raises(ValueError, match="fallback"):
        normalize_network(nodes, edges, config)


def test_one_unmatched_yes_way_blocks_whole_graph(config):
    nodes, edges = network()
    second = edges.iloc[[0]].copy()
    second["id"] = 3
    edges = pd.concat([edges, second], ignore_index=True)
    with pytest.raises(ValueError, match="fallback"):
        normalize_network(nodes, edges, config, raw_way_policy={1: raw()})
