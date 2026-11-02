import copy
from fractions import Fraction
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from dataclasses import FrozenInstanceError

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from road_certificate_fixtures import build as tiny_build,graph_payload,edge
from streaming_road_fixtures import graph_inputs,analytic_wide
from streaming_road_graph import sha,ResourceStop
from streaming_road_certificate import (read_source_unit,read_table,SourceSession,Session,UNIT_SCHEMA)
from generate_exact_source_unit import generate


def header(bundle,g,source='o'):
    p=bundle['table_payload']
    return dict(schema=UNIT_SCHEMA,numerical_contract=p['numerical_contract'],selected_leg_contract=p['selected_leg_contract'],
        graph_identity='sha256:'+g.payload_sha256,source_unit=source,
        **{k:p[k] for k in ('origin_anchor','destination_anchor','candidate_order','sites')})


class OneSourceTests(unittest.TestCase):
    def produce(self,root,bundle,source='o'):
        g=graph_inputs(bundle['graph_payload'],root)
        result=generate(g.path,header(bundle,g,source),root/'generated',expected_graph_sha=g.representation_sha256)
        return g,result

    def test_independent_exhaustive_tiny_parity_nodes_edges_lengths_and_reachability(self):
        for kind in ('base','deep','numeric'):
            b=tiny_build(graph_payload(kind),sites={} if kind!='base' else None)
            for source in b['table'].sources:
                with self.subTest(kind=kind,source=source),tempfile.TemporaryDirectory() as d:
                    root=Path(d);g,result=self.produce(root,b,source)
                    t=read_source_unit(root/'generated/paths.jsonl',g,root/'table.sqlite')
                    try:
                        self.assertEqual(t.sources,b['table'].sources);self.assertEqual(t.targets,b['table'].targets)
                        for target in t.targets:
                            expected=b['table'].pairs[source,target];reach,T,L=t.pair(source,target)
                            self.assertEqual(bool(reach),expected.reachable)
                            if reach:
                                self.assertEqual((Fraction(T),Fraction(L)),(expected.time,expected.length))
                                steps=list(t.steps(source,target))
                                self.assertEqual(tuple([source]+[r[1] for r in steps]),expected.nodes)
                                self.assertEqual(tuple(r[2] for r in steps),expected.edges)
                        session=SourceSession(g,t);session.check_source(root/'generated/source.jsonl',root/'checked');out=session.finish()
                        self.assertFalse(out['whole_table_certified']);self.assertEqual(out['source_denominator'],len(b['table'].sources))
                        self.assertEqual(out['unrun_sources'],len(b['table'].sources)-1)
                    finally:t.close();g.close()

    def test_full_N64_65bit_domain_remains_in_source_unit(self):
        b=analytic_wide()['bundle']
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);g,result=self.produce(root,b);t=read_source_unit(root/'generated/paths.jsonl',g,root/'table')
            try:
                self.assertEqual((len(t.sources),len(t.targets),result['candidate_pairs']),(65,65,65))
                session=SourceSession(g,t);session.check_source(root/'generated/source.jsonl',root/'checked');out=session.finish()
                self.assertEqual((out['checked_pairs'],out['pair_denominator'],out['unrun_sources']),(65,4225,64))
                cert=[json.loads(r) for r in (root/'generated/source.jsonl').read_text().splitlines()]
                self.assertEqual(next(r['mask'] for r in cert[1:] if r['node']=='o'),str((1<<65)-1))
                with self.assertRaises(TypeError):Session(g,t)
                with self.assertRaises(ValueError):Session.finish(session)
                with self.assertRaises(ValueError):read_table(root/'generated/paths.jsonl',g,root/'whole')
            finally:t.close();g.close()

    def test_exact_large_path_arithmetic_and_zero_alias(self):
        p,q=2**83-9,2**83-71
        gp=graph_payload();gp.update(nodes=['o','a','z'],edges=[edge('o','a','1/'+str(p),2**120,'01'),edge('a','z','1/'+str(q),1,'10')])
        b=tiny_build(gp,sites={'Alias':dict(anchor='o',effects=['C'])})
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);g,_=self.produce(root,b);t=read_source_unit(root/'generated/paths.jsonl',g,root/'table')
            try:
                self.assertEqual(t.pair('o','o'),(1,'0','0'));self.assertGreater(Fraction(t.pair('o','z')[1]).denominator.bit_length(),84)
                self.assertEqual(Fraction(t.pair('o','z')[2]),2**120+1)
                s=SourceSession(g,t);s.check_source(root/'generated/source.jsonl',root/'checked');self.assertFalse(s.finish()['whole_table_certified'])
            finally:t.close();g.close()

    def test_unit_coverage_mixing_and_wrong_certificates_fail_closed(self):
        for mode in ('missing_pair','extra_source','missing_node','wrong_mask','wrong_label','changed_hash','target_order'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as d:
                root=Path(d);g,_=self.produce(root,tiny_build());paths=root/'generated/paths.jsonl';cert=root/'generated/source.jsonl'
                if mode in ('missing_pair','extra_source'):
                    rows=[json.loads(v) for v in paths.read_text().splitlines()]
                    if mode=='missing_pair':
                        first=next(i for i,r in enumerate(rows[1:],1) if r=={'kind':'end_pair'});rows=rows[:1]+rows[first+1:]
                    else:rows[1]['source']='a'
                    paths.write_text(''.join(json.dumps(r)+'\n' for r in rows))
                    with self.assertRaises(ValueError):read_source_unit(paths,g,root/'table')
                else:
                    t=read_source_unit(paths,g,root/'table');rows=[json.loads(v) for v in cert.read_text().splitlines()]
                    if mode=='missing_node':rows.pop()
                    elif mode=='wrong_mask':next(r for r in rows[1:] if r['node']=='o')['mask']='0'
                    elif mode=='wrong_label':next(r for r in rows[1:] if r['node']=='a')['label']='999'
                    elif mode=='changed_hash':rows[0]['table_sha256']='0'*64
                    else:rows[0]['target_order']=list(reversed(rows[0]['target_order']))
                    cert.write_text(''.join(json.dumps(r)+'\n' for r in rows));session=SourceSession(g,t)
                    with self.assertRaises(ValueError):session.check_source(cert,root/'checked')
                    self.assertTrue(session.failed)
                    with self.assertRaises(ValueError):session.finish()
                    t.close()
                g.close()

    def test_partial_source_never_finishes_or_replays(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);g,_=self.produce(root,tiny_build());t=read_source_unit(root/'generated/paths.jsonl',g,root/'table');s=SourceSession(g,t)
            try:
                with self.assertRaises(ValueError):s.finish()
                s.check_source(root/'generated/source.jsonl',root/'checked');s.finish()
                with self.assertRaises(ValueError):s.check_source(root/'generated/source.jsonl',root/'duplicate')
                # Replay consumes the owned SQLite representation, not its historical
                # JSONL input stream. Mutate the actual retained representation.
                with t.path.open('ab') as changed:changed.write(b'changed')
                with self.assertRaises(ValueError):s.finish()
            finally:t.close();g.close()

    def test_valid_but_noncanonical_path_rejected_even_with_rebound_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);g,_=self.produce(root,tiny_build());paths=root/'generated/paths.jsonl'
            rows=[json.loads(v) for v in paths.read_text().splitlines()];start=next(i for i,r in enumerate(rows) if r.get('kind')=='pair' and r['target']=='z')
            end=next(i for i in range(start+1,len(rows)) if rows[i]=={'kind':'end_pair'})
            row=dict(rows[start],length_m='2')
            rows[start:end+1]=[row,dict(kind='step',u='o',v='b',edge_id='00'),dict(kind='step',u='b',v='z',edge_id='bz'),dict(kind='end_pair')]
            paths.write_text(''.join(json.dumps(r)+'\n' for r in rows));t=read_source_unit(paths,g,root/'table')
            cert=root/'generated/source.jsonl';c=[json.loads(v) for v in cert.read_text().splitlines()];c[0]['table_sha256']=sha(paths)
            cert.write_text(''.join(json.dumps(r)+'\n' for r in c));s=SourceSession(g,t)
            try:
                with self.assertRaisesRegex(ValueError,'noncanonical'):s.check_source(cert,root/'checked')
                self.assertTrue(s.failed)
            finally:t.close();g.close()

    def test_cross_graph_owner_and_unit_source_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);b=tiny_build();g,_=self.produce(root,b);t=read_source_unit(root/'generated/paths.jsonl',g,root/'table')
            other=root/'other';other.mkdir();g2=graph_inputs(b['graph_payload'],other)
            try:
                with self.assertRaises(TypeError):SourceSession(g2,t)
                h=header(b,g);h['source_unit']='not-present'
                with self.assertRaises(ValueError):generate(g.path,h,root/'outside',expected_graph_sha=g.representation_sha256)
            finally:t.close();g.close();g2.close()

    def test_source_unit_extra_fields_and_ownership_are_immutable(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);g,_=self.produce(root,tiny_build());t=read_source_unit(root/'generated/paths.jsonl',g,root/'table')
            try:
                for name,value in [('unit_source','a'),('_graph_owner',object()),('_db',None),('_validated',False),('injected',True)]:
                    with self.subTest(field=name),self.assertRaises(FrozenInstanceError):setattr(t,name,value)
                s=SourceSession(g,t);s.check_source(root/'generated/source.jsonl',root/'checked');self.assertFalse(s.finish()['whole_table_certified'])
            finally:t.close();g.close()

    def test_generation_resource_stop_and_input_mutation_never_issue_success(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);b=tiny_build();g=graph_inputs(b['graph_payload'],root);h=header(b,g)
            def stop():raise ResourceStop('injected')
            try:
                with self.assertRaises(ResourceStop):generate(g.path,h,root/'partial',expected_graph_sha=g.representation_sha256,check=stop)
                self.assertFalse((root/'partial/source.jsonl').exists())
                with self.assertRaises(FileExistsError):generate(g.path,h,root/'partial',expected_graph_sha=g.representation_sha256)
                with self.assertRaises(ValueError):generate(g.path,h,root/'bad_hash',expected_graph_sha='0'*64)
            finally:g.close()

    def test_report_rejects_empty_duplicate_active_and_incomplete_proof(self):
        from report_one_source_gate import summarize
        b=analytic_wide()['bundle'];p=b['table_payload']
        h=dict(schema=UNIT_SCHEMA,numerical_contract=p['numerical_contract'],selected_leg_contract=p['selected_leg_contract'],
            graph_identity='sha256:mock',source_unit='o',**{k:p[k] for k in ('origin_anchor','destination_anchor','candidate_order','sites')})
        generation=dict(label='real_origin_generation',phase='real_pair',child_CPU_limit=120,wall_limit=120,reserved_CPU_s=150,charged_CPU_s=10,finished_at=1,returncode=125,guard_reason='wall_guard')
        budget=dict(active=None,source='o',source_denominator=65,pair_denominator=4225,records=[generation],fixed_precharge_CPU_s=240,
            phase_charged_CPU_s=dict(tiny_validation=0,real_pair=10,verification_tails=0),allocations_CPU_s=dict(tiny_validation=180,real_pair=300,verification_tails=180),carried_research_CPU_s='16342.296649741')
        with patch('report_one_source_gate.frozen_header',return_value=h):
            result=summarize({'source':'o'},'unused',budget,None)
            self.assertEqual(result['independently_certified_pairs'],0);self.assertEqual(sum(result['pair_status_counts'].values()),4225)
            self.assertEqual(len(result['source_statuses']),65)
            for mode in ('empty','duplicate','active','incomplete_check','hidden_phase','charge_drift'):
                altered=copy.deepcopy(budget)
                if mode=='empty':altered['records']=[]
                elif mode=='duplicate':altered['records'].append(generation)
                elif mode=='active':altered['active']={'pid':1}
                elif mode=='incomplete_check':altered['records'].append(dict(generation,label='real_origin_check',charged_CPU_s=0))
                elif mode=='hidden_phase':altered['records'].append(dict(generation,label='hidden',phase='unaccounted'))
                else:altered['phase_charged_CPU_s']['real_pair']=9
                with self.subTest(mode=mode),self.assertRaises(ValueError):summarize({'source':'o'},'unused',altered,None)
            good=copy.deepcopy(budget);good['records'][0].update(returncode=0,guard_reason=None)
            good['records'].append(dict(good['records'][0],label='real_origin_check',charged_CPU_s=0))
            producer=dict(decision='UNTRUSTED_SOURCE_CANDIDATE_COMPLETE')
            checked=dict(decision='VERIFIED_SINGLE_SOURCE_ONLY',result=dict(source='o',checked_pairs=65,source_denominator=65,pair_denominator=4225,unrun_sources=64,whole_table_certified=False))
            self.assertEqual(summarize({'source':'o'},'unused',good,None,producer_result=producer,checker_result=checked)['independently_certified_pairs'],65)
            for mode in ('check_limits','check_phase','whole_claim','missing_pairs'):
                altered=copy.deepcopy(good);result=copy.deepcopy(checked)
                if mode=='check_limits':altered['records'][-1]['wall_limit']=121
                elif mode=='check_phase':altered['records'][-1]['phase']='verification_tails'
                elif mode=='whole_claim':result['result']['whole_table_certified']=True
                else:result['result']['checked_pairs']=64
                with self.subTest(mode=mode),self.assertRaises(ValueError):summarize({'source':'o'},'unused',altered,None,producer_result=producer,checker_result=result)


if __name__=='__main__':unittest.main()
