import copy
import json
from pathlib import Path
import unittest
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO

from hiroute.contracts import ProblemSnapshot, SolverConfig
from hiroute.exact.search import selected_leg, solve_snapshot
from hiroute.cli import main as cli_main

ROOT = Path(__file__).resolve().parents[1]


def config(method="flat"):
    return SolverConfig(method, "none", "bounded_time_cut_v2", "none", "none", "none",
                        "full_lexicographic_J_Q_H_Pi")


def load_c01():
    raw = json.loads((ROOT / "tests/r0/c01_zero_stop_snapshot.json").read_text())
    return ProblemSnapshot.from_dict(raw)


class NativeSearchTests(unittest.TestCase):
    def test_c01_directed_zero_stop_exact_core(self):
        snapshot = load_c01()
        result = solve_snapshot(snapshot, config())
        self.assertEqual(result["status"], "attained_optimum")
        self.assertEqual(result["key"], (1, 0, 0, ()))
        self.assertEqual(result["replay"]["key"], (1, 0, 0, ()))
        self.assertEqual(result["legs"][0].edges[0]["edge_id"], "direct")
        # Independent physical ledger: no charge event, one unit consumed.
        # Q = E_terminal - E_initial + road consumption = 9 - 10 + 1 = 0.
        self.assertEqual(result["replay"]["energy"], 9)
        self.assertEqual(result["replay"]["rho"], -9)
        self.assertEqual(result["key"][1], 9 - 10 + 1)
        self.assertEqual(result["replay"]["events"], ())

    def test_c02_zero_charge_transition_is_rejected_by_physical_replay(self):
        from fractions import Fraction
        from hiroute.exact.pipeline import InitialWitness, replay_chain
        from hiroute.exact.pwa_partition import TransitionWitness
        witness = TransitionWitness(
            "C", "c", Fraction(2), Fraction(0), Fraction(2), Fraction(1),
            InitialWitness(Fraction(2), Fraction(0)),
            (((Fraction(0), Fraction(5), Fraction(1), Fraction(0)),),
             Fraction(1), Fraction(0), Fraction(0), Fraction(0)),
        )
        with self.assertRaisesRegex(ValueError, "strictly increase"):
            replay_chain(witness)

    def test_single_charge_full_witness_and_route(self):
        # This is a real solve with no incumbent seed supplied.
        self.assertEqual(config("flat").seed_policy, "none")
        self.assertEqual(config("hier").seed_policy, "none")
        raw = load_c01().to_dict()
        raw.pop("semantic_problem_id")
        raw.update({
            "origin": "o", "destination": "z", "initial_energy_kwh": "2",
            "capacity_kwh": "5", "minimum_energy_kwh": "1",
            "destination_reserve_kwh": "1", "consumption_kwh_per_m": "1",
            "candidate_order": ["c"], "site_capabilities": {"c": ["C"]},
            "charging_curve": [["0", "5", "1", "0"]],
            "directed_edges": [
                {"source": "o", "target": "c", "time_s": "1", "length_m": "1", "edge_id": "oc"},
                {"source": "c", "target": "z", "time_s": "3", "length_m": "3", "edge_id": "cz"},
            ],
            "depth_limit": 1,
        })
        snapshot = ProblemSnapshot.from_dict(raw)
        flat = solve_snapshot(snapshot, config("flat"))
        hier = solve_snapshot(snapshot, config("hier"))
        self.assertEqual(flat["status"], "attained_optimum")
        self.assertEqual(flat["key"], (9, 3, 1, (("c", "C"),)))
        self.assertEqual(hier["key"], flat["key"])
        self.assertEqual(hier["hierarchical_search"], "region_refinement_strict_primary_bound")
        self.assertEqual(hier["enumeration_backend"], "exact_region_search")
        self.assertEqual(hier["input_identity"], flat["input_identity"])
        self.assertEqual(hier["input_identity"]["semantic_problem_id"], snapshot.semantic_problem_id)
        self.assertGreater(hier["hierarchy_metrics"]["region_nodes"], 0)
        self.assertGreaterEqual(hier["hierarchy_metrics"]["region_nodes"],
                                hier["hierarchy_metrics"]["leaf_actions"])
        self.assertGreaterEqual(hier["hierarchy_metrics"]["pruned_regions"], 0)
        self.assertEqual(flat["hierarchical_search"], "not_requested")
        self.assertEqual(flat["replay"]["events"], (("c", "C"),))
        self.assertEqual(flat["replay"]["trace"][0][0], "D")
        self.assertEqual([x["edge_id"] for leg in flat["legs"] for x in leg.edges], ["oc", "cz"])

    def test_c09_original_76_kwh_end_to_end_flat_hier(self):
        raw_case = json.loads((ROOT / "tests/fixtures/milestone_4r_b2_b21/hand_cases.json").read_text())[0]
        self.assertEqual(raw_case["independent_expected"]["Q_total"], "76")
        raw = load_c01().to_dict()
        raw.pop("semantic_problem_id")
        raw.update({
            "origin": raw_case["origin"], "destination": raw_case["destination"],
            "departure_time_s": str(raw_case["start_time_s"]),
            "initial_energy_kwh": str(raw_case["initial_energy_kwh"]),
            "capacity_kwh": str(raw_case["capacity_kwh"]),
            "minimum_energy_kwh": str(raw_case["minimum_energy_kwh"]),
            "destination_reserve_kwh": str(raw_case["reserve_kwh"]),
            "stop_overhead_s": str(raw_case["overhead_s"]),
            "stop_penalty_s": str(raw_case["lambda_stop_s"]),
            "consumption_kwh_per_m": "2/12500",
            "schedule": {k: str(v) for k, v in raw_case["schedule"].items()},
            "initial_remaining_schedule": 1,
            "candidate_order": list(raw_case["sites"]),
            "site_capabilities": raw_case["sites"],
            "charging_curve": raw_case["charging_segments"],
            "directed_edges": [{**edge, "time_s": str(edge["time_s"]),
                                "length_m": str(edge["length_m"])}
                               for edge in raw_case["edges"]],
            "depth_limit": raw_case["H_ref"],
        })
        snapshot = ProblemSnapshot.from_dict(raw)
        flat = solve_snapshot(snapshot, config("flat"))
        hier = solve_snapshot(snapshot, config("hier"))
        expected = raw_case["independent_expected"]
        self.assertEqual(flat["key"], (int(expected["J"]), int(expected["Q_total"]),
                                       expected["H"], tuple(map(tuple, expected["site_action_tuple"]))))
        self.assertEqual(hier["key"], flat["key"])
        self.assertEqual(hier["replay"]["key"], flat["replay"]["key"])
        self.assertEqual(hier["replay"]["energy"], int(expected["terminal_energy_kwh"]))
        self.assertEqual(hier["hierarchical_search"], "region_refinement_strict_primary_bound")
        self.assertEqual(hier["hierarchy_metrics"]["missing_actions"], 0)
        self.assertEqual(hier["hierarchy_metrics"]["duplicate_actions"], 0)
        self.assertGreater(hier["hierarchy_metrics"]["region_nodes"], 0)
        self.assertGreater(hier["hierarchy_metrics"]["leaf_actions"], 0)
        self.assertEqual(hier["input_identity"], flat["input_identity"])
        self.assertEqual(hier["input_identity"]["semantic_problem_id"], snapshot.semantic_problem_id)
        self.assertEqual(hier["input_identity"]["model_contract_id"], snapshot.model_contract_id)
        self.assertEqual(hier["input_identity"]["numerical_contract_id"], snapshot.numerical_contract_id)
        self.assertEqual(hier["input_identity"]["graph_or_leg_identity"], snapshot.graph_or_leg_identity)
        self.assertEqual(hier["replay"]["key"], hier["key"])

    def test_hierarchical_empty_and_unreachable_regions_report_coverage(self):
        raw = load_c01().to_dict()
        raw.pop("semantic_problem_id")
        raw["candidate_order"] = []
        raw["site_capabilities"] = {}
        raw["depth_limit"] = 1
        empty = solve_snapshot(ProblemSnapshot.from_dict(raw), config("hier"))
        self.assertEqual(empty["status"], "attained_optimum")
        self.assertEqual(empty["hierarchy_metrics"]["empty_regions"], 1)
        self.assertEqual(empty["hierarchy_metrics"]["missing_actions"], 0)
        self.assertEqual(empty["hierarchy_metrics"]["duplicate_actions"], 0)

        raw = load_c01().to_dict()
        raw.pop("semantic_problem_id")
        raw["candidate_order"] = ["c"]
        raw["site_capabilities"] = {"c": ["C"]}
        raw["directed_edges"] = []
        raw["depth_limit"] = 1
        unreachable = solve_snapshot(ProblemSnapshot.from_dict(raw), config("hier"))
        self.assertEqual(unreachable["status"], "infeasible")
        self.assertGreater(unreachable["hierarchy_metrics"]["unreachable_regions"], 0)
        self.assertEqual(unreachable["hierarchy_metrics"]["missing_actions"], 0)
        self.assertEqual(unreachable["hierarchy_metrics"]["duplicate_actions"], 0)

    def test_c06_schedule_window_infeasible_stop_is_excluded(self):
        raw = load_c01().to_dict()
        raw.pop("semantic_problem_id")
        raw.update({
            "origin": "o", "destination": "z", "departure_time_s": "0",
            "initial_energy_kwh": "5", "capacity_kwh": "5",
            "minimum_energy_kwh": "0", "destination_reserve_kwh": "0",
            "stop_overhead_s": "1", "stop_penalty_s": "0",
            "consumption_kwh_per_m": "0", "candidate_order": ["c"],
            "site_capabilities": {"c": ["S"]}, "schedule": {"a": "0", "b": "5", "D": "0"},
            "initial_remaining_schedule": 1, "depth_limit": 1,
            "directed_edges": [
                {"source": "o", "target": "c", "time_s": "10", "length_m": "1", "edge_id": "oc"},
                {"source": "c", "target": "z", "time_s": "1", "length_m": "1", "edge_id": "cz"},
            ],
        })
        snapshot = ProblemSnapshot.from_dict(raw)
        for method in ("flat", "hier"):
            with self.subTest(method=method):
                result = solve_snapshot(snapshot, config(method), observer="detailed_trace")
                self.assertEqual(result["status"], "infeasible")
                trace = {tuple(tuple(a) for a in row["plan"]): row["terminal_status"]
                         for row in result["observer"]["trace"]}
                self.assertEqual(trace[(("c", "S"),)], "infeasible")
                self.assertIsNone(result.get("incumbent"))
        # Widening only the latest-start boundary makes the same action feasible.
        raw["schedule"]["b"] = "12"
        feasible = solve_snapshot(ProblemSnapshot.from_dict(raw), config("flat"))
        self.assertEqual(feasible["status"], "attained_optimum")
        self.assertEqual(feasible["key"], (12, 0, 1, (("c", "S"),)))
        self.assertEqual(feasible["replay"]["key"], feasible["key"])

    def test_hierarchical_primary_bound_equality_is_retained(self):
        raw = load_c01().to_dict()
        raw.pop("semantic_problem_id")
        raw.update({
            "origin": "o", "destination": "z", "initial_energy_kwh": "5",
            "capacity_kwh": "5", "minimum_energy_kwh": "0",
            "destination_reserve_kwh": "0", "stop_overhead_s": "1",
            "stop_penalty_s": "0", "consumption_kwh_per_m": "0",
            "candidate_order": ["c"], "site_capabilities": {"c": ["C"]},
            "charging_curve": [["0", "5", "1", "0"]], "depth_limit": 1,
            "directed_edges": [
                {"source": "o", "target": "c", "time_s": "1", "length_m": "1", "edge_id": "oc"},
                {"source": "c", "target": "z", "time_s": "1", "length_m": "1", "edge_id": "cz"},
                {"source": "o", "target": "z", "time_s": "3", "length_m": "3", "edge_id": "oz"},
            ],
        })
        snapshot = ProblemSnapshot.from_dict(raw)
        flat = solve_snapshot(snapshot, config("flat"))
        hier = solve_snapshot(snapshot, config("hier"))
        self.assertEqual(hier["key"], flat["key"])
        self.assertEqual(hier["key"], (2, 0, 0, ()))
        self.assertGreater(hier["hierarchy_metrics"]["equality_nodes_retained"], 0)
        self.assertEqual(hier["hierarchy_metrics"]["missing_actions"], 0)
        self.assertEqual(hier["hierarchy_metrics"]["duplicate_actions"], 0)

    def test_selected_leg_min_time_then_actual_length_then_first_discovery(self):
        raw = load_c01().to_dict()
        raw.pop("semantic_problem_id")
        raw.update({
            "directed_edges": [
                {"source": "o", "target": "a", "time_s": "1", "length_m": "2", "edge_id": "first-a"},
                {"source": "a", "target": "z", "time_s": "1", "length_m": "2", "edge_id": "first-z"},
                {"source": "o", "target": "b", "time_s": "1", "length_m": "1", "edge_id": "short-a"},
                {"source": "b", "target": "z", "time_s": "1", "length_m": "1", "edge_id": "short-z"},
            ],
        })
        snapshot = ProblemSnapshot.from_dict(raw)
        leg = selected_leg(snapshot, "o", "z")
        self.assertEqual(leg.time_s, 2)
        self.assertEqual(leg.length_m, 2)
        self.assertEqual([e["edge_id"] for e in leg.edges], ["short-a", "short-z"])


    def test_m5_c10_c15_full_search_tuple_tie_and_primary_unattained(self):
        frozen = json.loads((ROOT / "tests/fixtures/milestone_5_reference/frozen_cases_v2.json").read_text())
        for index in (5, 7, 14):
            case = frozen[index]
            with self.subTest(case=case["case_id"]):
                raw = load_c01().to_dict()
                raw.pop("semantic_problem_id")
                schedule = case.get("schedule")
                raw.update({
                    "origin": case["origin"], "destination": case["destination"],
                    "departure_time_s": str(case["start_time_s"]),
                    "initial_energy_kwh": str(case["initial_energy_kwh"]),
                    "capacity_kwh": str(case["capacity_kwh"]),
                    "minimum_energy_kwh": str(case["minimum_energy_kwh"]),
                    "destination_reserve_kwh": str(case["reserve_kwh"]),
                    "stop_overhead_s": str(case["overhead_s"]),
                    "stop_penalty_s": str(case["lambda_stop_s"]),
                    "consumption_kwh_per_m": str(case["consumption_kwh_per_m"]),
                    "schedule": None if schedule is None else {k: str(v) for k, v in schedule.items()},
                    "initial_remaining_schedule": 0 if schedule is None else 1,
                    "candidate_order": list(case["sites"]),
                    "site_capabilities": case["sites"],
                    "charging_curve": [[str(v) for v in row] for row in case.get("charging_segments", [])],
                    "directed_edges": [
                        {**edge, "time_s": str(edge["time_s"]), "length_m": str(edge["length_m"]),
                         "edge_id": edge.get("edge_id", str(case.get("case_id")) + "-edge-" + str(i))}
                        for i, edge in enumerate(case["edges"])
                    ],
                    "depth_mode": "diagnostic_cap", "depth_limit": case["H_ref"],
                    "graph_or_leg_identity": "frozen-m5-v2:" + str(case["case_id"]),
                })
                snapshot = ProblemSnapshot.from_dict(raw)
                results = [solve_snapshot(snapshot, config(method), time_limit_s=60)
                           for method in ("flat", "hier")]
                expected = case["independent_expected"]
                for method, result in zip(("flat", "hier"), results):
                    self.assertEqual(result["status"], expected["status"], (method, case["case_id"], result))
                    if expected["status"] == "primary_unattained":
                        self.assertEqual(str(result["primary_infimum"]), expected["primary_infimum"])
                        self.assertNotIn("key", result)
                        self.assertNotIn("witness", result)
                    else:
                        expected_key = (int(expected["J"]), int(expected["Q_total"]),
                                        int(expected["H"]), tuple(map(tuple, expected["site_action_tuple"])))
                        self.assertEqual(result["key"], expected_key)
                        self.assertEqual(result["replay"]["key"], expected_key)
                self.assertEqual(results[0].get("key", results[0].get("primary_infimum")),
                                 results[1].get("key", results[1].get("primary_infimum")))

    def test_m5_c16_secondary_unattained_full_search_keeps_attained_primary(self):
        frozen = json.loads((ROOT / "tests/fixtures/milestone_5_reference/frozen_cases_v2.json").read_text())
        for index, expected_j in ((6, "13"), (8, "14")):
            case = frozen[index]
            raw = load_c01().to_dict()
            raw.pop("semantic_problem_id")
            schedule = case.get("schedule")
            raw.update({
                "origin": case["origin"], "destination": case["destination"],
                "departure_time_s": str(case["start_time_s"]),
                "initial_energy_kwh": str(case["initial_energy_kwh"]),
                "capacity_kwh": str(case["capacity_kwh"]),
                "minimum_energy_kwh": str(case["minimum_energy_kwh"]),
                "destination_reserve_kwh": str(case["reserve_kwh"]),
                "stop_overhead_s": str(case["overhead_s"]),
                "stop_penalty_s": str(case["lambda_stop_s"]),
                "consumption_kwh_per_m": str(case["consumption_kwh_per_m"]),
                "schedule": None if schedule is None else {k: str(v) for k, v in schedule.items()},
                "initial_remaining_schedule": 0 if schedule is None else 1,
                "candidate_order": list(case["sites"]),
                "site_capabilities": case["sites"],
                "charging_curve": [[str(v) for v in row] for row in case.get("charging_segments", [])],
                "directed_edges": [
                    {**edge, "time_s": str(edge["time_s"]), "length_m": str(edge["length_m"]),
                     "edge_id": edge.get("edge_id", str(case.get("case_id")) + "-edge-" + str(i))}
                    for i, edge in enumerate(case["edges"])
                ],
                "depth_mode": "diagnostic_cap", "depth_limit": case["H_ref"],
                "graph_or_leg_identity": "frozen-m5-v2:" + str(case["case_id"]),
            })
            snapshot = ProblemSnapshot.from_dict(raw)
            results = []
            for method in ("flat", "hier"):
                result = solve_snapshot(snapshot, config(method), time_limit_s=60)
                self.assertEqual(result["status"], "secondary_unattained", (case["case_id"], method, result))
                self.assertEqual(result["primary_value"], int(expected_j))
                self.assertEqual(result["primary_infimum"], int(expected_j))
                self.assertEqual(result["secondary_infimum"], 0)
                self.assertNotIn("key", result)
                results.append((result["status"], result["primary_value"],
                                result["primary_infimum"], result["secondary_infimum"]))
            self.assertEqual(results[0], results[1], case["case_id"])

    def test_new_synthetic_c07_c13_c04_c12_c14_fixed_cases(self):
        fixture = json.loads((ROOT / "tests/fixtures/synthetic_c07_c13_c04_c14_v1.json").read_text())
        cases = fixture["cases"]
        for name, case in cases.items():
            with self.subTest(case=name):
                snapshot = ProblemSnapshot.from_dict(case["snapshot"])
                expected = case["expected"]
                results = {}
                for method in ("flat", "hier"):
                    result = solve_snapshot(snapshot, config(method), time_limit_s=60)
                    results[method] = result
                    self.assertEqual(result["status"], expected["status"], (name, method, result))
                    if expected["status"] == "attained_optimum":
                        key = (int(expected["key"][0]), int(expected["key"][1]),
                               expected["key"][2], tuple(map(tuple, expected["key"][3])))
                        self.assertEqual(result["key"], key, (name, method, result))
                        self.assertEqual(result["replay"]["key"], key)
                        self.assertEqual(result["input_identity"]["semantic_problem_id"], snapshot.semantic_problem_id)
                    elif expected["status"] == "secondary_unattained":
                        for field in ("primary_value", "primary_infimum", "secondary_infimum"):
                            self.assertEqual(str(result[field]), expected[field], (name, method, result))
                        self.assertNotIn("key", result)
                if expected["status"] == "infeasible":
                    self.assertEqual(results["flat"]["status"], results["hier"]["status"])
                else:
                    flat_semantics = results["flat"].get("key", (results["flat"]["status"], results["flat"].get("primary_value"), results["flat"].get("secondary_infimum")))
                    hier_semantics = results["hier"].get("key", (results["hier"]["status"], results["hier"].get("primary_value"), results["hier"].get("secondary_infimum")))
                    self.assertEqual(flat_semantics, hier_semantics)

    def test_native_cli_emits_verified_result_without_adapter_arguments(self):
        snapshot = load_c01()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            problem, solver, output = root / "problem.json", root / "solver.json", root / "result.json"
            problem.write_text(json.dumps(snapshot.to_dict()))
            solver.write_text(json.dumps(config().to_dict()))
            with redirect_stdout(StringIO()):
                code = cli_main(["solve", "--problem", str(problem), "--config", str(solver),
                                 "--output", str(output)])
            self.assertEqual(code, 0)
            record = json.loads(output.read_text())
            self.assertEqual(record["backend"], "exact_core_search")
            self.assertEqual(record["mathematical_status"], "attained_optimum")
            self.assertEqual(record["verification_status"], "witness_verified")
            self.assertEqual(record["key"], ["1", "0", 0, []])
            self.assertEqual(record["witness"]["charges_kwh"], [])
            self.assertEqual(record["witness"]["events"][0]["output_energy_kwh"], "9")
            self.assertEqual(record["witness"]["route_legs"][0]["edges"][0]["edge_id"], "direct")

    def test_native_cli_rejects_seed_depth_without_writing_result(self):
        snapshot = load_c01().to_dict()
        snapshot.pop("semantic_problem_id")
        snapshot["depth_mode"] = "seed_derived"
        snapshot["depth_certificate_reference"] = "fixture:seed"
        snapshot = ProblemSnapshot.from_dict(snapshot)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            problem, solver, output = root / "problem.json", root / "solver.json", root / "result.json"
            problem.write_text(json.dumps(snapshot.to_dict()))
            solver.write_text(json.dumps(config().to_dict()))
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as errors:
                code = cli_main(["solve", "--problem", str(problem), "--config", str(solver),
                                 "--output", str(output)])
            self.assertEqual(code, 3)
            self.assertIn("unsupported_model", errors.getvalue())
            self.assertFalse(output.exists())

    def test_c07_isolated_battery_floor_capacity_and_reserve_equalities(self):
        cases = {
            "floor": {
                "initial_energy_kwh": "5", "capacity_kwh": "5",
                "minimum_energy_kwh": "1", "destination_reserve_kwh": "2",
                "consumption_kwh_per_m": "1", "candidate_order": ["c"],
                "site_capabilities": {"c": ["C"]}, "charging_curve": [["0", "5", "1", "0"]],
                "depth_limit": 1, "directed_edges": [
                    {"source": "o", "target": "c", "time_s": "4", "length_m": "4", "edge_id": "floor-in"},
                    {"source": "c", "target": "z", "time_s": "1", "length_m": "1", "edge_id": "floor-out"}],
                "key": (8, 2, 1, (("c", "C"),)),
            },
            "capacity": {
                "initial_energy_kwh": "5", "capacity_kwh": "5",
                "minimum_energy_kwh": "0", "destination_reserve_kwh": "1",
                "consumption_kwh_per_m": "1", "candidate_order": ["c"],
                "site_capabilities": {"c": ["C"]}, "charging_curve": [["0", "5", "1", "0"]],
                "depth_limit": 1, "directed_edges": [
                    {"source": "o", "target": "c", "time_s": "1", "length_m": "1", "edge_id": "cap-in"},
                    {"source": "c", "target": "z", "time_s": "4", "length_m": "4", "edge_id": "cap-out"}],
                "key": (7, 1, 1, (("c", "C"),)),
            },
            "reserve": {
                "initial_energy_kwh": "5", "capacity_kwh": "5",
                "minimum_energy_kwh": "0", "destination_reserve_kwh": "1",
                "consumption_kwh_per_m": "1", "directed_edges": [
                    {"source": "o", "target": "z", "time_s": "4", "length_m": "4", "edge_id": "reserve-eq"}],
                "key": (4, 0, 0, ()),
            },
        }
        for name, case in cases.items():
            with self.subTest(boundary=name):
                expected = case.pop("key")
                raw = load_c01().to_dict()
                raw.pop("semantic_problem_id")
                raw.update({"origin": "o", "destination": "z", "departure_time_s": "0",
                            "stop_overhead_s": "1", "stop_penalty_s": "0",
                            "minimum_energy_kwh": "0", "destination_reserve_kwh": "0",
                            "capacity_kwh": "5", "initial_energy_kwh": "5",
                            "consumption_kwh_per_m": "0", "candidate_order": [],
                            "site_capabilities": {}, "charging_curve": [], "depth_limit": 0,
                            **case})
                snapshot = ProblemSnapshot.from_dict(raw)
                for method in ("flat", "hier"):
                    result = solve_snapshot(snapshot, config(method), time_limit_s=60)
                    self.assertEqual(result["key"], expected)
                    self.assertEqual(result["replay"]["key"], expected)

    def test_c07_isolated_battery_boundaries_just_outside_controls(self):
        # Each case changes only one boundary from its matching equality case.
        cases = {
            "floor": {"initial_energy_kwh": "5", "minimum_energy_kwh": "1",
                      "destination_reserve_kwh": "1", "candidate_order": ["c"],
                      "site_capabilities": {"c": ["C"]}, "charging_curve": [["0", "5", "1", "0"]],
                      "depth_limit": 1, "directed_edges": [
                          {"source": "o", "target": "c", "time_s": "4001/1000", "length_m": "4001/1000", "edge_id": "floor-outside-in"},
                          {"source": "c", "target": "z", "time_s": "1", "length_m": "1", "edge_id": "floor-outside-out"}]},
            "capacity": {"initial_energy_kwh": "5", "minimum_energy_kwh": "0",
                         "destination_reserve_kwh": "1", "candidate_order": ["c"],
                         "site_capabilities": {"c": ["C"]}, "charging_curve": [["0", "5", "1", "0"]],
                         "depth_limit": 1, "directed_edges": [
                             {"source": "o", "target": "c", "time_s": "1", "length_m": "1", "edge_id": "capacity-outside-in"},
                             {"source": "c", "target": "z", "time_s": "4001/1000", "length_m": "4001/1000", "edge_id": "capacity-outside-out"}]},
            "reserve": {"initial_energy_kwh": "5", "minimum_energy_kwh": "0",
                        "destination_reserve_kwh": "1001/1000", "candidate_order": [],
                        "site_capabilities": {}, "charging_curve": [], "depth_limit": 0,
                        "directed_edges": [{"source": "o", "target": "z", "time_s": "4", "length_m": "4", "edge_id": "reserve-outside"}]},
        }
        for boundary, values in cases.items():
            raw = load_c01().to_dict()
            raw.pop("semantic_problem_id")
            raw.update({"origin": "o", "destination": "z", "departure_time_s": "0",
                        "stop_overhead_s": "1", "stop_penalty_s": "0", "capacity_kwh": "5",
                        "consumption_kwh_per_m": "1", "minimum_energy_kwh": "0", "schedule": None,
                        "initial_remaining_schedule": 0, **values})
            snapshot = ProblemSnapshot.from_dict(raw)
            for method in ("flat", "hier"):
                with self.subTest(boundary=boundary, method=method):
                    result = solve_snapshot(snapshot, config(method), time_limit_s=60)
                    self.assertEqual(result["status"], "infeasible")
                    self.assertNotIn("key", result)

    def test_c20_diagnostic_cap_is_domain_scoped_and_seed_depth_is_not_silently_used(self):
        raw = load_c01().to_dict()
        raw.pop("semantic_problem_id")
        raw.update({
            "origin": "o", "destination": "z", "initial_energy_kwh": "2",
            "capacity_kwh": "5", "minimum_energy_kwh": "1",
            "destination_reserve_kwh": "1", "consumption_kwh_per_m": "1",
            "candidate_order": ["c"], "site_capabilities": {"c": ["C"]},
            "charging_curve": [["0", "5", "1", "0"]],
            "directed_edges": [
                {"source": "o", "target": "c", "time_s": "1", "length_m": "1", "edge_id": "oc"},
                {"source": "c", "target": "z", "time_s": "3", "length_m": "3", "edge_id": "cz"},
            ],
            "depth_mode": "diagnostic_cap", "depth_limit": 0,
            "depth_certificate_reference": None,
        })
        diagnostic = ProblemSnapshot.from_dict(raw)
        self.assertEqual(config().seed_policy, "none")
        for method in ("flat", "hier"):
            limited = solve_snapshot(diagnostic, config(method), time_limit_s=60)
            self.assertEqual(limited["status"], "infeasible")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            problem, solver, output = root / "problem.json", root / "solver.json", root / "result.json"
            problem.write_text(json.dumps(diagnostic.to_dict()))
            solver.write_text(json.dumps(config().to_dict()))
            with redirect_stdout(StringIO()):
                self.assertEqual(cli_main(["solve", "--problem", str(problem), "--config", str(solver),
                                           "--output", str(output)]), 0)
            record = json.loads(output.read_text())
            self.assertEqual(record["mathematical_status"], "infeasible_within_declared_domain")
            self.assertEqual(record["backend_evidence"]["depth_contract"],
                             {"mode": "diagnostic_cap", "limit": 0, "certificate_reference": None})
        raw["depth_limit"] = 1
        feasible = ProblemSnapshot.from_dict(raw)
        self.assertEqual(solve_snapshot(feasible, config("flat"), time_limit_s=60)["key"],
                         (9, 3, 1, (("c", "C"),)))
        raw["depth_mode"] = "seed_derived"
        raw["depth_certificate_reference"] = "fixture:unverified-depth"
        seed_depth = ProblemSnapshot.from_dict(raw)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            problem, solver, output = root / "problem.json", root / "solver.json", root / "result.json"
            problem.write_text(json.dumps(seed_depth.to_dict()))
            solver.write_text(json.dumps(config().to_dict()))
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as errors:
                code = cli_main(["solve", "--problem", str(problem), "--config", str(solver),
                                 "--output", str(output)])
            self.assertEqual(code, 3)
            self.assertIn("unsupported_model", errors.getvalue())
            self.assertFalse(output.exists())

    def _c20_seed_case(self, method="flat"):
        raw = load_c01().to_dict()
        raw.pop("semantic_problem_id")
        raw.update({
            "origin": "o", "destination": "z", "departure_time_s": "0",
            "initial_energy_kwh": "2", "capacity_kwh": "5",
            "minimum_energy_kwh": "1", "destination_reserve_kwh": "1",
            "stop_overhead_s": "1", "stop_penalty_s": "1",
            "consumption_kwh_per_m": "1", "candidate_order": ["c"],
            "site_capabilities": {"c": ["C"]},
            "charging_curve": [["0", "5", "1", "0"]],
            "directed_edges": [
                {"source": "o", "target": "c", "time_s": "1", "length_m": "1", "edge_id": "oc"},
                {"source": "c", "target": "z", "time_s": "2", "length_m": "3", "edge_id": "cz"},
            ],
            "depth_mode": "seed_derived", "depth_limit": 4,
            "depth_certificate_reference": "fixture:c20-independent-seed-v1",
        })
        snapshot = ProblemSnapshot.from_dict(raw)
        seed_witness = {
            "schema": "hiroute.witness.v1",
            "actions": [["c", "C"]], "charges_kwh": ["3"],
            "route_legs": [
                {"source": "o", "target": "c", "time_s": "1", "actual_length_m": "1",
                 "edges": [{"source": "o", "target": "c", "edge_id": "oc", "time_s": "1", "length_m": "1"}]},
                {"source": "c", "target": "z", "time_s": "2", "actual_length_m": "3",
                 "edges": [{"source": "c", "target": "z", "edge_id": "cz", "time_s": "2", "length_m": "3"}]},
            ],
            "events": [
                {"effect": "D", "site": "c", "input_energy_kwh": "2", "input_time_s": "0", "output_energy_kwh": "1", "output_time_s": "1"},
                {"effect": "C", "site": "c", "input_energy_kwh": "1", "input_time_s": "1", "output_energy_kwh": "4", "output_time_s": "5"},
                {"effect": "D", "site": "z", "input_energy_kwh": "4", "input_time_s": "5", "output_energy_kwh": "1", "output_time_s": "7"},
            ],
        }
        certificate = {
            "schema": "hiroute.seed_depth_certificate.v1",
            "semantic_problem_id": snapshot.semantic_problem_id,
            "reference": snapshot.depth_certificate_reference,
            "plan": [["c", "C"]], "key": ["8", "3", 1, [["c", "C"]]],
            "witness": seed_witness, "h_min": "1", "lambda": "1",
            "U_J": "8", "H_max": 4,
        }
        solver = SolverConfig(method, "none", "bounded_time_cut_v2", "none", "none",
                              "verified_seed_certificate", "full_lexicographic_J_Q_H_Pi")
        return snapshot, solver, certificate

    def test_c20_seed_certificate_replayed_and_formula_depth_used_flat_hier(self):
        for method in ("flat", "hier"):
            with self.subTest(method=method):
                snapshot, solver, certificate = self._c20_seed_case(method)
                result = solve_snapshot(snapshot, solver, depth_certificate=certificate, time_limit_s=60)
                self.assertEqual(result["status"], "attained_optimum")
                self.assertEqual(result["key"], (8, 3, 1, (("c", "C"),)))
                self.assertEqual(result["replay"]["key"], result["key"])
                proof = result["depth_certificate"]
                self.assertEqual(proof["mode"], "seed_derived")
                self.assertEqual(proof["seed_key"], ["8", "3", 1, [["c", "C"]]])
                self.assertEqual(proof["per_stop_lower_bound"], "2")
                self.assertEqual(proof["first_excluded_depth"], 5)
                self.assertEqual(proof["first_excluded_lower_bound"], "10")
                self.assertTrue(proof["equality_depth_retained"])
                self.assertEqual(proof["incumbent_pruning"], False)
                if method == "hier":
                    self.assertEqual(result["hierarchy_metrics"]["max_depth"], 4)

    def test_c20_certificate_rejects_missing_mismatch_forgery_and_no_seed(self):
        snapshot, solver, certificate = self._c20_seed_case()
        mutations = []
        missing = copy.deepcopy(certificate); del missing["witness"]; mutations.append(missing)
        wrong_id = copy.deepcopy(certificate); wrong_id["semantic_problem_id"] = "0" * 64; mutations.append(wrong_id)
        wrong_u = copy.deepcopy(certificate); wrong_u["U_J"] = "7"; mutations.append(wrong_u)
        wrong_h = copy.deepcopy(certificate); wrong_h["H_max"] = 5; mutations.append(wrong_h)
        wrong_key = copy.deepcopy(certificate); wrong_key["key"][0] = "7"; mutations.append(wrong_key)
        wrong_witness = copy.deepcopy(certificate); wrong_witness["witness"]["events"][1]["output_time_s"] = "4"; mutations.append(wrong_witness)
        for bad in mutations:
            with self.subTest(bad=bad):
                with self.assertRaises((ValueError, TypeError)):
                    solve_snapshot(snapshot, solver, depth_certificate=bad, time_limit_s=60)
        with self.assertRaises(NotImplementedError):
            solve_snapshot(snapshot, config("flat"), depth_certificate=certificate)
        with self.assertRaises(ValueError):
            solve_snapshot(snapshot, solver)
        no_seed_policy = SolverConfig("flat", "none", "bounded_time_cut_v2", "none", "none",
                                      "none", "full_lexicographic_J_Q_H_Pi")
        with self.assertRaises(NotImplementedError):
            solve_snapshot(snapshot, no_seed_policy, depth_certificate=certificate)

    def test_c20_cli_requires_certificate_and_emits_verified_bound(self):
        snapshot, solver, certificate = self._c20_seed_case()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            problem, config_path, cert_path, output = (root / "problem.json", root / "solver.json",
                                                        root / "seed.json", root / "result.json")
            problem.write_text(json.dumps(snapshot.to_dict()))
            config_path.write_text(json.dumps(solver.to_dict()))
            cert_path.write_text(json.dumps(certificate))
            with redirect_stdout(StringIO()):
                code = cli_main(["solve", "--problem", str(problem), "--config", str(config_path),
                                 "--depth-certificate", str(cert_path),
                                 "--output", str(output), "--time-limit-s", "60"])
            self.assertEqual(code, 0)
            record = json.loads(output.read_text())
            self.assertEqual(record["mathematical_status"], "attained_optimum")
            self.assertEqual(record["backend_evidence"]["depth_contract"]["mode"], "seed_derived")
            self.assertEqual(record["backend_evidence"]["depth_contract"]["limit"], 4)
            self.assertEqual(record["backend_evidence"]["depth_contract"]["first_excluded_lower_bound"], "10")

    def test_unreachable_is_within_domain_infeasibility(self):
        raw = load_c01().to_dict()
        raw.pop("semantic_problem_id")
        raw["directed_edges"] = []
        snapshot = ProblemSnapshot.from_dict(raw)
        self.assertEqual(config().seed_policy, "none")
        for method in ("flat", "hier"):
            result = solve_snapshot(snapshot, config(method))
            self.assertEqual(result["status"], "infeasible")
            self.assertEqual(result["domains"], 0)


if __name__ == "__main__":
    unittest.main()
