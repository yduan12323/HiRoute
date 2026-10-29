"""R4 adapter enforcement of the approved exact raw-way exception."""
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import osmium
import pandas as pd
import pytest
from shapely.geometry import Point

from hiroute.data.raw_way_policy import RawWay
from hiroute.data.shandong import _highway_exclusion_reason, read_shandong_pbf

ROOT = Path(__file__).resolve().parents[1]
ROUTING = json.loads((ROOT / "configs/shandong-routing.json").read_text())


def write_way(path, way_id, tags, refs):
    with osmium.SimpleWriter(str(path)) as writer:
        writer.add_way(osmium.osm.mutable.Way(id=way_id, nodes=list(refs), tags=tags))


def fake_pyrosm(edges):
    nodes = pd.DataFrame([
        {"id": 1, "geometry": Point(117.0, 35.0)},
        {"id": 2, "geometry": Point(117.01, 35.0)},
        {"id": 3, "geometry": Point(117.02, 35.0)},
        {"id": 4, "geometry": Point(117.03, 35.0)},
    ])
    frame = pd.DataFrame([
        {"id": way_id, "highway": highway, "u": u, "v": v, "length": 100.0, "oneway": None}
        for way_id, highway, u, v in edges
    ])

    class FakeOSM:
        def __init__(self, path, **kwargs):
            assert kwargs == {"engine": "out_of_core", "workers": 1}

        def get_network(self, **kwargs):
            assert kwargs["network_type"] == "driving"
            return nodes, frame
    return FakeOSM


def test_exact_closed_shelter_way_is_removed_before_directions_and_counted(tmp_path):
    path = tmp_path / "exact-closed-shelter.osm.pbf"
    write_way(path, 100, {"highway": "yes", "building": "yes", "amenity": "shelter"}, (1, 2, 3, 1))
    rows = [(100, "yes", 1, 2), (100, "yes", 2, 3), (100, "yes", 3, 1),
            (200, "primary", 1, 4)]
    with patch("pyrosm.OSM", fake_pyrosm(rows)):
        graph = read_shandong_pbf(path, ROUTING)
    assert [edge["osm_way_id"] for edge in graph.edges] == ["200", "200"]
    assert graph.source_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert graph.audit["raw_highway_yes_candidate_ways"] == 1
    assert graph.audit["excluded_closed_shelter_contour"] == 3
    assert graph.audit["excluded_closed_shelter_contour_ways"] == 1
    assert graph.audit["excluded_street_lamp"] == 0


@pytest.mark.parametrize("tags,refs", [
    ({"highway": "yes", "building": "yes", "amenity": "shelter"}, (1, 2, 3)),
    ({"highway": "yes", "building": "no", "amenity": "shelter"}, (1, 2, 1)),
    ({"highway": "yes", "building": "yes", "amenity": "Shelter"}, (1, 2, 1)),
    ({"highway": "yes", "building": "yes", "amenity": "shelter "}, (1, 2, 1)),
    ({"highway": "yes", "amenity": "shelter"}, (1, 2, 1)),
])
def test_near_miss_raw_tags_or_open_refs_remain_fatal(tmp_path, tags, refs):
    path = tmp_path / "near-miss.osm.pbf"
    write_way(path, 100, tags, refs)
    with pytest.raises(ValueError, match="unsupported/unproven highway class 'yes'"):
        with patch("pyrosm.OSM", fake_pyrosm([(100, "yes", 1, 2)])):
            read_shandong_pbf(path, ROUTING)


def test_original_way_identity_must_match_parsed_segment_id(tmp_path):
    path = tmp_path / "wrong-way-id.osm.pbf"
    write_way(path, 100, {"highway": "yes", "building": "yes", "amenity": "shelter"}, (1, 2, 1))
    with pytest.raises(ValueError, match="unsupported/unproven highway class 'yes'"):
        with patch("pyrosm.OSM", fake_pyrosm([(101, "yes", 1, 2)])):
            read_shandong_pbf(path, ROUTING)


@pytest.mark.parametrize("raw_highway", [" yes", "yes ", "YES", "unmodeled_class"])
def test_exact_highway_label_and_unknown_classes_fail_closed(raw_highway):
    evidence = {100: RawWay((("highway", "yes"), ("building", "yes"), ("amenity", "shelter")), (1, 2, 1))}
    with pytest.raises(ValueError, match="unsupported/unproven highway class"):
        _highway_exclusion_reason(raw_highway, 100, ROUTING, evidence)


def test_closed_shelter_rule_off_or_missing_original_evidence_fails_closed():
    evidence = {100: RawWay((("highway", "yes"), ("building", "yes"), ("amenity", "shelter")), (1, 2, 1))}
    routing = json.loads(json.dumps(ROUTING))
    routing["access"]["exclude_closed_shelter_contour"] = False
    with pytest.raises(ValueError, match="unsupported/unproven highway class 'yes'"):
        _highway_exclusion_reason("yes", 100, routing, evidence)
    with pytest.raises(ValueError, match="unsupported/unproven highway class 'yes'"):
        _highway_exclusion_reason("yes", 101, ROUTING, evidence)


def test_raw_way_policy_is_shared_with_source_graph_pipeline():
    from graph.raw_way_policy import RawWay as GraphRawWay
    from graph.raw_way_policy import read_raw_way_policy as graph_reader
    from hiroute.data.raw_way_policy import read_raw_way_policy
    assert GraphRawWay is RawWay
    assert graph_reader is read_raw_way_policy
