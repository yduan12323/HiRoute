"""Cold proof restart checks use hand certificates only; no optimizer or server."""
import base64
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import zlib

from experiments.time_cut_v2.recorded_real import block_archive, block_replay, plan
from experiments.time_cut_v2.recorded_real.archive_reader import ArchiveReader
from experiments.time_cut_v2.recorded_real.lp_stream_jobs import LPStreamJob
from tests.test_suffix_block_archive import FakeResults
from tests.test_suffix_block_certificates import declaration
from validation.suffix5.block_certificates import BlockCertificates
from validation.suffix5.test_convex_checker import hand_record


def population(groups):
    blocks, records = [], {}
    for block_id, start, values in groups:
        block = declaration(values)[0]
        block['range'].update(block_id=block_id, start=start, end=start + len(values))
        for row, record in zip(block['descriptors'], values):
            row['ordinal'] += start
            records[row['ordinal']] = record
        blocks.append(block)
    return blocks, records


def archive_rows(ctx, blocks, records, source, *, unresolved=(), omit=(), reverse=False):
    candidates = []
    for block in blocks:
        for descriptor in block['descriptors']:
            ordinal = descriptor['ordinal']
            if ordinal in omit:
                continue
            record = records[ordinal]
            job = LPStreamJob(source, block['range']['block_id'], ordinal,
                              plan.digest(record['model']), record['model'])
            generation = 'a' * 32
            candidates.append(dict(job=job.to_dict(), response_identity=job.header(generation),
                                   generation=generation, status='unresolved' if ordinal in unresolved else 'complete',
                                   reason='candidate timeout' if ordinal in unresolved else None,
                                   stages=record['stages'], result=None if ordinal in unresolved else record['result'],
                                   metrics={}, stdout_base64=base64.b64encode(b'hand proof\n').decode(),
                                   stderr_base64=''))
    if reverse:
        candidates.reverse()
    return list(block_archive.checked_records(ctx, blocks, source, FakeResults(candidates),
                                             deadline=time.monotonic() + 60))


class ColdBlockReplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'proof.jsonl.gz'
        self.ctx, first = hand_record('C', 0, True)
        _, second = hand_record('C', 1, True)
        _, excluded = hand_record('C', 2, True)
        self.blocks, self.records = population([(0, 0, [first]), (1352, 346112, [second, excluded])])
        self.source = dict(bundle=self.ctx.summary['bundle_sha256'], source_sha256='a' * 64)
        self.docs = archive_rows(self.ctx, self.blocks, self.records, self.source, reverse=True)
        # An accidental optimizer/process launch fails every test, including
        # the physical-witness reconstruction performed by cold replay.
        for name in ('Popen', 'run', 'check_output'):
            manager = patch('subprocess.' + name, side_effect=AssertionError('no process/LP allowed'))
            manager.start()
            self.addCleanup(manager.stop)

    def reader(self, docs=None, *, raw=None, incomplete=False, sha=None):
        if raw is None:
            raw = b''.join(block_archive.ArchiveEncoding().chunks(self.docs if docs is None else docs))
        self.path.write_bytes(raw)
        return ArchiveReader(self.path, compressed_sha256=sha or hashlib.sha256(raw).hexdigest(),
                             compressed_bytes=len(raw), allow_incomplete=incomplete)

    def replay(self, docs=None, **reader_options):
        return block_replay.replay_blocks(self.reader(docs, **reader_options), self.ctx, self.blocks,
                                          self.source, deadline=time.monotonic() + 60)

    @staticmethod
    def interrupted(docs, partial=b''):
        raw = b''.join(plan.canonical(row) + b'\n' for row in docs) + partial
        encoder = zlib.compressobj(wbits=31)
        return encoder.compress(raw) + encoder.flush(zlib.Z_SYNC_FLUSH)

    def test_full_roundtrip_preserves_records_ordinals_aggregates_and_witnesses(self):
        old_ctx = self.ctx
        self.ctx, _ = hand_record('C', 0, True)
        self.assertIsNot(self.ctx, old_ctx)
        receipt = self.replay()
        summary = receipt.summary()
        self.assertEqual(summary['reusable_block_ids'], [0, 1352])
        self.assertEqual(summary['certified_ordinals'], sorted(self.records))
        self.assertTrue(summary['archive']['gzip_eof'])
        self.assertTrue(summary['historical_attempt_claimed_complete'])
        self.assertFalse(summary['historical_runtime_revalidated'])
        for key in ('query_optimum_certified', 'full_population_complete', 'literal_G8_closed'):
            self.assertIs(summary[key], False)
        self.assertEqual({row['descriptor']['ordinal']: row['record'] for row in receipt.certificates()}, self.records)
        self.assertEqual([r['descriptor']['ordinal'] for r in receipt.certificates(block_id=1352)], [346112, 346113])
        for reference in summary['certificate_refs']:
            original = self.docs[reference['archive_row_index']]
            self.assertEqual(original['descriptor']['ordinal'], reference['model_ordinal'])
            self.assertEqual(reference['archive_row_sha256'],
                             hashlib.sha256(plan.canonical(original) + b'\n').hexdigest())
            self.assertEqual(reference['current_verification'], original['verification'])
        for result in summary['blocks']:
            original = next(row for row in self.docs if row['kind'] == 'block_report' and
                            row['report']['range']['block_id'] == result['report']['range']['block_id'])
            self.assertEqual(result['report']['aggregate'], original['report']['aggregate'])
            old, new = deepcopy(original['winner_witness']), deepcopy(result['winner_witness'])
            old.pop('timings'); new.pop('timings')
            self.assertEqual(old, new)
        certificate = next(receipt.certificates())
        certificate['record']['result']['J'] = '999'
        summary['certified_ordinals'].clear()
        self.assertEqual(receipt.summary()['checked_models'], 3)
        self.assertNotEqual(next(receipt.certificates())['record']['result'].get('J'), '999')

    def test_completed_archive_retains_good_rows_in_incomplete_block(self):
        docs = archive_rows(self.ctx, self.blocks, self.records, self.source, unresolved=(346113,))
        receipt = self.replay(docs)
        summary = receipt.summary()
        self.assertEqual(summary['reusable_block_ids'], [0])
        self.assertEqual(summary['checked_models'], 2)
        self.assertFalse(summary['historical_attempt_claimed_complete'])
        self.assertEqual(summary['coverage'][1]['unresolved_ordinals'], [346113])
        saved = list(receipt.certificates(block_id=1352))
        self.assertEqual([r['descriptor']['ordinal'] for r in saved], [346112])
        self.assertEqual(saved[0]['record'], self.records[346112])

    def test_254_hand_certificates_keep_ordinals_for_a_later_exact_join(self):
        # Repeat a tiny hand proof to exercise storage/accounting at one block's
        # capacity; this is no claim about the unavailable real pilot archive.
        start = 687872
        blocks, records = population([(2687, start, [self.records[346113]] * 256)])
        unresolved = (start + 63, start + 255)
        docs = archive_rows(self.ctx, blocks, records, self.source, unresolved=unresolved)
        receipt = block_replay.replay_blocks(self.reader(docs), self.ctx, blocks, self.source,
                                             deadline=time.monotonic() + 60)
        self.assertEqual(receipt.summary()['checked_models'], 254)
        self.assertEqual(receipt.summary()['reusable_block_ids'], [])
        self.assertEqual(len(receipt.summary()['certificate_refs']), 254)
        fresh_ctx, _ = hand_record('C', 2, True)
        later = BlockCertificates(fresh_ctx, blocks)
        saved = list(receipt.certificates(block_id=2687))
        self.assertEqual([row['descriptor']['ordinal'] for row in saved],
                         [ordinal for ordinal in range(start, start + 256) if ordinal not in unresolved])
        for row in saved:
            later.check(row['descriptor']['ordinal'], row['record'])
        for ordinal in unresolved:
            later.check(ordinal, records[ordinal])
        self.assertTrue(later.summary(2687)['complete_certificates'])
        self.assertEqual(later.summary(2687)['verified_models'], 256)

    def test_checkpoint_prefix_and_partial_next_row_preserve_exact_coverage(self):
        docs = archive_rows(self.ctx, self.blocks, self.records, self.source)
        prefix = docs[:4]  # header, complete first block, checkpoint, next model
        self.assertEqual([r['kind'] for r in prefix],
                         ['header', 'model_certificate', 'block_certificate_checkpoint', 'model_certificate'])
        raw = self.interrupted(prefix, b'{"kind":"model_cert')
        receipt = self.replay(raw=raw, incomplete=True)
        summary = receipt.summary()
        self.assertFalse(summary['archive']['gzip_eof'])
        self.assertEqual(summary['reusable_block_ids'], [0])
        self.assertEqual(summary['certified_ordinals'], [0, 346112])
        self.assertEqual(summary['coverage'][1]['unsubmitted_ordinals'], [346113])
        with self.assertRaises(ValueError):
            self.replay(raw=raw)

    def test_writer_sync_flush_checkpoint_recovers_without_trailer(self):
        documents = archive_rows(self.ctx, self.blocks, self.records, self.source)
        def interrupted():
            yield from documents[:3]
            raise TimeoutError('interrupted producer')
        encoding, saved = block_archive.ArchiveEncoding(), []
        with self.assertRaises(TimeoutError):
            for chunk in encoding.chunks(interrupted()):
                saved.append(chunk)
        receipt = self.replay(raw=b''.join(saved), incomplete=True)
        self.assertEqual(receipt.summary()['reusable_block_ids'], [0])
        self.assertEqual(receipt.summary()['certified_ordinals'], [0])

    def test_completed_record_without_checkpoint_only_retains_individual(self):
        docs = archive_rows(self.ctx, self.blocks, self.records, self.source)
        result = self.replay(raw=self.interrupted(docs[:2]), incomplete=True)
        self.assertEqual(result.summary()['reusable_block_ids'], [])
        self.assertEqual(result.summary()['certified_ordinals'], [0])

    def test_truncated_trailer_never_promotes_historical_footer_to_finalized(self):
        raw = b''.join(block_archive.ArchiveEncoding().chunks(self.docs))[:-5]
        result = self.replay(raw=raw, incomplete=True).summary()
        self.assertFalse(result['archive']['gzip_eof'])
        self.assertFalse(result['historical_archive_finalized'])
        self.assertTrue(result['historical_footer_present'])
        self.assertTrue(result['historical_attempt_claimed_complete'])
        self.assertFalse(result['historical_runtime_revalidated'])
        self.assertEqual(result['reusable_block_ids'], [0, 1352])

    def test_hash_failure_or_bad_later_row_never_returns_reusable_block(self):
        reader = self.reader(sha='f' * 64)
        with patch.object(block_replay, 'verify_model', side_effect=AssertionError('physical before pin')):
            with self.assertRaisesRegex(ValueError, 'hash/size'):
                block_replay.replay_blocks(reader, self.ctx, self.blocks, self.source,
                                          deadline=time.monotonic() + 60)
        self.assertIsNone(reader.summary)
        docs = archive_rows(self.ctx, self.blocks, self.records, self.source)
        raw = self.interrupted(docs[:3], b'{"broken":}\n')
        with self.assertRaises(ValueError):
            self.replay(raw=raw, incomplete=True)

    def test_duplicate_foreign_gap_and_missing_checkpoint_reject(self):
        for mode in ('duplicate', 'foreign', 'gap', 'checkpoint', 'after_footer'):
            docs = deepcopy(self.docs)
            if mode == 'duplicate':
                docs.insert(2, deepcopy(docs[1]))
            elif mode == 'foreign':
                docs[1]['descriptor']['ordinal'] = 99
            elif mode == 'gap':
                docs.pop(1)
            elif mode == 'checkpoint':
                docs = [row for row in docs if row['kind'] != 'block_certificate_checkpoint']
            else:
                docs.append(dict(kind='unknown'))
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.replay(docs)

    def test_missing_rows_can_be_retained_only_with_honest_incomplete_coverage(self):
        docs = archive_rows(self.ctx, self.blocks, self.records, self.source, omit=(346113,))
        result = self.replay(docs).summary()
        self.assertEqual(result['reusable_block_ids'], [0])
        self.assertEqual(result['coverage'][1]['unsubmitted_ordinals'], [346113])
        docs[-1]['transport'].update(submitted_count=3, terminal_count=3)
        with self.assertRaisesRegex(ValueError, 'gap'):
            self.replay(docs)

    def test_changed_record_certificate_model_bound_or_verified_flag_reject(self):
        for mode in ('result', 'certificate', 'bound', 'identity', 'verified', 'descriptor', 'checkpoint'):
            docs = deepcopy(self.docs)
            row = next(row for row in docs if row['kind'] == 'model_certificate' and row['descriptor']['ordinal'] == 0)
            if mode == 'result':
                row['record']['result']['J'] = '999'
            elif mode == 'certificate':
                row['record']['stages'][0]['certificate']['x'][0] = '999'
            elif mode == 'bound':
                row['record']['model']['H'] += 1
                job = LPStreamJob(self.source, 0, 0, plan.digest(row['record']['model']), row['record']['model'])
                row['candidate_identity'] = job.header('a' * 32)
            elif mode == 'identity':
                row['candidate_identity']['input_sha256'] = 'f' * 64
            elif mode == 'verified':
                row['verification']['independent_certificate_verified'] = False
            elif mode == 'descriptor':
                row['descriptor']['segment_id'] = 99
            else:
                checkpoint = next(r for r in docs if r['kind'] == 'block_certificate_checkpoint')
                checkpoint['report']['verified_models'] = 999
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.replay(docs)

    def test_changed_physical_witness_or_family_context_reject(self):
        docs = deepcopy(self.docs)
        witness = next(r for r in docs if r['kind'] == 'block_report')['winner_witness']
        witness['evidence']['witness']['events'][-1]['departure_energy'] = '999'
        with self.assertRaisesRegex(ValueError, 'physical witness'):
            self.replay(docs)
        other_ctx, _ = hand_record('C', 1, False)
        with self.assertRaises(ValueError):
            block_replay.replay_blocks(self.reader(), other_ctx, self.blocks, self.source,
                                      deadline=time.monotonic() + 60)
        with self.assertRaisesRegex(ValueError, 'genuine checked'):
            block_replay.replay_blocks(self.reader(), SimpleNamespace(summary=self.ctx.summary), self.blocks,
                                      self.source, deadline=time.monotonic() + 60)

    def test_changed_source_or_unresolved_model_identity_reject(self):
        docs = deepcopy(self.docs)
        docs[0]['source_context']['source_sha256'] = 'f' * 64
        with self.assertRaisesRegex(ValueError, 'source'):
            self.replay(docs)
        docs = archive_rows(self.ctx, self.blocks, self.records, self.source, unresolved=(346113,))
        candidate = next(r for r in docs if r['kind'] == 'unresolved_model')['candidate']
        # Even correctly rehashed unresolved jobs must name their admitted model.
        model = self.records[346112]['model']
        job = LPStreamJob(self.source, 1352, 346113, plan.digest(model), model)
        candidate.update(job=job.to_dict(), response_identity=job.header('a' * 32))
        with self.assertRaisesRegex(ValueError, 'admitted model'):
            self.replay(docs)

    def test_late_certificate_and_physical_timers_fail_closed(self):
        for failing_call in (1, 4):
            calls = []
            @contextmanager
            def late(deadline):
                calls.append(deadline)
                yield
                if len(calls) == failing_call:
                    raise TimeoutError('late replay verification deadline')
            with self.subTest(failing_call=failing_call), patch.object(block_replay, 'verification_deadline', late):
                with self.assertRaises(TimeoutError):
                    self.replay()
        with self.assertRaisesRegex(ValueError, 'deadline'):
            block_replay.replay_blocks(self.reader(), self.ctx, self.blocks, self.source,
                                      deadline=time.monotonic() - 1)

    def test_guard_covers_bounded_reads_and_callback_mutation_does_not_rebind(self):
        blocks, source = deepcopy(self.blocks), deepcopy(self.source)
        calls = []
        def mutate():
            calls.append(1)
            source['source_sha256'] = 'f' * 64
            blocks[0]['range']['block_id'] = 99
        receipt = block_replay.replay_blocks(self.reader(), self.ctx, blocks, source,
                                             deadline=time.monotonic() + 60, before=mutate)
        self.assertEqual(receipt.summary()['reusable_block_ids'], [0, 1352])
        self.assertEqual(receipt.summary()['source_context'], self.source)
        self.assertGreater(len(calls), len(self.docs))

    def test_all_excluded_block_requires_no_physical_witness(self):
        blocks, records = population([(2687, 687872, [self.records[346113]])])
        docs = archive_rows(self.ctx, blocks, records, self.source)
        with patch.object(block_replay, 'verify_model', side_effect=AssertionError('empty block witness')):
            receipt = block_replay.replay_blocks(self.reader(docs), self.ctx, blocks, self.source,
                                                 deadline=time.monotonic() + 60)
        self.assertEqual(receipt.summary()['reusable_block_ids'], [2687])
        self.assertTrue(receipt.summary()['blocks'][0]['report']['physical_witness_not_required'])
        report = next(row for row in docs if row['kind'] == 'block_report')
        report['report']['physical_witness_verified'] = True
        report['winner_witness'] = {'arbitrary': 'forged physical witness'}
        with self.assertRaisesRegex(ValueError, 'empty block'):
            block_replay.replay_blocks(self.reader(docs), self.ctx, blocks, self.source,
                                      deadline=time.monotonic() + 60)

    def test_finished_gzip_missing_footer_or_model_after_reports_reject(self):
        with self.assertRaisesRegex(ValueError, 'grammar'):
            self.replay(self.docs[:-1])
        docs = deepcopy(self.docs)
        first_report = next(i for i, row in enumerate(docs) if row['kind'] == 'block_report')
        docs.insert(first_report + 1, deepcopy(docs[1]))
        with self.assertRaisesRegex(ValueError, 'reporting'):
            self.replay(docs)
        with self.assertRaisesRegex(ValueError, 'partial record after'):
            self.replay(raw=self.interrupted(self.docs, b'{'), incomplete=True)

    def test_missing_required_model_field_is_a_validation_error(self):
        docs = deepcopy(self.docs)
        del docs[1]['descriptor']
        with self.assertRaises(ValueError):
            self.replay(docs)


if __name__ == '__main__':
    unittest.main()
