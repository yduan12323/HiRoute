"""Shared real/fixture preprocessing phases. Real launch remains code-gated.

Only source() distinguishes fixture input from the proposed provider download.
All downstream phases use the same implementation and original core algorithms.
Every phase executes in its own bounded supervisor child.
"""
from __future__ import annotations
import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import stat
from pathlib import Path
import subprocess
import sys
from urllib.request import urlopen
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts'),str(ROOT/'src')]
# Root must replace these only in a reviewed, source-frozen follow-up commit.
USER_DATA_SCOPE_APPROVAL = None
ROOT_PROTOCOL_FREEZE = None


def gate(fixture):
    if not fixture and (USER_DATA_SCOPE_APPROVAL is None or ROOT_PROTOCOL_FREEZE is None):
        from experiments.m6h_manifest_v1.recovery_runtime import require_active
        try:require_active()
        except PermissionError as exc:
            raise RuntimeError('HELD: reviewed disclosed recovery source/protocol release pending') from exc


def digest(path,checkpoint=None):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):
            h.update(block)
            if checkpoint is not None:checkpoint()
    return h.hexdigest()


def code_contract():
    paths=('scripts/prepare_opportunity_data.py','src/graph/preprocessing.py',
           'src/graph/raw_way_policy.py','experiments/shandong_preprocessing_v1/bounded_io.py',
           'experiments/shandong_preprocessing_v1/way_partition.py',
           'experiments/shandong_preprocessing_v1/registry_worker.py',
           'experiments/m6h_manifest_v1/supervisor.py','experiments/m6h_manifest_v1/resources.py',
           'experiments/m6h_selection_v1/rules.py',
           'src/graph/road_graph.py','src/opportunity/attachment.py','src/opportunity/taxonomy.py',
           'src/stopplan4r/sites.py','src/hierarchy4r/bisection.cpp','src/hierarchy4r/tree.py',
           'configs/routing.yaml','configs/opportunity.yaml','configs/stopplan_4r.yaml','pyproject.toml',
           'experiments/shandong_preprocessing_v1/installed.txt',
           'experiments/shandong_preprocessing_v1/requirements-hashed.txt','environment-osmium-linux-64.lock')
    return {name:digest(ROOT/name) for name in paths}


def write(path,data):
    with Path(path).open('x') as f:
        json.dump(data,f,sort_keys=True,allow_nan=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())


def native(osmium,*args):
    return subprocess.check_output([osmium,*map(str,args)],text=True,
                                  env={**os.environ,'OSMIUM_POOL_THREADS':'1'})


REQUIRED_FILES = {
    'source': {'source.osm.pbf','boundary.poly','boundary.geojson','sources.json'},
    'graph': {'nodes.parquet','edges.parquet','metadata.json','highways.pbf'},
    'inventory': {'inventory.parquet','exclusions.json','opportunities.pbf'},
    'sites': {'attachments.parquet','stop_sites.parquet','local_support.parquet','site_build.json'},
    'hierarchy': {'hierarchy.json','site_membership.parquet','hierarchy_provenance.json'},
}
COMPILER_FLAGS = ['-O3','-std=c++17']


def verify_stage(identity,expected_phase,checkpoint=None):
    if (not isinstance(identity,dict) or set(identity)!={'path','manifest_sha256','phase','synthetic'}
        or identity['phase']!=expected_phase or expected_phase not in REQUIRED_FILES
        or type(identity['synthetic']) is not bool
        or not isinstance(identity['manifest_sha256'],str)
        or not re.fullmatch('[0-9a-f]{64}',identity['manifest_sha256'])):
        raise ValueError('Invalid bound prior-stage identity')
    directory=Path(identity['path'])
    if not directory.is_absolute() or directory.resolve()!=directory or not directory.is_dir():
        raise ValueError('Prior stage must be an absolute nonsymlink directory')
    path=directory/'artifact_manifest.json'
    if path.is_symlink() or not path.is_file() or path.stat().st_size>1024*1024:
        raise ValueError('Invalid manifest file')
    if digest(path,checkpoint)!=identity['manifest_sha256']:
        raise ValueError('Prior manifest digest differs from supervisor-approved identity')
    manifest=json.loads(path.read_text())
    if manifest.get('phase')!=expected_phase or manifest.get('synthetic') is not identity['synthetic']:
        raise ValueError('Prior manifest phase/synthetic mismatch')
    files=manifest.get('files')
    if not isinstance(files,dict) or not REQUIRED_FILES[expected_phase]<=files.keys():
        raise ValueError('Missing required consumed stage files')
    for name,record in files.items():
        rel=Path(name)
        if (not isinstance(name,str) or rel.is_absolute() or '..' in rel.parts
            or not rel.parts or (len(rel.parts)>1 and rel.parts[0]!='scratch')):
            raise ValueError('Invalid artifact filename')
        p=directory/rel
        if (p.resolve()!=p or not p.is_file() or p.is_symlink()
            or p.stat().st_size!=record['size_bytes'] or digest(p,checkpoint)!=record['sha256']):
            raise ValueError('Stage artifact identity mismatch: '+name)
    return directory


