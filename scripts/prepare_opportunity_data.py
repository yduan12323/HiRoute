"""Streaming, same-snapshot activity PBF and independently frozen inventory.

No live OSM; no Pyrosm. Geometry conversion uses pinned osmium-tool.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import xml.etree.ElementTree as ET
from collections import Counter
import pandas as pd
from pyproj import Transformer
import shapely
import yaml
from _common import ROOT, read_config, sha256
from _regional_common import measured_command
from prepare_regional_data import immutable_install, osmium_version
from opportunity.taxonomy import classify_tags, filter_expressions
from opportunity.regions import fingerprint


def object_catalogue(osmium, path, extraction):
    """XML iterparse preserves identities/tags even when geometry cannot export."""
    result = {}
    with subprocess.Popen([osmium, 'cat', str(path), '-f', 'osm'], stdout=subprocess.PIPE,
                          env={**os.environ, 'OSMIUM_POOL_THREADS':'1'}) as process:
        context = ET.iterparse(process.stdout, events=('start','end'))
        _, root = next(context)
        for event, element in context:
            if event != 'end' or element.tag not in ('node','way','relation'): continue
            tags = {t.attrib['k']:t.attrib['v'] for t in element.findall('tag')}
            capabilities, subtype = classify_tags(tags, extraction)
            if capabilities:
                key = (element.tag, int(element.attrib['id']))
                result[key] = {'original_tags':tags, 'capabilities':sorted(capabilities), 'subtype':subtype}
            root.clear()
        if process.wait(): raise RuntimeError('OSM catalogue streaming failed')
    return result


def export_identity(feature):
    identifier = feature['id']; prefix, number = identifier[0], int(identifier[1:])
    if prefix == 'n': return 'node', number
    if prefix == 'w': return 'way', number
    if prefix == 'a': return ('relation', (number-1)//2) if number%2 else ('way', number//2)
    raise ValueError(f'Unknown exported identity {identifier}')


def parse_geometry(path, catalogue, polygon):
    to_metric = Transformer.from_crs(4326,3035,always_xy=True)
    to_wgs = Transformer.from_crs(3035,4326,always_xy=True)
    located = {}
    errors = Counter()
    with Path(path).open() as stream:
        for line in stream:
            if not line.strip(): continue
            feature = json.loads(line.lstrip('\x1e'))
            key = export_identity(feature)
            if key not in catalogue: continue
            geometry = shapely.geometry.shape(feature['geometry'])
            if geometry.is_empty or not geometry.is_valid:
                errors['invalid_exported_geometry'] += 1; continue
            projected = shapely.transform(geometry,to_metric.transform,interleaved=False)
            if geometry.geom_type in ('Polygon','MultiPolygon'):
                point = projected.representative_point(); method = 'EPSG:3035 point-on-surface'; priority=3
            elif geometry.geom_type in ('LineString','MultiLineString'):
                point = projected.interpolate(0.5,normalized=True); method='EPSG:3035 line midpoint'; priority=2
            elif geometry.geom_type == 'Point':
                point = projected; method='OSM node'; priority=1
            else:
                errors['unsupported_geometry'] += 1; continue
            point = shapely.transform(point,to_wgs.transform,interleaved=False)
            item={'lon':point.x,'lat':point.y,'geometry_method':method,'geometry_type':geometry.geom_type,
                  'geometry_wkb':shapely.to_wkb(geometry),'inside_polygon':bool(polygon.covers(point)), '_priority':priority}
            if key not in located or priority > located[key]['_priority']: located[key]=item
    rows, excluded = [], []
    for key, tags in sorted(catalogue.items()):
        geom=located.get(key)
        reason = 'no_exportable_geometry' if geom is None else ('representative_outside_polygon' if not geom['inside_polygon'] else None)
        if reason:
            excluded.append({'osm_type':key[0],'osm_id':key[1],'reason':reason}); continue
        rows.append({'osm_type':key[0],'osm_id':key[1],**tags,**{k:v for k,v in geom.items() if not k.startswith('_')}})
    return rows, excluded, dict(errors)


def run(config, osmium, reproduce=False):
    regional=read_config(config['regional_config'])
    polygon=ROOT/regional['polygon_path']
    if sha256(polygon)!=config['polygon_sha256']: raise ValueError('Frozen polygon checksum mismatch')
    sources=json.loads((ROOT/regional['results_dir']/'sources.json').read_text())['sources']
    version=osmium_version(osmium)
    raw=ROOT/config['raw_dir']; raw.mkdir(parents=True,exist_ok=True)
    manifest=raw/'MANIFEST.yaml'
    if manifest.exists():
        frozen=yaml.safe_load(manifest.read_text())
        if frozen['extraction_config_fingerprint']!=fingerprint(config['extraction']): raise ValueError('Frozen extraction rules changed')
        if frozen['polygon_sha256']!=sha256(polygon) or frozen['tool_version']!=version: raise ValueError('Frozen extraction contract changed')
        for name, digest in frozen['files'].items():
            if sha256(raw/name)!=digest: raise ValueError('Frozen opportunity bytes changed')
        if not reproduce:
            print('Verified frozen opportunity dataset',flush=True); return
    cache=ROOT/config['cache_dir']/('rebuild' if reproduce else 'extract')
    cache.mkdir(parents=True,exist_ok=False)
    logs=ROOT/config['results_dir']/('extraction_rebuild_logs' if reproduce else 'extraction_logs')
    logs.mkdir(parents=True,exist_ok=True)
    headers=['--output-header=osmosis_replication_timestamp='+config['snapshot_timestamp']]
    expressions=filter_expressions(config['extraction'])
    commands=[]; crops=[]; source_ids={}; raw_count=0
    def command(args, output, label):
        record=measured_command([osmium,*args,'-o',str(output)],logs/(label+'.json'))
        record['artifact_sha256']=sha256(output); commands.append(record)
    started=time.perf_counter()
    for source in sources:
        path=ROOT/source['path']; name=path.name.replace('.osm.pbf','')
        if sha256(path)!=source['sha256']: raise ValueError('Frozen source checksum mismatch')
        info=json.loads(subprocess.check_output([osmium,'fileinfo','-j',str(path)]))
        if info['header']['option']['osmosis_replication_timestamp']!=config['snapshot_timestamp']: raise ValueError('Snapshot mismatch')
        filtered=cache/(name+'.filtered.pbf'); crop=cache/(name+'.crop.pbf')
        # Filter first bounds relation completion to this taxonomy, retaining references.
        command(['tags-filter',str(path),*expressions,*headers],filtered,name+'_filter')
        command(['extract','-p',str(polygon),'-s',config['extraction']['strategy'],
                 '-S','types='+config['extraction']['relation_types'],str(filtered),*headers],crop,name+'_crop')
        catalogue=object_catalogue(osmium,crop,config['extraction']); raw_count+=len(catalogue)
        for key,value in catalogue.items():
            if key in source_ids and source_ids[key]['tags']!=value:
                raise ValueError(f'Same-snapshot overlapping object conflicts: {key}')
            source_ids.setdefault(key,{'sources':[],'tags':value})['sources'].append(name)
        crops.append(crop)
        print(name,'candidates',len(catalogue),flush=True)
    merged=cache/'opportunities-260929.osm.pbf'
    command(['merge',*map(str,crops),*headers],merged,'merge')
    refs = subprocess.run([osmium,'check-refs',str(merged)],capture_output=True,text=True)
    (logs/'way_node_references.txt').write_text(refs.stdout+refs.stderr)
    if refs.returncode: raise ValueError('Opportunity way-node references are incomplete')
    catalogue=object_catalogue(osmium,merged,config['extraction'])
    if set(catalogue)!=set(source_ids): raise ValueError('Merge identity mismatch')
    export=cache/'geometry.geojsonseq'
    command(['export',str(merged),'-u','type_id','-f','geojsonseq','--show-errors'],export,'export')
    extraction_seconds=time.perf_counter()-started
    started=time.perf_counter()
    rows,excluded,errors=parse_geometry(export,catalogue,shapely.geometry.shape(json.loads(polygon.read_text())['geometry']))
    for row in rows:
        key=(row['osm_type'],row['osm_id'])
        row['source_datasets']=sorted(source_ids[key]['sources'])
        row['snapshot_timestamp']=config['snapshot_timestamp']
        row['original_tags']=json.dumps(row['original_tags'],sort_keys=True,separators=(',',':'),ensure_ascii=False)
    inventory=cache/'inventory.parquet'; pd.DataFrame(rows).to_parquet(inventory,index=False)
    parsing_seconds=time.perf_counter()-started
    pd.DataFrame(excluded).to_parquet(ROOT/config['results_dir']/('extraction_rebuild_exclusions.parquet' if reproduce else 'extraction_exclusions.parquet'),index=False)
    result={'schema_version':1,'snapshot_timestamp':config['snapshot_timestamp'],'polygon_sha256':sha256(polygon),
            'extraction_config_fingerprint':fingerprint(config['extraction']),'source_records':sources,'tool_version':version,
            'files':{merged.name:sha256(merged),inventory.name:sha256(inventory)},'raw_candidate_count':raw_count,
            'duplicate_count':raw_count-len(catalogue),'unique_candidate_count':len(catalogue),
            'final_located_in_polygon_count':len(rows),'excluded_count':len(excluded),
            'exclusion_reasons':dict(Counter(r['reason'] for r in excluded)), 'geometry_errors':errors,
            'extraction_seconds':extraction_seconds,'parsing_seconds':parsing_seconds,
            'maximum_command_rss_mib':max(r['process_peak_rss_mib'] for r in commands),
            'commands':commands,'license':'ODbL-1.0','attribution':'OpenStreetMap contributors; Geofabrik',
            'method':'taxonomy-filter with references; smart polygon extraction; same-snapshot merge; projected point-on-surface; representative-in-polygon'}
    if reproduce:
        result['byte_identical']=result['files']==frozen['files']
        (ROOT/config['results_dir']/'extraction_reproducibility.json').write_text(json.dumps(result,indent=2)+'\n')
        if not result['byte_identical']: raise RuntimeError('Opportunity snapshot did not reproduce byte-for-byte')
        print('PBF and inventory reproduced byte-for-byte',flush=True)
    else:
        immutable_install(merged,raw/merged.name); immutable_install(inventory,raw/inventory.name)
        manifest.write_text(yaml.safe_dump({k:v for k,v in result.items() if k!='commands'},sort_keys=False))
        manifest.chmod(0o444)
        (raw/'PROVENANCE.json').write_text(json.dumps(result,indent=2)+'\n'); (raw/'PROVENANCE.json').chmod(0o444)
        (ROOT/config['results_dir']/'extraction.json').write_text(json.dumps(result,indent=2)+'\n')
        print('Frozen',len(rows),'opportunities',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',default='configs/opportunity.yaml')
    parser.add_argument('--osmium',default='../osmium-env/bin/osmium')
    parser.add_argument('--verify',action='store_true')
    args=parser.parse_args(); run(read_config(args.config),str(Path(args.osmium).resolve()),args.verify)

if __name__=='__main__':main()
