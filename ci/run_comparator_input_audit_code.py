"""120CPU dedicated software envelope; pure fixtures, no real input/SMT work."""
import json
import os
from pathlib import Path
import resource
import subprocess
import sys

out=Path(os.environ['RUNNER_TEMP'])/'comparator-input-audit-code'
out.mkdir(parents=True,exist_ok=True)
resource.setrlimit(resource.RLIMIT_CPU,(20,20))
charged=0;records=[];fixed=60;cap=120
env={k:v for k,v in os.environ.items() if k in ('PATH','TMPDIR','LANG','LC_ALL')}
env.update(PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',
           OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
for flags in ([],['-OO']):
    if charged+16+fixed>cap:raise SystemExit('dedicated audit CI admission exhausted')
    argv=[sys.executable,*flags,'-m','unittest','discover','-s','tests',
          '-p','test_comparator_input_audit.py']
    (out/'started.json').write_text(json.dumps(dict(argv=argv,charged_prior_cpu_s=charged,reserved_cpu_s=16)))
    def limit():resource.setrlimit(resource.RLIMIT_CPU,(15,15))
    before=resource.getrusage(resource.RUSAGE_CHILDREN)
    try:
        p=subprocess.run(argv,env=env,preexec_fn=limit,timeout=45,capture_output=True,text=True)
        code,output=p.returncode,p.stdout+p.stderr
    except subprocess.TimeoutExpired as exc:
        code=124;output='Timeout: '+str(exc)
    after=resource.getrusage(resource.RUSAGE_CHILDREN)
    cost=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime+1
    charged+=cost;records.append(dict(argv=argv,cpu_s=cost,returncode=code,output=output))
    print(output,flush=True)
    temporary=out/'accounting.tmp'
    temporary.write_text(json.dumps(dict(cap_cpu_s=cap,
        fixed_setup_controller_reservation_cpu_s=fixed,charged_children_cpu_s=charged,
        inclusive_reserved_cpu_s=charged+fixed,records=records),indent=2)+'\n')
    temporary.replace(out/'accounting.json');(out/'started.json').unlink()
    if code:raise SystemExit(code)
print(json.dumps(dict(passed=True,inclusive_reserved_cpu_s=charged+fixed,cap_cpu_s=cap)))
