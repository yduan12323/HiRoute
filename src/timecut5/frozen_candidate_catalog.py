"""Authenticated original-corridor catalog, parameterized by a frozen OD.
Only metadata is read here; no graph, native router or reachability verdict.
"""
import json,math
from pathlib import Path
from .portable_candidate_policy import canonical,digest,ELIGIBILITY_SCHEMA,ELIGIBILITY_POLICY

def file_sha(path):return digest(Path(path).read_bytes())
def build_catalog(*,paths,expected,od_id,query,baseline_sites):
 if set(paths)!=set(expected) or set(paths)!={'sites','pools','geo','slate'}:raise ValueError('Catalog source set differs')
 def check():
  if any(file_sha(paths[k])!=expected[k] for k in paths):raise ValueError('Original catalog source drift')
 check()
 import pandas as pd
 import numpy as np
 pools=json.loads(Path(paths['pools']).read_bytes());geo=json.loads(Path(paths['geo']).read_bytes());slate=json.loads(Path(paths['slate']).read_bytes())
 if pools['site_catalog_sha256']!=expected['sites'] or pools['geographic_sha256']!=expected['geo'] or pools['slate_sha256']!=expected['slate']:raise ValueError('Catalog provenance chain differs')
 ps=[x for x in pools['pools'] if x['od_id']==od_id];ods=[x for x in slate['od'] if x['od_id']==od_id]
 if len(ps)!=1 or len(ods)!=1:raise ValueError('Unknown or duplicate frozen OD')
 p,od=ps[0],ods[0]
 if query['origin']!='road:'+str(od['origin_anchor']) or query['destination']!='road:'+str(od['destination_anchor']) or not query['case_id'].startswith(od_id+'_'):raise ValueError('Actual query does not match frozen OD')
 loc={x['site_id']:x for x in geo['fixed_grid_candidates']};a,b=loc[od['origin_site']],loc[od['destination_site']]
 sx=111320*math.cos(math.radians((a['lat']+b['lat'])/2));sy=111320;dx=(b['lon']-a['lon'])*sx;dy=(b['lat']-a['lat'])*sy;sq=dx*dx+dy*dy
 if not math.isfinite(sq) or sq<=0:raise ValueError('Degenerate original corridor')
 baseline={x['site_id']:x for x in baseline_sites};frozen={x['site_id']:x for x in p['sites']}
 if len(baseline)!=len(baseline_sites) or any(frozen.get(k)!=v for k,v in baseline.items()):raise ValueError('Baseline rows outside authenticated pool')
 eligible_count=0;rows=[];seen=set();found=set()
 for row in pd.read_parquet(paths['sites'],columns=['site_id','access_node','lat','lon','transport_capabilities','meal_count']).itertuples(index=False):
  if pd.isna(row.access_node):continue
  charge=isinstance(row.transport_capabilities,(list,tuple,np.ndarray)) and 'charge' in row.transport_capabilities;meal=pd.notna(row.meal_count) and row.meal_count>=1
  if not(charge or meal):continue
  if not all(math.isfinite(float(v)) for v in (row.lat,row.lon,row.access_node)) or int(row.access_node)!=row.access_node:raise ValueError('Invalid original catalog geometry')
  sid=str(row.site_id)
  if sid in seen:raise ValueError('Duplicate capable site ID')
  seen.add(sid);node=int(row.access_node)
  x=(row.lon-a['lon'])*sx;y=(row.lat-a['lat'])*sy;progress=(x*dx+y*dy)/sq;perp=abs(x*dy-y*dx)/math.sqrt(sq)
  eligible=(sid not in (od['origin_site'],od['destination_site']) and row.access_node not in (od['origin_anchor'],od['destination_anchor']) and 0<progress<1 and perp<=p['radius_m'])
  eligible_count+=int(eligible)
  effects=(['C'] if charge else [])+(['S'] if meal else [])+(['CS'] if charge and meal else [])
  simple=dict(site_id=sid,access_node=node,anchor_id='road:'+str(node),effects=effects)
  if sid in baseline:
   if not eligible or any(baseline[sid].get(k)!=v for k,v in simple.items()):raise ValueError('Baseline catalog semantics or eligibility changed')
   found.add(sid)
  if charge and eligible:rows.append(baseline.get(sid,simple))
 if eligible_count!=p['eligible_capable_site_count'] or found!=set(baseline):raise ValueError('Complete original catalog counts/membership differ')
 rows.sort(key=lambda x:x['site_id']);check()
 eligibility=dict(schema=ELIGIBILITY_SCHEMA,policy_version=ELIGIBILITY_POLICY,complete=True,source_sha256=expected,query_sha256=digest(canonical(query)),origin=query['origin'],destination=query['destination'],od_id=od_id,origin_site_id=od['origin_site'],destination_site_id=od['destination_site'],radius_m=str(p['radius_m']),eligible_charging_count=len(rows),eligible_candidate_sha256=digest(canonical([x['site_id'] for x in rows])),eligible_sites_sha256=digest(canonical(rows)))
 return rows,eligibility
