"""Pure workload/status checks: no road graph or numeric worker is launched."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import json
import signal
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('scale_pilot_control',ROOT/'tools/run_real_scale_pilot.py')
pilot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pilot)


def args(**updates):
    value = dict(diagnostic=False,ablation=False,no_bound=False,solve_limit_seconds=None,
                 domains=None,queries=None,scenarios=None,methods=None)
    value.update(updates)
    return SimpleNamespace(**value)


def config():
    return dict(resources=dict(pilot_method_query_wall_s=120,main_threshold_s=60),
        selection=dict(candidate_counts=[16,64],ods=[dict(query_id='SD01'),dict(query_id='SD02')],
                       scenarios=['energy_only','schedule']),
        pilot_matrix=[dict(N=16,query_ids=['SD01'],scenarios=['energy_only']),
                      dict(N=64,query_ids=['SD01','SD02'],scenarios=['energy_only','schedule'])],
        diagnostics=dict(legacy_common_domain=dict(N=4,query_id='SD01',scenario='energy_only',wall_s=60),
            bound_ablation=dict(N=16,query_id='SD02',scenario='energy_only',method='scale',
                                use_bound_values=[True,False],wall_s=60)))


def supervised(**updates):
    value = dict(timed_out=False,memory_limited=False,host_headroom_limited=False,cpu_limited=False,
                 returncode=0,stderr=b'',elapsed_s=10,rss_peak_bytes=100,host_available_min_bytes=200,
                 cpu_peak_s=8)
    value.update(updates)
    return SimpleNamespace(**value)


class PilotControlTests(unittest.TestCase):
    def test_default_and_filtered_workload_never_expand_declared_matrix(self):
        rows = pilot.selected_workload(config(),args())
        self.assertEqual(len(rows),10)
        self.assertFalse(any(row['N']==16 and row['query_id']=='SD02' for row in rows))
        chosen = pilot.selected_workload(config(),args(domains='64',queries='SD02',scenarios='schedule',methods='scale'))
        self.assertEqual(len(chosen),1)
        self.assertEqual(chosen[0]['solve_limit_s'],120)
        for scoped in (args(domains='16',queries='SD02'),args(domains='16,16'),args(domains='128'),
                       args(solve_limit_seconds=300),args(no_bound=True)):
            with self.assertRaises(ValueError):
                pilot.selected_workload(config(),scoped)

    def test_diagnostics_and_ablation_match_their_separate_declarations(self):
        legacy = pilot.selected_workload(config(),args(diagnostic=True))
        self.assertEqual({r['method'] for r in legacy},{'flat_bb_legacy','flat_bb_strong','scale'})
        self.assertEqual({r['N'] for r in legacy},{4})
        self.assertEqual({r['solve_limit_s'] for r in legacy},{60})
        ablation = pilot.selected_workload(config(),args(ablation=True))
        self.assertEqual({r['use_bound'] for r in ablation},{True,False})
        self.assertEqual({r['query_id'] for r in ablation},{'SD02'})
        self.assertEqual(len(pilot.selected_workload(config(),args(ablation=True,no_bound=True))),1)
        for scoped in (args(ablation=True,methods='flat_bb_strong'),args(ablation=True,queries='SD01'),
                       args(ablation=True,solve_limit_seconds=120),args(diagnostic=True,no_bound=True),
                       args(ablation=True,diagnostic=True)):
            with self.assertRaises(ValueError):
                pilot.selected_workload(config(),scoped)

    def test_loaded_query_watchdog_interrupts_and_disarms(self):
        from hiroute.exact.scale import ResourceLimit
        previous = signal.getsignal(signal.SIGALRM)
        with self.assertRaises(ResourceLimit) as caught:
            with pilot.loaded_query_watchdog(time.monotonic(),.01):
                time.sleep(.04)
        self.assertEqual(caught.exception.status,'time_limit')
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.,0.))
        self.assertIs(signal.getsignal(signal.SIGALRM),previous)
        with self.assertRaises(ValueError):
            with pilot.loaded_query_watchdog(time.monotonic(),1):
                raise ValueError('verification failure')
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL),(0.,0.))

    def test_worker_file_cannot_retain_success_after_replay_error(self):
        from hiroute.exact import road_index,scale,scale_replay
        import hiroute.runtime as runtime
        class FakeNative:
            check = None
            def __init__(self,*a,**kw):
                pass
            def selected_leg(self,source,target):
                return road_index.IndexedLeg(source,target,1,1,())
            def distances_to(self,*a):
                return {'o':1,'z':0,'a':1}
            def metrics(self):
                return {}
            def close(self):
                pass
        model = config()
        model['selection']['domain_claim']='explicit test domain'
        model['resources'].update(host_headroom_bytes=0,query_extra_memory_bytes=10000)
        query = dict(query_id='SD01',great_circle_m=1,eligible_unique_anchors=1,
            scenario_candidate_domains={'energy_only':{'16':[dict(site_id=str(i),access_node=str(i),
                capabilities=['C']) for i in range(16)]}},scenario_eligible_counts={'energy_only':16},
            endpoints={'origin':dict(site_id='o',access_node='o'),
                       'destination':dict(site_id='z',access_node='z')})
        snapshot = SimpleNamespace(origin='o',destination='z',consumption_kwh_per_m=1,
                                  destination_reserve_kwh=0,initial_energy_kwh=10,
                                  capacity_kwh=10,minimum_energy_kwh=0)
        result = dict(status='attained_optimum',key=['1','0',0,[]],metrics={},seconds={},
                      depth_contract={},seed=None,query_extra_peak_bytes=0,routing_metrics={},open_remaining=0)
        with tempfile.TemporaryDirectory() as work:
            work=Path(work)
            (work/'config.json').write_text(json.dumps(model))
            (work/'preflight.json').write_text(json.dumps(dict(queries=[query])))
            worker_args=args(config=work/'config.json',preflight=work/'preflight.json',query='SD01',
                n=16,scenario='energy_only',method='scale',graph_tsv='unused',native_cache=work,
                output=work/'row.json')
            with patch.object(road_index,'NativeRoadIndex',FakeNative), \
                 patch.object(scale,'solve_scale',return_value=result), \
                 patch.object(scale,'validate_scale_input'), \
                 patch.object(scale,'_resident_bytes',return_value=100), \
                 patch.object(scale_replay,'verify_scale_witness',side_effect=ValueError('bad physical replay')), \
                 patch.object(runtime,'system_mem_available_bytes',return_value=100000), \
                 patch.object(pilot,'bind_snapshot',return_value=snapshot):
                with self.assertRaisesRegex(ValueError,'bad physical replay'):
                    pilot.worker(worker_args)
            row=json.loads((work/'row.json').read_text())
            self.assertEqual(row['status'],'worker_error')
            self.assertEqual(row['mathematical_status'],'unknown')
            self.assertNotIn('key',row)
            self.assertIn('bad physical replay',row['error'])

    def test_unavailable_input_returns_before_native_index_construction(self):
        from hiroute.exact import road_index
        import hiroute.runtime as runtime
        model = config()
        model['selection']['domain_claim']='explicit test domain'
        model['resources'].update(host_headroom_bytes=0,query_extra_memory_bytes=10000)
        query = dict(query_id='SD01',great_circle_m=1,eligible_unique_anchors=1,
            scenario_candidate_domains={'energy_only':{'16':[dict(site_id='a',access_node='a',capabilities=['C'])]}},
            scenario_eligible_counts={'energy_only':1},
            endpoints={'origin':dict(site_id='o',access_node='o'),
                       'destination':dict(site_id='z',access_node='z')})
        with tempfile.TemporaryDirectory() as work:
            work=Path(work)
            (work/'config.json').write_text(json.dumps(model))
            (work/'preflight.json').write_text(json.dumps(dict(queries=[query])))
            worker_args=args(config=work/'config.json',preflight=work/'preflight.json',query='SD01',
                n=16,scenario='energy_only',method='scale',graph_tsv='unused',native_cache=work,
                output=work/'row.json')
            with patch.object(road_index,'NativeRoadIndex') as constructor, \
                 patch.object(runtime,'system_mem_available_bytes',return_value=100000):
                pilot.worker(worker_args)
                constructor.assert_not_called()
            row=json.loads((work/'row.json').read_text())
            self.assertEqual(row['status'],'input_domain_unavailable')
            self.assertEqual(row['mathematical_status'],'unknown')
            self.assertEqual((row['requested_N'],row['available_N']),(16,1))
            self.assertNotIn('key',row)

    def test_written_result_cannot_hide_failed_independent_verification(self):
        claimed = dict(status='attained_optimum',mathematical_status='attained_optimum',key=['5','2',1,[]],
                       primary_infimum='5',secondary_infimum='2',witness=None)
        checkpoint = dict(key=['6','3',1,[]],verified=dict(physical_verified=True),
                          time_to_first_feasible_s=4)
        row = pilot.apply_supervisor_outcome(claimed,supervised(returncode=1,stderr=b'physical replay failed'),checkpoint)
        self.assertEqual(row['status'],'worker_error')
        self.assertEqual(row['mathematical_status'],'unknown')
        for field in ('key','primary_infimum','secondary_infimum'):
            self.assertNotIn(field,row)
        self.assertEqual(row['feasible_key'],checkpoint['key'])
        self.assertTrue(row['witness']['physical_verified'])
        self.assertIn('physical replay failed',row['error'])
        self.assertIn('key',claimed)  # The pure helper does not modify its input.

    def test_resource_exit_is_unknown_and_success_keeps_global_result(self):
        claimed = dict(status='attained_optimum',key=['5','2',1,[]])
        timeout = pilot.apply_supervisor_outcome(claimed,supervised(timed_out=True,returncode=-15))
        self.assertEqual(timeout['status'],'time_limit')
        self.assertEqual(timeout['mathematical_status'],'unknown')
        self.assertNotIn('key',timeout)
        success = pilot.apply_supervisor_outcome(claimed,supervised())
        self.assertEqual(success['status'],'attained_optimum')
        self.assertEqual(success['key'],claimed['key'])
        with self.assertRaises(ValueError):
            pilot.apply_supervisor_outcome(claimed,supervised(),dict(verified=dict(physical_verified=False)))


if __name__ == '__main__':
    unittest.main()
