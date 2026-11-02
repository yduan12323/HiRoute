import copy
from fractions import Fraction as F
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from road_certificate_fixtures import IDS,fixture,evaluate as old_evaluate,build as tiny_build,graph_payload,edge
from streaming_road_graph import build,validate,Graph,Unsupported,ResourceStop
from streaming_road_certificate import read_table,Session,Checked,Arithmetic
from streaming_road_fixtures import graph_inputs,write_jsonl,table_rows,source_rows,evaluate,analytic_wide


def outcome(function):
    try:return function()['status']
    except Unsupported:return 'unsupported'
    except (ValueError,TypeError):return 'rejected'


class StreamingTests(unittest.TestCase):
    def test_frozen_15_decisions_match_existing_independent_checker(self):
        with tempfile.TemporaryDirectory() as d:
            for name in IDS:
                with self.subTest(name=name):
                    f=fixture(name);old=outcome(lambda:old_evaluate(f));new=outcome(lambda:evaluate(f,Path(d)/name))
                    self.assertEqual((old,new),(f['expected'],f['expected']))

    def test_literal_numeric_and_unicode_collisions_are_not_coerced(self):
        gp=dict(nodes=['01','1','10','2','ss','ß'],edges=[edge('01','1',1,1,'01'),edge('1','10',1,1,'1'),edge('10','2',1,1,'10'),edge('ss','ß',1,1,'2')])
        with tempfile.TemporaryDirectory() as d:
            g=graph_inputs(gp,Path(d))
            try:
                self.assertEqual(list(g.nodes()),sorted(gp['nodes']));self.assertEqual(g.edge('01').source,'01')
                with self.assertRaises(ValueError):g.edge(1)
            finally:g.close()

    def test_missing_extra_swapped_and_changed_edges_fail_independent_join(self):
        for mode in ('missing','extra','weight','identity','ordinal'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as d:
                root=Path(d);gp=graph_payload();g=graph_inputs(gp,root);g.close()
                db=sqlite3.connect(root/'graph.sqlite')
                if mode=='missing':db.execute('DELETE FROM edges WHERE ordinal=0')
                elif mode=='extra':db.execute("INSERT INTO edges VALUES(100,'o','a','extra','1','1')")
                elif mode=='weight':db.execute("UPDATE edges SET t='2' WHERE ordinal=0")
                elif mode=='identity':db.execute("UPDATE edges SET u='b' WHERE ordinal=0")
                else:db.execute('UPDATE edges SET ordinal=100 WHERE ordinal=0')
                db.commit();db.close()
                with self.assertRaises(ValueError):validate(root/'graph.tsv',root/'graph.sqlite',root/'second',nodes_path=root/'nodes.jsonl')

    def test_node_union_missing_extra_and_duplicate_explicit_nodes_rejected(self):
        for mode in ('missing','extra','duplicate'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as d:
                root=Path(d);g=graph_inputs(graph_payload(),root);g.close()
                if mode=='duplicate':
                    (root/'nodes.jsonl').write_text('"a"\n"a"\n')
                else:
                    db=sqlite3.connect(root/'graph.sqlite')
                    db.execute("DELETE FROM nodes WHERE node='a'" if mode=='missing' else "INSERT INTO nodes VALUES('invented')")
                    db.commit();db.close()
                with self.assertRaises(ValueError):validate(root/'graph.tsv',root/'graph.sqlite',root/'second',nodes_path=root/'nodes.jsonl')

    def test_global_edge_ID_duplicate_and_nonpositive_input_rejected(self):
        for mode in ('duplicate','zero','negative'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as d:
                p=Path(d)/'raw';p.write_text('a\tb\tedge\t1\t1\n'+('b\tc\tedge\t1\t1\n' if mode=='duplicate' else 'b\tc\tother\t'+('0' if mode=='zero' else '-1')+'\t1\n'))
                with self.assertRaises(ValueError):build(p,Path(d)/'db')

    def test_both_directions_of_union_mapping_and_untrusted_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'raw';p.write_text('01\t1\tID\t1/3\t7/5\n');build(p,root/'db')
            g=validate(p,root/'db',root/'v');self.assertEqual(list(g.nodes()),['01','1']);g.close()
            db=sqlite3.connect(root/'db');db.execute("UPDATE meta SET value='\"forged\"' WHERE key='raw_sha256'");db.commit();db.close()
            with self.assertRaises(ValueError):validate(p,root/'db',root/'bad')

    def test_duplicate_edge_ID_rejected_without_trusting_unique_schema(self):
        from streaming_road_graph import sha,graph_identity,SCHEMA
        from exact_leg_table import NUMERICAL,SELECTION
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'raw';p.write_text('a\tb\tsame\t1\t1\nb\tc\tsame\t1\t1\n')
            db=sqlite3.connect(root/'db');db.executescript('CREATE TABLE nodes(node TEXT);CREATE TABLE edges(ordinal INTEGER,u TEXT,v TEXT,eid TEXT,t TEXT,l TEXT);CREATE TABLE meta(key TEXT,value TEXT);')
            db.executemany('INSERT INTO nodes VALUES(?)',[(v,) for v in ('a','b','c')]);db.executemany('INSERT INTO edges VALUES(?,?,?,?,?,?)',[(0,'a','b','same','1','1'),(1,'b','c','same','1','1')])
            meta=dict(schema=SCHEMA,numerical_contract=NUMERICAL,selected_leg_contract=SELECTION,raw_sha256=sha(p),declared_nodes_sha256=None,graph_identity=graph_identity(sha(p),None))
            db.executemany('INSERT INTO meta VALUES(?,?)',[(k,json.dumps(v)) for k,v in meta.items()]);db.commit();db.close()
            with self.assertRaisesRegex(ValueError,'global edge-ID'):validate(p,root/'db',root/'v')

    def test_exact_arithmetic_exceeds_int64_and_component_denominator_width(self):
        A=Arithmetic();p=2**83-9;q=2**83-71;value=A.add(A.parse('1/'+str(p)),A.parse('1/'+str(q)))
        self.assertEqual(value,F(1,p)+F(1,q));self.assertGreater(value.denominator.bit_length(),84)
        self.assertEqual(A.parse(str(2**120)),F(2**120));prior=sys.get_int_max_str_digits()
        big=A.parse('9'*5000+'/7');self.assertGreater(big.numerator.bit_length(),16000)
        self.assertEqual(sys.get_int_max_str_digits(),prior)
        with self.assertRaises(ResourceStop):Arithmetic(2048).parse('9'*5000)

    def test_path_arithmetic_growth_parity_and_65bit_target_masks(self):
        from exact_road_certificate import GRAPH_SCHEMA
        from exact_leg_table import NUMERICAL,SELECTION
        p,q=2**83-9,2**83-71
        gp=dict(schema=GRAPH_SCHEMA,numerical_contract=NUMERICAL,selected_leg_contract=SELECTION,
            nodes=['o','a','z'],edges=[edge('o','a','1/'+str(p),1,'oa'),edge('a','z','1/'+str(q),1,'az')])
        f=dict(expected='verified',bundle=tiny_build(gp,sites={}))
        self.assertGreater(f['bundle']['table'].pairs['o','z'].time.denominator.bit_length(),84)
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(outcome(lambda:evaluate(f,Path(d)/'grown')),'verified')
            wide=analytic_wide();self.assertEqual(outcome(lambda:old_evaluate(wide)),'verified')
            result=evaluate(wide,Path(d)/'wide');self.assertEqual((result['pairs'],result['sources']),(4225,65))
            db=sqlite3.connect(Path(d)/'wide'/'state-64'/'state.sqlite')
            row=db.execute("SELECT mask,typeof(mask) FROM state WHERE node='o'").fetchone();db.close()
            self.assertEqual(row,(str((1<<65)-1),'text'))

    def test_same_bytes_reparsed_owner_and_final_resource_failure(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);b=tiny_build(sites={},destination='o');g=graph_inputs(b['graph_payload'],root)
            write_jsonl(root/'t',table_rows(b['table_payload'],g));t=read_table(root/'t',g,root/'tdb')
            other=validate(root/'graph.tsv',root/'graph.sqlite',root/'again',nodes_path=root/'nodes.jsonl')
            try:
                with self.assertRaises(TypeError):Session(other,t)
                armed=[False]
                def check():
                    if armed[0]:raise ResourceStop('final deadline')
                session=Session(g,t,check=check);write_jsonl(root/'c',source_rows(b['certificates'][0],g,t));session.check_source(root/'c',root/'state');armed[0]=True
                with self.assertRaises(ResourceStop):session.finish()
                self.assertTrue(session.failed)
            finally:other.close();t.close();g.close()

    def test_converter_does_not_hide_invalid_suffix_extra_labels_or_order(self):
        for mode in ('path_suffix','extra_label','target_order','forged_hash'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as d:
                b=tiny_build();f=dict(bundle=b,expected='rejected')
                if mode=='path_suffix':
                    next(r for r in b['table_payload']['pairs'] if r['edges'])['nodes'].append('dead')
                    from road_certificate_fixtures import raw
                    import hashlib
                    for c in b['certificates']:c['table_sha256']=hashlib.sha256(raw(b['table_payload'])).hexdigest()
                elif mode=='extra_label':b['certificates'][0]['labels']['hidden']='0'
                elif mode=='target_order':b['certificates'][0]['target_order'].reverse()
                else:b['certificates'][0]['graph_sha256']='0'*64
                self.assertEqual(outcome(lambda:evaluate(f,Path(d)/'case')),'rejected')

    def test_duplicate_metadata_rejected_without_an_input_schema_flag(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);g=graph_inputs(graph_payload(),root);g.close();db=sqlite3.connect(root/'graph.sqlite')
            values=list(db.execute('SELECT key,value FROM meta'));db.execute('DROP TABLE meta');db.execute('CREATE TABLE meta(key TEXT,value TEXT)')
            db.executemany('INSERT INTO meta VALUES(?,?)',values+[values[0]]);db.commit();db.close()
            with self.assertRaisesRegex(ValueError,'duplicate representation metadata'):
                validate(root/'graph.tsv',root/'graph.sqlite',root/'v2',nodes_path=root/'nodes.jsonl')

    def test_issued_certificate_and_cached_finish_reject_changed_disk_inputs(self):
        for mode in ('raw','representation','paths'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as d:
                root=Path(d);b=tiny_build(sites={},destination='o');g=graph_inputs(b['graph_payload'],root)
                write_jsonl(root/'t',table_rows(b['table_payload'],g));t=read_table(root/'t',g,root/'tdb');session=Session(g,t)
                write_jsonl(root/'c',source_rows(b['certificates'][0],g,t));session.check_source(root/'c',root/'state');result=session.finish()
                self.assertTrue(result.is_for(g,t));self.assertIs(session.finish(),result)
                if mode=='raw':
                    with (root/'graph.tsv').open('a') as s:s.write('o\tz\tnew-edge\t1\t1\n')
                else:
                    db=sqlite3.connect(root/('graph.sqlite' if mode=='representation' else 'tdb'))
                    db.execute("UPDATE edges SET l='2' WHERE ordinal=0" if mode=='representation' else "UPDATE pairs SET length='1'");db.commit();db.close()
                self.assertFalse(result.is_for(g,t))
                with self.assertRaises(ValueError):session.finish()
                self.assertTrue(session.failed);t.close();g.close()

    def test_large_exact_input_is_TEXT_and_no_decimal_digit_truncation(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'raw';p.write_text('a\tb\te\t'+('9'*5000)+'/7\t1\n');build(p,root/'db')
            g=validate(p,root/'db',root/'v')
            try:self.assertGreater(g.edge('e').time.numerator.bit_length(),16000)
            finally:g.close()

    def test_empty_explicit_graph_and_exact_alias_zero(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);g=graph_inputs(dict(nodes=['o'],edges=[]),root)
            p=dict(origin_anchor='o',destination_anchor='o',candidate_order=['Alias'],sites={'Alias':dict(anchor='o',effects=['C','S','CS'])},pairs=[dict(source='o',target='o',reachable=True,time_s='0',actual_length_m='0',nodes=['o'],edges=[])])
            write_jsonl(root/'t',table_rows(p,g));t=read_table(root/'t',g,root/'tdb');s=Session(g,t)
            c=dict(source='o',target_order=list(t.targets),labels={'o':'0'},predecessors={},target_masks={'o':1});write_jsonl(root/'c',source_rows(c,g,t));s.check_source(root/'c',root/'state')
            try:self.assertTrue(s.finish().is_for(g,t));self.assertEqual(t.candidate_order,('Alias',))
            finally:t.close();g.close()

    def test_owner_binding_partial_coverage_resource_stop_and_tampering(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);b=tiny_build();g=graph_inputs(b['graph_payload'],root)
            write_jsonl(root/'t',table_rows(b['table_payload'],g));t=read_table(root/'t',g,root/'tdb');s=Session(g,t)
            with self.assertRaises(ValueError):s.finish()
            with self.assertRaises(TypeError):Session(Graph.__new__(Graph),t)
            self.assertFalse(Checked.__new__(Checked).is_for(g,t))
            def stop():raise ResourceStop('deadline')
            bad=Session(g,t,check=stop)
            with self.assertRaises(ResourceStop):bad.check_source(root/'absent',root/'state')
            self.assertTrue(bad.failed)
            db=sqlite3.connect(root/'graph.sqlite');db.execute("UPDATE edges SET l='2' WHERE ordinal=0");db.commit();db.close()
            with self.assertRaises(ValueError):g.assert_unchanged()
            t.close();g.close()

    def test_missing_terminal_duplicate_pairs_and_unmatched_step_rejected(self):
        for mode in ('missing','duplicate','wrong_edge'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as d:
                root=Path(d);b=tiny_build();g=graph_inputs(b['graph_payload'],root);p=copy.deepcopy(b['table_payload'])
                if mode=='missing':p['pairs'].pop()
                elif mode=='duplicate':p['pairs'].append(p['pairs'][0])
                else:next(r for r in p['pairs'] if r['edges'])['edges'][0]='unknown'
                write_jsonl(root/'t',table_rows(p,g))
                try:
                    with self.assertRaises(ValueError):read_table(root/'t',g,root/'tdb')
                finally:g.close()


if __name__=='__main__':unittest.main()
