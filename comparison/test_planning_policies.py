from fractions import Fraction as F
import unittest
from planning_policies import action_mask,choose_activity,charging_activity_overlap


class PolicyContracts(unittest.TestCase):
    def test_masks_only_remove_legal_effects_and_never_invent_charge_or_service(self):
        caps={'a':['CS'],'b':['C','S','CS'],'c':['C']}
        self.assertEqual(action_mask(caps,'separated_no_overlap'),{('b','C'),('b','S'),('c','C')})
        self.assertEqual(action_mask(caps,'activity_first_fixed_site','a'),{('a','CS'),('b','C'),('c','C')})
        with self.assertRaises(ValueError):action_mask(caps,'activity_first_fixed_site','c')

    def test_ranking_uses_exact_time_ties_and_is_translation_invariant(self):
        caps={'b':['S'],'a':['CS'],'c':['C']};features={'a':('2','3'),'b':('2','3')}
        for shift in (-100,0,100):
            self.assertEqual(choose_activity(caps,features,start_time=shift,overhead=1,penalty=10,a=shift,b=10+shift,duration=2),'a')

    def test_unreachable_and_late_are_explicit_not_missing_feature_fallbacks(self):
        caps={'a':['S']}
        args=dict(start_time=0,overhead=1,penalty=10,a=0,b=2,duration=1)
        self.assertIsNone(choose_activity(caps,{'a':(None,1)},**args))
        self.assertIsNone(choose_activity(caps,{'a':(2,1)},**args))
        self.assertEqual(choose_activity(caps,{'a':(1,1)},**args),'a')
        with self.assertRaises(ValueError):choose_activity(caps,{},**args)

    def test_overlap_is_interval_intersection_not_always_minimum_durations(self):
        self.assertEqual(charging_activity_overlap(arrival=0,overhead=1,charge_duration=4,a=10,service_duration=3),0)
        self.assertEqual(charging_activity_overlap(arrival=0,overhead=1,charge_duration=4,a=3,service_duration=3),2)
        self.assertEqual(charging_activity_overlap(arrival=0,overhead=1,charge_duration=4,a=0,service_duration=3),3)
