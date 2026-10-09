"""Byte and namespace continuity for a private, process-local receipt epoch.

This module authenticates bytes, not their semantics. Only a successful full
receipt admission may seal its first snapshot. No snapshot is loadable from
disk and no identity check substitutes for a phase's actual streaming hash.
"""
import hashlib
import os
from pathlib import Path
import stat
from types import MappingProxyType

from experiments.time_cut_v2.recorded_real import plan as binding
from experiments.time_cut_v2.recorded_real.archive_reader import _open_regular
from experiments.time_cut_v2.recorded_real.runtime import _directory

MAX_FILES = 100000
MAX_FILE_BYTES = 1024**3


def _path(value):
    value = os.fspath(value)
    binding.require(os.path.isabs(value) and os.path.normpath(value) == value,
                    'epoch closure requires normalized absolute paths')
    return value


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _directory_id(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid)


def _file(path, before, expected=None, *, limit=MAX_FILE_BYTES):
    before()
    fd = _open_regular(path)
    try:
        initial = os.fstat(fd)
        binding.require(initial.st_nlink == 1 and initial.st_size <= limit,
                        'epoch file alias or byte cap')
        digest, count = hashlib.sha256(), 0
        while True:
            before()
            raw = os.read(fd, 65536)
            if not raw:
                break
            count += len(raw)
            binding.require(count <= limit, 'epoch consumed file byte cap')
            digest.update(raw)
        final = os.fstat(fd)
        binding.require(_identity(initial) == _identity(final) == _identity(os.lstat(path)),
                        'epoch file changed or replaced during hash')
        binding.require(count == initial.st_size, 'epoch file short read')
        row = dict(path=path, size_bytes=count, sha256=digest.hexdigest())
        if expected is not None:
            binding.require(row == expected, 'epoch independently pinned bytes changed: '+path)
        return _identity(final), (count, digest.hexdigest())
    finally:
        os.close(fd)


