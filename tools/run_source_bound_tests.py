"""Run only tiny regression modules and bind their log to a clean source commit.

Use under shared_pilot_budget.py; this receipt does not replace CPU accounting.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys
from run_shared_leg_pilot import ROOT,source,atomic,sha
from run_grounded_lookup_consumer import environment

p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--optimized',action='store_true');p.add_argument('--collect',action='store_true');a=p.parse_args()
before=source()
if before['dirty']:raise SystemExit('source-bound regression requires a clean commit')
a.output.mkdir(exist_ok=False)
identity=environment();argv=[sys.executable,*(['-OO'] if a.optimized else []),'-m','unittest',
    'tests.test_exact_physical_adapter','tests.test_exact_leg_table','tests.test_shared_leg_pilot','tests.test_grounded_lookup_consumer','tests.test_finite_leg_lookup','tests.test_dag_formula_export','tests.test_dag_audit_path','tests.test_cached_dag_audit','tests.test_incumbent_model_certificate','tests.test_folded_lookup']
commands=[argv]
if a.collect:
    commands=[[sys.executable,'-m','pytest','--collect-only','-q'],
              [sys.executable,'-m','pytest','--collect-only','-q','tests/test_grounded_lookup_consumer.py']]
atomic(a.output/'started.json',dict(source=before,environment=identity,commands=commands,
    PYTHONPATH=os.environ.get('PYTHONPATH')))
code=0;results=[]
with (a.output/'tests.log').open('x') as log:
    for command in commands:
        log.write('COMMAND: '+repr(command)+'\n');log.flush()
        code=subprocess.call(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        results.append(dict(command=command,returncode=code))
        if code:break
after=source();unchanged=before==after and environment()==identity
atomic(a.output/'result.json',dict(source_before=before,source_after=after,environment=identity,
    unchanged=unchanged,returncode=code,log_sha256=sha(a.output/'tests.log'),commands=results,PYTHONPATH=os.environ.get('PYTHONPATH')))
print((a.output/'tests.log').read_text())
raise SystemExit(code if unchanged else 75)
