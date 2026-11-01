"""Bounded provincial Site audit/supplement; no planner or road routing calls."""
from __future__ import annotations
import argparse
from collections import Counter
import gc
import hashlib
import json
from pathlib import Path
import resource
import time

from hiroute.data.charging_coverage import AttachmentIndex, charging_evidence
from real_scale_inputs import pretty_array, write_new


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def extract(path,boundary,historical_C):
    """Three streaming passes; cache only tagged objects/member node positions."""
    import osmium
    from shapely.geometry import Point,LineString,Polygon
    from shapely.ops import polygonize,unary_union
    from hiroute.data.shandong import _representative_wgs84
    objects={};ways={};coordinates={}
    class Tagged(osmium.SimpleHandler):
        def retain(self,kind,obj):
            tags={t.k:t.v for t in obj.tags};ident=f'{kind}/{obj.id}'
            ev=charging_evidence(tags)
            if not ev['charging_signal'] and ident not in historical_C:return
            row=dict(site_id=ident,tags=tags,evidence=ev)
            if kind=='node':
                if obj.location.valid():
                    coordinates[obj.id]=(obj.location.lon,obj.location.lat)
                    row['node']=obj.id
            elif kind=='way':
                ways[obj.id]=tuple(n.ref for n in obj.nodes);row['way']=obj.id
            else:row['members']=[(m.type,m.ref,m.role) for m in obj.members]
            objects[ident]=row
        def node(self,n):self.retain('node',n)
        def way(self,w):self.retain('way',w)
        def relation(self,r):self.retain('relation',r)
    keys=['amenity','man_made','charging']+[p+':'+k for p in
        ('disused','abandoned','demolished','removed','proposed','construction')
        for k in ('amenity','man_made')]
    osmium.apply(str(path),osmium.filter.KeyFilter(*keys),Tagged())
    required_ways={m[1] for o in objects.values() for m in o.get('members',[]) if m[0]=='w'}
    class Members(osmium.SimpleHandler):
        def way(self,w):
            if w.id in required_ways:ways[w.id]=tuple(n.ref for n in w.nodes)
    if required_ways:Members().apply_file(str(path))
    required_nodes={n for ns in ways.values() for n in ns}
    class Locations(osmium.SimpleHandler):
        def node(self,n):
            if n.id in required_nodes and n.location.valid():
                coordinates[n.id]=(n.location.lon,n.location.lat)
    if required_nodes:Locations().apply_file(str(path))
    def line(ident):
        ns=ways[ident]
        return LineString([coordinates[n] for n in ns])
    records=[];geometries={};errors=[]
    for ident,row in sorted(objects.items()):
        try:
            if 'node' in row:geom=Point(coordinates[row['node']])
            elif 'way' in row:
                ns=ways[row['way']];xy=[coordinates[n] for n in ns]
                geom=Polygon(xy) if len(ns)>=4 and ns[0]==ns[-1] else LineString(xy)
            elif 'members' in row:
                outer=[line(ref) for typ,ref,role in row['members'] if typ=='w' and role in ('','outer')]
                inner=[line(ref) for typ,ref,role in row['members'] if typ=='w' and role=='inner']
                geom=unary_union(list(polygonize(unary_union(outer))))
                if inner:geom=geom.difference(unary_union(list(polygonize(unary_union(inner)))))
            else:raise ValueError('source geometry unavailable')
            if geom.is_empty or not geom.is_valid:raise ValueError('empty/invalid source geometry')
            lon,lat,method=_representative_wgs84(geom)
            if not boundary.covers(Point(lon,lat)):
                row['evidence']['exclusion_reasons'].append('outside_frozen_boundary')
                row['evidence']['modeled_C_eligible']=False
            out=dict(site_id=ident,lon=lon,lat=lat,geometry_method=method,
                evidence=row['evidence'],source_tags=row['tags'],geometry=geom.__geo_interface__)
            records.append(out);geometries[ident]=geom
        except (KeyError,ValueError,RuntimeError) as exc:
            errors.append(dict(site_id=ident,error=str(exc),evidence=row['evidence']))
    # An individual point is never promoted to a station. Record containment
    # aliases among station nodes/areas, preferring a historical identity. This
    # is an explicit workload deduplication rule, not a safe optimization theorem.
    eligible=[r for r in records if r['evidence']['modeled_C_eligible']]
    priority=lambda r:(0 if r['site_id'] in historical_C else 1,
        -int(geometries[r['site_id']].geom_type in ('Polygon','MultiPolygon')),r['site_id'])
    retained=[];aliases={}
    for row in sorted(eligible,key=priority):
        geom=geometries[row['site_id']]
        duplicate=None
        for old in retained:
            other=geometries[old['site_id']]
            same=geom.equals(other)
            contained=(geom.geom_type=='Point' and other.geom_type in ('Polygon','MultiPolygon') and other.covers(geom)) or (other.geom_type=='Point' and geom.geom_type in ('Polygon','MultiPolygon') and geom.covers(other))
            if same or contained:
                a=row['source_tags'].get('operator');b=old['source_tags'].get('operator')
                if a and b and a!=b:continue
                duplicate=old['site_id'];break
        if duplicate:aliases[row['site_id']]=duplicate
        else:retained.append(row)
    reader=osmium.io.Reader(str(path))
    timestamp=reader.header().get('osmosis_replication_timestamp');reader.close()
    return records,retained,aliases,errors,dict(replication_timestamp=timestamp)


