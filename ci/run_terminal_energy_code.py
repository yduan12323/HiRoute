"""Finite installed-wheel energy gate, supported Python3.11 only."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]

def main():
    if sys.version_info[:2]!=(3,11) or sys.prefix==sys.base_prefix:
        raise RuntimeError('Use the existing isolated Python3.11 CI environment')
    env=dict(os.environ,PYTHONPATH=str(ROOT),PYTHONDONTWRITEBYTECODE='1',
        OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
    env.pop('PYTHONOPTIMIZE',None)
    script="""
import resource,signal
resource.setrlimit(resource.RLIMIT_CPU,(90,100));resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,)*2);signal.alarm(150)
from pathlib import Path
import sys,unittest
import timecut5.terminal_energy as energy
if not Path(energy.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()):
    raise RuntimeError('Energy imports must originate inside installed wheel')
suite=unittest.TestLoader().discover(SUITE,pattern='test_*.py',top_level_dir=TOP)
r=unittest.TextTestRunner(verbosity=2).run(suite)
if not r.wasSuccessful() or r.testsRun==0 or r.skipped:raise SystemExit(1)
print('Finite installed energy gate passed; screen remains opt-in')
""".replace('SUITE',repr(str(ROOT/'tests/terminal_energy'))).replace('TOP',repr(str(ROOT/'tests')))
    with tempfile.TemporaryDirectory(prefix='hiroute-installed-energy-') as outside:
        for flags in ([],['-OO']):
            subprocess.run([sys.executable,*flags,'-B','-c',script],cwd=outside,env=env,check=True,timeout=165)
if __name__=='__main__':main()
