import copy
from fractions import Fraction
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from exact_leg_table import ExactLegTable
from exact_road_certificate import ExactRoadGraph,CertificateSession,CheckedRoadCertificate,Unsupported,decode
from road_certificate_fixtures import IDS,raw,graph_payload,build,fixture,evaluate,source_row,pair_row,rebound


def checked(bundle):
    session=CertificateSession(bundle['graph'],bundle['table'])
    for row in bundle['certificates']:session.check_source(raw(row))
    return session,session.finish()


class CertificateTests(unittest.TestCase):
    def test_complete_streamed_domain_includes_terminals_and_alias_zeros(self):
        b=build();session,result=checked(b)
        self.assertTrue(result.is_for(b['graph'],b['table']))
        self.assertEqual((result.checked_pairs,result.literal_sites),(20,5))
        self.assertEqual(sum(r['zero_pairs'] for r in result.source_receipts),4)
        self.assertEqual([r['source'] for r in result.source_receipts],list(b['table'].sources))
        self.assertIs(session.finish(),result)
        self.assertFalse(b['table'].road_selection_certified)  # Input flags are not promoted.
        self.assertNotEqual(b['table'].aliases['o'],b['table'].origin_anchor)
        with self.assertRaises(ValueError):session.check_source(raw(b['certificates'][0]))

    def test_valid_attaining_tree_need_not_be_canonical(self):
        f=fixture('valid_noncanonical_predecessor');b=f['bundle']
        self.assertEqual(source_row(b)['predecessors']['z'],'direct')
        self.assertEqual(b['table'].pairs['o','z'].edges,('10','az'))
        self.assertEqual(evaluate(f)['status'],'verified')

    def test_full_node_tuple_precedes_edge_tuple_and_selected_length_is_not_shortest(self):
        b=build();checked(b);pair=b['table'].pairs['o','z']
        self.assertEqual((pair.nodes,pair.edges,pair.time,pair.length),(('o','a','z'),('10','az'),Fraction(2),Fraction(20)))
        self.assertLess('00','10')  # Edge-first selection would incorrectly go through b.
        for name in ('wrong_node_tuple','wrong_parallel_string_edge','wrong_selected_length'):
            with self.subTest(name=name):self.assertEqual(evaluate(fixture(name))['status'],'rejected')

    def test_deep_shared_prefix_node_and_full_string_edge_tuple_ties(self):
        b=build(graph_payload('deep'),sites={});checked(b)
        self.assertEqual(b['table'].pairs['o','z'].nodes,('o','p','a','z'))
        self.assertEqual(b['table'].pairs['o','z'].edges,('prefix','10','az'))
        for mode in ('node','edge'):
            bad=build(graph_payload('deep'),sites={});row=pair_row(bad)
            if mode=='node':row.update(nodes=['o','p','b','z'],edges=['prefix','00','bz'],actual_length_m='3')
            else:row.update(edges=['prefix','2','az'],actual_length_m='12')
            rebound(bad)
            with self.subTest(mode=mode),self.assertRaisesRegex(ValueError,'not canonical'):checked(bad)
        r=evaluate(fixture('string_node_tuple'))
        self.assertEqual(r['status'],'verified');self.assertEqual(r['selected_example']['nodes'],('o','10','z'))

    def test_attaining_valid_slower_path_is_not_a_global_shortest_certificate(self):
        f=fixture('wrong_shortest_lower_certificate');b=f['bundle'];p=b['table'].pairs['o','z']
        self.assertEqual((p.time,p.nodes,p.edges),(Fraction(3),('o','z'),('slow-valid-path',)))
        c=source_row(b);self.assertEqual(c['predecessors']['z'],'slow-valid-path')
        with self.assertRaisesRegex(ValueError,'lower inequality'):checked(b)

    def test_unreachable_cut_and_all_node_label_domain_are_checked(self):
        b=build();self.assertFalse(b['table'].pairs['b','o'].reachable)
        self.assertTrue(b['table'].pairs['o','b'].reachable)
        with self.assertRaisesRegex(ValueError,'outgoing edge'):checked(fixture('false_unreachable_cut')['bundle'])
        for missing in ('a','dead'):
            b=build();source_row(b)['labels'].pop(missing)
            with self.subTest(missing=missing),self.assertRaisesRegex(ValueError,'every graph node'):checked(b)
        b=build();source_row(b)['labels']['a']='1/2'
        with self.assertRaisesRegex(ValueError,'predecessor'):checked(b)
        b=build();source_row(b)['predecessors']['z']='no-such-edge'
        with self.assertRaisesRegex(ValueError,'predecessor'):checked(b)

    def test_target_masks_cannot_hide_or_invent_tight_suffixes(self):
        with self.assertRaisesRegex(ValueError,'bitset equation'):checked(fixture('forged_target_masks')['bundle'])
        for value in (True,-1,1<<20):
            b=build();source_row(b)['target_masks']['a']=value
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'bitset'):checked(b)
        b=build();source_row(b)['target_order'].reverse()
        with self.assertRaisesRegex(ValueError,'target identity'):checked(b)

    def test_prefix_and_missing_source_or_terminal_never_certify_whole_table(self):
        b=build();session=CertificateSession(b['graph'],b['table']);session.check_source(raw(b['certificates'][0]))
        with self.assertRaisesRegex(ValueError,'incomplete'):session.finish()
        for row in b['certificates'][1:]:session.check_source(raw(row))
        self.assertTrue(session.finish().is_for(b['graph'],b['table']))
        for name in ('missing_source_coverage','missing_terminal_pair'):
            with self.subTest(name=name):self.assertEqual(evaluate(fixture(name))['status'],'rejected')
        for mode in ('duplicate','skip'):
            b=build();s=CertificateSession(b['graph'],b['table']);s.check_source(raw(b['certificates'][0]))
            index=0 if mode=='duplicate' else 2
            with self.subTest(mode=mode),self.assertRaises(ValueError):s.check_source(raw(b['certificates'][index]))
            self.assertTrue(s.failed)
            with self.assertRaises(ValueError):s.finish()

    def test_zero_time_edges_and_cycles_are_explicitly_unsupported_not_reduced(self):
        for name in ('zero_time_acyclic','zero_time_cycle'):
            f=fixture(name)
            with self.subTest(name=name),self.assertRaisesRegex(Unsupported,'zero-time'):ExactRoadGraph.from_bytes(raw(f['unsupported_graph']))
        # Positive cycles are supported; only the tight shortest-time DAG must be acyclic.
        self.assertIn('back-positive-cycle',build()['graph'].edges)
        self.assertEqual(evaluate(fixture('valid_empty_alias_zero'))['status'],'verified')

    def test_input_identity_and_owner_binding_cannot_be_replaced_by_claimed_flags(self):
        b=build();s,result=checked(b)
        clone=ExactRoadGraph.from_bytes(raw(b['graph_payload']))
        self.assertEqual(clone.payload_sha256,b['graph'].payload_sha256)
        self.assertFalse(result.is_for(clone,b['table']))
        clone_table=ExactLegTable.from_bytes(raw(b['table_payload']))
        self.assertFalse(result.is_for(b['graph'],clone_table))
        self.assertFalse(CheckedRoadCertificate().is_for(b['graph'],b['table']))
        with self.assertRaises(TypeError):ExactRoadGraph.from_dict(b['graph_payload'],payload_sha256='caller-override')
        b=build();source_row(b)['graph_sha256']='claimed'
        with self.assertRaisesRegex(ValueError,'digest'):checked(b)
        b=build();source_row(b)['verified']=True
        with self.assertRaisesRegex(ValueError,'fields'):checked(b)
        for field,value in [('graph',clone),('table',clone_table),('receipts',()),('failed',False)]:
            with self.subTest(field=field),self.assertRaises(AttributeError):setattr(s,field,value)
        with self.assertRaises(TypeError):s.receipts[0]['checked_pairs']=0

    def test_graph_contract_exact_types_and_duplicate_json_fail_closed(self):
        for value in (0,-1,True,.5,'0.5'):
            p=graph_payload();p['edges'][0]['time_s']=value
            with self.subTest(value=value),self.assertRaises((ValueError,TypeError)):ExactRoadGraph.from_bytes(raw(p))
        for mode in ('node','edge','endpoint','length','contract'):
            p=graph_payload()
            if mode=='node':p['nodes'].append(p['nodes'][0])
            elif mode=='edge':p['edges'][1]['edge_id']=p['edges'][0]['edge_id']
            elif mode=='endpoint':p['edges'][0]['source']='absent-node'
            elif mode=='length':p['edges'][0]['length_m']='0'
            else:p['selected_leg_contract']='min-time-then-length'
            with self.subTest(mode=mode),self.assertRaises((ValueError,TypeError)):ExactRoadGraph.from_bytes(raw(p))
        with self.assertRaisesRegex(ValueError,'duplicate JSON'):decode(b'{"a":1,"a":2}')
        with self.assertRaises(TypeError):CertificateSession(ExactRoadGraph(),build()['table'])

    def test_rational_labels_and_length_sums_are_exact(self):
        p=graph_payload('numeric');p['edges']=[dict(source='o',target='z',time_s='1/3',length_m='7/5',edge_id='fraction')]
        b=build(p,sites={});source_row(b)['labels']['z']='2/6'
        checked(b);self.assertEqual(b['table'].pairs['o','z'].length,Fraction(7,5))
        source_row(b)['labels']['z']=.3333333333
        with self.assertRaises(TypeError):checked(b)

    def test_resource_callback_at_finish_cannot_issue_a_late_whole_certificate(self):
        stopped=[False]
        def guard():
            if stopped[0]:raise RuntimeError('resource stop')
        b=build();session=CertificateSession(b['graph'],b['table'],guard)
        for row in b['certificates']:session.check_source(raw(row))
        stopped[0]=True
        with self.assertRaisesRegex(RuntimeError,'resource stop'):session.finish()
        stopped[0]=False
        with self.assertRaisesRegex(ValueError,'failed'):session.finish()

    def test_gate_consumes_saved_certificate_bytes_not_generator_answers(self):
        from run_road_certificate_gate import materialize,evaluate_saved
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'cell';materialize(fixture('valid_full_table'),path)
            self.assertEqual(evaluate_saved(path)['status'],'verified')
            file=sorted(path.glob('source-*.json'))[-1]
            value=json.loads(file.read_bytes());value['graph_sha256']='different-actual-input'
            file.write_bytes(raw(value))
            self.assertEqual(evaluate_saved(path)['status'],'rejected')

    def test_receipt_join_cannot_pass_empty_missing_or_tampered_case_coverage(self):
        from report_road_certificate_gate import report
        import hashlib
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);gate=root/'gate';gate.mkdir();rows=[]
            for name in IDS:
                folder=gate/name;folder.mkdir();graph=b'mock graph';(folder/'graph.json').write_bytes(graph)
                actual=dict(status='unsupported' if name.startswith('zero_time_') else
                    'verified' if name.startswith('valid_') or name in ('string_node_tuple','deep_tuple_ties') else 'rejected')
                hashes={'graph.json':hashlib.sha256(graph).hexdigest()}
                if actual['status']=='verified':
                    table=dict(origin_anchor='o',destination_anchor='z',sites={},candidate_order=[],pairs=[dict(source='o',target='z')])
                    data=raw(table);(folder/'table.json').write_bytes(data);cert=b'mock certificate';(folder/'source-0000.json').write_bytes(cert)
                    hashes.update({'table.json':hashlib.sha256(data).hexdigest(),'source-0000.json':hashlib.sha256(cert).hexdigest()})
                    actual.update(checked_pairs=1,literal_sites=0,physical_sources=1,physical_targets=1,owns_exact_inputs=True,
                        graph_sha256=hashes['graph.json'],table_sha256=hashes['table.json'],
                        source_receipts=[dict(source='o',checked_pairs=1,certificate_sha256=hashes['source-0000.json'])])
                rows.append(dict(case=name,status='verified',expected=actual['status'],actual=actual,input_sha256=hashes))
            result=dict(case_denominator=15,rows=rows,source=dict(commit='mock',dirty=False),config_sha256='mock',
                real_table_generation=False,real_scale_optimization=False,holdout=False,production_oracle=False)
            path=gate/'results.json';path.write_bytes(raw(result))
            commands=[dict(label=x,pid=1,returncode=0,charged_CPU_s=0) for x in
                ('saved_input_checker_normal','saved_input_checker_optimized','final_receipt_normal','final_receipt_optimized','receipt_integrity_normal','receipt_integrity_optimized','frozen_certificate_gate')]
            (root/'budget.json').write_bytes(raw(dict(active=None,records=commands,charged_commands_CPU_s=0,carried_research_CPU_s='15646.570668741')))
            self.assertEqual(report(root)['gate_status'],'PASS_TINY_CERTIFICATE_CHECKER')
            for mode in ('empty','missing','duplicate'):
                bad=copy.deepcopy(result)
                if mode=='empty':bad['rows']=[]
                elif mode=='missing':bad['rows'].pop()
                else:bad['rows'][1]=bad['rows'][0]
                path.write_bytes(raw(bad))
                with self.subTest(mode=mode),self.assertRaises(ValueError):report(root)
            partial=copy.deepcopy(result);partial['rows'][-1]=dict(case=IDS[-1],status='unrun')
            path.write_bytes(raw(partial));joined=report(root)
            self.assertEqual(joined['gate_status'],'LIMITED_OR_FAILED');self.assertEqual(joined['rows'][-1]['status'],'unrun')
            path.write_bytes(raw(result));file=gate/IDS[0]/'source-0000.json';file.write_bytes(b'changed')
            self.assertEqual(report(root)['gate_status'],'LIMITED_OR_FAILED')
            budget=json.loads((root/'budget.json').read_text());budget['records'].append(dict(label='frozen_certificate_gate_extra',pid=2,returncode=0))
            (root/'budget.json').write_bytes(raw(budget))
            with self.assertRaisesRegex(ValueError,'unexpected formal gate'):report(root)

    def test_checker_does_not_call_a_router_optimizer_or_fixture_producer(self):
        b=build()
        import builtins
        original=builtins.__import__
        def block(name,*a,**kw):
            if name.split('.')[0] in ('hiroute','hiroute_ref','timecut5','z3','tiny_smt','road_certificate_fixtures'):
                raise AssertionError('routing/optimization/fixture dependency')
            return original(name,*a,**kw)
        spec=importlib.util.spec_from_file_location('isolated_road_certificate',ROOT/'tools/exact_road_certificate.py')
        module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module
        try:
            with patch('builtins.__import__',side_effect=block):
                spec.loader.exec_module(module)
                g=module.ExactRoadGraph.from_bytes(raw(b['graph_payload']))
                session=module.CertificateSession(g,b['table'])
                for row in b['certificates']:session.check_source(raw(row))
                self.assertTrue(session.finish().is_for(g,b['table']))
        finally:sys.modules.pop(spec.name,None)


if __name__=='__main__':unittest.main()