def toolchain_identity(interpreter,osmium,compiler):
    interpreter=str(Path(interpreter).absolute())  # Preserve the venv symlink.
    compiler=str(Path(compiler).resolve());osmium=str(Path(osmium).resolve())
    query='import json,sys; print(json.dumps(dict(executable=sys.executable,version=sys.version,prefix=sys.prefix,base_prefix=sys.base_prefix)))'
    py=json.loads(subprocess.check_output([interpreter,'-c',query],text=True,timeout=10))
    py.update(requested_executable=interpreter,binary_path=str(Path(interpreter).resolve()),binary_sha256=digest(interpreter))
    version=subprocess.check_output([compiler,'--version'],text=True,timeout=10)
    libenv={**os.environ,'LD_LIBRARY_PATH':str(Path(osmium).parent.parent/'lib')}
    ldd=subprocess.check_output(['/usr/bin/ldd',osmium],text=True,env=libenv,timeout=10)
    if 'not found' in ldd:raise ValueError('Unresolved osmium dynamic library')
    libs={}
    for line in ldd.splitlines():
        match=re.search(r'(?:=>\s+)?(/[^\s]+)\s+\(',line)
        if match:
            path=Path(match[1]).resolve();libs[str(path)]=digest(path)
    if not libs:raise ValueError('No osmium dynamic library identities resolved')
    return {'interpreter':py,'compiler':{'path':compiler,'sha256':digest(compiler),'version':version,'flags':COMPILER_FLAGS},
            'osmium':{'path':osmium,'sha256':digest(osmium),'libraries':libs}}


def owned_scratch(out):
    if out.resolve()!=out or not out.is_dir() or out.stat().st_uid!=os.getuid():
        raise ValueError('Stage artifacts directory is not owned/nonsymlink')
    scratch=out/'scratch'
    if any(os.environ.get(key)!=str(scratch) for key in ('TMPDIR','TMP','TEMP')):raise ValueError('TMPDIR must be owned stage scratch')
    if not scratch.exists():
        scratch.mkdir(mode=0o700,exist_ok=False)
    if scratch.is_symlink() or scratch.stat().st_uid!=os.getuid() or stat.S_IMODE(scratch.stat().st_mode)!=0o700:
        raise ValueError('Invalid scratch ownership/mode')
    return scratch


def stream_download(url,path,limit):
    # No retries; partial bytes remain forensic evidence if bounded stage fails.
    count=0
    with urlopen(url,timeout=30) as r, Path(path).open('xb') as f:
        if r.url != url:raise ValueError('Unexpected source redirect; review destination')
        while True:
            block=r.read(1024*1024)
            if not block:break
            count+=len(block)
            if count>limit:raise ValueError('Source exceeds frozen byte bound')
            f.write(block)
    return count


def copy_frozen_input(source_path, destination, limit):
    """Bounded copy of a separately frozen local source; never trust path alone."""
    source_path=Path(source_path)
    if (not source_path.is_absolute() or source_path.resolve()!=source_path
        or not source_path.is_file() or source_path.stat().st_size>limit):
        raise ValueError('Invalid frozen local source path or size')
    count=0
    with source_path.open('rb') as src, destination.open('xb') as dst:
        for block in iter(lambda:src.read(1024*1024),b''):
            count+=len(block)
            if count>limit:raise ValueError('Frozen local source exceeds byte bound')
            dst.write(block)
        dst.flush();os.fsync(dst.fileno())
    return count


def acquire_source_input(spec, key, url, destination, limit):
    if spec.get(key) is not None:
        return copy_frozen_input(spec[key],destination,limit)
    return stream_download(url,destination,limit)


