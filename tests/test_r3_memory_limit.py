import json, os, sys, tempfile, time, unittest
from pathlib import Path
from hiroute.runtime import run_supervised, load_incumbent_receipt
ROOT=Path(__file__).resolve().parents[1]
class RSSMemoryTests(unittest.TestCase):
 def test_tree_limit_TERM_KILL_and_cold_REF_replay(self):
  from hiroute.contracts import ProblemSnapshot
  snapshot=ProblemSnapshot.from_dict(json.loads((ROOT/"tests/r0/c01_zero_stop_snapshot.json").read_text()))
  with tempfile.TemporaryDirectory() as td:
   d=Path(td); receipt=d/"incumbent.json"; pidfile=d/"grandchild.pid"
   worker=d/"worker.py"; child=d/"grandchild.py"
   child.write_text("""import os,signal,time
from pathlib import Path
signal.signal(signal.SIGTERM, signal.SIG_IGN)
Path(os.environ["PIDFILE"]).write_text(str(os.getpid()))
chunks=[]
while True:
 chunks.append(bytearray(4*1024*1024))
 chunks[-1][0]=1
 time.sleep(.02)
""")
   worker.write_text("""import os,subprocess,sys
from hiroute.runtime import save_incumbent_receipt
save_incumbent_receipt(sys.argv[1],semantic_problem_id=sys.argv[2],
 payload={"semantic_problem_id":sys.argv[2],"key":["1","0",0,[]],"actions":[],"charges_kwh":[],"status":"attained_feasible_incumbent"})
child=subprocess.Popen([sys.executable,sys.argv[3]],env={**os.environ,"PIDFILE":sys.argv[4]})
child.wait()
""")
   env={**os.environ,"PYTHONPATH":str(ROOT/"src")}
   run=run_supervised([sys.executable,str(worker),str(receipt),snapshot.semantic_problem_id,str(child),str(pidfile)],
      timeout_s=10,term_grace_s=.15,cwd=ROOT,env=env,memory_limit_bytes=96*1024*1024,memory_poll_s=.01)
   self.assertTrue(run.memory_limited,(run.returncode,run.rss_peak_bytes))
   self.assertTrue(run.term_sent); self.assertTrue(run.kill_sent)
   self.assertGreater(run.rss_peak_bytes,96*1024*1024)
   saved=load_incumbent_receipt(receipt,expected_semantic_problem_id=snapshot.semantic_problem_id)
   self.assertEqual(saved["key"],["1","0",0,[]])
   import importlib.util
   spec=importlib.util.spec_from_file_location("ref_replay",ROOT/"validation/reference5/model.py")
   ref=importlib.util.module_from_spec(spec)
   sys.modules[spec.name]=ref
   spec.loader.exec_module(ref)
   case={"case_id":"C01_MEMORY_LIMIT","origin":"o","destination":"z","H_ref":0,"start_time_s":"0","initial_energy_kwh":"10","capacity_kwh":"10","minimum_energy_kwh":"0","reserve_kwh":"0","consumption_kwh_per_m":"1","overhead_s":"1","lambda_stop_s":"1","initial_remaining_schedule":0,"schedule":None,"sites":{},"charging_segments":[],"edges":[{"source":"o","target":"z","time_s":"1","length_m":"1","id":"direct"}]}
   replay=ref.replay_witness(case,saved["actions"],saved["charges_kwh"])
   self.assertEqual(tuple(replay["lex_key"]),(1,0,0,()))
   evidence=os.environ.get("A8_EVIDENCE_DIR")
   if evidence:
    out=Path(evidence); out.mkdir(parents=True,exist_ok=True)
    (out/"incumbent.json").write_bytes(receipt.read_bytes())
    (out/"memory_result.json").write_text(json.dumps({"execution_status":"memory_limit",
      "memory_limited":run.memory_limited,"timed_out":run.timed_out,"term_sent":run.term_sent,
      "kill_sent":run.kill_sent,"returncode":run.returncode,"rss_peak_bytes":run.rss_peak_bytes,
      "memory_limit_bytes":96*1024*1024,"cold_read_key":saved["key"],
      "ref_replay_key":[str(replay["lex_key"][0]),str(replay["lex_key"][1]),
       replay["lex_key"][2],[list(x) for x in replay["lex_key"][3]]],
      "grandchild_pid":pidfile.read_text().strip()},
      sort_keys=True,indent=2)+"\n")
    (out/"incumbent_ref_replay.txt").write_text("Cold-read checksum and semantic ID validated; REF5 replay key="+str(tuple(replay["lex_key"]))+"\n")
   print("A8_STATUS=memory_limit rss_peak_bytes="+str(run.rss_peak_bytes)+" TERM="+str(run.term_sent)+" KILL="+str(run.kill_sent))
   pid=int(pidfile.read_text()); deadline=time.monotonic()+2
   while time.monotonic()<deadline:
    try:
     state=Path(f"/proc/{pid}/stat").read_text().split()[2]
     if state=="Z": break
    except FileNotFoundError: break
    time.sleep(.02)
   else: self.fail("memory worker grandchild still live")
   if Path(f"/proc/{pid}/stat").exists(): self.assertEqual(Path(f"/proc/{pid}/stat").read_text().split()[2],"Z")
