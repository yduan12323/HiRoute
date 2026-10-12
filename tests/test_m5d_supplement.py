"""Low-cost fixed-denominator and same-ALT parity gates."""
from pathlib import Path
import hashlib
import json
import sys
import tempfile
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import unittest

from scripts.m5d_supplement_alt import SameALTMemberScan
from scripts import m5d_supplement_batch as batch
from scripts.m5d_supplement_freeze import rows_for
from timecut5.deployable import LandmarkDistances, RegionLandmarkSummary, member_set_digest
from timecut5.road_provider import TableFreeRegionBoundProvider


def check(condition):
    if not condition:
        raise AssertionError("Supplemental protocol check failed")


def test_fixed_24_row_denominator():
    queries = {"queries": [{"query_id": f"Q{i}", "od_id": f"OD{i // 4}"}
                           for i in range(48)]}
    full = {"target_query_ids": [f"Q{i}" for i in range(6)],
            "universes_by_od": {f"OD{i}": {"site_count": 6000 + i}
                                for i in range(2)}}
    rows = rows_for(queries, full)
    check(len(rows) == 24)
    check([r["ordinal"] for r in rows[:12]] == [i for i in range(6) for _ in range(2)])
    check({(r["ordinal"], r["candidate_count"]) for r in rows[12:16]} == {
        (8, 32), (8, 128), (47, 32), (47, 128)})
    check(len({r["row_id"] for r in rows}) == 24)
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
    check(provider._incoming("x", region) == 2)
    check(provider.action_mask(region, "C", 1) == 3)
    check(provider.action_mask(region, "S", 0) == 0)
    check(provider.member_scan_reads == 6)
    check(provider.member_scan_summary_queries == 1)
    check(provider.member_scan_mask_queries == 2)
    provider._summary["r"] = RegionLandmarkSummary(provider._member_hash["r"],
        sha, sha, (1.,), (3.,))
    with unittest.TestCase().assertRaisesRegex(ValueError, "summary parity"):
        provider._incoming("x", region)


def test_restricted_mixed_effects_unreachable_alt_and_counts():
    region = SimpleNamespace(identifier="restricted", members=("a", "b"))
    sha = "1" * 64
    provider = object.__new__(SameALTMemberScan)
    provider._regions = {region.identifier: region}
    provider.sites = {name: SimpleNamespace(anchor_id=name) for name in ("a", "b", "c")}
    provider.landmarks = (LandmarkDistances(
        {"x": 0., "a": 2., "b": float("inf"), "c": 9.},
        {"x": 0., "a": 1., "b": float("inf"), "c": 9.}),)
    provider.graph_sha256 = provider.landmark_sha256 = sha
    provider._member_hash = {region.identifier: member_set_digest(region.members)}
    provider._summary = {region.identifier: RegionLandmarkSummary(
        provider._member_hash[region.identifier], sha, sha, (2.,), (float("inf"),))}
    provider._action_bits = {("a", "C"): 1, ("b", "CS"): 2, ("c", "S"): 4}
    provider._action_masks = {(region.identifier, effect, remaining):
        (0 if effect in ("S", "CS") and not remaining else
         sum(bit for (site, action), bit in provider._action_bits.items()
             if site in region.members and action == effect))
        for effect in ("C", "S", "CS") for remaining in (0, 1)}
    provider.online_mask_word_work = provider.member_scan_reads = 0
    provider.member_scan_summary_queries = provider.member_scan_mask_queries = 0
    check(provider._incoming("x", region) == TableFreeRegionBoundProvider._incoming(
        provider, "x", region) == 2)
    check(provider.member_scan_reads == 4)
    for effect in ("C", "S", "CS"):
        for remaining in (0, 1):
            actual = provider.action_mask(region, effect, remaining)
            check(actual == provider._action_masks[region.identifier, effect, remaining])
            check(actual & 4 == 0)  # c is outside the restricted Region universe.
    check(provider.member_scan_mask_queries == 6)
    check(provider.member_scan_reads == 12)  # 4 ALT + four enabled two-member masks.
    provider._action_masks[region.identifier, "C", 1] = 3
    with unittest.TestCase().assertRaisesRegex(ValueError, "mask parity"):
        provider.action_mask(region, "C", 1)


