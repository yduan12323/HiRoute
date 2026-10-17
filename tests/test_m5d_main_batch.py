"""Durable whole-unit status and stopping rules without numerical work."""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from scripts.m5d_main_batch import run, completed_pair_agrees
from scripts.m5d_main_row import exact_outcome, DurableLayerReplay
from scripts.m5d_freeze_main_phase import run as freeze_main
from timecut5.probe import TerminalResult
from fractions import Fraction
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
                cpu_usage_ns=601000000000, receipt_path=str(root / "receipt.json"),
                cpu_quota_percent=100)
            with patch("scripts.m5d_main_batch.run_m5d_phase", return_value=receipt) as launch:
                final = run(root, root, root, root, phase_path, output)
            launch.assert_called_once()
            self.assertEqual(final["rows"][rows[-1]["row_id"]]["status"], "time_limit")
            self.assertEqual(final["charged_cpu_ns"], receipt.cpu_usage_ns)
            self.assertEqual(len(final["rows"]), 192)
            self.assertTrue(final["stopped"])
            self.assertTrue(_group_empty(""))

    def test_exact_terminal_coordinates_and_seed_contradiction(self):
        witness = object()
        attained = exact_outcome(TerminalResult("attained_optimum",
            key=(Fraction(3, 2), Fraction(1, 3), 1, (("s1", "C"),)),
            witness=witness))
        primary = exact_outcome(TerminalResult("infimum_unattained",
            primary_infimum=Fraction(3, 2), unattained_component="J"))
        secondary = exact_outcome(TerminalResult("infimum_unattained",
            primary_infimum=Fraction(3, 2), secondary_infimum=Fraction(1, 3),
            unattained_component="Q"))
        self.assertEqual(attained["Pi"], [["s1", "C"]])
        self.assertEqual((primary["J"], primary["Q"], primary["J_attained"]),
                         ("3/2", None, False))
        self.assertEqual((secondary["J"], secondary["Q"], secondary["Q_attained"]),
                         ("3/2", "1/3", False))
        with self.assertRaisesRegex(ValueError, "Certified seed"):
            exact_outcome(TerminalResult("infeasible"))

    def test_completed_methods_must_agree_on_status_and_defined_coordinates(self):
        base = {"seed_j": "4", "certified_depth": 2, "prewarm_sha256": "a" * 64,
                "exact_outcome": {"status": "infimum_unattained_J", "J": "3/2",
                    "Q": None, "H": None, "Pi": None,
                    "J_attained": False, "Q_attained": None}}
        self.assertTrue(completed_pair_agrees(base, dict(base)))
        for changed in ({"status": "infimum_unattained_Q"}, {"J": "4/3"},
                        {"Q": "1/3"}, {"J_attained": True}):
            other = dict(base, exact_outcome=dict(base["exact_outcome"], **changed))
            self.assertFalse(completed_pair_agrees(base, other))
        self.assertIsNone(completed_pair_agrees(base, {"status": "time_limit"}))

    def test_durable_layer_checkpoint_is_source_bound(self):
        external = {name: "a" * 64 for name in
            ("graph_nodes", "graph_edges", "router", "anchors", "sites",
             "query", "hierarchy", "landmark", "seed", "policy", "runtime")}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "layer.json"
            hook = DurableLayerReplay(path, mode="flat", domain_sha256="b" * 64,
                external_source_sha256=external)
            hook(0, ("open",), (), Fraction(3), (0, 1, 1))
            saved = path.read_bytes()
            restored = DurableLayerReplay(Path(directory) / "continued.json",
                mode="flat", domain_sha256="b" * 64,
                external_source_sha256=external, previous_checkpoint=saved)
            restored(0, ("open",), (), Fraction(3), (0, 1, 1))
            restored.finish()
            self.assertEqual(restored.replay.replayed_restore_layers, 1)
            with self.assertRaisesRegex(ValueError, "source or sequence"):
                DurableLayerReplay(Path(directory) / "bad.json", mode="flat",
                    domain_sha256="c" * 64, external_source_sha256=external,
                    previous_checkpoint=saved)

    def test_freeze_rejects_shared_non_48_query_count(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = [root / f"input{i}.json" for i in range(4)]
            for path, value in zip(paths,
                    ({"query_count": 49}, {"query_count": 49}, {}, {})):
                path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "Fixed main query"):
                freeze_main(root, *paths, 10.0, root / "frozen.json")

    def test_completed_method_disagreement_stops_remaining_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "out"
            output.mkdir()
            rows = ([{"row_id": f"old_{i:03d}_flat", "method": "flat"}
                     for i in range(189)] +
                    [{"row_id": "case_flat", "method": "flat"},
                     {"row_id": "case_hier", "method": "hier"},
                     {"row_id": "later_flat", "method": "flat"}])
            phase = {"schema": "hiroute.m5d.frozen_main_phase.v1", "rows": rows,
                "wall_seconds": 600, "memory_bytes": 8 * 1024**3,
                "main_cpu_seconds_ceiling": 117000, "max_concurrent_rows": 2,
                "initial_concurrency": 1, "conservative_cpu_hours_before_main": 10.5,
                "outside_main_reserve_seconds": 18000}
            path = root / "phase.json"
            path.write_text(json.dumps(phase))
            import hashlib
            (output / "state.json").write_text(json.dumps({
                "schema": "hiroute.m5d.main_batch_state.v1",
                "phase_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "charged_cpu_ns": 0, "stopped": False,
                "rows": {row["row_id"]: {"status": "time_limit"}
                         for row in rows[:189]}}))
            receipt = SimpleNamespace(result="success", exit_status=0,
                cpu_usage_ns=10**9, receipt_path=str(root / "receipt.json"),
                cpu_quota_percent=100)
            call = 0
            def launch(*args, **kwargs):
                nonlocal call
                call += 1
                value = {"status": "attained_optimum", "J": str(call), "Q": "0",
                    "H": 0, "Pi": [], "J_attained": True, "Q_attained": True}
                (kwargs["output_dir"] / "status.json").write_text(json.dumps({
                    "status": "attained_optimum", "exact_outcome": value,
                    "seed_j": "4", "certified_depth": 2,
                    "prewarm_sha256": "a" * 64}))
                return receipt
            with patch("scripts.m5d_main_batch.run_m5d_phase", side_effect=launch):
                final = run(root, root, root, root, path, output)
            self.assertEqual(call, 2)
            self.assertEqual(final["rows"]["case_flat"]["status"],
                             "verification_failed_method_disagreement")
            self.assertEqual(final["rows"]["case_hier"]["status"],
                             "verification_failed_method_disagreement")
            self.assertEqual(final["rows"]["later_flat"]["status"],
                             "verification_blocked_unrun")


if __name__ == "__main__":
    unittest.main()
