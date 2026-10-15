import ast
from dataclasses import replace
from fractions import Fraction as R
from types import SimpleNamespace
import json
from pathlib import Path
import resource
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'src'),str(ROOT)]
from fixture_source import fixture,Router
from timecut5 import sparse_feasible_execution as e, deployable, sparse_seed
from timecut5.feasible_incumbent import canonical,sha,verifier_sources
from timecut5.streaming_seed_diagnostic import StreamingSeedObserver
from timecut5.real_adapter import TableFreeRealProblem
from timecut5.road_provider import TableFreeRegionBoundProvider
from timecut5.hierarchy import build_regions,_solve_hierarchical_problem
from timecut5.bounded import _solve_problem
# Execute only the unmodified pinned completed-seed execution function, not
# launcher imports, graph loading, native compilation or the CLI.
source=(ROOT/'reference/m5d_main_row.py').read_text();tree=ast.parse(source)
function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='execute_exact_method')
original_globals=dict(TableFreeRealProblem=TableFreeRealProblem,_solve_problem=_solve_problem,
    _solve_hierarchical_problem=_solve_hierarchical_problem,replay_sparse_seed=sparse_seed.replay_sparse_seed)
exec(compile(ast.Module(body=[function],type_ignores=[]),str(ROOT/'reference/m5d_main_row.py'),'exec'),original_globals)
original_execute=original_globals['execute_exact_method']