def _mock_batch_inputs(root: Path, *, component="same_alt_member_scan"):
    for name in ("source", "graph", "out"):
        (root / name).mkdir()
    paths = {name: root / f"{name}.json" for name in
             ("pools", "queries", "full", "manifest", "main", "reconciliation")}
    for name in ("pools", "queries", "full"):
        paths[name].write_text("{}")
    first = {"row_id": "scan_08_n32_hier", "query_id": "Q8", "ordinal": 8,
             "candidate_count": 32, "component": component, "method": "hier"}
    rows = [first] + [{"row_id": f"pending_{i}"} for i in range(23)]
    phase_sha = "a" * 64
    manifest = {"schema": "hiroute.m5d.frozen_supplement.v1", "rows": rows,
        "total_reservation_cpu_seconds": 14640, "wall_seconds": 600,
        "memory_bytes": 8 * 1024**3, "cpu_quota_percent": 100,
        "host_cpu_guard_seconds": 60,
        "input_sha256": {**{name: hashlib.sha256(paths[name].read_bytes()).hexdigest()
                            for name in ("pools", "queries", "full")},
                         "full_universes": hashlib.sha256(paths["full"].read_bytes()).hexdigest(),
                         "main": phase_sha}}
    paths["manifest"].write_text(json.dumps(manifest))
    main_rows = {f"filler_{i}": {"status": "time_limit"} for i in range(191)}
    main_rows["Q8_n32_hier"] = {"exact_outcome": {"J": "1"},
        "seed_j": "1", "certified_depth": 4, "prewarm_sha256": "p"}
    main = {"schema": "hiroute.m5d.main_batch_state.v1", "phase_sha256": phase_sha,
            "stopped": True, "rows": main_rows}
    paths["main"].write_text(json.dumps(main))
    reconciliation = {"schema": "hiroute.m5d.launch_reconciliation.v1",
        "main_state_sha256": hashlib.sha256(paths["main"].read_bytes()).hexdigest(),
        "main_cgroup_empty": True, "outside_main_receipts_reconciled": True,
        "independent_review_approved": True, "main_host_cpu_reconciled": True,
        "main_host_cpu_ns": 627 * 10**9, "available_cpu_seconds": 17000,
        "required_margin_cpu_seconds": 0}
    paths["reconciliation"].write_text(json.dumps(reconciliation))
    return paths, manifest, main, reconciliation


def test_wrong_main_phase_and_changed_resume_reconciliation_fail_closed():
    with tempfile.TemporaryDirectory() as directory:
        paths, manifest, main, reconciliation = _mock_batch_inputs(Path(directory))
        main["phase_sha256"] = "b" * 64
        with unittest.TestCase().assertRaisesRegex(ValueError, "phase binding"):
            batch.verify_launch_binding(manifest, json.dumps(main).encode(),
                                        paths["reconciliation"].read_bytes())
        state = {"manifest_sha256": "m", "reconciliation_sha256": "old",
                 "host_cpu_ns": 0}
        with unittest.TestCase().assertRaisesRegex(ValueError, "changed"):
            batch.verify_resume_binding(state, "m", "new")
        # The run path rejects a changed reconciliation before any row unit.
        paths["main"].write_text(json.dumps({**main, "phase_sha256": "a" * 64}))
        reconciliation["main_state_sha256"] = hashlib.sha256(
            paths["main"].read_bytes()).hexdigest()
        paths["reconciliation"].write_text(json.dumps(reconciliation))
        saved = {"schema": "hiroute.m5d.supplement_batch_state.v1",
            "manifest_sha256": hashlib.sha256(paths["manifest"].read_bytes()).hexdigest(),
            "reconciliation_sha256": "old", "host_cpu_ns": 0,
            "charged_cpu_ns": 0, "rows": {}, "stopped": False}
        (Path(directory) / "out" / "state.json").write_text(json.dumps(saved))
        with mock.patch.object(batch, "run_supervised") as supervised:
            with unittest.TestCase().assertRaisesRegex(ValueError, "changed"):
                batch.run(Path(directory) / "source", Path(directory) / "graph",
                    paths["pools"], paths["queries"], paths["full"],
                    paths["manifest"], paths["main"], paths["reconciliation"],
                    Path(directory) / "out")
            supervised.assert_not_called()


def test_host_cpu_includes_waited_systemctl_children():
    own = SimpleNamespace(ru_utime=1.0, ru_stime=2.0)
    children = SimpleNamespace(ru_utime=3.0, ru_stime=4.0)
    with mock.patch.object(batch.resource, "getrusage", side_effect=(own, children)):
        check(batch.host_cpu_ns() == 10 * 10**9)


def test_parity_mismatch_and_quota_overrun_stop_before_next_row():
    for kind in ("parity", "quota"):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths, _, _, _ = _mock_batch_inputs(root)
            calls = []

            def supervised(_command, **kwargs):
                calls.append(1)
                status = {"status": "attained_optimum", "exact_outcome": {"J": "2"},
                    "seed_j": "1", "certified_depth": 4, "prewarm_sha256": "p"}
                (kwargs["output_dir"] / "status.json").write_text(json.dumps(status))
                return SimpleNamespace(result="success", exit_status=0,
                    cpu_quota_percent=100,
                    cpu_usage_ns=(611 * 10**9 if kind == "quota" else 1000),
                    receipt_path=str(kwargs["output_dir"] / "receipt.json"))

            with mock.patch.object(batch, "run_supervised", side_effect=supervised):
                state = batch.run(root / "source", root / "graph", paths["pools"],
                    paths["queries"], paths["full"], paths["manifest"],
                    paths["main"], paths["reconciliation"], root / "out")
            check(calls == [1])
            check(state["stopped"] is True)
            check(state["rows"]["scan_08_n32_hier"]["status"] == (
                "verification_failed_main_parity" if kind == "parity" else
                "verification_failed_cpu_limit"))
            check(state["rows"]["pending_0"]["status"] == "verification_blocked_unrun")
            check(state["host_cpu_ns"] >= 0)
