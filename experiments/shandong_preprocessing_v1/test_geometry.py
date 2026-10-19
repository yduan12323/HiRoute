"""Tiny synthetic geometry tests; no raw source, catalog or OD reads."""
import ast
from collections import Counter
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from pyproj import Proj, Transformer
import shapely
import shapely.geometry

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
# Isolate the actual production functions from CLI imports and their data tools.
source = ast.parse((ROOT/'scripts/prepare_opportunity_data.py').read_text())
selected = ast.Module(body=[n for n in source.body if isinstance(n, ast.FunctionDef)
                           and n.name in ('parse_geometry','export_identity')], type_ignores=[])
ns = dict(Transformer=Transformer, shapely=shapely, Counter=Counter, Path=Path, json=json)
exec(compile(selected, 'prepare_opportunity_data.py', 'exec'), ns)
parse = ns['parse_geometry']
CRS = json.loads((HERE/'config.json').read_text())['geometry']['projection']

class GeometryTests(unittest.TestCase):
    def test_legacy_default_exactly_matches_explicit(self):
        features = [{'type':'Feature','id':'n1','geometry':{'type':'Point','coordinates':[14.5,46]}}]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'fixture.geojsonseq'; path.write_text('\n'.join(map(json.dumps,features)))
            catalog = {('node',1):{'capabilities':['charge']}}
            polygon = shapely.geometry.box(14,45,15,47)
            self.assertEqual(parse(path,catalog,polygon),parse(path,catalog,polygon,'EPSG:3035'))

    def test_polygon_priority_and_line_midpoint(self):
        features = [
            {'id':'w5','geometry':{'type':'LineString','coordinates':[[118,36],[119,37]]}},
            {'id':'a10','geometry':{'type':'Polygon','coordinates':[[[118,36],[119,36],[119,37],[118,37],[118,36]]]}},
            {'id':'w7','geometry':{'type':'LineString','coordinates':[[118,36],[119,37]]}},
            {'id':'n9','geometry':{'type':'Point','coordinates':[130,45]}}]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'fixture.geojsonseq'; path.write_text('\n'.join(map(json.dumps,features)))
            cat = {('way',5):{},('way',7):{},('node',9):{}}
            rows,excluded,errors = parse(path,cat,shapely.geometry.box(114,34,123,39),CRS)
        self.assertEqual([r['osm_id'] for r in rows],[5,7])
        self.assertTrue(rows[0]['geometry_method'].endswith('point-on-surface'))
        self.assertTrue(rows[1]['geometry_method'].endswith('line midpoint'))
        self.assertEqual(excluded,[{'osm_type':'node','osm_id':9,'reason':'representative_outside_polygon'}])
        self.assertEqual(errors,{})
        for row in rows:
            self.assertTrue(shapely.from_wkb(row['geometry_wkb']).distance(shapely.Point(row['lon'],row['lat'])) < .02)

    def test_public_coordinate_projection_contract(self):
        config=json.loads((HERE/'config.json').read_text())['geometry']
        west,south,east,north=config['public_validation_box_lon_lat']
        self.assertEqual([west,south,east,north],[114,34,124,39])
        lon,lat=np.meshgrid(np.arange(west,east+.001,.25),np.arange(south,north+.001,.25))
        f=Proj(CRS).get_factors(lon,lat)
        self.assertLess(np.max(abs(f.meridional_scale-1)),.003)
        self.assertLess(np.max(abs(f.parallel_scale-1)),.003)
        x,y=Transformer.from_crs(4326,CRS,always_xy=True).transform(lon,lat)
        a,b=Transformer.from_crs(CRS,4326,always_xy=True).transform(x,y)
        self.assertTrue(np.isfinite(x).all() and np.isfinite(y).all())
        self.assertLess(np.max(abs(a-lon)),1e-10)
        self.assertLess(np.max(abs(b-lat)),1e-10)

if __name__ == '__main__': unittest.main()
