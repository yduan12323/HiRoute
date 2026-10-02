"""Milestone 4B data readers, exclusively reading frozen previous outputs."""
import json
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from _common import ROOT,sha256,read_config
from opportunity.models import OpportunityId
from opportunity.regions import fingerprint
from microplan.models import OpportunityArrays,LocalPairs
from microplan.generation import CAPABILITY_BITS,task_mask

TYPE_CODES={'node':0,'way':1,'relation':2}


def identity_keys(types, ids):
    return np.asarray(ids)*4 + pd.Series(types).map(TYPE_CODES).to_numpy()


def read_opportunities(config):
    old=ROOT/config['frozen_region_dir']
    inventory=pd.read_parquet(old/'opportunity_inventory.parquet',columns=[
        'osm_type','osm_id','lat','lon','capabilities','geometry_type','geometry_method'])
    attachment=pd.read_parquet(old/'opportunity_attachment.parquet')
    assert np.array_equal(identity_keys(inventory.osm_type,inventory.osm_id),identity_keys(attachment.osm_type,attachment.osm_id))
    table=inventory.join(attachment.drop(columns=['osm_type','osm_id']))
    table=table[table.attachment_status=='attached'].reset_index(drop=True)
    # Stable lexical OSM type/id order, independent of physical inventory ordering.
    table=table.sort_values(['osm_type','osm_id']).reset_index(drop=True)
    table['opportunity_index']=np.arange(len(table))
    low=(table.access_distance_m<=config['access']['low_risk_snap_m']) & table.geometry_type.isin(config['access']['low_risk_geometry_types'])
    table['access_risk']=np.where(low,'low_access_risk','uncertain_access')
    identities=tuple(OpportunityId(t,int(i)) for t,i in zip(table.osm_type,table.osm_id))
    masks=np.array([sum(CAPABILITY_BITS.get(c,0) for c in caps) for caps in table.capabilities],dtype=np.int8)
    arrays=OpportunityArrays(identities,table.access_node.to_numpy(np.int64),masks,(~low).to_numpy(np.int8))
    lookup=pd.Index(identity_keys(table.osm_type,table.osm_id))
    return table,arrays,lookup


def candidate_pairs(config,opportunities,lookup):
    old=ROOT/config['frozen_region_dir']
    previous=read_config(config['opportunity_config'])
    if config['bundles']['geographic_radius_m']>previous['network']['maximum_candidate_radius_m'] or config['bundles']['directed_shortest_distance_cutoff_m']>previous['network']['maximum_search_distance_m']:
        raise ValueError('Bundle cutoffs exceed verified sparse-neighbor completeness; create a new independently validated neighbor cache')
    pairs=pd.read_parquet(old/'local_neighbor_pairs.parquet',columns=[
        'first_type','first_id','second_type','second_id','geographic_m','forward_m','reverse_m'])
    a=lookup.get_indexer(identity_keys(pairs.first_type,pairs.first_id))
    b=lookup.get_indexer(identity_keys(pairs.second_type,pairs.second_id))
    assert (a>=0).all() and (b>=0).all()
    eligible=np.zeros(len(pairs),dtype=bool)
    caps=opportunities.capability_masks
    for task in config['tasks'].values():
        if len(task['required_capabilities'])!=2:continue
        mask=sum(CAPABILITY_BITS[c] for c in task['required_capabilities'])
        eligible |= (((caps[a]|caps[b])&mask)==mask)&((caps[a]&mask)!=0)&((caps[b]&mask)!=0)
    distance=config['bundles']['directed_shortest_distance_cutoff_m']
    eligible &= pairs.geographic_m.to_numpy()<=config['bundles']['geographic_radius_m']
    eligible &= (pairs.forward_m.to_numpy()<=distance)|(pairs.reverse_m.to_numpy()<=distance)
    return a[eligible],b[eligible],pairs.geographic_m.to_numpy()[eligible],pairs.forward_m.to_numpy()[eligible],pairs.reverse_m.to_numpy()[eligible]


def prepare_pairs(config,router,opportunities,lookup,result):
    contract={'bundles':config['bundles'],'tasks':config['tasks'],
              'source_pair_sha256':sha256(ROOT/config['frozen_region_dir']/'local_neighbor_pairs.parquet'),
              'inventory_sha256':sha256(ROOT/config['frozen_region_dir']/'opportunity_attachment.parquet'),
              'native':router.provenance['source_sha256']}
    meta_path=result/'local_costs.json';path=result/'local_costs.parquet'
    if meta_path.exists():
        meta=json.loads(meta_path.read_text())
        if meta['contract']!=contract or meta['sha256']!=sha256(path):
            raise ValueError('4B local-cost cache contract mismatch; use a distinct results directory')
        t=pd.read_parquet(path)
        return LocalPairs(*(t[c].to_numpy() for c in t.columns)),meta
    import time
    start=time.perf_counter();a,b,geo,df,dr=candidate_pairs(config,opportunities,lookup)
    screening_seconds=time.perf_counter()-start
    dmax=config['bundles']['directed_shortest_distance_cutoff_m']
    f=np.flatnonzero(df<=dmax);r=np.flatnonzero(dr<=dmax)
    time_start=time.perf_counter()
    costs,lengths=router.pairs(np.concatenate([opportunities.access_nodes[a[f]],opportunities.access_nodes[b[r]]]),
                              np.concatenate([opportunities.access_nodes[b[f]],opportunities.access_nodes[a[r]]]),
                              config['bundles']['directed_shortest_time_cutoff_s'])
    tf,tr,lf,lr=[np.full(len(a),np.inf) for _ in range(4)]
    tf[f],tr[r],lf[f],lr[r]=costs[:len(f)],costs[len(f):],lengths[:len(f)],lengths[len(f):]
    routing_seconds=time.perf_counter()-time_start
    pairs=LocalPairs(a,b,geo,df,dr,tf,tr,lf,lr)
    pd.DataFrame({name:getattr(pairs,name) for name in pairs.__dataclass_fields__}).to_parquet(path,index=False,compression='zstd')
    meta={'contract':contract,'sha256':sha256(path),'pair_count':len(a),
          'ordered_queries':len(costs),'finite_ordered_local_costs':int(np.isfinite(costs).sum()),
          'screening_seconds':screening_seconds,'exact_local_routing_seconds':routing_seconds,
          'distinct_query_access_nodes':len(np.unique(np.concatenate([opportunities.access_nodes[a[f]],opportunities.access_nodes[b[r]]])))}
    meta_path.write_text(json.dumps(meta,indent=2)+'\n')
    return pairs,meta


class TableWriter:
    """Streaming explicit dtype alignment avoids first-empty/null schema hazards."""
    def __init__(self,path):self.path=path;self.writer=None
    def write(self,frame):
        if isinstance(frame,list):frame=pd.DataFrame(frame)
        if frame.empty:return
        table=pa.Table.from_pandas(frame,preserve_index=False)
        # All text missing values stay nullable strings; all diagnostic cost
        # fields are explicitly floats before the first group is serialized.
        for i,field in enumerate(table.schema):
            if pa.types.is_null(field.type):table=table.set_column(i,field.name,table[field.name].cast(pa.string()))
        if self.writer is None:self.writer=pq.ParquetWriter(self.path,table.schema,compression='zstd')
        self.writer.write_table(table.cast(self.writer.schema))
    def close(self):
        if self.writer:self.writer.close()
