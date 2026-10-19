import unittest
from unittest.mock import patch
from experiments.m6h_manifest_v1 import recovery_protocol as r
from experiments.m6h_manifest_v1.contract import plan

class RecoveryProtocolTest(unittest.TestCase):
    def test_portable_fixed_design(self):
        p=r.protocol()
        self.assertEqual(p['design'],plan(6))
        self.assertFalse(p['strict_independent_holdout_claim'])
        self.assertEqual(p['cpu_limit_seconds'],144000)
        self.assertEqual(p['absolute_deadline_utc'],'2026-10-20T10:19:43.011913Z')
        self.assertEqual(p['budget_history']['historical_numerical_slots'],0)
        self.assertEqual(len(r.validate_protocol(p)),64)
        p['cpu_limit_seconds']+=1
        with self.assertRaises(ValueError):r.validate_protocol(p)
    def test_no_reset_or_double_count(self):
        with patch.object(r,'ContinuationBudget') as b:
            r.make_continuation_budget(transition_utc='2026-10-19T10:06:00Z')
        self.assertEqual(b.call_args.kwargs['carried_cpu_seconds'],70893+9*60)
        self.assertEqual(b.call_args.kwargs['deadline_utc'],r.DEADLINE)
    def test_held_before_argument_access(self):
        class Exploding:
            def __fspath__(self):raise AssertionError('input accessed')
        with patch('experiments.m6h_manifest_v1.recovery_runtime.ROOT_RELEASE',None):
            with self.assertRaises(PermissionError):r.launch_recovery(Exploding())

if __name__=='__main__':unittest.main()

class RecoveryReleaseGuards(unittest.TestCase):
    def test_root_hold_precedes_io_with_env(self):
        from experiments.m6h_manifest_v1 import recovery_runtime as rt
        from experiments.m6h_manifest_v1 import recovery_runner as rr
        from experiments.m6h_manifest_v1 import launcher
        from pathlib import Path
        with patch.object(rt,'ROOT_RELEASE',None), patch.dict('os.environ',{rt.ENV:'{"path":"/missing","sha256":"x"}'}):
            with patch.object(Path,'read_bytes',side_effect=AssertionError('external access')):
                for call in (rt.require_active,lambda:rr.supervise('/missing',configuration={}),
                             lambda:rr.worker('/missing','x'),lambda:launcher.launch_real(),
                             lambda:launcher.supervise_real_round('/missing',interpreter=None,osmium=None,freeze=None)):
                    with self.assertRaises(PermissionError):call()
    def test_registry_and_preprocessing_are_pinned(self):
        from experiments.m6h_manifest_v1 import recovery_runtime as rt
        if rt.ROOT_RELEASE is None:
            self.assertIsNone(rt.ROOT_REGISTRY_ADMISSION)
            self.assertIsNone(rt.ROOT_PREPROCESSING_SHA256)
            self.assertIsNone(rt.ROOT_REGISTRY_BYTES_SHA256)
        else:
            self.assertEqual(rt.ROOT_RELEASE,'reviewed_disclosed_recovery_v1')
            self.assertIsInstance(rt.ROOT_REGISTRY_ADMISSION,dict)
            self.assertEqual(len(rt.ROOT_PREPROCESSING_SHA256),64)
            self.assertEqual(len(rt.ROOT_REGISTRY_BYTES_SHA256),64)

class RecoveryRegistryMemoryContract(unittest.TestCase):
    def test_one_shot_recovery_returns_only_small_summary(self):
        import json, tempfile, hashlib
        from pathlib import Path
        from experiments.m6h_selection_v1 import rules
        from experiments.shandong_preprocessing_v1.registry_worker import validate
        endpoint=dict(site_id='tiny',access_node=1,lat=30,lon=120)
        registry=dict(schema=rules.RECOVERY_SCHEMA,strict_independent_holdout_claim=False,
            coverage=dict(status='incomplete_recovery',known_missing_artifacts=[dict(gap_id='lost',description='lost receipt')]),
            sources=[dict(source_id='tiny',sha256='a'*64)],records=[dict(source_id='tiny',reason='synthetic',
            graph_identity=dict(nodes_sha256='b'*64,edges_sha256='c'*64),origin=endpoint,destination=endpoint)])
        admission=dict(schema=rules.RECOVERY_SCHEMA,registry_sha256=rules.digest(registry),
            gap_list_sha256=rules.digest(registry['coverage']['known_missing_artifacts']),
            purpose='new_map_correctness_and_performance_validation',strict_independent_holdout_claim=False)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'registry.json';path.write_text(json.dumps(registry,indent=2))
            byte_hash=hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertNotEqual(byte_hash,admission['registry_sha256'])
            result=validate(path,byte_hash,admission['registry_sha256'],16384,recovery_admission=admission)
            self.assertEqual(result['exposure_pairs'],1)
            self.assertNotIn('records',result)
            with self.assertRaises(ValueError):validate(path,byte_hash,admission['registry_sha256'],16384)
            admission['gap_list_sha256']='f'*64
            with self.assertRaises(ValueError):validate(path,byte_hash,rules.digest(registry),16384,recovery_admission=admission)
