"""Portable synthetic catalog tests; production-fixture scope is in README.md."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from timecut5.frozen_candidate_catalog import build_catalog,file_sha
from timecut5.portable_candidate_policy import canonical,digest
class CatalogTests(unittest.TestCase):
 def fixture(self,r):
  sites=[dict(site_id='charge',access_node=1,anchor_id='road:1',effects=['C']),dict(site_id='meal',access_node=3,anchor_id='road:3',effects=['S'])]
  geo={'fixed_grid_candidates':[dict(site_id='o',lat=0,lon=0),dict(site_id='d',lat=0,lon=2)]};slate={'od':[dict(od_id=x,origin_site='o',destination_site='d',origin_anchor=0,destination_anchor=4) for x in ['OD00','OD02']]}
  paths={k:str(r/(k+'.json')) for k in ['sites','geo','slate','pools']}
  for k,v in [('sites',{}),('geo',geo),('slate',slate)]:Path(paths[k]).write_bytes(canonical(v))
  pools=dict(site_catalog_sha256=file_sha(paths['sites']),geographic_sha256=file_sha(paths['geo']),slate_sha256=file_sha(paths['slate']),pools=[dict(od_id=x,sites=sites,radius_m=1000,eligible_capable_site_count=3) for x in ['OD00','OD02']]);Path(paths['pools']).write_bytes(canonical(pools))
  rows=[]
  for sid,node,lon,lat,charge,meal in [('charge',1,1,0,True,0),('added',2,1.5,0,True,0),('meal',3,.5,0,False,1),('o',5,1,0,True,0),('endpointanchor',4,1,0,True,0),('outside',6,1,1,True,0)]:rows.append(dict(site_id=sid,access_node=node,lon=lon,lat=lat,transport_capabilities=['charge'] if charge else [],meal_count=meal))
  return dict(paths=paths,expected={k:file_sha(p) for k,p in paths.items()},baseline_sites=sites),pd.DataFrame(rows)
 def test_actual_od_parameter_and_original_exclusions(self):
  with tempfile.TemporaryDirectory() as tmp:
   args,rows=self.fixture(Path(tmp))
   for od in ['OD00','OD02']:
    with patch('pandas.read_parquet',return_value=rows):sites,e=build_catalog(**args,od_id=od,query=dict(case_id=od+'_tiny',origin='road:0',destination='road:4'))
    self.assertEqual([s['site_id'] for s in sites],['added','charge']);self.assertEqual(e['od_id'],od)
 def test_source_and_query_drift(self):
  with tempfile.TemporaryDirectory() as tmp:
   args,rows=self.fixture(Path(tmp));q=dict(case_id='OD00_tiny',origin='road:0',destination='road:4')
   with patch('pandas.read_parquet',return_value=rows),self.assertRaises(ValueError):build_catalog(**args,od_id='OD02',query=q)
   Path(args['paths']['sites']).write_text('changed')
   with self.assertRaises(ValueError):build_catalog(**args,od_id='OD00',query=q)
if __name__=='__main__':unittest.main()