def attachment_index(graph_path,node_count,excluded):
    import numpy as np
    ids=[];lookup={};xy=np.empty((node_count,2),dtype=np.float64)
    for i,row in enumerate(pretty_array(graph_path,'nodes')):
        if i>=node_count:raise ValueError('graph node count exceeds provenance')
        ident=row['node_id']
        if ident in lookup:raise ValueError('duplicate graph node identity')
        lookup[ident]=i;ids.append(ident);xy[i]=(row['lon'],row['lat'])
    if len(ids)!=node_count:raise ValueError('graph node count differs from provenance')
    incoming=np.zeros(node_count,dtype=np.bool_);outgoing=incoming.copy();edges=0
    for row in pretty_array(graph_path,'directed_edges'):
        edges+=1
        if row['highway'] not in excluded:
            outgoing[lookup[row['source']]]=True;incoming[lookup[row['target']]]=True
    selected=np.flatnonzero(incoming & outgoing)
    chosen_ids=[ids[int(i)] for i in selected];chosen_xy=xy[selected]
    del ids,lookup,xy,incoming,outgoing,selected
    gc.collect()
    index=AttachmentIndex(chosen_ids,chosen_xy)
    return index,dict(nodes=node_count,directed_edges=edges,eligible_nodes=len(chosen_ids))


