"""Cold compact neighbor rebuild and resource benchmark against the frozen cache."""
from dataclasses import replace
import json
import resource
import time
import numpy as np
import pandas as pd
from pyproj import Transformer
from _common import ROOT,configs,read_config,load_graph,sha256
from run_opportunity_benchmark import inventory_objects
from opportunity.network import validate_network_pairs


def main():
    cfg=read_config('configs/opportunity.yaml');result=ROOT/cfg['results_dir']
    data,routing=configs(cfg['graph_data_config']);graph=load_graph(data,routing)
    inventory=pd.read_parquet(ROOT/cfg['raw_dir']/'inventory.parquet')
    attachments=pd.read_parquet(result/'opportunity_attachment.parquet')
    if not inventory[['osm_type','osm_id']].equals(attachments[['osm_type','osm_id']]):
        raise ValueError('Attachment inventory identities do not align')
    objects=inventory_objects(inventory)
    opportunities=[replace(o,access_node=int(a.access_node),access_osm_node_id=int(a.access_osm_node_id),
                           access_distance_m=float(a.access_distance_m),attachment_status=a.attachment_status)
                   for o,a in zip(objects,attachments.itertuples(),strict=True) if a.attachment_status=='attached']
    transform=Transformer.from_crs(4326,3035,always_xy=True)
    xy=np.column_stack(transform.transform([o.lon for o in opportunities],[o.lat for o in opportunities]))
    index,directed,pairs,metadata=validate_network_pairs(graph,opportunities,xy,cfg['network'],ROOT/cfg['cache_dir']/'network_compact_verification')
    osm_types=np.array([o.identity.osm_type for o in opportunities],dtype=object)
    osm_ids=np.array([o.identity.osm_id for o in opportunities],dtype=np.int64)
    table=pd.DataFrame({'first_type':osm_types[pairs[:,0]],'first_id':osm_ids[pairs[:,0]],
        'second_type':osm_types[pairs[:,1]],'second_id':osm_ids[pairs[:,1]],
        'geographic_m':index.geographic_m,'network_m':index.network_m,
        'forward_m':directed[:,0],'reverse_m':directed[:,1]})
    path=ROOT/cfg['cache_dir']/'network_compact_verification'/'local_neighbor_pairs.parquet'
    start=time.perf_counter();table.to_parquet(path,index=False);metadata['serialization_seconds']=time.perf_counter()-start
    metadata['pair_file_sha256']=sha256(path);metadata['original_pair_file_sha256']=sha256(result/'local_neighbor_pairs.parquet')
    metadata['input_sha256']={'inventory':sha256(ROOT/cfg['raw_dir']/'inventory.parquet'),'attachment':sha256(result/'opportunity_attachment.parquet'),'graph_metadata':sha256(ROOT/data['graph_dir']/'metadata.json')}
    metadata['configuration']=cfg['network']
    metadata['byte_identical']=metadata['pair_file_sha256']==metadata['original_pair_file_sha256']
    metadata['process_peak_rss_mib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
    (result/'network_compact_reproducibility.json').write_text(json.dumps(metadata,indent=2)+'\n')
    if not metadata['byte_identical']:raise RuntimeError('Compact cold neighbor rebuild changed frozen sparse pair bytes')
    print(json.dumps(metadata,indent=2),flush=True)

if __name__=='__main__':main()
