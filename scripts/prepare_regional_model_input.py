"""Quarantine only candidate road classes outside the unchanged routing domain.

The complete geographic road crop stays immutable. A separate input removes
classes that the original normalizer cannot assign a cost, retaining all nodes
and every other way. No supported speed or access rule is changed.
"""
import argparse
import json
from pathlib import Path
import resource
import subprocess
import sys
import xml.etree.ElementTree as ET

import pandas as pd
from pyrosm import OSM
from pyrosm.config import Conf
import yaml

from _common import ROOT, configs, read_config, sha256
from _regional_common import measured_command
from graph.preprocessing import ATTRIBUTES
from prepare_regional_data import freeze_command, osmium_version


def unsupported_candidates(histogram, routing):
    modeled=set(routing['speed_model']['class_kph'])
    explicit=set(routing['access']['excluded_highway'])
    parser_excluded=Conf.network_filters.driving['highway']
    return sorted(k for k in histogram if k not in modeled|explicit and k not in parser_excluded)


def probe(path, output):
    if path.stat().st_size > 16*2**20:
        raise ValueError('Unmodelled-class probe too large; analyze before parsing')
    nodes,edges=OSM(str(path),workers=1).get_network(network_type='driving',nodes=True,extra_attributes=ATTRIBUTES)
    counts={} if edges is None else {k:int(v) for k,v in edges.highway.value_counts().items()}
    output.write_text(json.dumps({'candidate_pbf_sha256':sha256(path),'parsed_highway_segments':counts,
        'node_count':0 if nodes is None else len(nodes),
        'process_peak_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024},indent=2)+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',default='configs/regional.yaml')
    parser.add_argument('--osmium',default='../osmium-env/bin/osmium')
    parser.add_argument('--verify',action='store_true',help='Independently reproduce the modeled-input PBF')
    parser.add_argument('--probe',nargs=2,metavar=('PBF','JSON'))
    args=parser.parse_args()
    if args.probe:
        probe(Path(args.probe[0]),Path(args.probe[1]));return
    osmium=str(Path(args.osmium).resolve())
    version=osmium_version(osmium)
    config=read_config(args.config)
    output=ROOT/config['results_dir']
    extraction=json.loads((output/'extraction_provenance.json').read_text())
    raw=ROOT/config['raw_dir']/'slovenia_extended-260929.osm.pbf'
    if extraction['config']!=config or sha256(raw)!=extraction['resulting_pbf_sha256']:
        raise ValueError('Frozen geographic input/provenance mismatch')
    _,routing=configs()
    provenance_path=output/'model_input_provenance.json'
    target=raw.with_name('slovenia_extended-modeled-260929.osm.pbf')
    if args.verify:
        frozen=json.loads(provenance_path.read_text())
        if frozen['routing_config_sha256']!=sha256(ROOT/'configs/routing.yaml'):
            raise ValueError('Routing domain changed')
        rebuilt=ROOT/'data/cache/regional_modeled_input_rebuild.pbf'
        freeze_command([osmium,'tags-filter','-i',str(raw),
            'w/highway='+','.join(frozen['quarantined_highway_classes']),
            '--output-header=osmosis_replication_timestamp='+config['snapshot_timestamp'].replace('+00:00','Z')],
            rebuilt,output/'model_input_rebuild.json',config)
        result=json.loads((output/'model_input_rebuild.json').read_text())
        result['byte_identical']=sha256(rebuilt)==frozen['resulting_pbf_sha256']
        (output/'model_input_reproducibility.json').write_text(json.dumps(result,indent=2)+'\n')
        if not result['byte_identical']:raise RuntimeError('Model-domain filtering did not reproduce PBF bytes')
        return
    if target.exists():
        frozen=json.loads(provenance_path.read_text())
        if (sha256(target)!=frozen['resulting_pbf_sha256'] or frozen['input_sha256']!=sha256(raw)
            or frozen['routing_config_sha256']!=sha256(ROOT/'configs/routing.yaml') or frozen['tool_version']!=version):
            raise ValueError('Frozen modeled-input provenance mismatch')
        print('Verified existing model-domain input');return
    histogram_text=subprocess.check_output([osmium,'tags-count','-t','way',str(raw),'highway=*'],text=True)
    histogram={}
    for line in histogram_text.splitlines():
        count,key,value=line.split('\t');assert json.loads(key)=='highway'
        histogram[json.loads(value)]=int(count)
    candidates=unsupported_candidates(histogram,routing)
    if not candidates:raise ValueError('No model-domain adapter needed for this input')
    candidate=ROOT/'data/cache/regional_unmodeled_candidates.pbf'
    headers=['--output-header=osmosis_replication_timestamp='+config['snapshot_timestamp'].replace('+00:00','Z')]
    freeze_command([osmium,'tags-filter',str(raw),'w/highway='+','.join(candidates),*headers],
                   candidate,output/'model_candidate_filter.json',config)
    probe_json=output/'model_candidate_probe.json'
    measured_command([sys.executable,str(Path(__file__).resolve()),'--probe',str(candidate),str(probe_json)],
        output/'model_candidate_probe_benchmark.json',rss_limit_gib=config['memory']['maximum_rss_gib'],
        reserve_gib=config['memory']['minimum_reserve_gib'],interval=config['memory']['monitor_interval_s'])
    parsed=json.loads(probe_json.read_text())['parsed_highway_segments']
    unknown=sorted(parsed)
    if not unknown or not set(unknown)<=set(candidates):raise ValueError('Unexpected driving candidate domain')
    # Archive full tags and references for every quarantined way.
    quarantine=raw.with_name('unmodeled_highway_ways-260929.osm.pbf')
    freeze_command([osmium,'tags-filter',str(raw),'w/highway='+','.join(unknown),*headers],
                   quarantine,output/'model_quarantine_filter.json',config)
    xml=ET.fromstring(subprocess.check_output([osmium,'cat',str(quarantine),'-f','osm']))
    ways=[{'osm_way_id':int(way.attrib['id']),
           'osm_node_ids':[int(n.attrib['ref']) for n in way.findall('nd')],
           'tags':{tag.attrib['k']:tag.attrib['v'] for tag in way.findall('tag')}} for way in xml.findall('way')]
    freeze_command([osmium,'tags-filter','-i',str(raw),'w/highway='+','.join(unknown),*headers],
                   target,output/'model_input_filter.json',config)
    # Empirical control: the identical filter must preserve the original graph.
    calibration=ROOT/'data/cache/regional_model_calibration.osm.pbf'
    source=ROOT/config['calibration_raw_path']
    freeze_command([osmium,'tags-filter','-i',str(source),'w/highway='+','.join(unknown),*headers],
                   calibration,output/'model_calibration_filter.json',config)
    data,_=configs()
    data.update(graph_dir='data/cache/regional_model_calibration_graph',results_dir=config['results_dir'])
    data['dataset']={'region':'Slovenia model-domain control','source_url':'derived:slovenia-model-domain-260929',
        'raw_path':str(calibration.relative_to(ROOT)),'sha256':sha256(calibration),
        'manifest_path':config['results_dir']+'/model_calibration_manifest.yaml'}
    (ROOT/data['dataset']['manifest_path']).write_text(yaml.safe_dump({'dataset':{**data['dataset'],
        'size_bytes':calibration.stat().st_size,'osm_snapshot_timestamp':config['snapshot_timestamp']}},sort_keys=False))
    data_path=output/'model_calibration_data.yaml';data_path.write_text(yaml.safe_dump(data,sort_keys=False))
    measured_command([sys.executable,'scripts/build_graph.py','--data-config',str(data_path)],
        output/'model_calibration_build.json',rss_limit_gib=config['memory']['maximum_rss_gib'],
        reserve_gib=config['memory']['minimum_reserve_gib'],interval=config['memory']['monitor_interval_s'])
    old=json.loads((ROOT/'data/processed/graphs/slovenia/metadata.json').read_text())
    new=json.loads((ROOT/data['graph_dir']/'metadata.json').read_text())
    control={'parquet_byte_identical':old['files']==new['files'],'original_files':old['files'],
        'filtered_files':new['files'],'filtered_pbf_size_bytes':calibration.stat().st_size,
        'filtered_pbf_sha256':sha256(calibration),'preprocessing_peak_rss_mib':new['process_peak_rss_mib'],
        'preprocessing_seconds':new['preprocessing_seconds']}
    (output/'model_calibration.json').write_text(json.dumps(control,indent=2)+'\n')
    if not control['parquet_byte_identical']:raise RuntimeError('Model-domain filtering changed Slovenia graph')
    frozen={'input_path':str(raw.relative_to(ROOT)),'input_sha256':sha256(raw),
        'resulting_pbf_path':str(target.relative_to(ROOT)),'resulting_pbf_sha256':sha256(target),
        'resulting_pbf_size_bytes':target.stat().st_size,'tool_version':version,
        'snapshot_timestamp':config['snapshot_timestamp'],'routing_config_sha256':sha256(ROOT/'configs/routing.yaml'),
        'source_highway_way_counts':histogram,'raw_candidate_classes':candidates,
        'quarantined_highway_classes':unknown,'quarantined_parsed_segments':parsed,
        'quarantined_way_count':len(ways),'quarantined_ways':ways,'quarantine_pbf_sha256':sha256(quarantine),
        'filter_measurement':json.loads((output/'model_input_filter.json').read_text()),
        'policy':'Remove only unmodelled way classes rejected by the original normalizer; retain all other ways, tags and nodes; no new speed/access assumption'}
    provenance_path.write_text(json.dumps(frozen,indent=2)+'\n')
    data,_=configs('configs/data_extended.yaml')
    data['dataset'].update(raw_path=str(target.relative_to(ROOT)),sha256=sha256(target),
        source_url='derived:geofabrik-260929-regional-crop-original-model-domain',
        manifest_path=config['results_dir']+'/MODEL_DATA_MANIFEST.yaml')
    (ROOT/data['dataset']['manifest_path']).write_text(yaml.safe_dump({'schema_version':1,'dataset':{
        **data['dataset'],'size_bytes':target.stat().st_size,'osm_snapshot_timestamp':config['snapshot_timestamp'],
        'extraction_provenance':config['results_dir']+'/extraction_provenance.json',
        'model_input_provenance':config['results_dir']+'/model_input_provenance.json'}},sort_keys=False))
    (ROOT/'configs/data_extended.yaml').write_text(yaml.safe_dump(data,sort_keys=False))
    print(json.dumps({k:v for k,v in frozen.items() if k not in ('quarantined_ways','filter_measurement','source_highway_way_counts')},indent=2))


if __name__=='__main__':main()
