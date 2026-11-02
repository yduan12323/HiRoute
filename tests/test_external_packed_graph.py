import hashlib
import json
from pathlib import Path
import sqlite3
import struct
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import external_packed_graph as X
import streaming_road_graph as G
from packed_source_prototype import Packed,ARC,U64


class ExternalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.raw=self.root/'raw.tsv';self.db=self.root/'source.sqlite'
        self.rows=[('2','10','e/2','1/3','9007199254740993/7'),
            ('2','10','e/10','2/6','3/5'),('10','北京','é','7/11','1'),
            ('北京','2','中',str(2**160+7)+'/13','1/17'),('z','z','self','1','2')]
        self.raw.write_text(''.join('\t'.join(r)+'\n' for r in self.rows))
        self.nodes=None;self.N=4;self.E=5;self.rebuild_source()

    def rebuild_source(self):
        if self.db.exists():self.db.unlink()
        G.build(self.raw,self.db,nodes_path=self.nodes)
        self.raw_hash=G.sha(self.raw);self.gid=G.graph_identity(self.raw_hash,G.sha(self.nodes) if self.nodes else None)

    def build(self,name='pack',**kwargs):
        folder=self.root/name
        result=X.build(self.db,folder,expected_db_sha=G.sha(self.db),expected_identity=self.gid,
            expected_N=self.N,expected_E=self.E,**kwargs)
        return folder/'graph.csr',result

    def check(self,p,work='verify',**kwargs):
        return X.validate(self.raw,p,self.root/work,expected_raw_sha=self.raw_hash,
            expected_N=self.N,expected_E=self.E,nodes_path=self.nodes,**kwargs)

    def rehash(self,p):
        mp=p.parent/'manifest.jsonl';m=json.loads(mp.read_text());m.update(data_bytes=p.stat().st_size,data_sha256=G.sha(p));mp.write_text(json.dumps(m)+'\n')

    def test_complete_literal_parallel_alias_and_wide_exact_parity(self):
        p,result=self.build();v=self.check(p,anchors=['2','z','北京'])
        self.assertEqual(v['decision'],'PASS_COMPLETE_REPRESENTATION_IDENTITY_ONLY')
        self.assertEqual((v['nodes'],v['edges'],v['anchors_checked']),(4,5,3));self.assertGreater(v['max_observed_component_bits'],160)
        self.assertFalse(v['source_certified']);self.assertTrue(v['exact_weights'])
        self.assertTrue(all('TEMP B-TREE' not in row for plan in v['query_plans'].values() for row in plan))
        packed=Packed.open(p);self.addCleanup(packed.close)
        self.assertEqual([packed.node(i) for i in range(4)],['10','2','z','北京'])
        self.assertEqual([packed.eid(i) for i in range(5)],['e/10','e/2','self','é','中'])

    def test_explicit_isolated_node_and_empty_edges(self):
        self.raw.write_text('');self.nodes=self.root/'nodes.jsonl';self.nodes.write_text('"10"\n"2"\n"isolated"\n')
        self.N=3;self.E=0;self.rebuild_source();p,_=self.build();v=self.check(p,anchors=['isolated'])
        self.assertEqual((v['nodes'],v['edges']),(3,0))

    def test_independent_raw_detects_valid_but_wrong_source_weights(self):
        with sqlite3.connect(self.db) as d:d.execute("UPDATE edges SET t='5' WHERE eid='e/2'")
        p,_=self.build()
        with self.assertRaisesRegex(ValueError,'exact time'):self.check(p)

    def test_missing_or_extra_source_nodes_and_edges_rejected(self):
        for label,statement in [('node',"DELETE FROM nodes WHERE node='z'"),('edge',"DELETE FROM edges WHERE eid='self'")]:
            with self.subTest(label=label):
                self.rebuild_source()
                with sqlite3.connect(self.db) as d:d.execute(statement)
                with self.assertRaisesRegex(ValueError,'count'):self.build('pack-'+label)

    def test_duplicate_raw_edge_is_not_silently_deduplicated(self):
        p,_=self.build();self.raw.write_text(self.raw.read_text()+'\t'.join(self.rows[0])+'\n');self.raw_hash=G.sha(self.raw);self.E+=1
        with self.assertRaisesRegex(ValueError,'duplicate raw'):self.check(p)

    def test_frozen_input_hash_and_graph_ownership_fail_closed(self):
        with self.assertRaisesRegex(ValueError,'frozen representation'):
            X.build(self.db,self.root/'bad',expected_db_sha='0'*64,expected_identity=self.gid,expected_N=4,expected_E=5)
        p,_=self.build();mp=p.parent/'manifest.jsonl';m=json.loads(mp.read_text());m['graph_identity']='0'*64;mp.write_text(json.dumps(m)+'\n')
        with self.assertRaisesRegex(ValueError,'ownership'):self.check(p)

    def test_malformed_layout_counts_offsets_order_and_extra_bytes(self):
        changes=['node_offset','edge_offset','adjacency','wrong_direction','duplicate_eid','weight_gap','wrong_length','suffix']
        for label in changes:
            with self.subTest(label=label):
                p,_=self.build(label);g=Packed.open(p)
                np,ep,ap,rp=g.np,g.ep,g.ap,g.rp;row=g.arc(0);end=g.pages.size;g.close()
                with p.open('r+b') as f:
                    if label=='node_offset':f.seek(np+8);f.write(U64.pack(0))
                    elif label=='edge_offset':f.seek(ep);f.write(U64.pack(0))
                    elif label=='adjacency':f.seek(ap);f.write(U64.pack(1))
                    elif label=='wrong_direction':f.seek(rp);f.write(ARC.pack(0,*row[1:]))
                    elif label=='duplicate_eid':f.seek(rp+ARC.size+4);f.write(struct.pack('<I',row[1]))
                    elif label=='weight_gap':f.seek(rp+8);f.write(U64.pack(row[2]+1))
                    elif label=='wrong_length':f.seek(row[3]+8);f.write(b'\x09')
                    else:f.seek(end);f.write(b'x')
                self.rehash(p)
                with self.assertRaises((ValueError,G.ResourceStop)):self.check(p,'verify-'+label)

    def test_truncation_and_corrupt_magnitude_rejected(self):
        for label in ['truncate','zero_denominator','huge_magnitude']:
            with self.subTest(label=label):
                p,_=self.build(label);g=Packed.open(p);pos=g.arc(0)[2];end=g.pages.size;g.close()
                with p.open('r+b') as f:
                    if label=='truncate':f.truncate(end-1)
                    elif label=='zero_denominator':f.seek(pos+4);f.write(struct.pack('<I',0))
                    else:f.seek(pos);f.write(struct.pack('<I',2**31))
                self.rehash(p)
                with self.assertRaises((ValueError,G.ResourceStop)):self.check(p,'verify-'+label)

    def test_resource_limits_fail_without_partial_success(self):
        with self.assertRaises(G.ResourceStop):self.build('small',max_packed_bytes=64)
        p,_=self.build()
        with self.assertRaises(G.ResourceStop):self.check(p,max_adjacency_bytes=1)
        with self.assertRaisesRegex(ValueError,'anchor'):self.check(p,'missing-anchor',anchors=['missing'])

    def test_construction_callback_failure_preserves_partial_no_manifest(self):
        def stop():raise G.ResourceStop('test guard')
        with self.assertRaises(G.ResourceStop):self.build(check=stop)
        self.assertFalse((self.root/'pack/manifest.jsonl').exists())

    def test_duplicate_or_malformed_input_has_no_pass(self):
        p,_=self.build()
        for i,row in enumerate(['u\tv\te\t0\t1\n','u\tv\te\t1.2\t1\n','u\tv\tbad\x00\t1\t1\n']):
            self.raw.write_text(row);self.raw_hash=G.sha(self.raw);self.E=1
            with self.assertRaises((ValueError,G.ResourceStop)):self.check(p,'invalid-'+str(i))

    def test_raw_mutation_during_check_is_rejected(self):
        p,_=self.build();changed=False
        def mutate():
            nonlocal changed
            if not changed:self.raw.write_text(self.raw.read_text()+'\n');changed=True
        with self.assertRaisesRegex(ValueError,'changed during'):self.check(p,check=mutate)

    def test_existing_outputs_not_overwritten_and_quota_domain_rejected(self):
        self.build()
        with self.assertRaisesRegex(ValueError,'existing output'):self.build()
        with self.assertRaises(G.ResourceStop):X.database(self.root/'too-big.sqlite',3*1024**3)


if __name__=='__main__':unittest.main()
