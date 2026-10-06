"""Optional representation-mode parity against frozen bounded signatures."""
from copy import deepcopy
from dataclasses import replace
from fractions import Fraction as R
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from timecut5.bounded import solve_bounded,replay_witness
from timecut5.hierarchy import solve_hierarchical
from timecut5.coalesced_solver import solve_bounded_coalesced,solve_hierarchical_coalesced
from timecut5.coalesce import coalesce_pieces,VERSION
from timecut5.pwa import reduce_frontier

ROOT=Path(__file__).resolve().parents[1]
CASES=json.loads((ROOT/'results/milestone_5_reference/frozen_cases_v2.json').read_text())


def signature(value):
    s=value['status']
    if s=='attained_optimum':return s,R(value['J']),R(value['Q_total']),value['H'],tuple(map(tuple,value['site_action_tuple']))
    if s=='primary_unattained':return s,R(value['primary_infimum'])
    if s=='secondary_unattained':return s,R(value['J']),R(value['secondary_infimum'])
    return (s,)


class TestOptionalCoalescedSolver(unittest.TestCase):
    def test_eighteen_positive_frozen_cases_all_modes(self):
        for case in CASES:
            for baseline,coalesced in ((solve_bounded,solve_bounded_coalesced),(solve_hierarchical,solve_hierarchical_coalesced)):
                for dominance in (False,True):
                    with self.subTest(case=case['case_id'],solver=coalesced.__name__,dominance=dominance):
                        old=baseline(case,dominance=dominance);new=coalesced(case,dominance=dominance)
                        self.assertEqual(signature(old.canonical()['result']),signature(new.canonical()['result']))
                        self.assertEqual(new.canonical()['representation_version'],VERSION)
                        actual=new.inner.bounded if hasattr(new.inner,'bounded') else new.inner
                        if actual.result.witness is not None:self.assertEqual(replay_witness(case,actual.result.witness),actual.result.key)
                        self.assertLessEqual(new.statistics.output_pieces,new.statistics.input_pieces)

    def test_optional_reducer_hook_is_used(self):
        case=next(c for c in CASES if c['sites'])
        for solver in (solve_bounded_coalesced,solve_hierarchical_coalesced):
            with patch('timecut5.coalesced_solver.reduce_frontier',wraps=reduce_frontier) as observed:
                solver(case,dominance=True)
                self.assertTrue(observed.called)

    def test_mode_rejects_known_singleton_before_each_processing_entry(self):
        from timecut5.coalesced_solver import _SyntheticProblem
        problem=_SyntheticProblem(CASES[0]);piece=problem.initial_piece()
        object.__setattr__(piece,'_family',object())
        site=next(iter(problem.sites));effect=problem.sites[site][0]
        operations=(lambda:problem.compact((piece,)),lambda:problem.advance((piece,),site,effect),
                    lambda:problem.finish((piece,)),lambda:problem.reduce((piece,)))
        for operation in operations:
            with patch('timecut5.coalesced_solver.coalesce_pieces',side_effect=AssertionError('Guard was too late')):
                with self.assertRaisesRegex(ValueError,'before processing'):operation()
        self.assertEqual(problem.statistics().calls,0)

    def test_public_solver_rejects_a_known_family_initial_piece(self):
        from timecut5.coalesced_solver import _SyntheticProblem
        original=_SyntheticProblem.initial_piece
        def known(problem):
            piece=original(problem);object.__setattr__(piece,'_family',object());return piece
        with patch.object(_SyntheticProblem,'initial_piece',known):
            for solve in (solve_bounded_coalesced,solve_hierarchical_coalesced):
                with self.assertRaisesRegex(ValueError,'before processing'):solve(CASES[0])

    def test_known_proof_family_fails_closed_instead_of_inheriting_first_id(self):
        from test_time_cut_coalescing import seed
        from timecut5.probe import Interval
        first=seed(Interval(0,1));second=seed(Interval(1,2))
        object.__setattr__(first,'_family',object())
        with self.assertRaisesRegex(ValueError,'fresh certified guarded-union'):
            coalesce_pieces((first,second))
        self.assertIs(coalesce_pieces((first,))[0],first)


if __name__=='__main__':unittest.main()
