"""Portable tests, using only the public bundle and synthetic unit inputs."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest
from verify_public_bundle import verify, verify_records
ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('report_generator', ROOT/'generator/build_report.py')
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)

class PublicBundleTests(unittest.TestCase):
    def setUp(self):
        self.report = json.loads((ROOT/'public_report.json').read_text())
        self.audit = json.loads((ROOT/'public_receipt_audit.json').read_text())
    def test_pinned_bundle(self):
        self.assertEqual(verify(ROOT)['result'], 'PASS')
    def test_reject_duplicate_identity(self):
        self.report['rows'][2]['row_id'] = self.report['rows'][0]['row_id']
        with self.assertRaises(ValueError): verify_records(self.report,self.audit)
    def test_reject_unknown_reclassification(self):
        self.report['rows'][1]['status'] = 'time_limit'
        with self.assertRaises(ValueError): verify_records(self.report,self.audit)
    def test_reject_false_cleanup(self):
        self.report['rows'][1]['cleanup_verified'] = True
        with self.assertRaises(ValueError): verify_records(self.report,self.audit)
    def test_reject_false_acceptance(self):
        self.report['acceptance'] = 'passed'
        with self.assertRaises(ValueError): verify_records(self.report,self.audit)
    def test_reject_false_speedup(self):
        self.report['pairs'][0]['flat_over_hier_wall_ratio'] = 2
        with self.assertRaises(ValueError): verify_records(self.report,self.audit)
    def test_reject_missing_receipt(self):
        self.audit['rows'].pop()
        with self.assertRaises(ValueError): verify_records(self.report,self.audit)
    def test_reject_cpu_undercharge(self):
        self.audit['conservative_accounted_total_decimal_seconds'] = '0'
        with self.assertRaises(ValueError): verify_records(self.report,self.audit)
    def test_generator_unknown_keeps_measurement(self):
        ident = {'row_id':'synthetic', 'component':'full_universe', 'method':'flat', 'ordinal':0,'candidate_count':32}
        attempt = {'row_id':'synthetic','reserved_cpu_s':670,'charged_conservative_cpu_s':4,'controller_cpu_s':1,'state':'reserved','receipt':{'complete':False}}
        row = generator.normalize(ident, attempt, unknown=True, unknown_phase='seed_started')
        self.assertEqual(row['status'],'infrastructure_unknown')
        self.assertEqual(row['conservative_cpu_charge_seconds'],4)
        self.assertEqual(row['unknown_conservative_reservation_seconds'],670)
    def test_generator_exact_schema_rejects_invalid_attainment(self):
        valid = {'status':'attained_optimum','J':'1','Q':'0','H':0,'Pi':[],'J_attained':True,'Q_attained':True}
        generator.exact_schema(valid)
        for key,value in [('J','nan'),('H',True),('Q_attained',False),('Pi',None)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                generator.exact_schema(dict(valid,**{key:value}))
    def test_generator_timeouts_never_make_speedup(self):
        a = self.report['rows'][0]
        b = dict(a, method='hier')
        self.assertIsNone(generator.pairs([a,b])[0]['flat_over_hier_wall_ratio'])

if __name__ == '__main__': unittest.main()
