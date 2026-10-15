"""Package-owned native builds, independent of graph data and experiment paths.

The cache is a local trust boundary, not a signature or a sandbox against hostile
Python reflection. Receipts bind actual package/compiler/binary bytes. A fresh
read-only load copy is used by every router; a mapped file is never overwritten.
The current runtime supports Linux, matching the existing shared-object build.
"""
from dataclasses import dataclass
import ctypes
import hashlib
from importlib import resources
import json
import os
from pathlib import Path
import platform
import resource
import shutil
import stat
import subprocess
import tempfile
import time


ROLES = ('generation', 'verification', 'search', 'durable_verification',
         'recovery', 'landmark')
SEMANTIC_CONTRACT = {
    'schema': 'hiroute.selected_leg_settlement.v1',
    'weights': 'immutable finite nonnegative binary64 time and length',
    'arithmetic': 'binary64 round-to-nearest; no fast-math; same binary and edge order',
    'queue': 'lexicographic (time,length,uint32 node); stale labels discarded',
    'relaxation': 'strictly smaller time, then length; equality never replaces predecessor',
    'adjacency': 'input edge order; parallel edges retain first strict discovery',
    'settlement': 'target stops only at a nonstale queue pop before outgoing relaxation',
    'certificate': 'target pair and predecessor edge chain only; no partial source-cache admission',
    'zero_edges': 'allowed; strict relaxation prevents equal-label predecessor replacement',
    'overflow': 'reject inputs whose simple-path sum can overflow either binary64 coordinate',
    'selected_identity': 'same settled pair and ordered witness in candidate full and target modes',
}
_SAFE_FLAGS = frozenset(('-O0', '-O1', '-O2', '-O3', '-g', '-g0', '-g1', '-g2',
    '-std=c++17', '-std=c++20', '-std=c++23', '-Wall', '-Wextra', '-Werror',
    '-pedantic', '-fno-fast-math', '-ffp-contract=off'))
_RESOURCES = ('routing.cpp', 'routing.py', 'native_artifact.py')
_COMPILER_LIMITS = dict(wall_seconds=30, cpu_soft_seconds=20, cpu_hard_seconds=25)


def _limit_compiler_cpu():
    # Run only in the Linux compiler child. Never enlarge an inherited hard cap.
    _, inherited_hard = resource.getrlimit(resource.RLIMIT_CPU)
    hard = 25 if inherited_hard == resource.RLIM_INFINITY else min(25, inherited_hard)
    resource.setrlimit(resource.RLIMIT_CPU, (min(20, hard), hard))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _file_sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def _regular(path):
    if not stat.S_ISREG(Path(path).lstat().st_mode):
        raise ValueError('Native resource must be a regular file')


def mapped_library(native, path):
    """Bind exported symbols to the exact regular file mapped by this loader."""
    path = Path(path).resolve()
    _regular(path)
    info = path.stat()
    rows = []
    for line in Path('/proc/self/maps').read_text().splitlines():
        fields = line.split(maxsplit=5)
        if len(fields) == 6 and fields[5] == str(path):
            span, permissions, _, device, inode, _ = fields
            if (int(inode) != info.st_ino or
                    device != f'{os.major(info.st_dev):02x}:{os.minor(info.st_dev):02x}'):
                raise ValueError('Native mapped inode/device differs')
            rows.append((span, permissions))
    if not any('x' in permissions for _, permissions in rows):
        raise ValueError('Exact native executable mapping missing')
    class DlInfo(ctypes.Structure):
        _fields_ = [('name', ctypes.c_char_p), ('base', ctypes.c_void_p),
                    ('symbol', ctypes.c_char_p), ('address', ctypes.c_void_p)]
    libc = ctypes.CDLL(None)
    libc.dladdr.argtypes = [ctypes.c_void_p, ctypes.POINTER(DlInfo)]
    libc.dladdr.restype = ctypes.c_int
    symbols = {}
    for name in ('graph_create', 'graph_free', 'graph_full', 'graph_full_edges',
                 'graph_target_edges', 'graph_pairs', 'graph_gateways'):
        address = ctypes.cast(getattr(native, name), ctypes.c_void_p).value
        record = DlInfo()
        if (not libc.dladdr(address, ctypes.byref(record)) or
                Path(os.fsdecode(record.name)).resolve() != path or
                not any('x' in permissions and int(span.split('-')[0], 16) <= address <
                        int(span.split('-')[1], 16) for span, permissions in rows)):
            raise ValueError('Native symbol belongs to another mapping')
        symbols[name] = address
    return dict(path=str(path), inode=info.st_ino, device=info.st_dev,
                symbols=symbols, mappings=rows)


