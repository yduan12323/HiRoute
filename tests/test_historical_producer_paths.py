"""Historical command bytes stay bound while read paths use the producer root."""
import sys
import unittest
from pathlib import Path

from experiments.time_cut_v2.recorded_real import plan, window_receipts as receipts
from experiments.time_cut_v2.recorded_real import recovery_plan, window_recovery_receipts
from experiments.time_cut_v2.recorded_real.runtime import BATCH_REPLAY


class HistoricalProducerPaths(unittest.TestCase):
    def request(self, path):
        values = {key: 'results/retained/'+key+'.json' for key in receipts.COMMON_PATHS}
        values.update({key: 'a'*64 for key in receipts.COMMON_PINS})
        values['source_commit'] = 'b'*40
        values.update(source_policy='results/retained/policy.json', source_policy_sha='c'*64,
                      registry_output='results/retained/registry.json',
                      registration_return_output='results/retained/registration.json',
                      old_archive=path, deadline='1000.0', worker_cpus=[1,2,3,4,5])
        # A seed request uses old inputs, rather than window-only policy fields.
        values.pop('source_policy'); values.pop('source_policy_sha')
        values.pop('registry_output'); values.pop('registration_return_output')
        values['old_summary']='results/retained/summary.json'
        values['old_selection']='results/retained/selection.json'
        command=[sys.executable,'-B','-m',receipts.MODULE_PREFIX+'block_resume','--worker']
        for key,value in values.items():
            command.append('--'+key.replace('_','-'))
            command.extend(map(str,value)) if key=='worker_cpus' else command.append(value)
        context=plan.digest({k:str(v) for k,v in values.items() if k!='deadline'})
        return dict(command=command, deadline_monotonic=1000., worker_cpus=[1,2,3,4,5],
                    context=dict(plan_sha256=values['replay_plan_sha'],
                                 source_sha256=values['source_sha'], input_sha256=context,
                                 profile_name=BATCH_REPLAY.name))

    def test_relative_and_absolute_retained_paths_keep_raw_command_binding(self):
        root=Path('/producer/checkpoint')
        relative='results/retained/model-proofs.jsonl.gz'
        absolute=str(root/relative)
        for given in (relative,absolute):
            request=self.request(given)
            raw=receipts._command(request,'block_resume')
            resolved=receipts._command(request,'block_resume',producer_root=root)
            self.assertEqual(raw['old_archive'],given)
            self.assertEqual(resolved['old_archive'],absolute)
            self.assertEqual(resolved['historical_plan'],str(root/'results/retained/historical_plan.json'))
            self.assertEqual(request['command'][request['command'].index('--old-archive')+1],given)

    def test_wrong_root_traversal_and_source_fail_closed(self):
        root=Path('/producer/checkpoint')
        absolute=str(root/'results/retained/model-proofs.jsonl.gz')
        with self.assertRaises(ValueError):
            receipts.historical_path(absolute,Path('/other/checkpoint'))
        for path in ('../escape', 'results/../escape', '/producer/other/archive'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                receipts.historical_path(path,root)
        with self.assertRaises(ValueError):
            receipts._source('b'*40,'a'*64,'suffix_window',{'c'*40:'a'*64})

    def test_wrong_producer_origin_rejected(self):
        root=Path('/producer/checkpoint')
        module=receipts.MODULE_PREFIX+'suffix_window_recovery'
        origin=dict(schema='hiroute-reviewed-controller-origin-v1', checkout_root=str(root),
                    controller_module=module, controller_path=str(root/(module.replace('.','/')+'.py')),
                    python_executable=sys.executable, executable_realpath=str(Path(sys.executable).resolve()),
                    cwd=str(root))
        request=dict(command=[sys.executable])
        recovery_plan._origin(origin,request,module,producer_root=root)
        with self.assertRaises(ValueError):
            recovery_plan._origin(origin,request,module,producer_root=Path('/other/checkpoint'))
        with self.assertRaises(ValueError):
            window_recovery_receipts._origin(origin,request,producer_root=Path('/other/checkpoint'))
