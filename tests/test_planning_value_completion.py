"""Mocked only-unrun execution, history integrity and report-read barriers."""
import copy
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import run_planning_value_completion as completion
import report_planning_value_completion as report

stage=completion.stage


class Completion(unittest.TestCase):
    def setUp(self):
        self.spec,self.definition,_=completion.recipe(ROOT/'configs/planning_value_completion.json')

    def prepared(self,out,spec=None):
        stage.pilot.atomic(out/'preparation.json',dict(spec=spec or self.spec,
            definition=self.definition,source={},configs={},inputs={},input_stat={}))

    def execute(self,out,worker,spec=None):
        with patch.object(stage.common,'source_identity',return_value={}),\
             patch.object(stage.time,'process_time',return_value=0),\
             patch.object(stage,'run_worker',side_effect=worker) as launch:
            stage.execute(SimpleNamespace(output_root=str(out),config='mock'),
                recipe_loader=lambda _:(spec or self.spec,self.definition,{}))
            return launch.call_count

    @staticmethod
    def worker(out,prepared,slot,total,guard):
        (out/'attempts'/stage.row_id(slot)).mkdir(parents=True)
        return dict(status='time_limit',mathematical_status='unknown',worker_cpu_s=2,supervisor_cpu_s=2)

    def test_only_two_fresh_slots_no_historical_replay_and_terminal_guard(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);self.prepared(out)
            self.assertEqual(self.execute(out,self.worker),2)
            rows=stage.load(out/'results.json')
            self.assertEqual((rows['query_denominator'],rows['policy_row_denominator']),(1,2))
            self.assertEqual([stage.row_id(r) for r in rows['rows']],
                             [stage.row_id(r) for r in self.definition['rows']])
            self.assertEqual(stage.load(out/'status.json')['worker_cpu_charged_s'],6)
            with self.assertRaisesRegex(RuntimeError,'inspect instead'):
                self.execute(out,lambda *_:self.fail('duplicate solve'))

    def test_pair_admission_includes_controller_cleanup_and_global_cap(self):
        self.assertTrue(stage.admission(self.spec,120))
        self.assertFalse(stage.admission(self.spec,120.001))
        constrained={**self.spec,'original_cap_cpu_s':self.spec['carried_cpu_s']+120+1000}
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);self.prepared(out,constrained)
            self.assertEqual(self.execute(out,lambda *_:self.fail('unreserved pair'),constrained),0)
            self.assertEqual([r['status'] for r in stage.load(out/'results.json')['rows']],
                             ['budget_unrun','budget_unrun'])
            self.assertEqual(stage.load(out/'status.json')['state'],'budget_stopped')

    def test_worker_failure_is_charged_and_suffix_preserved(self):
        def failing(out,prepared,slot,total,guard):
            (out/'attempts'/stage.row_id(slot)).mkdir(parents=True)
            return dict(status='worker_error',mathematical_status='unknown',worker_cpu_s=3,supervisor_cpu_s=3)
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);self.prepared(out)
            with self.assertRaisesRegex(RuntimeError,'unexpected worker outcome'):
                self.execute(out,failing)
            self.assertEqual(stage.load(out/'status.json')['worker_cpu_charged_s'],4)
            self.assertEqual([r['status'] for r in stage.load(out/'results.json')['rows']],
                             ['worker_error','not_run'])

    def test_predecessor_requires_unstarted_suffix_and_preserves_old_charge(self):
        _,full,_=stage.recipe(ROOT/'configs/planning_value_dev_gate.json')
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);rows=copy.deepcopy(full['rows'])
            for row in rows[:6]:
                row.update(status='time_limit',mathematical_status='unknown',worker_cpu_s=1)
                (out/'attempts'/stage.row_id(row)).mkdir(parents=True)
                stage.pilot.atomic(out/'attempts'/stage.row_id(row)/'final.json',row)
            for row in rows[-2:]:row['status']='budget_unrun'
            stage.pilot.atomic(out/'results.json',dict(rows=rows))
            stage.pilot.atomic(out/'status.json',dict(state='budget_stopped',controller_pid=999999))
            stage.pilot.atomic(out/'preparation.json',dict(definition=full,source={'commit':'historical'}))
            spec={**self.spec,'predecessor_sha256':{n:stage.digest(out/n)
                  for n in ('preparation.json','results.json','status.json')}}
            with patch.object(stage.common,'active_pid',return_value=False):
                _,prior=completion.predecessor(out,spec)
                self.assertTrue(prior['prior_setup_cost_already_inside_carried_charge'])
                (out/'attempts'/stage.row_id(rows[-2])).mkdir()
                with self.assertRaisesRegex(ValueError,'may already have started'):
                    completion.predecessor(out,spec)

    def test_six_historical_rows_are_not_mutated_or_replaced(self):
        _,full,_=stage.recipe(ROOT/'configs/planning_value_dev_gate.json')
        previous=copy.deepcopy(full['rows'])
        for row in previous[:6]:row.update(status='time_limit',payload=['preserve'])
        for row in previous[-2:]:row['status']='budget_unrun'
        before=copy.deepcopy(previous)
        source={'commit':'old'}
        box=dict(rows=previous,numerical_source=source,query_denominator=4,policy_row_denominator=8)
        original=dict(definition=full,source=source)
        report.validate_previous(box,original,before)
        previous[0]['witness']={'substituted':True}
        with self.assertRaisesRegex(ValueError,'differs from raw'):
            report.validate_previous(box,original,before)
        previous[0].pop('witness')
        fresh=[{**r,'status':'time_limit'} for r in previous[-2:]]
        combined=report.combine_rows(previous,fresh,{'commit':'old'})
        self.assertEqual(previous,before)
        self.assertEqual([{k:v for k,v in r.items() if k!='numerical_source'} for r in combined[:6]],previous[:6])
        self.assertEqual(len(combined),8)
        fresh[0]['policy']='different'
        with self.assertRaises(ValueError):report.combine_rows(previous,fresh,{})

    def test_running_report_cannot_read_controls(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);stage.pilot.atomic(out/'status.json',dict(state='running'))
            with patch.object(stage,'digest',side_effect=AssertionError('control read')):
                with self.assertRaisesRegex(RuntimeError,'before terminal'):
                    report.report(out,'unused',out/'report')

    def test_missing_terminal_receipt_blocks_control_read_even_if_status_complete(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)
            stage.pilot.atomic(out/'status.json',dict(state='complete'))
            prepared=dict(spec={},definition=self.definition,predecessor={'root':'unused'})
            stage.pilot.atomic(out/'preparation.json',prepared)
            rows=[{**r,'status':'time_limit','mathematical_status':'unknown'} for r in self.definition['rows']]
            stage.pilot.atomic(out/'results.json',dict(rows=rows))
            with patch.object(completion,'predecessor',return_value=({},prepared['predecessor'])),\
                 patch.object(stage,'digest',side_effect=AssertionError('control read')):
                with self.assertRaises(FileNotFoundError):report.report(out,'unused',out/'report')


if __name__=='__main__':unittest.main()
