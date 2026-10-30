import json, os, signal, subprocess, sys, tempfile, threading, time, unittest
from pathlib import Path
from hiroute.contracts import ProblemSnapshot
from hiroute.runtime import (ReceiptError, load_incumbent_receipt,
                             run_supervised, save_incumbent_receipt)
ROOT = Path(__file__).resolve().parents[1]
C01 = ROOT / "tests/r0/c01_zero_stop_snapshot.json"
import importlib.util
_ref_spec = importlib.util.spec_from_file_location("hiroute_ref5_model", ROOT / "validation/reference5/model.py")
_ref_model = importlib.util.module_from_spec(_ref_spec)
sys.modules[_ref_spec.name] = _ref_model
_ref_spec.loader.exec_module(_ref_model)
replay_witness = _ref_model.replay_witness
class TestR3OSSupervisor(unittest.TestCase):
    def test_os_timeout_without_incumbent_does_not_create_recoverable_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            receipt=root/"never-written.json"
            worker=root/"no-incumbent.py"
            worker.write_text(r"""
import subprocess, sys, time
subprocess.Popen([sys.executable, "-c",
    "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)"])
time.sleep(60)
""")
            env=os.environ.copy()
            result=run_supervised([sys.executable,str(worker)],timeout_s=.4,
                                  term_grace_s=.05,cwd=str(ROOT),env=env)
            self.assertTrue(result.timed_out)
            self.assertTrue(result.term_sent)
            self.assertTrue(result.kill_sent)
            self.assertNotEqual(result.returncode,0)
            self.assertFalse(receipt.exists())
            self.assertEqual(list(root.iterdir()),[worker])

    def test_c21_os_kill_during_no_seed_search_has_no_result_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = json.loads(C01.read_text())
            raw.pop("semantic_problem_id", None)
            snapshot = ProblemSnapshot.from_dict(raw)
            problem = root / "no-seed.json"
            output = root / "result.json"
            ready = root / "search-entered"
            problem.write_text(json.dumps(snapshot.to_dict()))
            worker = root / "no-seed-worker.py"
            worker.write_text(r"""
import json, signal, sys, time
from pathlib import Path
from unittest.mock import patch
signal.signal(signal.SIGTERM, signal.SIG_IGN)
from hiroute.contracts import ProblemSnapshot, SolverConfig
from hiroute.exact import search
from hiroute.exact.search import solve_snapshot
snapshot = ProblemSnapshot.from_dict(json.loads(Path(sys.argv[1]).read_text()))
config = SolverConfig("flat", "none", "bounded_time_cut_v2", "none", "none", "none",
                      "full_lexicographic_J_Q_H_Pi")
real = search.terminal_optimize
def delayed(*args, **kwargs):
    Path(sys.argv[3]).write_text("entered")
    time.sleep(60)
    return real(*args, **kwargs)
with patch("hiroute.exact.search.terminal_optimize", side_effect=delayed):
    result = solve_snapshot(snapshot, config)
Path(sys.argv[2]).write_text(json.dumps(result))
""")
            env = os.environ.copy()
            env["PYTHONPATH"] = os.environ.get(
                "HIR_ROUTE_TEST_PYTHONPATH", str(ROOT / "src"))
            outcome = {}
            def supervise():
                outcome["result"] = run_supervised(
                    [sys.executable, str(worker), str(problem), str(output), str(ready)],
                    timeout_s=10, term_grace_s=.05, cwd=str(ROOT), env=env,
                    receipt_path=root / "run-receipt.json",
                    run_identity={"case": "C21-no-seed-os-interruption"})
            supervisor = threading.Thread(target=supervise, daemon=True)
            supervisor.start()
            deadline = time.monotonic() + 15
            while supervisor.is_alive() and not ready.exists() and time.monotonic() < deadline:
                time.sleep(.01)
            supervisor.join(timeout=15)
            self.assertFalse(supervisor.is_alive(), "supervisor did not finish its bounded cleanup")
            self.assertTrue(ready.exists(), "worker never entered the blocked search hook")
            result = outcome["result"]
            self.assertTrue(result.timed_out)
            self.assertTrue(result.term_sent)
            self.assertTrue(result.kill_sent)
            self.assertFalse(output.exists())
            self.assertNotEqual(result.returncode, 0)
            record = json.loads((root / "run-receipt.json").read_text())
            self.assertEqual(record["execution_status"], "time_limit")
            self.assertEqual(record["mathematical_status"], "unknown")
            self.assertEqual(record["verification_status"], "not_run")

    def test_supervisor_uses_resource_caps_without_provenance_gates(self):
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / "run.json"
            result = run_supervised(
                [sys.executable, "-c", "print('bounded')"],
                timeout_s=10, cpu_limit_s=1,
                memory_limit_bytes=128 * 1024 * 1024,
                receipt_path=receipt)
            record = json.loads(receipt.read_text())
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout.strip(), b"bounded")
            self.assertEqual(record["status"], "completed")
            self.assertEqual(record["execution_status"], "completed")
            self.assertIsNone(record["mathematical_status"])
            self.assertEqual(record["cpu_limit_s"], 1)
            self.assertEqual(record["memory_limit_bytes"], 128 * 1024 * 1024)
            self.assertNotIn("source_sha256", record)
            self.assertNotIn("budget_id", record)

    def test_parent_audit_receipt_and_cpu_limit_kill_are_atomic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            worker = root / "cpu-worker.py"
            receipt = root / "run-receipt.json"
            worker.write_text(r"""
import signal, time
signal.signal(signal.SIGTERM, signal.SIG_IGN)
while True:
    pass
""")
            result = run_supervised(
                [sys.executable, str(worker)], timeout_s=5, term_grace_s=.05,
                cwd=str(root), memory_limit_bytes=512 * 1024 * 1024,
                cpu_limit_s=.15, memory_poll_s=.01, receipt_path=receipt,
                run_identity={"purpose": "fixture-test"})
            record = json.loads(receipt.read_text())
            self.assertTrue(result.cpu_limited)
            self.assertTrue(result.term_sent)
            self.assertTrue(result.kill_sent)
            self.assertEqual(record["schema"], "hiroute.supervised_run.v1")
            self.assertEqual(record["status"], "cpu_limit")
            self.assertEqual(record["execution_status"], "cpu_limit")
            self.assertEqual(record["mathematical_status"], "unknown")
            self.assertEqual(record["verification_status"], "not_run")
            self.assertEqual(record["argv"], [sys.executable, str(worker)])
            self.assertEqual(record["run_identity"]["purpose"], "fixture-test")
            self.assertEqual(record["process_group_id"], record["pid"])
            self.assertIsNotNone(record["started_at"])
            self.assertIsNotNone(record["finished_at"])
            self.assertGreaterEqual(record["cpu_peak_s"], .15)
            self.assertLessEqual(record["memory_limit_bytes"], 512 * 1024 * 1024)

    def test_parent_audit_receipt_enforces_small_rss_cap_and_reaps_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            worker = root / "rss-worker.py"
            receipt = root / "run-receipt.json"
            worker.write_text(r"""
import signal, time
signal.signal(signal.SIGTERM, signal.SIG_IGN)
blocks = []
while True:
    blocks.append(bytearray(4 * 1024 * 1024))
    time.sleep(.01)
""")
            cap = 128 * 1024 * 1024
            result = run_supervised(
                [sys.executable, str(worker)], timeout_s=5, term_grace_s=.05,
                cwd=str(root), memory_limit_bytes=cap, memory_poll_s=.01,
                receipt_path=receipt,
                run_identity={"case": "tiny-rss-cap"})
            record = json.loads(receipt.read_text())
            self.assertTrue(result.memory_limited)
            self.assertTrue(result.term_sent)
            self.assertEqual(record["status"], "memory_limit")
            self.assertEqual(record["execution_status"], "memory_limit")
            self.assertEqual(record["mathematical_status"], "unknown")
            self.assertEqual(record["verification_status"], "not_run")
            self.assertGreater(record["rss_peak_bytes"], cap)
            self.assertEqual(record["process_group_id"], record["pid"])
            self.assertIsNotNone(result.returncode)

    def test_poll_interval_preserves_wall_cpu_and_rss_enforcement(self):
        identity = {"purpose": "bounded-resource-supervision-fixture"}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            worker = root / "wall-worker.py"
            receipt = root / "wall-receipt.json"
            worker.write_text(r"""
import signal, subprocess, sys, time
subprocess.Popen([sys.executable, "-c", "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)"])
signal.signal(signal.SIGTERM, signal.SIG_IGN)
time.sleep(60)
""")
            result = run_supervised(
                [sys.executable, str(worker)], timeout_s=.4, cpu_limit_s=10,
                memory_limit_bytes=512 * 1024 * 1024, process_address_space_limit_bytes=512 * 1024 * 1024, term_grace_s=.05,
                memory_poll_s=.1, receipt_path=receipt, run_identity=identity,
                cwd=str(root), env=os.environ.copy())
            self.assertTrue(result.timed_out)
            self.assertTrue(result.term_sent)
            self.assertTrue(result.kill_sent)
            self.assertEqual(json.loads(receipt.read_text())["execution_status"], "time_limit")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            worker = root / "cpu-worker.py"
            receipt = root / "cpu-receipt.json"
            worker.write_text("import signal\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\nwhile True: pass\n")
            result = run_supervised(
                [sys.executable, str(worker)], timeout_s=5, cpu_limit_s=.15,
                memory_limit_bytes=512 * 1024 * 1024, process_address_space_limit_bytes=512 * 1024 * 1024, term_grace_s=.05,
                memory_poll_s=.1, receipt_path=receipt, run_identity=identity,
                cwd=str(root), env=os.environ.copy())
            self.assertTrue(result.cpu_limited)
            self.assertTrue(result.term_sent)
            self.assertTrue(result.kill_sent)
            self.assertEqual(json.loads(receipt.read_text())["execution_status"], "cpu_limit")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            worker = root / "rss-worker.py"
            receipt = root / "rss-receipt.json"
            worker.write_text("import signal,subprocess,sys,time\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\nsubprocess.Popen([sys.executable, '-c', 'import time; x=bytearray(72*1024*1024); time.sleep(60)'])\nx=bytearray(72*1024*1024)\ntime.sleep(60)\n")
            cap = 128 * 1024 * 1024
            result = run_supervised(
                [sys.executable, str(worker)], timeout_s=5, cpu_limit_s=10,
                memory_limit_bytes=cap, process_address_space_limit_bytes=cap, term_grace_s=.05, memory_poll_s=.1,
                receipt_path=receipt, run_identity=identity, cwd=str(root), env=os.environ.copy())
            self.assertTrue(result.memory_limited)
            self.assertTrue(result.term_sent)
            self.assertEqual(json.loads(receipt.read_text())["execution_status"], "memory_limit")
            self.assertGreater(result.rss_peak_bytes, cap)

    def test_cold_read_rejects_missing_and_unsupported_schema_receipts(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"receipt.json"
            with self.assertRaisesRegex(ReceiptError,"cannot be decoded"):
                load_incumbent_receipt(path,expected_semantic_problem_id="p")
            path.write_text(json.dumps({"schema":"future.schema","semantic_problem_id":"p",
                                        "payload":{},"sha256":"0"*64}))
            with self.assertRaisesRegex(ReceiptError,"unsupported receipt schema"):
                load_incumbent_receipt(path,expected_semantic_problem_id="p")
    def test_os_timeout_kills_group_and_saved_incumbent_replays_with_ref(self):
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp)
            problem, receipt, pid_file = temp/"c01.json", temp/"incumbent.json", temp/"grandchild.pid"
            raw = json.loads(C01.read_text()); raw.pop("semantic_problem_id", None)
            snapshot = ProblemSnapshot.from_dict(raw); problem.write_text(json.dumps(snapshot.to_dict()))
            worker = temp/"worker.py"
            worker.write_text(r"""
import json, os, subprocess, sys, time
from pathlib import Path
from hiroute.contracts import ProblemSnapshot, SolverConfig
from hiroute.exact.search import solve_snapshot
from hiroute.runtime import save_incumbent_receipt
snapshot = ProblemSnapshot.from_dict(json.loads(Path(sys.argv[1]).read_text()))
config = SolverConfig("flat", "none", "bounded_time_cut_v2", "none", "none", "none",
                      "full_lexicographic_J_Q_H_Pi")
receipt, pid_file = Path(sys.argv[2]), Path(sys.argv[3])
def persist(incumbent):
    key = incumbent["key"]
    row = {"semantic_problem_id": snapshot.semantic_problem_id,
           "key": [str(key[0]), str(key[1]), key[2], [list(x) for x in key[3]]],
           "actions": [list(x) for x in key[3]], "charges_kwh": [],
           "status": "attained_feasible_incumbent"}
    save_incumbent_receipt(receipt, semantic_problem_id=snapshot.semantic_problem_id,
                           payload=row)
    child = subprocess.Popen([sys.executable, "-c",
        "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)"])
    pid_file.write_text(str(child.pid))
solve_snapshot(snapshot, config, on_incumbent=persist)
time.sleep(60)
""")
            env = os.environ.copy(); env["PYTHONPATH"] = os.environ.get("HIR_ROUTE_TEST_PYTHONPATH", str(ROOT / "src"))
            result = run_supervised([sys.executable, str(worker), str(problem), str(receipt), str(pid_file)],
                                    timeout_s=3, term_grace_s=.15, cwd=str(ROOT), env=env)
            self.assertTrue(result.timed_out, (result.returncode, result.stderr.decode(errors="replace"))); self.assertTrue(result.term_sent); self.assertTrue(result.kill_sent)
            self.assertIn(result.returncode, (-signal.SIGTERM, -signal.SIGKILL))
            saved = load_incumbent_receipt(
                receipt, expected_semantic_problem_id=snapshot.semantic_problem_id)
            self.assertEqual(saved["semantic_problem_id"], snapshot.semantic_problem_id)
            self.assertEqual(saved["key"], ["1", "0", 0, []])
            self.assertEqual(saved["status"], "attained_feasible_incumbent")
            ref_case = {
                "case_id": "C01_OS_TIMEOUT_RECEIPT_REPLAY", "origin": "o", "destination": "z", "H_ref": 0,
                "start_time_s": "0", "initial_energy_kwh": "10", "capacity_kwh": "10",
                "minimum_energy_kwh": "0", "reserve_kwh": "0", "consumption_kwh_per_m": "1",
                "overhead_s": "1", "lambda_stop_s": "1", "initial_remaining_schedule": 0,
                "schedule": None, "sites": {}, "charging_segments": [],
                "edges": [{"source":"o","target":"z","time_s":"1","length_m":"1","id":"direct"}],
            }
            replay = replay_witness(ref_case, saved["actions"], saved["charges_kwh"])
            key = [str(replay["lex_key"][0]), str(replay["lex_key"][1]), replay["lex_key"][2],
                   [list(x) for x in replay["lex_key"][3]]]
            self.assertEqual(key, saved["key"]); self.assertEqual(str(replay["terminal_energy_kwh"]), "9")
            pid = int(pid_file.read_text()); deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                try: state = Path(f"/proc/{pid}/stat").read_text().split()[2]
                except FileNotFoundError: break
                if state == "Z": break
                time.sleep(.02)
            else: self.fail("grandchild remained live after process-group kill")
            if Path(f"/proc/{pid}/stat").exists():
                self.assertEqual(Path(f"/proc/{pid}/stat").read_text().split()[2], "Z")
    def test_receipt_cold_read_rejects_tampering_truncation_and_wrong_problem(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "incumbent.json"
            payload = {"key": ["1", "0", 0, []], "actions": [], "charges_kwh": []}
            save_incumbent_receipt(path, semantic_problem_id="problem-a", payload=payload)
            self.assertEqual(load_incumbent_receipt(
                path, expected_semantic_problem_id="problem-a"), payload)
            with self.assertRaisesRegex(ReceiptError, "different semantic"):
                load_incumbent_receipt(path, expected_semantic_problem_id="problem-b")
            envelope = json.loads(path.read_text())
            envelope["payload"]["key"][0] = "2"
            path.write_text(json.dumps(envelope))
            with self.assertRaisesRegex(ReceiptError, "checksum"):
                load_incumbent_receipt(path, expected_semantic_problem_id="problem-a")
            path.write_text("{partial")
            with self.assertRaisesRegex(ReceiptError, "cannot be decoded"):
                load_incumbent_receipt(path, expected_semantic_problem_id="problem-a")

    def test_receipt_replace_failure_preserves_previous_checkpoint(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "incumbent.json"
            first = {"key": ["1", "0", 0, []]}
            save_incumbent_receipt(path, semantic_problem_id="problem-a", payload=first)
            with patch("hiroute.runtime.os.replace", side_effect=OSError("injected replace fault")):
                with self.assertRaisesRegex(OSError, "injected"):
                    save_incumbent_receipt(path, semantic_problem_id="problem-a",
                                           payload={"key": ["2", "0", 0, []]})
            self.assertEqual(load_incumbent_receipt(
                path, expected_semantic_problem_id="problem-a"), first)
            self.assertEqual([p.name for p in Path(tmp).iterdir()], ["incumbent.json"])

    def test_successful_leader_exit_cleans_remaining_group_descendants(self):
        with tempfile.TemporaryDirectory() as tmp:
            pid_file = Path(tmp) / "grandchild.pid"
            worker = (
                "import subprocess,sys; "
                "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'], "
                "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); "
                "open(sys.argv[1], 'w').write(str(p.pid))"
            )
            result = run_supervised([sys.executable, "-c", worker, str(pid_file)],
                                    timeout_s=3, term_grace_s=.1, memory_poll_s=.01)
            self.assertEqual(result.returncode, 0)
            self.assertFalse(result.timed_out)
            self.assertTrue(result.term_sent)
            self.assertTrue(pid_file.exists())
            pid = int(pid_file.read_text())
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                try:
                    state = Path(f"/proc/{pid}/stat").read_text().split()[2]
                except FileNotFoundError:
                    break
                if state == "Z":
                    break
                time.sleep(.02)
            else:
                self.fail("background descendant remained live after successful leader exit")

    def test_supervisor_returns_normal_worker_output_without_timeout(self):
        result = run_supervised([sys.executable, "-c", "print('ok')"],
                                timeout_s=2, term_grace_s=.1)
        self.assertFalse(result.timed_out)
        self.assertFalse(result.term_sent)
        self.assertFalse(result.kill_sent)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), b"ok")

if __name__ == "__main__": unittest.main()
