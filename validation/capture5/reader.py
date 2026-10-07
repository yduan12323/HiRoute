"""Bounded-scratch, lossless loading of the unchanged JSON capture format.

The complete immutable JSON value is retained, but never the complete encoded
file or a second mutable/deep-cloned document. Strings are decoded individually
and containers are frozen as they close. Equal lowercase 64-hex strings (keys
included) share one object for this load. Other object keys also share storage.
Nothing here verifies a family, trace, callback, or mathematical result.

Budgets bound input, scratch space, nesting and retained population. They are
admission limits, not a measured RSS promise. Exceeding one is an unresolved
resource failure; it must never be interpreted as infeasibility.
"""
from dataclasses import dataclass, fields
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from types import MappingProxyType
from typing import Mapping


class CaptureError(ValueError):
    """The capture was not loaded; no mathematical conclusion follows."""


class CaptureFormatError(CaptureError):
    """Malformed or ambiguous JSON evidence."""


class CaptureIntegrityError(CaptureError):
    """Pinned bytes, size, or stable source identity did not match."""


class CaptureResourceError(CaptureError):
    """Unresolved: an explicit storage/parser resource budget was exceeded."""


@dataclass(frozen=True, slots=True)
class CaptureLimits:
    """Explicit finite budgets; byte limits refer to source UTF-8 bytes.

    max_record_bytes applies to each ordinary metadata value or collection
    record, including every family node, batch, event and callback. The known
    collection envelopes are streamed rather than subjected to that per-record
    limit. Unknown top-level fields remain supported within the metadata budget.
    """
    chunk_bytes: int = 65536
    max_file_bytes: int = 2 * 1024 ** 3
    max_record_bytes: int = 16 * 1024 ** 2
    max_token_bytes: int = 1024 ** 2
    max_depth: int = 128
    max_values: int = 50_000_000
    max_container_items: int = 12_000_000
    max_unique_ids: int = 1_000_000
    max_unique_keys: int = 65_536

    def __post_init__(self):
        for field in fields(self):
            value = getattr(self, field.name)
            if type(value) is not int or value <= 0:
                raise ValueError(f'{field.name} must be a positive integer')
        if self.max_depth > 256:
            raise ValueError('max_depth must not exceed 256')
        if self.chunk_bytes > self.max_file_bytes:
            raise ValueError('chunk_bytes exceeds max_file_bytes')


@dataclass(frozen=True, slots=True)
class LoadedCapture:
    """Fully consumed pinned input and immutable, semantically unchanged JSON.

    storage_stats is diagnostic only. The dataclass is a storage handle, never
    an attestation of mathematical validity or an authorization capability.
    """
    payload: Mapping
    sha256: str
    size_bytes: int
    storage_stats: Mapping


_HEX_ID = re.compile(r'[0-9a-f]{64}\Z')
_NUMBER = re.compile(rb'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?\Z')
_STRING_SPECIAL = re.compile(rb'["\\\x00-\x1f]')
_WHITESPACE = re.compile(rb'[ \t\r\n]*')
_NUMBER_CHARS = frozenset(b'-+0123456789.eE')
# Only these envelopes can be larger than max_record_bytes. Each value below
# them is admitted separately, with an inherited outer budget if applicable.
_ENVELOPES = frozenset({(), ('bundle',), ('trace',), ('bundle', 'nodes'),
                        ('bundle', 'batches'), ('bundle', 'batch_ids'),
                        ('bundle', 'roots'), ('trace', 'events'),
                        ('callback_requests',)})


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


