"""Regression tests for the opt-in, bounded Shandong site attachment path."""
import multiprocessing as mp
import os
import time
from types import SimpleNamespace

import pytest

import hiroute.data.shandong_spatial as spatial


def _nodes():
    return [
        {"node_id": str(i + 1), "lat": 0.0, "lon": i * 0.01}
        for i in range(8)
    ]


def _sites():
    return [
        SimpleNamespace(site_id=f"s{i}", lat=0.0, lon=(i % 7) * 0.01 + 0.001)
        for i in range(9)
    ]


@pytest.mark.skipif("fork" not in mp.get_all_start_methods(), reason="requires Linux fork")
def test_parallel_attachment_matches_serial_and_reports_effective_workers():
    sites = _sites()
    nodes = _nodes()
    expected = spatial.snap_sites_wgs84(
        sites, nodes, max_distance_m=100_000, candidate_count=4
    )
    profile = []
    actual = spatial.snap_sites_wgs84_parallel(
        sites, nodes, max_distance_m=100_000, candidate_count=4, workers=3,
        max_group_rss_bytes=8 * 1024**3, memory_margin_bytes=256 * 1024**2,
        _profile=profile,
    )
    assert actual == expected
    assert profile[0]["mode"] == "fork"
    assert profile[0]["requested_workers"] == 3
    assert profile[0]["effective_workers"] == 3
    assert len(profile[0]["worker_records"]) == 3
    assert profile[0]["child_cpu_seconds"] >= 0


def test_parallel_merge_preserves_last_duplicate_site_id_like_serial():
    sites = [
        SimpleNamespace(site_id="duplicate", lat=0.0, lon=0.0),
        SimpleNamespace(site_id="other", lat=0.0, lon=0.07),
        SimpleNamespace(site_id="duplicate", lat=0.0, lon=0.07),
    ]
    nodes = _nodes()
    expected = spatial.snap_sites_wgs84(
        sites, nodes, max_distance_m=100_000, candidate_count=4
    )
    actual = spatial.snap_sites_wgs84_parallel(
        sites, nodes, max_distance_m=100_000, candidate_count=4, workers=3,
        max_group_rss_bytes=8 * 1024**3, memory_margin_bytes=256 * 1024**2,
    )
    assert actual == expected
    assert actual["duplicate"]["node_id"] == "8"


def test_parallel_falls_back_to_serial_for_lazy_iterable():
    consumed = []
    def lazy_sites():
        for site in _sites():
            consumed.append(site.site_id)
            yield site

    profile = []
    actual = spatial.snap_sites_wgs84_parallel(
        lazy_sites(), _nodes(), max_distance_m=100_000, candidate_count=4,
        workers=3, _profile=profile,
    )
    expected = spatial.snap_sites_wgs84(
        _sites(), _nodes(), max_distance_m=100_000, candidate_count=4
    )
    assert actual == expected
    assert len(consumed) == 9
    assert profile[0]["effective_workers"] == 1
    assert profile[0]["mode"] == "serial_nonmaterialized_input"


def test_topk_keeps_stable_input_order_for_duplicate_keys():
    first = {"node_id": "7", "marker": "first"}
    second = {"node_id": "7", "marker": "second"}
    third = {"node_id": "7", "marker": "third"}
    indexed = [((1.0, 0.0, 0.0), first),
               ((1.0, 0.0, 0.0), second),
               ((1.0, 0.0, 0.0), third)]
    selected = spatial._prefilter_site_nodes(
        indexed, (0.0, 0.0, 0.0), candidate_count=2, finite_index=True
    )
    assert selected[0][1] is first
    assert selected[1][1] is second


@pytest.mark.skipif("fork" not in mp.get_all_start_methods(), reason="requires Linux fork")
def test_parallel_raises_earliest_input_block_exception_not_fastest(monkeypatch):
    def fail_by_block(sites, *args, **kwargs):
        site_id = sites[0].site_id
        if site_id == "first":
            time.sleep(0.5)
            raise ValueError("first input block")
        raise LookupError("later input block")

    monkeypatch.setattr(spatial, "_snap_indexed_sites", fail_by_block)
    sites = [
        SimpleNamespace(site_id="first", lat=0.0, lon=0.0),
        SimpleNamespace(site_id="later", lat=0.0, lon=0.0),
    ]
    profile = []
    with pytest.raises(ValueError, match="first input block"):
        spatial.snap_sites_wgs84_parallel(
            sites, _nodes(), max_distance_m=100_000, candidate_count=4,
            workers=2, max_group_rss_bytes=8 * 1024**3,
            memory_margin_bytes=256 * 1024**2, _profile=profile,
        )
    finishes = [row["finished_at"] for row in profile[0]["worker_records"]]
    assert finishes[1] < finishes[0]


@pytest.mark.skipif("fork" not in mp.get_all_start_methods(), reason="requires Linux fork")
def test_unexpected_worker_exit_is_reaped_and_reported(monkeypatch):
    def exit_worker(sites, *args, **kwargs):
        if sites[0].site_id == "exit":
            os._exit(17)
        return {}

    monkeypatch.setattr(spatial, "_snap_indexed_sites", exit_worker)
    sites = [
        SimpleNamespace(site_id="exit", lat=0.0, lon=0.0),
        SimpleNamespace(site_id="ok", lat=0.0, lon=0.0),
    ]
    with pytest.raises(ChildProcessError, match="exited unexpectedly"):
        spatial.snap_sites_wgs84_parallel(
            sites, _nodes(), max_distance_m=100_000, candidate_count=4,
            workers=2, max_group_rss_bytes=8 * 1024**3,
            memory_margin_bytes=256 * 1024**2,
        )
    assert not mp.active_children()
