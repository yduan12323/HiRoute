"""Black-box dispatch checks against the installed hiroute executable.

Run with HIROUTE_TEST_CLI pointing at the non-editable wheel console script and
with PYTHONPATH unset. The accepted tiny case intentionally exercises the
separate legacy adapter; unsupported mutations must be rejected before it runs.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from hiroute.contracts import ProblemSnapshot

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.environ.get("HIROUTE_TEST_CLI"), "requires installed wheel CLI")
class InstalledDispatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="hiroute-cli-matrix-")
        cls.root = Path(cls.tmp.name)
        cls.cli = os.environ["HIROUTE_TEST_CLI"]
        cls.adapter = ROOT / "migration/legacy_bounded_adapter.py"
        cls.legacy = ROOT / "src"
        cls.config = ROOT / "configs/rebuild/r1_flat.json"
        raw = json.loads((ROOT / "tests/r0/c01_zero_stop_snapshot.json").read_text())
        cls.base = ProblemSnapshot.from_dict(raw).to_dict()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def invoke(self, snapshot, config=None):
        problem = self.root / "problem.json"
        config_path = self.root / "config.json"
        output = self.root / f"result-{self.id().split('.')[-1]}.json"
        output.unlink(missing_ok=True)
        problem.write_text(json.dumps(snapshot))
        config_path.write_text(json.dumps(config or json.loads(self.config.read_text())))
        return subprocess.run([
            self.cli, "solve", "--problem", str(problem), "--config", str(config_path),
            "--backend", "legacy_migration_adapter", "--adapter-script", str(self.adapter),
            "--adapter-python", os.sys.executable, "--adapter-source-root", str(self.legacy),
            "--output", str(output)], text=True, capture_output=True), output

    def recanonicalize(self, mutation):
        value = dict(self.base)
        value.pop("semantic_problem_id", None)
        value.update(mutation)
        return ProblemSnapshot.from_dict(value).to_dict()

    def test_supported_snapshot_reaches_installed_adapter_and_validated_result(self):
        completed, output = self.invoke(self.base)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(output.read_text())
        self.assertEqual(result["execution_status"], "completed")
        self.assertEqual(result["mathematical_status"], "attained_optimum")
        self.assertEqual(len(result["key"]), 4)

    def test_unknown_model_is_rejected_as_unsupported_before_adapter(self):
        completed, output = self.invoke(self.recanonicalize({"model_contract_id": "future:model"}))
        self.assertEqual(completed.returncode, 3, completed.stderr)
        self.assertIn("unsupported_model", completed.stderr)
        self.assertFalse(output.exists())

    def test_unknown_numerical_and_leg_contracts_are_rejected(self):
        for field in ("numerical_contract_id", "selected_leg_contract"):
            with self.subTest(field=field):
                completed, output = self.invoke(self.recanonicalize({field: "future:contract"}))
                self.assertEqual(completed.returncode, 3, completed.stderr)
                self.assertIn("unsupported_model", completed.stderr)
                self.assertFalse(output.exists())

    def test_missing_semantic_id_is_rejected_instead_of_recomputed(self):
        snapshot = dict(self.base)
        snapshot.pop("semantic_problem_id")
        completed, output = self.invoke(snapshot)
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertIn("must include semantic_problem_id", completed.stderr)
        self.assertFalse(output.exists())

    def test_unknown_solver_profile_is_rejected_before_adapter(self):
        config = json.loads(self.config.read_text())
        config["coalescing_profile"] = "future_coalescing"
        completed, output = self.invoke(self.base, config)
        self.assertEqual(completed.returncode, 3, completed.stderr)
        self.assertIn("unsupported solver profile", completed.stderr)
        self.assertFalse(output.exists())

    def test_seed_derived_depth_is_rejected_before_adapter(self):
        snapshot = self.recanonicalize({
            "depth_mode": "seed_derived",
            "depth_certificate_reference": "fixture:seed-cert",
        })
        completed, output = self.invoke(snapshot)
        self.assertEqual(completed.returncode, 3, completed.stderr)
        self.assertIn("unsupported_model", completed.stderr)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
