from __future__ import annotations
import tempfile
import unittest
from pathlib import Path

from hiroute.data.shandong import RawSite
from hiroute.data.shandong_spatial import (
    clip_lines_to_boundary, geodesic_detour_scores_wgs84, read_osm_poly,
    snap_sites_wgs84,
)
from shapely.geometry import LineString

PROJECTION = '+proj=lcc +lat_1=35 +lat_2=38 +lat_0=36.5 +lon_0=118.5 +datum=WGS84 +units=m +no_defs +type=crs'

class ShandongSpatialTests(unittest.TestCase):
    def test_poly_structure_and_projected_line_clipping(self):
        text='''fixture\nouter\n-0.05 -0.05\n0.05 -0.05\n0.05 0.05\n-0.05 0.05\n-0.05 -0.05\nEND\nEND\n'''
        raw=text.encode()
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'boundary.poly'; p.write_bytes(raw)
            boundary=read_osm_poly(p)
            clipped=clip_lines_to_boundary([LineString([(-0.1,0),(0.1,0)])],boundary,PROJECTION)
            self.assertEqual(len(clipped),1)
            self.assertGreater(clipped[0].length,0)
            self.assertLess(clipped[0].length,30000)

    def test_wgs84_snap_uses_frozen_radius_and_numeric_node_tie(self):
        site=RawSite('node/55',118.5,36.5,'charging_station',('C',),'a'*64)
        nodes=[{'node_id':'10','lon':118.5,'lat':36.5},{'node_id':'2','lon':118.5,'lat':36.5}]
        attached=snap_sites_wgs84([site],nodes,max_distance_m=1)
        self.assertEqual(attached['node/55']['node_id'],'2')
        self.assertEqual(attached['node/55']['distance_m'],0)
        self.assertEqual(snap_sites_wgs84([site],nodes,max_distance_m=0,excluded_node_ids={'2','10'}),{})
        self.assertEqual(snap_sites_wgs84([site],nodes,max_distance_m=0.0,excluded_node_ids={'2'}),{'node/55':{'node_id':'10','distance_m':0.0}})
        self.assertEqual(snap_sites_wgs84([site],nodes,max_distance_m=0),{'node/55':{'node_id':'2','distance_m':0.0}})
        with self.assertRaises(ValueError): snap_sites_wgs84([site],nodes,max_distance_m=-1)

    def test_geodesic_candidate_score_is_deterministic_and_nonnegative(self):
        sites=[RawSite('node/2',118.6,36.5,'charging_station',('C',),'b'*64),
               RawSite('node/1',118.4,36.5,'restaurant',('S',),'b'*64)]
        scores=geodesic_detour_scores_wgs84(sites,(118.3,36.5),(118.7,36.5))
        self.assertEqual(set(scores),{'node/1','node/2'})
        self.assertTrue(all(v>=0 for v in scores.values()))
        self.assertAlmostEqual(scores['node/1'],scores['node/2'],delta=0.02)

if __name__=='__main__': unittest.main()
