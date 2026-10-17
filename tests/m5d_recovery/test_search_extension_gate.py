"""Independent tiny-graph tests; never starts the OD02 road experiment."""
import json
from pathlib import Path
import tempfile
import unittest

from experiments.search_extensions_v1 import run as gate
from experiments.mechanism_recovery_v1 import run as base
from test_runner import native_test_domain


def extension_domain(path, arm):
    original = native_test_domain(path/'original')
    return gate.ExtensionDomain(arm=arm, manifest_binding=base.digest('tiny frozen manifest'),
        graph_factory=original.graph_factory, query=json.loads(original.query_bytes),
        sites=original.sites, tree=original.tree, source_hashes=original.source_hashes,
        cache=path/arm, compiler=original.compiler['compiler'])


class ExtensionGateTests(unittest.TestCase):
    def test_default_manifest_closed_and_fixed(self):
        path=Path(gate.__file__).with_name('manifest.json')
        m=json.loads(path.read_bytes())
        self.assertFalse(m['launchable'])
        self.assertEqual(m['order'],list(gate.ARMS))
        self.assertEqual(m['denominator']['total_stages'],7)
        self.assertEqual(m['limits']['search_seconds'],120)
        self.assertFalse(m['reverse_order_auto_launch'])
        with self.assertRaisesRegex(ValueError,'not launchable'):
            gate._manifest(path,base.file_hash(path))

    def test_policy_tampering_fails_before_source_or_inputs(self):
        source=json.loads(Path(gate.__file__).with_name('manifest.json').read_bytes())
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'manifest.json'
            for field, value in [('order',list(reversed(gate.ARMS))),('arms',{}),
                ('denominator',{}),('reverse_order_auto_launch',True),('limits',{})]:
                changed=dict(source,launchable=True);changed[field]=value
                path.write_bytes(base.canonical(changed))
                with self.assertRaisesRegex(ValueError,'policy differs'):
                    gate._manifest(path,base.file_hash(path))

    def test_fixed_runner_plan_no_auto_reverse(self):
        from unittest.mock import patch
        with patch.object(base,'_run_plan',return_value={'status':'COMPLETED'}) as plan:
            gate.run_gate('frozen.json','hash','owned',0)
        args=plan.call_args.kwargs
        self.assertEqual(args['fixed_cases'],(gate.CASE,))
        self.assertEqual(args['fixed_pairs'],[[gate.CASE,list(gate.ARMS)]])
        self.assertEqual(args['worker_module'],'experiments.search_extensions_v1.run')
        self.assertIs(args['manifest_loader'],gate._manifest)

    def test_exact_phase_rejects_setup_timeout(self):
        good=dict(status='TIMEOUT',reason='phase_timeout',phase_entered_monotonic=1,
            phase_budget=dict(seconds=120))
        gate.require_exact_phase(good)
        for changed in (dict(good,reason='wall_timeout'),
                        dict(good,phase_entered_monotonic=None),
                        dict(good,phase_budget=dict(seconds=60))):
            with self.assertRaises(ValueError):gate.require_exact_phase(changed)

    def test_seven_stage_forward_ledger_preserves_failure_denominator(self):
        import resource
        from unittest.mock import patch
        manifest=dict(schema=gate.SCHEMA,repo='.',source=dict(closure_sha256='0'*64))
        replies=[dict(status='SUCCESS'),dict(status='TIMEOUT'),dict(status='SUCCESS'),
                 dict(status='FAILED')]
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(gate,'_manifest',return_value=manifest), \
                 patch.object(base,'file_hash',return_value='a'*64), \
                 patch.object(base,'load_worker_result',return_value=dict(status='timeout_feasible_only')), \
                 patch('experiments.mechanism_recovery_v1.supervisor.run',side_effect=replies) as launch, \
                 patch('os.sched_getaffinity',return_value={0}),patch('os.sched_setaffinity'), \
                 patch('resource.getrlimit',return_value=(resource.RLIM_INFINITY,resource.RLIM_INFINITY)), \
                 patch('resource.setrlimit'),patch('signal.signal'):
                ledger=gate.run_gate('frozen','b'*64,Path(temp)/'gate',0)
        self.assertEqual(ledger['denominator'],7)
        self.assertEqual(ledger['schema'],gate.SCHEMA)
        self.assertEqual(ledger['status'],'FAILED_SEARCH')
        self.assertEqual([a['strategy'] for a in ledger['arms']],list(gate.ARMS))
        self.assertEqual(ledger['arms'][-1]['status'],'BLOCKED')
        self.assertEqual(launch.call_count,4)
        search_calls=[c for c in launch.call_args_list if 'phase_budget' in c.kwargs]
        self.assertEqual([c.kwargs['phase_budget'].seconds for c in search_calls],[120,120])

    def test_unknown_at_every_stage_keeps_seven_rows_and_stops(self):
        import resource
        from unittest.mock import patch
        manifest=dict(schema=gate.SCHEMA,repo='.',source=dict(closure_sha256='0'*64))
        for failed_at in range(7):
            with self.subTest(stage=failed_at),tempfile.TemporaryDirectory() as temp:
                replies=[dict(status='SUCCESS') for _ in range(failed_at)]+[dict(status='UNKNOWN')]
                with patch.object(gate,'_manifest',return_value=manifest), \
                     patch.object(base,'file_hash',return_value='a'*64), \
                     patch.object(base,'load_worker_result',return_value=dict(status='timeout_feasible_only')), \
                     patch('experiments.mechanism_recovery_v1.supervisor.run',side_effect=replies) as launch, \
                     patch('os.sched_getaffinity',return_value={0}),patch('os.sched_setaffinity'), \
                     patch('resource.getrlimit',return_value=(resource.RLIM_INFINITY,resource.RLIM_INFINITY)), \
                     patch('resource.setrlimit'),patch('signal.signal'):
                    ledger=gate.run_gate('frozen','b'*64,Path(temp)/'gate',0)
                self.assertEqual(ledger['denominator'],7)
                self.assertEqual(len(ledger['stages']),7)
                self.assertEqual(ledger['status'],'UNKNOWN')
                self.assertEqual(launch.call_count,failed_at+1)
                self.assertEqual(ledger['stages'][failed_at]['status'],'UNKNOWN')

    def test_three_arms_fresh_replay_and_cross_arm_rejected(self):
        from timecut5.bounded import _solve_problem
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)
            baseline=extension_domain(path,'baseline')
            with baseline.context('verification') as context:
                witness=_solve_problem(baseline.problem(context), True).result.witness
            seed=baseline.freeze_seed(witness)
            keys=[];bindings=[]
            for arm in gate.ARMS:
                domain=baseline if arm=='baseline' else extension_domain(path,arm)
                self.assertEqual(domain.freeze_seed(witness),seed)
                output=path/('result-'+arm)
                from unittest.mock import patch
                from timecut5.terminal_energy import activate
                with patch('timecut5.terminal_energy.activate',wraps=activate) as activation:
                    result=domain.run_arm(arm,seed,output,search_seconds=2)
                self.assertEqual(activation.call_count,1)
                replay=domain.recover_durable(seed,output/'incumbent.json')
                self.assertEqual(result['accepted_key'],replay['accepted_key'])
                keys.append(replay['accepted_key']);bindings.append(domain.durable_binding(seed))
                metrics=json.loads((output/'metrics.json').read_bytes())
                self.assertEqual(metrics['configuration'],gate.CONFIGS[arm])
                self.assertTrue(metrics['counters_complete'])
                self.assertIsInstance(metrics['search_counters']['attempted_extensions'],int)
                self.assertIn('terminal_piece_count',metrics['search_counters'])
                self.assertEqual(metrics['counter_semantics']['source_cache_bytes'],'instantaneous_gauge_at_snapshot')
                self.assertIn('route_wall_ns',metrics['route'])
                if arm=='coalescing_only':self.assertGreater(metrics['coalescing']['calls'],0)
                with self.assertRaises(ValueError):
                    domain.run_arm('indexed',seed,path/'invalid')
            self.assertEqual(keys,[keys[0]]*3)
            self.assertEqual(len({base.digest(b) for b in bindings}),3)
            with self.assertRaises(ValueError):
                baseline.recover_durable(seed,path/'result-onward_only/incumbent.json')
            baseline.extension_config['onward_alt']=True
            with self.assertRaisesRegex(ValueError,'policy changed'):
                baseline.check()


if __name__ == '__main__':unittest.main()
