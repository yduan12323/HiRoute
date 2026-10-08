"""Synthetic writer/guard tests; no final-collector group, archive, or LP launch."""
from dataclasses import asdict, replace
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from experiments.time_cut_v2.recorded_real import runtime as rt


class FinalCollectorWriterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def writer(self, name="evidence", cap=2 * rt.MiB):
        return rt.BoundedEvidenceWriter(self.root / name, cap, profile_name=rt.TINY_TEST.name)

    def assert_poisoned(self, writer):
        with self.assertRaisesRegex(ValueError, "failed"):
            writer.finalize()
        self.assertFalse((writer.root / "__manifest.json").exists())

    def test_callback_matches_iterable_bytes_hash_charge_and_exact_journal(self):
        chunks = (b"", b"a" * (2 * rt.CHUNK_BYTES + 3), b"tail")
        payload = b"".join(chunks)
        expected_row = {"path": "nested/proof.bin", "size_bytes": len(payload),
                        "sha256": hashlib.sha256(payload).hexdigest()}
        expected_journal = (rt._json({"event": "begin", "path": "nested/proof.bin",
                                      "partial": "__partial/0000.part"}) +
                            rt._json({"event": "published", **expected_row}))
        manifests = []
        for name in ("iterable", "callback"):
            frames = []
            original = rt._write_all
            def record(fd, data):
                if os.readlink(f"/proc/self/fd/{fd}").endswith("0000.part"):
                    frames.append(len(data))
                original(fd, data)
            with self.writer(name) as writer, patch.object(rt, "_write_all", record):
                if name == "iterable":
                    row = writer.write("nested/proof.bin", iter(chunks), expected_bytes=len(payload))
                else:
                    def producer(emit):
                        for chunk in chunks:
                            emit(chunk)
                        return "ignored completion token"
                    row = writer.write_from_callback("nested/proof.bin", producer, expected_bytes=len(payload))
                self.assertEqual(row, expected_row)
                self.assertEqual(frames, [rt.CHUNK_BYTES, rt.CHUNK_BYTES, 3, 4])
                manifest = writer.finalize()
                self.assertEqual(manifest["charged_bytes"], rt.WRITER_HEADROOM + rt.ENTRY_CHARGE + 2 * len(payload))
                manifests.append(manifest)
            root = self.root / name
            self.assertEqual((root / "nested/proof.bin").read_bytes(), payload)
            self.assertEqual((root / "__journal.jsonl").read_bytes(), expected_journal)
            self.assertEqual(list((root / "__partial").iterdir()), [])
        self.assertEqual(manifests[0], manifests[1])
        self.assertEqual((self.root / "iterable/__manifest.json").read_bytes(),
                         (self.root / "callback/__manifest.json").read_bytes())

    def test_quota_failure_preserves_charged_frames_and_partial(self):
        cap = rt.WRITER_HEADROOM + rt.ENTRY_CHARGE + 2 * rt.CHUNK_BYTES
        with self.writer(cap=cap) as writer:
            with self.assertRaisesRegex(ValueError, "charge exceeded"):
                writer.write_from_callback("over", lambda emit: emit(b"x" * (rt.CHUNK_BYTES + 1)))
            self.assertEqual(writer.charged_bytes, cap)
            self.assert_poisoned(writer)
        self.assertEqual((writer.root / "__partial/0000.part").read_bytes(), b"x" * rt.CHUNK_BYTES)
        self.assertFalse((writer.root / "over").exists())

    def test_expected_size_is_exact_and_errors_keep_reservations(self):
        for index, expected in enumerate((0, 1, 3)):
            with self.subTest(expected=expected), self.writer(str(index)) as writer:
                with self.assertRaisesRegex(ValueError, "expected byte count"):
                    writer.write_from_callback("wrong-size", lambda emit: emit(b"ab"), expected_bytes=expected)
                self.assertEqual(writer.charged_bytes, rt.WRITER_HEADROOM + rt.ENTRY_CHARGE + 4)
                self.assertEqual((writer.root / "__partial/0000.part").read_bytes(), b"ab")
                self.assert_poisoned(writer)
        with self.writer("empty") as writer:
            row = writer.write_from_callback("empty", lambda emit: emit(b""), expected_bytes=0)
            self.assertEqual(row["sha256"], hashlib.sha256(b"").hexdigest())
            writer.finalize()
        for index, expected in enumerate((True, 1.0, -1)):
            with self.subTest(expected=expected), self.writer(f"invalid-{index}") as writer:
                with self.assertRaises(ValueError):
                    writer.write_from_callback("invalid", lambda emit: self.fail("producer called"),
                                               expected_bytes=expected)
                self.assertEqual(writer.charged_bytes, rt.WRITER_HEADROOM)
                self.assert_poisoned(writer)

    def test_nonbytes_and_caught_sink_failures_poison_completion(self):
        class BytesSubclass(bytes):
            pass
        for index, chunk in enumerate((bytearray(b"x"), memoryview(b"x"), "x", BytesSubclass(b"x"))):
            with self.subTest(chunk=type(chunk)), self.writer(str(index)) as writer:
                def producer(emit):
                    emit(b"prefix")
                    with self.assertRaisesRegex(ValueError, "immutable bytes"):
                        emit(chunk)
                    with self.assertRaisesRegex(ValueError, "failed"):
                        emit(b"must not append")
                with self.assertRaisesRegex(ValueError, "failed"):
                    writer.write_from_callback("bad", producer)
                self.assertEqual((writer.root / "__partial/0000.part").read_bytes(), b"prefix")
                self.assert_poisoned(writer)

    def test_partial_and_late_producer_exceptions_never_publish(self):
        for index, error in enumerate((RuntimeError("late producer"), KeyboardInterrupt())):
            with self.subTest(error=type(error)), self.writer(str(index)) as writer:
                def producer(emit):
                    emit(b"complete payload")
                    raise error
                with self.assertRaises(type(error)):
                    writer.write_from_callback("proof", producer, expected_bytes=16)
                self.assertEqual((writer.root / "__partial/0000.part").read_bytes(), b"complete payload")
                self.assertFalse((writer.root / "proof").exists())
                self.assertEqual(writer.charged_bytes, rt.WRITER_HEADROOM + rt.ENTRY_CHARGE + 32)
                self.assert_poisoned(writer)
                self.assertEqual(json.loads((writer.root / "__journal.jsonl").read_bytes().splitlines()[-1]),
                                 {"event": "failed", "reason": type(error).__name__})

    def test_escaped_sink_rejects_after_return_failure_and_close(self):
        for state in ("returned", "failed", "closed", "finalized"):
            with self.subTest(state=state), self.writer(state) as writer:
                sinks = []
                def producer(emit):
                    sinks.append(emit)
                    emit(b"original")
                    if state == "failed":
                        raise RuntimeError("interrupted")
                if state == "failed":
                    with self.assertRaises(RuntimeError):
                        writer.write_from_callback("proof", producer)
                else:
                    writer.write_from_callback("proof", producer)
                if state == "finalized":
                    writer.finalize()
                elif state == "closed":
                    writer.close()
                charged = writer.charged_bytes
                before = {p.relative_to(writer.root): p.read_bytes() for p in writer.root.rglob("*") if p.is_file()}
                with self.assertRaisesRegex(ValueError, "inactive"):
                    sinks[0](b"must not write through a reused descriptor")
                self.assertEqual(writer.charged_bytes, charged)
                self.assertEqual(before, {p.relative_to(writer.root): p.read_bytes() for p in writer.root.rglob("*") if p.is_file()})
                if state != "finalized":
                    self.assert_poisoned(writer)

    def test_nested_callback_and_generator_writes_keep_independent_sinks(self):
        for mode in ("callback", "iterable"):
            with self.writer(mode) as writer:
                def chunks():
                    yield b"before"
                    writer.write_from_callback("nested/inner", lambda emit: emit(b"inner"))
                    yield b"after"
                def producer(emit):
                    for chunk in chunks():
                        emit(chunk)
                if mode == "callback":
                    writer.write_from_callback("outer", producer)
                else:
                    writer.write("outer", chunks())
                self.assertEqual([row["path"] for row in writer.files], ["nested/inner", "outer"])
                writer.finalize()
            self.assertEqual((writer.root / "outer").read_bytes(), b"beforeafter")
            self.assertEqual((writer.root / "nested/inner").read_bytes(), b"inner")
        self.assertEqual((self.root / "callback/__journal.jsonl").read_bytes(),
                         (self.root / "iterable/__journal.jsonl").read_bytes())

    def test_failed_nested_write_or_active_finalization_cannot_be_swallowed(self):
        for mode in ("nested", "finalize", "stale-inner"):
            with self.subTest(mode=mode), self.writer(mode) as writer:
                def producer(emit):
                    emit(b"outer prefix")
                    try:
                        if mode == "nested":
                            writer.write("outer", iter([b"duplicate"]))
                        elif mode == "finalize":
                            writer.finalize()
                        else:
                            sinks = []
                            writer.write_from_callback("inner", lambda sink: sinks.append(sink))
                            sinks[0](b"stale")
                    except ValueError:
                        pass
                with self.assertRaisesRegex(ValueError, "failed"):
                    writer.write_from_callback("outer", producer)
                self.assertFalse((writer.root / "outer").exists())
                self.assertEqual((writer.root / "__partial/0000.part").read_bytes(), b"outer prefix")
                self.assert_poisoned(writer)


