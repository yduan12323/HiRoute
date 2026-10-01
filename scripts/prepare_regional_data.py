"""Dated acquisition, deterministic geographic extraction and safe Pyrosm calibration."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
import pandas as pd
from pyproj import Transformer
import shapely
import yaml

from _common import ROOT, configs, read_config, sha256, verified_dataset
from _regional_common import (available_memory_bytes, measured_command, polygon_bytes,
                              region_polygon)
from download_data import snapshot_timestamp
from envelope.boundary import read_poly


def immutable_install(temporary, destination):
    """Link exclusively so another run cannot replace a frozen raw artifact."""
    os.link(temporary, destination)
    destination.chmod(0o444)
    temporary.unlink()


def acquire_sources(config, resolve=None):
    directory = ROOT / config['source_dir']
    directory.mkdir(parents=True, exist_ok=True)
    manifest = ROOT / config['results_dir'] / 'sources.json'
    pinned = json.loads(manifest.read_text()) if manifest.exists() else None
    def acquire(source):
        url = 'https://download.geofabrik.de/' + source
        if 'latest' in url:
            raise ValueError('A dated source is required')
        destination = directory / Path(source).name
        frozen = next((s for s in pinned['sources'] if s['url'] == url), None) if pinned else None
        if destination.exists():
            if frozen is None or sha256(destination) != frozen['sha256']:
                raise ValueError(f'Unverified existing source {destination}')
            return frozen
        partial = destination.with_suffix('.partial')
        transport = ['--noproxy','*','--resolve', 'download.geofabrik.de:443:'+resolve] if resolve else []
        command = ['curl', *transport, '--fail', '--location', '--retry', '8', '--retry-all-errors',
                        '--connect-timeout', '20', '--max-time', '1800', '--speed-time', '90',
                        '--speed-limit', '1024', '--continue-at', '-', '--output', str(partial), url]
        # A completed, not-yet-verified temporary download may be adopted only after
        # exact size, publisher checksum, pinned SHA256 and snapshot checks below.
        transferred = not partial.exists() or partial.stat().st_size != config['source_sizes_bytes'][destination.name]
        if transferred:
            subprocess.run(command, check=True)
        if partial.stat().st_size != config['source_sizes_bytes'][destination.name]:
            raise ValueError('Dated source size differs from the pre-download inspection')
        md5_file = directory / (destination.name + '.md5')
        subprocess.run(['curl', *transport, '--fail', '--location', '--retry', '8', '--retry-all-errors',
                        '--connect-timeout', '20', '--max-time', '120', '-o', str(md5_file), url + '.md5'], check=True)
        md5 = hashlib.md5()
        with partial.open('rb') as stream:
            for block in iter(lambda: stream.read(8 * 2**20), b''):
                md5.update(block)
        expected_md5 = md5_file.read_text().split()[0]
        if md5.hexdigest() != expected_md5:
            raise ValueError(f'Publisher MD5 mismatch {source}')
        digest = sha256(partial)
        if frozen and digest != frozen['sha256']:
            raise ValueError('Pinned source SHA256 mismatch')
        stamp = snapshot_timestamp(partial)
        if stamp != config['snapshot_timestamp']:
            raise ValueError(f'Cannot merge a different snapshot: {source} {stamp}')
        record = {'url': url, 'path': str(destination.relative_to(ROOT)), 'sha256': digest,
                  'size_bytes': partial.stat().st_size, 'snapshot_timestamp': stamp,
                  'publisher_md5': expected_md5, 'acquired_at_utc': datetime.now(timezone.utc).isoformat()}
        record['download_command'] = command if transferred else None
        record['acquisition_method'] = 'curl transfer' if transferred else 'complete temporary artifact adopted after all checks'
        immutable_install(partial, destination)
        # Per-source record makes interrupted multi-source acquisition recoverable.
        destination.with_suffix('.json').write_text(json.dumps(record, indent=2) + '\n')
        print(f'Frozen {source}: {digest}', flush=True)
        return frozen or record
    # Recover exclusively frozen, checksum-verified sources after a partial first run.
    if pinned is None:
        recovered = [json.loads(p.read_text()) for p in directory.glob('*.json')]
        if recovered:
            pinned = {'sources': recovered}
    # Sequential transfers avoid starvation on the measured workstation connection.
    records = [acquire(source) for source in config['sources']]
    data, _ = configs()
    si = verified_dataset(data)
    records.append({'url': si['source_url'], 'path': str(config['slovenia_source']),
                    'sha256': si['sha256'], 'size_bytes': si['size_bytes'],
                    'snapshot_timestamp': si['osm_snapshot_timestamp'],
                    'publisher_md5': si['geofabrik_md5']})
    result = {'sources': records, 'license': 'ODbL-1.0',
              'attribution': 'OpenStreetMap contributors; extracts by Geofabrik'}
    if manifest.exists() and result != json.loads(manifest.read_text()):
        raise ValueError('Frozen source manifest changed')
    if not manifest.exists():
        manifest.write_text(json.dumps(result, indent=2) + '\n')


def create_polygon(config):
    provenance = ROOT/config['results_dir']/'extraction_provenance.json'
    if provenance.exists() and json.loads(provenance.read_text())['config'] != config:
        raise ValueError('Frozen region configuration changed; use a separate result/raw/cache directory')
    polygon, _, base = region_polygon(config)
    destination = ROOT / config['polygon_path']
    contents = polygon_bytes(polygon)
    if destination.exists() and destination.read_bytes() != contents:
        raise ValueError('Existing research polygon differs; use a separate dataset for another margin')
    if not destination.exists():
        destination.write_bytes(contents)
    nodes = pd.read_parquet(ROOT / 'data/processed/graphs/slovenia/nodes.parquet')
    od = pd.read_parquet(ROOT / 'data/processed/od_instances.parquet')
    endpoint_ids = np.unique(od[['origin_node', 'destination_node']].to_numpy())
    transform = Transformer.from_crs(4326, config['projection'], always_xy=True)
    points = shapely.points(*transform.transform(nodes.iloc[endpoint_ids].lon, nodes.iloc[endpoint_ids].lat))
    si_size = (ROOT / config['slovenia_source']).stat().st_size
    coverage = shapely.union_all([read_poly(ROOT / config['base_polygon']),
        *[read_poly(ROOT / config['results_dir'] / 'boundary' / (name + '.poly'))
          for name in ['austria', 'nord-est', 'croatia', 'hungary', 'bosnia-herzegovina']]])
    rows = []
    for margin in config['candidate_margins_km']:
        p, projected, _ = region_polygon(config, margin)
        source = shapely.transform(coverage, transform.transform, interleaved=False)
        rows.append({'margin_km': margin, 'area_km2': projected.area / 1e6,
                     'all_tag_pbf_estimated_bytes': projected.area / base.area * si_size,
                     'minimum_endpoint_boundary_distance_km': float(shapely.distance(points, projected.boundary).min()/1000),
                     'source_proxy_uncovered_area_km2': projected.difference(source).area/1e6,
                     'wgs84_bounds': list(p.bounds)})
    result = {'method': 'EPSG:3035 metric buffer of frozen extract proxy',
              'config': config, 'polygon_sha256': sha256(destination), 'candidates': rows,
              'coverage_polygon_sha256': {p.name: sha256(p) for p in (ROOT/config['results_dir']/'boundary').glob('*.poly')}}
    (ROOT / config['results_dir'] / 'region_design.json').write_text(json.dumps(result, indent=2) + '\n')
    pd.DataFrame(rows).drop(columns='wgs84_bounds').to_csv(ROOT/config['results_dir']/'region_candidates.csv', index=False)
    print(json.dumps(result['candidates'], indent=2))


def osmium_version(osmium):
    version = subprocess.check_output([osmium, '--version'], text=True)
    if not version.startswith('osmium version 1.18.0'):
        raise ValueError(f'Expected pinned osmium 1.18.0: {version}')
    return version


def freeze_command(command, destination, record, config):
    partial = destination.with_suffix('.partial.pbf')
    if partial.exists():
        raise ValueError(f'Incomplete extraction already exists: {partial}; inspect before removing')
    inputs = {str(Path(arg)):sha256(Path(arg)) for arg in command
              if Path(str(arg)).is_file() and str(arg).endswith(('.pbf','.geojson'))}
    result = measured_command([*command, '-o', str(partial)], record,
                     rss_limit_gib=config['memory']['maximum_rss_gib'],
                     reserve_gib=config['memory']['minimum_reserve_gib'],
                     interval=config['memory']['monitor_interval_s'])
    immutable_install(partial, destination)
    result.update({'input_sha256': inputs, 'artifact_sha256': sha256(destination),
                   'artifact_size_bytes': destination.stat().st_size})
    Path(record).write_text(json.dumps(result,indent=2)+'\n')


def extract_source(config, osmium, raw, cache, logs):
    """A source can be streamed independently once its bytes are verified/frozen."""
    cache.mkdir(parents=True,exist_ok=True)
    name = raw.name.replace('.osm.pbf','')
    crop,roads = cache/(name+'.crop.pbf'),cache/(name+'.highways.pbf')
    headers = ['--output-header=osmosis_replication_timestamp='+config['snapshot_timestamp'].replace('+00:00','Z')]
    measurements=[]
    for command,destination,label in [
        ([osmium,'extract','-p',str(ROOT/config['polygon_path']),'-s','complete_ways',str(raw),*headers],crop,'extract'),
        ([osmium,'tags-filter',str(crop),'w/highway',*headers],roads,'filter')]:
        record=logs/(name+'_'+label+'.json')
        if destination.exists():
            result=json.loads(record.read_text())
            inputs={str(Path(arg)):sha256(Path(arg)) for arg in command
                    if Path(str(arg)).is_file() and str(arg).endswith(('.pbf','.geojson'))}
            expected=[*command,'-o',str(destination.with_suffix('.partial.pbf'))]
            if (result['artifact_sha256'] != sha256(destination) or result['input_sha256'] != inputs
                    or result['command'] != expected or result['exit_code'] != 0):
                raise ValueError('Intermediate frozen extraction fingerprint/command mismatch')
        else:
            freeze_command(command,destination,record,config)
            result=json.loads(record.read_text())
        measurements.append(result)
    return roads,measurements


def filtered_calibration(config, osmium):
    osmium_version(osmium)
    directory = ROOT / config['raw_dir']
    directory.mkdir(parents=True, exist_ok=True)
    raw = ROOT/config['calibration_raw_path'] if config.get('calibration_raw_path') else directory / 'slovenia_highways_calibration.osm.pbf'
    if not raw.exists():
        freeze_command([osmium, 'tags-filter', str(ROOT/config['slovenia_source']), 'w/highway',
                        '--output-header=osmosis_replication_timestamp='+config['snapshot_timestamp'].replace('+00:00','Z')],
                       raw, ROOT/config['results_dir']/'calibration_filter.json', config)
    data, _ = configs()
    data.update({'results_dir': config['results_dir'], 'graph_dir': 'data/cache/regional_calibration'})
    data['dataset'] = {'region': 'Slovenia highway-filter calibration', 'source_url': 'derived:slovenia-highways-260929',
                       'raw_path': str(raw.relative_to(ROOT)), 'sha256': sha256(raw),
                       'manifest_path': config['results_dir']+'/calibration_manifest.yaml'}
    manifest = ROOT/data['dataset']['manifest_path']
    manifest.write_text(yaml.safe_dump({'dataset': {**data['dataset'], 'size_bytes': raw.stat().st_size,
                                                  'osm_snapshot_timestamp': config['snapshot_timestamp']}}, sort_keys=False))
    data_path = ROOT/config['results_dir']/'calibration_data.yaml'
    data_path.write_text(yaml.safe_dump(data, sort_keys=False))
    measured_command([sys.executable, 'scripts/build_graph.py', '--data-config', str(data_path)],
                     ROOT/config['results_dir']/'calibration_build.json',
                     rss_limit_gib=config['memory']['maximum_rss_gib'],
                     reserve_gib=config['memory']['minimum_reserve_gib'],
                     interval=config['memory']['monitor_interval_s'])
    old = json.loads((ROOT/'data/processed/graphs/slovenia/metadata.json').read_text())
    new = json.loads((ROOT/data['graph_dir']/'metadata.json').read_text())
    equal = old['files'] == new['files']
    result = {'parquet_byte_identical': equal, 'original_files': old['files'], 'filtered_files': new['files'],
              'filtered_pbf_sha256': sha256(raw), 'filtered_pbf_size_bytes': raw.stat().st_size,
              'preprocessing_peak_rss_mib': new['process_peak_rss_mib'],
              'preprocessing_seconds': new['preprocessing_seconds']}
    (ROOT/config['results_dir']/'calibration.json').write_text(json.dumps(result, indent=2)+'\n')
    if not equal:
        raise RuntimeError('Highway filtering changed Slovenia graph semantics')
    print(json.dumps(result, indent=2))


def extract(config, osmium, reproduce=False):
    version = osmium_version(osmium)
    design = json.loads((ROOT/config['results_dir']/'region_design.json').read_text())
    polygon = ROOT/config['polygon_path']
    if sha256(polygon) != design['polygon_sha256'] or polygon.read_bytes() != polygon_bytes(region_polygon(config)[0]):
        raise ValueError('Extraction polygon changed')
    sources = json.loads((ROOT/config['results_dir']/'sources.json').read_text())['sources']
    directory = ROOT/(config.get('rebuild_cache_dir','data/cache/regional_extraction_rebuild')+'/final'
                      if reproduce else config['raw_dir'])
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory/'slovenia_extended-260929.osm.pbf'
    frozen_provenance = ROOT/config['results_dir']/'extraction_provenance.json'
    if destination.exists() and not reproduce:
        provenance = json.loads(frozen_provenance.read_text())
        if (sha256(destination) != provenance['resulting_pbf_sha256']
                or sha256(polygon) != provenance['polygon_sha256']
                or provenance['config'] != config or provenance['tool_version'] != version):
            raise ValueError('Immutable regional extraction provenance mismatch')
        print('Verified existing immutable regional PBF')
        return
    cache = ROOT/(config.get('rebuild_cache_dir','data/cache/regional_extraction_rebuild')+'/stages'
                  if reproduce else config.get('extraction_cache_dir','data/cache/regional_extraction'))
    cache.mkdir(parents=True, exist_ok=True)
    filtered = []
    measurements = []
    for source in sources:
        raw = ROOT/source['path']
        if sha256(raw) != source['sha256'] or snapshot_timestamp(raw) != config['snapshot_timestamp']:
            raise ValueError(f'Invalid frozen source {raw}')
        roads,records=extract_source(config,osmium,raw,cache,
            ROOT/config['results_dir']/('extraction_rebuild_logs' if reproduce else 'extraction_logs'))
        measurements.extend(records)
        filtered.append(roads)
    record = ROOT/config['results_dir']/('extraction_rebuild_logs' if reproduce else 'extraction_logs')/'merge.json'
    freeze_command([osmium, 'merge', *map(str, filtered),
                    '--output-header=osmosis_replication_timestamp='+config['snapshot_timestamp'].replace('+00:00','Z')],
                   destination, record, config)
    measurements.append(json.loads(record.read_text()))
    subprocess.run([osmium, 'check-refs', str(destination)], check=True)
    if reproduce:
        frozen = json.loads(frozen_provenance.read_text())
        result = {'resulting_pbf_sha256': sha256(destination), 'polygon_sha256': sha256(polygon),
                  'byte_identical': sha256(destination) == frozen['resulting_pbf_sha256'],
                  'commands': measurements, 'tool_version': version}
        (ROOT/config['results_dir']/'extraction_reproducibility.json').write_text(json.dumps(result,indent=2)+'\n')
        if not result['byte_identical']:
            raise RuntimeError('Regional streaming extraction did not reproduce identical PBF bytes')
        print('Regional streaming extraction reproduced identical PBF bytes')
        return
    provenance = {'schema_version': 1, 'source_records': sources, 'tool_version': version,
                  'polygon_sha256': sha256(polygon), 'polygon_path': config['polygon_path'],
                  'config': config, 'commands': measurements, 'resulting_pbf_sha256': sha256(destination),
                  'resulting_pbf_size_bytes': destination.stat().st_size,
                  'snapshot_timestamp': snapshot_timestamp(destination),
                  'method': 'complete_ways per source; all highway ways plus referenced nodes; same-date merge',
                  'license': 'ODbL-1.0', 'attribution': 'OpenStreetMap contributors; Geofabrik'}
    (ROOT/config['results_dir']/'extraction_provenance.json').write_text(json.dumps(provenance, indent=2)+'\n')
    data, _ = configs()
    data.update({'graph_dir': config['graph_dir'], 'results_dir': config['results_dir'],
                 'instances_path': config['results_dir']+'/od_remapping.parquet'})
    data['dataset'] = {'region': f"Slovenia cross-border {config['buffer_km']} km research region",
                       'source_url': 'derived:geofabrik-same-snapshot-regional-crop-260929',
                       'raw_path': str(destination.relative_to(ROOT)),
                       'sha256': provenance['resulting_pbf_sha256'],
                       'manifest_path': config['results_dir']+'/DATA_MANIFEST.yaml'}
    (ROOT/data['dataset']['manifest_path']).write_text(yaml.safe_dump({'schema_version': 1, 'dataset': {
        **data['dataset'], 'size_bytes': destination.stat().st_size,
        'osm_snapshot_timestamp': config['snapshot_timestamp'],
        'extraction_provenance': config['results_dir']+'/extraction_provenance.json'}}, sort_keys=False))
    (ROOT/'configs/data_extended.yaml').write_text(yaml.safe_dump(data, sort_keys=False))
    print(json.dumps({k: v for k, v in provenance.items() if k not in ('commands', 'config', 'source_records')}, indent=2))


def build(config):
    calibration = json.loads((ROOT/config['results_dir']/'calibration.json').read_text())
    if not calibration['parquet_byte_identical']:
        raise ValueError('Calibration must preserve original graph exactly')
    data, _ = configs('configs/data_extended.yaml')
    if data['graph_dir'] != config['graph_dir'] or Path(data['graph_dir']).name == 'slovenia':
        raise ValueError('Regional graph output must be separate from Slovenia')
    model_path=ROOT/config['results_dir']/'model_input_provenance.json'
    model=json.loads(model_path.read_text()) if model_path.exists() else None
    expected_raw=model['resulting_pbf_path'] if model else config['raw_dir']+'/slovenia_extended-260929.osm.pbf'
    if data['dataset']['raw_path'] != expected_raw:
        raise ValueError('Regional build must use the immutable cropped PBF')
    if model:
        control=json.loads((ROOT/config['results_dir']/'model_calibration.json').read_text())
        if (not control['parquet_byte_identical'] or model['input_sha256'] != sha256(ROOT/model['input_path'])
                or model['routing_config_sha256'] != sha256(ROOT/'configs/routing.yaml')
                or model['resulting_pbf_sha256'] != data['dataset']['sha256']):
            raise ValueError('Model-domain adapter/control verification failed')
    verified_dataset(data)
    size = (ROOT/data['dataset']['raw_path']).stat().st_size
    old = json.loads((ROOT/'data/processed/graphs/slovenia/metadata.json').read_text())
    original_factor = old['process_peak_rss_mib']*2**20/(ROOT/config['slovenia_source']).stat().st_size
    filtered_factor = calibration['preprocessing_peak_rss_mib']*2**20/calibration['filtered_pbf_size_bytes']
    if model:
        filtered_factor=max(filtered_factor,control['preprocessing_peak_rss_mib']*2**20/control['filtered_pbf_size_bytes'])
    estimate = max(original_factor, filtered_factor)*size*config['memory']['safety_factor']
    available = available_memory_bytes()
    permitted = estimate <= config['memory']['maximum_rss_gib']*2**30 and available-estimate >= config['memory']['minimum_reserve_gib']*2**30
    record = {'raw_size_bytes': size, 'original_rss_amplification': original_factor,
              'filtered_rss_amplification': filtered_factor, 'safety_factor': config['memory']['safety_factor'],
              'estimated_rss_gib': estimate/2**30, 'available_ram_gib': available/2**30,
              'permitted': permitted, 'limits': config['memory']}
    (ROOT/config['results_dir']/'memory_guard.json').write_text(json.dumps(record, indent=2)+'\n')
    print(json.dumps(record, indent=2), flush=True)
    if not permitted:
        raise RuntimeError('Estimated preprocessing exceeds safe memory; analyze a smaller crop or tiled parsing')
    measured_command([sys.executable, 'scripts/build_graph.py', '--data-config', 'configs/data_extended.yaml'],
                     ROOT/config['results_dir']/'preprocessing_benchmark.json',
                     rss_limit_gib=config['memory']['maximum_rss_gib'],
                     reserve_gib=config['memory']['minimum_reserve_gib'],
                     interval=config['memory']['monitor_interval_s'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['download', 'polygon', 'calibrate', 'extract', 'verify-extraction', 'build'])
    parser.add_argument('--config', default='configs/regional.yaml')
    parser.add_argument('--osmium', default='../osmium-env/bin/osmium')
    parser.add_argument('--download-resolve', help='Optional verified Geofabrik IPv4 transport override; dataset checks remain mandatory')
    args = parser.parse_args()
    config = read_config(args.config)
    if args.stage not in ('download','polygon','build'):
        executable = shutil.which(args.osmium)
        if executable is None:
            raise FileNotFoundError(f'Pinned osmium executable unavailable: {args.osmium}')
        args.osmium = str(Path(executable).resolve())
    if args.stage == 'download': acquire_sources(config, args.download_resolve)
    elif args.stage == 'polygon': create_polygon(config)
    elif args.stage == 'calibrate': filtered_calibration(config, args.osmium)
    elif args.stage == 'extract': extract(config, args.osmium)
    elif args.stage == 'verify-extraction': extract(config, args.osmium, reproduce=True)
    else: build(config)


if __name__ == '__main__':
    main()
