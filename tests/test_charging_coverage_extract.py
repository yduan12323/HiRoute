"""Actual native reader/geometry fixture, run in the separate pinned data env."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

READY=all(importlib.util.find_spec(x) for x in ('osmium','shapely','pyproj'))


@unittest.skipUnless(READY,'requires optional pinned provincial-data dependencies')
class ExtractTests(unittest.TestCase):
    def test_tagged_nodes_areas_relation_members_and_missing_geometry(self):
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
        try:from audit_shandong_charging import extract
        finally:sys.path.pop(0)
        from shapely.geometry import box
        xml=['<osm version="0.6">']
        for i,x,y,tags in [(1,118,36,{'amenity':'charging_station'}),
            (2,118,36,{'man_made':'charge_point'}),
            (3,118,36,{'amenity':'charging_station','access':'private'}),
            (4,118,36,{'amenity':'charging_station','motorcar':'no'}),
            (5,118,36,{'amenity':'parking'})]:
            xml.append(f'<node id="{i}" version="1" lon="{x}" lat="{y}">')
            xml.extend(f'<tag k="{k}" v="{v}"/>' for k,v in tags.items());xml.append('</node>')
        for base,lo,la in ((100,117.99,35.99),(200,118.5,36.5)):
            for j,(x,y) in enumerate(((lo,la),(lo+.02,la),(lo+.02,la+.02),(lo,la+.02))):
                xml.append(f'<node id="{base+j}" version="1" lon="{x}" lat="{y}"/>')
        for wid,base,tag in ((10,100,True),(99,200,False)):
            xml.append(f'<way id="{wid}" version="1">')
            xml.extend(f'<nd ref="{base+j}"/>' for j in (0,1,2,3,0))
            if tag:xml.append('<tag k="amenity" v="charging_station"/>')
            xml.append('</way>')
        xml.extend(['<way id="30" version="1"><nd ref="998"/><nd ref="999"/><tag k="amenity" v="charging_station"/></way>',
            '<relation id="20" version="1"><member type="way" ref="99" role="outer"/><tag k="type" v="multipolygon"/><tag k="amenity" v="charging_station"/></relation>',
            '</osm>'])
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'source.osm';p.write_text('\n'.join(xml))
            records,stations,aliases,errors,_=extract(p,box(117,35,119,37),{'node/1','node/5'})
        rows={r['site_id']:r for r in records}
        self.assertFalse(rows['node/2']['evidence']['modeled_C_eligible'])
        self.assertFalse(rows['node/3']['evidence']['modeled_C_eligible'])
        self.assertFalse(rows['node/4']['evidence']['modeled_C_eligible'])
        self.assertFalse(rows['node/5']['evidence']['modeled_C_eligible'])
        self.assertEqual(aliases,{'way/10':'node/1'})
        self.assertEqual({r['site_id'] for r in stations},{'node/1','relation/20'})
        self.assertEqual({r['site_id'] for r in errors},{'way/30'})


if __name__=='__main__':unittest.main()
