import unittest

from scripts.m5d_charge_gate import evaluate


class ChargeGateTest(unittest.TestCase):
    def test_exact_boundary_and_proof_label(self):
        common = dict(od_id="OD", initial_energy_kwh="18", capacity_kwh="60",
                      terminal_reserve_kwh="6", consumption_kwh_per_m="1/6250")
        payload = {"distance_certified": False, "states": [
            dict(common, state_id="at_boundary", road_distance_lower_m="450000"),
            dict(common, state_id="above_boundary", road_distance_lower_m="450001"),
        ]}
        answer = evaluate(payload)
        self.assertEqual([row["minimum_charges_from_distance"] for row in answer["states"]], [1, 2])
        self.assertEqual(answer["od_ids_with_minimum_two_charges"], ["OD"])
        self.assertEqual(evaluate(payload)["claim_status"], "screening_only")
        payload["distance_certified"] = True
        with self.assertRaises(ValueError):
            evaluate(payload)

    def test_reject_unbound_numeric_type_and_duplicate(self):
        state = dict(state_id="C01", od_id="OD", road_distance_lower_m=450001,
                     initial_energy_kwh="18", capacity_kwh="60", terminal_reserve_kwh="6",
                     consumption_kwh_per_m="1/6250")
        with self.assertRaises(ValueError):
            evaluate({"distance_certified": False, "states": [state]})
        state["road_distance_lower_m"] = "450001"
        with self.assertRaises(ValueError):
            evaluate({"distance_certified": False, "states": [state, state]})


if __name__ == "__main__":
    unittest.main()
