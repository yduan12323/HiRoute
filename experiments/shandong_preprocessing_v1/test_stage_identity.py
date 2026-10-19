"""Negative probes use tiny synthetic bytes only, never real data."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from phases import digest,verify_stage,REQUIRED_FILES,owned_scratch

class StageIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.out=Path(self.tmp.name).resolve()
        self.m={'phase':'graph','synthetic':True,'files':{}}
        for name in REQUIRED_FILES['graph']:
            p=self.out/name;p.write_bytes(b'synthetic only')
            self.m['files'][name]={'sha256':digest(p),'size_bytes':p.stat().st_size}
        self.identity={'path':str(self.out),'phase':'graph','synthetic':True,'manifest_sha256':''}
        self.refresh()

    def refresh(self):
        (self.out/'artifact_manifest.json').write_text(json.dumps(self.m))
        self.identity['manifest_sha256']=digest(self.out/'artifact_manifest.json')

    def test_valid_bound_stage(self):
        self.assertEqual(verify_stage(self.identity,'graph'),self.out)

    def test_empty_file_map_rejected_even_with_bound_hash(self):
        self.m['files']={};self.refresh()
        with self.assertRaisesRegex(ValueError,'required'):verify_stage(self.identity,'graph')

    def test_omitted_nodes_rejected_even_with_bound_hash(self):
        del self.m['files']['nodes.parquet'];self.refresh()
        with self.assertRaisesRegex(ValueError,'required'):verify_stage(self.identity,'graph')

    def test_wrong_manifest_phase_rejected(self):
        self.m['phase']='sites';self.refresh()
        with self.assertRaisesRegex(ValueError,'phase'):verify_stage(self.identity,'graph')

    def test_edited_manifest_rejected_without_rebinding(self):
        self.m['files']={};(self.out/'artifact_manifest.json').write_text(json.dumps(self.m))
        with self.assertRaisesRegex(ValueError,'digest'):verify_stage(self.identity,'graph')

    def test_changed_artifact_rejected(self):
        (self.out/'nodes.parquet').write_bytes(b'changed bytes')
        with self.assertRaisesRegex(ValueError,'identity'):verify_stage(self.identity,'graph')

    def test_missing_phase_or_manifest_digest_rejected(self):
        for key in ('phase','manifest_sha256'):
            bad=dict(self.identity);del bad[key]
            with self.assertRaises(ValueError):verify_stage(bad,'graph')

    def test_synthetic_real_mismatch_rejected(self):
        self.m['synthetic']=False;self.refresh()
        with self.assertRaisesRegex(ValueError,'synthetic'):verify_stage(self.identity,'graph')

    def test_scratch_owned_and_stays_under_artifacts(self):
        with patch.dict(os.environ,{k:str(self.out/'scratch') for k in ('TMPDIR','TMP','TEMP')}):
            scratch=owned_scratch(self.out)
        self.assertEqual(scratch.parent,self.out)
        self.assertEqual(scratch.stat().st_mode & 0o777,0o700)
        with patch.dict(os.environ,{'TMPDIR':'/tmp'}):
            with self.assertRaisesRegex(ValueError,'TMPDIR'):owned_scratch(self.out)

    def test_scratch_symlink_rejected(self):
        (self.out/'scratch').symlink_to('/tmp',target_is_directory=True)
        with patch.dict(os.environ,{k:str(self.out/'scratch') for k in ('TMPDIR','TMP','TEMP')}):
            with self.assertRaises(ValueError):owned_scratch(self.out)

if __name__=='__main__':unittest.main()
