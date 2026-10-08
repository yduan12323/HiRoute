"""Bounded pinned archive decoding with hand-written rows; no solver or LP."""
import gzip
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

from experiments.time_cut_v2.recorded_real import archive_reader as reader_module
from experiments.time_cut_v2.recorded_real.block_archive import ArchiveEncoding
from experiments.time_cut_v2.recorded_real.domain import chunks


class ArchiveReaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / 'proofs.jsonl.gz'

    def reader(self, data, **kwargs):
        self.path.write_bytes(data)
        pins = dict(compressed_sha256=hashlib.sha256(data).hexdigest(),
                    compressed_bytes=len(data))
        pins.update(kwargs)
        return reader_module.ArchiveReader(self.path, **pins)

    def assert_rejected(self, data, **kwargs):
        reader = None
        with self.assertRaises(ValueError):
            reader = self.reader(data, **kwargs)
            list(reader)
        if reader is not None:
            self.assertIsNone(reader.summary)

    @staticmethod
    def raw(rows):
        return b''.join(part for row in rows for part in chunks(row))

    @staticmethod
    def prefix(raw):
        compressor = zlib.compressobj(wbits=31)
        return compressor.compress(raw) + compressor.flush(zlib.Z_SYNC_FLUSH)

    def test_archive_encoding_roundtrip_and_summary_only_after_exhaustion(self):
        rows = [dict(kind='header', nested={'text': 'caf\u00e9', 'values': [1, None, True]}),
                dict(kind='block_certificate_checkpoint', acceptance=False),
                dict(kind='footer', complete=True)]
        encoding = ArchiveEncoding()
        encoded = b''.join(encoding.chunks(rows))
        raw = self.raw(rows)
        reader = self.reader(encoded)
        self.assertIsNone(reader.summary)
        iterator = iter(reader)
        for row in rows:
            self.assertEqual(next(iterator), row)
            self.assertIsNone(reader.summary)
        with self.assertRaises(StopIteration):
            next(iterator)
        expected = dict(compressed_bytes=len(encoded),
                        compressed_sha256=hashlib.sha256(encoded).hexdigest(),
                        uncompressed_bytes=len(raw),
                        uncompressed_sha256=hashlib.sha256(raw).hexdigest(),
                        rows=len(rows), gzip_eof=True, trailing_partial_row_bytes=0)
        for name, value in expected.items():
            self.assertEqual(reader.summary[name], value, name)
        self.assertEqual(reader.summary['uncompressed_sha256'],
                         encoding.summary()['uncompressed_sha256'])

    def test_rows_and_summary_do_not_alias_internal_or_later_values(self):
        rows = [{'nested': {'values': [1]}}, {'nested': {'values': [1]}}]
        raw = self.raw(rows)
        reader = self.reader(gzip.compress(raw))
        iterator = iter(reader)
        first = next(iterator)
        first['nested']['values'].append('caller mutation')
        self.assertEqual(next(iterator), rows[1])
        with self.assertRaises(StopIteration):
            next(iterator)
        summary = reader.summary
        summary['rows'] = -1
        summary['uncompressed_sha256'] = 'mutated'
        self.assertEqual(reader.summary['rows'], 2)
        self.assertEqual(reader.summary['uncompressed_sha256'], hashlib.sha256(raw).hexdigest())

    def test_hash_and_size_pins_are_required_for_consumed_bytes(self):
        encoded = gzip.compress(self.raw([{'value': 1}]))
        self.assert_rejected(encoded, compressed_sha256='0' * 64)
        for size in (len(encoded) - 1, len(encoded) + 1):
            with self.subTest(size=size):
                self.assert_rejected(encoded, compressed_bytes=size)
        original = gzip.compress(self.raw([{'value': 1}]), mtime=0)
        changed = gzip.compress(self.raw([{'value': 2}]), mtime=0)
        self.assertEqual(len(original), len(changed))
        reader = self.reader(original)
        self.path.write_bytes(changed)
        with self.assertRaises(ValueError):
            list(reader)
        self.assertIsNone(reader.summary)

    def test_noncanonical_duplicate_nonfinite_and_malformed_rows_are_rejected(self):
        invalid = [b'{"b":2,"a":1}\n', b'{"a": 1}\n', b'{"a":1}\r\n',
                   b'{"a":1,"a":2}\n', b'{"outer":{"a":1,"a":2}}\n',
                   b'{"value":NaN}\n', b'{"value":Infinity}\n',
                   b'{"value":-Infinity}\n', b'{"value":1e999}\n',
                   b'{"value":1e0}\n', b'{"value":"\xc3\xa9"}\n',
                   b'{"value":"\\u0061"}\n', b'{"value":"\xff"}\n',
                   b'\n', b'not-json\n', b'{"value":\n']
        for raw in invalid:
            for incomplete in (False, True):
                with self.subTest(raw=raw, allow_incomplete=incomplete):
                    self.assert_rejected(gzip.compress(raw), allow_incomplete=incomplete)

    def test_corrupt_crc_and_trailing_or_concatenated_gzip_are_rejected(self):
        encoded = gzip.compress(self.raw([{'valid': True}]))
        corrupt = bytearray(encoded)
        corrupt[-8] ^= 1
        invalid = [bytes(corrupt), encoded + b'trailing', encoded + b'\x00',
                   encoded + gzip.compress(b''), encoded + encoded]
        for data in invalid:
            for incomplete in (False, True):
                with self.subTest(tail=data[-12:], allow_incomplete=incomplete):
                    self.assert_rejected(data, allow_incomplete=incomplete)

    def test_row_raw_and_compressed_caps_fail_closed_at_actual_bytes(self):
        row = {'value': 'bounded payload'}
        raw = self.raw([row])
        encoded = gzip.compress(raw)
        for name, actual in (('MAX_ROW_BYTES', len(raw)), ('MAX_RAW_BYTES', len(raw)),
                             ('MAX_COMPRESSED_BYTES', len(encoded))):
            with self.subTest(cap=name):
                with patch.object(reader_module, name, actual - 1):
                    self.assert_rejected(encoded)
                with patch.object(reader_module, name, actual):
                    self.assertEqual(list(self.reader(encoded)), [row])
        with patch.object(reader_module, 'MAX_ROW_BYTES', len(raw)):
            self.assertEqual(list(self.reader(gzip.compress(raw * 3))), [row] * 3)
        with patch.object(reader_module, 'MAX_RAW_BYTES', len(raw) * 3 - 1):
            self.assert_rejected(gzip.compress(raw * 3))

    def test_valid_high_compression_ratio_is_not_an_archive_failure(self):
        rows = [{'payload': 'a' * (1024 * 1024)}]
        encoding = ArchiveEncoding()
        encoded = b''.join(encoding.chunks(rows))
        self.assertGreater(encoding.raw_bytes / len(encoded), 500)
        reader = self.reader(encoded)
        self.assertEqual(list(reader), rows)
        self.assertEqual(reader.summary['uncompressed_bytes'], encoding.raw_bytes)

    def test_optional_raw_budget_preserves_default_bytes_and_summary(self):
        rows = [{'payload': 'x'*40}, {'other': True}]
        raw = self.raw(rows)
        encoded = gzip.compress(raw)
        default = self.reader(encoded)
        self.assertEqual(list(default), rows)
        expected = default.summary
        for cap in (len(raw), reader_module.MAX_RAW_BYTES):
            reader = self.reader(encoded, max_raw_bytes=cap)
            self.assertEqual(list(reader), rows)
            self.assertEqual(reader.summary, expected)
        self.assert_rejected(encoded, max_raw_bytes=len(raw)-1)
        self.assert_rejected(encoded, max_raw_bytes=0)
        self.assertEqual(list(self.reader(gzip.compress(b''), max_raw_bytes=0)), [])

    def test_raw_budget_is_exact_tightening_only_and_set_before_reading(self):
        encoded = gzip.compress(self.raw([{'value': 1}]))
        for invalid in (True, False, -1, 1.0, '10', reader_module.MAX_RAW_BYTES+1):
            with self.subTest(invalid=invalid):
                self.assert_rejected(encoded, max_raw_bytes=invalid)
                reader = self.reader(encoded)
                with self.assertRaises(ValueError):
                    reader.limit_raw_bytes(invalid)
        reader = self.reader(encoded, max_raw_bytes=1)
        reader.limit_raw_bytes(reader_module.MAX_RAW_BYTES)
        with self.assertRaisesRegex(ValueError, 'uncompressed archive byte cap'):
            list(reader)
        reader = self.reader(encoded)
        list(reader)
        with self.assertRaisesRegex(ValueError, 'precede reading'):
            reader.limit_raw_bytes(0)

    def test_small_remaining_budget_stops_decoder_at_first_overflow_byte(self):
        encoded = gzip.compress(self.raw([{'payload': 'x'*100000}]))
        real_decoder = zlib.decompressobj
        outputs = []
        class ObservedDecoder:
            def __init__(self, *args, **kwargs):
                self.decoder = real_decoder(*args, **kwargs)
            def decompress(self, data, max_length=0):
                result = self.decoder.decompress(data, max_length)
                outputs.append(len(result))
                return result
            def __getattr__(self, name):
                return getattr(self.decoder, name)
        with patch.object(reader_module.zlib, 'decompressobj', ObservedDecoder):
            self.assert_rejected(encoded, max_raw_bytes=17)
        self.assertEqual(sum(outputs), 18)

    def test_incomplete_trailing_bytes_consume_shared_raw_budget(self):
        raw = self.raw([{'value': 1}])+b'{"partial":'
        encoded = self.prefix(raw)
        self.assert_rejected(encoded, allow_incomplete=True, max_raw_bytes=len(raw)-1)
        reader = self.reader(encoded, allow_incomplete=True, max_raw_bytes=len(raw))
        self.assertEqual(list(reader), [{'value': 1}])
        self.assertEqual(reader.summary['uncompressed_bytes'], len(raw))

    def test_input_reads_and_decoder_output_are_bounded_chunks(self):
        rows = [{'index': i, 'payload': hashlib.sha256(str(i).encode()).hexdigest() * 7}
                for i in range(120)]
        encoded = b''.join(ArchiveEncoding().chunks(rows))
        chunk_bytes = 97
        read_sizes, decode_sizes, output_sizes, before_calls = [], [], [], []
        real_read = os.read
        real_decoder = zlib.decompressobj
        def bounded_read(fd, size):
            read_sizes.append(size)
            self.assertGreater(size, 0)
            self.assertLessEqual(size, chunk_bytes)
            return real_read(fd, size)
        case = self
        class ObservedDecoder:
            def __init__(self, *args, **kwargs):
                self.decoder = real_decoder(*args, **kwargs)
            def decompress(self, data, max_length=0):
                decode_sizes.append(max_length)
                case.assertGreater(max_length, 0)
                case.assertLessEqual(max_length, chunk_bytes)
                result = self.decoder.decompress(data, max_length)
                output_sizes.append(len(result))
                case.assertLessEqual(len(result), chunk_bytes)
                return result
            def __getattr__(self, name):
                return getattr(self.decoder, name)
        reader = self.reader(encoded, before=lambda: before_calls.append(True))
        with patch.object(reader_module, 'CHUNK_BYTES', chunk_bytes), \
                patch.object(reader_module.os, 'read', bounded_read), \
                patch.object(reader_module.zlib, 'decompressobj', ObservedDecoder):
            self.assertEqual(list(reader), rows)
        self.assertGreater(len(read_sizes), 1)
        self.assertGreater(len(decode_sizes), 1)
        self.assertGreater(len(before_calls), 1)
        self.assertEqual(sum(output_sizes), reader.summary['uncompressed_bytes'])

    def test_incomplete_archive_encoding_checkpoint_requires_explicit_opt_in(self):
        rows = [dict(kind='header'), dict(kind='block_certificate_checkpoint', acceptance=False)]
        def interrupted():
            yield from rows
            raise TimeoutError('producer interrupted after checkpoint')
        encoding = ArchiveEncoding()
        parts = []
        with self.assertRaises(TimeoutError):
            for part in encoding.chunks(interrupted()):
                parts.append(part)
        encoded = b''.join(parts)
        self.assertFalse(encoding.complete)
        self.assert_rejected(encoded)
        reader = self.reader(encoded, allow_incomplete=True)
        self.assertEqual(list(reader), rows)
        self.assertFalse(reader.summary['gzip_eof'])
        self.assertEqual(reader.summary['trailing_partial_row_bytes'], 0)
        self.assertEqual(reader.summary['uncompressed_sha256'],
                         hashlib.sha256(self.raw(rows)).hexdigest())

    def test_incomplete_partial_row_is_counted_but_never_yielded(self):
        rows = [{'valid': True}]
        tail = b'{"unfinished":'
        raw = self.raw(rows) + tail
        encoded = self.prefix(raw)
        self.assert_rejected(encoded)
        reader = self.reader(encoded, allow_incomplete=True)
        self.assertEqual(list(reader), rows)
        summary = reader.summary
        self.assertEqual(summary['rows'], 1)
        self.assertEqual(summary['trailing_partial_row_bytes'], len(tail))
        self.assertEqual(summary['uncompressed_bytes'], len(raw))
        self.assertEqual(summary['uncompressed_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertFalse(summary['gzip_eof'])
        with patch.object(reader_module, 'MAX_ROW_BYTES', 16):
            self.assert_rejected(self.prefix(self.raw(rows) + b'x' * 17), allow_incomplete=True)

    def test_incomplete_mode_still_rejects_malformed_complete_newline_row(self):
        encoded = self.prefix(self.raw([{'valid': True}]) + b'{broken}\n' + b'{"partial":')
        self.assert_rejected(encoded, allow_incomplete=True)

    def test_missing_final_newline_is_rejected_without_opt_in(self):
        for incomplete in (False, True):
            self.assert_rejected(gzip.compress(b'{"valid":true}'), allow_incomplete=incomplete)

    def test_before_exception_leaves_no_success_summary(self):
        def stop():
            raise TimeoutError('reader budget exhausted')
        reader = self.reader(gzip.compress(self.raw([{'valid': True}])), before=stop)
        with self.assertRaises(TimeoutError):
            list(reader)
        self.assertIsNone(reader.summary)

    def test_symlink_and_directory_inputs_are_rejected(self):
        encoded = gzip.compress(self.raw([{'valid': True}]))
        self.path.write_bytes(encoded)
        link = self.root / 'proof-link.gz'
        link.symlink_to(self.path)
        ancestor = self.root / 'directory-link'
        ancestor.symlink_to(self.root, target_is_directory=True)
        for path in (link, ancestor / self.path.name, self.root):
            with self.subTest(path=path), self.assertRaises((ValueError, OSError)):
                reader = reader_module.ArchiveReader(path, compressed_sha256=hashlib.sha256(encoded).hexdigest(),
                                                     compressed_bytes=len(encoded))
                list(reader)

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'FIFO requires POSIX')
    def test_fifo_is_rejected_without_waiting_for_a_writer(self):
        fifo = self.root / 'proof-fifo.gz'
        os.mkfifo(fifo)
        script = '''
import sys
from experiments.time_cut_v2.recorded_real.archive_reader import ArchiveReader
try:
    reader = ArchiveReader(sys.argv[1], compressed_sha256='0' * 64, compressed_bytes=1)
    list(reader)
except (ValueError, OSError):
    sys.exit(0)
sys.exit(1)
'''
        root = Path(__file__).resolve().parents[1]
        env = dict(os.environ)
        env['PYTHONPATH'] = os.pathsep.join((str(root), str(root / 'src'), env.get('PYTHONPATH', '')))
        result = subprocess.run([sys.executable, '-c', script, str(fifo)], cwd=root, env=env,
                                capture_output=True, text=True, timeout=5, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
