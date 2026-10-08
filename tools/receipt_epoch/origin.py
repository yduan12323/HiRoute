"""Independent tool/verifier/interpreter provenance; stdlib bootstrap only."""
import hashlib
import importlib.abc
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time

CORE_DIRS = ('src/timecut5', 'validation/family5', 'validation/trace5',
    'validation/real5_v2', 'validation/capture5',
    'experiments/time_cut_v2/recorded_real', 'validation/suffix5')
IMPORT_DIRS = ('src', 'validation', 'experiments/time_cut_v2/recorded_real',
               'experiments/__init__.py','experiments/time_cut_v2/__init__.py')
TOOL_DIR = 'tools/receipt_epoch'
MAX_CODE = 2*1024**2


def require(ok, why):
    if not ok: raise ValueError(why)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def hex_value(value, size):
    require(type(value) is str and len(value) == size and all(c in '0123456789abcdef' for c in value),
            'exact source commit/digest required')
    return value


def directory(path):
    path = Path(os.path.abspath(path))
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = child
        return fd
    except BaseException:
        os.close(fd); raise


def identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def consume(path, *, limit=MAX_CODE, before=lambda: None, binary=False):
    """Source/data links are forbidden; the preexisting interpreter may be a conda hardlink."""
    path = Path(os.path.abspath(path)); before()
    parent = directory(path.parent)
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    finally:
        os.close(parent)
    try:
        first = os.fstat(fd)
        require(stat.S_ISREG(first.st_mode) and first.st_size <= limit and
                (binary or first.st_nlink == 1), 'bounded nonalias regular source/data required')
        chunks, hasher, count = [], hashlib.sha256(), 0
        while True:
            before(); raw = os.read(fd, 65536)
            if not raw: break
            count += len(raw); require(count <= limit, 'source/data consumed byte cap')
            hasher.update(raw); chunks.append(raw)
        require(count == first.st_size and identity(first) == identity(os.fstat(fd)) == identity(os.lstat(path)),
                'source/data changed during safe consumption')
        return b''.join(chunks), dict(path=str(path),size_bytes=count,sha256=hasher.hexdigest()), identity(first)
    finally:
        os.close(fd)


def git(root, arguments, deadline):
    remaining = deadline-time.monotonic(); require(remaining > 0, 'source binding deadline')
    result = subprocess.run(['git', '-C', str(root), *arguments], check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=remaining,
        env=dict(os.environ, GIT_OPTIONAL_LOCKS='0', GIT_TERMINAL_PROMPT='0'))
    return result.stdout


def manifest(root, commit, folders, deadline):
    """Compare safe live source bytes to exact committed blobs before imports."""
    hex_value(commit, 40)
    require(git(root, ['rev-parse', 'HEAD'], deadline).decode().strip() == commit, 'source checkout HEAD changed')
    listing = git(root, ['ls-tree', '-rz', '--long', commit, '--', *folders], deadline)
    rows = {}
    for line in listing.split(b'\0'):
        if not line: continue
        header, name = line.split(b'\t', 1); name = name.decode('utf-8')
        if not name.endswith('.py'): continue
        mode, kind, oid, size = header.split()
        require(mode in (b'100644',b'100755') and kind == b'blob' and int(size) <= MAX_CODE and
                not Path(name).is_absolute() and '..' not in Path(name).parts and '\n' not in name,
                'fixed bounded ordinary source blob required')
        blob = git(root, ['cat-file', 'blob', oid.decode()], deadline)
        _, row, _ = consume(root/name, before=lambda: require(time.monotonic() < deadline, 'source binding deadline'))
        require(len(blob) == row['size_bytes'] and hashlib.sha256(blob).hexdigest() == row['sha256'],
                'source differs from reviewed commit: '+name)
        rows[name] = dict(size_bytes=row['size_bytes'], sha256=row['sha256'])
    actual = set()
    for folder in folders:
        path = root/folder
        if path.is_file(): actual.add(folder); continue
        if not path.exists(): continue
        fd = directory(path); os.close(fd)
        for parent, directories, names in os.walk(path, followlinks=False):
            require(not any((Path(parent)/name).is_symlink() for name in directories), 'source directory link forbidden')
            actual.update((Path(parent)/name).relative_to(root).as_posix() for name in names if name.endswith('.py'))
    require(actual == set(rows) and rows, 'source namespace has missing/uncommitted Python files')
    return dict(sorted(rows.items()))


def inspect(tool_root, tool_commit, verifier_root, verifier_commit, deadline):
    tool_root, verifier_root = Path(os.path.abspath(tool_root)), Path(os.path.abspath(verifier_root))
    for root in (tool_root, verifier_root): fd=directory(root); os.close(fd)
    tools = manifest(tool_root, tool_commit, (TOOL_DIR,), deadline)
    imported = manifest(verifier_root, verifier_commit, IMPORT_DIRS, deadline)
    core = {name:row for name,row in imported.items() if name == 'validation/__init__.py' or
            any(name.startswith(folder+'/') for folder in CORE_DIRS)}
    executable = Path(sys.executable).resolve()
    _, python, ident = consume(executable, limit=64*1024**2, binary=True)
    return dict(tool_root=str(tool_root),tool_commit=tool_commit,tool_source_sha=digest(tools),
        verifier_root=str(verifier_root),verifier_commit=verifier_commit,
        verifier_source_sha=digest(core),verifier_import_sha=digest(imported),
        python_realpath=str(executable),python_sha=python['sha256']), tools, imported, ident


