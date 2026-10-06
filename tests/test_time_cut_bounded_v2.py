"""Bounded physical FLAT tests; no full-network or global-infeasibility claim."""
from copy import deepcopy
from fractions import Fraction as R
import hashlib
import json
from pathlib import Path
import unittest

from timecut5.bounded import Problem, evaluate_sequence, replay_witness, solve_bounded
from timecut5.probe import Event, State, Witness


ROOT = Path(__file__).resolve().parents[1]


def simple_case(secondary=False):
    edges = [("o", "s", 1, 1)]
    if secondary:
        edges += [("o", "g", 1, 100), ("s", "g", 1, 1), ("g", "z", 1, 1)]
    else:
        edges += [("o", "z", 1, 20), ("s", "z", 1, 1)]
    return dict(H_ref=3, origin="o", destination="z", start_time_s=0,
                initial_energy_kwh=10, capacity_kwh=10, minimum_energy_kwh=0,
                reserve_kwh=0, consumption_kwh_per_m=1, overhead_s=1,
                lambda_stop_s=1, schedule={"a":10,"b":10,"D":1} if secondary else None,
                sites={"s":["C"], "g":["S"]} if secondary else {"s":["C"]},
                charging_segments=[[0,10,1,0]],
                edges=[dict(source=a,target=b,time_s=t,length_m=c) for a,b,t,c in edges])


