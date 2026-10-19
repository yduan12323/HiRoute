"""Read-only Git recovery. Writes private output outside the publication tree.

Run: python -m experiments.exposure_recovery_v1.build --repository REPO --output DIR
No graph processing, route computation, OD selection or optimizer calls occur.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from experiments.m6h_selection_v1.rules import digest, endpoint, graph_identity, RECOVERY_SCHEMA


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args])


def sha(data):
    return hashlib.sha256(data).hexdigest()


def walk_endpoints(value, location='$'):
    if isinstance(value, dict):
        if {'site_id', 'access_node', 'lat', 'lon'} <= value.keys():
            yield location, endpoint(value)
        for key, child in sorted(value.items()):
            yield from walk_endpoints(child, location + '.' + key)
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from walk_endpoints(child, f'{location}[{i}]')


def build(repo, config, external_root=None):
    revision = git(repo, 'rev-parse', config['source_revision'] + '^{commit}').decode().strip()
    inventory_revisions = [git(repo, 'rev-parse', ref + '^{commit}').decode().strip()
                           for ref in config.get('inventory_revisions', [revision])]
    objects = git(repo, 'rev-list', '--objects', *inventory_revisions).decode().splitlines()
    inventory = []
    # One batch process avoids thousands of subprocess starts; raw blobs are
    # length-delimited by Git, never decoded to inspect their framing.
    paths = {line.partition(' ')[0]: line.partition(' ')[2] for line in objects}
    batch = subprocess.Popen(['git', '-C', str(repo), 'cat-file', '--batch'],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        for oid, path in paths.items():
            batch.stdin.write((oid + '\n').encode()); batch.stdin.flush()
            header = batch.stdout.readline().decode().split()
            if len(header) != 3 or header[0] != oid:
                raise ValueError('invalid Git batch object header')
            size = int(header[2]); raw = batch.stdout.read(size)
            if len(raw) != size or batch.stdout.read(1) != b'\n':
                raise ValueError('truncated Git batch object')
            if header[1] == 'blob':
                inventory.append(dict(git_oid=oid, representative_path=path, sha256=sha(raw),
                                      size_bytes=len(raw), status='inventoried_not_endpoint_resolved'))
    finally:
        batch.stdin.close(); batch.stdout.close()
        if batch.wait() != 0:
            raise ValueError('Git batch failed')
    inventory.sort(key=lambda r: r['git_oid'])
    sources, loaded = [], {}
    for item in config['sources']:
        raw = git(repo, 'show', revision + ':' + item['path'])
        if sha(raw) != item['sha256']:
            raise ValueError('source hash mismatch: ' + item['path'])
        sid = item['path'] + '@' + item['sha256']
        sources.append(dict(source_id=sid, path=item['path'], sha256=sha(raw), commit=revision))
        loaded[item['path']] = (sid, json.loads(raw) if item['path'].endswith('.json') else None)
    partitions = [(sid, data) for path, (sid, data) in loaded.items() if '/grid14_distance_p' in path]
    identities = {digest(dict(nodes_sha256=d['graph_nodes_sha256'], edges_sha256=d['graph_edges_sha256'])):
                  graph_identity(dict(nodes_sha256=d['graph_nodes_sha256'], edges_sha256=d['graph_edges_sha256']))
                  for _, d in partitions}
    if len(identities) != 1:
        raise ValueError('partition graph identities disagree')
    identity = next(iter(identities.values()))
    catalog, inspected, records = {}, [], []
    for path, (sid, data) in loaded.items():
        if '/geographic_screen_' not in path:
            continue
        if data['nodes_sha256'] != identity['nodes_sha256']:
            raise ValueError('screen graph identity mismatch')
        for pointer, ep in walk_endpoints(data):
            if ep['site_id'] in catalog and catalog[ep['site_id']] != ep:
                raise ValueError('conflicting endpoint in screens')
            catalog[ep['site_id']] = ep
            inspected.append(dict(source_id=sid, reason='inspected_geographic_screen_endpoint',
                                  source_pointer=pointer, coordinate_role='graph_access_node', graph_identity=identity, endpoint=ep))
    for sid, data in partitions:
        screen_path = next(p for p in loaded if p.endswith('geographic_screen_v5_grid14.json'))
        if data['geographic_screen_sha256'] != next(s['sha256'] for s in sources if s['path'] == screen_path):
            raise ValueError('partition screen binding mismatch')
        if data['pair_count'] != len(data['pairs']):
            raise ValueError('partition pair count mismatch')
        for i, pair in enumerate(data['pairs']):
            a, b = catalog[pair['origin_site']], catalog[pair['destination_site']]
            if (a['access_node'], b['access_node']) != (pair['origin_anchor'], pair['destination_anchor']):
                raise ValueError('partition anchor mismatch')
            records.append(dict(source_id=sid, reason='all_screened_pairs_including_rejected_and_unreachable',
                                source_pointer=f'$.pairs[{i}]', coordinate_role='graph_access_node', graph_identity=identity, origin=a, destination=b))
    anchor_only = []
    if config.get('external_inputs'):
        if external_root is None:
            raise ValueError('authenticated external input directory required')
        import pandas as pd
        manifest = loaded[config['external_input_manifest']][1]
        declared = {f['path']: f['expected_sha256'] for f in manifest['files']}
        external = {}
        for item in config['external_inputs']:
            raw = (Path(external_root) / item['filename']).read_bytes()
            if sha(raw) != item['sha256'] or declared.get(item['path']) != item['sha256']:
                raise ValueError('external source hash mismatch')
            sid = item['path'] + '@' + item['sha256']
            sources.append(dict(source_id=sid, path=item['path'], sha256=sha(raw),
                                authentication_manifest=config['external_input_manifest']))
            external[item['filename']] = (sid, raw)
        import io
        metadata = json.loads(external['metadata.json'][1])
        if {k: metadata['files'][f]['sha256'] for k,f in
                [('nodes_sha256','nodes.parquet'),('edges_sha256','edges.parquet')]} != identity:
            raise ValueError('external graph identity mismatch')
        sid, raw = external['od_remapping.parquet']
        dev = pd.read_parquet(io.BytesIO(raw))
        if len(dev) != 30:
            raise ValueError('original DEV count mismatch')
        for i, row in dev.iterrows():
            if (row['graph_nodes_sha256'],row['graph_edges_sha256']) != (identity['nodes_sha256'],identity['edges_sha256']):
                raise ValueError('DEV graph identity mismatch')
            anchor_only.append(dict(source_id=sid, reason='original_dev_pair_coordinates_unavailable',
                source_pointer=f'row[{i}]', graph_identity=identity,
                origin_anchor=int(row['origin_node']), destination_anchor=int(row['destination_node'])))
        sid, raw = external['stop_sites.parquet']
        for i, row in pd.read_parquet(io.BytesIO(raw)).iterrows():
            ep = endpoint(dict(site_id=row['site_id'],lat=row['lat'],lon=row['lon'],
                          access_node=None if pd.isna(row['access_node']) else int(row['access_node'])))
            inspected.append(dict(source_id=sid, reason='conservative_full_historical_catalog_exclusion',
                                  source_pointer=f'row[{i}]', coordinate_role='site_geometry_not_access_node', graph_identity=identity, endpoint=ep))
            if ep['site_id'] in catalog and catalog[ep['site_id']]['access_node'] != ep['access_node']:
                raise ValueError('screen versus historical catalog anchor mismatch')
            catalog[ep['site_id']] = ep
    recovered_hashes = {s['sha256'] for s in sources if '/geographic_screen_' in s['path'] or '/grid14_distance_p' in s['path']}
    for row in inventory:
        if row['sha256'] in recovered_hashes:
            row['status'] = 'supported_screen_extraction'
    registry = dict(schema=RECOVERY_SCHEMA, strict_independent_holdout_claim=False,
        coverage=dict(status='incomplete_recovery', known_missing_artifacts=config['known_missing_artifacts']),
        provenance=dict(source_commit=revision, inventory_commits=inventory_revisions, config_sha256=digest(config),
                        builder_sha256=sha(Path(__file__).read_bytes()), inventory_sha256=digest(inventory)),
        sources=sources, records=records, inspected_endpoints=inspected, anchor_only_exposures=anchor_only,
        proposal_history=[dict(origin=a, destination=b, status='names_only_coordinates_unknown') for a,b in
                          [('Dali','Tianjin'), ('Chengdu','Shanghai'), ('Lhasa','Zhengzhou')]],
        counts=dict(pair_occurrences=len(records), anchor_only_pair_occurrences=len(anchor_only), inspected_endpoint_occurrences=len(inspected),
                    unique_site_identities_with_coordinates=len(catalog), inventoried_git_blobs=len(inventory)))
    return registry, inventory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', required=True, type=Path)
    parser.add_argument('--config', type=Path, default=Path(__file__).with_name('config.json'))
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--external-inputs', type=Path)
    args = parser.parse_args()
    publication = Path(__file__).resolve().parents[2]
    if args.output.resolve().is_relative_to(publication):
        parser.error('raw recovery output must be outside the publication tree')
    registry, inventory = build(args.repository, json.loads(args.config.read_text()), args.external_inputs)
    args.output.mkdir(parents=True, exist_ok=True)
    for name, value in [('registry',registry), ('inventory',inventory)]:
        (args.output / (name + '.json')).write_text(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False))
    receipt = dict(schema=registry['schema'], registry_sha256=digest(registry),
                   gap_list_sha256=digest(registry['coverage']['known_missing_artifacts']),
                   inventory_sha256=digest(inventory), counts=registry['counts'])
    (args.output / 'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))


if __name__ == '__main__':
    main()