def _package_bytes():
    # files()/read_bytes() also works for an installed package outside checkout.
    root = resources.files('microplan')
    return {name: root.joinpath(name).read_bytes() for name in _RESOURCES}


def _config(config):
    if (not isinstance(config, dict) or type(config.get('compiler')) is not str or
            not isinstance(config.get('compiler_flags'), (list, tuple)) or
            any(type(flag) is not str for flag in config['compiler_flags'])):
        raise ValueError('Explicit compiler and compiler_flags required')
    compiler = shutil.which(config['compiler'])
    if compiler is None:
        raise ValueError('Native compiler was not found')
    return str(Path(compiler).resolve()), list(config['compiler_flags'])


@dataclass(frozen=True)
class NativeArtifact:
    """An immutable identity pinned when build_artifact authenticates its files."""
    directory: Path
    _receipt_bytes: bytes

    @property
    def receipt(self):
        return json.loads(self._receipt_bytes)

    @property
    def identity_sha256(self):
        return self.receipt['artifact_identity_sha256']

    @property
    def binary_path(self):
        return self.directory / 'routing.so'

    @property
    def path(self):
        return self.binary_path

    def authenticate(self, config=None):
        receipt = self.receipt
        for filename in ('routing.so', 'receipt.json'):
            _regular(self.directory / filename)
        if (self.directory.joinpath('receipt.json').read_bytes() != self._receipt_bytes or
                _file_sha(self.directory / 'routing.so') != receipt['artifact_sha256']):
            raise ValueError('Native build receipt or artifact bytes changed')
        observed = {name: _digest(data) for name, data in _package_bytes().items()}
        if observed != receipt['build_spec']['package_resources']:
            raise ValueError('Installed native source/wrapper resources changed')
        spec = receipt['build_spec']
        if (receipt['source_sha256'] != observed['routing.cpp'] or
                receipt['wrapper_sha256'] != observed['routing.py'] or
                receipt['semantic_contract_sha256'] != _digest(canonical(SEMANTIC_CONTRACT))):
            raise ValueError('Native source or semantic contract identity differs')
        if _file_sha(spec['compiler']) != spec['compiler_sha256']:
            raise ValueError('Native compiler identity changed')
        if config is not None:
            compiler, flags = _config(config)
            if compiler != spec['compiler'] or flags != spec['compiler_flags']:
                raise ValueError('Requested native build differs from supplied artifact')
        stable = {k: receipt[k] for k in ('schema', 'build_spec', 'artifact_sha256',
                                         'semantic_contract_sha256')}
        if _digest(canonical(stable)) != receipt['artifact_identity_sha256']:
            raise ValueError('Native artifact identity mismatch')
        return receipt

    def load_copy(self, cache):
        receipt = self.authenticate()
        root = Path(cache).resolve() / 'routing-loads'
        root.mkdir(parents=True, exist_ok=True)
        directory = Path(tempfile.mkdtemp(prefix='instance-', dir=root))
        path = directory / 'routing.so'
        try:
            with path.open('xb') as stream:
                stream.write((self.directory / 'routing.so').read_bytes())
                stream.flush()
                os.fsync(stream.fileno())
            path.chmod(0o444)
            if _file_sha(path) != receipt['artifact_sha256']:
                raise ValueError('Native load-copy bytes differ')
            return path
        except BaseException:
            shutil.rmtree(directory)
            raise


