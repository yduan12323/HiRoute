"""Black-box checks for the installed HiRoute exact-core CLI."""
import json
from pathlib import Path
import tempfile
import unittest

from hiroute.cli import main

ROOT = Path(__file__).resolve().parents[2]


class ExactCoreCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="hiroute-cli-")
        self.root = Path(self.tmp.name)
        self.problem = self.root / "problem.json"
        self.config = ROOT / "configs/rebuild/r1_flat.json"
        self.output = self.root / "result.json"
        snapshot = json.loads((ROOT / "tests/r0/c01_zero_stop_snapshot.json").read_text())
        snapshot.pop("semantic_problem_id", None)
        self.problem.write_text(json.dumps(snapshot))

    def tearDown(self):
        self.tmp.cleanup()

    def invoke(self):
        return main(["solve", "--problem", str(self.problem), "--config", str(self.config),
                     "--output", str(self.output)])

    def test_exact_cli_computes_missing_problem_identity(self):
        self.assertEqual(self.invoke(), 0)
        result = json.loads(self.output.read_text())
        self.assertEqual(result["execution_status"], "completed")
        self.assertEqual(result["mathematical_status"], "attained_optimum")
        self.assertEqual(result["key"], ["1", "0", 0, []])
        self.assertTrue(result["semantic_problem_id"])

    def test_caller_identity_is_not_a_manual_gate(self):
        snapshot = json.loads(self.problem.read_text())
        snapshot["semantic_problem_id"] = "0" * 64
        self.problem.write_text(json.dumps(snapshot))
        self.assertEqual(self.invoke(), 0)
        result = json.loads(self.output.read_text())
        self.assertNotEqual(result["semantic_problem_id"], "0" * 64)

    def test_invalid_physical_input_is_still_rejected(self):
        snapshot = json.loads(self.problem.read_text())
        snapshot["initial_energy_kwh"] = "-1"
        self.problem.write_text(json.dumps(snapshot))
        self.assertEqual(self.invoke(), 2)
        self.assertFalse(self.output.exists())

    def test_existing_output_is_not_overwritten(self):
        self.assertEqual(self.invoke(), 0)
        original = self.output.read_bytes()
        self.assertEqual(self.invoke(), 4)
        self.assertEqual(self.output.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
