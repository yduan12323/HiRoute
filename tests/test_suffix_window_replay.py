"""Frozen cold-replay envelopes with tiny hand certificates, never an LP."""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from experiments.time_cut_v2.recorded_real import archive_reader, block_archive, block_replay, plan
from experiments.time_cut_v2.recorded_real.archive_reader import ArchiveReader
from tests import test_suffix_block_replay as replay_fixtures
from tests.test_suffix_block_replay import archive_rows, population
from validation.suffix5.test_convex_checker import hand_record


def without_timings(value):
    if type(value) is dict:
        return {key: without_timings(child) for key, child in value.items() if key != 'timings'}
    if type(value) is list:
        return [without_timings(child) for child in value]
    return value


class WindowColdReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx, cls.winner = hand_record('C', 0, True)
        _, cls.excluded = hand_record('C', 2, True)
        # Original block IDs and ordinals are deliberately not rebased to zero.
        cls.blocks, cls.records = population([
            (number, number * 256, [cls.winner, cls.excluded]) for number in range(100, 132)])
        cls.source = dict(bundle=cls.ctx.summary['bundle_sha256'], source_sha256='a' * 64)
        cls.docs = archive_rows(cls.ctx, cls.blocks, cls.records, cls.source, reverse=True)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'window.jsonl.gz'
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

    def replay(self, *, docs=None, blocks=None, profile='window32/8192', **options):
        return block_replay.replay_blocks(
            self.reader(docs), self.ctx, self.blocks if blocks is None else blocks,
            self.source, deadline=time.monotonic() + 60, replay_profile=profile, **options)

    def test_32_blocks_recheck_certificates_original_row_refs_and_physical_winners(self):
        fresh_ctx, _ = hand_record('C', 0, True)
        with patch.object(block_replay, 'verify_model', wraps=block_replay.verify_model) as physical:
            receipt = block_replay.replay_blocks(
                self.reader(), fresh_ctx, self.blocks, self.source,
                deadline=time.monotonic() + 60, replay_profile='window32/8192')
        result = receipt.summary()
        self.assertEqual(result['reusable_block_ids'], list(range(100, 132)))
        self.assertEqual(result['checked_models'], 64)
        self.assertEqual(result['expected_models'], 64)
        self.assertEqual(result['certified_ordinals'], sorted(self.records))
        self.assertEqual(physical.call_count, 32)
        self.assertEqual({row['descriptor']['ordinal']: row['record']
                          for row in receipt.certificates()}, self.records)
        for reference in result['certificate_refs']:
            original = self.docs[reference['archive_row_index']]
            self.assertEqual(original['descriptor']['ordinal'], reference['model_ordinal'])
            self.assertEqual(reference['archive_row_sha256'],
                             hashlib.sha256(plan.canonical(original) + b'\n').hexdigest())
            self.assertEqual(reference['current_verification'], original['verification'])
        for key in ('historical_runtime_revalidated', 'query_optimum_certified',
                    'full_population_complete', 'literal_G8_closed'):
            self.assertIs(result[key], False)
        self.assertTrue(result['historical_attempt_claimed_complete'])

    def test_exact_frozen_maxima_admit_header_only_without_claiming_any_certificate(self):
        # Exercise all 8,192 descriptor slots, without running 8,192 models or
        # confusing envelope admission with checked certificate coverage.
        for profile, count in (('pilot4/1024', 4), ('window32/8192', 32)):
            blocks, _ = population([(i, i * 256, [self.excluded] * 256) for i in range(count)])
            header = dict(kind='header', schema='hiroute-suffix-block-proof-archive-v1',
                          source_context=self.source, expected_models=count * 256,
                          blocks=[block['range'] for block in blocks], certificate_reuse_enabled=False)
            raw = replay_fixtures.ColdBlockReplayTests.interrupted([header])
            with self.subTest(profile=profile):
                receipt = block_replay.replay_blocks(
                    self.reader(raw=raw, incomplete=True), self.ctx, blocks, self.source,
                    deadline=time.monotonic() + 60, replay_profile=profile)
                result = receipt.summary()
                self.assertEqual(result['expected_models'], count * 256)
                self.assertEqual(result['checked_models'], 0)
                self.assertEqual(result['observed_models'], 0)
                self.assertEqual(result['reusable_block_ids'], [])
                self.assertEqual(len(result['coverage']), count)
                self.assertEqual(sum(len(row['unsubmitted_ordinals']) for row in result['coverage']),
                                 count * 256)
                self.assertFalse(result['historical_footer_present'])

    def test_over_cap_and_malformed_blocks_reject_before_maps_or_reader(self):
        class ListSubclass(list):
            pass
        for profile, count in (('pilot4/1024', 4), ('window32/8192', 32)):
            blocks, _ = population([(i, i * 256, [self.excluded] * 256) for i in range(count)])
            too_many_models = deepcopy(blocks)
            too_many_models[-1]['descriptors'].append(deepcopy(blocks[-1]['descriptors'][-1]))
            too_many_models[-1]['range']['end'] += 1
            too_many_models[-1]['range']['model_count'] += 1
            malformed = [[], (), ListSubclass(blocks), blocks + [deepcopy(blocks[-1])],
                         too_many_models, [None], [dict(descriptors=())], [dict(descriptors=[])]]
            for bad in malformed:
                with self.subTest(profile=profile, kind=type(bad).__name__, count=len(bad)), \
                     patch.object(block_replay, 'BlockCertificates',
                                  side_effect=AssertionError('declarations reached model map')), \
                     patch.object(ArchiveReader, 'iter_rows', side_effect=AssertionError('reader started')):
                    with self.assertRaises(ValueError):
                        self.replay(blocks=bad, profile=profile)

    def test_profile_is_a_strict_frozen_name_and_default_still_rejects_five_blocks(self):
        class StringSubclass(str):
            pass
        for value in (None, True, 32, 8192, 32.0, [], {}, b'window32/8192',
                      StringSubclass('window32/8192'), 'window32', 'window32/8193', 'pilot4/8192'):
            with self.subTest(profile=repr(value)), \
                 patch.object(block_replay, 'BlockCertificates', side_effect=AssertionError('profile reached map')):
                with self.assertRaisesRegex(ValueError, 'profile'):
                    self.replay(profile=value)
        with self.assertRaisesRegex(ValueError, 'block count'):
            block_replay.replay_blocks(self.reader(), self.ctx, self.blocks[:5], self.source,
                                       deadline=time.monotonic() + 60)
        with self.assertRaises(ValueError):
            self.replay(max_models=8193)

    def test_four_block_default_and_explicit_profiles_have_identical_wire_receipts(self):
        blocks = self.blocks[:4]
        records = {row['ordinal']: self.records[row['ordinal']]
                   for block in blocks for row in block['descriptors']}
        docs = archive_rows(self.ctx, blocks, records, self.source, reverse=True)
        receipts = []
        for options in ({}, dict(replay_profile='pilot4/1024'), dict(replay_profile='window32/8192')):
            receipt = block_replay.replay_blocks(self.reader(docs), self.ctx, blocks, self.source,
                                                 deadline=time.monotonic() + 60, **options)
            receipts.append((plan.canonical(without_timings(receipt.summary())),
                             tuple(plan.canonical(row) for row in receipt.certificates())))
        self.assertEqual(receipts[0], receipts[1])
        self.assertEqual(receipts[0], receipts[2])

    def test_incomplete_last_block_preserves_individually_checked_rows(self):
        missing = self.blocks[-1]['range']['start'] + 1
        docs = archive_rows(self.ctx, self.blocks, self.records, self.source, unresolved=(missing,))
        receipt = self.replay(docs=docs)
        result = receipt.summary()
        self.assertEqual(result['reusable_block_ids'], list(range(100, 131)))
        self.assertEqual(result['checked_models'], 63)
        self.assertEqual(result['coverage'][-1]['unresolved_ordinals'], [missing])
        self.assertFalse(result['historical_attempt_claimed_complete'])
        self.assertEqual([row['descriptor']['ordinal'] for row in receipt.certificates(block_id=131)],
                         [missing - 1])
        # Even a good complete block needs its immediate checkpoint to be reusable.
        ordered = archive_rows(self.ctx, self.blocks, self.records, self.source)
        raw = replay_fixtures.ColdBlockReplayTests.interrupted(ordered[:3])
        prefix = block_replay.replay_blocks(
            self.reader(raw=raw, incomplete=True), self.ctx, self.blocks, self.source,
            deadline=time.monotonic() + 60, replay_profile='window32/8192')
        self.assertEqual(prefix.summary()['reusable_block_ids'], [])
        self.assertEqual(prefix.summary()['certified_ordinals'], [25600, 25601])

    def test_late_tampering_checkpoint_gaps_and_physical_receipts_fail_closed(self):
        for mode in ('certificate', 'checkpoint', 'physical', 'gap'):
            docs = deepcopy(self.docs)
            if mode == 'certificate':
                row = next(row for row in reversed(docs) if row['kind'] == 'model_certificate')
                row['record']['result']['J'] = '999'
            elif mode == 'checkpoint':
                row = next(row for row in reversed(docs) if row['kind'] == 'block_certificate_checkpoint')
                docs.remove(row)
            elif mode == 'physical':
                row = next(row for row in reversed(docs) if row['kind'] == 'block_report')
                row['winner_witness']['evidence']['witness']['events'][-1]['departure_energy'] = '999'
            else:
                docs.remove(next(row for row in reversed(docs) if row['kind'] == 'model_certificate'))
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.replay(docs=docs)

    def test_bad_pin_precedes_any_physical_authority(self):
        reader = self.reader(sha='f' * 64)
        with patch.object(block_replay, 'verify_model', side_effect=AssertionError('physical before pin')):
            with self.assertRaisesRegex(ValueError, 'hash/size'):
                block_replay.replay_blocks(reader, self.ctx, self.blocks, self.source,
                                          deadline=time.monotonic() + 60, replay_profile='window32/8192')
        self.assertIsNone(reader.summary)

    def test_resource_exceptions_at_io_exact_check_and_physical_replay_propagate(self):
        for error in (MemoryError, TimeoutError):
            for target in ('before', 'exact', 'physical'):
                with self.subTest(error=error.__name__, target=target):
                    if target == 'before':
                        def fail():
                            raise error('resource guard')
                        with self.assertRaises(error):
                            self.replay(before=fail)
                    else:
                        owner = block_replay.BlockCertificates if target == 'exact' else block_replay
                        name = 'check' if target == 'exact' else 'verify_model'
                        with patch.object(owner, name, side_effect=error('resource verification')), \
                             self.assertRaises(error):
                            self.replay()
        @contextmanager
        def late(deadline):
            yield
            raise TimeoutError('late verification exit')
        with patch.object(block_replay, 'verification_deadline', late), self.assertRaises(TimeoutError):
            self.replay()

    def test_archive_reader_caps_are_unchanged(self):
        self.assertEqual(archive_reader.MAX_COMPRESSED_BYTES, 512 * 1024**2)
        self.assertEqual(archive_reader.MAX_RAW_BYTES, 512 * 1024**2)
        self.assertEqual(archive_reader.MAX_ROW_BYTES, 8 * 1024**2)
        with self.assertRaisesRegex(ValueError, 'byte cap'):
            ArchiveReader(self.path, compressed_sha256='a' * 64, compressed_bytes=512 * 1024**2 + 1)


if __name__ == '__main__':
    unittest.main()