def source(out,prior,config,osmium,fixture):
    import shapely.geometry
    from envelope.boundary import read_poly
    stamp=config['source']['snapshot_timestamp']
    raw=out/'source.osm.pbf'; poly=out/'boundary.poly'
    if fixture:
        xml=['<osm version="0.6" generator="HiRoute synthetic fixture">']
        for i in range(130):
            xml.append(f'<node id="{i+1}" version="1" lat="36" lon="{118+i*.001:.6f}"><tag k="amenity" v="charging_station"/></node>')
        xml+=['<way id="1000" version="1">']+[f'<nd ref="{i+1}"/>' for i in range(130)]
        xml+=['<tag k="highway" v="residential"/><tag k="maxspeed" v="30"/></way>',
              '<way id="1001" version="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="street_lamp"/></way>',
              '<way id="1002" version="1"><nd ref="3"/><nd ref="4"/><nd ref="5"/><nd ref="3"/><tag k="highway" v="yes"/><tag k="building" v="yes"/><tag k="amenity" v="shelter"/></way></osm>']
        (out/'fixture.osm').write_text('\n'.join(xml))
        native(osmium,'cat',out/'fixture.osm','--output-header=osmosis_replication_timestamp='+stamp,'-o',raw)
        poly.write_text('synthetic\n1\n117 35\n119 35\n119 37\n117 37\n117 35\nEND\nEND\n')
        publisher_md5=None
    else:
        s=config['source']; url=s['url']; partial=out/'source.partial.pbf'
        if acquire_source_input(s,'local_pbf',url,partial,s['expected_size_bytes'])!=s['expected_size_bytes']:raise ValueError('Source size mismatch')
        md5file=out/'publisher.md5';acquire_source_input(s,'local_publisher_md5',url+'.md5',md5file,4096)
        publisher_md5=md5file.read_text().split()[0]
        if not re.fullmatch('[0-9a-f]{32}',publisher_md5):raise ValueError('Invalid publisher MD5')
        if s.get('publisher_md5') is not None and publisher_md5!=s['publisher_md5']:raise ValueError('Frozen publisher MD5 mismatch')
        h=hashlib.md5()
        with partial.open('rb') as f:
            for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
        if h.hexdigest()!=publisher_md5:raise ValueError('Publisher MD5 mismatch')
        if digest(partial)!=s['sha256']:raise ValueError('Frozen source SHA256 mismatch')
        partial.rename(raw)
        acquire_source_input(s,'local_polygon','https://download.geofabrik.de/asia/china/shandong.poly',poly,16*1024*1024)
        if s.get('polygon_sha256') is None or digest(poly)!=s['polygon_sha256']:
            raise ValueError('Frozen provider polygon SHA256 required and must match')
    info=json.loads(native(osmium,'fileinfo','-j',raw))
    if info['header']['option']['osmosis_replication_timestamp']!=stamp:raise ValueError('Source timestamp mismatch')
    polygon=read_poly(poly)
    if not fixture:
        lo,la,hi,ha=config['geometry']['public_validation_box_lon_lat']
        a,b,c,d=polygon.bounds
        if a<lo or b<la or c>hi or d>ha:raise ValueError('Boundary outside predeclared projection validation extent')
    write(out/'boundary.geojson',{'type':'Feature','properties':{},'geometry':shapely.geometry.mapping(polygon)})
    write(out/'sources.json',{'synthetic':fixture,'source_url':None if fixture else config['source']['url'],
        'sha256':digest(raw),'size_bytes':raw.stat().st_size,'publisher_md5':publisher_md5,
        'snapshot_timestamp':stamp,'polygon_sha256':digest(poly),'polygon_snapshot_matched':False,'acquired_at_utc':None if fixture else datetime.now(timezone.utc).isoformat(),
        'acquisition_method':None if fixture else {key:('verified_local_copy' if config['source'].get(key) else 'provider_download') for key in ('local_pbf','local_polygon','local_publisher_md5')},
        'polygon_url':None if fixture else 'https://download.geofabrik.de/asia/china/shandong.poly',
        'license':'synthetic' if fixture else config['source']['license'],'attribution':config['source']['attribution']})


