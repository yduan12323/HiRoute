import random
import unittest

from hiroute.data.charging_coverage import AttachmentIndex, charging_evidence, node_tie, sphere


class EvidenceTests(unittest.TestCase):
    def test_station_is_source_evidence_not_availability_or_curve(self):
        row = charging_evidence({'amenity': 'charging_station', 'socket:type2': '2'})
        self.assertTrue(row['modeled_C_eligible'])
        self.assertEqual(row['operational_availability'], 'unknown')
        self.assertEqual(row['connector_compatibility'], 'not_verified')
        self.assertEqual(row['charging_curve'], 'modeled_default_not_observed')
        self.assertEqual(row['observed']['socket:type2'], '2')

    def test_restrictions_lifecycle_and_individual_points_do_not_pad_C(self):
        for tags in ({'amenity': 'cafe'}, {'man_made': 'charge_point'},
                     {'charging': 'yes'}, {'disused:amenity': 'charging_station'},
                     {'amenity': 'charging_station', 'access': 'private'},
                     {'amenity': 'charging_station', 'motorcar': 'no'},
                     {'amenity': 'charging_station', 'capacity': '0'},
                     {'amenity': 'charging_station', 'charging_station:battery_swapping': 'only'},
                     {'amenity': 'charging_station', 'access:conditional': 'yes @ (Mo)'}):
            with self.subTest(tags=tags):
                self.assertFalse(charging_evidence(tags)['modeled_C_eligible'])


class IndexTests(unittest.TestCase):
    def test_prefix_matches_independent_legacy_sort_including_ties(self):
        rng = random.Random(241)
        ids = [str(i) for i in range(120)] + ['02', 'clip:b', 'clip:a']
        xy = [(115+rng.random()*8, 34+rng.random()*5) for _ in ids]
        xy[-7:] = [(118, 36)]*7
        index = AttachmentIndex(ids, xy)
        for point in [(118, 36), (115, 34)] + [(115+rng.random()*8,34+rng.random()*5) for _ in range(20)]:
            center = sphere(*point)
            expected = sorted(range(len(ids)), key=lambda i:(
                sum((a-b)**2 for a,b in zip(center,sphere(*xy[i]))),node_tie(ids[i]),i))
            for count in (1,4,7,200):
                self.assertEqual(index.prefix(*point,count),expected[:count])

    def test_refine_geodesic_after_prefix_and_keep_threshold_equality(self):
        class Geod:
            @staticmethod
            def inv(a,b,c,d):
                return 0,0,250.0
        index = AttachmentIndex(['10','2'],[(118,36),(118,36)])
        site = dict(lon=118,lat=36)
        self.assertEqual(index.attach(site,Geod(),250)['node_id'],'2')
        self.assertIsNone(index.attach(site,Geod(),249))

    def test_input_validation(self):
        for ids,xy in (([],[]),(['1','1'],[(0,0),(1,1)]),(['1'],[(181,0)])):
            with self.assertRaises(ValueError):AttachmentIndex(ids,xy)
        index=AttachmentIndex(['1'],[(0,0)])
        for count in (0,-1,True):
            with self.assertRaises(ValueError):index.prefix(0,0,count)
        with self.assertRaises(ValueError):index.prefix(float('nan'),0)


if __name__=='__main__':unittest.main()
