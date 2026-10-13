"""Same-full-domain admission only; no heuristic enumeration or exact solve."""
from dataclasses import replace
from fractions import Fraction as R
import json
from pathlib import Path
import resource
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT), str(ROOT.parents[1])]
from timecut5 import deployable as d
from timecut5 import exact_feasible_incumbent as f
from timecut5.real_legs import encode_binary64, SCHEMA, NUMERICS, TIE_POLICY


def fixture(root):
    graph=f.canonical({'anchors':['A','B','D'],'selected_times':[[0,1,3],[1,0,2],[3,2,0]]})
    router=b'tiny fixture externally reviewed complete selected-pair policy'
    paths={}
    for name,data in [('graph.json',graph),('router.txt',router)]:
        paths[name]=root/name;paths[name].write_bytes(data)
    hierarchy=f.canonical(dict(site_ids=['s'],regions=[dict(parent=-1,children=[],members=[0])]));sites=[dict(site_id='s',anchor_id='B',effects=['C'])]
    payload=dict(schema=SCHEMA,numerical_contract=NUMERICS,anchors=['A','B','D'],origin_anchor='A',destination_anchor='D',
        sites=sites,source_sha256={'graph.json':f.sha(graph)},
        backend=dict(name='fixture',tie_policy=TIE_POLICY,direction_policy='forward_per_source_v1',
                     source_sha256={'router.txt':f.sha(router)}),
        hierarchy_sha256=f.sha(hierarchy),selection_certificate_sha256=f.sha(b'fixture selected pair review'),legs=[])
    distances=json.loads(graph)['selected_times']
    for i,a in enumerate(payload['anchors']):
        for j,b in enumerate(payload['anchors']):
            payload['legs'].append(dict(source_anchor=a,target_anchor=b,reachable=True,
                label_direction='identity' if i==j else 'forward_from_source',
                time_s=encode_binary64(float(distances[i][j])),actual_length_m=encode_binary64(float(distances[i][j]))))
    table=f.canonical(payload); candidates=f.canonical(['s'])
    query=f.canonical(dict(origin='A',destination='D',H_ref=1,start_time_s=0,
        initial_energy_kwh=10,capacity_kwh=20,minimum_energy_kwh=0,reserve_kwh=1,
        consumption_kwh_per_m=1,overhead_s=2,lambda_stop_s=1,
        charging_segments=[[0,20,1,0]],schedule=None,
        hierarchy_sha256=f.sha(hierarchy),leg_payload_sha256=f.sha(table),selection_certificate_sha256=payload['selection_certificate_sha256']))
    source_bytes=dict(graph_sha256=graph,site_catalog_sha256=f.canonical(sites),population_sha256=b'fixture population',
        hierarchy_sha256=hierarchy,landmark_sha256=b'fixture no landmarks',selected_leg_contract_sha256=TIE_POLICY.encode(),
        candidate_set_sha256=candidates,query_sha256=query,mobility_budget_sha256=b'unrestricted',
        depth_policy_sha256=b'positive_overhead_verified_seed_v1',numeric_contract_sha256=NUMERICS.encode())
    binding=d.DomainBinding.from_verified_bytes({k:(v,f.sha(v)) for k,v in source_bytes.items()})
    domain=d.QueryDomain(binding,query,candidates,table,f.sha(table))
    witness=dict(schema=f.SCHEMA,domain={k:getattr(binding,k) for k in binding.__dataclass_fields__},
                 table_sha256=domain.table_sha256,sequence=[['s','C']],charges=['3'])
    manifest=json.loads((ROOT/'REF_SOURCE_MANIFEST.json').read_text())
    approved={('package' if Path(e['path']).stem=='__init__' else Path(e['path']).stem):e['sha256'] for e in manifest['files']}
    return domain,witness,dict(expected_domain=binding,approved_verifier_sha256=approved,actual_source_paths=paths)


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.domain,self.witness,self.kw=fixture(Path(self.tmp.name))
    def admit(self,witness=None,**kw):
        return f.admit_exact_feasible_incumbent(self.domain,f.canonical(self.witness if witness is None else witness),**(self.kw|kw))

    def test_any_feasible_same_domain_plan_no_enumeration_or_solver(self):
        from validation.reference5 import real_solver, solver, lp
        with patch.object(d,'constructive_seed_candidates',side_effect=AssertionError('heuristic called')), \
             patch.object(d,'iter_constructive_seed_candidates',side_effect=AssertionError('iterator called')), \
             patch.object(d,'construct_verified_seed',side_effect=AssertionError('completed seed called')), \
             patch.object(real_solver,'solve_real_case',side_effect=AssertionError('REF optimizer called')), \
             patch.object(solver,'solve_prepared_case',side_effect=AssertionError('regime optimizer called')), \
             patch.object(lp,'exact_lp',side_effect=AssertionError('LP called')):
            certificate=self.admit()
            self.assertEqual(certificate.seed.primary_j,R(9))
            self.assertEqual(certificate.max_depth,3) # exact equality is included
            direct=dict(self.witness,sequence=[],charges=[])
            better=self.admit(direct)
            self.assertEqual(better.seed.primary_j,R(3))
            self.assertLess(better.seed.primary_j,certificate.seed.primary_j)
            admitted=f.prepare_exact_feasible_admission(certificate,**self.kw)
            self.assertEqual(admitted.primary_upper,R(9))
            self.assertEqual(json.loads(admitted.bounded_query_bytes)['H_ref'],3)
            self.assertEqual(json.loads(certificate.domain.query_bytes)['H_ref'],1)
            self.assertFalse(certificate.heuristic_minimum_claimed)
            self.assertFalse(certificate.exact_optimum_claimed)
            self.assertNotIsInstance(certificate,d.SeedDepthCertificate)
            with self.assertRaises(ValueError): d.solve_deployable_pair(certificate,b'',self.kw['approved_verifier_sha256'])

    def test_every_domain_field_must_match_frozen_target(self):
        for key in self.domain.binding.__dataclass_fields__:
            wrong=replace(self.domain.binding,**{key:'a'*64})
            with self.subTest(key=key),self.assertRaises(ValueError): self.admit(expected_domain=wrong)
            w=dict(self.witness,domain=dict(self.witness['domain'],**{key:'a'*64}))
            with self.subTest(witness_key=key),self.assertRaises(ValueError): self.admit(w)

    def test_physical_or_table_tampering_fails(self):
        for w in [dict(self.witness,charges=['0']),dict(self.witness,charges=['100']),
                  dict(self.witness,charges=[True]),dict(self.witness,charges=[3.0]),
                  dict(self.witness,sequence=[['missing','C']]),dict(self.witness,table_sha256='a'*64),
                  dict(self.witness,unknown_upper_bound=0)]:
            with self.assertRaises(ValueError): self.admit(w)

    def test_source_file_and_verifier_hash_changes_fail(self):
        with self.assertRaises(ValueError): self.admit(approved_verifier_sha256={})
        changed=dict(self.kw['approved_verifier_sha256'],lp='a'*64)
        with self.assertRaises(ValueError): self.admit(approved_verifier_sha256=changed)
        self.kw['actual_source_paths']['graph.json'].write_bytes(b'changed')
        with self.assertRaises(ValueError): self.admit()

    def test_untrusted_bound_or_certificate_fields_replayed(self):
        c=self.admit()
        for bad in [replace(c,max_depth=0),replace(c,seed=replace(c.seed,primary_j=R(1))),
                    replace(c,witness_sha256='a'*64),replace(c,sequence=()),replace(c,source_sha256=())]:
            with self.assertRaises(ValueError): f.prepare_exact_feasible_admission(bad,**self.kw)
        with self.assertRaises(ValueError): f.prepare_exact_feasible_admission(None,**self.kw)

    def test_missing_pair_never_becomes_unreachable(self):
        payload=json.loads(self.domain.table_bytes);payload['legs'].pop()
        data=f.canonical(payload)
        with self.assertRaises(ValueError): replace(self.domain,table_bytes=data,table_sha256=f.sha(data))

    def test_query_float_and_nonpositive_overhead_rejected(self):
        # Rebinding is explicit in this test, so rejection must be semantic.
        for value in [0,-1,2.0]:
            query=dict(json.loads(self.domain.query_bytes),overhead_s=value);data=f.canonical(query)
            binding=replace(self.domain.binding,query_sha256=f.sha(data))
            domain=replace(self.domain,binding=binding,query_bytes=data)
            w=dict(self.witness,domain={k:getattr(binding,k) for k in binding.__dataclass_fields__})
            with self.assertRaises(ValueError): f.admit_exact_feasible_incumbent(domain,f.canonical(w),**(self.kw|dict(expected_domain=binding)))

if __name__=='__main__':
    resource.setrlimit(resource.RLIMIT_CPU,(60,60));started=time.process_time()
    r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    report=dict(tests_run=r.testsRun,failures=len(r.failures),errors=len(r.errors),cpu_seconds=time.process_time()-started,
                real_od_runs=0,exact_solver_runs=0,heuristic_enumerations=0)
    (ROOT/'EXACT_ADMISSION_TEST_RESULTS.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(not r.wasSuccessful())
