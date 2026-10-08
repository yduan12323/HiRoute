"""Generic cold recovery uses genuine hand proofs and fake transport only."""
import base64
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zlib

from experiments.time_cut_v2.recorded_real import block_archive, plan
from experiments.time_cut_v2.recorded_real import window_recovery_core as recovery
from experiments.time_cut_v2.recorded_real.archive_reader import ArchiveReader
from experiments.time_cut_v2.recorded_real.lp_stream_jobs import LPStreamJob
from experiments.time_cut_v2.recorded_real.runtime import BATCH_REPLAY, BoundedEvidenceWriter
from tests.test_suffix_block_archive import FakeResults as BaseFakeResults
from tests.test_suffix_block_replay import archive_rows, population
from validation.suffix5 import calibration, convex_model, independent_convex_model
from validation.suffix5.test_convex_checker import hand_record


class FakeResults(BaseFakeResults):
    def __init__(self, rows):
        super().__init__(rows)
        self.summary['input_bytes'] = sum(len(LPStreamJob.from_dict(row['job']).input_bytes) for row in rows)


class WindowRecoveryCoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ctx, first = hand_record('C', 0, True)
        _, second = hand_record('C', 1, True)
        _, excluded = hand_record('C', 2, True)
        self.blocks, self.records = population([(7, 100, [first, second, excluded]),
                                                (9, 900, [second, excluded])])
        self.source = dict(source_sha256='a'*64, source_bundle_sha256=self.ctx.summary['bundle_sha256'])
        self.new_source = dict(self.source, source_sha256='b'*64)
        self.docs = archive_rows(self.ctx, self.blocks, self.records, self.source,
                                 unresolved=(102,), omit=(901,))
        self.inputs = [(self.docs, self.source, False)]
        for name in ('Popen', 'run', 'check_output'):
            manager = patch('subprocess.'+name, side_effect=AssertionError('no process/LP allowed'))
            manager.start()
            self.addCleanup(manager.stop)

    def write_input(self, data, source, incomplete=False, index=0):
        if type(data) is list:
            data = b''.join(block_archive.ArchiveEncoding().chunks(data))
        path = self.root / ('history-'+str(index)+'.gz')
        path.write_bytes(data)
        reader = ArchiveReader(path, compressed_sha256=hashlib.sha256(data).hexdigest(),
                               compressed_bytes=len(data), allow_incomplete=incomplete)
        return recovery.ArchiveInput(reader, source)

    def session(self, inputs=None, *, blocks=None, ctx=None, deadline=None, before=lambda: None):
        histories = self.inputs if inputs is None else inputs
        admitted = [self.write_input(*item, index=i) for i, item in enumerate(histories)]
        return recovery.open_recovery(self.ctx if ctx is None else ctx,
            self.blocks if blocks is None else blocks, admitted,
            deadline=time.monotonic()+60 if deadline is None else deadline, before=before)

    def outcomes(self, ordinals=(102, 901), source=None, *, unresolved=()):
        source = self.new_source if source is None else source
        result = []
        for ordinal in ordinals:
            record = self.records[ordinal]
            number = next(b['range']['block_id'] for b in self.blocks
                          if b['range']['start'] <= ordinal < b['range']['end'])
            job = LPStreamJob(source, number, ordinal, plan.digest(record['model']), record['model'])
            generation = 'd'*32
            result.append(dict(job=job.to_dict(), response_identity=job.header(generation), generation=generation,
                status='unresolved' if ordinal in unresolved else 'complete', reason='timeout' if ordinal in unresolved else None,
                stages=record['stages'], result=None if ordinal in unresolved else record['result'], metrics={},
                stdout_base64=base64.b64encode(b'hand proof\n').decode(), stderr_base64=''))
        return result

    def recovered(self, *, session=None, ordinals=(102, 901), source=None, unresolved=()):
        return list((session or self.session()).records(source or self.new_source,
            FakeResults(self.outcomes(ordinals, source, unresolved=unresolved))))

    @staticmethod
    def prefix(rows, partial=b''):
        encoder = zlib.compressobj(wbits=31)
        raw = b''.join(plan.canonical(row)+b'\n' for row in rows)+partial
        return encoder.compress(raw)+encoder.flush(zlib.Z_SYNC_FLUSH)

    def test_exact_complement_includes_unresolved_and_missing_original_ids(self):
        summary = self.session().summary()
        self.assertEqual(summary['expected_models'], 5)
        self.assertEqual(summary['retained_verified_models'], 3)
        self.assertEqual(summary['candidate_models'], 2)
        self.assertEqual(summary['candidate_ordinals'], [102, 901])
        self.assertEqual(summary['certified_ordinals'], [100, 101, 900])
        self.assertEqual(summary['coverage'][0]['verified_models'], 2)
        for unresolved, omitted in (((100, 900), (101,)), ((), (100, 101, 102, 900, 901)), ((), ())):
            docs = archive_rows(self.ctx, self.blocks, self.records, self.source, unresolved=unresolved, omit=omitted)
            cold = self.session([(docs, self.source, False)]).summary()
            self.assertEqual(cold['candidate_ordinals'], sorted(set(unresolved) | set(omitted)))

    def test_join_retains_original_full_rows_and_reconstructs_physical_witness(self):
        rows = self.recovered()
        footer = rows[-1]
        self.assertTrue(footer['complete'])
        self.assertEqual((footer['verified_models'], footer['retained_verified_models'],
                          footer['new_verified_models'], footer['candidate_models']), (5, 3, 2, 2))
        retained = [row for row in rows if row['kind'] == 'retained_certificate_reference']
        for row in retained:
            provenance = row['provenance']
            original = self.docs[provenance['archive_row_index']]
            self.assertEqual(original['kind'], 'model_certificate')
            self.assertEqual(row['descriptor'], original['descriptor'])
            self.assertEqual(row['verification'], original['verification'])
            self.assertEqual(provenance['source_context'], self.source)
            self.assertEqual(provenance['archive_row_sha256'],
                hashlib.sha256(plan.canonical(original)+b'\n').hexdigest())
        reports = [row for row in rows if row['kind'] == 'block_report']
        self.assertTrue(all(row['winner_witness']['physical_witness_verified'] for row in reports))
        for key in recovery.FALSE_AUTHORITY:
            self.assertIs(footer[key], False)
        self.assertFalse(footer['historical_runtime_revalidated'])

    def test_only_complement_enters_candidate_construction(self):
        session = self.session()
        with patch.object(convex_model, 'build_model', wraps=convex_model.build_model) as candidate, \
             patch.object(independent_convex_model, 'build_model', wraps=independent_convex_model.build_model) as independent, \
             patch.dict('sys.modules', {'numpy': None, 'scipy': None, 'sympy': None}):
            jobs = list(session.candidate_jobs(self.new_source))
        self.assertEqual([job.model_ordinal for job in jobs], [102, 901])
        self.assertEqual((candidate.call_count, independent.call_count), (2, 2))
        self.assertEqual([job.model_sha256 for job in jobs],
                         [plan.digest(self.records[i]['model']) for i in (102, 901)])
        with self.assertRaises(ValueError):
            session.candidate_jobs(self.new_source)

    def test_exact_only_path_does_not_require_or_fabricate_transport(self):
        docs = archive_rows(self.ctx, self.blocks, self.records, self.source)
        session = self.session([(docs, self.source, False)])
        self.assertEqual(list(session.candidate_jobs(self.new_source)), [])
        rows = list(session.records(self.new_source))
        self.assertEqual(rows[0]['recovery_mode'], 'exact-only')
        self.assertIsNone(rows[-1]['transport'])
        self.assertTrue(rows[-1]['proof_complete'])
        self.assertEqual(rows[-1]['new_verified_models'], 0)
        session = self.session([(docs, self.source, False)])
        with self.assertRaisesRegex(ValueError, 'no candidate transport'):
            session.records(self.new_source, FakeResults([]))

    def test_same_source_recovery_and_changed_current_context(self):
        self.assertTrue(self.recovered(source=self.source)[-1]['complete'])
        session = self.session()
        list(session.candidate_jobs(self.new_source))
        with self.assertRaisesRegex(ValueError, 'source context changed'):
            session.records(self.source, FakeResults(self.outcomes(source=self.source)))

    def test_invalid_full_certificate_fails_closed_unresolved_stays_retryable(self):
        outcomes = self.outcomes()
        outcomes[0]['result'] = dict(outcomes[0]['result'], J='999')
        seen = []
        with self.assertRaises(ValueError):
            for row in self.session().records(self.new_source, FakeResults(outcomes)):
                seen.append(row)
        self.assertNotIn('footer', [row['kind'] for row in seen])
        self.assertNotIn('unresolved_model', [row['kind'] for row in seen])
        rows = self.recovered(unresolved=(102,))
        self.assertFalse(rows[-1]['complete'])
        self.assertEqual(rows[-1]['verified_models'], 4)
        follow = self.session(self.inputs+[(rows, self.new_source, False)]).summary()
        self.assertEqual(follow['candidate_ordinals'], [102])

    def test_invalid_old_certificate_never_becomes_retry(self):
        docs = deepcopy(self.docs)
        full = next(row for row in docs if row['kind'] == 'model_certificate')
        full['record']['result']['J'] = '999'
        with self.assertRaises(ValueError):
            self.session([(docs, self.source, False)])

    def test_missing_new_disposition_is_explicit_and_false_complete_rejects(self):
        rows = self.recovered(ordinals=(102,))
        self.assertFalse(rows[-1]['complete'])
        self.assertEqual([r['descriptor']['ordinal'] for r in rows if r['kind'] == 'unsubmitted_model'], [901])
        self.assertEqual(self.session(self.inputs+[(rows, self.new_source, False)]).summary()['candidate_ordinals'], [901])
        transport = FakeResults(self.outcomes((102,)))
        transport.summary.update(submitted_count=2, terminal_count=2)
        with self.assertRaisesRegex(ValueError, 'gap'):
            list(self.session().records(self.new_source, transport))

    def test_repeated_recovery_flattens_every_leaf_and_keeps_all_ancestors(self):
        first = self.recovered(unresolved=(901,))
        history = self.inputs+[(first, self.new_source, False)]
        session = self.session(history)
        self.assertEqual(session.summary()['candidate_ordinals'], [901])
        second = self.recovered(session=session, ordinals=(901,))
        inherited = {r['descriptor']['ordinal']: r for r in second if r['kind'] == 'retained_certificate_reference'}
        for ordinal, row in inherited.items():
            original = self.docs if ordinal != 102 else first
            leaf = original[row['provenance']['archive_row_index']]
            self.assertEqual(leaf['kind'], 'model_certificate')
            self.assertEqual(leaf['descriptor']['ordinal'], ordinal)
        final_session = self.session(history+[(second, self.new_source, False)])
        self.assertEqual(final_session.summary()['candidate_models'], 0)
        final = list(final_session.records(self.new_source))
        self.assertEqual(len(final[0]['history']), 3)
        self.assertEqual(final[0]['previous_archive'], final[0]['history'][-1]['archive'])
        self.assertTrue(final[-1]['complete'])
        self.assertIsNone(final[-1]['transport'])

    def test_leaf_hash_source_descriptor_result_and_ancestry_tampering_rejects(self):
        rows = self.recovered()
        for mode in ('hash', 'source', 'index', 'archive', 'descriptor', 'result', 'duplicate', 'history', 'cycle'):
            altered = deepcopy(rows)
            ref = next(row for row in altered if row['kind'] == 'retained_certificate_reference')
            if mode == 'hash':
                ref['provenance']['archive_row_sha256'] = '0'*64
            elif mode == 'source':
                ref['provenance']['source_context'] = self.new_source
            elif mode == 'index':
                ref['provenance']['archive_row_index'] += 1
            elif mode == 'archive':
                ref['provenance']['archive']['sha256'] = '0'*64
            elif mode == 'descriptor':
                ref['descriptor']['segment_id'] += 1
            elif mode == 'result':
                ref['verification']['result']['J'] = '999'
            elif mode == 'duplicate':
                altered.insert(2, deepcopy(ref))
            elif mode == 'history':
                altered[0]['history'].clear()
            else:
                altered[0]['history'].append(deepcopy(altered[0]['history'][0]))
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.session(self.inputs+[(altered, self.new_source, False)])
        with self.assertRaises(ValueError):
            self.session(self.inputs+[(rows, self.source, False)])

    def test_bound_original_declarations_and_genuine_checked_family_required(self):
        with self.assertRaisesRegex(ValueError, 'genuine checked'):
            self.session(ctx=SimpleNamespace(summary=self.ctx.summary))
        altered = deepcopy(self.blocks)
        altered[0]['descriptors'][0]['segment_id'] += 1
        with self.assertRaises(ValueError):
            self.session(blocks=altered)
        with self.assertRaises(ValueError):
            recovery.RecoverySession()
        forged = object.__new__(recovery.RecoverySession)
        with self.assertRaisesRegex(ValueError, 'live cold'):
            forged.summary()

    def test_interrupted_root_and_recovery_prefix_use_only_complete_rows(self):
        prefix = self.prefix(self.docs[:2], b'{"kind":"model_cert')
        session = self.session([(prefix, self.source, True)])
        self.assertEqual(session.summary()['certified_ordinals'], [100])
        self.assertFalse(session.summary()['history'][0]['gzip_eof'])
        with self.assertRaises(ValueError):
            self.session([(prefix, self.source, False)])
        first = self.recovered()
        end = next(i for i, row in enumerate(first) if row['kind'] == 'model_certificate')+1
        prefix = self.prefix(first[:end], b'{"kind":"block_cert')
        continued = self.session(self.inputs+[(prefix, self.new_source, True)])
        self.assertEqual(continued.summary()['candidate_ordinals'], [901])
        self.assertEqual(continued.summary()['retained_verified_models'], 4)
        self.assertGreater(continued.summary()['history'][-1]['trailing_partial_row_bytes'], 0)
        # Even a prefix interrupted before writing all retained references keeps
        # independently checked ancestral certificates, but claims no new proof.
        earlier = self.prefix(first[:2])
        self.assertEqual(self.session(self.inputs+[(earlier, self.new_source, True)]).summary()['candidate_ordinals'], [102, 901])

    def test_complete_gzip_without_footer_and_fake_footer_after_partial_reject(self):
        rows = self.recovered()
        with self.assertRaises(ValueError):
            self.session(self.inputs+[(rows[:-1], self.new_source, False)])
        partial = self.prefix(rows, b'{')
        with self.assertRaisesRegex(ValueError, 'partial record after'):
            self.session(self.inputs+[(partial, self.new_source, True)])

    def test_changed_new_model_or_source_and_duplicate_candidate_reject(self):
        for mode in ('model', 'source', 'duplicate', 'response', 'unresolved-model'):
            outcomes = self.outcomes()
            if mode == 'duplicate':
                outcomes.append(deepcopy(outcomes[0]))
            elif mode == 'response':
                outcomes[0]['response_identity']['input_sha256'] = '0'*64
            else:
                old = LPStreamJob.from_dict(outcomes[0]['job'])
                source = self.source if mode == 'source' else self.new_source
                model = self.records[100]['model'] if mode in ('model', 'unresolved-model') else old.model
                job = LPStreamJob(source, old.block_id, old.model_ordinal, plan.digest(model), model)
                outcomes[0].update(job=job.to_dict(), response_identity=job.header(outcomes[0]['generation']))
                if mode == 'unresolved-model':
                    outcomes[0].update(status='unresolved', result=None)
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                list(self.session().records(self.new_source, FakeResults(outcomes)))

    def test_deadline_and_late_checker_exit_never_publish_stale_certificate(self):
        with self.assertRaises(ValueError):
            self.session(deadline=time.monotonic()-1)
        with self.assertRaises(ValueError):
            self.session(deadline=time.monotonic()+901)
        session = self.session()
        calls, seen = [], []
        @contextmanager
        def late(deadline):
            calls.append(deadline)
            yield
            if len(calls) == 1:
                raise TimeoutError('late checker exit')
        with patch.object(calibration, 'verification_deadline', late), self.assertRaises(TimeoutError):
            for row in session.records(self.new_source, FakeResults(self.outcomes())):
                seen.append(row)
        self.assertEqual([r['kind'] for r in seen], ['header'])
        session = self.session()
        with patch.object(recovery.time, 'monotonic', return_value=time.monotonic()+100), self.assertRaises(ValueError):
            session.records(self.new_source, FakeResults(self.outcomes()))

    def test_live_join_defensively_checks_retained_rows_again(self):
        session = self.session()
        with patch.object(recovery.BlockCertificates, 'check', side_effect=ValueError('fresh retained check')):
            with self.assertRaisesRegex(ValueError, 'fresh retained'):
                list(session.records(self.new_source, FakeResults(self.outcomes())))

    def test_failed_transport_never_grants_physical_or_block_completion(self):
        outcomes = FakeResults(self.outcomes())
        outcomes.summary['all_processes_reaped'] = False
        with patch.object(calibration, 'verify_model', side_effect=AssertionError('dirty transport witness')):
            # Cold opening itself can reconstruct any complete ancestor blocks;
            # this fixture deliberately has no complete ancestor blocks.
            rows = list(self.session().records(self.new_source, outcomes))
        self.assertFalse(rows[-1]['complete'])
        self.assertTrue(all(row['complete_certificates'] for row in rows[-1]['blocks']))
        self.assertTrue(all(not row['complete'] for row in rows[-1]['blocks']))

    def test_writer_roundtrip_and_cumulative_resource_limits(self):
        with BoundedEvidenceWriter(self.root/'evidence', BATCH_REPLAY.worker_evidence_bytes,
                                   profile_name=BATCH_REPLAY.name) as writer:
            proof = recovery.publish_proofs(self.session(), self.new_source,
                block_archive.QuotaWriter(writer, lambda: None), FakeResults(self.outcomes()))
            writer.finalize()
        blob = (self.root/'evidence'/'recovery-model-proofs.jsonl.gz').read_bytes()
        self.assertEqual(hashlib.sha256(blob).hexdigest(), proof['archive']['sha256'])
        self.assertTrue(proof['footer']['complete'])
        self.assertEqual(self.session(self.inputs+[(blob, self.new_source, False)]).summary()['candidate_models'], 0)
        with patch.object(recovery, 'MAX_HISTORY_BYTES', 10), self.assertRaisesRegex(ValueError, 'compressed'):
            self.session()
        session = self.session()
        with patch.object(recovery, 'MAX_INPUT_BYTES', 10), self.assertRaisesRegex(ValueError, 'input cap'):
            list(session.candidate_jobs(self.new_source))

    def test_transport_input_bytes_are_actual_and_failed_unaccounted_work_is_preserved(self):
        for change in (-1, 1, True):
            outcomes = FakeResults(self.outcomes())
            outcomes.summary['input_bytes'] = (True if change is True else outcomes.summary['input_bytes']+change)
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'input byte'):
                list(self.session().records(self.new_source, outcomes))
        outcomes = FakeResults(self.outcomes((102,)))
        outcomes.summary.update(status='unresolved', all_submitted_accounted=False,
            input_exhausted=False, submitted_count=2, input_bytes=outcomes.summary['input_bytes']+100)
        rows = list(self.session().records(self.new_source, outcomes))
        self.assertFalse(rows[-1]['complete'])
        self.assertEqual(self.session(self.inputs+[(rows, self.new_source, False)]).summary()['candidate_ordinals'], [901])

    def test_mutating_a_detached_summary_cannot_change_live_complement_or_sources(self):
        session = self.session()
        summary = session.summary()
        summary['candidate_ordinals'].clear()
        summary['certified_ordinals'].append(901)
        summary['certificate_refs'][0]['source_context']['source_sha256'] = '0'*64
        summary['history'].clear()
        self.assertEqual(session.summary()['candidate_ordinals'], [102, 901])
        self.assertTrue(self.recovered(session=session)[-1]['complete'])

    def test_late_new_or_physical_check_aborts_without_successful_footer(self):
        for failing_call in (4, 6):
            session = self.session()
            calls, seen = [], []
            @contextmanager
            def late(deadline):
                calls.append(deadline)
                yield
                if len(calls) == failing_call:
                    raise TimeoutError('late fresh or witness exit')
            with self.subTest(failing_call=failing_call), \
                 patch.object(calibration, 'verification_deadline', late), self.assertRaises(TimeoutError):
                for row in session.records(self.new_source, FakeResults(self.outcomes())):
                    seen.append(row)
            self.assertNotIn('footer', [row['kind'] for row in seen])
            if failing_call == 4:
                self.assertNotIn('model_certificate', [row['kind'] for row in seen])

    def test_changed_physical_witness_or_report_cannot_be_reused(self):
        rows = self.recovered()
        for mode in ('witness', 'complete', 'exemption', 'authority'):
            altered = deepcopy(rows)
            report = next(row for row in altered if row['kind'] == 'block_report')
            if mode == 'witness':
                report['winner_witness']['physical_witness_verified'] = False
            elif mode == 'complete':
                report['report']['complete'] = False
                altered[-1]['blocks'][0]['complete'] = False
            elif mode == 'exemption':
                report['report']['physical_witness_not_required'] = True
            else:
                altered[-1]['literal_G8_closed'] = True
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.session(self.inputs+[(altered, self.new_source, False)])

    def test_shared_raw_history_budget_is_applied_before_next_archive_decodes(self):
        rows = self.recovered()
        root_raw = sum(len(plan.canonical(row))+1 for row in self.docs)
        next_raw = sum(len(plan.canonical(row))+1 for row in rows)
        original = ArchiveReader.limit_raw_bytes
        limits = []
        def record_limit(reader, limit):
            limits.append(limit)
            return original(reader, limit)
        with patch.object(recovery, 'MAX_HISTORY_BYTES', root_raw+next_raw), \
             patch.object(ArchiveReader, 'limit_raw_bytes', record_limit):
            session = self.session(self.inputs+[(rows, self.new_source, False)])
        self.assertEqual(session.summary()['candidate_models'], 0)
        self.assertEqual(limits, [root_raw+next_raw, next_raw])
        for remaining in (0, 17, next_raw-1):
            with self.subTest(remaining=remaining), \
                 patch.object(recovery, 'MAX_HISTORY_BYTES', root_raw+remaining), \
                 self.assertRaisesRegex(ValueError, 'uncompressed archive byte cap'):
                self.session(self.inputs+[(rows, self.new_source, False)])


if __name__ == '__main__':
    unittest.main()
