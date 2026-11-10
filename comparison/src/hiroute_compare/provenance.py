"""Per-run verifier identity; no frozen numerical source gate."""
import hashlib
import importlib.metadata
from pathlib import Path
import subprocess
import sys


def source():
    package = Path(__file__).resolve().parent
    # Preserve the historical adapter's git provenance when used in a checkout.
    for root in package.parents:
        if (root / '.git').exists():
            def git(*args):
                return subprocess.check_output(['git', *args], cwd=root, text=True).strip()
            return dict(commit=git('rev-parse', 'HEAD'), dirty=bool(git('status', '--porcelain')))
    h = hashlib.sha256()
    for path in sorted(package.glob('*.py')):
        h.update(path.name.encode() + b'\0' + path.read_bytes() + b'\0')
    return dict(package='hiroute-compare', version=importlib.metadata.version('hiroute-compare'),
                code_sha256=h.hexdigest(), python=sys.version, dirty=False,
                z3=importlib.metadata.version('z3-solver'))