class TestBoundedPhysicalFlat(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = ROOT / "results/milestone_4r_b2_b21/hand_cases.json"
        cls.fixture_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        cls.original = json.loads(path.read_text())[0]
        cls.original_results = [solve_bounded(cls.original, dominance=d) for d in (False, True)]

    def test_original_frozen_fixture_identity(self):
        self.assertEqual(self.fixture_hash, "5e8f4b92bdbefdf5f35104b9430bbc2d0541517e0df41b4ecdb9ca67f85a5744")
        manifest = json.loads((ROOT / "results/milestone_4r_b2_b21/case_construction_manifest.json").read_text())
        self.assertEqual(manifest["case_file_sha256"], self.fixture_hash)

    def test_original_76_regression_full_bounded_d_on_off(self):
        expected = (44950, 76, 3, (("4r:node/2","C"),("4r:node/3","C"),("4r:node/4","S")))
        for result in self.original_results:
            self.assertEqual(result.scope, "bounded_H_ref_diagnostic")
            self.assertEqual(result.H_ref, 4)
            self.assertEqual(result.result.status, "attained_optimum")
            self.assertEqual(result.result.key, expected)
            self.assertEqual(replay_witness(self.original, result.result.witness), expected)
            self.assertEqual(result.canonical()["result"]["charges"], (28,48))

    def test_original_alternative_is_83_and_cannot_win(self):
        sequence = (("4r:node/1","C"),("4r:node/3","C"),("4r:node/4","S"))
        result = evaluate_sequence(self.original, sequence)
        self.assertEqual(result.key[:3], (44950,83,3))
        self.assertEqual(replay_witness(self.original, result.witness), result.key)

    def test_primary_nonattainment_is_not_a_fake_optimum(self):
        for dominance in (False, True):
            output = solve_bounded(simple_case(), dominance).canonical()["result"]
            self.assertEqual(output, {"status":"primary_unattained", "primary_infimum":R(4)})

    def test_secondary_nonattainment_uses_attained_primary_face(self):
        for dominance in (False, True):
            output = solve_bounded(simple_case(True), dominance).canonical()["result"]
            self.assertEqual(output, {"status":"secondary_unattained", "J":R(14),
                                      "secondary_infimum":R(0)})

    def test_cs_is_concurrent_and_beats_separate_effects(self):
        case = simple_case()
        case.update(initial_energy_kwh=3, reserve_kwh=1,
                    sites={"s":["C","S","CS"]},
                    schedule={"a":5,"b":6,"D":2}, charging_segments=[[0,10,2,0]])
        case["edges"] = [dict(source=a,target=b,time_s=t,length_m=c) for a,b,t,c in
                         [("o","z",1,10),("o","s",1,2),("s","z",1,2)]]
        for dominance in (False,True):
            result = solve_bounded(case,dominance)
            self.assertEqual(result.result.key, (9,2,1,(("s","CS"),)))
            self.assertEqual(replay_witness(case,result.result.witness),result.result.key)

    def test_explicit_initial_schedule_state(self):
        case = simple_case(True)
        case["initial_remaining_schedule"] = 0
        result = solve_bounded(case)
        self.assertEqual(result.result.unattained_component, "J")
        self.assertEqual(result.result.primary_infimum, 5)
        case["schedule"] = None
        case["initial_remaining_schedule"] = 1
        with self.assertRaises(ValueError):
            Problem(case)

    def test_fastest_path_uses_its_actual_energy_with_edge_ties(self):
        case = simple_case()
        case["edges"] = [dict(source="o",target="z",time_s=1,length_m=2,edge_id="z"),
                         dict(source="o",target="z",time_s=1,length_m=5,edge_id="a"),
                         dict(source="o",target="z",time_s=2,length_m=1,edge_id="b")]
        leg = Problem(case).legs["o","z"]
        self.assertEqual((leg.time,leg.energy,leg.edge_ids), (1,5,("a",)))

    def test_stop_bound_is_explicit_and_zero_bound_not_global_infeasibility(self):
        case = deepcopy(self.original)
        case["H_ref"] = 0
        result = solve_bounded(case)
        self.assertEqual(result.canonical(), dict(scope="bounded_H_ref_diagnostic", H_ref=0,
                                                  result={"status":"infeasible_within_H_ref"}))
        with self.assertRaises(ValueError):
            evaluate_sequence(case, (("4r:node/1","C"),))

    def test_no_charge_law_needed_when_charging_is_unavailable(self):
        case = simple_case()
        case.update(sites={}, charging_segments=[], initial_energy_kwh=10,
                    edges=[dict(source="o",target="z",time_s=1,length_m=1)])
        self.assertEqual(solve_bounded(case).result.key, (1,0,0,()))
        case["sites"] = {"s":["C"]}
        with self.assertRaises(ValueError):
            Problem(case)

    def test_destination_is_terminal_not_a_service_site(self):
        case = simple_case()
        case.update(H_ref=1, initial_energy_kwh=2, sites={"z":["S"]}, charging_segments=[],
                    schedule={"a":0,"b":100,"D":1},
                    edges=[dict(source="o",target="z",time_s=1,length_m=1)])
        for dominance in (False,True):
            self.assertEqual(solve_bounded(case,dominance).canonical()["result"]["status"],
                             "infeasible_within_H_ref")
        self.assertEqual(evaluate_sequence(case, (("z","S"),)).status, "infeasible")
        forged = Witness(3,1,-1,(("z","S"),),State("z",0,1),(
            Event("initial","o",0,0,2,2), Event("D","z",0,1,2,1), Event("S","z",1,3,1,1)))
        with self.assertRaises(AssertionError):
            replay_witness(case, forged)

    def test_terminal_origin_cannot_depart_or_satisfy_pending_service(self):
        case = simple_case()
        case.update(origin="z", destination="z", sites={"s":["S"]}, charging_segments=[],
                    schedule=None, edges=[dict(source="z",target="s",time_s=1,length_m=1),
                                          dict(source="s",target="z",time_s=1,length_m=1)])
        result = solve_bounded(case)
        self.assertEqual(result.result.key, (0,0,0,()))
        self.assertEqual(len(result.result.witness.events), 1)
        case["schedule"] = {"a":0,"b":100,"D":1}
        self.assertEqual(solve_bounded(case).canonical()["result"]["status"], "infeasible_within_H_ref")

    def test_witness_replay_rejects_a_plan_outside_diagnostic_bound(self):
        # Use the original attained three-stop plan as a physically valid
        # witness whose H is outside a subsequently reduced comparison domain.
        witness = self.original_results[0].result.witness
        restricted = deepcopy(self.original)
        restricted["H_ref"] = 2
        with self.assertRaises(AssertionError):
            replay_witness(restricted, witness)

    def test_consecutive_drive_bypass_is_not_a_physical_plan(self):
        case = simple_case()
        case.update(H_ref=1, initial_energy_kwh=2, lambda_stop_s=0,
                    edges=[dict(source=a,target=b,time_s=1,length_m=c) for a,b,c in
                           [("o","z",5),("o","s",1),("s","z",1)]])
        forged = Witness(2,0,0,(),State("z",0,0),(
            Event("initial","o",0,0,2,2),Event("D","s",0,1,2,1),Event("D","z",1,2,1,0)))
        with self.assertRaises(AssertionError):
            replay_witness(case,forged)
        from timecut5.hierarchy import solve_hierarchical
        with self.assertRaises(AssertionError):
            solve_hierarchical(case,incumbent=forged)


if __name__ == "__main__":
    unittest.main()
