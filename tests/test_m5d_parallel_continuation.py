"""Synthetic admission and 4-to-5 ramp checks; no numerical row is launched."""
from concurrent.futures import Future
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import m5d_parallel_continuation as parallel
from timecut5.systemd_supervisor import ResourceReceipt


GiB = 1024 ** 3


class ParallelContinuationTest(unittest.TestCase):
    def test_memavailable_is_read_as_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "meminfo"
            path.write_text("MemTotal: 1024 kB\nMemAvailable: 42 kB\n")
            self.assertEqual(parallel.mem_available_bytes(path), 42 * 1024)

    def test_worst_case_memory_includes_each_active_cgroup_growth_and_reserve(self):
        all_empty = parallel.memory_admission(48 * GiB, [0, 0, 0, 0])
        self.assertEqual(all_empty["required_mem_available_bytes"], 48 * GiB)
        self.assertTrue(all_empty["admitted"])
        self.assertFalse(parallel.memory_admission(48 * GiB - 1, [0, 0, 0, 0])["admitted"])

        half_full = parallel.memory_admission(32 * GiB, [4 * GiB] * 4)
        self.assertEqual(half_full["active_remaining_to_cap_bytes"], [4 * GiB] * 4)
        self.assertEqual(half_full["required_mem_available_bytes"], 32 * GiB)
        self.assertTrue(half_full["admitted"])

    def test_budget_admission_keeps_row_and_host_guards(self):
        exact = parallel.budget_admission(
            110900 * 10**9, 10, 700, 40 * 10**9)
        self.assertEqual(exact["cgroup_required_ns"], 117000 * 10**9)
        self.assertEqual(exact["outside_required_ns"], 660 * 10**9)
        self.assertTrue(exact["admitted"])
        self.assertFalse(parallel.budget_admission(
            110901 * 10**9, 10, 700, 40 * 10**9)["admitted"])
        self.assertFalse(parallel.budget_admission(
            110900 * 10**9, 10, 659.999999, 0)["admitted"])

    def test_ramp_uses_receipts_and_ignores_solver_outcomes(self):
        launch = [f"row{i}" for i in range(4)]
        for outcomes in (
            ["incumbent_search_failed"] * 4,
            ["time_limit"] * 4,
            ["memory_limit"] * 4,
            ["attained_optimum"] * 4,
        ):
            completed = {row_id: {"status": status, "receipt_durable": True}
                         for row_id, status in zip(launch, outcomes)}
            self.assertTrue(parallel.ramp_receipts_ready(launch, completed))
            self.assertEqual(parallel.worker_target(12, launch, completed), 5)

        incomplete = {row_id: {"status": "time_limit", "receipt_durable": True}
                      for row_id in launch[:-1]}
        self.assertFalse(parallel.ramp_receipts_ready(launch, incomplete))
        self.assertEqual(parallel.worker_target(12, launch, incomplete), 4)
        failed = dict(incomplete, row3={"status": "verification_failed_receipt",
                                        "receipt_durable": True})
        self.assertFalse(parallel.ramp_receipts_ready(launch, failed))
        self.assertEqual(parallel.worker_target(12, launch, failed), 4)
        self.assertEqual(parallel.worker_target(4, launch, {
            row_id: {"status": "time_limit", "receipt_durable": True}
            for row_id in launch}), 4)

    def test_ramp_rehashes_the_first_four_receipt_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            launch = [f"row{i}" for i in range(4)]
            completed = {}
            for row_id in launch:
                path = root / f"{row_id}.receipt.json"
                payload = {"receipt_path": str(path), "unit": row_id}
                raw = json.dumps(payload, sort_keys=True).encode()
                path.write_bytes(raw)
                completed[row_id] = {"status": "time_limit", "receipt_durable": True,
                    "receipt_path": str(path), "receipt_sha256": hashlib.sha256(raw).hexdigest()}
            self.assertEqual(parallel.durable_ramp_receipts(launch, completed), (launch, True))
            (root / "row2.receipt.json").write_text("changed")
            self.assertFalse(parallel.durable_ramp_receipts(launch, completed)[1])

    def test_cgroup_sampler_uses_memory_current_and_checks_memory_max(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control = "/user.slice/user-1000.slice/app.slice/hiroute-m5d-test.service"
            group = root / control.lstrip("/")
            group.mkdir(parents=True)
            (group / "memory.current").write_text(str(3 * GiB))
            (group / "memory.max").write_text(str(8 * GiB))
            result = SimpleNamespace(stdout=(
                "ActiveState=active\nControlGroup=" + control +
                "\nMemoryMax=" + str(8 * GiB) + "\n"))
            with patch.object(parallel.subprocess, "run", return_value=result):
                sample = parallel.cgroup_memory_sample("hiroute-m5d-test.service", root)
            self.assertEqual(sample["memory_current_bytes"], 3 * GiB)
            self.assertEqual(sample["memory_max_bytes"], 8 * GiB)
            self.assertTrue(sample["memory_current_path"].endswith("/memory.current"))

    def test_active_row_without_created_cgroup_gets_full_cap_reserve(self):
        with tempfile.TemporaryDirectory() as directory:
            row_out = Path(directory)
            future = Future()
            rows, valid = parallel.active_memory_samples({
                future: ({"row_id": "row0"}, row_out, "claim")})
        self.assertTrue(valid)
        self.assertEqual(rows[0]["source"], "pre-cgroup-full-cap-reserve")
        self.assertEqual(rows[0]["memory_current_bytes"], 0)
        self.assertEqual(rows[0]["memory_max_bytes"], 8 * GiB)

    def test_contiguous_state_advances_after_out_of_order_receipts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = [{"row_id": f"row{i}", "method": "flat"} for i in range(3)]
            state = {"rows": {"row0": {"status": "time_limit"}},
                     "charged_cpu_ns": 1, "stopped": False}
            ledger = {"completed": {
                "row2": {"row_result": {"status": "memory_limit"}, "charged_cpu_ns": 30},
                "row1": {"row_result": {"status": "incumbent_search_failed"}, "charged_cpu_ns": 20}},
                "charged_cpu_ns": 51}
            path = root / "state.json"
            parallel.advance_state_prefix(rows, state, ledger, "a" * 64, path)
            self.assertEqual(list(state["rows"]), ["row0", "row1", "row2"])
            self.assertEqual(state["charged_cpu_ns"], 51)
            self.assertEqual(json.loads(path.read_text())["rows"]["row2"]["status"], "memory_limit")

    def test_full_handoff_mock_ramps_only_after_four_durable_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            output = root / "output"
            source.mkdir(); output.mkdir()
            inputs = {}
            for name in ("pool", "queries", "full"):
                path = root / f"{name}.json"
                path.write_text("{}")
                inputs[name] = path
            rows = [{"row_id": f"row{i:03d}_flat", "method": "flat"}
                    for i in range(192)]
            manifest = {"schema": "hiroute.m5d.frozen_main_phase.v1", "rows": rows,
                "wall_seconds": 600, "memory_bytes": 8 * GiB,
                "main_cpu_seconds_ceiling": 117000, "source_sha256": {},
                "input_sha256": {"pools": parallel.sha_file(inputs["pool"]),
                    "queries": parallel.sha_file(inputs["queries"]),
                    "full_universes": parallel.sha_file(inputs["full"])}}
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest, sort_keys=True))
            manifest_sha = parallel.sha_file(manifest_path)
            state = {"schema": "hiroute.m5d.main_batch_state.v1",
                "phase_sha256": manifest_sha, "charged_cpu_ns": 0,
                "rows": {row["row_id"]: {"status": "time_limit"} for row in rows[:183]},
                "stopped": False}
            state_path = output / "state.json"
            state_path.write_text(json.dumps(state, sort_keys=True))
            handoff_path = root / "handoff.json"
            handoff_path.write_text(json.dumps({
                "schema": "hiroute.m5d.parallel_handoff.v1",
                "manifest_sha256": manifest_sha,
                "main_state_sha256": parallel.sha_file(state_path),
                "old_scheduler_gone": True, "old_main_units_empty": True,
                "review_approved": True,
                "outside_main_available_cpu_seconds": 10000,
                "main_host_cpu_ns": 0}, sort_keys=True))
            controller_sha = parallel.sha_file(Path(parallel.__file__))
            amendment = {"schema": "hiroute.m5d.parallel_continuation_amendment.v2",
                "manifest_sha256": manifest_sha, "controller_sha256": controller_sha,
                "max_workers": 5, "initial_workers": 4,
                "ramp_after_durable_receipts": 4, "ramp_ignores_row_outcomes": True,
                "ramp_requires_clean_receipts": True,
                "ramp_requires_five_worker_memory_admission": True,
                "ramp_requires_budget_admission": True,
                "cpu_quota_percent_per_row": 100, "wall_seconds_per_row": 600,
                "memory_bytes_per_row": 8 * GiB,
                "host_memory_reserve_bytes": 8 * GiB,
                "host_cpu_guard_seconds_per_row": 60,
                "memory_current_source": "systemd-cgroup-v2-memory.current"}
            amendment_path = root / "amendment.json"
            amendment_path.write_text(json.dumps(amendment, sort_keys=True))

            launch_lock = threading.Lock()
            launch_count = 0
            first_four = threading.Barrier(4)
            ramp_five = threading.Barrier(5)
            thread_env = {name: "1" for name in
                ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
                 "NUMEXPR_NUM_THREADS")}

            def mock_row_runner(argv, *, cwd, output_dir, **kwargs):
                nonlocal launch_count
                with launch_lock:
                    ordinal = launch_count
                    launch_count += 1
                unit = f"hiroute-m5d-fixture-{ordinal}.service"
                stdout = output_dir / (unit + ".stdout")
                stderr = output_dir / (unit + ".stderr")
                stdout.write_text("")
                stderr.write_text("")
                if ordinal < 4:
                    first_four.wait(timeout=5)
                else:
                    ramp_five.wait(timeout=5)
                (output_dir / "status.json").write_text(json.dumps({
                    "status": "incumbent_search_failed"}))
                receipt_path = output_dir / (unit + ".receipt.json")
                receipt = ResourceReceipt(unit, f"/user.slice/fixture/{unit}",
                    "success", 0, 10**9, 2 * GiB, 8 * GiB, 10**9,
                    str(stdout), str(stderr), str(receipt_path), 100, thread_env)
                with receipt_path.open("x") as stream:
                    json.dump(asdict(receipt), stream, sort_keys=True)
                    stream.write("\n"); stream.flush()
                    import os
                    os.fsync(stream.fileno())
                return receipt

            def fake_active_memory(active):
                samples = [{"row_id": row["row_id"],
                    "unit": "hiroute-m5d-fixture.service",
                    "memory_current_bytes": 4 * GiB,
                    "memory_max_bytes": 8 * GiB,
                    "memory_current_path": "/fixture/memory.current",
                    "source": "systemd-cgroup-v2-memory.current"}
                    for future, (row, _row_out, _token) in active.items()
                    if not future.done()]
                return samples, True

            with (patch.object(parallel, "current_main_processes", return_value=False),
                  patch.object(parallel, "active_main_units", return_value=[]),
                  patch.object(parallel, "effective_cpu_count", return_value=12),
                  patch.object(parallel, "mem_available_bytes", return_value=64 * GiB),
                  patch.object(parallel, "active_memory_samples", side_effect=fake_active_memory),
                  patch.object(parallel, "run_m5d_phase", side_effect=mock_row_runner)):
                final = parallel.run(source, root, inputs["pool"], inputs["queries"],
                    inputs["full"], manifest_path, amendment_path, handoff_path, output)

            self.assertEqual(len(final["launch_order"]), 9)
            self.assertEqual(len(final["ramp_events"]), 1)
            event = final["ramp_events"][0]
            self.assertEqual(event["first_four_rows"], final["launch_order"][:4])
            self.assertEqual(len(event["first_four_receipt_sha256"]), 4)
            self.assertEqual(event["memory_admission"]["active_worker_count"], 4)
            self.assertGreaterEqual(event["memory_admission"]["required_mem_available_bytes"],
                                    32 * GiB)
            self.assertTrue(event["budget_admission"]["admitted"])
            self.assertTrue(all(row["regime"] == "initial_4"
                                for row in final["admissions"][:4]))
            self.assertTrue(any(row["regime"] == "ramp_armed"
                                for row in final["admissions"]))
            self.assertTrue(any(row["regime"] == "ramped_5"
                                for row in final["admissions"]))
            final_state = json.loads(state_path.read_text())
            self.assertEqual(len(final_state["rows"]), 192)
            self.assertTrue(final_state["stopped"])
            self.assertEqual(final_state["rows"]["row183_flat"]["status"],
                             "incumbent_search_failed")


if __name__ == "__main__":
    unittest.main()
