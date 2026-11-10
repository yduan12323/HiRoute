"""Describe running code and environment; no frozen source acceptance list."""
import hashlib
import importlib.metadata
from pathlib import Path
import platform
import sys
import os
import shutil
import subprocess


def identity():
    package = Path(__file__).resolve().parents[1]
    h = hashlib.sha256()
    for path in sorted(p for p in package.rglob('*') if p.suffix in {'.py', '.cpp'}):
        h.update(path.relative_to(package).as_posix().encode() + b'\0' + path.read_bytes() + b'\0')
    dependencies = {}
    for name in ('hiroute', 'psutil'):
        try:
            dependencies[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            dependencies[name] = 'not-installed'
    compiler = shutil.which('c++') or shutil.which('g++')
    compiler_version = subprocess.check_output([compiler, '--version'], text=True, timeout=5).splitlines()[0] if compiler else None
    return dict(code_sha256=h.hexdigest(), dependencies=dependencies,
                compiler=compiler, compiler_version=compiler_version,
                include_environment={k: os.environ.get(k) for k in ('CPATH', 'CPLUS_INCLUDE_PATH')},
                python=sys.version, executable=sys.executable, platform=platform.platform())
