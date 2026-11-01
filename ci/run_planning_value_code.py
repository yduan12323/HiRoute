"""180CPU-second inclusive dedicated policy CI; no real-input workers."""
import json
import os
from pathlib import Path
import resource
import subprocess
import sys

out=Path(os.environ['RUNNER_TEMP'])/'planning-value-code'
out.mkdir(parents=True,exist_ok=True)
resource.setrlimit(resource.RLIMIT_CPU,(20,20))
charged=0
records=[]
env={k:v for k,v in os.environ.items() if k in ('PATH','TMPDIR','LANG','LC_ALL')}
env.update(PYTHONPATH='src',PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',
           OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
for flags in ([],['-OO']):
    for directory,pattern in [('tests','test_planning_value_dev.py'),
                              ('tests','test_scale_pilot_control.py'),
                              ('comparison','test_planning_policies.py')]:
        if charged+16+60>180:raise SystemExit('dedicated policy CI cap')
        argv=[sys.executable,*flags,'-m','unittest','discover','-s',directory,'-p',pattern]
        (out/'started.json').write_text(json.dumps(dict(argv=argv,charged_prior_cpu_s=charged,reserved_cpu_s=16)))
        def limit():resource.setrlimit(resource.RLIMIT_CPU,(15,15))
        before=resource.getrusage(resource.RUSAGE_CHILDREN)
        result=subprocess.run(argv,env=env,preexec_fn=limit,timeout=60,capture_output=True,text=True)
        after=resource.getrusage(resource.RUSAGE_CHILDREN)
        cost=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime+1
        charged+=cost
        records.append(dict(argv=argv,cpu_s=cost,returncode=result.returncode,output=result.stdout+result.stderr))
        print(result.stdout+result.stderr,flush=True)
        (out/'accounting.json').write_text(json.dumps(dict(cap_cpu_s=180,
            fixed_setup_controller_reservation_cpu_s=60,charged_children_cpu_s=charged,
            inclusive_reserved_cpu_s=charged+60,records=records),indent=2)+'\n')
        (out/'started.json').unlink()
        if result.returncode:raise SystemExit(result.returncode)
print(json.dumps(dict(passed=True,inclusive_reserved_cpu_s=charged+60,cap_cpu_s=180)))
