"""Linux CI for synthetic bootstrap, receipt epoch and collector boundaries."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MODULE_GROUPS = (
    ('tests.test_c01_variant_scope','tests.test_c01_d0_bootstrap','tests.test_suffix_single_block_limit'),
    ('tests.test_receipt_epoch','tests.test_receipt_epoch_origin'),
    ('tests.test_suffix_window_receipts','tests.test_suffix_final_collector'),
)


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
suite = unittest.TestLoader().loadTestsFromNames(sys.argv[1:])
result = unittest.TextTestRunner(verbosity=1).run(suite)
if not result.wasSuccessful() or result.testsRun == 0 or result.skipped:
    raise SystemExit(1)
print('Bootstrap/one-block code boundaries passed; no real-population execution')
"""
    for flags in ([], ['-OO']):
        for modules in MODULE_GROUPS:
            subprocess.run([sys.executable, *flags, '-B', '-c', script, *modules],
                           cwd=ROOT, env=env, check=True, timeout=120)


if __name__ == '__main__':
    main()
