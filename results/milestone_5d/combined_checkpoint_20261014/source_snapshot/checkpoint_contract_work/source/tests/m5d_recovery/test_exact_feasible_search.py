"""Three tiny same-domain FLAT/HIER comparisons; no production data."""
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
from test_exact_feasible_incumbent import fixture
from timecut5 import deployable as d, exact_feasible_incumbent as f, bounded, hierarchy

HIER=f.canonical(dict(site_ids=['s'],regions=[dict(parent=-1,children=[1],members=[0]),
                                            dict(parent=0,children=[],members=[0])]))


def search_fixture(root,case):
    domain,w,kw=fixture(root)
    table=json.loads(domain.table_bytes);table['hierarchy_sha256']=f.sha(HIER)
    query=json.loads(domain.query_bytes);query['hierarchy_sha256']=f.sha(HIER)
    if case=='charge_required':query['initial_energy_kwh']=2
    if case=='scheduled_equality':
        table['sites'][0]['effects']=['S']
        query.update(schedule=dict(a=0,b=100,D=0),overhead_s=10,lambda_stop_s=0)
        w.update(sequence=[['s','S']],charges=[])
    data=f.canonical(table);query['leg_payload_sha256']=f.sha(data)
    q=f.canonical(query)
    binding=replace(domain.binding,query_sha256=f.sha(q),hierarchy_sha256=f.sha(HIER),
                    site_catalog_sha256=f.sha(f.canonical(table['sites'])))
    domain=d.QueryDomain(binding,q,domain.candidate_bytes,data,f.sha(data))
    w.update(domain={k:getattr(binding,k) for k in binding.__dataclass_fields__},table_sha256=f.sha(data))
    kw['expected_domain']=binding
    return domain,w,kw


class Tests(unittest.TestCase):
    results=[]
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
    def test_three_real_tiny_searches_match_completed_seed_default(self):
        for case in ['nonbest_charge','charge_required','scheduled_equality']:
            domain,w,kw=search_fixture(self.root,case)
            certificate=f.admit_exact_feasible_incumbent(domain,f.canonical(w),**kw)
            calls=[]
            real_flat,real_hier=bounded._solve_problem,hierarchy._solve_hierarchical_problem
            def flat(problem,**options):
                calls.append(('flat',problem.bound,options['verified_primary_upper']))
                return real_flat(problem,**options)
            def hier(problem,*args,**options):
                calls.append(('hier',problem.bound,options['verified_primary_upper']))
                return real_hier(problem,*args,**options)
            with patch.object(bounded,'_solve_problem',side_effect=flat), \
                 patch.object(hierarchy,'_solve_hierarchical_problem',side_effect=hier), \
                 patch.object(d,'construct_verified_seed',side_effect=AssertionError('completed seed called')), \
                 patch.object(d,'iter_constructive_seed_candidates',side_effect=AssertionError('heuristic called')):
                actual=f.solve_deployable_pair_with_feasible_incumbent(certificate,HIER,**kw)
            self.assertEqual(calls,[('flat',certificate.max_depth,certificate.seed.primary_j),
                                    ('hier',certificate.max_depth,certificate.seed.primary_j)])
            original=d.construct_verified_seed(domain,kw['approved_verifier_sha256'])
            expected=d.solve_deployable_pair(original,HIER,kw['approved_verifier_sha256'])
            self.assertEqual(actual.flat,expected.flat)
            self.assertEqual(actual.hier,expected.hier)
            self.assertEqual(actual.flat,actual.hier)
            self.assertEqual(actual.flat.status,d.SolveStatus.ATTAINED_OPTIMUM)
            self.assertGreater(actual.region_setup_index_entries,0)
            self.assertGreater(actual.shared_seed_cache_misses,0)
            self.assertEqual(actual.hier_online_internal_member_accesses,0)
            if case=='scheduled_equality':
                self.assertEqual(actual.flat.j,certificate.seed.primary_j)
                self.assertEqual(actual.flat.h,certificate.max_depth)
            else:self.assertLess(actual.flat.j,certificate.seed.primary_j)
            self.results.append(dict(case=case,initial_upper=str(certificate.seed.primary_j),
                certified_depth=certificate.max_depth,status=actual.flat.status.value,
                final_key=[str(actual.flat.j),str(actual.flat.q),actual.flat.h,actual.flat.pi],
                default_agrees=True,boundary_calls=[(mode,h,str(j)) for mode,h,j in calls]))

    def test_bad_hierarchy_source_domain_and_bound_fail_before_search(self):
        domain,w,kw=search_fixture(self.root,'nonbest_charge')
        c=f.admit_exact_feasible_incumbent(domain,f.canonical(w),**kw)
        with patch.object(bounded,'_solve_problem',side_effect=AssertionError('search entered')), \
             patch.object(hierarchy,'_solve_hierarchical_problem',side_effect=AssertionError('search entered')):
            with self.assertRaises(ValueError): f.solve_deployable_pair_with_feasible_incumbent(c,b'{}',**kw)
            with self.assertRaises(ValueError): f.solve_deployable_pair_with_feasible_incumbent(replace(c,max_depth=0),HIER,**kw)
            with self.assertRaises(ValueError): f.solve_deployable_pair_with_feasible_incumbent(c,HIER,**(kw|dict(expected_domain=replace(domain.binding,population_sha256='a'*64))))
            kw['actual_source_paths']['router.txt'].write_bytes(b'changed')
            with self.assertRaises(ValueError): f.solve_deployable_pair_with_feasible_incumbent(c,HIER,**kw)

    def test_shared_search_body_is_exactly_original(self):
        baseline=(ROOT/'fixtures/pinned_deployable.py').read_text()
        current=(ROOT.parents[1]/'src/timecut5/deployable.py').read_text()
        marker='    query, table = domain.open()\n'
        old=baseline[baseline.index(marker,baseline.index('def solve_deployable_pair(')):]
        new=current[current.index(marker,current.index('def _solve_deployable_pair_verified(')):]
        self.assertEqual(old,new)

if __name__=='__main__':
    resource.setrlimit(resource.RLIMIT_CPU,(60,60));started=time.process_time()
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    report=dict(tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),
        cpu_seconds=time.process_time()-started,real_od_runs=0,
        tiny_cases=Tests.results,exact_pair_comparisons=len(Tests.results))
    (ROOT/'EXACT_SEARCH_TEST_RESULTS.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(not result.wasSuccessful())
