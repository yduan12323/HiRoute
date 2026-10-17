import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parents[1]/'checkpoint_contract_work/source'
sys.path[:0]=[str(ROOT),str(ROOT.parent/'candidate/src'),str(SOURCE/'tests/m5d_recovery'),str(SOURCE)]
import test_sparse_feasible_execution as helpers
from fixture_source import Router
from timecut5.feasible_incumbent import canonical
from timecut5.layer_envelope import LayerEnvelopeStop
from timecut5.road_provider import TableFreeRegionBoundProvider
from timecut5.hierarchy import build_regions
from sparse_layer_session import SparseLayerSession
import production_boundary as boundary

class Tests(unittest.TestCase):
    def setUp(self):
        self.h=helpers.Tests();self.h.setUp();self.addCleanup(self.h.doCleanups);self.serial=0
    def context(self,case='nonbest',previous=None,depth=None):
        admission,path=self.h.admission(case)
        search=self.h.inputs(case,path);verifier=self.h.inputs(case,path)
        c=search['catalog'];root=build_regions(c.sites)
        bound=TableFreeRegionBoundProvider(c.provider,c.sites,root,destination_anchor=c.destination_anchor,
            landmark_anchor=c.origin_anchor,site_catalog_sha256=c.site_catalog_sha256,router_factory=Router)
        sources=dict(nodes=verifier['nodes_path'],edges=verifier['edges_path'],router=verifier['router_source_path'])
        sessions=[];self.serial+=1;output=self.h.root/f'layer-{self.serial}.json'
        def factory(query,a,provider,method):
            session=SparseLayerSession(output,method=method,exact_query=query,admission=a,
                search_provider=provider,verifier_catalog=verifier['catalog'],source_paths=sources,
                policy_check=lambda:None,previous_checkpoint=previous,stop_after_depth=depth)
            sessions.append(session);return session
        options=dict(admission=admission,catalog=c,provider=c.provider,bound=bound,root=root,
            initial='tiny_test',spec={'region_tree_sha256':'tiny_test'},stage=lambda *a,**k:None,
            policy_check=lambda:None)
        return options,factory,sessions,verifier,output
    def test_production_dispatch_three_cases_both_methods_parity(self):
        for case in ('nonbest','charge_required','equality'):
            for method in ('flat','hier'):
                base,*_=self.context(case);expected=boundary._execute_admitted(method=method,**base)
                options,factory,sessions,verifier,output=self.context(case)
                actual=boundary._execute_admitted(method=method,**options,checkpoint_factory=factory)
                self.assertEqual(actual,expected)
                row=json.loads(output.read_bytes())
                self.assertFalse(row['header']['complete'])
                self.assertEqual(row['state']['H_ref'],options['admission'].incumbent.max_depth)
                self.assertIsNot(sessions[0].catalog.provider,options['provider'])
                self.assertGreater(verifier['catalog'].provider.source_run_count,0)
    def test_fresh_dispatch_restores_original_seed_same_domain(self):
        for method in ('flat','hier'):
            options,factory,_,_,output=self.context(depth=1)
            with self.assertRaises(LayerEnvelopeStop):boundary._execute_admitted(method=method,**options,checkpoint_factory=factory)
            previous=output.read_bytes()
            resumed,factory,_,_,_=self.context(previous=previous)
            actual=boundary._execute_admitted(method=method,**resumed,checkpoint_factory=factory)
            base,*_=self.context();expected=boundary._execute_admitted(method=method,**base)
            self.assertEqual(actual,expected)
    def test_alias_source_and_query_mutation_rejected(self):
        options,factory,sessions,verifier,_=self.context()
        a=options['admission'];query=dict(json.loads(a.incumbent.query_bytes),H_ref=a.incumbent.max_depth)
        with self.assertRaisesRegex(ValueError,'Independent verifier'):
            factory(query,a,verifier['catalog'].provider,'flat')
        session=factory(query,a,options['provider'],'flat')
        session.query['H_ref']+=1
        with self.assertRaisesRegex(ValueError,'domain or transitive'):session.bindings()
        session.query['H_ref']-=1
        verifier['nodes_path'].write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'domain or transitive'):session.bindings()
    def test_actual_search_factory_root_and_bound_rejected(self):
        options,factory,sessions,_,_=self.context()
        original=SparseLayerSession.run
        def changed(session,**kwargs):
            kwargs['problem'].case=dict(kwargs['problem'].case,H_ref=999)
            return original(session,**kwargs)
        with patch.object(SparseLayerSession,'run',changed):
            with self.assertRaisesRegex(ValueError,'factory or Region'):
                boundary._execute_admitted(method='flat',**options,checkpoint_factory=factory)
    def test_effective_fields_with_unchanged_case_are_rejected(self):
        for field in ('penalty','bound','start','reserve','rate','overhead','initial_remaining','legs_rate'):
            options,factory,*_=self.context(depth=0)
            original=SparseLayerSession.run
            def changed(session,**kwargs):
                problem=kwargs['problem']
                if field=='legs_rate':problem.legs.rate+=1000
                else:setattr(problem,field,getattr(problem,field)+1000)
                return original(session,**kwargs)
            with self.subTest(field=field),patch.object(SparseLayerSession,'run',changed):
                with self.assertRaisesRegex(ValueError,'Effective production'):
                    boundary._execute_admitted(method='flat',**options,checkpoint_factory=factory)
    def test_mutated_live_landmark_labels_rejected(self):
        from dataclasses import replace
        options,factory,*_=self.context(depth=0)
        bound=options['bound'];landmark=bound.landmarks[0]
        altered=dict(landmark.from_landmark);altered[next(iter(altered))]+=1000
        bound.landmarks=(replace(landmark,from_landmark=altered),)
        with self.assertRaisesRegex(ValueError,'Live landmark'):
            boundary._execute_admitted(method='flat',**options,checkpoint_factory=factory)
    def test_mutated_region_summary_or_action_coverage_rejected(self):
        from dataclasses import replace
        for kind in ('summary','mask','actions','members'):
            options,factory,*_=self.context(depth=0)
            bound=options['bound']
            if kind=='summary':
                key=next(iter(bound._summary));bound._summary[key]=replace(bound._summary[key],min_from_landmark=(999999.0,))
            if kind=='mask':bound._action_masks[next(iter(bound._action_masks))]=123456
            if kind=='actions':bound._actions[next(iter(bound._actions))]=(('fake','C'),)
            if kind=='members':bound._member_hash[next(iter(bound._member_hash))]='a'*64
            with self.subTest(kind=kind),self.assertRaisesRegex(ValueError,'bound summaries or action'):
                boundary._execute_admitted(method='hier',**options,checkpoint_factory=factory)
    def test_native_output_path_normalization_preserves_all_other_identity(self):
        import copy
        native=dict(binary_path='/first/output.so',compiler_command=['g++','-O3','source.cpp','-o','/first/output.so'],
            loaded_binary_path_verified=True,source_sha256='a'*64,binary_sha256='b'*64,compiler_sha256='c'*64)
        other=copy.deepcopy(native);other['binary_path']='/second/output.so';other['compiler_command'][-1]=other['binary_path']
        self.assertEqual(boundary.normalized_native_identity(native),boundary.normalized_native_identity(other))
        for key in ('source_sha256','binary_sha256','compiler_sha256'):
            changed=copy.deepcopy(other);changed[key]='d'*64
            self.assertNotEqual(boundary.normalized_native_identity(native),boundary.normalized_native_identity(changed))
        other['compiler_command'][1]='-O2'
        self.assertNotEqual(boundary.normalized_native_identity(native),boundary.normalized_native_identity(other))
        other['compiler_command'][-1]='/wrong.so'
        with self.assertRaises(ValueError):boundary.normalized_native_identity(other)
    def test_mutually_exclusive_persistence_before_dispatch(self):
        options,factory,*_=self.context()
        with self.assertRaisesRegex(ValueError,'Choose durable-only'):
            boundary._execute_admitted(method='flat',**options,checkpoint_factory=factory,durable_factory=lambda *a:None)
    def test_production_admission_gate_still_rejects_synthetic(self):
        options,*_=self.context()
        with self.assertRaisesRegex(ValueError,'explicitly frozen production'):
            boundary.runtime_policy({'catalog':options['catalog']},{},{})
    def test_rehashed_checkpoint_source_or_bound_is_not_reused(self):
        from timecut5.layer_envelope import _hash,_bytes
        options,factory,_,_,output=self.context(depth=1)
        with self.assertRaises(LayerEnvelopeStop):boundary._execute_admitted(method='flat',**options,checkpoint_factory=factory)
        row=json.loads(output.read_bytes());row['state']['lower_bounds']['bounded_domain_conservative_primary']='9999'
        row['history'][-1]=_hash(row['state'])
        options,factory,*_=self.context(previous=_bytes(row))
        with self.assertRaisesRegex(ValueError,'Reconstructed'):
            boundary._execute_admitted(method='flat',**options,checkpoint_factory=factory)

if __name__=='__main__':unittest.main(verbosity=2)
