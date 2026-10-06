"""Coverage and externally anchored hash checks for standalone receipt replay."""
from copy import deepcopy
import gzip, hashlib, json
from pathlib import Path
import sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'validation'))
sys.path.insert(0,str(ROOT/'experiments/time_cut_v2/family_faithfulness'))
from family5.checker import verify_bundle,check_witness,reconstruct
from make_pilot import build_ancestral
from verify_recording_pilots import replay,reconstruction_requests,verify_seal,sealed_member


class TestReceiptCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload=build_ancestral();cls.ctx=verify_bundle(cls.payload['bundle'],cls.payload['case'])
        source=cls.payload['witnesses']['A'][0]
        request=dict(node_id=source['node_id'],witness=source['witness'],contract=dict(kind='minimum',energy='3'))
        cls.payload['callback_requests']=[request]
        cls.rows=[dict(kind='actual_production_callback',index=0,**request,
                       receipt=check_witness(cls.ctx,request['node_id'],request['witness'],request['contract']))]
        for node_id,contract in reconstruction_requests(cls.payload):
            result=reconstruct(cls.ctx,node_id,contract['energy'],contract['budget'])
            cls.rows.append(dict(kind='independent_reconstruction',node_id=node_id,
                                 witness=result['witness'],receipt=result['receipt'],contract=contract))

    def run_rows(self,rows,report=None):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'receipts.gz'
            with gzip.open(path,'wt') as stream:
                for row in rows:stream.write(json.dumps(row)+'\n')
            return replay(path,self.ctx,self.payload,report,'source-sha')

    def test_complete_stream_passes(self):
        self.assertEqual(self.run_rows(self.rows),len(self.rows))

    def test_dropped_or_duplicated_original_callbacks_fail(self):
        for rows in (self.rows[1:],[self.rows[0]]+self.rows):
            with self.subTest(count=len(rows)),self.assertRaises(ValueError):self.run_rows(rows)

    def test_wrong_original_family_is_not_rebound(self):
        rows=deepcopy(self.rows);rows[0]['node_id']=self.payload['witnesses']['B'][0]['node_id']
        with self.assertRaises(ValueError):self.run_rows(rows)

    def test_missing_extra_or_wrong_energy_reconstruction_fails(self):
        for rows in (self.rows[:-1],self.rows+[self.rows[-1]]):
            with self.subTest(count=len(rows)),self.assertRaises(ValueError):self.run_rows(rows)
        rows=deepcopy(self.rows);rows[-1]['contract']['energy']='999'
        with self.assertRaises(ValueError):self.run_rows(rows)

    def test_reconstruction_cannot_drop_all_budget_annotations(self):
        rows=deepcopy(self.rows)
        cursor=rows[-1]['receipt']
        while cursor is not None:
            cursor.pop('requested_budget',None);cursor=cursor['parent']
        with self.assertRaises(ValueError):self.run_rows(rows)

    def test_report_source_and_raw_hashes_are_checked(self):
        for report in (dict(source_sha256='wrong',raw_sha256='wrong'),
                       dict(source_sha256='source-sha',raw_sha256='wrong')):
            with self.assertRaises(ValueError):self.run_rows(self.rows,report)

    def test_manifest_is_externally_anchored_and_scope_bound(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);file=root/'data.json';file.write_text('{}\n')
            manifest=dict(files={'data.json':dict(sha256=hashlib.sha256(file.read_bytes()).hexdigest(),bytes=file.stat().st_size)})
            path=root/'manifest.json';path.write_text(json.dumps(manifest));sha=hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(verify_seal(path,sha),manifest)
            sealed_member(file,manifest,root)
            with self.assertRaises(ValueError):sealed_member(root/'not-listed.json',manifest,root)
            with self.assertRaises(ValueError):verify_seal(path,'wrong')
            file.write_text('{"changed":true}')
            with self.assertRaises(ValueError):verify_seal(path,sha)

if __name__=='__main__':unittest.main()
