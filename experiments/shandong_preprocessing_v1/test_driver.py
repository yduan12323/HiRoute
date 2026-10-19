import copy
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('held_driver', HERE/'driver.py')
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)

class HeldDriverTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((HERE/'config.json').read_text())

    def test_real_pipeline_gate_precedes_io(self):
        import sys
        sys.path.insert(0,str(HERE))
        import pipeline
        import phases
        with patch.object(Path, 'open', side_effect=AssertionError('unexpected file access')):
            with self.assertRaisesRegex(RuntimeError,'HELD'):
                pipeline.run_preprocessing('/never-created',budget=None,interpreter='/unused',osmium='/unused')
            with self.assertRaisesRegex(RuntimeError,'HELD'):
                phases.gate(False)
        with self.assertRaisesRegex(ValueError,'Budget'):
            pipeline.run_preprocessing('/never-created',budget=None,interpreter='/unused',osmium='/unused',fixture=True)

    def test_plan_is_deterministic_and_data_free(self):
        with patch.object(Path, 'open', side_effect=AssertionError('unexpected file access')):
            a = driver.plan(self.config)
            b = driver.plan(copy.deepcopy(self.config))
        self.assertEqual(a, b)
        self.assertFalse(a['execution_available'])
        self.assertFalse(a['source_accessed'])
        self.assertEqual(a['stages'][0]['stage'], 'source_freeze')
        self.assertEqual(a['stages'][-1]['stage'], 'terminal_receipt')

    def test_execute_unconditionally_held(self):
        for args in ((), ({'approved': True},)):
            with self.assertRaises(driver.HeldError):
                driver.execute(*args)

    def test_no_configuration_bypass(self):
        for key,value in [('status', 'APPROVED'), ('execution_enabled', True), ('execution_enabled', 0)]:
            altered = copy.deepcopy(self.config); altered[key] = value
            with self.assertRaises(driver.HeldError): driver.plan(altered)

    def test_source_and_projection_are_frozen_proposals(self):
        for section,key,value in [('source','url', 'latest'), ('source','expected_size_bytes',1),
                                  ('source','snapshot_timestamp','other'), ('geometry','projection','EPSG:3035')]:
            altered = copy.deepcopy(self.config); altered[section][key] = value
            with self.assertRaises(ValueError): driver.plan(altered)

    def test_resource_expansion_fails(self):
        for key in ('cpu_seconds','wall_seconds','sampled_tree_rss_bytes','per_process_as_bytes','threads'):
            altered = copy.deepcopy(self.config); altered['resources'][key] *= 2
            with self.assertRaises(ValueError): driver.plan(altered)

    def test_fake_hashes_cannot_enable_acquisition(self):
        altered = copy.deepcopy(self.config); altered['source']['sha256'] = '0'*64
        with self.assertRaises(driver.HeldError): driver.plan(altered)

    def test_approval_requirements_cannot_be_removed(self):
        altered = copy.deepcopy(self.config); altered['required_approvals'] = []
        with self.assertRaises(ValueError): driver.plan(altered)

if __name__ == '__main__': unittest.main()