def graph(out,prior,config,osmium,fixture):
    from pyrosm.config import NetworkFilter
    from bounded_io import literal_exclusions, progress, DENSE_FORMAT
    import yaml
    from way_partition import build_partitioned_graph
    import pandas as pd
    from graph.road_graph import IgraphRoadGraph
    src=verify_stage(prior['source'],'source')
    report=out/'graph_progress.json'
    progress(report,'road_filter_started')
    all_roads=out/'highways-all.pbf'
    native(osmium,'tags-filter',src/'source.osm.pbf','w/highway','-f',DENSE_FORMAT,'-o',all_roads)
    filtered=out/'highways-filtered.pbf'
    exclusions=literal_exclusions(NetworkFilter.driving)
    native(osmium,'tags-filter',all_roads,*exclusions,'--invert-match','-f',DENSE_FORMAT,'-o',filtered)
    roads=out/'highways.pbf'
    native(osmium,'tags-filter',filtered,'w/highway','-f',DENSE_FORMAT,'-o',roads)
    native(osmium,'check-refs',roads)
    routing=yaml.safe_load((ROOT/'configs/routing.yaml').read_text())
    progress(report,'parser_started',engine='whole_way_partitioned_out_of_core',workers=1,
             literal_exclusions=exclusions,max_way_refs=50000,max_ways=10000)
    audit=build_partitioned_graph(roads,out/'scratch',out,routing,osmium,report)
    # Validate the same graph contract after all parser heaps have exited. Only
    # routing columns are needed; never load the full global tag/geometry table.
    nodes=pd.read_parquet(out/'nodes.parquet')
    edges=pd.read_parquet(out/'edges.parquet',columns=['edge_id','source','target','length_m','travel_time_s'])
    g=IgraphRoadGraph(nodes,edges)
    node_count,edge_count=g.node_count,g.edge_count
    del g,nodes,edges
    progress(report,'graph_files_written',nodes=node_count,edges=edge_count)
    write(out/'metadata.json',{'schema_version':1,'crs':'EPSG:4326','directed':True,'parallel_edges':True,
        'all_components_retained':True,'simplified':False,'node_count':node_count,'edge_count':edge_count,
        'source_sha256':digest(src/'source.osm.pbf'),'routing_config_sha256':digest(ROOT/'configs/routing.yaml'),
        'audit':audit,'files':{n:{'sha256':digest(out/n),'size_bytes':(out/n).stat().st_size} for n in ('nodes.parquet','edges.parquet')}})


def inventory(out,prior,config,osmium,fixture):
    import pandas as pd
    import shapely.geometry
    import yaml
    from opportunity.taxonomy import filter_expressions
    from prepare_opportunity_data import object_catalogue,parse_geometry
    src=verify_stage(prior['source'],'source')
    cfg=yaml.safe_load((ROOT/'configs/opportunity.yaml').read_text())['extraction']
    filtered=out/'opportunities-filtered.pbf'; crop=out/'opportunities.pbf'
    native(osmium,'tags-filter',src/'source.osm.pbf',*filter_expressions(cfg),'-o',filtered)
    native(osmium,'extract','-p',src/'boundary.geojson','-s',cfg['strategy'],'-S','types='+cfg['relation_types'],filtered,'-o',crop)
    native(osmium,'check-refs',crop)
    catalogue=object_catalogue(osmium,crop,cfg)
    geo=out/'geometry.geojsonseq';native(osmium,'export',crop,'-u','type_id','-f','geojsonseq','--show-errors','-o',geo)
    polygon=shapely.geometry.shape(json.loads((src/'boundary.geojson').read_text())['geometry'])
    rows,excluded,errors=parse_geometry(geo,catalogue,polygon,config['geometry']['projection'])
    if not rows:raise ValueError('DATA_LIMITED: empty opportunity inventory')
    for row in rows:
        row['source_datasets']=['synthetic' if fixture else 'shandong-261016']
        row['snapshot_timestamp']=config['source']['snapshot_timestamp']
        row['original_tags']=json.dumps(row['original_tags'],sort_keys=True,separators=(',',':'),ensure_ascii=False)
    pd.DataFrame(rows).to_parquet(out/'inventory.parquet',index=False)
    write(out/'exclusions.json',{'rows':excluded,'geometry_errors':errors,'catalogue_count':len(catalogue)})


