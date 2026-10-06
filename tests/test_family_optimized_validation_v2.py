"""Actual standalone replay must reject tampering in normal/-O/-OO Python."""
from copy import deepcopy
from fractions import Fraction as F
import gzip, hashlib, json, os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'validation'))
sys.path.insert(0,str(ROOT/'experiments/time_cut_v2/family_faithfulness'))
from family5.checker import verify_bundle,reconstruct,check_witness,check_receipt,VerificationError,wire_equal,digest
from family5.test_checker_units import hand_bundle
from verify_recording_pilots import reconstruction_requests


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path,value):path.write_text(json.dumps(value,sort_keys=True,indent=2)+'\n')


class OptimizedStandaloneReplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case,cls.bundle,ids=hand_bundle();cls.ctx=verify_bundle(cls.bundle,cls.case)
        out=reconstruct(cls.ctx,ids['A'],'3','5')
        request=dict(node_id=ids['A'],witness=out['witness'],contract=dict(kind='minimum',energy='3'))
        cls.payload=dict(case=cls.case,bundle=cls.bundle,callback_requests=[request])
        cls.rows=[dict(kind='actual_production_callback',index=0,**request,
                      receipt=check_witness(cls.ctx,ids['A'],request['witness'],request['contract']))]
        for node_id,contract in reconstruction_requests(cls.payload):
            value=reconstruct(cls.ctx,node_id,contract['energy'],contract['budget'])
            cls.rows.append(dict(kind='independent_reconstruction',node_id=node_id,contract=contract,**value))

    def fixture(self,root,scenario):
        source=root/'source_final'
        script='experiments/time_cut_v2/family_faithfulness/verify_recording_pilots.py'
        for relative in (script,'validation/family5/__init__.py','validation/family5/checker.py','validation/family5/independent_oracle_v2.py'):
            target=source/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/relative,target)
        inputs=root/'inputs';outputs=root/'receipts';inputs.mkdir();outputs.mkdir()
        payload=deepcopy(self.payload);rows=deepcopy(self.rows)
        if scenario.startswith('event_count_'):
            cursor=rows[0]['receipt']
            while cursor['parent'] is not None:cursor=cursor['parent']
            cursor['event_count']=True if scenario.endswith('bool') else 1.0
        elif scenario.startswith('callback_index_'):
            rows[0]['index']=False if scenario.endswith('bool') else 0.0
        elif scenario=='drop_callback':rows=rows[1:]
        elif scenario=='duplicate_callback':rows.insert(1,deepcopy(rows[0]))
        elif scenario=='drop_reconstruction':rows.pop()
        elif scenario=='duplicate_reconstruction':rows.append(deepcopy(rows[-1]))
        elif scenario=='reorder_reconstruction':
            i=next(i for i in range(2,len(rows)) if rows[i]['node_id']!=rows[1]['node_id'])
            rows[1],rows[i]=rows[i],rows[1]
        elif scenario=='wrong_probe_contract':rows[-1]['contract']['energy']=int(F(rows[-1]['contract']['energy']))
        save(inputs/'hand.json',payload);save(root/'trusted.json',[self.case])
        raw=outputs/(self.case['case_id']+'.receipts.jsonl.gz')
        with gzip.open(raw,'wt') as stream:
            for row in rows:stream.write(json.dumps(row)+'\n')
        report=dict(source_sha256=sha(inputs/'hand.json'),raw_sha256=sha(raw),raw_receipts_replayed=len(self.rows),
                    actual_production_callbacks_replayed=1,independently_reconstructed_witnesses=len(self.rows)-1)
        if scenario=='report_count_bool':report['actual_production_callbacks_replayed']=True
        elif scenario=='report_count_float':report['actual_production_callbacks_replayed']=1.0
        elif scenario=='bad_source_hash':report['source_sha256']='0'*64
        elif scenario=='bad_raw_hash':report['raw_sha256']='0'*64
        save(outputs/(self.case['case_id']+'.json'),report)
        (root/'onebyte').write_text('x')
        manifest=dict(files={str(p.relative_to(root)):dict(sha256=sha(p),bytes=p.stat().st_size)
                             for p in sorted(root.rglob('*')) if p.is_file()},
                      replay_population=dict(inputs_directory='inputs',receipts_directory='receipts',input_files=['hand.json']))
        if scenario=='manifest_bytes_bool':manifest['files']['onebyte']['bytes']=True
        elif scenario=='manifest_bytes_float':manifest['files']['onebyte']['bytes']=1.0
        elif scenario=='missing_case_coverage':manifest['replay_population']['input_files']=['absent.json','hand.json']
        seal=root/'EVIDENCE_MANIFEST.json';save(seal,manifest)
        seal_sha=sha(seal)
        if scenario=='bad_external_hash':seal_sha='0'*64
        elif scenario=='sealed_file_tamper':(root/'onebyte').write_text('y')
        return [str(source/script),'--replay-only','--inputs-dir',str(inputs),'--output-dir',str(outputs),
                '--case-files',str(root/'trusted.json'),'--evidence-manifest',str(seal),'--manifest-sha',seal_sha]

    def test_standalone_optimization_modes(self):
        expected={
            'valid':None,'event_count_bool':'receipt_event_count_type','event_count_float':'receipt_event_count_type',
            'callback_index_bool':'callback kind/index mismatch','callback_index_float':'callback kind/index mismatch',
            'drop_callback':'callback kind/index mismatch','duplicate_callback':'reconstruction family/order mismatch',
            'drop_reconstruction':'missing callback or reconstruction receipts','duplicate_reconstruction':'extra reconstruction receipt',
            'reorder_reconstruction':'reconstruction family/order mismatch','wrong_probe_contract':'reconstruction energy/budget coverage mismatch',
            'report_count_bool':'reported callback count mismatch','report_count_float':'reported callback count mismatch',
            'bad_source_hash':'source artifact differs','bad_raw_hash':'raw receipts differ',
            'manifest_bytes_bool':'manifest byte count mismatch','manifest_bytes_float':'manifest byte count mismatch',
            'bad_external_hash':'wrong external evidence-manifest hash','sealed_file_tamper':'manifest file hash mismatch',
            'missing_case_coverage':'replay case coverage mismatch'}
        for flag in (None,'-O','-OO'):
            for scenario,reason in expected.items():
                with self.subTest(mode=flag or 'normal',scenario=scenario),tempfile.TemporaryDirectory() as temp:
                    args=self.fixture(Path(temp),scenario)
                    command=[sys.executable]+([flag] if flag else [])+args
                    done=subprocess.run(command,capture_output=True,text=True,
                                        env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},timeout=30)
                    if reason is None:
                        self.assertEqual(done.returncode,0,done.stderr)
                        self.assertEqual(json.loads(done.stdout)['replayed'],len(self.rows))
                    else:
                        self.assertNotEqual(done.returncode,0,done.stdout)
                        self.assertIn(reason,done.stderr)

    def test_antichain_guard_survives_optimization(self):
        code="""from fractions import Fraction as F
from family5.independent_oracle_v2 import Piece, antichain
p=Piece(F(0),F(1),True,True,F(0),F(0),True,F(0),(),('a',0,0))
try:
    antichain([p,p])
except AssertionError:
    print('rejected')
else:
    raise SystemExit('incorrectly accepted dominated duplicate')
"""
        for flag in (None,'-O','-OO'):
            with self.subTest(mode=flag or 'normal'):
                done=subprocess.run([sys.executable]+([flag] if flag else [])+['-c',code],capture_output=True,text=True,
                                    env={**os.environ,'PYTHONPATH':str(ROOT/'validation'),'PYTHONDONTWRITEBYTECODE':'1'},timeout=30)
                self.assertEqual(done.returncode,0,done.stderr)
                self.assertEqual(done.stdout.strip(),'rejected')

    def test_guarded_union_endpoint_flags_are_exact_booleans(self):
        case,bundle,ids=hand_bundle()
        node=bundle['nodes'].pop(ids['guarded']);node['params']['guards'][0][2]=1
        ident=digest(node);bundle['nodes'][ident]=node;bundle['roots']=[ident]
        with self.assertRaisesRegex(VerificationError,'guarded_union_parent_guard'):
            verify_bundle(bundle,case)

    def test_recursive_wire_types_are_distinct(self):
        self.assertFalse(wire_equal({'count':[1]},{'count':[True]}))
        self.assertFalse(wire_equal({'count':[1]},{'count':[1.0]}))
        self.assertTrue(wire_equal({'count':[1]},{'count':[1]}))
        out=reconstruct(self.ctx,self.payload['callback_requests'][0]['node_id'],'3','5')
        for value in (True,1.0):
            receipt=deepcopy(out['receipt']);cursor=receipt
            while cursor['parent'] is not None:cursor=cursor['parent']
            cursor['event_count']=value
            with self.assertRaisesRegex(VerificationError,'receipt_event_count_type'):
                check_receipt(self.ctx,self.payload['callback_requests'][0]['node_id'],out['witness'],receipt['contract'],receipt,require_budgets=True)

if __name__=='__main__':unittest.main()
