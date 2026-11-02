"""Bounded ordinary software CI: independent stdlib certificate fixtures; no router or optimizer calls."""
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
out=Path(os.environ['RUNNER_TEMP'])/'road-certificate-code';out.mkdir(parents=True,exist_ok=True)
resource.setrlimit(resource.RLIMIT_CPU,(20,20))
python=out/'venv/bin/python';fixed,cap,charged=60,120,0
commands=[
    [sys.executable,'-m','venv',str(out/'venv')],
    [str(python),'-m','unittest','discover','-s','tests','-p','test_*road_certificate*.py'],
    [str(python),'-OO','-m','unittest','discover','-s','tests','-p','test_*road_certificate*.py'],
    [str(python),'-m','unittest','discover','-s','tests','-p','test_streaming_road_representation.py'],
    [str(python),'-OO','-m','unittest','discover','-s','tests','-p','test_streaming_road_representation.py'],
    [str(python),'-m','unittest','discover','-s','tests','-p','test_one_source_certificate.py'],
    [str(python),'-OO','-m','unittest','discover','-s','tests','-p','test_one_source_certificate.py']]
records=[dict(command=i,argv=a,state='unrun') for i,a in enumerate(commands)]
env={k:v for k,v in os.environ.items() if k in ('PATH','TMPDIR','LANG','LC_ALL')}
env.update(PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',
           OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')
def save():
    temporary=out/'accounting.tmp'
    temporary.write_text(json.dumps(dict(cap_cpu_s=cap,fixed_setup_controller_reservation_cpu_s=fixed,
        charged_children_cpu_s=charged,inclusive_reserved_cpu_s=charged+fixed,
        command_denominator=len(commands),records=records),indent=2)+'\n')
    temporary.replace(out/'accounting.json')
save()
for i,argv in enumerate(commands):
    reserve=46 if i==0 else 16
    if charged+reserve+fixed>cap:raise SystemExit('dedicated certificate CI admission exhausted')
    records[i].update(state='running',reserved_cpu_s=reserve);save()
    (out/'started.json').write_text(json.dumps(records[i])+'\n')
    def limit():resource.setrlimit(resource.RLIMIT_CPU,(15,15))
    before=resource.getrusage(resource.RUSAGE_CHILDREN);process=None;output='';code=125
    try:
        process=subprocess.Popen(argv,cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                 text=True,start_new_session=True,preexec_fn=limit)
        (out/'started.json').write_text(json.dumps(dict(records[i],pid=process.pid))+'\n')
        try:output=process.communicate(timeout=55)[0];code=process.returncode
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL);output=process.communicate()[0];code=124
    except BaseException as exc:output+='\n'+repr(exc)
    finally:
        if process is not None and process.poll() is None:
            os.killpg(process.pid,signal.SIGKILL);output+=process.communicate()[0]
    after=resource.getrusage(resource.RUSAGE_CHILDREN)
    cost=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime+1
    charged+=cost;records[i].update(state='passed' if code==0 else 'failed',returncode=code,cpu_s=cost,output=output)
    save();(out/'started.json').unlink();print(output,flush=True)
    if code:raise SystemExit(code)
print(json.dumps(dict(passed=True,inclusive_reserved_cpu_s=charged+fixed,cap_cpu_s=cap)))
