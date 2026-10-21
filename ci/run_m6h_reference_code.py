"""Isolated tiny REF interface checks, not real-map reference acceptance."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def main():
    if sys.version_info[:2] != (3, 11) or sys.prefix == sys.base_prefix:
        raise RuntimeError('Use the existing isolated Python 3.11 CI environment')
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE='1',
               PYTHONNOUSERSITE='1', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',
               OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
    for key in ('PYTHONOPTIMIZE', 'PYTHONHOME', 'PYTEST_ADDOPTS'):
        env.pop(key, None)
    script = """
import resource
import sys
from pathlib import Path
resource.setrlimit(resource.RLIMIT_CPU, (90, 100))
resource.setrlimit(resource.RLIMIT_AS, (2*1024**3, 2*1024**3))
def audit(event, args):
    if event in ('subprocess.Popen', 'os.system', 'os.fork', 'os.forkpty',
                 'os.posix_spawn', 'os.posix_spawnp', 'os.exec',
                 'socket.connect', 'socket.bind'):
        raise PermissionError('Tiny REF gate forbids helper processes and network')
sys.addaudithook(audit)
import pytest
import timecut5
def check_origins():
    for name, module in tuple(sys.modules.items()):
        if name == 'timecut5' or name.startswith('timecut5.'):
            if not Path(module.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()):
                raise RuntimeError('Production imports must remain in the installed wheel: ' + name)
check_origins()
result = pytest.main(sys.argv[1:])
check_origins()
raise SystemExit(result)
"""
    with tempfile.TemporaryDirectory(prefix='hiroute-ref-ci-') as temporary:
        work = Path(temporary)
        config = work / 'pytest.ini'
        config.write_text('[pytest]\naddopts = -ra\n')
        for flags, label in (([], 'normal'), (['-OO'], 'optimized')):
            report = work / (label + '.xml')
            subprocess.run([sys.executable, *flags, '-B', '-c', script,
                            '-q', '-p', 'no:cacheprovider', '-c', str(config),
                            '--junitxml=' + str(report), str(ROOT / 'tests/test_m6h_reference.py')],
                           cwd=work, env=env, check=True, timeout=150)
            suites = list(ET.parse(report).getroot().iter('testsuite'))
            if not suites or sum(int(s.get('tests', '0')) for s in suites) == 0:
                raise RuntimeError(label + ': no REF interface tests were recorded')
            if any(int(s.get(key, '0')) for s in suites for key in ('skipped', 'errors', 'failures')):
                raise RuntimeError(label + ': skipped or unsuccessful REF interface tests')
    print('Tiny REF interface checks passed in both modes; no real-map REF claim')


if __name__ == '__main__':
    main()
