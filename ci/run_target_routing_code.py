"""Optional legacy target-routing tests with core imports from the installed wheel."""
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
import resource, sys, unittest
resource.setrlimit(resource.RLIMIT_CPU, (90, 100))
import hiroute, microplan.routing, timecut5.routing_config
legacy_root = Path(sys.argv[1]).resolve()
if not Path(hiroute.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()):
    raise RuntimeError('Production HiRoute imports must remain inside the installed wheel')
for module in (microplan.routing, timecut5.routing_config):
    if not Path(module.__file__).resolve().is_relative_to(legacy_root):
        raise RuntimeError('Optional legacy routing tests must use explicitly staged source')
suite = unittest.TestLoader().discover('tests/target_routing', pattern='test_*.py', top_level_dir='tests')
result = unittest.TextTestRunner(verbosity=2).run(suite)
if not result.wasSuccessful() or result.testsRun == 0 or result.skipped:
    raise SystemExit(1)
print('Finite optional legacy target-routing gate passed; hiroute remains wheel-only')
"""
    with tempfile.TemporaryDirectory(prefix='hiroute-routing-ci-') as temporary:
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
        env['HIROUTE_LEGACY_TEST_SOURCE_ROOT'] = str(legacy_root)
        for flags in ([], ['-OO']):
            subprocess.run([sys.executable, *flags, '-B', '-c', script, str(legacy_root)],
                           cwd=ROOT, env=env, check=True, timeout=180)


if __name__ == '__main__':
    main()
