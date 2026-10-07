"""Independent immutable input checks; synthetic structural data only."""
from collections.abc import Mapping
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import MappingProxyType
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from validation.capture5 import (
    CaptureFormatError, CaptureIntegrityError, CaptureLimits,
    CaptureResourceError, LoadedCapture, load_capture,
)


def canonical(value):
    """Local independent encoder, without producer/checker imports or cloning."""
    if isinstance(value, Mapping):
        return '{' + ','.join(json.dumps(k, ensure_ascii=True) + ':' + canonical(value[k])
                              for k in sorted(value)) + '}'
    if isinstance(value, (list, tuple)):
        return '[' + ','.join(canonical(v) for v in value) + ']'
    return json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(',', ':'))


def sample():
    first, second = 'a' * 64, 'b' * 64
    return dict(
        schema='original-schema',
        canonical={'nil': None, 'empty': {}, 'singleton': [False], 'number': -1.25e-3},
        bundle=dict(nodes={first: dict(id=first, parents=[second, second, first],
                                      guards=[{'x': [1, '1', True, None]}, {'x': []}]),
                           second: dict(id=second, parents=[], guards=[])},
                    roots=[first], batch_ids=[second],
                    batches=[dict(parents=[first, second]), dict(parents=[second, first])]),
        trace=dict(events=[dict(kind='first', payload={'family': first}),
                           dict(kind='last', payload={'family': second})]),
        callback_requests=[dict(parent=second, details=['x', [], {}])],
        unicode='线🦦 é \\ " \t\r\n',
    )


