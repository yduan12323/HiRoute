"""Required installed-wheel CI: exact policy logic, no geospatial dependencies."""
from dataclasses import FrozenInstanceError
import sys
from types import SimpleNamespace

import pytest

from graph.raw_way_policy import RawWay, read_raw_way_policy, validate_access_tokens

TAGS = (("highway", "yes"), ("building", "yes"), ("amenity", "shelter"))


@pytest.mark.parametrize("key,value", [
    ("highway", None), ("highway", "YES"), ("highway", "yes "), ("highway", " yes"),
    ("highway", "unmodeled"), ("building", None), ("building", "true"),
    ("building", "YES"), ("building", "yes "), ("building", "roof"),
    ("amenity", None), ("amenity", "Shelter"), ("amenity", "shelter "),
    ("amenity", " shelter"), ("amenity", "bus_station"),
])
def test_literal_near_misses_rejected(key, value):
    tags = dict(TAGS)
    if value is None:
        tags.pop(key)
    else:
        tags[key] = value
    assert not RawWay(tuple(tags.items()), (1, 2, 3, 1)).is_closed_shelter_contour()


@pytest.mark.parametrize("refs,expected", [
    ((), False), ((1,), False), ((1, 2), False),
    ((1, 2, 3, 4), False), ((1, 2, 3, 1), True),
])
def test_original_reference_closure(refs, expected):
    assert RawWay(TAGS, refs).is_closed_shelter_contour() is expected


def test_duplicate_tags_rejected_and_records_immutable():
    assert not RawWay(TAGS + (("building", "yes"),), (1, 2, 1)).is_closed_shelter_contour()
    record = RawWay(TAGS, (1, 2, 3, 1))
    with pytest.raises(FrozenInstanceError):
        record.node_ids = (1, 2)


class FakeTags(list):
    def get(self, key):
        return next((item.v for item in self if item.k == key), None)


def fake_way(id_, highway="yes"):
    tags = [(k, highway if k == "highway" else v) for k, v in TAGS]
    tags.append(("name", " preserve raw spaces "))
    return SimpleNamespace(id=id_, tags=FakeTags(SimpleNamespace(k=k, v=v) for k, v in tags),
                           nodes=[SimpleNamespace(ref=n) for n in (10, 20, 30, 10)])


def test_decoder_copies_before_callback_expiry(monkeypatch):
    candidate, known = fake_way(1), fake_way(2, "residential")

    class Handler:
        def apply_file(self, path, locations):
            assert path == "snapshot.pbf"
            assert locations is False
            self.way(candidate)
            self.way(known)
            candidate.tags.clear()
            candidate.nodes.clear()

    monkeypatch.setitem(sys.modules, "osmium", SimpleNamespace(SimpleHandler=Handler))
    records = read_raw_way_policy("snapshot.pbf")
    assert set(records) == {1}
    assert records[1].node_ids == (10, 20, 30, 10)
    assert dict(records[1].tags)["name"] == " preserve raw spaces "
    assert records[1].is_closed_shelter_contour()


def test_decoder_duplicate_way_ids_fail(monkeypatch):
    class Handler:
        def apply_file(self, path, locations):
            self.way(fake_way(1))
            self.way(fake_way(1))

    monkeypatch.setitem(sys.modules, "osmium", SimpleNamespace(SimpleHandler=Handler))
    with pytest.raises(ValueError, match="Duplicate"):
        read_raw_way_policy("snapshot.pbf")


ACCESS_FIELDS = ("allowed", "excluded", "hierarchy", "excluded_highway")


@pytest.mark.parametrize("field", ACCESS_FIELDS)
@pytest.mark.parametrize("invalid", [True, False, 1, None, [True], [False], ["yes", True], [1], [None], ("yes",), {"yes": True}])
def test_access_token_lists_reject_non_strings(field, invalid):
    policy = {key: ["yes", "no"] for key in ACCESS_FIELDS}
    policy[field] = invalid
    with pytest.raises(ValueError, match=rf"access\.{field} must be a list of strings"):
        validate_access_tokens(policy)


def test_access_tokens_validate_without_mutation():
    policy = {"allowed": ["yes", "permissive", "designated", "official"],
              "excluded": ["no", "private"],
              "hierarchy": ["motorcar", "motor_vehicle", "vehicle", "access"],
              "excluded_highway": ["street_lamp"]}
    before = {key: list(value) for key, value in policy.items()}
    validate_access_tokens(policy)
    assert policy == before


@pytest.mark.parametrize("field", ACCESS_FIELDS)
def test_access_token_lists_are_required(field):
    policy = {key: [] for key in ACCESS_FIELDS if key != field}
    with pytest.raises(ValueError, match=rf"access\.{field}"):
        validate_access_tokens(policy)
