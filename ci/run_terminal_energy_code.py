"""Finite installed-wheel energy gate, supported Python3.11 only."""
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
    env = dict(os.environ, HIROUTE_REQUIRE_INSTALLED_WHEEL='1', PYTHONDONTWRITEBYTECODE='1',
               OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1')
    for key in ('PYTHONPATH', 'PYTHONHOME', 'PYTHONOPTIMIZE'):
        env.pop(key, None)
    script = """
import resource, signal
resource.setrlimit(resource.RLIMIT_CPU, (90, 100))
resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3,) * 2)
signal.alarm(150)
from pathlib import Path
import sys, unittest
import hiroute, timecut5.terminal_energy as energy
legacy_root = Path(sys.argv[1]).resolve()
if not Path(hiroute.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()):
    raise RuntimeError('Production HiRoute imports must remain inside the installed wheel')
if not Path(energy.__file__).resolve().is_relative_to(legacy_root):
    raise RuntimeError('Legacy energy tests must use explicitly staged source')
suite = unittest.TestLoader().discover(SUITE, pattern='test_*.py', top_level_dir=TOP)
result = unittest.TextTestRunner(verbosity=2).run(suite)
if not result.wasSuccessful() or result.testsRun == 0 or result.skipped:
    raise SystemExit(1)
print('Finite energy gate passed; screen remains opt-in')
"""
    with tempfile.TemporaryDirectory(prefix='hiroute-energy-ci-') as temporary:
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
        script = script.replace('SUITE', repr(str(ROOT / 'tests/terminal_energy')))
        script = script.replace('TOP', repr(str(ROOT / 'tests')))
        for flags in ([], ['-OO']):
            subprocess.run([sys.executable, *flags, '-B', '-c', script, str(legacy_root)],
                           cwd=Path(temporary), env=env, check=True, timeout=165)


if __name__ == '__main__':
    main()