class Closure:
    """Private immutable hashes plus complete closed-tree and ancestor identities."""
    __slots__ = ('roots', 'pins', 'files', 'directories', 'ancestors', 'names', 'replay_members')

    def __init__(self, roots, pins, files, directories, ancestors, names, replay_members):
        self.roots = tuple(roots)
        self.pins = tuple(dict(row) for row in pins)
        self.files = MappingProxyType(dict(files))
        self.directories = MappingProxyType(dict(directories))
        self.ancestors = MappingProxyType(dict(ancestors))
        self.names = MappingProxyType(dict(names))
        self.replay_members = MappingProxyType({path: MappingProxyType(dict(row))
                                                for path, row in replay_members.items()})

    @classmethod
    def capture(cls, roots, pins, before, *, replay_members=None):
        roots = sorted(set(_path(root) for root in roots))
        replay_members = {} if replay_members is None else {path: dict(row) for path, row in replay_members.items()}
        for path, row in replay_members.items():
            binding.require(path == _path(path) and type(row) is dict and
                            set(row) == {'path', 'size_bytes', 'sha256'} and row['path'] == path and
                            type(row['size_bytes']) is int and MAX_FILE_BYTES < row['size_bytes'],
                            'epoch exact authenticated replay member required')
        expected = {}
        for supplied in pins:
            row = dict(supplied)
            binding.require(set(row) == {'path', 'size_bytes', 'sha256'} and
                            type(row['size_bytes']) is int and 0 <= row['size_bytes'] <=
                            (replay_members[row['path']]['size_bytes'] if row['path'] in replay_members else MAX_FILE_BYTES),
                            'epoch exact bounded closure pin required')
            path = _path(row['path'])
            if path in replay_members:
                binding.require(row == replay_members[path], 'epoch replay member differs from authenticated manifest')
            binding.require(path not in expected or expected[path] == row, 'epoch conflicting file pins')
            expected[path] = row
        binding.require(set(replay_members) <= set(expected), 'epoch replay member lacks independent receipt pin')
        files, directories, ancestors, names = {}, {}, {}, {}

        def parents(path):
            for parent in reversed(Path(path).parents):
                if str(parent) in ancestors:
                    continue
                before()
                fd = _directory(parent)
                try:
                    ident = _directory_id(os.fstat(fd))
                    binding.require(ident == _directory_id(os.lstat(parent)), 'epoch ancestor replaced')
                    binding.require(str(parent) not in ancestors or ancestors[str(parent)] == ident,
                                    'epoch ancestor changed while capturing closure')
                    ancestors[str(parent)] = ident
                finally:
                    os.close(fd)

        def file(path):
            if path not in files:
                binding.require(len(files) < MAX_FILES, 'epoch closure file count cap')
                parents(path)
                files[path] = _file(path, before, expected.get(path),
                                    limit=replay_members[path]['size_bytes'] if path in replay_members else MAX_FILE_BYTES)

        def tree(path):
            if path in directories:
                return
            before(); parents(path)
            fd = _directory(Path(path))
            try:
                initial = os.fstat(fd)
                entries = tuple(sorted(os.listdir(fd)))
                binding.require(len(entries)+len(files)+len(directories) <= MAX_FILES,
                                'epoch closure namespace cap')
                names[path] = entries
                for name in entries:
                    before()
                    child = str(Path(path)/name)
                    info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                    if stat.S_ISDIR(info.st_mode):
                        tree(child)
                    else:
                        binding.require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
                                        'epoch closed tree contains link or special file')
                        file(child)
                binding.require(entries == tuple(sorted(os.listdir(fd))) and
                                _identity(initial) == _identity(os.fstat(fd)) == _identity(os.lstat(path)),
                                'epoch closed directory changed during inventory')
                directories[path] = _identity(initial)
            finally:
                os.close(fd)

        for root in roots:
            tree(root)
        for path in expected:
            file(path)
        result = cls(roots, expected.values(), files, directories, ancestors, names, replay_members)
        result.continuity(before)
        return result

    def continuity(self, before):
        """End-of-phase identity/names fence after this phase's consumed-byte pass."""
        for path, ident in self.ancestors.items():
            before()
            fd = _directory(Path(path))
            try:
                binding.require(_directory_id(os.fstat(fd)) == ident == _directory_id(os.lstat(path)),
                                'epoch ancestor continuity changed: '+path)
            finally:
                os.close(fd)
        for path, ident in self.directories.items():
            before()
            fd = _directory(Path(path))
            try:
                binding.require(_identity(os.fstat(fd)) == ident == _identity(os.lstat(path)) and
                                tuple(sorted(os.listdir(fd))) == self.names[path],
                                'epoch closed directory continuity changed: '+path)
            finally:
                os.close(fd)
        for path, (ident, _) in self.files.items():
            before()
            fd = _open_regular(path)
            try:
                binding.require(os.fstat(fd).st_nlink == 1 and
                                _identity(os.fstat(fd)) == ident == _identity(os.lstat(path)),
                                'epoch file continuity changed: '+path)
            finally:
                os.close(fd)
        before()

    def rehash(self, before):
        """Hash every unique historical file, then recheck the entire namespace."""
        self.continuity(before)
        for path, expected in self.files.items():
            actual = _file(path, before, self.replay_members.get(path),
                           limit=self.replay_members[path]['size_bytes'] if path in self.replay_members else MAX_FILE_BYTES)
            binding.require(actual == expected, 'epoch historical bytes/identity changed: '+path)
        self.continuity(before)

    def require_extension(self, newer):
        for name in ('files', 'directories', 'ancestors', 'names', 'replay_members'):
            current, proposed = getattr(self, name), getattr(newer, name)
            binding.require(all(path in proposed and proposed[path] == row for path, row in current.items()),
                            'epoch closure extension changed historical '+name)
