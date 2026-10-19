"""Whole-way bounded Pyrosm parsing; exact global normalization order on disk.

No geometry is cropped or split before parsing. Each child receives original
complete ways and their reference closure; the same installed parser and same
normalizer run on each independent set. Strict source ordering makes sorted
chunk concatenation identical to the canonical stable global edge sort.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'src'), str(Path(__file__).parent)]


def native(osmium, *args):
    subprocess.run([str(osmium), *map(str, args)], check=True,
                   env={**os.environ, 'OSMIUM_POOL_THREADS': '1'})


def file_digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def run_chunk(pbf, directory, routing_path):
    # A cooperative internal-worker capability, never an environment/fixture
    # switch. Standalone CLI calls cannot open arbitrary PBFs accidentally.
    read_fd, write_fd = os.pipe()
    try:
        binding = dict(parent_pid=os.getpid(), pbf=str(pbf.resolve()),
                       pbf_sha256=file_digest(pbf), routing=str(routing_path.resolve()),
                       routing_sha256=file_digest(routing_path))
        payload = json.dumps(binding).encode()
        if len(payload) > 4096:
            raise ValueError('Chunk capability exceeds bound')
        os.write(write_fd, payload)
        os.close(write_fd)
        write_fd = None
        subprocess.run([sys.executable, str(Path(__file__).resolve()), '--chunk',
                        str(pbf), str(directory), str(routing_path), str(read_fd)],
                       check=True, pass_fds=(read_fd,))
    finally:
        os.close(read_fd)
        if write_fd is not None:
            os.close(write_fd)


def verify_chunk_capability(fd, pbf, routing_path):
    import stat
    if not stat.S_ISFIFO(os.fstat(fd).st_mode):
        raise PermissionError('Chunk worker requires inherited anonymous pipe')
    raw = os.read(fd, 4097)
    os.close(fd)
    if len(raw) > 4096:
        raise PermissionError('Invalid chunk capability size')
    value = json.loads(raw)
    expected = dict(parent_pid=os.getppid(), pbf=str(pbf.resolve()),
                    pbf_sha256=value.get('pbf_sha256'), routing=str(routing_path.resolve()),
                    routing_sha256=value.get('routing_sha256'))
    if value != expected or not all(isinstance(value.get(k), str) and len(value[k]) == 64
                                    for k in ('pbf_sha256', 'routing_sha256')):
        raise PermissionError('Chunk parent/path capability mismatch')
    if file_digest(pbf) != value['pbf_sha256'] or file_digest(routing_path) != value['routing_sha256']:
        raise PermissionError('Chunk content capability mismatch')


def partition_ids(roads, directory, max_way_refs, max_ways):
    """Streaming O(1) bookkeeping; bound both references and number of ways."""
    import osmium
    if type(max_way_refs) is not int or max_way_refs < 2 or type(max_ways) is not int or max_ways < 1:
        raise ValueError('Invalid whole-way partition bounds')
    paths = []
    class Scan(osmium.SimpleHandler):
        last_node = last_way = 0
        refs = ways = 0
        stream = None
        def node(self, node):
            if node.id <= self.last_node:
                raise ValueError('Input node IDs must be positive, unique and strictly ordered')
            self.last_node = node.id
        def relation(self, relation):
            raise ValueError('Filtered highway input must contain only nodes and ways')
        def way(self, way):
            if way.id <= self.last_way:
                raise ValueError('Input way IDs must be positive, unique and strictly ordered')
            self.last_way = way.id
            count = len(way.nodes)
            if count > max_way_refs:
                raise ValueError('Single complete way exceeds frozen reference bound')
            if self.stream is None or self.refs + count > max_way_refs or self.ways >= max_ways:
                if self.stream is not None:
                    self.stream.close()
                path = directory / f'ways-{len(paths):06d}.ids'
                paths.append(path)
                self.stream = path.open('x')
                self.refs = self.ways = 0
            self.stream.write(f'w{way.id}\n')
            self.refs += count
            self.ways += 1
    scan = Scan()
    try:
        scan.apply_file(str(roads), locations=False)
    finally:
        if scan.stream is not None:
            scan.stream.close()
    if not paths:
        raise ValueError('No driving edges survive preprocessing')
    return paths


def parse_chunk(pbf, directory, routing_path):
    """Fresh process owns all parser allocation; no heap survives into next chunk."""
    import pandas as pd
    from pyrosm import OSM
    from graph.preprocessing import ATTRIBUTES, normalize_network
    from graph.raw_way_policy import read_raw_way_policy
    if importlib.metadata.version('pyrosm') != '0.13.1':
        raise ValueError('Whole-way path requires pinned pyrosm 0.13.1')
    routing = json.loads(routing_path.read_text())
    raw = read_raw_way_policy(pbf)
    nodes, edges = OSM(str(pbf), engine='out_of_core', workers=1).get_network(
        network_type='driving', nodes=True, extra_attributes=ATTRIBUTES)
    if edges is None:
        if nodes is not None and len(nodes):
            raise ValueError('Parser returned nodes without edges')
        (directory / 'audit.json').write_text(json.dumps({}))
        return
    if nodes is None or not nodes.id.is_unique:
        raise ValueError('Missing or duplicate parser node IDs')
    nodes[['id', 'lat', 'lon']].to_parquet(directory / 'parser_nodes.parquet', index=False)
    evidence = {}
    nodes, edges, audit = normalize_network(nodes, edges, routing, raw_way_policy=raw, allow_empty=True, policy_schema_evidence=evidence)
    (directory / 'policy_schema.json').write_text(json.dumps(evidence))
    if len(edges):
        nodes.to_parquet(directory / 'nodes.parquet', index=False)
        edges.to_parquet(directory / 'edges.parquet', index=False)
    (directory / 'audit.json').write_text(json.dumps(audit))


def build_partitioned_graph(roads: Path, scratch: Path, out: Path, routing: dict,
                            osmium: str, report: Path, *, max_way_refs=50000, max_ways=10000):
    import numpy as np
    import pandas as pd
    import pyarrow as pa
    import pyarrow.parquet as pq
    from bounded_io import DENSE_FORMAT, progress
    directory = scratch / 'whole-way-partitions'
    directory.mkdir(mode=0o700)
    routing_path = directory / 'routing.json'
    routing_path.write_text(json.dumps(routing))
    paths = partition_ids(roads, directory, max_way_refs, max_ways)
    db = sqlite3.connect(directory / 'nodes.sqlite')
    db.execute('PRAGMA cache_size=-16384')
    db.execute('PRAGMA temp_store=FILE')
    db.execute('CREATE TABLE nodes (id INTEGER PRIMARY KEY, lat REAL NOT NULL, lon REAL NOT NULL, used INTEGER NOT NULL DEFAULT 0)')
    # Reject conflicts before ON CONFLICT merges shared nodes across partitions.
    db.execute("CREATE TRIGGER coordinates BEFORE INSERT ON nodes WHEN EXISTS (SELECT 1 FROM nodes WHERE id=NEW.id AND (lat != NEW.lat OR lon != NEW.lon)) BEGIN SELECT RAISE(ABORT, 'Conflicting shared node coordinates'); END")
    audit = Counter(parsed_segments=0, excluded_street_lamp=0, excluded_street_lamp_ways=0,
                    excluded_closed_shelter_contour=0, excluded_closed_shelter_contour_ways=0)
    edge_paths = []
    selected_types = {}
    fallback_types = {}
    columns = None
    policy_nonnull_types = {}
    excluded_records = 0
    try:
        for i, ids in enumerate(paths):
            part = directory / f'part-{i:06d}'
            part.mkdir()
            pbf = part / 'input.pbf'
            native(osmium, 'getid', roads, '-i', ids, '-r', '-f', DENSE_FORMAT, '-o', pbf)
            native(osmium, 'check-refs', pbf)
            progress(report, 'partition_parser_started', partition=i, partitions=len(paths),
                     max_way_refs=max_way_refs, max_ways=max_ways)
            run_chunk(pbf, part, routing_path)
            chunk_audit = json.loads((part / 'audit.json').read_text())
            if (part / 'policy_schema.json').exists():
                evidence = json.loads((part / 'policy_schema.json').read_text())
                excluded_records += evidence.get('excluded_records', 0)
                for name, dtype in evidence.get('nonnull_types', {}).items():
                    if name != 'excluded_reason':
                        previous = policy_nonnull_types.setdefault(name, dtype)
                        if previous != dtype:
                            raise ValueError('Inconsistent policy dtype: ' + name)
            audit.update({k: v for k, v in chunk_audit.items() if k not in ('nodes', 'directed_edges', 'unused_parser_nodes')})
            if (part / 'parser_nodes.parquet').exists():
                for batch in pq.ParquetFile(part / 'parser_nodes.parquet').iter_batches(batch_size=16384):
                    data = batch.to_pydict()
                    db.executemany('INSERT INTO nodes(id,lat,lon) VALUES (?,?,?) ON CONFLICT(id) DO NOTHING', zip(data['id'], data['lat'], data['lon']))
            if (part / 'edges.parquet').exists():
                for batch in pq.ParquetFile(part / 'nodes.parquet').iter_batches(batch_size=16384):
                    db.executemany('UPDATE nodes SET used=1 WHERE id=?', ((x,) for x in batch.column('osm_node_id').to_pylist()))
                path = part / 'edges.parquet'
                edge_paths.append(path)
                for batch in pq.ParquetFile(path).iter_batches(batch_size=16384):
                    if columns is None:
                        columns = batch.schema.names
                    if columns != batch.schema.names:
                        raise ValueError('Inconsistent normalized edge columns')
                    for field, array in zip(batch.schema, batch.columns):
                        fallback_types.setdefault(field.name, field.type)
                        if array.null_count < len(array):
                            old = selected_types.setdefault(field.name, field.type)
                            if old != field.type:
                                raise ValueError('Inconsistent non-null normalized column type: ' + field.name)
            db.commit()
            # Reference closure and parser scratch no longer needed; retain normalized spools.
            pbf.unlink()
            progress(report, 'partition_complete', partition=i, partitions=len(paths),
                     parsed_segments=audit['parsed_segments'])
        if not edge_paths:
            raise ValueError('No driving edges survive preprocessing')
        used = np.fromiter((r[0] for r in db.execute('SELECT id FROM nodes WHERE used=1 ORDER BY id')), dtype=np.int64)
        node_schema = pa.Schema.from_pandas(pd.DataFrame({
            'node_id': pd.Series(dtype='int64'), 'osm_node_id': pd.Series(dtype='int64'),
            'lat': pd.Series(dtype='float64'), 'lon': pd.Series(dtype='float64')}), preserve_index=False)
        offset = 0
        with pq.ParquetWriter(out / 'nodes.parquet', node_schema, compression='zstd') as writer:
            cursor = db.execute('SELECT id,lat,lon FROM nodes WHERE used=1 ORDER BY id')
            while rows := cursor.fetchmany(16384):
                frame = pd.DataFrame.from_records(rows, columns=['osm_node_id', 'lat', 'lon'])
                frame.insert(0, 'node_id', np.arange(offset, offset + len(rows), dtype=np.int64))
                writer.write_table(pa.Table.from_pandas(frame, schema=node_schema, preserve_index=False))
                offset += len(rows)
        # All-null tag columns preserve canonical float dtype; any non-null string
        # selects the global string dtype just as pandas global construction does.
        types = {name: selected_types.get(name, fallback_types[name]) for name in columns}
        from graph.preprocessing import ATTRIBUTES
        policy_columns = set(ATTRIBUTES) | {'speed_kph', 'maxspeed_used', 'posted_maxspeed_kph',
                                          'speed_source', 'oneway_effective', 'access_effective'}
        for name in policy_columns:
            if name in policy_nonnull_types:
                dtype = policy_nonnull_types[name]
                types[name] = (pa.large_string() if dtype in ('str', 'string') else
                               pa.float64() if dtype == 'float64' else
                               pa.int64() if dtype == 'int64' else types[name])
            else:
                types[name] = pa.float64() if excluded_records else pa.null()

        dtypes = {name: ('str' if pa.types.is_large_string(t) or pa.types.is_string(t) else
                         'object' if pa.types.is_binary(t) or pa.types.is_null(t) else
                         'int64' if pa.types.is_integer(t) else 'float64') for name, t in types.items()}
        schema = pa.Schema.from_pandas(pd.DataFrame({name: pd.Series(dtype=dtypes[name]) for name in columns}), preserve_index=False)
        # Empty object series infers null; retain the observed binary geometry type.
        schema = pa.schema([pa.field(name, types[name]) for name in columns], metadata=schema.metadata)
        offset = 0
        with pq.ParquetWriter(out / 'edges.parquet', schema, compression='zstd') as writer:
            for path in edge_paths:
                for batch in pq.ParquetFile(path).iter_batches(batch_size=16384):
                    table = pa.Table.from_batches([batch]).cast(schema)
                    for name in ('source', 'target'):
                        ids = table[name + '_osm'].to_numpy()
                        indices = np.searchsorted(used, ids)
                        if (indices >= len(used)).any() or not np.array_equal(used[indices], ids):
                            raise ValueError('Missing global node endpoint')
                        table = table.set_column(schema.get_field_index(name), schema.field(name), pa.array(indices))
                    table = table.set_column(0, schema.field('edge_id'), pa.array(np.arange(offset, offset + len(batch), dtype=np.int64)))
                    writer.write_table(table)
                    offset += len(batch)
        audit['nodes'] = len(used)
        audit['directed_edges'] = offset
        audit['unused_parser_nodes'] = db.execute('SELECT COUNT(*) FROM nodes').fetchone()[0] - len(used)
        progress(report, 'normalization_complete', nodes=len(used), edges=offset, partitions=len(paths))
        return dict(audit)
    finally:
        db.close()


if __name__ == '__main__':
    if len(sys.argv) != 6 or sys.argv[1] != '--chunk':
        raise SystemExit('Internal whole-way parser worker only')
    verify_chunk_capability(int(sys.argv[5]), Path(sys.argv[2]), Path(sys.argv[4]))
    parse_chunk(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))
