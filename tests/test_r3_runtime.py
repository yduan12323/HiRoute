import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import redirect_stdout
from io import StringIO
import time
import sys

from hiroute.runtime import run_supervised

from hiroute.cli import _atomic_new_file, _native_result, main as cli_main
from hiroute.contracts import ProblemSnapshot, SolverConfig
from hiroute.exact.search import solve_snapshot


def base_snapshot():
    raw = json.loads((Path(__file__).parent / "r0/c01_zero_stop_snapshot.json").read_text())
    raw.pop("semantic_problem_id", None)
    raw["candidate_order"] = []
    raw["site_capabilities"] = {}
    raw["depth_limit"] = 0
    return ProblemSnapshot.from_dict(raw)


def config(method="flat"):
    return SolverConfig(method, "none", "bounded_time_cut_v2", "none", "none", "none",
                        "full_lexicographic_J_Q_H_Pi")


class TestR3Runtime(unittest.TestCase):
    def test_supervisor_receipt_records_process_group_vmsize_peak(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / "run.json"
            result = run_supervised(
                [sys.executable, "-c", "import time; x = bytearray(1024 * 1024); time.sleep(0.15)"],
                timeout_s=5,
                memory_poll_s=0.01,
                receipt_path=receipt,
                run_identity={"purpose": "bounded-vmsize-sampler-test"},
            )
            self.assertEqual(result.returncode, 0)
            self.assertGreater(result.vm_size_peak_bytes, 0)
            record = json.loads(receipt.read_text())
            self.assertEqual(record["vm_size_peak_bytes"], result.vm_size_peak_bytes)
            self.assertEqual(record["run_identity"]["purpose"], "bounded-vmsize-sampler-test")
    def test_deadline_retains_verified_incumbent_without_claiming_optimality(self):
        snapshot = base_snapshot()
        ticks = iter((0.0, 0.0, 0.0, 2.0, 3.0))
        solved = solve_snapshot(snapshot, config(), time_limit_s=1.0,
                                _clock=lambda: next(ticks))
        self.assertEqual(solved["status"], "time_limit")
        self.assertIsNotNone(solved["incumbent"])
        self.assertEqual(solved["incumbent"]["key"], (1, 0, 0, ()))
        record = _native_result(snapshot, config(), solved)
        self.assertEqual(record["execution_status"], "time_limit")
        self.assertEqual(record["mathematical_status"], "unknown")
        self.assertIsNone(record["key"])
        self.assertEqual(record["verification_status"], "witness_verified")
        self.assertEqual(record["backend_evidence"]["incumbent"]["label"],
                         "feasible_incumbent_not_optimality_claim")
        self.assertEqual(record["witness"]["actions"], [])

    def test_c21_no_seed_timeout_remains_unknown_not_infeasible(self):
        snapshot = base_snapshot()
        self.assertEqual(config().seed_policy, "none")
        ticks=iter((0.0, 0.0, 0.2, 0.3))
        solved=solve_snapshot(snapshot,config(),time_limit_s=0.1,
                              _clock=lambda: next(ticks))
        self.assertEqual(solved["status"],"time_limit")
        self.assertIsNone(solved["incumbent"])
        record=_native_result(snapshot,config(),solved)
        self.assertEqual(record["execution_status"],"time_limit")
        self.assertEqual(record["mathematical_status"],"unknown")
        self.assertIsNone(record["key"])

    def test_wall_deadline_after_attained_plan_retains_incumbent(self):
        snapshot = base_snapshot()
        from hiroute.exact import search
        real_terminal = search.terminal_optimize
        def delayed_terminal(*args, **kwargs):
            result = real_terminal(*args, **kwargs)
            time.sleep(0.02)  # test workload crosses the real monotonic deadline
            return result
        with patch("hiroute.exact.search.terminal_optimize", side_effect=delayed_terminal):
            solved = solve_snapshot(snapshot, config(), time_limit_s=0.005)
        self.assertEqual(solved["status"], "time_limit")
        self.assertGreaterEqual(solved["elapsed_s"], 0.005)
        self.assertEqual(solved["incumbent"]["key"], (1, 0, 0, ()))
        self.assertEqual(solved["incumbent"]["replay"]["key"], (1, 0, 0, ()))
        record = _native_result(snapshot, config(), solved)
        self.assertEqual(record["mathematical_status"], "unknown")
        self.assertEqual(record["verification_status"], "witness_verified")
        self.assertIsNone(record["key"])
        self.assertEqual(record["backend_evidence"]["incumbent"]["key"], ["1", "0", 0, ()])

    def test_observer_profiles_do_not_change_math_key_or_witness(self):
        snapshot = base_snapshot()
        off = solve_snapshot(snapshot, config(), observer="off")
        metrics = solve_snapshot(snapshot, config(), observer="metrics")
        trace = solve_snapshot(snapshot, config(), observer="detailed_trace")
        for other in (metrics, trace):
            self.assertEqual(other["key"], off["key"])
            self.assertEqual(other["replay"]["key"], off["replay"]["key"])
            self.assertEqual(other["replay"]["trace"], off["replay"]["trace"])
            self.assertEqual(other["plan"], off["plan"])
        self.assertIsNone(off["observer"])
        self.assertEqual(metrics["observer"]["plans_evaluated"], 1)
        self.assertEqual(metrics["observer"]["trace"], None)
        self.assertEqual(len(trace["observer"]["trace"]), 1)

    def test_atomic_writer_cleans_temp_if_publication_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "result.json"
            with patch("hiroute.cli.os.link", side_effect=OSError("injected publish fault")):
                with self.assertRaisesRegex(OSError, "injected"):
                    _atomic_new_file(target, b"result")
            self.assertFalse(target.exists())
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_atomic_writer_never_replaces_existing_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "result.json"
            target.write_bytes(b"old")
            with self.assertRaises(FileExistsError):
                _atomic_new_file(target, b"new")
            self.assertEqual(target.read_bytes(), b"old")
            self.assertEqual([x.name for x in Path(tmp).iterdir()], ["result.json"])

    def test_installed_cli_observer_emits_same_full_key(self):
        snapshot = base_snapshot()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            problem, solver = root / "problem.json", root / "solver.json"
            out_off, out_trace = root / "off.json", root / "trace.json"
            problem.write_text(json.dumps(snapshot.to_dict()))
            solver.write_text(json.dumps(config().to_dict()))
            for output, observer in ((out_off, "off"), (out_trace, "detailed_trace")):
                with redirect_stdout(StringIO()):
                    self.assertEqual(cli_main(["solve", "--problem", str(problem),
                        "--config", str(solver), "--backend", "exact_core_search",
                        "--observer", observer, "--output", str(output)]), 0)
            a, b = json.loads(out_off.read_text()), json.loads(out_trace.read_text())
            self.assertEqual(a["key"], b["key"])
            self.assertEqual(a["witness"], b["witness"])
            self.assertEqual(b["backend_evidence"]["observer"]["profile"], "detailed_trace")
            self.assertEqual(len(b["backend_evidence"]["observer"]["trace"]), 1)


if __name__ == "__main__":
    unittest.main()
