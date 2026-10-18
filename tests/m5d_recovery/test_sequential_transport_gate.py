"""No large graph launch: closed admission, tiny replay metrics and stage contracts."""
import hashlib
import json
import resource
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from experiments.sequential_transport_gate_v1 import run as gate


class GateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_default_closed(self):
        with self.assertRaisesRegex(ValueError, 'not launchable'):
            gate.load_manifest(gate.TEMPLATE, gate.file_hash(gate.TEMPLATE))

    def test_frozen_policy_and_budget_tampering_rejected(self):
        for field, value in [('Hmax', 38), ('attempts', 2), ('holdout', True),
                             ('policy', 'sequential_exact'), ('limits', {})]:
            m = json.loads(gate.TEMPLATE.read_bytes())
            m.update(launchable=True); m[field] = value
            path = self.root/(field+'.json'); path.write_bytes(gate.canonical(m))
            with self.assertRaisesRegex(ValueError, 'Frozen gate policy differs'):
                gate.load_manifest(path, gate.file_hash(path))

    def test_unknown_construction_payload_stops_without_replay(self):
        result, calls = self.execute(['SUCCESS'], construction_status='unknown')
        self.assertEqual(result['status'], 'UNKNOWN')
        self.assertEqual(len(calls), 1)
        self.assertEqual([s['status'] for s in result['stages']], ['UNKNOWN','BLOCKED','BLOCKED'])

    def test_large_compact_envelope_and_corruption(self):
        folder = self.root/'worker'; artifacts = folder/'artifacts'; artifacts.mkdir(parents=True)
        data = dict(status='first_feasible', evidence='x'*100000)
        gate._atomic(artifacts/'construction.json', data)
        env = gate.envelope(artifacts, 'construct')
        self.assertLess(len(gate.canonical(env)), 4096)
        receipt = dict(worker_receipt=dict(result=env))
        self.assertEqual(gate.admit(folder, receipt, 'construct'), data)
        (artifacts/'construction.json').write_text('{}')
        with self.assertRaises(ValueError): gate.admit(folder, receipt, 'construct')

    def execute(self, statuses, *, construction_status="first_feasible"):
        m = json.loads(gate.TEMPLATE.read_bytes()); m['repo'] = str(self.root)
        calls = []
        def launch(command, **kwargs):
            op = command[command.index('--worker')+1]; calls.append((command, kwargs))
            out = kwargs['output_dir']/'artifacts'; out.mkdir(parents=True)
            name = 'construction.json' if op == 'construct' else 'result.json'
            gate._atomic(out/name, dict(status=construction_status if op == 'construct' else 'fresh_feasible', metrics=dict(J='1')))
            return dict(status=statuses[len(calls)-1], worker_receipt=dict(result=gate.envelope(out,op)))
        with patch.object(gate,'load_manifest',return_value=m),patch.object(gate,'run',side_effect=launch), \
             patch('os.sched_getaffinity',return_value={0}),patch('os.sched_setaffinity'), \
             patch('resource.getrlimit',return_value=(-1,-1)),patch('resource.setrlimit') as limits,patch('signal.signal'):
            result = gate.run_gate('manifest','f'*64,self.root/('run'+str(len(list(self.root.iterdir())))),0)
        self.assertEqual(limits.call_args.args[1][1],resource.RLIM_INFINITY)
        return result, calls

    def test_stage_order_whole_budgets_no_extra_seed_worker(self):
        result,calls = self.execute(['SUCCESS']*3)
        self.assertEqual(result['status'],'COMPLETED')
        self.assertEqual([c[0][c[0].index('--worker')+1] for c in calls], list(gate.OPERATIONS))
        self.assertEqual([c[1]['limits'].wall_seconds for c in calls],[240,120,120])
        self.assertEqual([c[1]['limits'].cpu_seconds for c in calls],[240,120,120])
        self.assertNotIn('--construction',calls[0][0])
        self.assertEqual(set(result['comparison']),set(gate.OPERATIONS[1:]))

    def test_failure_unknown_timeout_stop_no_retry_keep_blocked(self):
        for stage in range(3):
            for failure in ('FAILED','UNKNOWN','TIMEOUT'):
                result,calls = self.execute(['SUCCESS']*stage+[failure])
                self.assertEqual(len(calls),stage+1)
                self.assertEqual(result['status'],failure)
                self.assertEqual(len(result['stages']),3)
                self.assertTrue(all(s['status']=='BLOCKED' for s in result['stages'][stage+1:]))

    def test_tiny_physical_metrics_are_replay_fields(self):
        import sys
        sys.path.insert(0,str(Path(__file__).parent))
        from test_first_sequential_feasible import FirstSequentialFeasibleTests
        from timecut5.sparse_seed import replay_sparse_seed
        from fractions import Fraction as R
        fixture = FirstSequentialFeasibleTests(); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        q,c = fixture.fixture()
        sequential = replay_sparse_seed(q,c,(('s','CS'),),(R(1,3),),sequential_no_overlap=True,include_events=True)
        q2,c2 = fixture.fixture('fresh')
        joint = replay_sparse_seed(q2,c2,(('s','CS'),),(R(1,3),),include_events=True)
        a,b = gate.metrics(sequential),gate.metrics(joint)
        self.assertEqual(a['J'],sequential['lex_key'][0])
        self.assertEqual(a['elapsed_s'],a['J']-R(q['lambda_stop_s']))
        self.assertEqual(a['overlap_s'],0)
        self.assertGreater(b['overlap_s'],0)
        self.assertEqual(a['distance_m'],b['distance_m'])
        self.assertEqual(a['service_events'][0]['window_margin_s'],R(q['schedule']['b'])-a['service_events'][0]['service_start'])


if __name__ == '__main__': unittest.main()