class SourceBinding:
    """Created by the owning CLI's independently supplied immutable contract."""
    def __init__(self, expected):
        self.expected = json.loads(canonical(expected))
        require(Path(__file__).absolute() == Path(expected['tool_root'])/TOOL_DIR/'origin.py',
                'source binding module is outside selected tool checkout')
        actual, tools, imported, binary_id = inspect(expected['tool_root'], expected['tool_commit'],
            expected['verifier_root'], expected['verifier_commit'], time.monotonic()+10)
        require(actual == self.expected, 'independently supplied source/interpreter contract differs')
        self._binary_id = binary_id
        self.pins = [dict(path=str(Path(expected['tool_root'])/name), **row) for name,row in tools.items()]
        self.pins += [dict(path=str(Path(expected['verifier_root'])/name), **row) for name,row in imported.items()]
        self._allowed = {row['path'] for row in self.pins}
        self._package_paths = {str(Path(expected['verifier_root'])/Path(name).parent)
                               for name in imported}
        for path in tuple(self._package_paths):
            self._package_paths.update(str(parent) for parent in Path(path).parents
                                       if parent.is_relative_to(Path(expected['verifier_root'])))
        self._imported = imported

    def phase_check(self, deadline):
        for prefix in ('tool','verifier'):
            require(git(self.expected[prefix+'_root'], ['rev-parse','HEAD'], deadline).decode().strip() ==
                    self.expected[prefix+'_commit'], 'epoch fixed '+prefix+' HEAD changed')
        _, python, ident = consume(self.expected['python_realpath'],limit=64*1024**2,binary=True,
            before=lambda: require(time.monotonic() < deadline, 'source binding deadline'))
        require(python['sha256'] == self.expected['python_sha'] and ident == self._binary_id,
                'epoch interpreter bytes/identity changed')
        root = Path(self.expected['verifier_root'])
        for name,module in tuple(sys.modules.items()):
            if name in ('experiments','validation','timecut5') or name.startswith(
                    ('experiments.', 'validation.', 'timecut5.')):
                path = getattr(module,'__file__',None)
                if path is not None:
                    require(str(Path(path).absolute()) in self._allowed,
                            'epoch loaded verifier module outside reviewed source pins: '+name)
                for path in getattr(module,'__path__',()):
                    require(str(Path(path).absolute()) in self._package_paths,
                            'epoch loaded verifier package outside reviewed source namespace: '+name)
        binding = sys.modules.get('experiments.time_cut_v2.recorded_real.plan')
        require(binding is not None and Path(binding.ROOT) == root and
                Path(binding.__file__).absolute() == root/'experiments/time_cut_v2/recorded_real/plan.py',
                'epoch verifier root/origin differs; ROOT reassignment is forbidden')
        require(time.monotonic() < deadline, 'source binding deadline')


class VerifiedLoader(importlib.abc.Loader):
    """Execute precisely the safe consumed source bytes, never a later reread."""
    def __init__(self, path, pin, *, raw=None):
        self.path, self.pin, self.raw = Path(path), pin, raw

    def create_module(self, spec): return None

    def exec_module(self, module):
        raw = self.raw
        if raw is None:
            raw, actual, _ = consume(self.path)
            require(actual['sha256'] == self.pin['sha256'] and actual['size_bytes'] == self.pin['size_bytes'],
                    'source import differs from independently reviewed bytes')
        module.__file__ = str(self.path)
        exec(compile(raw,str(self.path),'exec',dont_inherit=True,optimize=sys.flags.optimize),module.__dict__)


class VerifierFinder(importlib.abc.MetaPathFinder):
    """Only reviewed Python modules resolve inside the original verifier roots."""
    def __init__(self, root, pins): self.root,self.pins = Path(root),pins

    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] not in ('experiments','validation','timecut5'): return None
        relative = fullname.replace('.','/')
        if fullname.startswith('timecut5'): relative='src/'+relative
        for name, package in ((relative+'/__init__.py',True),(relative+'.py',False)):
            if name in self.pins:
                loader=VerifiedLoader(self.root/name,self.pins[name])
                return importlib.util.spec_from_file_location(fullname,self.root/name,loader=loader,
                    submodule_search_locations=[str(self.root/relative)] if package else None)
        if any(name.startswith(relative+'/') for name in self.pins):
            spec=importlib.machinery.ModuleSpec(fullname,loader=None,is_package=True)
            spec.submodule_search_locations=[str(self.root/relative)];return spec
        raise ImportError('unreviewed/native verifier import forbidden in metadata epoch: '+fullname)
