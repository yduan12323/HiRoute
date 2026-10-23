"""Installed-only synthetic E2E interface gate; never a real-map E4 claim."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]

def main():
    if sys.version_info[:2]!=(3,11) or sys.prefix==sys.base_prefix:
        raise RuntimeError('Use isolated Python 3.11 environment')
    env=dict(os.environ,PYTHONPATH='',PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1',
             PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
    for key in ('PYTHONOPTIMIZE','PYTHONHOME','PYTEST_ADDOPTS'):env.pop(key,None)
    with tempfile.TemporaryDirectory(prefix='hiroute-e2e-ci-') as temporary:
        work=Path(temporary); dist=work/'dist'
        subprocess.run([sys.executable,str(ROOT/'ci/build_m5e2e_tools.py'),'--out',str(dist)],check=True,env=env)
        wheel=next(dist.glob('*.whl'))
        subprocess.run([sys.executable,'-m','pip','--isolated','install','--no-deps','--force-reinstall',str(wheel)],check=True,env=env)
        (work/'tests').mkdir()
        shutil.copytree(ROOT/'configs/m5e2e',work/'configs/m5e2e')
        for path in (ROOT/'tests').glob('test_m5e2e_*.py'):shutil.copyfile(path,work/'tests'/path.name)
        (work/'pytest.ini').write_text('[pytest]\naddopts = -ra\n')
        script='''
import resource,sys
from pathlib import Path
resource.setrlimit(resource.RLIMIT_CPU,(90,100))
resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
from experiments.m5e2e_v1.common import installed_origins
import importlib.resources
for package, filename in [('experiments.m5e2e_v1','source_identity.json'),('experiments.shandong_preprocessing_v1','installed.txt'),('hierarchy4r','bisection.cpp')]:
    if not importlib.resources.files(package).joinpath(filename).is_file():raise RuntimeError('Missing packaged resource: '+filename)
if not all(x['installed'] for x in installed_origins().values()):raise RuntimeError('Source fallback')
from experiments.mechanism_recovery_v1.run import NativeDomain
import experiments.m6h_manifest_v1.physical
import pytest
result=pytest.main(sys.argv[1:])
for name,mod in tuple(sys.modules.items()):
    if name.split('.')[0] in ('timecut5','experiments','validation','graph','hierarchy4r','scripts') and getattr(mod,'__file__',None):
        if not Path(mod.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()):raise RuntimeError(name+' source fallback')
raise SystemExit(result)
'''
        for flags,label in (([],'normal'),(['-OO'],'optimized')):
            report=work/(label+'.xml')
            subprocess.run([sys.executable,*flags,'-B','-c',script,'-q','-p','no:cacheprovider',
                '--junitxml='+str(report),str(work)],cwd=work,env=env,check=True,timeout=150)
            suites=list(ET.parse(report).getroot().iter('testsuite'))
            if not suites or not sum(int(s.get('tests','0')) for s in suites):raise RuntimeError('No tests')
            if any(int(s.get(k,'0')) for s in suites for k in ('failures','errors','skipped')):raise RuntimeError('Incomplete tests')
    print('Installed E2E synthetic interfaces passed both modes; no real-map or E4 acceptance')
if __name__=='__main__':main()