class _Reader:
    def __init__(self, source, limits):
        self.source = source
        self.limits = limits
        self.buffer = b''
        self.position = 0
        self.offset = 0
        self.size = 0
        self.eof = False
        self.hash = hashlib.sha256()
        self.ids = {}
        self.keys = {}
        self.value_count = 0
        self.id_occurrences = 0
        self.key_occurrences = 0
        self.max_buffer_bytes = 0
        self.max_token_bytes = 0
        self.max_record_bytes = 0
        self.records = 0
        self.budget_end = None

    def resource(self, reason):
        raise CaptureResourceError(f'unresolved_capture_resource: {reason} at byte {self.offset}')

    def invalid(self, reason):
        raise CaptureFormatError(f'{reason} at byte {self.offset}')

    def fill(self):
        if self.position < len(self.buffer):
            return True
        if self.eof:
            return False
        self.buffer = self.source.read(self.limits.chunk_bytes)
        self.position = 0
        if not self.buffer:
            self.eof = True
            return False
        self.size += len(self.buffer)
        if self.size > self.limits.max_file_bytes:
            self.resource('max_file_bytes')
        self.hash.update(self.buffer)
        self.max_buffer_bytes = max(self.max_buffer_bytes, len(self.buffer))
        return True

    def peek(self):
        return self.buffer[self.position] if self.fill() else None

    def advance(self, size):
        self.position += size
        self.offset += size
        if self.budget_end is not None and self.offset > self.budget_end:
            self.resource('max_record_bytes')

    def whitespace(self):
        while self.fill():
            end = _WHITESPACE.match(self.buffer, self.position).end()
            self.advance(end - self.position)
            if self.position < len(self.buffer):
                return

    def expect(self, byte):
        if self.peek() != byte:
            self.invalid(f'expected {chr(byte)!r}')
        self.advance(1)

    def intern(self, value, *, key=False):
        if _HEX_ID.fullmatch(value):
            self.id_occurrences += 1
            existing = self.ids.get(value)
            if existing is not None:
                return existing
            if len(self.ids) >= self.limits.max_unique_ids:
                self.resource('max_unique_ids')
            self.ids[value] = value
            return value
        if key:
            self.key_occurrences += 1
            existing = self.keys.get(value)
            if existing is not None:
                return existing
            if len(self.keys) >= self.limits.max_unique_keys:
                self.resource('max_unique_keys')
            self.keys[value] = value
        return value

    def string(self, *, key=False):
        start = self.offset
        raw = bytearray(b'"')
        escaped = False
        # Decode one bounded token with the C JSON decoder to retain exactly
        # Python's legacy string, escape and surrogate semantics.
        self.expect(34)
        while self.fill():
            begin = self.position
            closing = False
            if escaped:
                end = begin + 1
                escaped = False
            else:
                match = _STRING_SPECIAL.search(self.buffer, begin)
                end = len(self.buffer) if match is None else match.start() + 1
                if match is not None:
                    marker = self.buffer[end - 1]
                    if marker < 32:
                        self.invalid('unescaped control character in string')
                    escaped = marker == 92
                    closing = marker == 34
            self.advance(end - begin)
            length = self.offset - start
            if length > self.limits.max_token_bytes:
                self.resource('max_token_bytes')
            raw.extend(self.buffer[begin:end])
            if closing:
                self.max_token_bytes = max(self.max_token_bytes, length)
                try:
                    value = json.loads(raw.decode('utf-8'))
                except (ValueError, UnicodeError) as exc:
                    self.invalid(f'invalid JSON string: {exc}')
                return self.intern(value, key=key)
        self.invalid('truncated JSON string')

    def scalar(self):
        start = self.offset
        first = self.peek()
        if first in (116, 102, 110):
            literal, result = {116: (b'true', True), 102: (b'false', False), 110: (b'null', None)}[first]
            if len(literal) > self.limits.max_token_bytes:
                self.resource('max_token_bytes')
            for byte in literal:
                self.expect(byte)
            self.max_token_bytes = max(self.max_token_bytes, len(literal))
            return result
        if first is None:
            self.invalid('truncated JSON value')
        if first not in _NUMBER_CHARS:
            self.invalid('invalid JSON value')
        raw = bytearray()
        while self.peek() in _NUMBER_CHARS:
            raw.append(self.peek())
            self.advance(1)
            if self.offset - start > self.limits.max_token_bytes:
                self.resource('max_token_bytes')
        self.max_token_bytes = max(self.max_token_bytes, len(raw))
        if not _NUMBER.fullmatch(raw):
            self.invalid('invalid JSON number')
        try:
            result = float(raw) if any(x in raw for x in b'.eE') else int(raw)
        except ValueError as exc:
            self.resource(f'number conversion limit: {exc}')
        if type(result) is float and not (-float('inf') < result < float('inf')):
            self.invalid('nonfinite JSON number')
        return result

    def value(self, path=(), depth=0):
        self.whitespace()
        if depth > self.limits.max_depth:
            self.resource('max_depth')
        self.value_count += 1
        if self.value_count > self.limits.max_values:
            self.resource('max_values')
        start = self.offset
        previous_end = self.budget_end
        record = previous_end is None and path not in _ENVELOPES
        if record:
            self.budget_end = start + self.limits.max_record_bytes
        byte = self.peek()
        if byte == 123:
            result = self.object(path, depth)
        elif byte == 91:
            result = self.array(path, depth)
        elif byte == 34:
            result = self.string()
        else:
            result = self.scalar()
        if record:
            self.records += 1
            self.max_record_bytes = max(self.max_record_bytes, self.offset - start)
        self.budget_end = previous_end
        return result

    def object(self, path, depth):
        self.expect(123)
        result = {}
        self.whitespace()
        if self.peek() == 125:
            self.advance(1)
            return MappingProxyType(result)
        while True:
            if len(result) >= self.limits.max_container_items:
                self.resource('max_container_items')
            if self.peek() != 34:
                self.invalid('object key must be a JSON string')
            key = self.string(key=True)
            if key in result:
                self.invalid('duplicate object key')
            self.whitespace()
            self.expect(58)
            result[key] = self.value(path + (key,), depth + 1)
            self.whitespace()
            if self.peek() == 125:
                self.advance(1)
                return MappingProxyType(result)
            self.expect(44)
            self.whitespace()

    def array(self, path, depth):
        self.expect(91)
        result = []
        self.whitespace()
        if self.peek() == 93:
            self.advance(1)
            return ()
        while True:
            if len(result) >= self.limits.max_container_items:
                self.resource('max_container_items')
            result.append(self.value(path + (len(result),), depth + 1))
            self.whitespace()
            if self.peek() == 93:
                self.advance(1)
                return tuple(result)
            self.expect(44)
            self.whitespace()

    def stats(self):
        return MappingProxyType(dict(
            authoritative=False,
            scope='storage diagnostics only; no mathematical acceptance',
            values=self.value_count,
            records=self.records,
            unique_ids=len(self.ids),
            id_occurrences=self.id_occurrences,
            shared_id_occurrences=self.id_occurrences - len(self.ids),
            unique_keys=len(self.keys),
            key_occurrences=self.key_occurrences,
            max_buffer_bytes=self.max_buffer_bytes,
            max_token_bytes=self.max_token_bytes,
            max_record_bytes=self.max_record_bytes,
        ))


