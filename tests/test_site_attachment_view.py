"""Tiny independent canonical-oracle checks; no provincial input required."""
import numpy as np
import pandas as pd
import pytest
from graph.road_graph import IgraphRoadGraph
from opportunity.attachment import attach_opportunities
from opportunity.models import Opportunity, OpportunityId, Provenance
from experiments.shandong_preprocessing_v1.attachment_view import load_attachment_view, NODE_COLUMNS, EDGE_COLUMNS


def tables():
    nodes = pd.DataFrame(dict(node_id=range(6), osm_node_id=[10, 20, 30, 40, 50, 60],
                              lat=[36.] * 6, lon=[118., 118., 118.001, 118.002, 118.003, 119.]))
    edges = pd.DataFrame(dict(edge_id=range(6), source=[0, 1, 2, 2, 3, 4], target=[1, 0, 0, 3, 4, 3],
                              length_m=[0., 0., 90., 90., 90., 90.], travel_time_s=[0., 0., 9., 9., 9., 9.],
                              highway=['residential'] * 4 + ['motorway'] * 2,
                              geometry_wkb=[b'not decoded'] * 6))
    return nodes, edges


def store(tmp_path, nodes, edges):
    nodes.to_parquet(tmp_path / 'nodes.parquet', index=False)
    edges.to_parquet(tmp_path / 'edges.parquet', index=False, row_group_size=2)


def opportunities():
    provenance = Provenance(('fixture',), '2026-01-01', 'node')
    return [Opportunity(OpportunityId('node', i + 1), lat, lon, frozenset({'charge'}), None, {}, provenance)
            for i, (lat, lon) in enumerate([(36., 118.), (36., 118.001), (37., 120.)])]


@pytest.mark.parametrize('require_both', [True, False])
@pytest.mark.parametrize('candidate_count', [1, 2, 8])
@pytest.mark.parametrize('excluded', [[], ['motorway'], ['motorway', 'residential']])
def test_canonical_exact_equivalence(tmp_path, require_both, candidate_count, excluded):
    nodes, edges = tables()
    store(tmp_path, nodes, edges)
    checkpoints = []
    view, classes = load_attachment_view(tmp_path, batch_size=2,
                                        checkpoint=lambda stage, **kw: checkpoints.append((stage, kw)))
    canonical = IgraphRoadGraph(nodes, edges)
    cfg = dict(default_threshold_m=100., candidate_count=candidate_count, excluded_highway=excluded,
               require_in_and_out_edges=require_both)
    ops = opportunities()
    expected = attach_opportunities(ops, canonical, edges.highway.to_numpy(), cfg)
    actual = attach_opportunities(ops, view, classes, cfg)
    assert actual == expected  # Includes exact distances, status, input order and selected IDs.
    assert view.source.dtype == view.target.dtype == np.dtype('int64')
    pd.testing.assert_frame_equal(view.nodes, canonical.nodes)
    assert not hasattr(view, '_graph') and not hasattr(view, '_tree') and not hasattr(view, 'weights')
    assert [kw['loaded_edges'] for stage, kw in checkpoints if stage == 'attachment_edges_loading'] == [2, 4, 6]


def test_projected_bounded_reads(tmp_path, monkeypatch):
    import experiments.shandong_preprocessing_v1.attachment_view as module
    nodes, edges = tables()
    store(tmp_path, nodes, edges)
    original_read = module.pd.read_parquet
    original_parquet = module.pq.ParquetFile
    calls = []
    def read(path, **kw):
        calls.append(('nodes', kw))
        return original_read(path, **kw)
    class Parquet:
        def __init__(self, path):
            self.inner = original_parquet(path)
            self.metadata = self.inner.metadata
        def iter_batches(self, **kw):
            calls.append(('edges', kw))
            for batch in self.inner.iter_batches(**kw):
                assert len(batch) <= 2
                yield batch
    monkeypatch.setattr(module.pd, 'read_parquet', read)
    monkeypatch.setattr(module.pq, 'ParquetFile', Parquet)
    load_attachment_view(tmp_path, batch_size=2)
    assert calls == [('nodes', {'columns': NODE_COLUMNS}),
                     ('edges', {'batch_size': 2, 'columns': EDGE_COLUMNS, 'use_threads': False})]


