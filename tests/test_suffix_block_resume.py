"""Continuation protocol tests use tiny hand certificates, never native LPs."""
import base64
from contextlib import contextmanager, redirect_stdout
from copy import deepcopy
import gzip
import hashlib
import io
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from experiments.time_cut_v2.recorded_real import block_archive, block_replay, block_resume as resume, domain, plan
from experiments.time_cut_v2.recorded_real.archive_reader import ArchiveReader
from experiments.time_cut_v2.recorded_real.lp_stream_jobs import LPStreamJob
from experiments.time_cut_v2.recorded_real.runtime import BATCH_REPLAY, BoundedEvidenceWriter
from tests.test_suffix_block_archive import FakeResults
from tests.test_suffix_block_replay import archive_rows, population
from validation.suffix5.test_convex_checker import hand_record


class BlockResumeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ctx, first = hand_record('C', 0, True)
        _, second = hand_record('C', 1, True)
        _, excluded = hand_record('C', 2, True)
        self.blocks, self.records = population([(0, 0, [first]), (1352, 346112, [second]),
                                               (2535, 648960, [excluded]), (2687, 687940, [second, excluded])])
        self.pins = {i: plan.digest(self.records[i]['model']) for i in (687940, 687941)}
        for target, key, value in ((resume, 'MODEL_PINS', self.pins), (resume.pilot, 'MAX_MODELS', 5)):
            manager = patch.object(target, key, value)
            manager.start()
            self.addCleanup(manager.stop)
        for name in ('Popen', 'run', 'check_output'):
            manager = patch('subprocess.'+name, side_effect=AssertionError('native process prohibited'))
            manager.start()
            self.addCleanup(manager.stop)
        self.selection = dict(schema='tiny-admitted-selection', blocks=self.blocks,
                              population=dict(block_plan_sha256='b'*64))
        self.index = dict(capture_sha256='c'*64, query_freeze_sha256='d'*64)
        self.args = SimpleNamespace(old_archive=self.root/'old.jsonl.gz', old_summary=self.root/'old-summary.json',
                                    old_selection=self.root/'old-selection.json')
        selection_raw = b''.join(domain.chunks(self.selection))
        self.args.old_selection.write_bytes(selection_raw)
        self.selection_sha = hashlib.sha256(selection_raw).hexdigest()
        old_resources = resume.resource_plan([1, 2, 3, 4, 5], historical=True)
        self.old_context = dict(schema='hiroute-suffix-block-work-context-v1', source_sha256=resume.OLD_SOURCE_SHA,
            source_bundle_sha256=self.ctx.summary['bundle_sha256'], capture_sha256=self.index['capture_sha256'],
            block_plan_sha256=self.selection['population']['block_plan_sha256'], selection_sha256=self.selection_sha,
            original_query_freeze_sha256=self.index['query_freeze_sha256'], resource_plan_sha256=plan.digest(old_resources))
        self.old_rows = archive_rows(self.ctx, self.blocks, self.records, self.old_context, unresolved=tuple(self.pins))
        encoder = block_archive.ArchiveEncoding()
        archive_raw = b''.join(encoder.chunks(self.old_rows))
        self.args.old_archive.write_bytes(archive_raw)
        self.archive_sha = hashlib.sha256(archive_raw).hexdigest()
        self.archive_bytes = len(archive_raw)
        self.old_summary = dict(schema='hiroute-four-block-resource-summary-v1', source_context=self.old_context,
            resource_plan=old_resources, population=self.selection['population'],
            selection=dict(path='pilot-selection.json', sha256=self.selection_sha, size_bytes=len(selection_raw)),
            proof_archive=dict(path='model-proofs.jsonl.gz', sha256=self.archive_sha, size_bytes=len(archive_raw)),
            encoding=encoder.summary(), complete=False, verified_models=3, blocks=self.old_rows[-1]['blocks'],
            transport=self.old_rows[-1]['transport'], numerical_wall_seconds=0., **resume.FALSE_AUTHORITY)
        summary_raw = b''.join(domain.chunks(self.old_summary))
        self.args.old_summary.write_bytes(summary_raw)
        self.summary_sha = hashlib.sha256(summary_raw).hexdigest()
        for key, value in (('OLD_SELECTION_SHA', self.selection_sha), ('OLD_SUMMARY_SHA', self.summary_sha),
                           ('OLD_ARCHIVE_SHA', self.archive_sha), ('OLD_ARCHIVE_BYTES', self.archive_bytes)):
            manager = patch.object(resume, key, value)
            manager.start()
            self.addCleanup(manager.stop)
        self.new_context = dict(schema='hiroute-suffix-block-resume-context-v1', source_sha256='e'*64,
                                previous_source_context=self.old_context, previous_archive=resume.archive_pin())

    def receipt(self):
        reader = ArchiveReader(self.args.old_archive, compressed_sha256=self.archive_sha, compressed_bytes=self.archive_bytes)
        return block_replay.replay_blocks(reader, self.ctx, self.blocks, self.old_context, deadline=time.monotonic()+60)

    def outcomes(self):
        result = []
        for ordinal in self.pins:
            record = self.records[ordinal]
            job = LPStreamJob(self.new_context, 2687, ordinal, plan.digest(record['model']), record['model'])
            generation = 'f'*32
            result.append(dict(job=job.to_dict(), response_identity=job.header(generation), generation=generation,
                               status='complete', reason=None, stages=record['stages'], result=record['result'], metrics={},
                               stdout_base64=base64.b64encode(b'hand proof\n').decode(), stderr_base64=''))
        return result

    def continue_rows(self, *, receipt=None, rows=None, results=None, context=None):
        return list(resume.continued_records(self.ctx, self.blocks, context or self.new_context,
            receipt or self.receipt(), results or FakeResults(self.outcomes() if rows is None else rows),
            deadline=time.monotonic()+60))

    def test_authenticated_failed_history_needs_no_pilot_successful_return(self):
        # A new genuine family object is used even though its immutable identity is unchanged.
        self.ctx, _ = hand_record('C', 0, True)
        receipt = resume.replay_history(self.args, self.ctx, self.selection, self.index, deadline=time.monotonic()+60)
        self.assertEqual(receipt.summary()['checked_models'], 3)
        self.assertFalse(receipt.summary()['historical_attempt_claimed_complete'])
        self.assertFalse(receipt.summary()['historical_runtime_revalidated'])
        self.assertFalse(hasattr(self.args, 'old_return'))
        self.assertEqual(receipt.summary()['coverage'][-1]['unresolved_ordinals'], [687940, 687941])

    def test_consumed_old_archive_selection_and_summary_bytes_are_authenticated(self):
        for name in ('old_archive', 'old_selection', 'old_summary'):
            path = getattr(self.args, name)
            raw = path.read_bytes()
            path.write_bytes(raw+b' ')
            with self.subTest(name=name), self.assertRaises(ValueError):
                resume.replay_history(self.args, self.ctx, self.selection, self.index, deadline=time.monotonic()+60)
            path.write_bytes(raw)

    def test_history_cannot_supply_its_own_population_or_source(self):
        for mode in ('selection', 'bundle', 'capture', 'query', 'source', 'resource', 'success'):
            selection, index, old = deepcopy(self.selection), deepcopy(self.index), deepcopy(self.old_summary)
            if mode == 'selection':
                selection['blocks'][0]['descriptors'][0]['segment_id'] = 98
            elif mode == 'bundle':
                old['source_context']['source_bundle_sha256'] = '0'*64
            elif mode in ('capture', 'query'):
                index['capture_sha256' if mode == 'capture' else 'query_freeze_sha256'] = '0'*64
            elif mode == 'source':
                old['source_context']['source_sha256'] = '0'*64
            elif mode == 'resource':
                old['resource_plan']['maximum_passes_per_model'] = 13
            else:
                old['complete'] = True
            raw = b''.join(domain.chunks(old))
            self.args.old_summary.write_bytes(raw)
            with self.subTest(mode=mode), patch.object(resume, 'OLD_SUMMARY_SHA', hashlib.sha256(raw).hexdigest()), \
                 self.assertRaises(ValueError):
                resume.replay_history(self.args, self.ctx, selection, index, deadline=time.monotonic()+60)

    def test_join_preserves_retained_provenance_and_new_full_proofs(self):
        receipt = self.receipt()
        rows = self.continue_rows(receipt=receipt)
        footer = rows[-1]
        self.assertTrue(footer['complete'])
        self.assertTrue(footer['proof_complete'])
        self.assertEqual((footer['verified_models'], footer['retained_verified_models'], footer['new_verified_models']), (5, 3, 2))
        retained = [r for r in rows if r['kind'] == 'retained_certificate_reference']
        self.assertEqual([r['descriptor']['ordinal'] for r in retained], [0, 346112, 648960])
        for row in retained:
            origin = row['provenance']
            self.assertEqual(origin['archive'], resume.archive_pin())
            self.assertEqual(origin['source_context'], self.old_context)
            self.assertEqual(origin['archive_row_sha256'], hashlib.sha256(
                plan.canonical(self.old_rows[origin['archive_row_index']])+b'\n').hexdigest())
            self.assertNotIn('candidate_identity', row)
        fresh = [r for r in rows if r['kind'] == 'model_certificate']
        self.assertEqual([r['descriptor']['ordinal'] for r in fresh], [687940, 687941])
        for row in fresh:
            ordinal = row['descriptor']['ordinal']
            self.assertEqual(row['record'], self.records[ordinal])
            self.assertEqual(row['candidate_identity']['source_context_sha256'], plan.digest(self.new_context))
        self.assertTrue(all(r['report']['complete'] for r in rows if r['kind'] == 'block_report'))
        winners = [r for r in rows if r['kind'] == 'block_report' and r['winner_witness'] is not None]
        self.assertEqual(len(winners), 3)
        self.assertTrue(all(r['winner_witness']['physical_witness_verified'] for r in winners))
        self.assertEqual(footer['historical_attempt_status'], 'failed')
        self.assertFalse(footer['historical_runtime_revalidated'])
        for key in resume.FALSE_AUTHORITY:
            self.assertIs(footer[key], False)

    def test_model_selection_builds_only_two_original_models_without_native_imports(self):
        from validation.suffix5 import convex_model, independent_convex_model
        with patch.object(convex_model, 'build_model', wraps=convex_model.build_model) as candidate, \
             patch.object(independent_convex_model, 'build_model', wraps=independent_convex_model.build_model) as independent, \
             patch.dict('sys.modules', {'numpy': None, 'scipy': None, 'sympy': None}):
            jobs = list(resume.candidate_jobs(self.ctx, self.selection, self.new_context))
        self.assertEqual([j.model_ordinal for j in jobs], [687940, 687941])
        self.assertEqual(candidate.call_count, 2)
        self.assertEqual(independent.call_count, 2)
        self.assertEqual([j.model_sha256 for j in jobs], list(self.pins.values()))
        self.assertEqual([j.block_id for j in jobs], [2687, 2687])
        self.assertEqual([j.source_context for j in jobs], [self.new_context]*2)

    def test_foreign_model_hash_or_missing_pending_descriptor_rejects_before_jobs(self):
        selection = deepcopy(self.selection)
        selection['blocks'][-1]['descriptors'].pop()
        with self.assertRaisesRegex(ValueError, 'two candidate'):
            list(resume.candidate_jobs(self.ctx, selection, self.new_context))
        with patch.object(resume, 'MODEL_PINS', {i: '0'*64 for i in self.pins}), \
             self.assertRaisesRegex(ValueError, 'model changed'):
            list(resume.candidate_jobs(self.ctx, self.selection, self.new_context))

    def test_retained_gaps_duplicates_wrong_row_reference_and_wrong_source_reject(self):
        receipt = self.receipt()
        for mode in ('gap', 'duplicate', 'reference', 'source'):
            summary, certificates = receipt.summary(), list(receipt.certificates())
            if mode == 'gap':
                certificates.pop()
            elif mode == 'duplicate':
                certificates.append(deepcopy(certificates[0]))
            elif mode == 'reference':
                summary['certificate_refs'][0]['archive_row_sha256'] = '0'*64
            else:
                summary['source_context']['source_sha256'] = '0'*64
            changed = block_replay.ReplayedBlocks(plan.canonical(summary), tuple(map(plan.canonical, certificates)))
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.continue_rows(receipt=changed)

    def test_prior_unsubmitted_or_extra_unresolved_model_is_not_a_two_model_resume(self):
        receipt = self.receipt()
        for mode in ('gap', 'extra', 'relabel'):
            summary = receipt.summary()
            if mode == 'gap':
                summary['coverage'][-1]['unsubmitted_ordinals'] = [687940]
            elif mode == 'extra':
                summary['coverage'][0]['unresolved_ordinals'] = [0]
            else:
                summary['historical_attempt_claimed_complete'] = True
            changed = block_replay.ReplayedBlocks(plan.canonical(summary), receipt._certificates)
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.continue_rows(receipt=changed)

    def test_forged_family_and_relabelled_current_source_are_rejected(self):
        receipt = self.receipt()
        genuine, self.ctx = self.ctx, SimpleNamespace(summary=self.ctx.summary)
        with self.assertRaisesRegex(ValueError, 'genuine checked'):
            self.continue_rows(receipt=receipt)
        self.ctx = genuine
        context = dict(self.new_context, source_sha256=self.old_context['source_sha256'])
        with self.assertRaisesRegex(ValueError, 'new source identity'):
            self.continue_rows(receipt=receipt, context=context)

    def test_new_duplicate_foreign_source_response_and_model_are_rejected(self):
        receipt = self.receipt()
        for mode in ('duplicate', 'foreign', 'source', 'response', 'model'):
            outcomes = self.outcomes()
            if mode == 'duplicate':
                outcomes.append(deepcopy(outcomes[0]))
            elif mode == 'response':
                outcomes[0]['response_identity']['input_sha256'] = '0'*64
            else:
                current = LPStreamJob.from_dict(outcomes[0]['job'])
                ordinal = 0 if mode == 'foreign' else current.model_ordinal
                context = dict(self.new_context, source_sha256='0'*64) if mode == 'source' else self.new_context
                model = self.records[0]['model'] if mode == 'model' else current.model
                job = LPStreamJob(context, current.block_id, ordinal, plan.digest(model), model)
                outcomes[0].update(job=job.to_dict(), response_identity=job.header(outcomes[0]['generation']))
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.continue_rows(receipt=receipt, rows=outcomes)

    def test_failed_candidate_and_bad_exact_certificate_remain_unresolved(self):
        receipt = self.receipt()
        for mode in ('candidate', 'certificate'):
            outcomes = self.outcomes()
            if mode == 'candidate':
                outcomes[0].update(status='unresolved', result=None, reason='model deadline')
            else:
                outcomes[0]['result'] = dict(outcomes[0]['result'], J='999')
            rows = self.continue_rows(receipt=receipt, rows=outcomes)
            self.assertFalse(rows[-1]['proof_complete'])
            self.assertEqual(rows[-1]['verified_models'], 4)
            self.assertEqual(rows[-1]['new_verified_models'], 1)
            report = rows[-1]['blocks'][-1]
            self.assertEqual(report['unresolved_ordinals'], [687940])
            self.assertIsNone(report['aggregate'])
            self.assertEqual([r['descriptor']['ordinal'] for r in rows if r['kind'] == 'unresolved_model'], [687940])

    def test_transport_gap_stays_explicit_and_falsely_complete_gap_rejects(self):
        receipt = self.receipt()
        outcomes = self.outcomes()[:1]
        rows = self.continue_rows(receipt=receipt, rows=outcomes)
        self.assertFalse(rows[-1]['proof_complete'])
        self.assertEqual(rows[-1]['blocks'][-1]['unsubmitted_ordinals'], [687941])
        self.assertEqual([r['descriptor']['ordinal'] for r in rows if r['kind'] == 'unsubmitted_model'], [687941])
        results = FakeResults(outcomes)
        results.summary.update(submitted_count=2, terminal_count=2)
        with self.assertRaisesRegex(ValueError, 'gap'):
            self.continue_rows(receipt=receipt, results=results)

    def test_late_transport_error_or_unreaped_worker_keeps_every_block_incomplete(self):
        receipt = self.receipt()
        for key, value in (('protocol_error_count', 1), ('all_processes_reaped', False), ('collector_error', 'late error')):
            results = FakeResults(self.outcomes())
            results.summary[key] = value
            with patch('validation.suffix5.calibration.verify_model', side_effect=AssertionError('dirty transport witness')):
                rows = self.continue_rows(receipt=receipt, results=results)
            self.assertFalse(rows[-1]['complete'])
            self.assertTrue(all(r['complete_certificates'] for r in rows[-1]['blocks']))
            self.assertTrue(all(not r['complete'] for r in rows[-1]['blocks']))

    def test_late_retained_or_new_exact_check_cannot_publish_stale_receipt(self):
        receipt = self.receipt()
        for failing_call in (1, 4):
            calls, seen = [], []
            @contextmanager
            def late(deadline):
                calls.append(deadline)
                yield
                if len(calls) == failing_call:
                    raise TimeoutError('late continuation exact deadline')
            with self.subTest(failing_call=failing_call), \
                 patch('validation.suffix5.calibration.verification_deadline', late), self.assertRaises(TimeoutError):
                for row in resume.continued_records(self.ctx, self.blocks, self.new_context, receipt,
                                                   FakeResults(self.outcomes()), deadline=time.monotonic()+60):
                    seen.append(row)
            self.assertNotIn('footer', [r['kind'] for r in seen])
            self.assertNotIn('model_certificate', [r['kind'] for r in seen])

    def test_late_physical_exit_has_no_stale_witness_or_completion(self):
        receipt = self.receipt()
        calls = []
        @contextmanager
        def late(deadline):
            calls.append(deadline)
            yield
            if len(calls) == 6:
                raise TimeoutError('late physical continuation deadline')
        with patch('validation.suffix5.calibration.verification_deadline', late):
            rows = self.continue_rows(receipt=receipt)
        block = next(r for r in rows if r['kind'] == 'block_report')
        self.assertIsNone(block['winner_witness'])
        self.assertFalse(block['report']['physical_witness_verified'])
        self.assertFalse(rows[-1]['proof_complete'])

    def test_archive_roundtrip_keeps_all_original_dispositions_and_bounds(self):
        receipt = self.receipt()
        with BoundedEvidenceWriter(self.root/'new-evidence', BATCH_REPLAY.worker_evidence_bytes,
                                   profile_name=BATCH_REPLAY.name) as raw:
            proof = resume.publish_proofs(self.ctx, self.selection, self.new_context, receipt,
                block_archive.QuotaWriter(raw, lambda: None), FakeResults(self.outcomes()), deadline=time.monotonic()+60)
            raw.finalize()
        blob = (self.root/'new-evidence'/'continued-model-proofs.jsonl.gz').read_bytes()
        self.assertEqual(proof['archive']['sha256'], hashlib.sha256(blob).hexdigest())
        decoded = gzip.decompress(blob)
        rows = [json.loads(line) for line in decoded.splitlines()]
        dispositions = [r['descriptor']['ordinal'] for r in rows if 'descriptor' in r]
        self.assertEqual(sorted(dispositions), sorted(self.records))
        self.assertEqual(len(set(dispositions)), len(self.records))
        self.assertEqual(proof['encoding']['uncompressed_sha256'], hashlib.sha256(decoded).hexdigest())
        self.assertTrue(proof['footer']['proof_complete'])


