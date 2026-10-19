"""Exact original-way evidence for the narrowly amended road-admission policy.

Never infer original closure from segmented geometry or coincident coordinates.
Only highway=yes candidate records are retained; no location index is required.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RawWay:
    """Copied before parser segmentation; strings and reference order are unchanged."""

    tags: tuple[tuple[str, str], ...]
    node_ids: tuple[int, ...]

    def is_closed_shelter_contour(self) -> bool:
        # Duplicate keys are ambiguous evidence, even if one occurrence matches.
        tags = dict(self.tags)
        return (len(tags) == len(self.tags)
                and tags.get("highway") == "yes"
                and tags.get("building") == "yes"
                and tags.get("amenity") == "shelter"
                and len(self.node_ids) >= 2
                and self.node_ids[0] == self.node_ids[-1])


def read_raw_way_policy(path: str | Path) -> dict[int, RawWay]:
    """Read a snapshot PBF/XML before segmentation, retaining exact yes-way evidence.

    Missing/duplicate candidate way IDs fail closed. This does not whitelist a
    highway class, mutate the input, or resolve node locations. Full original
    tags and references are copied because osmium callback objects expire.
    """
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
                tuple(node.ref for node in way.nodes),
            )

    Handler().apply_file(str(path), locations=False)
    return records
