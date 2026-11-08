"""Bounded ordinary software CI: new bounded tiny physical fixtures; no real road inputs or old cohorts."""
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
out=Path(os.environ['RUNNER_TEMP'])/'exact-physical-code';out.mkdir(parents=True,exist_ok=True)
resource.setrlimit(resource.RLIMIT_CPU,(20,20))
python=out/'venv/bin/python';fixed,cap,charged=60,180,0
commands=[
    [sys.executable,'-m','venv',str(out/'venv')],
    [str(python),'-m','pip','--isolated','--disable-pip-version-check','install',
     '--index-url','https://pypi.org/simple','--require-hashes','--only-binary=:all:',
     '--no-deps','--no-cache-dir','-r',str(ROOT/'comparison/requirements.txt')],
]
# Keep the existing per-child and cumulative caps. Split the expanded tiny suite
# into sequential groups; an exhausted budget still stops the job, never skips.
groups=(
    # Consolidate light modules, preserving every test in both modes. Fewer
    # processes remove repeated interpreter setup and per-child accounting
    # overhead; limits and conservative admission remain unchanged.
    ('tests.test_grounded_lookup_consumer','tests.test_dag_formula_export',
     'tests.test_import_strict_candidate','tests.test_candidate_finalization',
     'tests.test_shared_leg_pilot'),
    ('tests.test_finite_leg_lookup','tests.test_folded_lookup','tests.test_cached_dag_audit'),
    ('tests.test_dag_audit_path',),
    ('tests.test_strict_bound_decision','tests.test_strict_bound_witness','tests.test_strict_witness_integration'),
    ('tests.test_incumbent_model_certificate',),
    ('tests.test_exact_physical_adapter',),
)
for flags in ([],['-OO']):
    for group in groups:commands.append([str(python),*flags,'-m','unittest',*group])
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
    if charged+reserve+fixed>cap:raise SystemExit('dedicated physical CI admission exhausted')
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
