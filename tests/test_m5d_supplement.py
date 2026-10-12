"""Low-cost fixed-denominator and same-ALT parity gates."""
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import unittest

from scripts.m5d_supplement_alt import SameALTMemberScan
from scripts.m5d_supplement_freeze import rows_for
from timecut5.deployable import LandmarkDistances, RegionLandmarkSummary, member_set_digest


def test_fixed_24_row_denominator():
    queries = {"queries": [{"query_id": f"Q{i}", "od_id": f"OD{i // 4}"}
                           for i in range(48)]}
    full = {"target_query_ids": [f"Q{i}" for i in range(6)],
            "universes_by_od": {f"OD{i}": {"site_count": 6000 + i}
                                for i in range(2)}}
    rows = rows_for(queries, full)
    assert len(rows) == 24
    assert [r["ordinal"] for r in rows[:12]] == [i for i in range(6) for _ in range(2)]
    assert {(r["ordinal"], r["candidate_count"]) for r in rows[12:16]} == {
        (8, 32), (8, 128), (47, 32), (47, 128)}
    assert len({r["row_id"] for r in rows}) == 24
    full["target_query_ids"] = full["target_query_ids"][1:]
    with unittest.TestCase().assertRaises(ValueError):
        rows_for(queries, full)


def test_member_scan_uses_same_summary_and_mask():
    region = SimpleNamespace(identifier="r", members=("a", "b"))
    sha = "0" * 64
    provider = object.__new__(SameALTMemberScan)
    provider._regions = {"r": region}
    provider.sites = {"a": SimpleNamespace(anchor_id="a"),
                      "b": SimpleNamespace(anchor_id="b")}
    provider.landmarks = (LandmarkDistances(
        {"x": 0., "a": 2., "b": 3.},
        {"x": 0., "a": 2., "b": 3.}),)
    provider.graph_sha256 = provider.landmark_sha256 = sha
    provider._member_hash = {"r": member_set_digest(region.members)}
    provider._summary = {"r": RegionLandmarkSummary(provider._member_hash["r"],
        sha, sha, (2.,), (3.,))}
    provider._action_bits = {("a", "C"): 1, ("b", "C"): 2,
                             ("b", "S"): 4}
    provider._action_masks = {("r", "C", 1): 3, ("r", "S", 0): 0}
    provider.online_mask_word_work = provider.member_scan_reads = 0
    provider.member_scan_summary_queries = provider.member_scan_mask_queries = 0
    assert provider._incoming("x", region) == 2
    assert provider.action_mask(region, "C", 1) == 3
    assert provider.action_mask(region, "S", 0) == 0
    assert provider.member_scan_reads == 6
    provider._summary["r"] = RegionLandmarkSummary(provider._member_hash["r"],
        sha, sha, (1.,), (3.,))
    with unittest.TestCase().assertRaisesRegex(ValueError, "summary parity"):
        provider._incoming("x", region)
