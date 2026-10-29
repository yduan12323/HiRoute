"""Installed-wheel, synthetic-only regression gate for opt-in M5 recovery."""
from collections import Counter
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def main():
    if sys.version_info[:2] != (3, 11) or sys.prefix == sys.base_prefix:
        raise RuntimeError('Use the existing isolated Python3.11 CI environment')
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
               PYTHONNOUSERSITE='1', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',
               OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
    for key in ('PYTHONPATH', 'PYTHONHOME', 'PYTHONOPTIMIZE', 'PYTEST_ADDOPTS'):
        env.pop(key, None)
    script = """
from pathlib import Path
import sys
import pytest
import hiroute, timecut5

legacy_root = Path(sys.argv[1]).resolve()
def check_origins():
    if not Path(hiroute.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()):
        raise RuntimeError('Production HiRoute imports must remain inside the installed wheel')
    for name, module in tuple(sys.modules.items()):
        if name == 'hiroute' or name.startswith('hiroute.'):
            if not Path(module.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()):
                raise RuntimeError('Production HiRoute imports must remain inside the installed wheel: ' + name)
        elif name.split('.', 1)[0] in {'timecut5', 'microplan', 'graph', 'validation'}:
            if not Path(module.__file__).resolve().is_relative_to(legacy_root):
                raise RuntimeError('Legacy recovery imports must use explicitly staged source: ' + name)

check_origins()
result = pytest.main(sys.argv[2:])
check_origins()
raise SystemExit(result)
"""
    # Keep source-audit fixtures at their established relative paths, but never
    # inherit the repository pytest configuration's pythonpath=src override.
    # Legacy packages are staged outside the wheel; hiroute remains wheel-only.
    with tempfile.TemporaryDirectory(prefix='hiroute-recovery-ci-') as temporary:
        work = Path(temporary)
        legacy_root = work / 'legacy-source'
        for source in (ROOT / 'src').rglob('*'):
            if source.is_file() and source.suffix in ('.py', '.cpp'):
                relative = source.relative_to(ROOT / 'src')
                if relative.parts[0] == 'hiroute':
                    continue
                destination = legacy_root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
        env['PYTHONPATH'] = os.pathsep.join((str(legacy_root), str(ROOT)))
        config = work / 'pytest.ini'
        config.write_text('[pytest]\naddopts = -ra\n')
        for flags, label in (([], 'normal'), (['-OO'], 'optimized')):
            report = work / (label + '.xml')
            subprocess.run([sys.executable, *flags, '-B', '-c', script,
                            str(legacy_root),
                            '-q', '-p', 'no:cacheprovider', '-c', str(config),
                            '--junitxml=' + str(report), str(ROOT / 'tests/m5d_recovery')],
                           cwd=ROOT, env=env, check=True, timeout=900)
            document = ET.parse(report).getroot()
            suites = list(document.iter('testsuite'))
            counts = Counter(case.get('classname', '<unknown>')
                             for case in document.iter('testcase'))
            print(label + ' recovery collection by module/class: ' + str(dict(sorted(counts.items()))),
                  flush=True)
            if not suites or sum(int(suite.get('tests', '0')) for suite in suites) == 0:
                raise RuntimeError(label + ': no recovery tests were recorded')
            if any(int(suite.get(key, '0')) for suite in suites
                   for key in ('skipped', 'errors', 'failures')):
                raise RuntimeError(label + ': skipped or unsuccessful recovery tests')
    print('Synthetic recovery checks passed in both modes; no real-OD or performance acceptance')


if __name__ == '__main__':
    main()
