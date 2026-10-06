"""Recorder invariants; independent semantic validation is a separate module."""
from dataclasses import replace
from fractions import Fraction as R
import json
from pathlib import Path
import sys
import unittest
from timecut5.bounded import Problem, solve_bounded
from timecut5.probe import Interval
from timecut5.pwa import lower_envelope
from timecut5.provenance import Recorder, restrict, signature

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments/time_cut_v2/family_faithfulness'))
from make_pilot import ancestral_case, build_ancestral


class TestFamilyRecorder(unittest.TestCase):
    def test_disabled_does_not_add_provenance(self):
        p=Problem(ancestral_case()).initial_piece()
        self.assertIsNone(p._family)

    def test_immutable_ancestry_and_physical_foreign_family_pilot(self):
        data=build_ancestral()
        a,b=(data['witnesses'][k][0] for k in ('A','B'))
        self.assertEqual(a['piece'],b['piece'])
        self.assertNotEqual(a['node_id'],b['node_id'])
        for row in (a,b):
            w=row['witness'];self.assertEqual((w['time'],w['energy'],w['rho']),('5','3','-1'))
        ea=a['witness']['events'][2]['departure_energy']
        eb=b['witness']['events'][2]['departure_energy']
        self.assertTrue(1<R(ea)<R(3,2));self.assertTrue(2<R(eb)<R(5,2))
        self.assertEqual(len(data['bundle']['nodes']),20)
        self.assertEqual(len(data['bundle']['batch_ids']),9)

    def test_raw_replace_cannot_inherit_stale_output_binding(self):
        with Recorder():
            p=Problem(ancestral_case()).initial_piece()
            bad=replace(p,intercept=p.intercept+1)
            with self.assertRaisesRegex(ValueError,'Stale family'):
                bad.at(R(2))

    def test_restriction_records_endpoint_flags(self):
        with Recorder() as recorder:
            problem=Problem(ancestral_case())
            p=problem.advance((problem.initial_piece(),),'c','C')[0]
            q=restrict(p,Interval(R(5,4),R(3,2),False,False))
            node=recorder.export((q,))['nodes'][q._family.node_id]
            self.assertEqual(node['params']['domain'],['5/4','3/2',False,False])
            self.assertEqual(node['parents'],[p._family.node_id])

    def test_equal_scalar_pieces_keep_identity_specific_dispatch(self):
        with Recorder() as recorder:
            problem=Problem(ancestral_case())
            p=problem.initial_piece()
            q=restrict(p,p.domain,'different identity but equal tuple')
            self.assertEqual(p,q)
            output=lower_envelope((q,p))
            node=recorder.export(output)['nodes'][output[0]._family.node_id]
            self.assertEqual(node['params']['chosen'],0)
            self.assertEqual(node['parents'][0],q._family.node_id)
            self.assertNotEqual(node['parents'][0],node['parents'][1])

    def test_cannot_enlarge_guard_or_cross_recording_context(self):
        with Recorder():
            p=Problem(ancestral_case()).initial_piece()
            with self.assertRaisesRegex(ValueError,'enlarge'):
                restrict(p,Interval(1,3))
        with Recorder():
            with self.assertRaisesRegex(ValueError,'different recording'):
                restrict(p,p.domain)

    def test_recording_does_not_change_solution(self):
        case=ancestral_case()
        expected=solve_bounded(case).canonical()
        with Recorder() as recorder:
            actual=solve_bounded(case).canonical()
            bundle=recorder.export()
        self.assertEqual(actual,expected)
        self.assertGreater(len(bundle['nodes']),20)
        self.assertTrue(any(b['kind']=='reduction' for b in bundle['batches']))

if __name__=='__main__':unittest.main()
