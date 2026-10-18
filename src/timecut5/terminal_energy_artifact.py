"""Package-owned certified energy kernel builds; no graph or archive paths.

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
    'schema': 'hiroute.certified_terminal_energy_arithmetic.v1',
    'quantization': 'exact binary64 bit-floor dyadic uint64 capped weights',
    'certificate': 'all original edges; p(u)<=q+p(v); p(destination)=0; q/2^k<=distance',
    'rounding': 'RN binary64; beta=max(0,1-(n-1)/2^53); nonnegative cycle erasure',
    'use': 'immediate-finish rejection only; independent verification bypass',
}
_SAFE_FLAGS = frozenset(('-O0', '-O1', '-O2', '-O3', '-g', '-g0', '-g1', '-g2',
    '-std=c++17', '-std=c++20', '-std=c++23', '-Wall', '-Wextra', '-Werror',
    '-pedantic', '-fno-fast-math', '-frounding-math', '-ffp-contract=off'))
_RESOURCES = ('terminal_energy_native.cpp', 'terminal_energy.py', 'terminal_energy_artifact.py')
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
    for name in ('energy_build', 'energy_validate', 'energy_labels', 'energy_destroy',
                 'energy_environment_supported', 'energy_last_error'):
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
    root = resources.files('timecut5')
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
class EnergyArtifact:
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
        return self.directory / 'terminal_energy.so'

    @property
    def path(self):
        return self.binary_path

    def authenticate(self, config=None):
        receipt = self.receipt
        for filename in ('terminal_energy.so', 'receipt.json'):
            _regular(self.directory / filename)
        if (self.directory.joinpath('receipt.json').read_bytes() != self._receipt_bytes or
                _file_sha(self.directory / 'terminal_energy.so') != receipt['artifact_sha256']):
            raise ValueError('Native build receipt or artifact bytes changed')
        observed = {name: _digest(data) for name, data in _package_bytes().items()}
        if observed != receipt['build_spec']['package_resources']:
            raise ValueError('Installed native source/wrapper resources changed')
        spec = receipt['build_spec']
        if spec['compiler_flags'] != ['-O3', '-std=c++17', '-fno-fast-math', '-frounding-math']:
            raise ValueError('Energy compiler flags changed')
        if (receipt['source_sha256'] != observed['terminal_energy_native.cpp'] or
                receipt['wrapper_sha256'] != observed['terminal_energy.py'] or
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
        root = Path(cache).resolve() / 'energy-loads'
        root.mkdir(parents=True, exist_ok=True)
        directory = Path(tempfile.mkdtemp(prefix='instance-', dir=root))
        path = directory / 'terminal_energy.so'
        try:
            with path.open('xb') as stream:
                stream.write((self.directory / 'terminal_energy.so').read_bytes())
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
    if flags != ['-O3', '-std=c++17', '-fno-fast-math', '-frounding-math']:
        raise ValueError('Exact reviewed energy compiler flags required')
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
    root = Path(cache).resolve() / 'energy-artifacts'
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
            artifact = EnergyArtifact(directory, (directory / 'receipt.json').read_bytes())
            receipt = artifact.authenticate(config)
            if receipt['build_spec'] != spec:
                raise ValueError('Cached native build specification differs')
            return artifact
        temporary = Path(tempfile.mkdtemp(prefix='.build-', dir=root))
        try:
            source = temporary / 'terminal_energy_native.cpp'
            source.write_bytes(package['terminal_energy_native.cpp'])
            binary = temporary / 'terminal_energy.so'
            command = [compiler, *flags, '-shared', '-fPIC', str(source), '-o', str(binary)]
            subprocess.run(command, check=True, timeout=30, preexec_fn=_limit_compiler_cpu)
            _regular(binary)
            receipt = dict(schema='hiroute.package_energy_artifact.v1', build_spec=spec,
                source_sha256=spec['package_resources']['terminal_energy_native.cpp'],
                wrapper_sha256=spec['package_resources']['terminal_energy.py'],
                artifact_sha256=_file_sha(binary), compiler_command=command,
                semantic_contract_sha256=_digest(canonical(SEMANTIC_CONTRACT)))
            package_root = resources.files('timecut5')
            receipt.update(source_path=str(package_root.joinpath('terminal_energy_native.cpp')),
                wrapper_path=str(package_root.joinpath('terminal_energy.py')),
                artifact_path=str(directory / 'terminal_energy.so'))
            stable = {k: receipt[k] for k in ('schema', 'build_spec', 'artifact_sha256',
                                             'semantic_contract_sha256')}
            receipt['artifact_identity_sha256'] = _digest(canonical(stable))
            encoded = canonical(receipt)
            (temporary / 'receipt.json').write_bytes(encoded)
            for path in temporary.iterdir():
                path.chmod(0o444)
            os.rename(temporary, directory)
            artifact = EnergyArtifact(directory, encoded)
            artifact.authenticate(config)
            return artifact
        except BaseException:
            if temporary.exists():
                shutil.rmtree(temporary)
            raise
