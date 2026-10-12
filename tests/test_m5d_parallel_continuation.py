"""Synthetic admission and 4-to-5 ramp checks; no numerical row is launched."""
from concurrent.futures import Future
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import shutil
import sys
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

    def test_low_cpu_pause_still_stops_when_the_aggregate_budget_is_exhausted(self):
        failure, sample = parallel.paused_cpu_budget_failure(3, 0, 1, 59, 0)
        self.assertEqual(failure, "budget_exhausted")
        self.assertFalse(sample["admitted"])
        failure, sample = parallel.paused_cpu_budget_failure(3, 0, 1, 120, 0)
        self.assertIsNone(failure)
        self.assertTrue(sample["admitted"])

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

    def test_finished_error_future_keeps_full_cap_and_blocks_next_admission(self):
        with tempfile.TemporaryDirectory() as directory:
            row_out = Path(directory)
            future = Future()
            future.set_exception(RuntimeError("supervisor cleanup failed"))
            active = {future: ({"row_id": "row0"}, row_out, "claim")}
            samples, valid = parallel.active_memory_samples(active)
            self.assertFalse(valid)
            self.assertEqual(samples[0]["source"], "unreconciled-future-full-cap-reserve")
            self.assertEqual(samples[0]["memory_max_bytes"] -
                             samples[0]["memory_current_bytes"], 8 * GiB)
            failures = []
            claims = []

            def reconcile(done):
                failures.append(done.exception())

            if not parallel.reconcile_completed_futures(active, reconcile):
                claims.append("row1")
            self.assertEqual(len(failures), 1)
            self.assertEqual(claims, [])

    def test_controller_requires_supervisor_from_verified_source_tree(self):
        loaded = Path(parallel.__file__).resolve().parents[1] / "src/timecut5/systemd_supervisor.py"
        hashes = {"src/timecut5/systemd_supervisor.py": parallel.sha_file(loaded)}
        with tempfile.TemporaryDirectory() as directory:
            other = Path(directory)
            path = other / "src/timecut5/systemd_supervisor.py"
            path.parent.mkdir(parents=True)
            shutil.copyfile(loaded, path)
            runner = parallel.validate_supervisor_binding(other, hashes)
            self.assertEqual(Path(runner.__code__.co_filename).resolve(), path.resolve())
            path.write_text(path.read_text() + "\n# changed after freeze\n")
            with self.assertRaisesRegex(ValueError, "frozen source hash"):
                parallel.validate_supervisor_binding(other, hashes)

    def test_resume_rehashes_receipt_and_claim_before_advancing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            row_id = "row000_flat"
            row = {"row_id": row_id, "method": "flat"}
            row_out = root / row_id
            row_out.mkdir()
            manifest_sha, amendment_sha = "a" * 64, "b" * 64
            admission = {"row_id": row_id, "manifest_index": 0, "regime": "initial_4"}
            admission_sha = parallel.sha_bytes(parallel.canon(admission))
            token = "c" * 32
            claim = {"schema": "hiroute.m5d.parallel_row_claim.v2",
                "row_id": row_id, "manifest_sha256": manifest_sha,
                "amendment_sha256": amendment_sha, "claim": token,
                "manifest_index": 0, "admission_sha256": admission_sha,
                "regime": "initial_4"}
            claim_path = row_out / "parallel_claim.json"
            claim_path.write_text(json.dumps(claim, sort_keys=True) + "\n")
            unit = "hiroute-m5d-" + "1" * 32 + ".service"
            receipt_path = row_out / (unit + ".receipt.json")
            receipt = {"unit": unit, "control_group": "/user.slice/fixture/" + unit,
                "result": "timeout", "exit_status": 15, "cpu_usage_ns": 123,
                "memory_peak_bytes": 4096, "memory_limit_bytes": 8 * GiB,
                "wall_elapsed_ns": 600 * 10**9, "stdout_path": str(row_out / (unit + ".stdout")),
                "stderr_path": str(row_out / (unit + ".stderr")),
                "receipt_path": str(receipt_path), "cpu_quota_percent": 100,
                "thread_environment": {name: "1" for name in
                    ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
                     "NUMEXPR_NUM_THREADS")}}
            receipt_raw = json.dumps(receipt, sort_keys=True).encode() + b"\n"
            receipt_path.write_bytes(receipt_raw)
            result = {"status": "time_limit", "denominator_included": True,
                "receipt_path": str(receipt_path), "cgroup_cpu_usage_ns": 123,
                "cgroup_memory_peak_bytes": 4096, "cgroup_memory_limit_bytes": 8 * GiB,
                "wall_elapsed_ns": 600 * 10**9}
            record = {"status": "time_limit", "row_result": result, "charged_cpu_ns": 123,
                "claim_token": token, "claim_sha256": parallel.sha_file(claim_path),
                "receipt_durable": True, "receipt_path": str(receipt_path),
                "receipt_sha256": hashlib.sha256(receipt_raw).hexdigest(),
                "manifest_index": 0, "admission_sha256": admission_sha}
            ledger = {"schema": parallel.PARALLEL_STATE_SCHEMA, "start_index": 0,
                "charged_cpu_ns_at_start": 10, "charged_cpu_ns": 133,
                "completed": {row_id: record}, "launch_order": [row_id],
                "admissions": [admission], "inflight": {}, "stopped": False}
            state = {"rows": {row_id: result}, "charged_cpu_ns": 133, "stopped": False}
            parallel.validate_completed_evidence([row], state, ledger, root,
                manifest_sha, amendment_sha)
            receipt_path.write_text("tampered")
            with self.assertRaisesRegex(ValueError, "receipt hash differs"):
                parallel.validate_completed_evidence([row], state, ledger, root,
                    manifest_sha, amendment_sha)
            receipt_path.write_bytes(receipt_raw)
            claim_path.write_text("tampered")
            with self.assertRaisesRegex(ValueError, "row claim differs"):
                parallel.validate_completed_evidence([row], state, ledger, root,
                    manifest_sha, amendment_sha)

    def test_handoff_requires_start_identity_owned_units_and_runtime_pin(self):
        identity = {"pid": parallel.OLD_MAIN_PID, "start_ticks": 4242,
            "source_root": str(parallel.OLD_MAIN_SOURCE),
            "output_root": str(parallel.OLD_MAIN_OUTPUT), "cmdline_sha256": "d" * 64}
        handoff = {"schema": "hiroute.m5d.parallel_handoff.v2", "manifest_sha256": "a" * 64,
            "old_scheduler_gone": True, "old_main_units_empty": True,
            "review_approved": True, "outside_main_available_cpu_seconds": 1000,
            "main_host_cpu_ns": 20, "old_scheduler_identity": identity,
            "old_scheduler_identity_sha256": parallel.sha_bytes(parallel.canon(identity)),
            "old_owned_units": [{"unit": parallel.OLD_MAIN_OBSERVED_UNIT, "control_group": ""}],
            "python_runtime": {"executable_path": str(parallel.TRUSTED_PYTHON)}}
        parallel.validate_handoff(handoff, "a" * 64)
        handoff["old_scheduler_identity"].pop("start_ticks")
        with self.assertRaisesRegex(ValueError, "old-process"):
            parallel.validate_handoff(handoff, "a" * 64)

    def test_active_main_units_inspects_execstart_for_generic_unit_names(self):
        unit = "hiroute-m5d-" + "2" * 32 + ".service"
        listing = f"{unit} loaded active running M5-D row\n"
        props = ("ActiveState=active\nControlGroup=\nExecStart={{ path=/usr/bin/python3 ; "
                 f"argv[]=/usr/bin/python3 {parallel.OLD_MAIN_SOURCE}/scripts/m5d_main_row.py ; }}\n")
        with patch.object(parallel.subprocess, "check_output", side_effect=[listing, props]):
            self.assertEqual(parallel.active_main_units(), [unit])

    def test_old_dispatcher_search_uses_original_source_and_output_paths(self):
        identity = {"pid": parallel.OLD_MAIN_PID, "start_ticks": 4242}
        old_command = (f"/home/dy/miniconda3/envs/hiroute/bin/python "
            f"{parallel.OLD_MAIN_SOURCE}/scripts/m5d_main_batch.py "
            f"{parallel.OLD_MAIN_SOURCE} {parallel.OLD_MAIN_OUTPUT}")
        with patch.object(parallel, "proc_start_ticks", return_value=None), \
             patch.object(parallel.subprocess, "check_output", return_value=old_command):
            self.assertTrue(parallel.current_main_processes(identity))

    def test_handoff_unit_check_rejects_active_old_row_cgroup(self):
        result = SimpleNamespace(returncode=0, stdout=(
            "LoadState=loaded\nActiveState=active\nControlGroup=\n"
            f"ExecStart={{ path=/usr/bin/python ; argv[]=/usr/bin/python "
            f"{parallel.OLD_MAIN_SOURCE}/scripts/m5d_main_row.py ; }}\n"))
        unit = {"unit": parallel.OLD_MAIN_OBSERVED_UNIT, "control_group": ""}
        with patch.object(parallel.subprocess, "run", return_value=result):
            self.assertFalse(parallel.old_owned_units_empty([unit]))

    def test_runtime_fingerprint_rejects_changed_python_binary(self):
        fingerprint = {"executable_path": str(Path(sys.executable).resolve()),
            "executable_sha256": parallel.sha_file(Path(sys.executable).resolve()),
            "implementation": sys.implementation.name, "version": sys.version.split()[0],
            "cache_tag": sys.implementation.cache_tag}
        with patch.object(parallel, "TRUSTED_PYTHON", Path(sys.executable).resolve()):
            self.assertEqual(parallel.validate_python_runtime({"python_runtime": fingerprint}),
                             str(Path(sys.executable).resolve()))
            fingerprint["executable_sha256"] = "e" * 64
            with self.assertRaisesRegex(ValueError, "runtime fingerprint"):
                parallel.validate_python_runtime({"python_runtime": fingerprint})

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
            frozen_supervisor = source / "src/timecut5/systemd_supervisor.py"
            frozen_supervisor.parent.mkdir(parents=True)
            loaded_supervisor = Path(parallel.__file__).resolve().parents[1] / "src/timecut5/systemd_supervisor.py"
            shutil.copyfile(loaded_supervisor, frozen_supervisor)
            inputs = {}
            for name in ("pool", "queries", "full"):
                path = root / f"{name}.json"
                path.write_text("{}")
                inputs[name] = path
            rows = [{"row_id": f"row{i:03d}_flat", "method": "flat"}
                    for i in range(192)]
            manifest = {"schema": "hiroute.m5d.frozen_main_phase.v1", "rows": rows,
                "wall_seconds": 600, "memory_bytes": 8 * GiB,
                "main_cpu_seconds_ceiling": 117000,
                "source_sha256": {"src/timecut5/systemd_supervisor.py":
                    parallel.sha_file(frozen_supervisor)},
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
            identity = {"pid": parallel.OLD_MAIN_PID, "start_ticks": 4242,
                "source_root": str(parallel.OLD_MAIN_SOURCE),
                "output_root": str(parallel.OLD_MAIN_OUTPUT), "cmdline_sha256": "d" * 64}
            handoff_path.write_text(json.dumps({
                "schema": "hiroute.m5d.parallel_handoff.v2",
                "manifest_sha256": manifest_sha,
                "main_state_sha256": parallel.sha_file(state_path),
                "old_scheduler_gone": True, "old_main_units_empty": True,
                "review_approved": True,
                "outside_main_available_cpu_seconds": 10000,
                "main_host_cpu_ns": 0, "old_scheduler_identity": identity,
                "old_scheduler_identity_sha256": parallel.sha_bytes(parallel.canon(identity)),
                "old_owned_units": [{"unit": parallel.OLD_MAIN_OBSERVED_UNIT,
                    "control_group": ""}],
                "python_runtime": {"executable_path": str(parallel.TRUSTED_PYTHON),
                    "executable_sha256": "e" * 64, "implementation": "CPython",
                    "version": "3.11.0", "cache_tag": "cpython-311"}}, sort_keys=True))
            controller_sha = parallel.sha_file(Path(parallel.__file__))
            amendment = {"schema": parallel.AMENDMENT_SCHEMA,
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
                "finalize_cpu_guard_seconds": 60,
                "old_scheduler_pid": parallel.OLD_MAIN_PID,
                "old_scheduler_source": str(parallel.OLD_MAIN_SOURCE),
                "old_scheduler_output": str(parallel.OLD_MAIN_OUTPUT),
                "trusted_python_path": str(parallel.TRUSTED_PYTHON),
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
                  patch.object(parallel, "old_owned_units_empty", return_value=True),
                  patch.object(parallel, "validate_supervisor_binding",
                               return_value=mock_row_runner),
                  patch.object(parallel, "validate_python_runtime",
                               return_value=sys.executable),
                  patch.object(parallel, "effective_cpu_count", return_value=12),
                  patch.object(parallel, "mem_available_bytes", return_value=64 * GiB),
                  patch.object(parallel, "active_memory_samples", side_effect=fake_active_memory)):
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