@unittest.skipUnless(sys.platform == "linux", "Linux process guard required")
class FinalCollectorProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.profile = rt.FINAL_COLLECTOR
        self.context = rt.PlanContext("a" * 64, "b" * 64, "c" * 64, self.profile.name)
        self.cpu, self.workers = 10, (11, 12, 13, 14, 15)

    def tearDown(self):
        self.tmp.cleanup()

    def request(self):
        return {"profile": asdict(self.profile), "cpu": self.cpu, "worker_cpus": list(self.workers),
                "context": asdict(self.context), "entry_monotonic": 100.0, "deadline_monotonic": 110.0,
                "launcher_rss_bytes_at_entry": 1, "command": [sys.executable, "-c", "pass"]}

    def cold_fixture(self, name="cold", mutate=lambda request, report: None):
        """Fabricated tiny history exercises the reader, never claims a real run."""
        attempt = self.root / name
        attempt.mkdir()
        with rt.BoundedEvidenceWriter(attempt / "evidence", self.profile.worker_evidence_bytes,
                                      profile_name=self.profile.name) as writer:
            writer.write_from_callback("proof", lambda emit: emit(b"synthetic"))
            manifest = writer.finalize()
        manifest_raw = (attempt / "evidence/__manifest.json").read_bytes()
        manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
        request = self.request()
        report = {key: json.loads(json.dumps(value)) for key, value in request.items() if key != "command"}
        report.update(schema="hiroute-phase-v1", status="provisional", reason="synthetic fixture",
                      worker_exit_code=0, descendants_reaped=True, sampled_group_rss_peak_bytes=0,
                      kernel_max_reaped_ru_maxrss_bytes=0, supervisor_kernel_peak_rss_bytes=0,
                      supervisor_metadata_charge_bytes_before_report=0, worker_charged_bytes=manifest["charged_bytes"],
                      largest_sample_gap_seconds=0.0, phase_wall_seconds=0.1, reaped_cpu_seconds=0.0,
                      supervisor_cpu_seconds=0.0, verified_manifest_sha256=manifest_sha,
                      verified_manifest_size_bytes=len(manifest_raw))
        mutate(request, report)
        request_raw = rt._json(request)
        report["request_sha256"] = hashlib.sha256(request_raw).hexdigest()
        report_raw = rt._json(report)
        ready_raw = rt._json({"schema": "hiroute-supervisor-decision-v1", "status": "ready",
                              "report_sha256": hashlib.sha256(report_raw).hexdigest(),
                              "report_size_bytes": len(report_raw), "manifest_sha256": manifest_sha,
                              "manifest_size_bytes": len(manifest_raw)})
        decision_raw = rt._json({"schema": "hiroute-phase-decision-v1", "status": "completed",
                                 "supervisor_exit_code": 0, "accepted_monotonic": 100.2,
                                 "supervisor_decision_sha256": hashlib.sha256(ready_raw).hexdigest()})
        for filename, raw in (("request.json", request_raw), ("result.json", report_raw),
                              ("supervisor-decision.json", ready_raw), ("decision.json", decision_raw)):
            (attempt / filename).write_bytes(raw)
        receipt = {"schema": "hiroute-caller-return-v1", "returned_monotonic": 100.5,
                   "result_sha256": hashlib.sha256(report_raw).hexdigest(),
                   "decision_sha256": hashlib.sha256(decision_raw).hexdigest(),
                   "manifest_sha256": manifest_sha, "manifest_size_bytes": len(manifest_raw)}
        return attempt, dict(report, status="completed", phase_wall_seconds=0.5, acceptance_receipt=receipt)

    def test_fixed_profile_and_all_legacy_values_are_exact(self):
        common = {"supervisor_as_bytes": 512 * rt.MiB, "poll_ms": 50, "max_sample_gap_ms": 1000}
        cases = ((rt.CAPTURE, (8 * rt.GiB, 8 * rt.GiB, 1200, 4 * rt.GiB, 16 * rt.MiB, 16 * rt.GiB, 20 * rt.GiB)),
                 (rt.REPLAY, (16 * rt.GiB, 16 * rt.GiB, 1800, 8 * rt.GiB, 16 * rt.MiB, 16 * rt.GiB, 20 * rt.GiB)),
                 (rt.BATCH_REPLAY, (16 * rt.GiB, 20 * rt.GiB, 1800, 8 * rt.GiB, 16 * rt.MiB, 16 * rt.GiB, 20 * rt.GiB)),
                 (rt.TINY_TEST, (256 * rt.MiB, 256 * rt.MiB, 2, 2 * rt.MiB, 64 * 1024, rt.MiB, rt.MiB)),
                 (self.profile, (16 * rt.GiB, 20 * rt.GiB, 3600, rt.GiB, 16 * rt.MiB, 16 * rt.GiB, 20 * rt.GiB)))
        keys = ("child_as_bytes", "group_rss_bytes", "wall_seconds", "evidence_bytes",
                "supervisor_evidence_bytes", "host_reserve_bytes", "disk_floor_bytes")
        for profile, values in cases:
            self.assertEqual(asdict(profile), dict(name=profile.name, **dict(zip(keys, values)), **common))
            self.assertIs(rt.PROFILES[profile.name], profile)
        self.assertEqual(self.profile.name, "final-collector-v1")
        self.assertEqual(self.profile.worker_evidence_bytes, 1008 * rt.MiB)

    def test_only_exact_known_profiles_accept_a_six_cpu_partition(self):
        self.assertEqual(rt._worker_cpu_mask(self.profile, self.cpu, self.workers), self.workers)
        for profile in (rt.CAPTURE, rt.REPLAY, rt.TINY_TEST, replace(self.profile, wall_seconds=3601)):
            self.assertFalse(rt._is_group_profile(profile))
            with self.assertRaisesRegex(ValueError, "only supported"):
                rt._worker_cpu_mask(profile, self.cpu, self.workers)
        invalid = (None, (), self.workers[:-1], list(self.workers), (11,) * 5,
                   (self.cpu,) + self.workers[1:], (True,) + self.workers[1:], (11.0,) + self.workers[1:])
        with patch.object(rt.subprocess, "Popen") as launch:
            for index, mask in enumerate(invalid):
                start = time.monotonic()
                attempt = self.root / str(index)
                with self.subTest(mask=mask), self.assertRaises(ValueError):
                    rt.run_phase([sys.executable], attempt_dir=attempt, profile=self.profile,
                                 cpu=self.cpu, worker_cpus=mask, context=self.context,
                                 entry_monotonic=start, deadline_monotonic=start + 1.0)
                self.assertFalse(attempt.exists())
            launch.assert_not_called()

    def test_admission_reserves_exact_memory_disk_and_inherited_affinity(self):
        reserve = 36 * rt.GiB + 512 * rt.MiB
        with patch.object(rt, "_mem_available", return_value=reserve) as memory, \
                patch.object(rt, "_disk_available", return_value=21 * rt.GiB) as disk, \
                patch.object(rt.os, "sched_getaffinity", return_value={self.cpu, *self.workers}) as affinity:
            rt._preflight(self.profile, self.root, self.cpu, self.workers)
            memory.return_value -= 1
            with self.assertRaisesRegex(ValueError, "MemAvailable"):
                rt._preflight(self.profile, self.root, self.cpu, self.workers)
            memory.return_value = reserve
            disk.return_value -= 1
            with self.assertRaisesRegex(ValueError, "disk"):
                rt._preflight(self.profile, self.root, self.cpu, self.workers)
            disk.return_value = 21 * rt.GiB
            affinity.return_value = {self.cpu, *self.workers[:-1]}
            with self.assertRaisesRegex(ValueError, "inherited affinity"):
                rt._preflight(self.profile, self.root, self.cpu, self.workers)

    def test_final_collector_keeps_uid_lock_and_exact_request_report_mask(self):
        lock_path = Path("/tmp") / f"hiroute-recorded-phase-{os.getuid()}.lock"
        lock = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            rt.fcntl.flock(lock, rt.fcntl.LOCK_EX | rt.fcntl.LOCK_NB)
            start = time.monotonic()
            with patch.object(rt.subprocess, "Popen") as launch:
                report = rt.run_phase([sys.executable], attempt_dir=self.root / "locked", profile=self.profile,
                                      cpu=self.cpu, worker_cpus=self.workers, context=self.context,
                                      entry_monotonic=start, deadline_monotonic=start + 1.0)
                launch.assert_not_called()
        finally:
            os.close(lock)
        self.assertEqual(report["status"], "unresolved")
        self.assertIn("another phase owns admission", report["reason"])
        for record in (report, json.loads((self.root / "locked/request.json").read_bytes())):
            self.assertEqual(record["cpu"], self.cpu)
            self.assertEqual(record["worker_cpus"], list(self.workers))

    def test_mock_supervisor_pins_and_samples_entire_collector_group(self):
        request = self.request()
        request.update(entry_monotonic=time.monotonic(), deadline_monotonic=time.monotonic() + 5.0)
        attempt = self.root / "mock"
        attempt.mkdir()
        (attempt / "request.json").write_bytes(rt._json(request))
        class FakeWorker:
            pid = 99999999
            returncode = None
        def launch(command, **kwargs):
            self.assertTrue(kwargs["start_new_session"])
            kwargs["preexec_fn"]()
            return FakeWorker()
        rows = {FakeWorker.pid: (os.getpid(), FakeWorker.pid, 1, 16 * rt.GiB)}
        rows.update({FakeWorker.pid + index: (FakeWorker.pid, FakeWorker.pid, 1, rt.GiB + 1)
                     for index in range(1, 5)})
        with patch.object(rt.os, "sched_getaffinity", return_value={self.cpu, *self.workers}), \
                patch.object(rt.os, "sched_setaffinity") as affinity, \
                patch.object(rt.resource, "setrlimit") as limits, patch.object(rt, "_prctl"), \
                patch.object(rt, "_mem_available", return_value=100 * rt.GiB), \
                patch.object(rt, "_disk_available", return_value=100 * rt.GiB), \
                patch.object(rt, "_processes", return_value=rows), patch.object(rt.subprocess, "Popen", launch), \
                patch.object(rt.os, "wait4", side_effect=ChildProcessError), \
                patch.object(rt.os, "killpg") as kill_group, patch.object(rt.os, "kill"):
            report = rt._supervise(request, attempt)
        self.assertEqual(affinity.call_args_list, [unittest.mock.call(0, {self.cpu}), unittest.mock.call(0, set(self.workers))])
        limits.assert_any_call(resource.RLIMIT_AS, (512 * rt.MiB, resource.getrlimit(resource.RLIMIT_AS)[1]))
        limits.assert_any_call(resource.RLIMIT_AS, (16 * rt.GiB,) * 2)
        limits.assert_any_call(resource.RLIMIT_FSIZE, (1008 * rt.MiB,) * 2)
        self.assertEqual(report["status"], "unresolved")
        self.assertIn("process-group RSS limit exceeded", report["reason"])
        self.assertEqual(report["sampled_group_rss_peak_bytes"], 20 * rt.GiB + 4)
        self.assertEqual(report["worker_cpus"], list(self.workers))
        self.assertEqual(report["cpu"], self.cpu)
        self.assertTrue(report["descendants_reaped"])
        kill_group.assert_called_once_with(FakeWorker.pid, rt.signal.SIGKILL)

    def test_cold_result_requires_retained_return_and_binds_mask_without_live_affinity(self):
        attempt, returned = self.cold_fixture()
        self.assertEqual(rt.read_phase_result(attempt)["status"], "unresolved")
        with patch.object(rt.os, "sched_getaffinity", side_effect=AssertionError("historical mask only")):
            self.assertEqual(rt.read_phase_result(attempt, successful_return=returned)["status"], "completed")
        altered = dict(returned, worker_cpus=list(reversed(self.workers)))
        self.assertEqual(rt.read_phase_result(attempt, successful_return=altered)["status"], "unresolved")
        receipt = dict(returned["acceptance_receipt"], returned_monotonic=110.0)
        altered = dict(returned, acceptance_receipt=receipt, phase_wall_seconds=10.0)
        self.assertEqual(rt.read_phase_result(attempt, successful_return=altered)["status"], "unresolved")
        self.assertEqual(rt.read_phase_result(attempt, successful_return=returned,
                                             deadline_monotonic=time.monotonic() - 1)["status"], "unresolved")
        proof = attempt / "evidence/proof"
        proof.chmod(0o600)
        proof.write_bytes(b"different")
        self.assertEqual(rt.read_phase_result(attempt, successful_return=returned)["status"], "unresolved")

    def test_cold_result_rejects_missing_rebound_or_invalid_group_masks(self):
        def both(request, report, key, value):
            request[key] = report[key] = value
        mutations = (lambda q, r: r.update(worker_cpus=list(reversed(self.workers))),
                     lambda q, r: q.pop("worker_cpus"), lambda q, r: r.pop("worker_cpus"),
                     lambda q, r: both(q, r, "worker_cpus", [self.workers[0]] * 5),
                     lambda q, r: both(q, r, "worker_cpus", [self.cpu, *self.workers[1:]]),
                     lambda q, r: both(q, r, "worker_cpus", [True, *self.workers[1:]]),
                     lambda q, r: both(q, r, "cpu", float(self.cpu)),
                     lambda q, r: both(q, r, "deadline_monotonic", 3700.1))
        for index, mutate in enumerate(mutations):
            attempt, returned = self.cold_fixture(str(index), mutate)
            with self.subTest(index=index):
                self.assertEqual(rt.read_phase_result(attempt, successful_return=returned)["status"], "unresolved")

    def test_tiny_callback_phase_retains_actual_successful_return(self):
        worker = """
import os
from experiments.time_cut_v2.recorded_real.runtime import BoundedEvidenceWriter
with BoundedEvidenceWriter(os.environ['HIROUTE_EVIDENCE_ROOT'], int(os.environ['HIROUTE_EVIDENCE_CAP_BYTES']), profile_name=os.environ['HIROUTE_PROFILE']) as writer:
    writer.write_from_callback('proof', lambda emit: emit(b'actual tiny callback'))
    writer.finalize()
"""
        entry = time.monotonic()
        attempt = self.root / "tiny"
        returned = rt.run_phase([sys.executable, "-c", worker], attempt_dir=attempt, profile=rt.TINY_TEST,
                                cpu=min(os.sched_getaffinity(0)),
                                context=replace(self.context, profile_name=rt.TINY_TEST.name),
                                entry_monotonic=entry, deadline_monotonic=entry + rt.TINY_TEST.wall_seconds)
        self.assertEqual(returned["status"], "completed", returned)
        self.assertEqual(rt.read_phase_result(attempt)["status"], "unresolved")
        self.assertEqual(rt.read_phase_result(attempt, successful_return=returned)["status"], "completed")
        self.assertEqual((attempt / "evidence/proof").read_bytes(), b"actual tiny callback")


if __name__ == "__main__":
    unittest.main()
