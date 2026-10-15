import sys,os,json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'optimized_od06_phase2/runner'))
from cloud_adapter import run,Limits,sha,atomic
start=time.process_time()
manifest=ROOT/'experiment_manifest.json'
r=run([sys.executable,str(ROOT/'witness_worker.py'),str(ROOT/'witness_01'),sha(manifest)],output_dir=ROOT/'supervision_01',limits=Limits(wall_seconds=120,cpu_seconds=115,address_space_bytes=8*1024**3,cpu=min(os.sched_getaffinity(0))))
r['controller_cpu_seconds_including_preflight']=time.process_time()-start
atomic(ROOT/'witness_ledger.json',dict(scope='one_fresh_three_leg_replay',reservation_cpu_s=125,reservation_wall_s=123,receipt=r,charged_conservative_cpu_s=r['conservative_wait4_cpu_seconds']+r['controller_cpu_seconds_including_preflight'],next_stage_requires_independent_review=True))
print(json.dumps(r))
