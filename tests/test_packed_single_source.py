import copy
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from road_certificate_fixtures import build as tiny_build
from streaming_road_fixtures import graph_inputs
from streaming_road_graph import ResourceStop,sha
from streaming_road_certificate import UNIT_SCHEMA,SourceSession,read_source_unit
from packed_source_prototype import Packed,build_synthetic,generate,Transcript
from packing_output_limits import LimitedFile
from packed_source_certificate_codec import decode_certificate
from run_packed_single_source import admit,complete_input


class PackedSingleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        b=tiny_build();self.graph=graph_inputs(b['graph_payload'],self.root);self.addCleanup(self.graph.close)
        self.packed=Packed.open(build_synthetic(self.graph,self.root/'pack'));self.addCleanup(self.packed.close)
        p=b['table_payload'];self.header=dict(schema=UNIT_SCHEMA,numerical_contract=p['numerical_contract'],
            selected_leg_contract=p['selected_leg_contract'],graph_identity='sha256:'+self.graph.payload_sha256,
            source_unit='o',**{k:p[k] for k in ('origin_anchor','destination_anchor','candidate_order','sites')})
        self.limits=dict(paths=1024**2,binary=1024**2,decoded=1024**2)

    def producer(self,name='producer'):
        folder=self.root/name;folder.mkdir();result=generate(self.packed,self.header,folder/'candidate',output_limits=self.limits)
        receipt=dict(decision='COMPLETE_UNTRUSTED_PACKED_SOURCE',mode='generate',source='o',source_commit='b'*40,
            config_sha256='a'*64,source_dirty=False,whole_table_certified=False,result=result)
        (folder/'result.json').write_text(json.dumps(receipt));return folder,receipt

    def test_utf8_and_binary_quotas_reject_before_writes(self):
        path=self.root/'text'
        with LimitedFile(path,'x',3) as stream:
            stream.write('é')
            with self.assertRaises(ResourceStop):stream.write('é')
        self.assertEqual(path.read_bytes(),'é'.encode())
        with LimitedFile(self.root/'bin','xb',1) as stream:
            with self.assertRaises(ResourceStop):stream.write(b'xx')
        self.assertEqual((self.root/'bin').stat().st_size,0)
        with self.assertRaises(ValueError):LimitedFile(self.root/'bad','x',True)

    def test_each_generator_output_quota_stops_without_complete_source(self):
        for name in ('paths','binary','decoded'):
            with self.subTest(name=name):
                limits=dict(self.limits);limits[name]=1;folder=self.root/name
                with self.assertRaises(ResourceStop):generate(self.packed,self.header,folder,output_limits=limits)
                self.assertFalse((folder/'source.jsonl').exists())
                if name=='paths':self.assertEqual((folder/'paths.jsonl').stat().st_size,0)
                if name=='binary':self.assertEqual((folder/'source.binary').stat().st_size,0)

    def test_decoded_output_quota_never_truncates_a_record_to_success(self):
        folder,_=self.producer();candidate=folder/'candidate';output=self.root/'decoded'
        with self.assertRaises(ResourceStop):decode_certificate(candidate/'source.binary',output,self.packed,self.header,
            sha(candidate/'paths.jsonl'),max_output_bytes=1)
        self.assertEqual(output.stat().st_size,0)

    def test_quota_enabled_outputs_match_old_exact_bytes_and_independent_proof(self):
        old=generate(self.packed,self.header,self.root/'old');folder,r=self.producer()
        self.assertEqual((old['paths_sha256'],old['source_sha256']),(r['result']['paths_sha256'],r['result']['source_sha256']))
        paths,cert,_=complete_input(folder,self.header,'a'*64,'b'*40,self.limits)
        table=read_source_unit(paths,self.graph,self.root/'paths.sqlite',max_bytes=1024**2)
        try:
            session=SourceSession(self.graph,table,max_state_bytes=1024**2);session.check_source(cert,self.root/'checked')
            self.assertEqual(session.finish()['checked_sources'],1);self.assertFalse(session.finish()['whole_table_certified'])
        finally:table.close()

    def test_partial_generation_is_rejected_before_hash_or_check(self):
        folder=self.root/'partial';folder.mkdir();(folder/'result.json').write_text(json.dumps(dict(decision='UNKNOWN_UNCERTIFIED')))
        with patch('run_packed_single_source.sha',side_effect=AssertionError('must not inspect partial artifacts')):
            with self.assertRaisesRegex(ValueError,'complete generation'):complete_input(folder,self.header,'a'*64,'b'*40,self.limits)
        with self.assertRaises(FileNotFoundError):complete_input(self.root/'absent',self.header,'a'*64,'b'*40,self.limits)

    def test_complete_receipt_cannot_rebind_wrong_producer_or_changed_files(self):
        folder,r=self.producer()
        with self.assertRaises(ValueError):complete_input(folder,self.header,'a'*64,'c'*40,self.limits)
        r['result']['candidate_pairs']-=1;(folder/'result.json').write_text(json.dumps(r))
        with self.assertRaisesRegex(ValueError,'unit domain'):complete_input(folder,self.header,'a'*64,'b'*40,self.limits)
        r['result']['candidate_pairs']+=1;(folder/'result.json').write_text(json.dumps(r))
        with (folder/'candidate/source.binary').open('ab') as f:f.write(b'x')
        with self.assertRaisesRegex(ValueError,'sizes'):complete_input(folder,self.header,'a'*64,'b'*40,self.limits)

    def test_checker_state_quota_failure_cannot_finish_a_certificate(self):
        folder,_=self.producer();t=read_source_unit(folder/'candidate/paths.jsonl',self.graph,self.root/'table')
        try:
            with self.assertRaises(ValueError):SourceSession(self.graph,t,max_state_bytes=0)
            s=SourceSession(self.graph,t,max_state_bytes=4096)
            with self.assertRaises(sqlite3.OperationalError):s.check_source(folder/'candidate/source.jsonl',self.root/'state-small')
            self.assertTrue(s.failed)
            with self.assertRaises(ValueError):s.finish()
        finally:t.close()

    def test_frozen_domain_limits_and_denominator_cannot_shrink(self):
        cfg=json.loads((Path(__file__).resolve().parents[1]/'configs/packed_single_source.json').read_text());admit(cfg)
        for key,value in [('targets',64),('source','other'),('nodes',10),('component_wall_s',300),('component_CPU_s',120.0),('worker_threads',True),('EV_solve',True),('output_limits',{})]:
            with self.subTest(key=key):
                bad=copy.deepcopy(cfg);bad[key]=value
                with self.assertRaises(ValueError):admit(bad)

    def test_progress_records_phase_completion_without_certification(self):
        events=[];result=generate(self.packed,self.header,self.root/'events',output_limits=self.limits,progress=events.append)
        self.assertTrue(any(e['phase']=='labels' and e['phase_complete'] for e in events))
        self.assertFalse(result['whole_table_certified']);self.assertTrue(all('checked_sources' not in e for e in events))
        t=Transcript(1)
        with self.assertRaises(ResourceStop):t.write('é')
        self.assertEqual(t.bytes,0)


if __name__=='__main__':unittest.main()
