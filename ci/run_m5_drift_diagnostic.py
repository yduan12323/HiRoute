"""Shared180 CPU: first63.990695 charged; fix-only verification capped116.

The original process retry is never part of --verification-only. Its failed
diagnostic status and raw receipt evidence remain separate from this fix check.
"""
import json
import os
from pathlib import Path
import resource
import subprocess
import sys

verification='--verification-only' in sys.argv
cap=116 if verification else 180
out=Path(os.environ['RUNNER_TEMP'])/('m5-drift-fix-verification' if verification else 'm5-drift-diagnostic')
out.mkdir(parents=True,exist_ok=True)
resource.setrlimit(resource.RLIMIT_CPU,(20,20))
env={k:v for k,v in os.environ.items() if k in ('PATH','TMPDIR','LANG','LC_ALL')}
env.update(PYTHONPATH='src',PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',
           OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
commands=[([],False,'logical-normal',16),(['-OO'],False,'logical-optimized',16),
          (['-OO'],True,'original-optimized-once',85)]
if verification:
    commands=[([],False,'logical-normal',11),(['-OO'],False,'logical-optimized',11),
              ([],False,'collector-normal',11),(['-OO'],False,'collector-optimized',11)]
charged=0;records=[]
for flags,original,label,reservation in commands:
    if charged+reservation+60>cap:raise SystemExit('diagnostic CI admission cap')
    argv=[sys.executable,*flags,'-B','tools/m5_drift_diagnostic.py','--output',str(out/label)]
    if label.startswith('collector'):
        argv=[sys.executable,*flags,'-B','-m','unittest','discover','-s','tests','-p','test_m5_drift_capture.py']
    if original:argv.append('--original-process-retry')
    (out/'started.json').write_text(json.dumps(dict(argv=argv,reservation_cpu_s=reservation,
        charged_prior_cpu_s=charged,original_process_retry=original))+'\n')
    def limit():
        maximum=10 if verification else (20 if original else 15)
        resource.setrlimit(resource.RLIMIT_CPU,(maximum,maximum))
    before=resource.getrusage(resource.RUSAGE_CHILDREN)
    try:result=subprocess.run(argv,env=env,preexec_fn=limit,timeout=180)
    except subprocess.TimeoutExpired:code=124
    else:code=result.returncode
    after=resource.getrusage(resource.RUSAGE_CHILDREN)
    cost=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime+1
    charged+=cost;records.append(dict(label=label,argv=argv,returncode=code,cpu_s=cost))
    (out/'accounting.json').write_text(json.dumps(dict(cap_cpu_s=cap,setup_controller_reserved_cpu_s=60,
        charged_child_and_descendant_cpu_s=charged,inclusive_reserved_cpu_s=charged+60,records=records),indent=2)+'\n')
    (out/'started.json').unlink()
    if charged+60>cap or code:raise SystemExit(code or 1)
print(json.dumps(dict(passed=True,inclusive_reserved_cpu_s=charged+60,
                      original_process_retries=0 if verification else 1)))
