"""Mock-only immutable-leg solver wiring; never reads a real exported query."""
from copy import deepcopy
from dataclasses import replace
from fractions import Fraction as R
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

from timecut5.real_legs import ImmutableLegTable,restrict_frozen_tree
from timecut5.real_adapter import (RealProblem,original_region_view,solve_bounded_real,
    solve_hierarchical_real,evaluate_real_sequence,replay_real_witness)
from timecut5.hierarchy import region_bound
from timecut5.probe import Event,State,Witness

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/'results/milestone_5_real_leg_contract/mock_solver_cases.json'
CASES=json.loads(PATH.read_text())


def blob(v):return json.dumps(v,sort_keys=True,separators=(',',':')).encode()
def inputs(case):
    table=ImmutableLegTable.from_bytes(blob(case['table']),case['table_sha256'])
    tree=restrict_frozen_tree(blob(case['original_tree']),case['original_tree_sha256'],list(table.sites))
    return case['query'],table,tree
def normalized(e):
    e=dict(e)
    for k in ('J','Q_total','primary_infimum','secondary_infimum'):
        if k in e:e[k]=R(e[k])
    if 'site_action_tuple' in e:e['site_action_tuple']=tuple(tuple(x) for x in e['site_action_tuple'])
    return e


class TestRealSolverAdapter(unittest.TestCase):
    def test_frozen_mock_identity(self):
        manifest=json.loads(PATH.with_name('mock_solver_freeze.json').read_text())
        self.assertEqual(hashlib.sha256(PATH.read_bytes()).hexdigest(),manifest['sha256'])

    def test_expected_physical_results_both_solvers_and_reduction_modes(self):
        for case in CASES:
            query,table,tree=inputs(case)
            for solver in (solve_bounded_real,solve_hierarchical_real):
                for dominance in (False,True):
                    with self.subTest(case=case['case_id'],solver=solver.__name__,dominance=dominance):
                        result=solver(query,table,tree,dominance=dominance)
                        for k,v in normalized(case['independent_expected']).items():
                            self.assertEqual(result.canonical()['result'][k],v)
                        inner=result.inner.bounded if hasattr(result.inner,'bounded') else result.inner
                        if inner.result.witness is not None:
                            self.assertEqual(replay_real_witness(query,table,inner.result.witness),inner.result.key)
                            self.assertEqual(inner.result.witness.state.anchor,table.destination_anchor)

    def test_real_calls_never_construct_a_synthetic_graph(self):
        query,table,tree=inputs(CASES[0])
        with patch('timecut5.bounded.Problem.__init__',side_effect=AssertionError('graph route constructor called')):
            self.assertEqual(solve_bounded_real(query,table).canonical()['result']['J'],14)
            self.assertEqual(solve_hierarchical_real(query,table,tree).canonical()['result']['J'],14)

    def test_coattached_state_and_zero_leg_keep_distinct_sites(self):
        query,table,tree=inputs(CASES[0]);p=RealProblem(query,table)
        a=p.advance((p.initial_piece(),),'A','C')
        self.assertTrue(a)
        self.assertTrue(all(piece.state.anchor=='road:x' and piece.pi==(('A','C'),) for piece in a))
        result=evaluate_real_sequence(query,table,(('A','C'),('B','S')))
        witness=result.witness
        self.assertEqual(witness.pi,(('A','C'),('B','S')))
        zero=[e for e in witness.events if e.effect=='D' and e.arrival_time==e.departure_time]
        self.assertEqual(len(zero),1)
        self.assertEqual(zero[0].arrival_energy,zero[0].departure_energy)

    def test_nonmetric_onward_bound_stays_zero_with_external_incumbent(self):
        query,table,tree=inputs(CASES[1]);p=RealProblem(query,table)
        base=(p.initial_piece(),)
        root=original_region_view(table,tree)
        lower,_=region_bound(p,base,root,'C')
        self.assertEqual(lower,2)
        self.assertEqual(p.onward_time_lower_bound('road:x'),0)
        one_stop=p.finish(p.advance(base,'B','C'))
        incumbent=next(piece.at(R(1)).minimum() for piece in one_stop if piece.domain.contains(R(1)))
        self.assertEqual(replay_real_witness(query,table,incumbent)[0],13)
        result=solve_hierarchical_real(query,table,tree,incumbent=incumbent)
        self.assertEqual(result.canonical()['result']['J'],6)

    def test_original_tree_ids_and_empty_children_are_not_rebuilt(self):
        query,table,tree=inputs(CASES[2])
        root=original_region_view(table,tree)
        self.assertEqual(root.identifier,0)
        self.assertEqual(tuple(c.identifier for c in root.children),(1,2))
        self.assertEqual(root.children[0].members,())

    def test_rejects_conflicting_query_graph_and_provenance(self):
        query,table,tree=inputs(CASES[0])
        for key,value in (('origin','wrong'),('sites',{}),('edges',[]),('leg_payload_sha256','0'*64)):
            bad=dict(query);bad[key]=value
            with self.assertRaises(ValueError):solve_bounded_real(bad,table)

    def test_rejects_missing_site_or_wrong_original_tree(self):
        query,table,tree=inputs(CASES[0])
        for bad in (replace(tree,original_sha256='0'*64),replace(tree,selected_site_ids=('A',))):
            with self.assertRaises(ValueError):solve_hierarchical_real(query,table,bad)
        regions=list(tree.regions);regions[0]=replace(regions[0],site_ids=('A',))
        with self.assertRaises(ValueError):solve_hierarchical_real(query,table,replace(tree,regions=tuple(regions)))

    def test_incumbent_verification_survives_optimized_python(self):
        code = """
from test_real_solver_adapter import CASES,inputs
from timecut5.real_adapter import solve_hierarchical_real
from timecut5.probe import Event,State,Witness
query,table,tree=inputs(CASES[1])
forged=Witness(0,2,-2,(),State('road:z',0,0),(Event('initial','road:o',0,0,2,2),))
try:
    solve_hierarchical_real(query,table,tree,incumbent=forged)
except AssertionError:
    print('rejected')
else:
    raise RuntimeError('Forged incumbent accepted under Python -O')
"""
        environment=dict(os.environ,PYTHONPATH=os.pathsep.join((str(ROOT/'src'),str(ROOT/'tests'))))
        completed=subprocess.run([sys.executable,'-O','-c',code],env=environment,text=True,capture_output=True)
        self.assertEqual(completed.returncode,0,completed.stderr)
        self.assertEqual(completed.stdout.strip(),'rejected')

    def test_rejects_consecutive_drive_and_over_bound_real_witnesses(self):
        query,table,tree=inputs(CASES[0])
        witness=evaluate_real_sequence(query,table,(('A','C'),('B','S'))).witness
        with self.assertRaises(AssertionError):replay_real_witness(dict(query,H_ref=1),table,witness)
        forged=Witness(2,0,0,(),State('road:z',0,0),(
            Event('initial','road:o',0,0,2,2),Event('D','road:x',0,1,2,1),Event('D','road:z',1,2,1,0)))
        with self.assertRaises(AssertionError):solve_hierarchical_real(query,table,tree,incumbent=forged)


if __name__=='__main__':unittest.main()