def sites(out,prior,config,osmium,fixture):
    import pandas as pd
    import yaml
    from graph.road_graph import IgraphRoadGraph
    from opportunity.attachment import attach_opportunities
    from opportunity.models import Opportunity,OpportunityId,Provenance
    from stopplan4r.sites import build_sites
    gdir=verify_stage(prior['graph'],'graph'); idir=verify_stage(prior['inventory'],'inventory')
    nodes=pd.read_parquet(gdir/'nodes.parquet');edges=pd.read_parquet(gdir/'edges.parquet');g=IgraphRoadGraph(nodes,edges)
    table=pd.read_parquet(idir/'inventory.parquet')
    ops=[Opportunity(OpportunityId(r.osm_type,int(r.osm_id)),float(r.lat),float(r.lon),frozenset(r.capabilities),r.subtype,
        json.loads(r.original_tags),Provenance(tuple(r.source_datasets),r.snapshot_timestamp,r.geometry_method)) for r in table.itertuples()]
    cfg=yaml.safe_load((ROOT/'configs/opportunity.yaml').read_text())['attachment']
    attached=attach_opportunities(ops,g,edges.highway.to_numpy(),cfg)
    attachments=pd.DataFrame([{'osm_type':o.identity.osm_type,'osm_id':o.identity.osm_id,'access_node':o.access_node,
        'access_osm_node_id':o.access_osm_node_id,'access_distance_m':o.access_distance_m,'attachment_status':o.attachment_status} for o in attached])
    support=yaml.safe_load((ROOT/'configs/stopplan_4r.yaml').read_text())['support']
    static,local,stats=build_sites(table,attachments,support['radii_m'],support['primary_radius_m'])
    for filename,t in [('attachments.parquet',attachments),('stop_sites.parquet',static),('local_support.parquet',local)]:
        t.to_parquet(out/filename,index=False,compression='zstd')
    rebuilt,rebuilt_local,_=build_sites(table.iloc[::-1],attachments.iloc[::-1],support['radii_m'],support['primary_radius_m'])
    for filename,t in [('stop_sites',rebuilt),('local_support',rebuilt_local)]:
        t.to_parquet(out/(filename+'_rebuild.parquet'),index=False,compression='zstd')
        if digest(out/(filename+'.parquet'))!=digest(out/(filename+'_rebuild.parquet')):raise ValueError('Site reorder rebuild mismatch')
    write(out/'site_build.json',{'site_count':len(static),'attached_count':int(static.attachment_status.eq('attached').sum()),
        'byte_identical_rebuild':True,'support_stats':stats})


def hierarchy(out,prior,config,osmium,fixture):
    import numpy as np
    import pandas as pd
    from hierarchy4r.tree import tree_bytes,validate_tree
    gdir=verify_stage(prior['graph'],'graph');sdir=verify_stage(prior['sites'],'sites')
    nodes=pd.read_parquet(gdir/'nodes.parquet',columns=['node_id','osm_node_id']).sort_values('node_id')
    if not np.array_equal(nodes.node_id,np.arange(len(nodes))) or not nodes.osm_node_id.is_unique:raise ValueError('Graph identity invalid')
    if len(nodes)>np.iinfo(np.int32).max:raise ValueError('Original hierarchy int32 capacity exceeded')
    rank=np.empty(len(nodes),dtype=np.int32);rank[np.argsort(nodes.osm_node_id.to_numpy(),kind='stable')]=np.arange(len(nodes),dtype=np.int32)
    table=pd.read_parquet(sdir/'stop_sites.parquet')
    table=table[table.attachment_status.eq('attached') & table.access_node.notna()].sort_values('site_id').reset_index(drop=True)
    if table.empty:raise ValueError('DATA_LIMITED: no attached Sites')
    access=rank[table.access_node.to_numpy(dtype=np.int64)]
    edges=pd.read_parquet(gdir/'edges.parquet',columns=['source','target'])
    with (out/'topology.bin').open('xb') as f:
        np.array([len(nodes),len(edges),len(table)],dtype=np.int64).tofile(f)
        np.column_stack([rank[edges.source.to_numpy()],rank[edges.target.to_numpy()]]).astype(np.int32).tofile(f);access.tofile(f)
    del edges,nodes
    cpp=ROOT/'src/hierarchy4r/bisection.cpp'
    compiler=json.loads(os.environ['HIROUTE_TOOLCHAIN_IDENTITY'])['compiler']
    subprocess.run([compiler['path'],*compiler['flags'],str(cpp),'-o',str(out/'bisection')],check=True)
    for label in ('primary','rebuild'):
        subprocess.run([str(out/'bisection'),str(out/'topology.bin'),str(out/(label+'_cells.bin')),str(out/(label+'_regions.csv')),'64'],check=True)
    for suffix in ('cells.bin','regions.csv'):
        if digest(out/('primary_'+suffix))!=digest(out/('rebuild_'+suffix)):raise ValueError('Hierarchy rebuild mismatch')
    leaf=np.fromfile(out/'primary_cells.bin',dtype=np.int32)[access];regions=pd.read_csv(out/'primary_regions.csv')
    result=[dict(parent=int(r.parent),depth=int(r.depth),children=[] if r.left<0 else [int(r.left),int(r.right)],members=[],
        road_node_count=int(r.nodes),early_leaf_reason='coattached_at_one_road_anchor' if r.reason else None) for r in regions.itertuples()]
    for i,l in enumerate(leaf):result[l]['members'].append(i)
    for i in reversed(range(len(result))):
        if result[i]['children']:result[i]['members']=sorted(j for c in result[i]['children'] for j in result[c]['members'])
    tree=dict(site_ids=list(table.site_id),regions=result,capacity=64,branch_factor=2,mechanism='deterministic recursive unweighted topology BFS bisection')
    validate_tree(tree);(out/'hierarchy.json').write_bytes(tree_bytes(tree))
    table[['site_id','access_node']].assign(leaf_region=leaf).to_parquet(out/'site_membership.parquet',index=False)
    write(out/'hierarchy_provenance.json',{'global_all_graph_nodes':True,'all_attached_sites':True,'byte_identical_rebuild':True,
        'source_sha256':digest(cpp),'hierarchy_sha256':digest(out/'hierarchy.json')})

