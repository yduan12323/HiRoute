from dataclasses import FrozenInstanceError
from fractions import Fraction
import json
from pathlib import Path
import random
import copy
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from road_certificate_fixtures import build as tiny_build,graph_payload,edge
from streaming_road_fixtures import graph_inputs,analytic_wide
from streaming_road_graph import sha,ResourceStop
from streaming_road_certificate import UNIT_SCHEMA,Arithmetic,read_source_unit,SourceSession
from packed_source_prototype import (build_synthetic,Packed,validate_synthetic_pack,generate,Pages,
    Labels,IndexedHeap,HEAD,ARC,SENTINEL,MAX_LINE)


def header(bundle,g,source='o'):
    p=bundle['table_payload']
    return dict(schema=UNIT_SCHEMA,numerical_contract=p['numerical_contract'],selected_leg_contract=p['selected_leg_contract'],graph_identity='sha256:'+g.payload_sha256,
        source_unit=source,**{k:p[k] for k in ('origin_anchor','destination_anchor','candidate_order','sites')})


def rebound(path):
    mp=path.parent/'manifest.jsonl';m=json.loads(mp.read_text());m['data_sha256']=sha(path);m['data_bytes']=path.stat().st_size;mp.write_text(json.dumps(m)+'\n')


class PackedTests(unittest.TestCase):
    def test_exhaustive_tiny_parity_and_unchanged_independent_checker(self):
        for kind in ('base','deep','numeric'):
            b=tiny_build(graph_payload(kind),sites={} if kind!='base' else None)
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as d:
                root=Path(d);g=graph_inputs(b['graph_payload'],root);path=build_synthetic(g,root/'pack');p=Packed.open(path,65536)
                try:
                    validate_synthetic_pack(g,p)
                    for i,source in enumerate(b['table'].sources):
                        folder=root/f'unit-{i}'
                        with patch('sqlite3.connect',side_effect=AssertionError('SQL in exporter')):
                            result=generate(p,header(b,g,source),folder)
                        self.assertEqual(result['metrics']['SQL_execute_calls'],0)
                        t=read_source_unit(folder/'paths.jsonl',g,root/f'table-{i}')
                        try:
                            for target in t.targets:
                                expected=b['table'].pairs[source,target];reach,T,L=t.pair(source,target)
                                self.assertEqual(bool(reach),expected.reachable)
                                if reach:
                                    self.assertEqual((Fraction(T),Fraction(L)),(expected.time,expected.length))
                                    steps=list(t.steps(source,target));self.assertEqual(tuple([source]+[v for u,v,e in steps]),expected.nodes);self.assertEqual(tuple(e for u,v,e in steps),expected.edges)
                            s=SourceSession(g,t);s.check_source(folder/'source.jsonl',root/f'check-{i}');self.assertFalse(s.finish()['whole_table_certified'])
                        finally:t.close()
                finally:p.close();g.close()

    def test_full_width_mask_and_original_source_denominator(self):
        b=analytic_wide()['bundle']
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);g=graph_inputs(b['graph_payload'],root);p=Packed.open(build_synthetic(g,root/'pack'))
            try:
                r=generate(p,header(b,g),root/'unit');self.assertEqual((r['candidate_pairs'],r['source_denominator'],r['pair_denominator']),(65,65,4225))
                t=read_source_unit(root/'unit/paths.jsonl',g,root/'table')
                try:
                    s=SourceSession(g,t);s.check_source(root/'unit/source.jsonl',root/'checked');self.assertEqual(s.finish()['unrun_sources'],64)
                finally:t.close()
            finally:p.close();g.close()

    def test_arbitrary_precision_labels_and_selected_lengths(self):
        p,q=2**83-9,2**83-71;gp=graph_payload();gp.update(nodes=['o','a','z'],edges=[edge('o','a','1/'+str(p),2**140,'01'),edge('a','z','1/'+str(q),1,'10')]);b=tiny_build(gp,sites={})
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);g=graph_inputs(gp,root);packed=Packed.open(build_synthetic(g,root/'pack'))
            try:
                result=generate(packed,header(b,g),root/'unit');t=read_source_unit(root/'unit/paths.jsonl',g,root/'table')
                try:
                    self.assertGreater(Fraction(t.pair('o','z')[1]).denominator.bit_length(),84);self.assertEqual(Fraction(t.pair('o','z')[2]),2**140+1)
                    s=SourceSession(g,t);s.check_source(root/'unit/source.jsonl',root/'checked');s.finish()
                finally:t.close()
            finally:packed.close();g.close()

    def test_empty_alias_prefix_has_no_fabricated_leg(self):
        b=tiny_build(sites={},destination='o')
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);g=graph_inputs(b['graph_payload'],root);p=Packed.open(build_synthetic(g,root/'pack'))
            try:
                generate(p,header(b,g),root/'unit');t=read_source_unit(root/'unit/paths.jsonl',g,root/'table')
                try:self.assertEqual(t.pair('o','o'),(1,'0','0'));self.assertEqual(list(t.steps('o','o')),[])
                finally:t.close()
            finally:p.close();g.close()

    def test_indexed_frontier_has_one_exact_entry_per_vertex(self):
        rng=random.Random(9);A=Arithmetic();labels=Labels(128,1024**2);h=IndexedHeap(128,labels,A);live={}
        for i in range(128):
            v=Fraction(rng.randrange(1,1000),rng.randrange(1,50));labels.put(i,v);live[i]=v;h.changed(i)
        for i in range(128):
            v=live[i]-Fraction(2000,1);labels.put(i,v);live[i]=v;h.changed(i)
        self.assertEqual(h.peak,128)
        while live:
            expected=min(live,key=lambda i:(live[i],i));self.assertEqual(h.pop(),expected);live.pop(expected)
        self.assertEqual(h.size,0)

    def test_resource_stops_do_not_clip_labels_or_admit_real_constructor(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ResourceStop):build_synthetic(SimpleNamespace(node_count=2986695,edge_count=5900232),Path(d)/'prohibited')
            root=Path(d);b=tiny_build();g=graph_inputs(b['graph_payload'],root);p=Packed.open(build_synthetic(g,root/'pack'))
            try:
                with self.assertRaises(ResourceStop):generate(p,header(b,g),root/'short',label_bytes=1)
                self.assertFalse((root/'short/source.jsonl').exists())
            finally:p.close();g.close()

    def test_paged_reader_and_manifest_are_bounded_before_allocation(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);data=root/'pages';data.write_bytes(b'x'*10000)
            with data.open('r+b') as extended:extended.seek(MAX_LINE+1);extended.write(b'x')
            p=Pages(data,128,64)
            try:
                for i in range(0,10000,64):self.assertEqual(p.read(i,1),b'x')
                self.assertLessEqual(p.peak_bytes,128);self.assertLessEqual(len(p.cache),2)
                with self.assertRaises(ResourceStop):p.read(0,MAX_LINE+1)
                with self.assertRaises(ValueError):p.read(MAX_LINE+2,1)
            finally:p.close()
            b=tiny_build();g=graph_inputs(b['graph_payload'],root);path=build_synthetic(g,root/'pack');mp=path.parent/'manifest.jsonl';mp.write_text(mp.read_text()+'{}\n'*10000)
            try:
                with self.assertRaisesRegex(ValueError,'single bounded'):Packed.open(path)
            finally:g.close()

    def test_untrusted_offsets_counts_and_duplicate_identities_fail_closed(self):
        for mode in ('offset','count','edge_identity','weight'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as d:
                root=Path(d);b=tiny_build();g=graph_inputs(b['graph_payload'],root);path=build_synthetic(g,root/'pack');p=Packed.open(path);np,rp=p.np,p.rp;p.close()
                with path.open('r+b') as f:
                    if mode=='offset':f.seek(np);f.write(struct.pack('<Q',2**64-1))
                    elif mode=='count':f.seek(8);f.write(struct.pack('<Q',2**32))
                    elif mode=='edge_identity':f.seek(rp+ARC.size+4);f.write(struct.pack('<I',0))
                    else:
                        f.seek(rp);v,eid,tp,lp=ARC.unpack(f.read(ARC.size));f.seek(tp+8);f.write(b'\x00')
                rebound(path)
                try:
                    with self.assertRaises((ValueError,ResourceStop)):
                        altered=Packed.open(path)
                        try:validate_synthetic_pack(g,altered)
                        finally:altered.close()
                finally:g.close()

    def test_semantic_identity_and_mutable_files_cannot_be_rebound(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);b=tiny_build();g=graph_inputs(b['graph_payload'],root);path=build_synthetic(g,root/'pack');p=Packed.open(path)
            try:
                for name in ('N','graph_identity','path'):
                    with self.assertRaises(FrozenInstanceError):setattr(p,name,None)
                with path.open('ab') as stream:stream.write(b'changed')
                with self.assertRaises(ValueError):p.assert_unchanged()
            finally:p.close();g.close()

    def test_wrong_packed_weights_never_replace_independent_mathematics(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);b=tiny_build(sites={});g=graph_inputs(b['graph_payload'],root);path=build_synthetic(g,root/'pack');p=Packed.open(path)
            # Change o->b1 to9; canonical selected o->a->z remains an actual
            # original shortest path, while false label(b)=9 must be rejected.
            u=p.find_node('o');pos=next(tp for i,(v,e,tp,lp) in p.outgoing(u) if p.node(v)=='b');p.close()
            with path.open('r+b') as stream:stream.seek(pos+8);stream.write(b'\x09')
            rebound(path);p=Packed.open(path)
            try:
                with self.assertRaises(ValueError):validate_synthetic_pack(g,p)
                generate(p,header(b,g),root/'unit');t=read_source_unit(root/'unit/paths.jsonl',g,root/'table')
                try:
                    s=SourceSession(g,t)
                    with self.assertRaises(ValueError):s.check_source(root/'unit/source.jsonl',root/'checked')
                    self.assertTrue(s.failed)
                finally:t.close()
            finally:p.close();g.close()

    def test_frozen_matrix_rejects_vacuous_or_changed_profiles(self):
        from run_packed_source_feasibility import admit
        cfg=json.loads((Path(__file__).resolve().parents[1]/'configs/packed_source_feasibility.json').read_text());admit(cfg)
        for field,value in [('profiles',[]),('profiles',cfg['profiles'][:-1]),('profiles',[cfg['profiles'][0]]*8),('scaling_nodes',2048),('cache_bytes',1),('real_source',True),('real_pairs',65),('scaling_nodes',4096.0),('worker_threads',True)]:
            with self.subTest(field=field):
                altered=copy.deepcopy(cfg);altered[field]=value
                with self.assertRaises(ValueError):admit(altered)

    def test_storage_estimate_is_a_bound_not_real_RSS_measurement(self):
        from run_packed_source_feasibility import resource_proof
        proof=resource_proof();self.assertTrue(proof['index_proof']['node_and_edge_counts_below_uint32_sentinel'])
        self.assertLess(proof['generator_layout_admission_bytes'],1024**3);self.assertLess(proof['packed_file_conservative_upper_bytes'],4*1024**3)
        self.assertEqual(proof['decision'],'NO_GO_REAL_END_TO_END_RELEASE')
        for b in (tiny_build(),tiny_build(dict(graph_payload(),nodes=['o'],edges=[]),sites={},destination='o')):
            with tempfile.TemporaryDirectory() as d:
                root=Path(d);g=graph_inputs(b['graph_payload'],root);path=build_synthetic(g,root/'pack')
                try:
                    fixed=HEAD.size+16*(g.node_count+1)+8*(g.edge_count+1)+ARC.size*g.edge_count
                    upper=fixed+(root/'graph.tsv').stat().st_size+18*g.edge_count+(root/'nodes.jsonl').stat().st_size
                    self.assertLessEqual(path.stat().st_size,upper)
                finally:g.close()

    def test_binary_transport_reproduces_source_bytes_and_old_proof(self):
        from packed_source_certificate_codec import decode_certificate
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);b=tiny_build();g=graph_inputs(b['graph_payload'],root);p=Packed.open(build_synthetic(g,root/'pack'));h=header(b,g)
            try:
                result=generate(p,h,root/'unit');decoded=decode_certificate(root/'unit/source.binary',root/'replayed',p,h,sha(root/'unit/paths.jsonl'))
                self.assertEqual(decoded['decoded_sha256'],result['source_sha256'])
                t=read_source_unit(root/'unit/paths.jsonl',g,root/'table')
                try:
                    s=SourceSession(g,t);s.check_source(root/'replayed',root/'checked');self.assertFalse(s.finish()['whole_table_certified'])
                finally:t.close()
            finally:p.close();g.close()

    def test_binary_transport_rejects_corrupt_domain_lengths_and_suffix(self):
        from packed_source_certificate_codec import decode_certificate,HEAD as CERT_HEAD
        for mode in ('root','graph','length','denominator','mask','suffix'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as d:
                root=Path(d);b=tiny_build();g=graph_inputs(b['graph_payload'],root);p=Packed.open(build_synthetic(g,root/'pack'));h=header(b,g)
                try:
                    generate(p,h,root/'unit');path=root/'unit/source.binary';K=len(b['table'].targets);first=CERT_HEAD.size+4*K
                    with path.open('r+b') as stream:
                        if mode=='root':stream.seek(16);stream.write(struct.pack('<I',0))
                        elif mode=='graph':stream.seek(20);stream.write(b'\xff')
                        elif mode=='length':stream.seek(first+1);stream.write(struct.pack('<I',2**32-1))
                        elif mode=='denominator':stream.seek(first+1+8+1);stream.write(b'\x00')
                        elif mode=='mask':stream.seek(first+1+8+2+4);stream.write(b'\x80')
                        else:stream.seek(0,2);stream.write(b'extra')
                    with self.assertRaises((ValueError,ResourceStop)):decode_certificate(path,root/'bad',p,h,sha(root/'unit/paths.jsonl'))
                finally:p.close();g.close()

    def test_checker_choice_lookup_does_not_scan_all_paths_of_source(self):
        from exact_leg_fixtures import complete_payload
        import sqlite3
        nodes=['o']+['n'+str(i).zfill(3) for i in range(1,64)];gp=graph_payload();gp.update(nodes=nodes,edges=[edge(nodes[i],nodes[i+1],1,1,str(i)) for i in range(63)])
        sites={'Site/'+str(i):dict(anchor=nodes[i],effects=['C']) for i in range(1,63)};b=dict(graph_payload=gp,table_payload=complete_payload('o',nodes[-1],list(sites),sites))
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);g=graph_inputs(gp,root);p=Packed.open(build_synthetic(g,root/'pack'))
            try:
                generate(p,header(b,g),root/'unit');t=read_source_unit(root/'unit/paths.jsonl',g,root/'table')
                # A query with zero matching steps must seek by both source
                # and vertex, even though this source has2016path rows. The
                # guard counts VM work, not noisy elapsed time or index names.
                calls=[0]
                def bounded_work():calls[0]+=1;return calls[0]>256
                t._db.set_progress_handler(bounded_work,1)
                try:self.assertEqual(list(t.choices('o',nodes[-1])),[])
                finally:t._db.set_progress_handler(None,0);t.close()
            finally:p.close();g.close()

    def test_binary_input_size_is_admitted_before_hash_or_decode(self):
        from packed_source_certificate_codec import decode_certificate
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);b=tiny_build();g=graph_inputs(b['graph_payload'],root);p=Packed.open(build_synthetic(g,root/'pack'));h=header(b,g)
            try:
                generate(p,h,root/'unit')
                with patch('packed_source_certificate_codec.sha',side_effect=AssertionError('hash before admission')):
                    with self.assertRaises(ResourceStop):decode_certificate(root/'unit/source.binary',root/'unstarted',p,h,'unused',max_input_bytes=1)
                self.assertFalse((root/'unstarted').exists())
            finally:p.close();g.close()


if __name__=='__main__':unittest.main()