def load_capture(path, expected_sha256, expected_size_bytes, *, limits=CaptureLimits()):
    """Load all pinned bytes into deeply immutable JSON without a full raw copy.

    No handle is returned until EOF, pin checks and descriptor/path stability
    checks all pass. Failure is atomic from the caller's perspective. Only UTF-8
    JSON object documents with unique keys and finite numeric values are valid.
    Final-component symlinks and nonregular sources are rejected. Secure open
    requires OS support for both O_NOFOLLOW and O_NONBLOCK; otherwise loading
    fails closed. Identity is checked on the opened descriptor and path entry.
    """
    if type(expected_sha256) is not str or not _HEX_ID.fullmatch(expected_sha256):
        raise ValueError('expected_sha256 must be exactly 64 lowercase hex characters')
    if type(expected_size_bytes) is not int or expected_size_bytes < 0:
        raise ValueError('expected_size_bytes must be a nonnegative integer')
    if type(limits) is not CaptureLimits:
        raise TypeError('limits must be exactly CaptureLimits')
    if expected_size_bytes > limits.max_file_bytes:
        raise CaptureResourceError('unresolved_capture_resource: max_file_bytes')
    path = Path(path)
    nofollow = getattr(os, 'O_NOFOLLOW', 0)
    nonblock = getattr(os, 'O_NONBLOCK', 0)
    if not nofollow or not nonblock:
        raise CaptureIntegrityError('secure nonblocking no-follow open is unsupported')
    try:
        # Apply both flags atomically at open, not through a racy path precheck.
        # O_NONBLOCK prevents a FIFO open from waiting for a writer; O_NOFOLLOW
        # rejects a final-component symlink, including one installed in a race.
        def opener(name, flags):
            return os.open(name, flags | nofollow | nonblock)
        with open(path, 'rb', buffering=0, opener=opener) as source:
            initial = os.fstat(source.fileno())
            if not stat.S_ISREG(initial.st_mode):
                raise CaptureIntegrityError('capture source must be a regular file')
            if initial.st_size != expected_size_bytes:
                raise CaptureIntegrityError('capture size differs from expected_size_bytes')
            if _identity(path.lstat()) != _identity(initial):
                raise CaptureIntegrityError('capture path identity changed before reading')
            reader = _Reader(source, limits)
            payload = reader.value()
            if type(payload) is not MappingProxyType:
                raise CaptureFormatError('capture must be a JSON object')
            reader.whitespace()
            if reader.peek() is not None:
                raise CaptureFormatError(f'trailing content at byte {reader.offset}')
            if not reader.eof or reader.offset != reader.size:
                raise CaptureIntegrityError('capture source was not fully consumed')
            final = os.fstat(source.fileno())
            if _identity(initial) != _identity(final) or _identity(path.lstat()) != _identity(initial):
                raise CaptureIntegrityError('capture source identity changed while reading')
            if reader.size != expected_size_bytes:
                raise CaptureIntegrityError('consumed size differs from expected_size_bytes')
            digest = reader.hash.hexdigest()
            if digest != expected_sha256:
                raise CaptureIntegrityError('capture SHA-256 differs from expected_sha256')
            return LoadedCapture(payload, digest, reader.size, reader.stats())
    except (MemoryError, RecursionError) as exc:
        raise CaptureResourceError(f'unresolved_capture_resource: {type(exc).__name__}') from exc
    except OSError as exc:
        raise CaptureIntegrityError(f'capture source I/O or identity failure: {exc}') from exc