PHASES={'source':source,'graph':graph,'inventory':inventory,'sites':sites,'hierarchy':hierarchy}


def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--fixture',action='store_true')
    p.add_argument('--phase',choices=PHASES,required=True);p.add_argument('--prior',default='{}');p.add_argument('--osmium',required=True)
    args=p.parse_args();gate(args.fixture)  # Before reading config or any stage data.
    for line in (Path(__file__).parent/'installed.txt').read_text().splitlines():
        name,version=line.split('==')
        if importlib.metadata.version(name)!=version:raise ValueError('Pinned dependency version mismatch: '+name)
    if not native(args.osmium,'--version').startswith('osmium version 1.18.0\n'):raise ValueError('Pinned osmium version mismatch')
    config_path=Path(__file__).parent/'config.json'
    if not args.fixture:
        from experiments.m6h_manifest_v1.recovery_runtime import preprocessing_config_path
        config_path=preprocessing_config_path()
    config=json.loads(config_path.read_text())
    out=Path(os.environ['HIROUTE_OUTPUT_DIR'])
    scratch=owned_scratch(out)
    expected_tools=json.loads(os.environ['HIROUTE_TOOLCHAIN_IDENTITY'])
    actual_tools=toolchain_identity(sys.executable,args.osmium,expected_tools['compiler']['path'])
    if actual_tools!=expected_tools:raise ValueError('Toolchain identity changed')
    prior=json.loads(args.prior)
    if set(prior)!=set(list(PHASES)[:list(PHASES).index(args.phase)]):raise ValueError('Prior phase set mismatch')
    for phase,identity in prior.items():
        if identity['synthetic'] is not args.fixture:raise ValueError('Synthetic/real stage mismatch')
        verify_stage(identity,phase)
    PHASES[args.phase](out,prior,config,args.osmium,args.fixture)
    files={str(p.relative_to(out)):{'sha256':digest(p),'size_bytes':p.stat().st_size} for p in sorted(out.rglob('*')) if p.is_file()}
    scratch_files=[str(p.relative_to(scratch)) for p in sorted(scratch.rglob('*')) if p.is_file()]
    write(out/'artifact_manifest.json',{'schema_version':1,'phase':args.phase,'synthetic':args.fixture,'files':files,'prior':prior,
        'config_sha256':digest(config_path),'implementation_sha256':digest(Path(__file__)),'core_source_contract':code_contract(),
        'versions':{n:importlib.metadata.version(n) for n in ('pyrosm','pyproj','shapely','numpy','pandas','pyarrow','igraph')},
        'osmium_version':native(args.osmium,'--version'),'osmium_binary_sha256':digest(args.osmium),'toolchain_identity':actual_tools,
        'scratch':{'path':str(scratch),'owned_uid':os.getuid(),'mode':'0700','retained_files':scratch_files,'inside_supervised_artifacts':True}})
    for item in out.rglob('*'):
        if item.is_file():item.chmod(0o444 if not os.access(item,os.X_OK) else 0o555)
    write(Path(os.environ['HIROUTE_WORKER_RECEIPT']),{'status':'COMPLETED','result':{'phase':args.phase,
        'artifact_manifest_sha256':digest(out/'artifact_manifest.json'),'synthetic':args.fixture}})

if __name__=='__main__':main()
