"""Tiny generated source-cache contract checks; no provider data access."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import phases

class SourceCacheTests(unittest.TestCase):
    def test_copy_is_bounded_and_exclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);src=root/'raw';dst=root/'copied';src.write_bytes(b'abc')
            self.assertEqual(phases.copy_frozen_input(src,dst,3),3)
            self.assertEqual(dst.read_bytes(),b'abc')
            with self.assertRaises(FileExistsError):phases.copy_frozen_input(src,dst,3)
            with self.assertRaises(ValueError):phases.copy_frozen_input(src,root/'large',2)
            link=root/'link';link.symlink_to(src)
            with self.assertRaises(ValueError):phases.copy_frozen_input(link,root/'linked',3)
    def test_real_source_cache_requires_exact_pins(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);raw=root/'raw';raw.write_bytes(b'generated test input')
            poly=root/'polygon';poly.write_text('synthetic\n1\n117 35\n119 35\n119 37\n117 37\n117 35\nEND\nEND\n')
            md5=root/'md5';md5.write_text(hashlib.md5(raw.read_bytes()).hexdigest()+'  source.osm.pbf\n')
            config=json.loads((HERE/'config.json').read_text());s=config['source']
            s.update(local_pbf=str(raw),local_polygon=str(poly),local_publisher_md5=str(md5),sha256=phases.digest(raw),expected_size_bytes=raw.stat().st_size,publisher_md5=md5.read_text().split()[0],polygon_sha256=phases.digest(poly))
            info=json.dumps({'header':{'option':{'osmosis_replication_timestamp':s['snapshot_timestamp']}}})
            for key,value,error in [('sha256','0'*64,'source SHA256'),('polygon_sha256',None,'polygon SHA256'),('polygon_sha256','0'*64,'polygon SHA256'),('publisher_md5','0'*32,'publisher MD5'),('expected_size_bytes',100,'size mismatch'),(None,None,None)]:
                case=copy.deepcopy(config)
                if key:case['source'][key]=value
                out=root/('out'+str(len(list(root.glob('out*')))));out.mkdir()
                with patch.object(phases,'stream_download',side_effect=AssertionError('No network')),patch.object(phases,'native',return_value=info):
                    if error:
                        with self.assertRaisesRegex(ValueError,error):phases.source(out,{},case,'unused',False)
                    else:
                        phases.source(out,{},case,'unused',False)
                        receipt=json.loads((out/'sources.json').read_text())
                        self.assertFalse(receipt['synthetic']);self.assertFalse(receipt['polygon_snapshot_matched'])
                        self.assertEqual(receipt['sha256'],s['sha256'])
                        self.assertTrue(all(v=='verified_local_copy' for v in receipt['acquisition_method'].values()))

if __name__=='__main__':unittest.main()
