"""Tiny synthetic guard tests only; never invoke C01, capture, replay, or LP."""
from dataclasses import asdict, replace
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from experiments.time_cut_v2.recorded_real import runtime as rt


ROOT = Path(__file__).resolve().parents[1]
WORKER = """
import json, os, resource
from experiments.time_cut_v2.recorded_real.runtime import BoundedEvidenceWriter
with BoundedEvidenceWriter(os.environ['HIROUTE_EVIDENCE_ROOT'],
        int(os.environ['HIROUTE_EVIDENCE_CAP_BYTES']),
        profile_name=os.environ['HIROUTE_PROFILE']) as writer:
    data = json.dumps({'as': resource.getrlimit(resource.RLIMIT_AS),
                       'cpus': sorted(os.sched_getaffinity(0)),
                       'pid': os.getpid(), 'pgid': os.getpgrp()}).encode()
    writer.write('proof.json', iter([data]), expected_bytes=len(data))
    writer.finalize()
"""


@unittest.skipUnless(sys.platform == "linux", "Linux process limits and /proc required")
class RecordedRealRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cpu = min(os.sched_getaffinity(0))
        self.context = rt.PlanContext("a" * 64, "b" * 64, "c" * 64, rt.TINY_TEST.name)

    def tearDown(self):
        self.tmp.cleanup()

    def writer(self, name="evidence", cap=2 * rt.MiB):
        return rt.BoundedEvidenceWriter(self.root / name, cap, profile_name=rt.TINY_TEST.name)

    def phase(self, command=WORKER, name="attempt", *, entry=None, deadline=None):
        entry = time.monotonic() if entry is None else entry
        deadline = entry + rt.TINY_TEST.wall_seconds if deadline is None else deadline
        return rt.run_phase([sys.executable, "-c", command], attempt_dir=self.root / name,
                            profile=rt.TINY_TEST, cpu=self.cpu, context=self.context,
                            entry_monotonic=entry, deadline_monotonic=deadline)

    def verify(self, name="evidence", cap=2 * rt.MiB):
        return rt.verify_manifest(self.root / name, expected_cap_bytes=cap,
                                  expected_profile_name=rt.TINY_TEST.name)

    def batch_cpus(self):
        cpus = sorted(os.sched_getaffinity(0))
        if len(cpus) < 6:
            self.skipTest("six inherited CPUs required for batch mask tests")
        return cpus[0], tuple(cpus[1:6])

    def batch_request(self):
        cpu, worker_cpus = self.batch_cpus()
        start = time.monotonic()
        return {"profile": asdict(rt.BATCH_REPLAY), "cpu": cpu,
                "worker_cpus": list(worker_cpus),
                "context": asdict(replace(self.context, profile_name=rt.BATCH_REPLAY.name)),
                "entry_monotonic": start, "deadline_monotonic": start + 5.0,
                "launcher_rss_bytes_at_entry": 1, "command": [sys.executable, "-c", "pass"]}

    def batch_cold_fixture(self, name, mutate=lambda request, report: None):
        """Synthetic history only: write tiny evidence, never launch batch replay."""
        attempt = self.root / name
        attempt.mkdir()
        profile = rt.BATCH_REPLAY
        with rt.BoundedEvidenceWriter(attempt / "evidence", profile.worker_evidence_bytes,
                                      profile_name=profile.name) as writer:
            writer.write("proof", iter([b"tiny synthetic batch evidence"]))
            manifest = writer.finalize()
        manifest_raw = (attempt / "evidence/__manifest.json").read_bytes()
        manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
        request = self.batch_request()
        request.update(entry_monotonic=100.0, deadline_monotonic=110.0)
        report = {key: json.loads(json.dumps(value)) for key, value in request.items()
                  if key != "command"}
        report.update(schema="hiroute-phase-v1", status="provisional", reason="test fixture",
                      worker_exit_code=0, descendants_reaped=True,
                      sampled_group_rss_peak_bytes=0, kernel_max_reaped_ru_maxrss_bytes=0,
                      supervisor_kernel_peak_rss_bytes=0,
                      supervisor_metadata_charge_bytes_before_report=0,
                      worker_charged_bytes=manifest["charged_bytes"],
                      largest_sample_gap_seconds=0.0, phase_wall_seconds=0.1,
                      reaped_cpu_seconds=0.0, supervisor_cpu_seconds=0.0,
                      verified_manifest_sha256=manifest_sha,
                      verified_manifest_size_bytes=len(manifest_raw))
        mutate(request, report)
        request_raw = rt._json(request)
        report["request_sha256"] = hashlib.sha256(request_raw).hexdigest()
        report_raw = rt._json(report)
        ready = {"schema": "hiroute-supervisor-decision-v1", "status": "ready",
                 "report_sha256": hashlib.sha256(report_raw).hexdigest(),
                 "report_size_bytes": len(report_raw), "manifest_sha256": manifest_sha,
                 "manifest_size_bytes": len(manifest_raw)}
        ready_raw = rt._json(ready)
        decision = {"schema": "hiroute-phase-decision-v1", "status": "completed",
                    "supervisor_exit_code": 0, "accepted_monotonic": 100.2,
                    "supervisor_decision_sha256": hashlib.sha256(ready_raw).hexdigest()}
        decision_raw = rt._json(decision)
        for filename, raw in (("request.json", request_raw), ("result.json", report_raw),
                              ("supervisor-decision.json", ready_raw), ("decision.json", decision_raw)):
            (attempt / filename).write_bytes(raw)
        receipt = {"schema": "hiroute-caller-return-v1", "returned_monotonic": 100.5,
                   "result_sha256": hashlib.sha256(report_raw).hexdigest(),
                   "decision_sha256": hashlib.sha256(decision_raw).hexdigest(),
                   "manifest_sha256": manifest_sha, "manifest_size_bytes": len(manifest_raw)}
        return attempt, dict(report, status="completed", phase_wall_seconds=0.5,
                             acceptance_receipt=receipt)

    def test_fixed_profiles_and_exact_types(self):
        self.assertEqual(rt.CAPTURE.child_as_bytes, 8 * rt.GiB)
        self.assertEqual(rt.REPLAY.evidence_bytes, 8 * rt.GiB)
        self.assertEqual(rt.CAPTURE.supervisor_evidence_bytes, 16 * rt.MiB)
        self.assertEqual((rt.BATCH_REPLAY.child_as_bytes, rt.BATCH_REPLAY.group_rss_bytes,
                          rt.BATCH_REPLAY.wall_seconds, rt.BATCH_REPLAY.evidence_bytes,
                          rt.BATCH_REPLAY.host_reserve_bytes, rt.BATCH_REPLAY.disk_floor_bytes,
                          rt.BATCH_REPLAY.supervisor_as_bytes),
                         (16 * rt.GiB, 20 * rt.GiB, 1800, 8 * rt.GiB,
                          16 * rt.GiB, 20 * rt.GiB, 512 * rt.MiB))
        for cap in (True, False, 300000.0, "300000", 0):
            with self.subTest(cap=cap), self.assertRaises(ValueError):
                self.writer(cap=cap)
        for value in (True, 2.0):
            with self.subTest(value=value), self.assertRaises(ValueError):
                replace(rt.TINY_TEST, wall_seconds=value)
        changed = replace(rt.TINY_TEST, wall_seconds=3)
        start = time.monotonic()
        with self.assertRaisesRegex(ValueError, "fixed profile"):
            rt.run_phase([sys.executable], attempt_dir=self.root / "invalid", profile=changed,
                         cpu=self.cpu, context=self.context, entry_monotonic=start,
                         deadline_monotonic=start + 3)

    def test_batch_requires_exact_six_cpu_partition_before_any_launch(self):
        cpu, worker_cpus = self.batch_cpus()
        invalid = (None, (), worker_cpus[:-1], worker_cpus + (cpu,), list(worker_cpus),
                   set(worker_cpus), (worker_cpus[0],) * 5, (cpu,) + worker_cpus[1:],
                   (True,) + worker_cpus[1:], (float(worker_cpus[0]),) + worker_cpus[1:],
                   (str(worker_cpus[0]),) + worker_cpus[1:], (-1,) + worker_cpus[1:])
        context = replace(self.context, profile_name=rt.BATCH_REPLAY.name)
        with patch.object(rt.subprocess, "Popen") as launch:
            for index, mask in enumerate(invalid):
                attempt = self.root / f"invalid-batch-{index}"
                start = time.monotonic()
                with self.subTest(mask=mask), self.assertRaises(ValueError):
                    rt.run_phase([sys.executable, "-c", "pass"], attempt_dir=attempt,
                                 profile=rt.BATCH_REPLAY, cpu=cpu, worker_cpus=mask,
                                 context=context, entry_monotonic=start, deadline_monotonic=start + 1.0)
                self.assertFalse(attempt.exists())
            launch.assert_not_called()
        for profile in (rt.CAPTURE, rt.REPLAY, rt.TINY_TEST):
            with self.subTest(profile=profile.name), self.assertRaisesRegex(ValueError, "only supported"):
                rt._worker_cpu_mask(profile, cpu, worker_cpus)
        with self.assertRaises(ValueError):
            rt._worker_cpu_mask(rt.BATCH_REPLAY, True, worker_cpus)
        start = time.monotonic()
        with self.assertRaisesRegex(ValueError, "fixed profile"):
            rt.run_phase([sys.executable], attempt_dir=self.root / "arbitrary-batch",
                         profile=replace(rt.BATCH_REPLAY, group_rss_bytes=21 * rt.GiB),
                         cpu=cpu, worker_cpus=worker_cpus, context=context,
                         entry_monotonic=start, deadline_monotonic=start + 1.0)

    def test_batch_admission_reserves_group_rss_and_checks_entire_inherited_mask(self):
        cpu, worker_cpus = self.batch_cpus()
        profile = rt.BATCH_REPLAY
        reserve = profile.host_reserve_bytes + profile.group_rss_bytes + profile.supervisor_as_bytes
        with patch.object(rt, "_mem_available", return_value=reserve - 1), patch.object(rt, "_disk_available", return_value=100 * rt.GiB):
            with self.assertRaisesRegex(ValueError, "MemAvailable"):
                rt._preflight(profile, self.root, cpu, worker_cpus)
        with patch.object(rt, "_mem_available", return_value=reserve), patch.object(rt, "_disk_available", return_value=profile.disk_floor_bytes + profile.evidence_bytes):
            rt._preflight(profile, self.root, cpu, worker_cpus)
            for missing in (cpu, worker_cpus[-1]):
                inherited = {cpu, *worker_cpus} - {missing}
                with self.subTest(missing=missing), patch.object(rt.os, "sched_getaffinity", return_value=inherited):
                    with self.assertRaisesRegex(ValueError, "inherited affinity"):
                        rt._preflight(profile, self.root, cpu, worker_cpus)

    def test_batch_supervisor_pins_separately_and_samples_the_entire_group(self):
        request = self.batch_request()
        attempt = self.root / "mock-batch"
        attempt.mkdir()
        (attempt / "request.json").write_bytes(rt._json(request))
        cpu, worker_cpus = request["cpu"], tuple(request["worker_cpus"])
        events = []
        class FakeWorker:
            pid = 99999999
            returncode = None
        def inherited_affinity(pid):
            events.append("read inherited affinity")
            return {cpu, *worker_cpus}
        def set_affinity(pid, mask):
            events.append(set(mask))
        def launch(command, **kwargs):
            self.assertTrue(kwargs["start_new_session"])
            kwargs["preexec_fn"]()
            return FakeWorker()
        rows = {FakeWorker.pid: (os.getpid(), FakeWorker.pid, 1, 16 * rt.GiB)}
        rows.update({FakeWorker.pid + index: (FakeWorker.pid, FakeWorker.pid, 1, rt.GiB + 1)
                     for index in range(1, 5)})
        with patch.object(rt.os, "sched_getaffinity", inherited_affinity), patch.object(rt.os, "sched_setaffinity", set_affinity), patch.object(rt.resource, "setrlimit") as limits, patch.object(rt, "_prctl"), patch.object(rt, "_mem_available", return_value=100 * rt.GiB), patch.object(rt, "_disk_available", return_value=100 * rt.GiB), patch.object(rt, "_processes", return_value=rows), patch.object(rt.subprocess, "Popen", launch), patch.object(rt.os, "wait4", side_effect=ChildProcessError), patch.object(rt.os, "killpg") as kill_group, patch.object(rt.os, "kill"):
            report = rt._supervise(request, attempt)
        self.assertEqual(events, ["read inherited affinity", {cpu}, set(worker_cpus)])
        limits.assert_any_call(resource.RLIMIT_AS, (rt.BATCH_REPLAY.child_as_bytes,) * 2)
        self.assertEqual(report["status"], "unresolved")
        self.assertIn("process-group RSS limit exceeded", report["reason"])
        self.assertEqual(report["sampled_group_rss_peak_bytes"], 20 * rt.GiB + 4)
        self.assertEqual(report["worker_cpus"], list(worker_cpus))
        self.assertEqual(report["cpu"], cpu)
        self.assertTrue(report["descendants_reaped"])
        kill_group.assert_called_once_with(FakeWorker.pid, rt.signal.SIGKILL)

    def test_batch_keeps_uid_admission_lock_and_serializes_exact_cpu_mask(self):
        cpu, worker_cpus = self.batch_cpus()
        context = replace(self.context, profile_name=rt.BATCH_REPLAY.name)
        lock_path = Path("/tmp") / f"hiroute-recorded-phase-{os.getuid()}.lock"
        lock = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            rt.fcntl.flock(lock, rt.fcntl.LOCK_EX | rt.fcntl.LOCK_NB)
            start = time.monotonic()
            with patch.object(rt.subprocess, "Popen") as launch:
                report = rt.run_phase([sys.executable, "-c", "pass"], attempt_dir=self.root / "locked-batch",
                                      profile=rt.BATCH_REPLAY, cpu=cpu, worker_cpus=worker_cpus,
                                      context=context, entry_monotonic=start, deadline_monotonic=start + 1.0)
                launch.assert_not_called()
        finally:
            os.close(lock)
        self.assertEqual(report["status"], "unresolved")
        self.assertIn("another phase owns admission", report["reason"])
        request = json.loads((self.root / "locked-batch/request.json").read_bytes())
        for record in (request, report):
            self.assertEqual(record["cpu"], cpu)
            self.assertEqual(record["worker_cpus"], list(worker_cpus))

    def test_batch_cold_result_binds_cpu_mask_without_current_affinity(self):
        attempt, returned = self.batch_cold_fixture("cold-batch")
        with patch.object(rt.os, "sched_getaffinity", return_value={self.cpu}):
            self.assertEqual(rt.read_phase_result(attempt, successful_return=returned)["status"], "completed")
        altered = dict(returned, worker_cpus=list(reversed(returned["worker_cpus"])))
        self.assertEqual(rt.read_phase_result(attempt, successful_return=altered)["status"], "unresolved")

    def test_batch_cold_result_rejects_rebound_invalid_or_different_cpu_masks(self):
        def replace_both(request, report, key, value):
            request[key] = report[key] = value
        cpu, worker_cpus = self.batch_cpus()
        mutations = {
            "different-order": lambda q, r: r.update(worker_cpus=list(reversed(worker_cpus))),
            "different-supervisor": lambda q, r: r.update(cpu=worker_cpus[0], worker_cpus=[cpu, *worker_cpus[1:]]),
            "missing-request": lambda q, r: q.pop("worker_cpus"),
            "missing-report": lambda q, r: r.pop("worker_cpus"),
            "duplicate": lambda q, r: replace_both(q, r, "worker_cpus", [worker_cpus[0]] * 5),
            "overlap": lambda q, r: replace_both(q, r, "worker_cpus", [cpu, *worker_cpus[1:]]),
            "short": lambda q, r: replace_both(q, r, "worker_cpus", list(worker_cpus[:-1])),
            "float-worker": lambda q, r: replace_both(q, r, "worker_cpus", [float(worker_cpus[0]), *worker_cpus[1:]]),
            "bool-worker": lambda q, r: replace_both(q, r, "worker_cpus", [True, *worker_cpus[1:]]),
            "float-supervisor": lambda q, r: replace_both(q, r, "cpu", float(cpu)),
            "string-mask": lambda q, r: replace_both(q, r, "worker_cpus", str(list(worker_cpus))),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                attempt, returned = self.batch_cold_fixture(name, mutate)
                self.assertEqual(rt.read_phase_result(attempt, successful_return=returned)["status"], "unresolved")

    def test_one_pass_large_chunk_split_and_cold_rehash(self):
        consumed = []
        data = b"hello" * 40000
        def producer():
            yield data
            consumed.append("exhausted")
        with self.writer() as writer:
            row = writer.write("nested/proof.bin", producer(), expected_bytes=len(data))
            self.assertEqual(row["sha256"], hashlib.sha256(data).hexdigest())
            manifest = writer.finalize()
        self.assertEqual(consumed, ["exhausted"])
        self.assertEqual(manifest, self.verify())
        self.assertEqual(manifest["charged_bytes"], rt.WRITER_HEADROOM + rt.ENTRY_CHARGE + 2 * len(data))
        self.assertEqual(list((self.root / "evidence/__partial").iterdir()), [])

    def test_budget_failure_retains_partial_and_never_finalizes(self):
        cap = rt.WRITER_HEADROOM + rt.ENTRY_CHARGE + 2 * rt.CHUNK_BYTES
        with self.writer(cap=cap) as writer:
            with self.assertRaisesRegex(ValueError, "charge exceeded"):
                writer.write("big.bin", iter([b"x" * (rt.CHUNK_BYTES + 1)]))
            with self.assertRaisesRegex(ValueError, "failed"):
                writer.finalize()
            self.assertEqual(writer.charged_bytes, cap)
        partial = self.root / "evidence/__partial/0000.part"
        self.assertEqual(partial.stat().st_size, rt.CHUNK_BYTES)
        self.assertFalse((self.root / "evidence/big.bin").exists())
        self.assertFalse((self.root / "evidence/__manifest.json").exists())

    def test_duplicate_path_is_immutable_and_poisons_attempt(self):
        with self.writer() as writer:
            writer.write("one", iter([b"first"]))
            with self.assertRaisesRegex(ValueError, "duplicate"):
                writer.write("one", iter([b"second"]))
            with self.assertRaisesRegex(ValueError, "failed"):
                writer.finalize()
        self.assertEqual((self.root / "evidence/one").read_bytes(), b"first")

    def test_path_escape_reserved_path_and_symlink_reject(self):
        for index, path in enumerate(("../escape", "/absolute", "a/../b", "a//b", "a\\b", "__manifest.json")):
            with self.subTest(path=path), self.writer(f"case{index}") as writer:
                with self.assertRaises(ValueError):
                    writer.write(path, iter([b"x"]))
        with self.writer() as writer:
            (writer.root / "link").symlink_to(self.root, target_is_directory=True)
            with self.assertRaises(OSError):
                writer.write("link/escape", iter([b"x"]))
        self.assertFalse((self.root / "escape").exists())
        (self.root / "alias").symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(OSError):
            rt.BoundedEvidenceWriter(self.root / "alias/new", 2 * rt.MiB, profile_name=rt.TINY_TEST.name)

    def test_producer_failure_and_short_stream_remain_unresolved(self):
        def producer():
            yield b"partial"
            raise RuntimeError("producer did not finish")
        with self.writer() as writer:
            with self.assertRaisesRegex(RuntimeError, "did not finish"):
                writer.write("one", producer())
            with self.assertRaises(ValueError):
                writer.finalize()
        with self.writer("short") as writer:
            with self.assertRaisesRegex(ValueError, "expected byte count"):
                writer.write("one", iter([b"x"]), expected_bytes=2)
        self.assertFalse((self.root / "short/one").exists())

    def test_completed_writer_cannot_reopen_or_write_again(self):
        with self.writer() as writer:
            writer.write("one", iter([b"one"]))
            writer.finalize()
            with self.assertRaises(ValueError):
                writer.write("two", iter([b"two"]))
            with self.assertRaises(ValueError):
                writer.finalize()
        with self.assertRaises(FileExistsError):
            self.writer()

    def test_cold_verification_detects_tamper_extra_files_and_expected_cap(self):
        with self.writer() as writer:
            writer.write("one", iter([b"one"]))
            writer.finalize()
        with self.assertRaisesRegex(ValueError, "profile/cap"):
            self.verify(cap=3 * rt.MiB)
        with self.assertRaisesRegex(ValueError, "profile/cap"):
            rt.verify_manifest(self.root / "evidence", expected_cap_bytes=2 * rt.MiB,
                               expected_profile_name=rt.CAPTURE.name)
        path = self.root / "evidence/one"
        path.chmod(0o600)
        path.write_bytes(b"two")
        with self.assertRaisesRegex(ValueError, "hash/size"):
            self.verify()
        path.write_bytes(b"one")
        (self.root / "evidence/extra").write_bytes(b"x")
        with self.assertRaisesRegex(ValueError, "inventory"):
            self.verify()

    def test_tiny_phase_limits_affinity_metrics_and_immutable_attempt(self):
        report = self.phase()
        self.assertEqual(report["status"], "completed", report)
        proof = json.loads((self.root / "attempt/evidence/proof.json").read_text())
        self.assertEqual(proof["as"], [rt.TINY_TEST.child_as_bytes] * 2)
        self.assertEqual(proof["cpus"], [self.cpu])
        self.assertNotIn("worker_cpus", report)
        self.assertNotIn("worker_cpus", json.loads((self.root / "attempt/request.json").read_bytes()))
        self.assertEqual(proof["pid"], proof["pgid"])
        self.assertTrue(report["descendants_reaped"])
        self.assertGreater(report["kernel_max_reaped_ru_maxrss_bytes"], 0)
        self.assertGreater(report["launcher_rss_bytes_at_entry"], 0)
        # A very short worker can exit between samples; wait4 retains its peak.
        self.assertGreaterEqual(report["sampled_group_rss_peak_bytes"], 0)
        self.assertLessEqual(report["supervisor_kernel_peak_rss_bytes"], rt.TINY_TEST.supervisor_as_bytes)
        self.assertTrue((self.root / "attempt/samples.jsonl").read_text())
        before = (self.root / "attempt/result.json").read_bytes()
        with self.assertRaises(FileExistsError):
            self.phase()
        self.assertEqual((self.root / "attempt/result.json").read_bytes(), before)

    def test_timeout_kills_and_reaps_grandchild(self):
        command = """
import os, time
from experiments.time_cut_v2.recorded_real.runtime import BoundedEvidenceWriter
child = os.fork()
if child == 0:
    time.sleep(60)
else:
    with BoundedEvidenceWriter(os.environ['HIROUTE_EVIDENCE_ROOT'], int(os.environ['HIROUTE_EVIDENCE_CAP_BYTES']), profile_name=os.environ['HIROUTE_PROFILE']) as writer:
        writer.write('descendant', iter([str(child).encode()]))
    time.sleep(60)
"""
        report = self.phase(command)
        self.assertEqual(report["status"], "unresolved", report)
        self.assertIn("deadline", report["reason"])
        self.assertTrue(report["descendants_reaped"])
        child = int((self.root / "attempt/evidence/descendant").read_text())
        self.assertFalse(Path(f"/proc/{child}").exists())
        self.assertFalse(Path(f"/proc/{report['worker_pid']}").exists())
        self.assertFalse((self.root / "attempt/evidence/__manifest.json").exists())

    def test_expired_deadline_counts_prior_binding_time(self):
        entry = time.monotonic() - 3
        report = self.phase(entry=entry, deadline=entry + 2)
        self.assertEqual(report["status"], "unresolved")
        self.assertIn("expired before preflight", report["reason"])
        self.assertIsNone(report["worker_pid"])
        self.assertGreaterEqual(report["phase_wall_seconds"], 3)

    def test_missing_host_or_disk_reserve_rejects_preflight(self):
        with patch.object(rt, "_mem_available", return_value=0):
            with self.assertRaisesRegex(ValueError, "MemAvailable"):
                rt._preflight(rt.TINY_TEST, self.root, self.cpu)
        with patch.object(rt, "_mem_available", return_value=100 * rt.GiB), patch.object(rt, "_disk_available", return_value=0):
            with self.assertRaisesRegex(ValueError, "disk"):
                rt._preflight(rt.TINY_TEST, self.root, self.cpu)

    def test_inherited_smaller_as_hard_limit_rejects_before_worker(self):
        command = f"""
import resource, sys, time
from pathlib import Path
from experiments.time_cut_v2.recorded_real.runtime import *
resource.setrlimit(resource.RLIMIT_AS, (128 * MiB, 128 * MiB))
start = time.monotonic()
run_phase([sys.executable, '-c', 'raise AssertionError()'], attempt_dir={str(self.root / 'limited')!r},
          profile=TINY_TEST, cpu={self.cpu}, context=PlanContext('a'*64, 'b'*64, 'c'*64, TINY_TEST.name),
          entry_monotonic=start, deadline_monotonic=start+TINY_TEST.wall_seconds)
"""
        subprocess.run([sys.executable, "-c", command], cwd=ROOT, check=True, timeout=5)
        report = json.loads((self.root / "limited/result.json").read_text())
        self.assertEqual(report["status"], "unresolved")
        self.assertIn("inherited RLIMIT_AS hard limit", report["reason"])
        self.assertIsNone(report["worker_pid"])

    def test_worker_claiming_larger_evidence_cap_rejects(self):
        report = self.phase(WORKER.replace("int(os.environ['HIROUTE_EVIDENCE_CAP_BYTES'])", "int(os.environ['HIROUTE_EVIDENCE_CAP_BYTES']) + 1"))
        self.assertEqual(report["status"], "unresolved")
        self.assertIn("profile/cap mismatch", report["reason"])

    def test_concurrent_phase_admission_is_rejected(self):
        attempt = self.root / "first"
        script = f"""
import sys, time
from experiments.time_cut_v2.recorded_real.runtime import *
start = time.monotonic()
run_phase([sys.executable, '-c', 'import time; time.sleep(60)'], attempt_dir={str(attempt)!r},
          profile=TINY_TEST, cpu={self.cpu}, context=PlanContext('a'*64, 'b'*64, 'c'*64, TINY_TEST.name),
          entry_monotonic=start, deadline_monotonic=start+TINY_TEST.wall_seconds)
"""
        first = subprocess.Popen([sys.executable, "-c", script], cwd=ROOT)
        try:
            until = time.monotonic() + 3
            while not (attempt / "worker.json").exists() and time.monotonic() < until:
                if first.poll() is not None:
                    break
                time.sleep(0.01)
            self.assertTrue((attempt / "worker.json").exists())
            report = self.phase(name="second")
            self.assertEqual(report["status"], "unresolved", report)
            self.assertIn("BlockingIOError", report["reason"])
            self.assertIsNone(report["worker_pid"])
        finally:
            first.wait(timeout=5)

    def test_poisoned_writer_keeps_one_reserved_failure_diagnostic(self):
        command = """
import os
from experiments.time_cut_v2.recorded_real.runtime import BoundedEvidenceWriter, worker_failure
with BoundedEvidenceWriter(os.environ['HIROUTE_EVIDENCE_ROOT'], int(os.environ['HIROUTE_EVIDENCE_CAP_BYTES']), profile_name=os.environ['HIROUTE_PROFILE']) as writer:
    try:
        writer.write('oversized', iter([b'x' * (2 * 1024 * 1024)]))
    except ValueError as exc:
        if not worker_failure(type(exc).__name__, str(exc), 'export'):
            raise AssertionError('first failure slot was not recorded')
        if worker_failure('OtherError', 'must not overwrite', 'other'):
            raise AssertionError('duplicate failure slot was accepted')
        raise
"""
        report = self.phase(command)
        self.assertEqual(report["status"], "unresolved")
        self.assertEqual(report["worker_failure"]["error_type"], "ValueError")
        self.assertEqual(report["worker_failure"]["stage"], "export")
        self.assertIn("charge exceeded", report["worker_failure"]["message"])
        self.assertLessEqual((self.root / "attempt/worker-failure.json").stat().st_size, rt.FAILURE_SLOT_BYTES)
        self.assertFalse((self.root / "attempt/worker-failure.json.partial").exists())

    def test_failure_slot_prevents_success_even_when_worker_exits_zero(self):
        command = WORKER + "\nfrom experiments.time_cut_v2.recorded_real.runtime import worker_failure\nworker_failure('ValueError', 'incomplete domain result', 'search')\n"
        report = self.phase(command)
        self.assertEqual(report["status"], "unresolved", report)
        self.assertEqual(report["worker_failure"]["stage"], "search")

    def test_incomplete_failure_slot_never_accepts_completed_evidence(self):
        command = WORKER + "\nfrom pathlib import Path\nPath(os.environ['HIROUTE_FAILURE_PATH']).with_suffix('.claim').touch()\n"
        report = self.phase(command)
        self.assertEqual(report["status"], "unresolved", report)
        self.assertIn("invalid worker failure diagnostic", report["reason"])

    def test_completed_decision_binds_exact_manifest_and_provisional_report(self):
        report = self.phase()
        self.assertEqual(report["status"], "completed", report)
        attempt = self.root / "attempt"
        raw = (attempt / "evidence/__manifest.json").read_bytes()
        self.assertEqual(report["verified_manifest_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(report["verified_manifest_size_bytes"], len(raw))
        self.assertEqual(json.loads((attempt / "result.json").read_bytes())["status"], "provisional")
        self.assertEqual(rt.read_phase_result(attempt)["status"], "unresolved")
        self.assertEqual(rt.read_phase_result(attempt, successful_return=report)["status"], "completed")
        for key, value in (("worker_exit_code", False), ("descendants_reaped", 1),
                           ("worker_charged_bytes", float(report["worker_charged_bytes"]))):
            with self.subTest(alias=key):
                aliased = dict(report, **{key: value})
                self.assertEqual(rt.read_phase_result(attempt, successful_return=aliased)["status"], "unresolved")
        (attempt / "decision.json").unlink()
        self.assertEqual(rt.read_phase_result(attempt, successful_return=report)["status"], "unresolved")

    def test_metadata_lock_cannot_hide_bytes(self):
        with self.writer() as writer:
            writer.write("one", iter([b"one"]))
            writer.finalize()
        lock = self.root / "evidence/__writer.lock"
        lock.chmod(0o600)
        lock.write_bytes(b"x" * (2 * rt.MiB))
        with self.assertRaisesRegex(ValueError, "lock must be empty"):
            self.verify()

    def test_constructor_failure_closes_every_open_directory(self):
        before = set(Path("/proc/self/fd").iterdir())
        original = os.open
        def fail_journal(path, flags, *args, **kwargs):
            if path == "__journal.jsonl":
                raise OSError("injected initialization failure")
            return original(path, flags, *args, **kwargs)
        with patch.object(rt.os, "open", fail_journal), self.assertRaises(OSError):
            self.writer()
        self.assertEqual(set(Path("/proc/self/fd").iterdir()), before)

    def test_same_size_mutation_during_cold_hash_rejects(self):
        with self.writer() as writer:
            writer.write("one", iter([b"one"]))
            writer.finalize()
        path = self.root / "evidence/one"
        path.chmod(0o600)
        original = hashlib.sha256
        class MutatingDigest:
            def __init__(self, data=b""):
                self.digest = original(data)
            def update(self, data):
                self.digest.update(data)
                if data == b"one":
                    path.write_bytes(b"two")
            def hexdigest(self):
                return self.digest.hexdigest()
        with patch.object(rt.hashlib, "sha256", MutatingDigest):
            with self.assertRaisesRegex(ValueError, "changed while being hashed"):
                self.verify()

    def test_cold_hash_checks_live_floors_between_chunks(self):
        with self.writer() as writer:
            writer.write("one", iter([b"x" * (2 * rt.CHUNK_BYTES)]))
            writer.finalize()
        count = 0
        def checkpoint():
            nonlocal count
            count += 1
            with patch.object(rt, "_mem_available", return_value=0 if count >= 5 else 100 * rt.GiB):
                rt._live_checks(rt.TINY_TEST, self.root, time.monotonic() + 10)
        with self.assertRaisesRegex(MemoryError, "MemAvailable"):
            rt._verify_manifest(self.root / "evidence", expected_cap_bytes=2 * rt.MiB,
                                expected_profile_name=rt.TINY_TEST.name, resource_check=checkpoint)
        self.assertGreaterEqual(count, 5)

    def test_late_cleanup_publication_and_post_hash_floor_loss_never_complete(self):
        script = """
import json, os, sys, time
from dataclasses import asdict
from pathlib import Path
from experiments.time_cut_v2.recorded_real import runtime as rt
from tests.test_recorded_real_runtime import WORKER
attempt=Path(sys.argv[1]); attempt.mkdir(); mode=sys.argv[2]; start=time.monotonic()
deadline=start+(0.4 if mode.startswith('late') else 2.)
request=dict(profile=asdict(rt.TINY_TEST),context=asdict(rt.PlanContext('a'*64,'b'*64,'c'*64,rt.TINY_TEST.name)),entry_monotonic=start,deadline_monotonic=deadline,cpu=min(os.sched_getaffinity(0)),command=[sys.executable,'-c',WORKER],launcher_rss_bytes_at_entry=1)
(attempt/'request.json').write_text(json.dumps(request))
if mode=='late-cleanup':
    original=rt._read_worker_failure
    def delayed(path):
        time.sleep(max(0,deadline-time.monotonic())+.02)
        return original(path)
    rt._read_worker_failure=delayed
elif mode=='late-publication':
    original=rt._exclusive_json
    def delayed(path,*args,**kwargs):
        value=original(path,*args,**kwargs)
        if path.name=='result.json':time.sleep(max(0,deadline-time.monotonic())+.02)
        return value
    rt._exclusive_json=delayed
else:
    original=rt._verify_manifest
    def dropping(*args,**kwargs):
        value=original(*args,**kwargs)
        if mode=='host':rt._mem_available=lambda:0
        elif mode=='disk':rt._disk_available=lambda path:0
        else:rt._disk_available=lambda path:rt.TINY_TEST.disk_floor_bytes+1
        return value
    rt._verify_manifest=dropping
report=rt._supervise(request,attempt)
if report['status']!='unresolved':raise AssertionError(report)
if (attempt/'decision.json').exists():raise AssertionError('unexpected completed decision')
if rt.read_phase_result(attempt)['status']!='unresolved':raise AssertionError('unexpected recovery')
"""
        for mode in ("late-cleanup", "late-publication", "host", "disk", "metadata-floor"):
            with self.subTest(mode=mode):
                subprocess.run([sys.executable, "-c", script, str(self.root / mode), mode],
                               cwd=ROOT, check=True, timeout=5)

    def test_abrupt_supervisor_death_reaps_grandchild(self):
        command = """
import os, signal, time
from experiments.time_cut_v2.recorded_real.runtime import BoundedEvidenceWriter
child = os.fork()
if child == 0:
    time.sleep(60)
else:
    with BoundedEvidenceWriter(os.environ['HIROUTE_EVIDENCE_ROOT'], int(os.environ['HIROUTE_EVIDENCE_CAP_BYTES']), profile_name=os.environ['HIROUTE_PROFILE']) as writer:
        writer.write('descendant', iter([str(child).encode()]))
    os.kill(os.getppid(), signal.SIGKILL)
    time.sleep(60)
"""
        report = self.phase(command)
        self.assertEqual(report["status"], "unresolved", report)
        child = int((self.root / "attempt/evidence/descendant").read_text())
        self.assertFalse(Path(f"/proc/{child}").exists())
        self.assertEqual(rt.read_phase_result(self.root / "attempt")["status"], "unresolved")

    def test_killed_supervisor_reap_has_a_timeout(self):
        class HungSupervisor:
            pid = 99999999
            returncode = None
            def __init__(self):
                self.timeouts = []
            def wait(self, timeout=None):
                self.timeouts.append(timeout)
                raise subprocess.TimeoutExpired("injected", timeout)
        supervisor = HungSupervisor()
        with patch.object(rt.subprocess, "Popen", return_value=supervisor), patch.object(rt.os, "killpg"), patch.object(rt, "_prctl"), patch.object(rt, "_subreaper_value", return_value=0):
            report = self.phase()
        self.assertEqual(report["status"], "unresolved")
        self.assertEqual(len(supervisor.timeouts), 2)
        self.assertTrue(all(timeout is not None and timeout > 0 for timeout in supervisor.timeouts))
        self.assertFalse(report["supervisor_reaped"])

    def test_historical_decision_reconciles_request_metrics_and_cold_charge(self):
        report = self.phase()
        self.assertEqual(report["status"], "completed", report)
        attempt = self.root / "attempt"
        request_raw = (attempt / "request.json").read_bytes()
        manifest_raw = (attempt / "evidence/__manifest.json").read_bytes()
        original = json.loads((attempt / "result.json").read_bytes())
        original_ready = json.loads((attempt / "supervisor-decision.json").read_bytes())
        original_decision = json.loads((attempt / "decision.json").read_bytes())
        mutations = {
            "context": lambda x: x["context"].update(input_sha256="d" * 64),
            "entry": lambda x: x.update(entry_monotonic=x["entry_monotonic"] - 100),
            "deadline": lambda x: x.update(deadline_monotonic=x["deadline_monotonic"] + 100),
            "charge-zero": lambda x: x.update(worker_charged_bytes=0),
            "charge-bool": lambda x: x.update(worker_charged_bytes=True),
            "charge-float": lambda x: x.update(worker_charged_bytes=float(x["worker_charged_bytes"])),
            "exit": lambda x: x.update(worker_exit_code=7),
            "exit-bool": lambda x: x.update(worker_exit_code=False),
            "reaping": lambda x: x.update(descendants_reaped=False),
            "rss": lambda x: x.update(sampled_group_rss_peak_bytes=rt.TINY_TEST.group_rss_bytes + 1),
            "gap": lambda x: x.update(largest_sample_gap_seconds=99.0),
            "launcher": lambda x: x.update(launcher_rss_bytes_at_entry=x["launcher_rss_bytes_at_entry"] + 1),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                changed = json.loads(json.dumps(original))
                mutate(changed)
                report_raw = rt._json(changed)
                ready = dict(original_ready, report_sha256=hashlib.sha256(report_raw).hexdigest(), report_size_bytes=len(report_raw))
                ready_raw = rt._json(ready)
                decision = dict(original_decision, supervisor_decision_sha256=hashlib.sha256(ready_raw).hexdigest())
                for filename, data in (("result.json", report_raw), ("supervisor-decision.json", ready_raw), ("decision.json", rt._json(decision))):
                    path = attempt / filename
                    path.chmod(0o600)
                    path.write_bytes(data)
                receipt = dict(report["acceptance_receipt"], result_sha256=hashlib.sha256(report_raw).hexdigest(),
                               decision_sha256=hashlib.sha256(rt._json(decision)).hexdigest())
                repaired_return = dict(changed, status="completed", reason=report["reason"],
                                       phase_wall_seconds=report["phase_wall_seconds"], acceptance_receipt=receipt)
                self.assertEqual(rt.read_phase_result(attempt, successful_return=repaired_return)["status"], "unresolved")
        self.assertEqual((attempt / "request.json").read_bytes(), request_raw)
        self.assertEqual((attempt / "evidence/__manifest.json").read_bytes(), manifest_raw)

    def test_admission_lock_remains_owned_during_launcher_cold_verification(self):
        original = rt._verify_manifest
        blocked = []
        def checking(*args, **kwargs):
            lock = os.open(Path("/tmp") / f"hiroute-recorded-phase-{os.getuid()}.lock", os.O_RDWR)
            try:
                with self.assertRaises(BlockingIOError):
                    rt.fcntl.flock(lock, rt.fcntl.LOCK_EX | rt.fcntl.LOCK_NB)
                blocked.append(True)
            finally:
                os.close(lock)
            return original(*args, **kwargs)
        with patch.object(rt, "_verify_manifest", checking):
            report = self.phase()
        self.assertEqual(report["status"], "completed", report)
        self.assertEqual(blocked, [True])


if __name__ == "__main__":
    unittest.main()
