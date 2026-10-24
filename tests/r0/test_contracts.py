import json
from pathlib import Path
import unittest

from hiroute.contracts import ProblemSnapshot, SolverConfig, SolveResult, Witness

ROOT = Path(__file__).resolve().parents[2]


class ContractTests(unittest.TestCase):
    def test_c01_snapshot_has_stable_semantic_identity(self):
        raw = json.loads((ROOT / "tests/r0/c01_zero_stop_snapshot.json").read_text())
        snapshot = ProblemSnapshot.from_dict(raw)
        round_trip = ProblemSnapshot.from_dict(snapshot.to_dict())
        self.assertEqual(snapshot.semantic_problem_id, round_trip.semantic_problem_id)
        self.assertEqual(snapshot.candidate_order, ())

    def test_snapshot_rejects_binary64_and_identity_mismatch(self):
        raw = json.loads((ROOT / "tests/r0/c01_zero_stop_snapshot.json").read_text())
        raw["departure_time_s"] = 0.0
        with self.assertRaises(TypeError):
            ProblemSnapshot.from_dict(raw)
        raw = json.loads((ROOT / "tests/r0/c01_zero_stop_snapshot.json").read_text())
        raw["semantic_problem_id"] = "0" * 64
        with self.assertRaises(ValueError):
            ProblemSnapshot.from_dict(raw)

    def test_snapshot_defensively_freezes_nested_input_mappings(self):
        raw = json.loads((ROOT / "tests/r0/c01_zero_stop_snapshot.json").read_text())
        raw["schedule"] = {"a": "0", "b": "2", "D": "1"}
        raw["candidate_order"] = ["c"]
        raw["site_capabilities"] = {"c": ["C"]}
        raw["directed_edges"] = [{"source": "o", "target": "z", "time_s": "1", "length_m": "1"}]
        snapshot = ProblemSnapshot.from_dict(raw)
        identity = snapshot.semantic_problem_id
        raw["schedule"]["a"] = "1"
        raw["site_capabilities"]["c"].append("S")
        raw["directed_edges"][0]["time_s"] = "99"
        self.assertEqual(snapshot.semantic_problem_id, identity)
        self.assertEqual(snapshot.to_dict()["directed_edges"][0]["time_s"], "1")
        with self.assertRaises(TypeError):
            snapshot.schedule["a"] = "1"
        with self.assertRaises(TypeError):
            snapshot.directed_edges[0]["time_s"] = "2"
        with self.assertRaises(AttributeError):
            snapshot.site_capabilities["c"].append("S")

    def test_solve_result_rejects_inconsistent_status_key_and_verification(self):
        common = dict(semantic_problem_id="p", representation_id="r", build_id="b", run_id="c")
        with self.assertRaisesRegex(ValueError, "Non-completed"):
            SolveResult("time_limit", "attained_optimum", "not_run", **common)
        with self.assertRaisesRegex(ValueError, "key must contain"):
            SolveResult("completed", "attained_optimum", "not_run", key=("1", "0", 0), **common)
        with self.assertRaisesRegex(ValueError, "Only an attained"):
            SolveResult("completed", "primary_unattained", "not_run", key=("1", "0", 0, ()),
                        primary_infimum="1", **common)
        with self.assertRaisesRegex(ValueError, "witness_verified"):
            SolveResult("completed", "unknown", "witness_verified", **common)
        with self.assertRaisesRegex(ValueError, "Failed verification"):
            SolveResult("completed", "attained_optimum", "failed", key=("1", "0", 0, ()), **common)
        self.assertEqual(
            SolveResult("completed", "unknown", "failed", **common).verification_status,
            "failed",
        )
        with self.assertRaisesRegex(ValueError, "nonnegative integer"):
            SolveResult("completed", "attained_optimum", "not_run",
                        key=("1", "0", True, (("s", "C"),)), **common)

    def test_solve_result_rejects_status_incompatible_coordinates(self):
        common = dict(semantic_problem_id="p", representation_id="r", build_id="b", run_id="c")
        valid_key = ("5", "1", 1, (("c", "C"),))
        invalid_rows = [
            ("time_limit", "attained_optimum", (), {}),
            ("time_limit", "attained_optimum", (valid_key,), {}),
            ("completed", "primary_unattained", (), {"primary_infimum": "1", "key": valid_key}),
            ("completed", "primary_unattained", (), {"primary_infimum": "1", "secondary_infimum": "0"}),
            ("completed", "secondary_unattained", (), {"secondary_infimum": "0", "key": valid_key}),
            ("completed", "infeasible_within_declared_domain", (), {"key": valid_key}),
        ]
        for execution, mathematical, args, kwargs in invalid_rows:
            with self.subTest(execution=execution, mathematical=mathematical, kwargs=kwargs):
                key = kwargs.pop("key", None)
                with self.assertRaises(ValueError):
                    SolveResult(execution, mathematical, "not_run", key=key, **common, **kwargs)
        with self.assertRaisesRegex(ValueError, "Key H"):
            SolveResult("completed", "attained_optimum", "not_run",
                        key=("5", "1", 0, (("c", "C"),)), **common)
        with self.assertRaisesRegex(ValueError, "unsupported Site action"):
            SolveResult("completed", "attained_optimum", "not_run",
                        key=("5", "1", 1, (("c", "X"),)), **common)
        witness = Witness(actions=(("other", "C"),), charges_kwh=("1",), route_legs=(), events=())
        with self.assertRaisesRegex(ValueError, "match"):
            SolveResult("completed", "attained_optimum", "witness_verified",
                        key=("5", "1", 1, (("c", "C"),)), witness=witness, **common)

    def test_result_evidence_is_detached_and_read_only(self):
        common = dict(semantic_problem_id="p", representation_id="r", build_id="b", run_id="c")
        source = {"nested": {"x": 1}}
        result = SolveResult("completed", "unknown", "not_run", backend_evidence=source, **common)
        source["later"] = 2
        self.assertNotIn("later", result.backend_evidence)
        with self.assertRaises(TypeError):
            result.backend_evidence["later"] = 2
        exported = result.to_dict()
        exported["backend_evidence"]["later"] = 2
        self.assertNotIn("later", result.backend_evidence)

    def test_solver_config_is_explicit_and_typed(self):
        raw = json.loads((ROOT / "configs/rebuild/r1_flat.json").read_text())
        config = SolverConfig.from_dict(raw)
        self.assertEqual(config.method, "flat")
        raw["method"] = "automatic"
        with self.assertRaises(ValueError):
            SolverConfig.from_dict(raw)


if __name__ == "__main__":
    unittest.main()
