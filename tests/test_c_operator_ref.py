"""Independent REF replay of terminal faces and cached exact families."""
import unittest

class CReferenceTests(unittest.TestCase):
    def test_terminal_faces_cache_reuse_and_independent_physical_replay(self):
        import json
        from pathlib import Path
        from unittest.mock import patch
        from hiroute.contracts import ProblemSnapshot
        from hiroute.exact import search
        from hiroute_ref.cli import snapshot_case
        from hiroute_ref.model import normalize_case, replay_witness
        from test_prefix_reuse import raw_case, config, math_result
        raw = raw_case()
        cases = [raw]
        frozen = json.loads((Path(__file__).parent/'fixtures/milestone_5_reference/frozen_cases_v2.json').read_text())
        for case in (frozen[5],frozen[6]):
            item = dict(raw,origin=case['origin'],destination=case['destination'],
                departure_time_s=case['start_time_s'],initial_energy_kwh=case['initial_energy_kwh'],
                capacity_kwh=case['capacity_kwh'],minimum_energy_kwh=case['minimum_energy_kwh'],
                destination_reserve_kwh=case['reserve_kwh'],stop_overhead_s=case['overhead_s'],
                stop_penalty_s=case['lambda_stop_s'],consumption_kwh_per_m=case['consumption_kwh_per_m'],
                charging_curve=case['charging_segments'],candidate_order=list(case['sites']),
                site_capabilities=case['sites'],depth_limit=case['H_ref'],schedule=case['schedule'],
                initial_remaining_schedule=1,directed_edges=case['edges'])
            cases.append(item)
        for raw in cases:
            for method in ('flat','hier'):
                snap=ProblemSnapshot.from_dict(raw)
                old=search.solve_snapshot(snap,config(method),c_backend='projection',observer='detailed_trace')
                new=search.solve_snapshot(snap,config(method),c_backend='analytic',observer='detailed_trace')
                self.assertEqual(math_result(old),math_result(new))
                self.assertEqual(old['observer']['trace'],new['observer']['trace'])
                def cold(cache,plan,steps):
                    return search.execute_exact_plan(cache.families[()],steps,c_backend=cache.c_backend)
                with patch.object(search._PlanPrefixCache,'propagate',cold):
                    uncached=search.solve_snapshot(snap,config(method),c_backend='analytic')
                self.assertEqual(math_result(new),math_result(uncached))
                if new['status']=='attained_optimum':
                    source_case,_=snapshot_case(raw)
                    charges=[oe-ie for effect,_,ie,_,oe,_ in new['replay']['trace'] if effect in ('C','CS')]
                    replay=replay_witness(normalize_case(source_case),new['plan'],charges)
                    self.assertEqual(replay['lex_key'],new['key'])

