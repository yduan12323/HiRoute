"""180 CPU inclusive; two logical modes and at most one original -OO retry."""
import json
import os
from pathlib import Path
import resource
import subprocess
import sys

out=Path(os.environ['RUNNER_TEMP'])/'m5-drift-diagnostic'
out.mkdir(parents=True,exist_ok=True)
resource.setrlimit(resource.RLIMIT_CPU,(20,20))
env={k:v for k,v in os.environ.items() if k in ('PATH','TMPDIR','LANG','LC_ALL')}
env.update(PYTHONPATH='src',PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',
           OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
commands=[([],False,'logical-normal',16),(['-OO'],False,'logical-optimized',16),
          (['-OO'],True,'original-optimized-once',85)]
charged=0;records=[]
for flags,original,label,reservation in commands:
    if charged+reservation+60>180:raise SystemExit('diagnostic CI admission cap')
    argv=[sys.executable,*flags,'-B','tools/m5_drift_diagnostic.py','--output',str(out/label)]
    if original:argv.append('--original-process-retry')
    (out/'started.json').write_text(json.dumps(dict(argv=argv,reservation_cpu_s=reservation,
        charged_prior_cpu_s=charged,original_process_retry=original))+'\n')
    def limit():resource.setrlimit(resource.RLIMIT_CPU,(20 if original else 15,20 if original else 15))
    before=resource.getrusage(resource.RUSAGE_CHILDREN)
    try:result=subprocess.run(argv,env=env,preexec_fn=limit,timeout=180)
    except subprocess.TimeoutExpired:code=124
    else:code=result.returncode
    after=resource.getrusage(resource.RUSAGE_CHILDREN)
    cost=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime+1
    charged+=cost;records.append(dict(label=label,argv=argv,returncode=code,cpu_s=cost))
    (out/'accounting.json').write_text(json.dumps(dict(cap_cpu_s=180,setup_controller_reserved_cpu_s=60,
        charged_child_and_descendant_cpu_s=charged,inclusive_reserved_cpu_s=charged+60,records=records),indent=2)+'\n')
    (out/'started.json').unlink()
    if charged+60>180 or code:raise SystemExit(code or 1)
print(json.dumps(dict(passed=True,inclusive_reserved_cpu_s=charged+60,original_process_retries=1)))