def build_artifact(config, cache):
    """Build once per package/compiler recipe, without reading graph resources.

    A caller may pass the returned artifact to every role to pin the same build.
    Compiler processes have wall30/CPU20-soft/25-hard limits. Explicit-role routers also
    require the narrow, audited compiler flag set recorded as strict_binary64.
    """
    if platform.system() != 'Linux':
        raise ValueError('Native artifact authentication currently supports Linux')
    import fcntl
    compiler, flags = _config(config)
    package = _package_bytes()  # Missing resources fail before any native load.
    version = subprocess.check_output([compiler, '--version'], text=True, timeout=30,
                                      preexec_fn=_limit_compiler_cpu)
    spec = dict(package_resources={k: _digest(v) for k, v in package.items()},
        compiler=compiler, compiler_sha256=_file_sha(compiler), compiler_version=version,
        compiler_flags=flags, link_flags=['-shared', '-fPIC'],
        system=platform.system(), machine=platform.machine(),
        strict_binary64=all(flag in _SAFE_FLAGS for flag in flags),
        compiler_limits=_COMPILER_LIMITS,
        provenance_scope='package_sources_compiler_driver_flags_and_binary_not_hermetic',
        compiler_subtools_authenticated=False, runtime_dependencies_authenticated=False)
    key = _digest(canonical(spec))
    root = Path(cache).resolve() / 'routing-artifacts'
    root.mkdir(parents=True, exist_ok=True)
    directory = root / key
    lock_path = root / (key + '.lock')
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'a+b') as lock:
        deadline = time.monotonic() + 30
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError('Native artifact build lock timed out')
                time.sleep(0.05)
        if directory.exists() or directory.is_symlink():
            if directory.is_symlink() or not directory.is_dir():
                raise ValueError('Native artifact directory is not owned')
            _regular(directory / 'receipt.json')
            artifact = NativeArtifact(directory, (directory / 'receipt.json').read_bytes())
            receipt = artifact.authenticate(config)
            if receipt['build_spec'] != spec:
                raise ValueError('Cached native build specification differs')
            return artifact
        temporary = Path(tempfile.mkdtemp(prefix='.build-', dir=root))
        try:
            source = temporary / 'routing.cpp'
            source.write_bytes(package['routing.cpp'])
            binary = temporary / 'routing.so'
            command = [compiler, *flags, '-shared', '-fPIC', str(source), '-o', str(binary)]
            subprocess.run(command, check=True, timeout=30, preexec_fn=_limit_compiler_cpu)
            _regular(binary)
            receipt = dict(schema='hiroute.package_native_artifact.v1', build_spec=spec,
                source_sha256=spec['package_resources']['routing.cpp'],
                wrapper_sha256=spec['package_resources']['routing.py'],
                artifact_sha256=_file_sha(binary), compiler_command=command,
                semantic_contract_sha256=_digest(canonical(SEMANTIC_CONTRACT)))
            package_root = resources.files('microplan')
            receipt.update(source_path=str(package_root.joinpath('routing.cpp')),
                wrapper_path=str(package_root.joinpath('routing.py')),
                artifact_path=str(directory / 'routing.so'))
            stable = {k: receipt[k] for k in ('schema', 'build_spec', 'artifact_sha256',
                                             'semantic_contract_sha256')}
            receipt['artifact_identity_sha256'] = _digest(canonical(stable))
            encoded = canonical(receipt)
            (temporary / 'receipt.json').write_bytes(encoded)
            for path in temporary.iterdir():
                path.chmod(0o444)
            os.rename(temporary, directory)
            artifact = NativeArtifact(directory, encoded)
            artifact.authenticate(config)
            return artifact
        except BaseException:
            if temporary.exists():
                shutil.rmtree(temporary)
            raise
