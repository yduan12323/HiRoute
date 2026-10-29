"""Installed-wheel, synthetic-only regression gate for opt-in portable candidates."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    if sys.version_info[:2] != (3, 11) or sys.prefix == sys.base_prefix:
        raise RuntimeError('Use the existing isolated Python3.11 CI environment')
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
               OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
    for key in ('PYTHONPATH', 'PYTHONHOME', 'PYTHONOPTIMIZE'):
        env.pop(key, None)
    script = """
from pathlib import Path
import sys, unittest
import timecut5
legacy_root = Path(sys.argv[1]).resolve()
if not Path(timecut5.__file__).resolve().is_relative_to(legacy_root):
    raise RuntimeError('Legacy portable tests must use explicitly staged source')
suite = unittest.TestLoader().discover('tests/portable_candidate', pattern='test_*.py', top_level_dir='tests')
result = unittest.TextTestRunner(verbosity=1).run(suite)
if not result.wasSuccessful() or result.testsRun == 0 or result.skipped:
    raise SystemExit(1)
print('Portable candidate checks passed; defaults remain unchanged')
"""
    with tempfile.TemporaryDirectory(prefix='hiroute-portable-ci-') as temporary:
        legacy_root = Path(temporary) / 'legacy-source'
        for source in (ROOT / 'src').rglob('*'):
            if source.is_file() and source.suffix in ('.py', '.cpp'):
                relative = source.relative_to(ROOT / 'src')
                if relative.parts[0] == 'hiroute':
                    continue
                destination = legacy_root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
        env['PYTHONPATH'] = os.pathsep.join((str(legacy_root), str(ROOT)))
        for flags in ([], ['-OO']):
            subprocess.run([sys.executable, *flags, '-B', '-c', script, str(legacy_root)],
                           cwd=ROOT, env=env, check=True, timeout=120)


if __name__ == '__main__':
    main()
