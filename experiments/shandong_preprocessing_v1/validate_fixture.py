"""Synthetic-only integration: generated 130-node line, never reads map inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import numpy as np
import pandas as pd
import yaml
from pyrosm import OSM

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'scripts'), str(ROOT/'src')]
from graph.preprocessing import ATTRIBUTES, normalize_network
from graph.road_graph import IgraphRoadGraph
from opportunity.attachment import attach_opportunities
from opportunity.models import Opportunity, OpportunityId, Provenance


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--osmium', required=True)
    args=parser.parse_args()
    routing=yaml.safe_load((ROOT/'configs/routing.yaml').read_text())
    attachment=yaml.safe_load((ROOT/'configs/opportunity.yaml').read_text())['attachment']
    with tempfile.TemporaryDirectory(prefix='hiroute-synthetic-only-') as tmp:
        p=Path(tmp)
        xml=['<osm version="0.6" generator="HiRoute synthetic fixture">']
        for i in range(130):
            xml.append(f'<node id="{i+1}" version="1" lat="36" lon="{118+i*.001:.6f}"/>')
        xml += ['<way id="1000" version="1">']
        xml += [f'<nd ref="{i+1}"/>' for i in range(130)]
        xml += ['<tag k="highway" v="residential"/><tag k="maxspeed" v="30"/></way></osm>']
        (p/'fixture.osm').write_text('\n'.join(xml))
        subprocess.run([args.osmium,'cat',str(p/'fixture.osm'),'-o',str(p/'raw.pbf')],check=True)
        subprocess.run([args.osmium,'tags-filter',str(p/'raw.pbf'),'w/highway','-o',str(p/'roads.pbf')],check=True)
        tables=[]
        for name in ('raw','roads'):
            nodes,edges=OSM(str(p/f'{name}.pbf'),workers=1).get_network(network_type='driving',nodes=True,extra_attributes=ATTRIBUTES)
            tables.append(normalize_network(nodes,edges,routing))
        for i in (0,1):pd.testing.assert_frame_equal(tables[0][i],tables[1][i])
        if tables[0][2]!=tables[1][2]:raise ValueError('Filter changed normalizer audit')
        nodes,edges,_=tables[0]
        graph=IgraphRoadGraph(nodes,edges)
        opportunities=[Opportunity(OpportunityId('node',int(row.osm_node_id)),row.lat,row.lon,
            frozenset(['charge']),None,{},Provenance(('synthetic',),'synthetic','OSM node')) for row in nodes.itertuples()]
        attached=attach_opportunities(opportunities,graph,edges.highway.to_numpy(),attachment)
        if any(o.attachment_status!='attached' or o.access_distance_m!=0 or o.access_node!=i for i,o in enumerate(attached)):
            raise ValueError('Synthetic attachment mismatch')
        rank=np.empty(len(nodes),dtype=np.int32)
        rank[np.argsort(nodes.osm_node_id.to_numpy(),kind='stable')]=np.arange(len(nodes),dtype=np.int32)
        access=rank[np.array([o.access_node for o in attached],dtype=np.int64)]
        with (p/'topology.bin').open('wb') as stream:
            np.array([len(nodes),len(edges),len(attached)],dtype=np.int64).tofile(stream)
            np.column_stack([rank[edges.source.to_numpy()],rank[edges.target.to_numpy()]]).astype(np.int32).tofile(stream)
            access.tofile(stream)
        cpp=ROOT/'src/hierarchy4r/bisection.cpp'
        subprocess.run(['g++','-O3','-std=c++17',str(cpp),'-o',str(p/'bisection')],check=True)
        for label in ('primary','rebuild'):
            subprocess.run([str(p/'bisection'),str(p/'topology.bin'),str(p/f'{label}.bin'),str(p/f'{label}.csv'),'64'],check=True)
        for suffix in ('bin','csv'):
            if (p/f'primary.{suffix}').read_bytes()!=(p/f'rebuild.{suffix}').read_bytes():raise ValueError('Global hierarchy rebuild mismatch')
        regions=pd.read_csv(p/'primary.csv')
        leaves=regions[regions.left.lt(0)]
        if leaves.sites.sum()!=130 or leaves.sites.max()>64:raise ValueError('Global hierarchy coverage mismatch')
        print(json.dumps({'synthetic_only':True,'road_nodes':len(nodes),'directed_edges':len(edges),
            'filter_normalization_equal':True,'attached_sites':len(attached),
            'hierarchy_region_count':len(regions),'hierarchy_leaf_count':len(leaves),
            'hierarchy_rebuild_byte_identical':True,'hierarchy_source_sha256':hashlib.sha256(cpp.read_bytes()).hexdigest()},indent=2))

if __name__=='__main__':main()