def main(args):
    started,cpu=time.monotonic(),time.process_time()
    output=Path(args.output);output.mkdir(exist_ok=False)
    cfg=json.loads(Path(args.config).read_text());inputs=Path(args.inputs)
    graph=inputs/'historical-shared-graph.json';raw=inputs/'shandong-261031.osm.pbf';poly=inputs/'shandong.poly'
    for path,expected in ((graph,cfg['historical']['graph_sha256']),(poly,cfg['historical']['boundary_sha256'])):
        if digest(path)!=expected:raise ValueError('historical scientific input identity differs: '+str(path))
    if raw.stat().st_size!=cfg['fallback_source']['head_content_length']:raise ValueError('incomplete provincial PBF')
    raw_hash=digest(raw)
    source=Path(args.historical_inputs)
    old_sites=json.loads((source/'shared-sites.json').read_text())
    bindings=json.loads((source/'site-bindings.json').read_text())
    if digest(source/'shared-sites.json')!=cfg['historical']['sites_sha256']:raise ValueError('historical Site input changed')
    from hiroute.data.shandong_spatial import read_osm_poly
    from pyproj import Geod
    old_C={r['site_id'] for r in old_sites if 'C' in r['capabilities']}
    records,stations,aliases,errors,header=extract(raw,read_osm_poly(poly),old_C)
    write_new(output/'source-evidence.json',dict(records=records,station_aliases=aliases,geometry_errors=errors))
    print(json.dumps(dict(stage='source_extracted',records=len(records),eligible_stations=len(stations),aliases=len(aliases),geometry_errors=len(errors))),flush=True)
    index,graph_info=attachment_index(graph,2986695,set(bindings['audit']['excluded_highway']))
    geod=Geod(ellps='WGS84');historical_results={};mismatches=[]
    for row in old_sites:
        result=index.attach(row,geod)
        if result:historical_results[row['site_id']]=result['node_id']
        expected=bindings['site_access_nodes'].get(row['site_id'])
        actual=None if result is None else result['node_id']
        if actual!=expected:mismatches.append(dict(site_id=row['site_id'],expected=expected,actual=actual))
    write_new(output/'historical-attachment-parity.json',dict(site_count=len(old_sites),attached=len(historical_results),mismatches=mismatches,graph=graph_info))
    if mismatches:raise ValueError('historical attachment parity failed; supplemented attachment path stopped')
    new_bindings=dict(bindings['site_access_nodes']);catalog=[dict(x) for x in old_sites]
    known={r['site_id'] for r in old_sites};added=[];unattached=[]
    # Add-only static catalog. Historical rows remain dated historical evidence;
    # negative current evidence is reported explicitly, never called live access.
    for row in stations:
        if row['site_id'] in known:continue
        result=index.attach(row,geod)
        site=dict(site_id=row['site_id'],lon=row['lon'],lat=row['lat'],amenity='charging_station',
            capabilities=['C'],transport_classes=['charge'],meal_count_500m=0,
            geometry_method=row['geometry_method'],source_sha256=raw_hash,
            service_support='not_assessed_no_CS_invented',availability='unknown')
        catalog.append(site);added.append(row['site_id'])
        if result:new_bindings[row['site_id']]=result['node_id']
        else:unattached.append(row['site_id'])
    current={r['site_id']:r for r in records}
    negative=[dict(site_id=i,reasons=current[i]['evidence']['exclusion_reasons'])
        for i in sorted(old_C & set(current)) if not current[i]['evidence']['modeled_C_eligible']]
    # Quarantine explicitly contradicted historical C capabilities in the new
    # version only. Preserve old S support; missing-current records stay dated
    # historical observations, never assertions of present operational status.
    bad={r['site_id'] for r in negative}|set(aliases)
    for row in catalog:
        if row['site_id'] in bad:row['capabilities']=[c for c in row['capabilities'] if c not in ('C','CS')]
    new_C=[r for r in catalog if 'C' in r['capabilities']]
    anchors={new_bindings[r['site_id']] for r in new_C if r['site_id'] in new_bindings}
    summary=dict(schema='hiroute.shandong_charging_coverage_result.v1',solver_called=False,road_queries_called=False,
        raw_sha256=raw_hash,raw_bytes=raw.stat().st_size,source_header=header,
        old_raw_station_count=len(old_C),old_attached_C_sites=sum(i in bindings['site_access_nodes'] for i in old_C),
        old_unique_C_anchors=len({bindings['site_access_nodes'][i] for i in old_C if i in bindings['site_access_nodes']}),
        source_object_records=len(records)+len(errors),
        raw_signal_records=sum(r['evidence']['charging_signal'] for r in records+errors),
        raw_current_station_tags=sum(r['evidence']['station_tag'] for r in records+errors),
        raw_charge_points=sum(r['evidence']['charge_point_tag'] for r in records+errors),
        modeled_eligible_station_records=len(stations),station_aliases=aliases,geometry_errors=errors,
        old_C_currently_contradicted=negative,old_C_absent_from_current_records=sorted(old_C-set(current)),
        additional_raw_station_sites=len(added),additional_unattached_sites=unattached,
        supplemented_C_sites=len(new_C),supplemented_attached_C_sites=sum(r['site_id'] in new_bindings for r in new_C),
        supplemented_unique_C_anchors=len(anchors),energy_N256_global_shortfall=max(0,256-len(anchors)),
        historical_attachment_parity=True,exclusion_counts=dict(Counter(reason for r in records for reason in r['evidence']['exclusion_reasons'])),
        cautions=['Mixed-date add-only static research catalog, not a live operational registry.',
            'Temporal changes are not proven historical extraction fixes.',
            'Charging curve is the existing common modeled default, not source-observed station performance.',
            'No new CS support, connector compatibility, four-charge feasibility or timing claim.',
            'Candidate restrictions/alias handling are declared workloads, not full-province safe reductions.'],
        preparation_wall_s=time.monotonic()-started,preparation_cpu_s=time.process_time()-cpu,
        peak_rss_platform_units=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    write_new(output/'shared-sites.json',catalog)
    audit={**bindings['audit'],'attached_sites':len(new_bindings),
        'unattached_site_ids':sorted(r['site_id'] for r in catalog if r['site_id'] not in new_bindings)}
    write_new(output/'site-bindings.json',dict(site_access_nodes=new_bindings,audit=audit,
        note='Original graph/attachment policy; new version adds source-evidenced C Sites and quarantines explicit contradictions. Historical files unchanged.'))
    write_new(output/'summary.json',summary)
    print(json.dumps(summary,sort_keys=True),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('config','inputs','historical-inputs','output'):p.add_argument('--'+name,required=True)
    main(p.parse_args())
