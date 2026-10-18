"""Installed-wheel, synthetic-only regression gate for opt-in portable candidates."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    if sys.version_info[:2] != (3, 11) or sys.prefix == sys.base_prefix:
        raise RuntimeError('Use the existing isolated Python3.11 CI environment')
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE='1',
               OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
    env.pop('PYTHONOPTIMIZE', None)
    script = """
from pathlib import Path
import sys, unittest
import timecut5
if not Path(timecut5.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()):
    raise RuntimeError('Production imports must remain inside the installed wheel')
suite = unittest.TestLoader().discover('tests/portable_candidate', pattern='test_*.py', top_level_dir='tests')
result = unittest.TextTestRunner(verbosity=1).run(suite)
if not result.wasSuccessful() or result.testsRun == 0 or result.skipped:
    raise SystemExit(1)
print('Portable candidate checks passed; defaults remain unchanged')
"""
    for flags in ([], ['-OO']):
        subprocess.run([sys.executable, *flags, '-B', '-c', script],
                       cwd=ROOT, env=env, check=True, timeout=120)


if __name__ == '__main__':
    main()
