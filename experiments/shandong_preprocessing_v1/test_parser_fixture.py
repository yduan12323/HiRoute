"""Opt-in actual Pyrosm/osmium tiny fixture, including retained non-dense negative."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(Path(__file__).resolve().parent)]

@unittest.skipUnless(os.environ.get('HIROUTE_TEST_OSMIUM'),'Set HIROUTE_TEST_OSMIUM to pinned osmium 1.18')
class ParserFixtureTests(unittest.TestCase):
    def test_dense_ooc_literal_pushdown_equivalence_and_nondense_negative(self):
        import pandas as pd
        import yaml
        from pyrosm import OSM
        from pyrosm.config import NetworkFilter
        from graph.preprocessing import ATTRIBUTES,normalize_network
        from graph.raw_way_policy import read_raw_way_policy
        from bounded_io import literal_exclusions,DENSE_FORMAT
        osmium=os.environ['HIROUTE_TEST_OSMIUM']
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            # Exact excluded private, multi-value excluded private;delivery,
            # privateish retained by Pyrosm (and would be lost by wildcard).
            values=['yes','private','private;delivery','privateish','permissive']
            xml=['<osm version="0.6">']
            for i in range(20000):xml.append(f'<node id="{i+1}" version="1" lat="36" lon="{118+i*.000001}"/>')
            for i,value in enumerate(values):
                xml.append(f'<way id="{100+i}" version="1"><nd ref="{i*2+1}"/><nd ref="{i*2+2}"/><tag k="highway" v="residential"/><tag k="access" v="{value}"/></way>')
            xml.append('<way id="105" version="1">'+''.join(f'<nd ref="{i+1}"/>' for i in range(20000))+'<tag k="highway" v="residential"/></way>')
            xml.append('<way id="106" version="1"><nd ref="1"/><nd ref="2"/><nd ref="3"/><nd ref="1"/><tag k="highway" v="yes"/><tag k="building" v="yes"/><tag k="amenity" v="shelter"/></way>')
            xml.append('<way id="107" version="1"><nd ref="4"/><nd ref="5"/><tag k="highway" v="street_lamp"/></way>')
            xml.append('</osm>');(p/'fixture.osm').write_text('\n'.join(xml))
            def native(*args):subprocess.run([osmium,*map(str,args)],check=True,capture_output=True)
            native('cat',p/'fixture.osm','-f',DENSE_FORMAT,'-o',p/'raw.pbf')
            import struct,zlib
            def varint(buf,offset):
                n=0;shift=0
                while True:
                    byte=buf[offset];offset+=1;n|=(byte&127)<<shift
                    if byte<128:return n,offset
                    shift+=7
            def fields(buf):
                pos=0
                while pos<len(buf):
                    key,pos=varint(buf,pos)
                    if key&7==2:
                        length,pos=varint(buf,pos);value=buf[pos:pos+length];pos+=length
                    elif key&7==0:value,pos=varint(buf,pos)
                    else:raise ValueError('Unexpected protobuf wire type')
                    yield key>>3,value
            def dense_blocks(path):
                count=0
                with path.open('rb') as stream:
                    while header_size:=stream.read(4):
                        header=dict(fields(stream.read(struct.unpack('>I',header_size)[0])))
                        blob=dict(fields(stream.read(header[3])))
                        if header[1]!=b'OSMData':continue
                        payload=blob[1] if 1 in blob else zlib.decompress(blob[3])
                        if any(k==2 and any(gk==2 for gk,_ in fields(group)) for k,group in fields(payload)):
                            count+=1
                return count
            native('cat',p/'fixture.osm','-f','pbf,pbf_dense_nodes=false','-o',p/'non-dense.pbf')
            native('tags-filter',p/'raw.pbf',*literal_exclusions(NetworkFilter.driving),'--invert-match','-f',DENSE_FORMAT,'-o',p/'filtered.pbf')
            native('tags-filter',p/'filtered.pbf','w/highway','-f',DENSE_FORMAT,'-o',p/'roads.pbf')
            self.assertGreater(dense_blocks(p/'roads.pbf'),1,'OOC input must retain multiple dense-node blocks')
            kwargs=dict(network_type='driving',nodes=True,extra_attributes=ATTRIBUTES)
            base=OSM(str(p/'raw.pbf'),engine='in_memory',workers=1).get_network(**kwargs)
            new=OSM(str(p/'roads.pbf'),engine='out_of_core',workers=1).get_network(**kwargs)
            self.assertEqual(set(base[1].id),set(new[1].id))
            self.assertIn(103,set(new[1].id))
            self.assertNotIn(102,set(new[1].id))
            routing=yaml.safe_load((ROOT/'configs/routing.yaml').read_text())
            left=normalize_network(*base,routing,raw_way_policy=read_raw_way_policy(p/'raw.pbf'))
            right=normalize_network(*new,routing,raw_way_policy=read_raw_way_policy(p/'roads.pbf'))
            self.assertEqual(right[2]['excluded_closed_shelter_contour_ways'],1)
            self.assertEqual(right[2]['excluded_street_lamp_ways'],1)
            with self.assertRaisesRegex(ValueError,'No documented'):
                normalize_network(*new,routing)
            pd.testing.assert_frame_equal(left[0],right[0]);pd.testing.assert_frame_equal(left[1],right[1])
            broken='\n'.join(xml).replace('<nd ref="20000"/>','<nd ref="999999"/>')
            (p/'missing.osm').write_text(broken)
            native('cat',p/'missing.osm','-f',DENSE_FORMAT,'-o',p/'missing.pbf')
            with self.assertRaises(subprocess.CalledProcessError):native('check-refs',p/'missing.pbf')
            # Known 0.13.1 OOC bug: retained as a regression signal. If fixed,
            # deliberately review/update this test rather than removing coverage.
            try:
                bad=OSM(str(p/'non-dense.pbf'),engine='out_of_core',workers=1).get_network(**kwargs)
            except (ValueError,KeyError,IndexError,RuntimeError):
                return
            self.assertTrue(bad is None or any(x is None or len(x)==0 for x in bad),
                            'Non-dense OOC behavior changed; review explicit dense guard')
