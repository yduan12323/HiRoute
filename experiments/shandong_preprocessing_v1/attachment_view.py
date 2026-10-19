"""Attachment-only graph storage; no routing topology, weights or global index.

The canonical attachment algorithm consumes only nodes, endpoints and highway
classes. Keep their original order and int64 endpoint conversion, and preserve
IgraphRoadGraph's input checks without retaining its unused routing structures.
"""
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

NODE_COLUMNS = ['node_id', 'osm_node_id', 'lat', 'lon']
EDGE_COLUMNS = ['edge_id', 'source', 'target', 'length_m', 'travel_time_s', 'highway']


@dataclass
class AttachmentGraphView:
    nodes: pd.DataFrame
    source: np.ndarray
    target: np.ndarray

    @property
    def node_count(self):
        return len(self.nodes)


def load_attachment_view(directory, *, batch_size=65536, checkpoint=None):
    """O(V + E) retained primitive endpoints/classes, O(batch_size) edge decode.

    Costs/edge IDs are checked in projected batches and immediately discarded.
    No geometry, OSM way lists, routing igraph, weight lists or all-node KDTree
    are materialized. The existing attach_opportunities builds its own index.
    """
    if type(batch_size) is not int or batch_size < 1:
        raise ValueError('Invalid attachment edge batch size')
    directory = Path(directory)
    nodes = pd.read_parquet(directory / 'nodes.parquet', columns=NODE_COLUMNS)
    if not np.array_equal(nodes.node_id.to_numpy(), np.arange(len(nodes))):
        raise ValueError('Node IDs must be contiguous and table ordered')
    coords = nodes[['lat', 'lon']].to_numpy()
    if not np.isfinite(coords).all() or (np.abs(coords[:, 0]) > 90).any() or (np.abs(coords[:, 1]) > 180).any():
        raise ValueError('Invalid WGS84 graph coordinates')
    del coords
    if checkpoint is not None:
        checkpoint('attachment_nodes_loaded', node_count=len(nodes))
    parquet = pq.ParquetFile(directory / 'edges.parquet')
    count = parquet.metadata.num_rows
    source = np.empty(count, dtype=np.int64)
    target = np.empty(count, dtype=np.int64)
    classes = np.empty(count, dtype=object)
    offset = 0
    for batch in parquet.iter_batches(batch_size=batch_size, columns=EDGE_COLUMNS, use_threads=False):
        edges = batch.to_pandas()
        end = offset + len(edges)
        if not np.array_equal(edges.edge_id.to_numpy(), np.arange(offset, end)):
            raise ValueError('Edge IDs must be contiguous and table ordered')
        for name in ('length_m', 'travel_time_s'):
            costs = edges[name].to_numpy(dtype=float)
            if not np.isfinite(costs).all() or (costs < 0).any():
                raise ValueError('Edge costs must be finite and nonnegative')
        for name, values in (('source', source), ('target', target)):
            values[offset:end] = edges[name].to_numpy(dtype=np.int64)
            if ((values[offset:end] < 0).any() or (values[offset:end] >= len(nodes)).any()):
                raise ValueError('Invalid edge endpoint')
        classes[offset:end] = edges.highway.to_numpy()
        offset = end
        if checkpoint is not None:
            checkpoint('attachment_edges_loading', loaded_edges=offset, edge_count=count)
    if offset != count:
        raise ValueError('Parquet edge count changed')
    if checkpoint is not None:
        checkpoint('attachment_graph_loaded', node_count=len(nodes), edge_count=count)
    return AttachmentGraphView(nodes, source, target), classes
