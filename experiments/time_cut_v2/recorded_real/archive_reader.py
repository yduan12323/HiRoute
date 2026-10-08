"""Bounded, authenticated consumption of one canonical proof gzip snapshot.

Rows are provisional until exhaustion authenticates the consumed compressed
bytes. A caller opting into interrupted prefixes must pin that exact prefix;
neither a missing gzip trailer nor a discarded partial row is repaired here.
"""
import hashlib
import json
import os
import stat
import zlib

from .plan import canonical, require

CHUNK_BYTES = 65536
MAX_COMPRESSED_BYTES = 512 * 1024**2
MAX_RAW_BYTES = 512 * 1024**2
MAX_ROW_BYTES = 8 * 1024**2


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate archive JSON key')
        result[key] = value
    return result


def _nonfinite(value):
    raise ValueError('nonfinite archive JSON value: ' + value)


def _decode(raw):
    try:
        value = json.loads(raw.decode('ascii'), object_pairs_hook=_pairs,
                           parse_constant=_nonfinite)
        require(canonical(value) + b'\n' == raw, 'noncanonical archive JSON row')
        return value
    except (UnicodeError, RecursionError, OverflowError) as error:
        raise ValueError('malformed archive JSON row') from error


def _open_regular(path):
    """Do not follow links in any path component, or block opening a FIFO."""
    parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        parts = os.path.abspath(os.fspath(path)).split('/')[1:]
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=parent)
            os.close(parent)
            parent = child
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=parent)
        try:
            require(stat.S_ISREG(os.fstat(fd).st_mode), 'regular archive file required')
        except BaseException:
            os.close(fd)
            raise
        return fd
    except OSError as error:
        raise ValueError('archive path must be regular and contain no symlinks') from error
    finally:
        os.close(parent)


class ArchiveReader:
    """Single-use iterator. summary is detached and exists only after exhaustion."""

    def __init__(self, path, *, compressed_sha256, compressed_bytes,
                 allow_incomplete=False, before=lambda: None, max_raw_bytes=None):
        require(type(compressed_sha256) is str and len(compressed_sha256) == 64 and
                all(c in '0123456789abcdef' for c in compressed_sha256),
                'canonical compressed archive SHA256 required')
        require(type(compressed_bytes) is int and
                0 < compressed_bytes <= MAX_COMPRESSED_BYTES, 'compressed archive byte cap/pin')
        require(type(allow_incomplete) is bool and callable(before), 'reader policy/callback required')
        if max_raw_bytes is None:
            max_raw_bytes = MAX_RAW_BYTES
        require(type(max_raw_bytes) is int and 0 <= max_raw_bytes <= MAX_RAW_BYTES,
                'bounded exact integer archive raw-byte budget required')
        self._path = os.fspath(path)
        self._expected_sha256 = compressed_sha256
        self._expected_bytes = compressed_bytes
        self._allow_incomplete = allow_incomplete
        self._before = before
        self._started = False
        self._summary = None
        self._max_raw_bytes = max_raw_bytes

    def limit_raw_bytes(self, max_raw_bytes):
        """Tighten a not-yet-started reader to a shared history's remaining budget.

        A caller cannot expand a constructor cap or change it after reading has
        begun. Zero permits only a genuinely empty decompressed byte stream.
        """
        require(not self._started, 'archive raw-byte budget must precede reading')
        require(type(max_raw_bytes) is int and 0 <= max_raw_bytes <= MAX_RAW_BYTES,
                'bounded exact integer archive raw-byte budget required')
        self._max_raw_bytes = min(self._max_raw_bytes, max_raw_bytes)

    @property
    def summary(self):
        return None if self._summary is None else json.loads(self._summary)

    def __iter__(self):
        return self.iter_rows()

    def iter_rows(self, *, before=lambda: None):
        """Add a consumer resource guard to every bounded I/O/decode operation."""
        require(not self._started, 'archive reader is single-use')
        require(callable(before), 'consumer callback required')
        self._started = True
        return self._rows(before)

    def _rows(self, consumer_before):
        def before():
            self._before()
            consumer_before()

        before()
        fd = _open_regular(self._path)
        try:
            require(os.fstat(fd).st_size == self._expected_bytes,
                    'compressed archive size differs from pin')
            compressed_hash, raw_hash = hashlib.sha256(), hashlib.sha256()
            compressed_bytes = raw_bytes = rows = 0
            pending_row = bytearray()
            decoder = zlib.decompressobj(wbits=31)
            while True:
                before()
                chunk = os.read(fd, CHUNK_BYTES)
                if not chunk:
                    break
                compressed_bytes += len(chunk)
                require(compressed_bytes <= min(MAX_COMPRESSED_BYTES, self._expected_bytes),
                        'compressed archive byte cap/pin exceeded')
                compressed_hash.update(chunk)
                require(not decoder.eof, 'trailing gzip stream or bytes')
                while True:
                    before()
                    try:
                        # Decode at most one byte beyond the remaining budget,
                        # enough to detect overflow without expanding a large
                        # final chunk just to reject it. Existing per-row and
                        # global limits remain in force.
                        remaining = min(MAX_RAW_BYTES, self._max_raw_bytes) - raw_bytes
                        raw = decoder.decompress(chunk, min(CHUNK_BYTES, remaining + 1))
                    except zlib.error as error:
                        raise ValueError('corrupt gzip archive') from error
                    chunk = decoder.unconsumed_tail
                    require(not decoder.unused_data, 'trailing gzip stream or bytes')
                    raw_bytes += len(raw)
                    require(raw_bytes <= min(MAX_RAW_BYTES, self._max_raw_bytes),
                            'uncompressed archive byte cap')
                    raw_hash.update(raw)
                    fragments = raw.split(b'\n')
                    for index, fragment in enumerate(fragments):
                        pending_row.extend(fragment)
                        terminated = index < len(fragments) - 1
                        require(len(pending_row) + int(terminated) <= MAX_ROW_BYTES,
                                'archive JSON row byte cap')
                        if terminated:
                            before()
                            value = _decode(bytes(pending_row) + b'\n')
                            pending_row.clear()
                            rows += 1
                            yield value
                    if decoder.eof or (not chunk and len(raw) < CHUNK_BYTES):
                        break
            before()
            require(compressed_bytes == self._expected_bytes and
                    compressed_hash.hexdigest() == self._expected_sha256,
                    'consumed compressed archive hash/size differs from pin')
            require(decoder.eof or self._allow_incomplete, 'unfinished gzip archive')
            require(not pending_row or (self._allow_incomplete and not decoder.eof),
                    'unterminated archive JSON row')
            summary = dict(encoding='canonical-jsonl-gzip-v1', gzip_eof=decoder.eof,
                           compressed_bytes=compressed_bytes,
                           compressed_sha256=compressed_hash.hexdigest(),
                           uncompressed_bytes=raw_bytes,
                           uncompressed_sha256=raw_hash.hexdigest(), rows=rows,
                           trailing_partial_row_bytes=len(pending_row))
        finally:
            os.close(fd)
        # A close failure or any validation/resource exception leaves no summary.
        self._summary = canonical(summary)