class Tests(unittest.TestCase):
    results=[]
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.index=0
    def saved(self,case):
        q,c,paths=fixture(self.root/case,case)
        sequence=(('s','S'),) if case=='equality' else (('s','C'),)
        charges=() if case=='equality' else (R(3),)
        replay=sparse_seed.replay_sparse_seed(q,c,sequence,charges)
        self.index+=1
        observer=StreamingSeedObserver(q,c,output_dir=self.root/f'snapshot-{self.index}',provenance={'fixture':case})
        observer('incumbent',sequence=sequence,charges=charges,lex_key=replay['lex_key'],
            edge_witnesses=replay['edge_witnesses'],status='replayed_feasible_incumbent')
        observer.journal.close()
        return self.root/f'snapshot-{self.index}'/'snapshot.json'
    def inputs(self,case,path):
        q,c,paths=fixture(self.root/case,case)
        return dict(checkpoint_path=path,expected_checkpoint_sha256=sha(path.read_bytes()),
            query_bytes=canonical(q),catalog=c,approved_verifier_sha256=verifier_sources(),**paths)
    def admission(self,case):
        path=self.saved(case);inputs=self.inputs(case,path)
        policy=e.experimental_policy(inputs['query_bytes'],inputs['catalog'])
        a=e.admit_sparse_feasible(recovery_inputs=inputs,policy_bytes=policy,expected_policy_sha256=sha(policy))
        return a,path
    def solve(self,a,path,case,method,**changes):
        inputs=self.inputs(case,path);inputs.update(changes)
        return e.solve_sparse_with_feasible_incumbent(a,method=method,recovery_inputs=inputs,
            expected_policy_sha256=a.policy_sha256,router_factory=Router)

    def test_three_tiny_cases_match_actual_completed_seed_tablefree_path(self):
        for case in ['nonbest','charge_required','equality']:
            a,path=self.admission(case);rows=[];prewarms=[];providers=[]
            for method in ['flat','hier']:
                inputs=self.inputs(case,path);providers.append(inputs['catalog'].provider)
                self.assertEqual(len(providers[-1].legs),0)
                with patch.object(deployable,'iter_constructive_seed_candidates',side_effect=AssertionError('heuristic called')), \
                     patch.object(deployable,'construct_verified_seed',side_effect=AssertionError('full-table seed called')), \
                     patch.object(deployable.ImmutableLegTable,'from_bytes',side_effect=AssertionError('full table parsed')):
                    result=e.solve_sparse_with_feasible_incumbent(a,method=method,recovery_inputs=inputs,
                        expected_policy_sha256=a.policy_sha256,router_factory=Router)
                prewarms.append(result.initial_witness_cache_sha256)
                self.assertTrue(result.terminal_replayed)
                self.assertEqual(result.bounded.H_ref,a.incumbent.max_depth)
                self.assertLess(result.requested_pair_count,16) # unknown pairs not enumerated
                self.assertEqual(result.region_policy,e.POLICY)
                q,c,_=fixture(self.root/case,case)
                seed=sparse_seed.admit_sparse_seed(q,c)
                root=build_regions(c.sites)
                bound=TableFreeRegionBoundProvider(c.provider,c.sites,root,destination_anchor='D',landmark_anchor='A',
                    site_catalog_sha256=c.site_catalog_sha256,router_factory=Router)
                old,replayed=original_execute(q,c.sites,c.provider,c,bound,root,seed,method)
                self.assertEqual(result.bounded.result.status,old.result.status)
                self.assertEqual(result.bounded.result.key,old.result.key)
                if case=='equality':
                    self.assertEqual(result.bounded.result.key[0],a.incumbent.primary_upper)
                    self.assertEqual(result.bounded.result.key[2],a.incumbent.max_depth)
                else:self.assertLess(result.bounded.result.key[0],a.incumbent.primary_upper)
                rows.append((method,tuple(str(v) for v in result.bounded.result.key[:3])))
            self.assertIsNot(providers[0],providers[1]);self.assertIsNot(providers[0].router,providers[1].router)
            self.assertIsNot(providers[0].legs,providers[1].legs)
            self.assertEqual(prewarms[0],prewarms[1])
            self.results.append(dict(case=case,initial_upper=str(a.incumbent.primary_upper),depth=a.incumbent.max_depth,
                                     outcomes=rows,identical_isolated_witness_prewarm=True))

    def test_cached_provider_cannot_cross_method_boundary(self):
        a,path=self.admission('nonbest');inputs=self.inputs('nonbest',path)
        e.solve_sparse_with_feasible_incumbent(a,method='flat',recovery_inputs=inputs,
            expected_policy_sha256=a.policy_sha256,router_factory=Router)
        with self.assertRaises(ValueError):e.solve_sparse_with_feasible_incumbent(a,method='hier',recovery_inputs=inputs,
            expected_policy_sha256=a.policy_sha256,router_factory=Router)

    def test_unknown_pair_stays_unknown_and_manifest_labels_alternative_tree(self):
        path=self.saved('nonbest');inputs=self.inputs('nonbest',path);c=inputs['catalog']
        policy=e.experimental_policy(inputs['query_bytes'],c)
        a=e.admit_sparse_feasible(recovery_inputs=inputs,policy_bytes=policy,expected_policy_sha256=sha(policy))
        self.assertNotIn(('X','A'),c.provider.legs)
        self.assertEqual(len(c.provider.legs),2)
        self.assertFalse(json.loads(policy)['frozen_hierarchy_equivalence'])
        self.assertFalse(json.loads(policy)['source_hierarchy_file_verified'])
        self.assertEqual(json.loads(policy)['scope'],'synthetic_tablefree_fixture_only')

    def test_tampered_bounds_policy_query_sources_reject_before_engine(self):
        a,path=self.admission('nonbest')
        with patch.object(e,'_solve_problem',side_effect=AssertionError('entered search')):
            for bad in [replace(a,incumbent=replace(a.incumbent,max_depth=0)),
                        replace(a,incumbent=replace(a.incumbent,primary_upper=R(1)))]:
                with self.assertRaises(ValueError):self.solve(bad,path,'nonbest','flat')
            policy=dict(json.loads(a.policy_bytes),region_policy='original_frozen_hierarchy')
            bad=replace(a,policy_bytes=canonical(policy),policy_sha256=sha(canonical(policy)))
            with self.assertRaises(ValueError):self.solve(bad,path,'nonbest','flat')
            inputs=self.inputs('nonbest',path);q=json.loads(inputs['query_bytes']);q['reserve_kwh']=2
            inputs['query_bytes']=canonical(q)
            with self.assertRaises(ValueError):e.solve_sparse_with_feasible_incumbent(a,method='flat',recovery_inputs=inputs,
                expected_policy_sha256=a.policy_sha256,router_factory=Router)
            inputs=self.inputs('nonbest',path);inputs['edges_path'].write_bytes(b'changed')
            with self.assertRaises(ValueError):e.solve_sparse_with_feasible_incumbent(a,method='flat',recovery_inputs=inputs,
                expected_policy_sha256=a.policy_sha256,router_factory=Router)

    def test_corrupt_landmark_certificate_rejected(self):
        a,path=self.admission('nonbest');real=e.TableFreeRegionBoundProvider
        def broken(*args,**kw):
            bound=real(*args,**kw);bound.landmark_certificate=b'changed';return bound
        with patch.object(e,'TableFreeRegionBoundProvider',side_effect=broken), \
             patch.object(e,'_solve_problem',side_effect=AssertionError('entered search')):
            with self.assertRaises(ValueError):self.solve(a,path,'nonbest','flat')

    def test_runtime_scope_candidate_catalog_and_transitive_code_reject(self):
        a,path=self.admission('nonbest')
        for mutation in ['native','large','site','anchor','code']:
            inputs=self.inputs('nonbest',path);c=inputs['catalog']
            if mutation=='native':c.provider.router.provenance.pop('implementation_kind')
            if mutation=='large':c.provider.graph.node_count=17
            if mutation=='site':c.sites.pop('t')
            if mutation=='anchor':c.provider.anchor_nodes['X']=0
            if mutation=='code':inputs['approved_verifier_sha256']={}
            with patch.object(e,'_solve_problem',side_effect=AssertionError('entered search')):
                with self.assertRaises(ValueError):e.solve_sparse_with_feasible_incumbent(a,method='flat',recovery_inputs=inputs,
                    expected_policy_sha256=a.policy_sha256,router_factory=Router)

    def test_mutated_landmark_labels_fail_before_engine(self):
        a,path=self.admission('nonbest');real=e.TableFreeRegionBoundProvider
        def broken(*args,**kw):
            bound=real(*args,**kw);bound.landmarks[0].from_landmark['B']+=100;return bound
        with patch.object(e,'TableFreeRegionBoundProvider',side_effect=broken), \
             patch.object(e,'_solve_problem',side_effect=AssertionError('entered search')):
            with self.assertRaises(ValueError):self.solve(a,path,'nonbest','flat')

    def test_unknown_or_infeasible_terminal_cannot_be_accepted(self):
        a,path=self.admission('nonbest')
        for status in ['unknown','infeasible','attained_optimum']:
            terminal=SimpleNamespace(status=status,witness=None,key=None)
            with patch.object(e,'_solve_problem',return_value=SimpleNamespace(result=terminal)):
                with self.assertRaises(ValueError):self.solve(a,path,'nonbest','flat')

    def test_unattained_and_lexicographic_incumbent_contradictions_rejected(self):
        a,path=self.admission('nonbest');j=a.incumbent.primary_upper
        impossible=[SimpleNamespace(status='infimum_unattained',witness=None,key=None,
                        unattained_component='J',primary_infimum=j-R(1),secondary_infimum=R(2)),
                    SimpleNamespace(status='infimum_unattained',witness=None,key=None,
                        unattained_component='J',primary_infimum=j,secondary_infimum=None),
                    SimpleNamespace(status='infimum_unattained',witness=None,key=None,
                        unattained_component='Q',primary_infimum=j,secondary_infimum=R(3)),
                    SimpleNamespace(status='infimum_unattained',witness=None,key=None,
                        unattained_component='Q',primary_infimum=j,secondary_infimum=R(4)),
                    SimpleNamespace(status='attained_optimum',witness=object(),key=(j,R(4),1,(('s','C'),))),
                    SimpleNamespace(status='attained_optimum',witness=object(),key=(j,R(3),2,(('s','C'),('s','C')))),
                    SimpleNamespace(status='attained_optimum',witness=object(),key=(j,R(3),1,(('t','C'),)))]
        for terminal in impossible:
            with patch.object(e,'_solve_problem',return_value=SimpleNamespace(result=terminal)):
                with self.assertRaises(ValueError):self.solve(a,path,'nonbest','flat')

    def test_legitimate_partial_lexicographic_shapes_are_not_overrejected(self):
        a,path=self.admission('nonbest');j=a.incumbent.primary_upper
        candidates=[('J',j-R(1),None),('Q',j-R(1),R(4)),('Q',j,R(2))]
        for component,primary,secondary in candidates:
            terminal=SimpleNamespace(status='infimum_unattained',witness=None,key=None,
                unattained_component=component,primary_infimum=primary,secondary_infimum=secondary)
            with patch.object(e,'_solve_problem',return_value=SimpleNamespace(result=terminal)):
                result=self.solve(a,path,'nonbest','flat')
                self.assertFalse(result.terminal_replayed)
                self.assertIsNone(result.bounded.result.key)

    def test_changed_witness_and_snapshot_digest_rejected(self):
        a,path=self.admission('nonbest')
        snap=json.loads(path.read_bytes());snap['provisional_incumbent']['charges']=['4'];path.write_bytes(canonical(snap))
        with self.assertRaises(ValueError):self.solve(a,path,'nonbest','flat')

if __name__=='__main__':
    resource.setrlimit(resource.RLIMIT_CPU,(60,60));started=time.process_time()
    r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    report=dict(tests_run=r.testsRun,failures=len(r.failures),errors=len(r.errors),cpu_seconds=time.process_time()-started,
        actual_tiny_cases=Tests.results,real_od_runs=0,native_binary_runs=0,full_leg_tables_built=0)
    (ROOT/'TEST_RESULTS.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(not r.wasSuccessful())
