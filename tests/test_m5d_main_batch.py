"""Durable whole-unit status and stopping rules without numerical work."""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from scripts.m5d_main_batch import run
from timecut5.systemd_supervisor import _group_empty


class MainBatchTest(unittest.TestCase):
    def test_timeout_stays_in_fixed_denominator_and_empty_group(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            phase_path, output = root / "phase.json", root / "out"
            output.mkdir()
            rows = [{"row_id": f"case_{i:03d}_flat", "method": "flat"}
                    for i in range(192)]
            phase = {"schema": "hiroute.m5d.frozen_main_phase.v1",
                "rows": rows, "wall_seconds": 600,
                "memory_bytes": 8 * 1024**3,
                "main_cpu_seconds_ceiling": 117000,
                "max_concurrent_rows": 2, "initial_concurrency": 1,
                "conservative_cpu_hours_before_main": 10.531416,
                "outside_main_reserve_seconds": 17886.9024}
            phase_path.write_text(json.dumps(phase))
            import hashlib
            initial = {"schema": "hiroute.m5d.main_batch_state.v1",
                "phase_sha256": hashlib.sha256(phase_path.read_bytes()).hexdigest(),
                "charged_cpu_ns": 0, "rows": {
                    row["row_id"]: {"status": "time_limit", "denominator_included": True}
                    for row in rows[:-1]}, "stopped": False}
            (output / "state.json").write_text(json.dumps(initial))
            receipt = SimpleNamespace(result="timeout", exit_status=15,
                cpu_usage_ns=601000000000, receipt_path=str(root / "receipt.json"))
            with patch("scripts.m5d_main_batch.run_m5d_phase", return_value=receipt) as launch:
                final = run(root, root, root, root, phase_path, output)
            launch.assert_called_once()
            self.assertEqual(final["rows"][rows[-1]["row_id"]]["status"], "time_limit")
            self.assertEqual(final["charged_cpu_ns"], receipt.cpu_usage_ns)
            self.assertEqual(len(final["rows"]), 192)
            self.assertTrue(final["stopped"])
            self.assertTrue(_group_empty(""))


if __name__ == "__main__":
    unittest.main()
