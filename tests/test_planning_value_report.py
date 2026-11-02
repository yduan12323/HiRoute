"""Synthetic report semantics; never access a historical joint result file."""
from fractions import Fraction as F
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import report_planning_value_dev as report


def row(status='time_limit',value='9',policy=True):
    witness=dict(physical_verified=True,elapsed_time_s='5',driving_time_s='2',
                 total_distance_m='3',positive_charge_count=1)
    if policy:witness['original_joint_model_verified']=True
    result=dict(status=status,feasible_key=[value,'1',1,[['c','CS']]],witness=witness)
    if status=='attained_optimum':result['key']=result['feasible_key']
    return result


class PlanningValueReport(unittest.TestCase):
    def test_unknown_joint_is_only_observed_feasible_reference(self):
        comparison=report.compare(row(),row(value='10',policy=False))
        self.assertEqual(comparison['delta_J_s'],F(-1))
        self.assertEqual(comparison['comparison_type'],'observed_feasible_plans_only_UNKNOWN_joint')
        self.assertIsNone(comparison['delta_charging_duration_s'])

    def test_full_key_counterexample_to_attained_joint_is_not_a_benefit(self):
        actual=row(value='10')
        joint=row(status='attained_optimum',value='10',policy=False)
        joint['key']=['10','2',1,[['c','CS']]]
        joint['feasible_key']=joint['key']
        self.assertEqual(report.compare(actual,joint)['comparison_type'],'verification_error')

    def test_policy_unknown_remains_unknown_against_attained_reference(self):
        comparison=report.compare(row(value='11'),row(status='attained_optimum',value='10',policy=False))
        self.assertEqual(comparison['delta_J_s'],1)
        self.assertEqual(comparison['policy_mathematical_status'],'time_limit')
        self.assertEqual(comparison['comparison_type'],'feasible_plan_gap_to_attained_joint_optimum')

    def test_no_actual_plan_never_substitutes_infimum_or_zero(self):
        actual=dict(status='primary_unattained',primary_infimum='1')
        comparison=report.compare(actual,row(value='10',policy=False))
        self.assertNotIn('delta_J_s',comparison)
        self.assertEqual(comparison['comparison_type'],'no_pair_of_verified_feasible_values')
        self.assertEqual(report.policy_status(dict(status='time_limit')),'time_limit_no_feasible')

    def test_running_stage_cannot_read_controls(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            report.atomic(root/'status.json',dict(state='running'))
            report.atomic(root/'preparation.json',{})
            with patch.object(report.stage,'digest',side_effect=AssertionError('control read')):
                with self.assertRaisesRegex(RuntimeError,'before terminal'):
                    report.report(root,'unused',root/'report')


if __name__=='__main__':unittest.main()
