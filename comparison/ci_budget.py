"""Bound this dedicated CI's setup+tests, with cumulative child-CPU receipts.

Explicit CPU soft/hard limits protect controller and child processes. Before
each command reserve its full remaining allowance; all commands are sequential.
Only binary wheels are installed. Solver calls are in-process, single-threaded.
"""
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

out=Path(os.environ['RUNNER_TEMP'])/'independent-comparator-gate'
out.mkdir(parents=True,exist_ok=True)
budget,charged,FIXED=120,0,60
resource.setrlimit(resource.RLIMIT_CPU,(20,20))
records=[]
python=out/'venv/bin/python'
commands=[
    [sys.executable,'-m','venv',str(out/'venv')],
    [str(python),'-m','pip','--isolated','--disable-pip-version-check','install',
     '--index-url','https://pypi.org/simple','--require-hashes','--only-binary=:all:',
     '--no-deps','--no-cache-dir','-r','comparison/requirements.txt'],
    [str(python),'-m','unittest','discover','-s','comparison','-p','test_gate.py'],
    [str(python),'comparison/run_gate.py','--output',str(out/'normal')],
    [str(python),'-OO','-m','unittest','discover','-s','comparison','-p','test_gate.py'],
    [str(python),'-OO','comparison/run_gate.py','--output',str(out/'optimized')],
]
env={k:v for k,v in os.environ.items() if k in ('PATH','TMPDIR','LANG','LC_ALL')}
env.update(PYTHONPATH='src',PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',
           OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
for number,argv in enumerate(commands):
    left=budget-charged
    reservation=46 if number==0 else 16
    if left<reservation:raise SystemExit('dedicated CI CPU budget exhausted')
    def limit():
        resource.setrlimit(resource.RLIMIT_CPU,(15,15))
    b=resource.getrusage(resource.RUSAGE_CHILDREN);start=time.monotonic()
    (out/'started.json').write_text(json.dumps(dict(command=number,argv=argv,
        charged_prior_cpu_s=charged,command_reservation_cpu_s=reservation))+'\n')
    try:
        p=subprocess.run(argv,env=env,preexec_fn=limit,timeout=240)
        code=p.returncode
    except subprocess.TimeoutExpired:
        code=124
    a=resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu=a.ru_utime+a.ru_stime-b.ru_utime-b.ru_stime+1
    charged+=cpu;records.append(dict(argv=argv,cpu_s=cpu,wall_s=time.monotonic()-start,returncode=code))
    (out/'accounting.json').write_text(json.dumps(dict(cap_cpu_s=180,fixed_setup_controller_reservation_cpu_s=FIXED,
        charged_child_and_tails_cpu_s=charged,inclusive_reserved_cpu_s=charged+FIXED,records=records),indent=2)+'\n')
    (out/'started.json').unlink()
    if code:raise SystemExit(code)
print(json.dumps(dict(gate='passed',inclusive_reserved_cpu_s=charged+FIXED,cap_cpu_s=180)))
