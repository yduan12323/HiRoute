"""Exact original-way evidence for the approved road-admission exception."""
from __future__ import annotations
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

def validate_access_tokens(policy: Mapping) -> None:
    """Reject YAML-coerced access tokens instead of silently changing admission."""
    for field in ("allowed", "excluded", "hierarchy", "excluded_highway"):
        tokens = policy.get(field)
        if not isinstance(tokens, list) or any(not isinstance(token, str) for token in tokens):
            raise ValueError(f"access.{field} must be a list of strings; quote YAML yes/no tokens")


@dataclass(frozen=True)
class RawWay:
    """Copied before parser segmentation; raw tags and reference order are preserved."""
    tags: tuple[tuple[str, str], ...]
    node_ids: tuple[int, ...]

    def is_closed_shelter_contour(self) -> bool:
        values = dict(self.tags)
        return (len(values) == len(self.tags)
                and values.get("highway") == "yes"
                and values.get("building") == "yes"
                and values.get("amenity") == "shelter"
                and len(self.node_ids) >= 2
                and self.node_ids[0] == self.node_ids[-1])

def read_raw_way_policy(path: str | Path) -> dict[int, RawWay]:
    """Read exact highway=yes original-way evidence, without node-location indexing."""
    import osmium
    records: dict[int, RawWay] = {}
    class Handler(osmium.SimpleHandler):
        def way(self, way):
            if way.tags.get("highway") != "yes":
                return
            if way.id in records:
                raise ValueError(f"Duplicate raw highway=yes way ID: {way.id}")
            records[way.id] = RawWay(
                tuple((item.k, item.v) for item in way.tags),
                tuple(node.ref for node in way.nodes))
    Handler().apply_file(str(path), locations=False)
    return records