class BlockResumeControllerTests(unittest.TestCase):
    def test_fixed_resource_policy_and_only_two_candidate_pass_budgets(self):
        resources = resume.resource_plan([1, 2, 3, 4, 5])
        self.assertEqual((resources['models'], resources['retained_models'], resources['candidate_models']), (1024, 1022, 2))
        self.assertEqual(resources['candidate_ordinals'], [687940, 687941])
        self.assertEqual(resources['maximum_candidate_passes'], 24)
        self.assertEqual(resources['candidate_as_bytes'], 1024**3)
        self.assertEqual(resources['candidate_peak_rss_bytes'], 768*1024**2)
        self.assertEqual(resources['evidence_charge_bytes'], 512*1024**2)
        self.assertEqual(resources['absolute_seconds'], 900)
        self.assertEqual(BATCH_REPLAY.group_rss_bytes, 20*1024**3)
        self.assertEqual(BATCH_REPLAY.host_reserve_bytes, 16*1024**3)

    def test_controller_preserves_admission_arguments_and_900_second_guard(self):
        argv = ['block_resume']
        for name in ('historical-plan', 'replay-plan', 'replay-attempt', 'replay-return', 'logical-attempt',
                     'logical-return', 'capture', 'old-archive', 'old-summary', 'old-selection'):
            argv += ['--'+name, '/tmp/'+name]
        for name in ('historical-plan-sha', 'replay-plan-sha', 'replay-return-sha', 'replay-manifest-sha',
                     'replay-result-sha', 'replay-decision-sha', 'query-index-sha', 'source-commit', 'source-sha',
                     'logical-return-sha', 'logical-report-sha', 'logical-source-sha'):
            argv += ['--'+name, 'a'*64]
        argv += ['--worker-cpus', '1', '2', '3', '4', '5', '--cpu', '0', '--attempt-dir', '/tmp/fresh-resume']
        with patch.object(resume.sys, 'argv', argv), patch.object(resume.suffix_census, 'check_sources'), \
             patch.object(resume.resource, 'getrlimit', return_value=(1024**3, resume.resource.RLIM_INFINITY)), \
             patch.object(resume.resource, 'setrlimit') as limits, \
             patch.object(resume, 'run_phase', return_value={'status': 'completed'}) as phase, redirect_stdout(io.StringIO()):
            self.assertEqual(resume.main(), 0)
        self.assertEqual(limits.call_args.args[1][0], 512*1024**2)
        args = phase.call_args
        self.assertEqual(args.kwargs['deadline_monotonic']-args.kwargs['entry_monotonic'], 900)
        self.assertIs(args.kwargs['profile'], BATCH_REPLAY)
        self.assertEqual(args.kwargs['worker_cpus'], (1, 2, 3, 4, 5))
        command = args.args[0]
        self.assertEqual(command[command.index('-m')+1], 'experiments.time_cut_v2.recorded_real.block_resume')
        self.assertEqual(command[command.index('--old-archive')+1], '/tmp/old-archive')
        self.assertNotIn('--old-return', command)
        self.assertEqual(command[command.index('--deadline')+1], repr(resume.ENTRY+900))


if __name__ == '__main__':
    unittest.main()