class CaptureReader(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'capture.json'

    def load(self, value, *, raw=False, **kwargs):
        data = value if raw else json.dumps(value, ensure_ascii=True, separators=(',', ':')).encode() + b'\n'
        self.path.write_bytes(data)
        return load_capture(self.path, hashlib.sha256(data).hexdigest(), len(data), **kwargs)

    def test_exact_semantics_canonical_hash_and_order(self):
        value = sample()
        loaded = self.load(value)
        self.assertIs(type(loaded), LoadedCapture)
        self.assertIs(type(loaded.payload), MappingProxyType)
        expected = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
        self.assertEqual(canonical(loaded.payload), expected)
        self.assertEqual(hashlib.sha256(canonical(loaded.payload).encode()).hexdigest(),
                         hashlib.sha256(expected.encode()).hexdigest())
        self.assertEqual(loaded.sha256, hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertEqual(loaded.size_bytes, self.path.stat().st_size)
        self.assertEqual([x['kind'] for x in loaded.payload['trace']['events']], ['first', 'last'])
        self.assertFalse(loaded.storage_stats['authoritative'])

    def test_every_nested_value_is_immutable(self):
        loaded = self.load(sample())
        def inspect(value):
            if isinstance(value, Mapping):
                self.assertIs(type(value), MappingProxyType)
                with self.assertRaises(TypeError):
                    value['forged'] = 1
                for child in value.values():
                    inspect(child)
            elif isinstance(value, (list, tuple)):
                self.assertIs(type(value), tuple)
                for child in value:
                    inspect(child)
            else:
                self.assertIn(type(value), (str, int, float, bool, type(None)))
        inspect(loaded.payload)
        inspect(loaded.storage_stats)
        with self.assertRaises(FrozenInstanceError):
            loaded.sha256 = 'c' * 64
        with self.assertRaises(FrozenInstanceError):
            CaptureLimits().chunk_bytes = 1

    def test_ids_and_keys_share_storage_without_conflating_unequal_values(self):
        loaded = self.load(sample())
        first, second = loaded.payload['bundle']['nodes'].keys()
        nodes = loaded.payload['bundle']['nodes']
        self.assertIs(first, nodes[first]['id'])
        self.assertIs(second, nodes[first]['parents'][0])
        self.assertIs(nodes[first]['parents'][0], nodes[first]['parents'][1])
        self.assertIsNot(first, second)
        key1 = next(k for k in nodes[first] if k == 'parents')
        key2 = next(k for k in nodes[second] if k == 'parents')
        self.assertIs(key1, key2)
        self.assertEqual(loaded.storage_stats['unique_ids'], 2)
        self.assertGreater(loaded.storage_stats['shared_id_occurrences'], 10)

    def test_chunk_boundaries_unicode_escapes_nested_empty_and_singleton(self):
        values = [sample(), {}, {'single': [[{'a': ''}]]},
                  {'x': '\ud800', 'y': '\udc00', 'z': '\ud83e\udda6'},
                  {'escapes': '\\"\\\\ / \b\f\n\r\t', 'number': -12.345e-100}]
        for value in values:
            for ascii_only in (True, False):
                try:
                    data = json.dumps(value, ensure_ascii=ascii_only).encode('utf-8')
                except UnicodeEncodeError:
                    continue
                expected = json.loads(data)
                for chunk in (1, 2, 3, 7, 63, 64, 65, 127):
                    with self.subTest(value=value, ascii_only=ascii_only, chunk=chunk):
                        loaded = self.load(data, raw=True, limits=replace(CaptureLimits(), chunk_bytes=chunk))
                        self.assertEqual(canonical(loaded.payload), canonical(expected))
                        self.assertLessEqual(loaded.storage_stats['max_buffer_bytes'], chunk)

    def test_duplicate_decoded_keys_rejected_at_every_level(self):
        for data in (b'{"x":1,"x":2}', b'{"x":1,"\\u0078":2}',
                     b'{"bundle":{"nodes":{"id":{"x":1,"x":2}}}}',
                     b'{"trace":{"events":[{"x":1,"x":2}]}}'):
            with self.subTest(data=data), self.assertRaisesRegex(CaptureFormatError, 'duplicate'):
                self.load(data, raw=True, limits=replace(CaptureLimits(), chunk_bytes=1))

    def test_malformed_nonfinite_and_nonobject_documents_rejected(self):
        invalid = [b'[]', b'null', b'{', b'{"x":', b'{"x":"unfinished',
                   b'{"x":"\\', b'{"x":1,}', b'{"x":[1,]}', b'{"x":NaN}',
                   b'{"x":Infinity}', b'{"x":-Infinity}', b'{"x":1e999}',
                   b'{"x":01}', b'{"x":+1}', b'{"x":.1}', b'{"x":1.}',
                   b'{"x":1e}', b'{"x":truefalse}', b'{"x":"\\q"}',
                   b'{"x":"\\uZZZZ"}', b'{"x":"\x00"}', b'{"x":"\xff"}',
                   b'\xef\xbb\xbf{}', b'{}\v', b'{}{}', b'{}garbage']
        for data in invalid:
            with self.subTest(data=data), self.assertRaises(CaptureFormatError):
                self.load(data, raw=True, limits=replace(CaptureLimits(), chunk_bytes=1))

    def test_every_truncated_prefix_fails(self):
        complete = b'{"x":[{},"\\u7ebf\\n\\\"\\\\",1.2e-3,true,false,null]}'
        for length in range(len(complete)):
            with self.subTest(length=length), self.assertRaises(CaptureFormatError):
                self.load(complete[:length], raw=True, limits=replace(CaptureLimits(), chunk_bytes=3))
        self.load(complete, raw=True)

    def test_pins_and_full_whitespace_consumption(self):
        data = b'{"x":1}' + b' \t\r\n' * 100
        loaded = self.load(data, raw=True, limits=replace(CaptureLimits(), chunk_bytes=3))
        self.assertEqual(loaded.sha256, hashlib.sha256(data).hexdigest())
        self.assertEqual(loaded.size_bytes, len(data))
        with self.assertRaisesRegex(CaptureIntegrityError, 'SHA-256'):
            load_capture(self.path, 'f' * 64, len(data))
        with self.assertRaisesRegex(CaptureIntegrityError, 'size'):
            load_capture(self.path, loaded.sha256, len(data) - 1)
        for digest, size in (('x', len(data)), ('A' * 64, len(data)), (loaded.sha256, True),
                             (loaded.sha256, -1)):
            with self.subTest(digest=digest, size=size), self.assertRaises(ValueError):
                load_capture(self.path, digest, size)

    def test_record_budget_applies_to_each_record_not_full_collection(self):
        for field in ('nodes', 'batches', 'events', 'callback_requests', 'metadata'):
            record = {'parents': ['a' * 64] * 8}
            if field == 'nodes':
                value = {'bundle': {'nodes': {str(i): record for i in range(5)}}}
            elif field == 'batches':
                value = {'bundle': {'batches': [record] * 5}}
            elif field == 'events':
                value = {'trace': {'events': [record] * 5}}
            else:
                value = {field: [record] * 5 if field == 'callback_requests' else record}
            with self.subTest(field=field):
                self.load(value, limits=replace(CaptureLimits(), max_record_bytes=600))
                with self.assertRaisesRegex(CaptureResourceError, 'max_record_bytes'):
                    self.load(value, limits=replace(CaptureLimits(), max_record_bytes=500))

    def test_resource_limits_never_report_mathematical_infeasibility(self):
        cases = [({'x': 'a' * 100}, dict(max_token_bytes=10)),
                 ({'x': 123456789012345}, dict(max_token_bytes=10)),
                 ({'x': [[[[1]]]]}, dict(max_depth=3)),
                 ({'x': [1, 2, 3]}, dict(max_values=3)),
                 ({'x': [1, 2, 3]}, dict(max_container_items=2)),
                 ({'x': 1, 'y': 2, 'z': 3}, dict(max_container_items=2)),
                 ({'x': ['a' * 64, 'b' * 64]}, dict(max_unique_ids=1)),
                 ({'x': 1, 'y': 2}, dict(max_unique_keys=1)),
                 ({'x': 'a' * 100}, dict(max_file_bytes=50, chunk_bytes=10))]
        for value, options in cases:
            with self.subTest(options=options), self.assertRaisesRegex(CaptureResourceError, 'unresolved_capture_resource'):
                self.load(value, limits=replace(CaptureLimits(), **options))
        with patch('validation.capture5.reader._Reader.value', side_effect=MemoryError):
            with self.assertRaisesRegex(CaptureResourceError, 'MemoryError'):
                self.load({})

    def test_changed_file_descriptor_identity_rejected(self):
        real_fstat = os.fstat
        calls = 0
        def fstat(fd):
            nonlocal calls
            result = real_fstat(fd)
            calls += 1
            if calls == 2:
                # Write a byte during the read's final identity observation.
                with self.path.open('ab') as stream:
                    stream.write(b' ')
                result = real_fstat(fd)
            return result
        with patch('validation.capture5.reader.os.fstat', side_effect=fstat):
            with self.assertRaisesRegex(CaptureIntegrityError, 'identity changed'):
                self.load({'x': 1})

    def test_path_replacement_rejected_even_with_identical_bytes(self):
        real_fstat = os.fstat
        calls = 0
        def fstat(fd):
            nonlocal calls
            result = real_fstat(fd)
            calls += 1
            if calls == 2:
                replacement = self.path.with_suffix('.new')
                replacement.write_bytes(self.path.read_bytes())
                replacement.replace(self.path)
            return result
        with patch('validation.capture5.reader.os.fstat', side_effect=fstat):
            with self.assertRaisesRegex(CaptureIntegrityError, 'identity changed'):
                self.load({'x': 1})

    def test_literal_tokens_respect_exact_budget_and_diagnostics(self):
        for literal in (b'true', b'false', b'null'):
            data = b'{"":' + literal + b'}'
            with self.subTest(literal=literal):
                loaded = self.load(data, raw=True, limits=replace(CaptureLimits(), max_token_bytes=len(literal)))
                self.assertEqual(loaded.storage_stats['max_token_bytes'], len(literal))
                with self.assertRaisesRegex(CaptureResourceError, 'max_token_bytes'):
                    self.load(data, raw=True, limits=replace(CaptureLimits(), max_token_bytes=len(literal) - 1))

    def test_nonregular_fifo_and_fifo_symlink_reject_without_blocking(self):
        fifo = self.path.with_suffix('.fifo')
        os.mkfifo(fifo)
        self.path.symlink_to(fifo)
        # A timeout protects this negative test against an accidental blocking
        # open regression. The child inherits the suite's resource ceiling.
        program = """
import sys
from validation.capture5 import CaptureIntegrityError, load_capture
try:
    load_capture(sys.argv[1], '0' * 64, 0)
except CaptureIntegrityError:
    print('rejected')
else:
    raise RuntimeError('nonregular source accepted')
"""
        for path in (fifo, self.path):
            with self.subTest(path=path):
                result = subprocess.run([sys.executable, '-c', program, str(path)], cwd=ROOT,
                                        capture_output=True, text=True, timeout=3)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), 'rejected')
        with self.assertRaises(CaptureIntegrityError):
            load_capture(Path(self.directory.name), '0' * 64, 0)

    def test_final_component_symlink_rejects_even_exact_pinned_bytes(self):
        data = b'{"x":1}'
        target = self.path.with_suffix('.target')
        target.write_bytes(data)
        self.path.symlink_to(target)
        with self.assertRaises(CaptureIntegrityError):
            load_capture(self.path, hashlib.sha256(data).hexdigest(), len(data))

    def test_symlink_substitution_during_open_rejected_atomically(self):
        data = b'{"x":1}'
        self.path.write_bytes(data)
        target = self.path.with_suffix('.target')
        target.write_bytes(data)
        real_open = os.open
        def substitute(name, flags):
            self.assertTrue(flags & os.O_NOFOLLOW)
            self.assertTrue(flags & os.O_NONBLOCK)
            self.path.unlink()
            self.path.symlink_to(target)
            return real_open(name, flags)
        with patch('validation.capture5.reader.os.open', side_effect=substitute):
            with self.assertRaises(CaptureIntegrityError):
                load_capture(self.path, hashlib.sha256(data).hexdigest(), len(data))

    def test_symlink_to_open_inode_replacement_rejected(self):
        real_fstat = os.fstat
        calls = 0
        def substitute(fd):
            nonlocal calls
            calls += 1
            if calls == 1:
                target = self.path.with_suffix('.target')
                self.path.rename(target)
                self.path.symlink_to(target)
            return real_fstat(fd)
        with patch('validation.capture5.reader.os.fstat', side_effect=substitute):
            with self.assertRaisesRegex(CaptureIntegrityError, 'path identity changed'):
                self.load({'x': 1})

    def test_missing_secure_open_flags_fails_closed(self):
        for name in ('O_NOFOLLOW', 'O_NONBLOCK'):
            with self.subTest(flag=name), patch.object(os, name, 0):
                with self.assertRaisesRegex(CaptureIntegrityError, 'unsupported'):
                    self.load({})

    def test_loader_uses_no_whole_file_read_or_producer_import(self):
        data = b'{"x": [1, 2, 3]}'
        self.path.write_bytes(data)
        with patch.object(Path, 'read_text', side_effect=AssertionError('whole file read')), \
             patch.object(Path, 'read_bytes', side_effect=AssertionError('whole file read')):
            load_capture(self.path, hashlib.sha256(data).hexdigest(), len(data))
        source = (ROOT / 'validation/capture5/reader.py').read_text()
        self.assertNotIn('from timecut5', source)
        self.assertNotIn('import timecut5', source)
        self.assertNotIn('independent_oracle', source)
        self.assertNotIn('import math', source)

    def test_repeated_parent_structural_sample_under_512_mib(self):
        # Isolated process: enforce a 512 MiB virtual-address ceiling as well as
        # inspecting process peak RSS. No solver, real C01 input, or LP runs.
        program = r'''
import hashlib, json, resource, sys, tempfile
from pathlib import Path
from validation.capture5 import load_capture
limit = 512 * 1024 ** 2
resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
def rss():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
report = {'baseline_peak_rss_bytes': rss()}
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / 'synthetic.json'
    digest = hashlib.sha256()
    size = 0
    def emit(stream, data):
        global size
        stream.write(data); digest.update(data); size += len(data)
    parent = 'a' * 64
    record = json.dumps({'parents': [parent] * 256, 'guards': [None] * 256}, separators=(',', ':')).encode()
    with path.open('wb') as stream:
        emit(stream, b'{"bundle":{"nodes":{')
        for i in range(2048):
            emit(stream, (b',' if i else b'') + json.dumps(format(i, '064x')).encode() + b':' + record)
        emit(stream, b'},"batches":[],"roots":[]},"trace":{"events":[]},"callback_requests":[]}')
    report['publication_peak_rss_bytes'] = rss()
    loaded = load_capture(path, digest.hexdigest(), size)
    report['loaded_peak_rss_bytes'] = rss()
    report['size_bytes'] = size
    report['sha256'] = digest.hexdigest()
    report['storage_stats'] = dict(loaded.storage_stats)
    nodes = loaded.payload['bundle']['nodes']
    assert len(nodes) == 2048
    all_parents = [row['parents'] for row in nodes.values()]
    assert sum(map(len, all_parents)) == 524288
    representative = all_parents[0][0]
    assert all(parent is representative for parents in all_parents for parent in parents)
    assert report['loaded_peak_rss_bytes'] < limit
print(json.dumps(report, sort_keys=True))
'''
        result = subprocess.run([sys.executable, '-c', program], cwd=ROOT,
                                text=True, capture_output=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertLess(report['loaded_peak_rss_bytes'], 512 * 1024 ** 2)
        self.assertEqual(report['storage_stats']['shared_id_occurrences'], 524287)
        self.assertLessEqual(report['storage_stats']['max_buffer_bytes'], 65536)
        print('capture5 structural memory: ' + json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    unittest.main()
