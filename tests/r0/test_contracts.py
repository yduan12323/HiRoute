import json
from pathlib import Path
import unittest

from hiroute.contracts import ProblemSnapshot, SolverConfig

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

    def test_solver_config_is_explicit_and_typed(self):
        raw = json.loads((ROOT / "configs/rebuild/r1_flat.json").read_text())
        config = SolverConfig.from_dict(raw)
        self.assertEqual(config.method, "flat")
        raw["method"] = "automatic"
        with self.assertRaises(ValueError):
            SolverConfig.from_dict(raw)


if __name__ == "__main__":
    unittest.main()
