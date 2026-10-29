"""Executable R0 checks for C20-C24 status and observation semantics."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from hiroute.contracts import ProblemSnapshot, SolveResult, Witness
from timecut5.hierarchy import solve_hierarchical
from timecut5.invocation_trace import InvocationTrace
from timecut5.provenance import Recorder

SPECS = json.loads((ROOT / "tests/r0/fixtures/c18_c20_c24_expected.json").read_text())


def snapshot_raw():
    return json.loads((ROOT / "tests/r0/c01_zero_stop_snapshot.json").read_text())


def run_observed(case, profile):
    if profile == "off":
        return solve_hierarchical(case), None
    with Recorder() as recorder, InvocationTrace(recorder) as trace:
        result = solve_hierarchical(case)
        if profile == "metrics":
            observation = {"invocations": trace.invocations, "groups": trace.groups,
                           "coalescings": trace.coalescings, "events": len(trace.events)}
        elif profile == "detailed_trace":
            observation = trace.export()
        else:
            raise AssertionError("unknown observation profile")
    return result, observation


class RemainingFixtureTests(unittest.TestCase):
    def test_c20_depth_modes_have_separate_contract_admission(self):
        raw = snapshot_raw()
        diagnostic = dict(raw, depth_mode="diagnostic_cap", depth_limit=1,
                          depth_certificate_reference=None)
        self.assertEqual(ProblemSnapshot.from_dict(diagnostic).depth_mode, "diagnostic_cap")
        seed_without_certificate = dict(raw, depth_mode="seed_derived", depth_limit=1,
                                        depth_certificate_reference=None)
        with self.assertRaisesRegex(ValueError, "requires a certificate reference"):
            ProblemSnapshot.from_dict(seed_without_certificate)
        seed_with_reference = dict(raw, depth_mode="seed_derived", depth_limit=1,
                                   depth_certificate_reference="fixture:seed-certificate")
        accepted = ProblemSnapshot.from_dict(seed_with_reference)
        self.assertEqual(accepted.depth_mode, "seed_derived")
        self.assertEqual(accepted.depth_certificate_reference, "fixture:seed-certificate")
        self.assertFalse(SPECS["C20"]["depth_modes"][2]["certificate_contents_verified"])

    def test_c21_no_seed_is_unknown_not_infeasible(self):
        row = SPECS["C21"]["no_seed"]
        result = SolveResult(row["execution_status"], row["mathematical_status"],
                             "not_run", "p", "r", "b", "c")
        self.assertEqual((result.execution_status, result.mathematical_status),
                         ("completed", "unknown"))
        self.assertIsNone(result.key)
        self.assertNotEqual(result.mathematical_status, "infeasible_within_declared_domain")

    def test_c22_bad_input_and_unsupported_model_do_not_claim_infeasibility(self):
        malformed = snapshot_raw()
        malformed["semantic_problem_id"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "does not match"):
            ProblemSnapshot.from_dict(malformed)
        missing = snapshot_raw()
        del missing["origin"]
        with self.assertRaisesRegex(ValueError, "exactly match"):
            ProblemSnapshot.from_dict(missing)
        unsupported = dict(snapshot_raw(), model_contract_id="fixture:unsupported-model")
        parsed = ProblemSnapshot.from_dict(unsupported)
        result = SolveResult("unsupported_model", "unknown", "not_run",
                             parsed.semantic_problem_id, "r", "b", "c")
        self.assertEqual(result.execution_status, "unsupported_model")
        self.assertEqual(result.mathematical_status, "unknown")
        self.assertIsNone(result.key)

    def test_c23_timeout_preserves_feasible_incumbent_without_optimum_key(self):
        row = SPECS["C23"]["timeout"]
        raw = row["witness"]
        witness = Witness(tuple(map(tuple, raw["actions"])), tuple(raw["charges_kwh"]),
                          tuple(raw["route_legs"]), tuple(raw["events"]))
        result = SolveResult(row["execution_status"], row["mathematical_status"],
                             row["verification_status"], "p", "r", "b", "c",
                             key=row["key"], witness=witness, backend=row["backend"])
        encoded = result.to_dict()
        self.assertEqual(encoded["execution_status"], "time_limit")
        self.assertEqual(encoded["mathematical_status"], "unknown")
        self.assertEqual(encoded["verification_status"], "witness_verified")
        self.assertIsNone(encoded["key"])
        self.assertEqual(encoded["witness"]["charges_kwh"], ["1"])

    def test_c24_observation_profiles_do_not_change_solver_result(self):
        case = json.loads((ROOT / "tests/fixtures/invocation_trace_pilot_v1.json").read_text())
        profiles = SPECS["C24"]["observation_profiles"]
        results = {}
        observations = {}
        for profile in profiles:
            with self.subTest(profile=profile):
                result, observation = run_observed(case, profile)
                results[profile] = result.canonical()
                observations[profile] = observation
        self.assertEqual(results["off"], results["metrics"])
        self.assertEqual(results["off"], results["detailed_trace"])
        self.assertGreater(observations["metrics"]["events"], 0)
        self.assertGreater(len(observations["detailed_trace"]["events"]), 0)
        expected = SPECS["C24"]["expected_key"]
        self.assertEqual(
            results["off"]["result"]["lex_key"],
            (int(expected[0]), int(expected[1]), expected[2],
             tuple(tuple(action) for action in expected[3])),
        )
        self.assertTrue(results["off"]["result"]["witness_replayed"])
        for profile in profiles:
            self.assertEqual(results[profile]["result"]["lex_key"], results["off"]["result"]["lex_key"])
            self.assertEqual(results[profile]["result"]["witness_replayed"], True)


if __name__ == "__main__":
    unittest.main()