@pytest.mark.parametrize('table,column,index,value', [
    ('nodes', 'node_id', 3, 9), ('nodes', 'lat', 3, 91.), ('nodes', 'lon', 3, np.nan),
    ('edges', 'edge_id', 3, 9), ('edges', 'source', 3, -1), ('edges', 'target', 3, 6),
    ('edges', 'length_m', 3, -1.), ('edges', 'travel_time_s', 3, np.inf)])
def test_preserves_canonical_rejections(tmp_path, table, column, index, value):
    nodes, edges = tables()
    (nodes if table == 'nodes' else edges).loc[index, column] = value
    store(tmp_path, nodes, edges)
    with pytest.raises(ValueError):
        IgraphRoadGraph(nodes, edges)
    with pytest.raises(ValueError):
        load_attachment_view(tmp_path, batch_size=2)


def test_empty_edges(tmp_path):
    nodes, edges = tables()
    store(tmp_path, nodes, edges.iloc[:0])
    view, classes = load_attachment_view(tmp_path, batch_size=2)
    assert view.node_count == 6 and len(view.source) == len(view.target) == len(classes) == 0
    cfg = dict(default_threshold_m=100., candidate_count=3, excluded_highway=[], require_in_and_out_edges=True)
    assert attach_opportunities(opportunities(), view, classes, cfg) == attach_opportunities(
        opportunities(), IgraphRoadGraph(nodes, edges.iloc[:0]), edges.iloc[:0].highway.to_numpy(), cfg)


def test_site_artifact_bytes_and_reorder(tmp_path):
    from stopplan4r.sites import build_sites
    nodes, edges = tables()
    store(tmp_path, nodes, edges)
    view, classes = load_attachment_view(tmp_path, batch_size=2)
    cfg = dict(default_threshold_m=100., candidate_count=8, excluded_highway=['motorway'],
               require_in_and_out_edges=True)
    ops = opportunities()
    raw = pd.DataFrame([dict(osm_type=o.identity.osm_type, osm_id=o.identity.osm_id,
                             lat=o.lat, lon=o.lon, capabilities=['charge', 'meal', 'toilets', 'sleep'],
                             original_tags='{}', geometry_type='Point', geometry_method='node',
                             source_datasets=['fixture'], snapshot_timestamp='2026-01-01') for o in ops])
    def attachment_frame(graph, road_classes):
        attached = attach_opportunities(ops, graph, road_classes, cfg)
        assert attached[0].access_node == 0  # Co-located distance tie resolves to graph identity.
        return pd.DataFrame([dict(osm_type=o.identity.osm_type, osm_id=o.identity.osm_id,
                                  access_node=o.access_node, access_osm_node_id=o.access_osm_node_id,
                                  access_distance_m=o.access_distance_m, attachment_status=o.attachment_status)
                             for o in attached])
    expected = attachment_frame(IgraphRoadGraph(nodes, edges), edges.highway.to_numpy())
    actual = attachment_frame(view, classes)
    canonical_sites, canonical_local, _ = build_sites(raw, expected)
    sites, local, _ = build_sites(raw, actual)
    rebuilt, rebuilt_local, _ = build_sites(raw.iloc[::-1], actual.iloc[::-1])
    for name, original, candidates in [('attachments', expected, [actual]),
                                      ('stop_sites', canonical_sites, [sites, rebuilt]),
                                      ('local_support', canonical_local, [local, rebuilt_local])]:
        first = tmp_path / (name + '-oracle.parquet')
        original.to_parquet(first, index=False, compression='zstd')
        for i, candidate in enumerate(candidates):
            pd.testing.assert_frame_equal(original, candidate)
            target = tmp_path / (name + str(i) + '.parquet')
            candidate.to_parquet(target, index=False, compression='zstd')
            assert target.read_bytes() == first.read_bytes()
