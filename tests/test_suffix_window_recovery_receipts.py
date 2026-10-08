"""Tiny hand/protocol receipts only: no optimizer, real archive or remote run."""
from copy import deepcopy
from dataclasses import asdict
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from experiments.time_cut_v2.recorded_real import block_archive, domain, plan, runtime
from experiments.time_cut_v2.recorded_real import window_receipts as wr
from experiments.time_cut_v2.recorded_real import window_recovery_receipts as rr
from experiments.time_cut_v2.recorded_real.lp_stream_jobs import LPStreamJob
from tests import test_suffix_window_recovery_core as core_fixtures
from tests import test_suffix_window_receipts as receipt_fixtures

FakeResults = core_fixtures.FakeResults


def raw(value):
    return plan.canonical(value)+b'\n'


class RecoveryProofClosureTests(unittest.TestCase):
    def setUp(self):
        self.fx = core_fixtures.WindowRecoveryCoreTests(); self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.root = self.fx.root
        # The old hand fixture predates transport-byte accounting. Preserve its
        # actual jobs when adding the field required by the new receipt reader.
        self.fx.docs[-1]['transport']['input_bytes'] = sum(len(LPStreamJob(
            self.fx.source, block['range']['block_id'], descriptor['ordinal'],
            plan.digest(self.fx.records[descriptor['ordinal']]['model']),
            self.fx.records[descriptor['ordinal']]['model']).input_bytes)
            for block in self.fx.blocks for descriptor in block['descriptors'] if descriptor['ordinal'] != 901)

    def consume(self, docs, source, history, leaves, *, root=False, name='proof'):
        path = self.root/(name+'.gz')
        path.write_bytes(b''.join(block_archive.ArchiveEncoding().chunks(docs)))
        return rr._consume(path, plan.pin(path), self.fx.blocks, source, history, leaves, lambda: None, root=root)

    def history(self):
        leaves, encoding, _, _ = self.consume(self.fx.docs, self.fx.source, [], {}, root=True, name='root')
        return [dict(archive=dict(sha256=encoding['compressed_sha256'], size_bytes=encoding['compressed_bytes']),
            source_context=self.fx.source, gzip_eof=True, trailing_partial_row_bytes=0)], leaves

    def test_flat_leaf_closure_and_physical_winner_bytes(self):
        history, leaves = self.history()
        rows = self.fx.recovered()
        with patch('validation.suffix5.convex_checker.check_regime', side_effect=AssertionError('cold receipt is not replay')):
            added, _, footer, reports = self.consume(rows, self.fx.new_source, history, leaves)
        self.assertEqual(sorted(added), [102, 901]); self.assertTrue(footer['complete'])
        self.assertEqual(len(reports), 2)
        self.assertEqual(rr._cold_summary(self.fx.blocks, history, leaves), self.fx.session().summary())

    def test_foreign_duplicate_missing_leaf_and_physical_winner_reject(self):
        history, leaves = self.history(); source = self.fx.new_source
        original = self.fx.recovered()
        def foreign(rows): rows[1]['provenance']['archive']['sha256'] = '0'*64
        def rowhash(rows): rows[1]['provenance']['archive_row_sha256'] = '0'*64
        def rowindex(rows): rows[1]['provenance']['archive_row_index'] += 1
        def context(rows): rows[1]['provenance']['source_context']['source_sha256'] = '0'*64
        def duplicate(rows): rows.insert(2, deepcopy(rows[1]))
        def missing(rows): rows.pop(1)
        def winner(rows): next(row for row in rows if row['kind'] == 'block_report')['winner_witness']['binding']['model_ordinal'] = 901
        def bytes_drift(rows): rows[-1]['transport']['input_bytes'] += 1
        for mutation in (foreign, rowhash, rowindex, context, duplicate, missing, winner, bytes_drift):
            rows = deepcopy(original); mutation(rows)
            with self.subTest(mutation=mutation.__name__), self.assertRaises(ValueError):
                self.consume(rows, source, history, leaves)

    def test_same_source_second_failure_and_transitive_leaves(self):
        history, leaves = self.history()
        rows = self.fx.recovered(source=self.fx.source, unresolved=(901,))
        added, encoding, footer, _ = self.consume(rows, self.fx.source, history, leaves)
        self.assertFalse(footer['complete']); self.assertEqual(sorted(added), [102])
        history.append(dict(archive=dict(sha256=encoding['compressed_sha256'], size_bytes=encoding['compressed_bytes']),
            source_context=self.fx.source, gzip_eof=True, trailing_partial_row_bytes=0))
        leaves.update(added)
        session = self.fx.session(self.fx.inputs+[(rows, self.fx.source, False)])
        last = list(session.records(self.fx.source, FakeResults(self.fx.outcomes((901,), self.fx.source))))
        fresh, _, footer, _ = self.consume(last, self.fx.source, history, leaves)
        self.assertTrue(footer['complete']); self.assertEqual(sorted(fresh), [901])
        broken = deepcopy(leaves); broken[102]['provenance']['archive_row_sha256'] = '0'*64
        with self.assertRaises(ValueError): self.consume(last, self.fx.source, history, broken)

    def test_exact_only_truthfulness_and_late_callback_failure(self):
        history, leaves = self.history()
        recovered = self.fx.recovered()
        added, encoding, _, _ = self.consume(recovered, self.fx.new_source, history, leaves)
        leaves.update(added)
        history.append(dict(archive=dict(sha256=encoding['compressed_sha256'], size_bytes=encoding['compressed_bytes']),
            source_context=self.fx.new_source, gzip_eof=True, trailing_partial_row_bytes=0))
        session = self.fx.session(self.fx.inputs+[(recovered, self.fx.new_source, False)])
        rows = list(session.records(self.fx.new_source))
        fresh, _, footer, _ = self.consume(rows, self.fx.new_source, history, leaves)
        self.assertEqual(fresh, {}); self.assertIsNone(footer['transport'])
        rows[-1]['transport'] = dict(status='complete', input_bytes=0)
        with self.assertRaisesRegex(ValueError, 'fabricate'): self.consume(rows, self.fx.new_source, history, leaves)
        path = self.root/'proof.gz'; pin = plan.pin(path)
        def late(): raise TimeoutError('late publication failure')
        with self.assertRaises(TimeoutError):
            rr._consume(path, pin, self.fx.blocks, self.fx.new_source, history, leaves, late)


class RecoveryRuntimeReceiptTests(unittest.TestCase):
    """Synthetic source execution tests isolate the provenance trust boundary.

    The tiny original family/population is genuine. Synthetic model outcomes do
    not assert numerical truth; the separate core fixtures check actual proofs.
    """
    def setUp(self):
        from tests import test_suffix_recovery_plan as plan_fixtures
        self.planfx = plan_fixtures.RecoveryPlanTests(); self.planfx.setUp()
        self.addCleanup(self.planfx.doCleanups)
        self.fx, self.root, self.number = self.planfx.fx, self.planfx.root, 0

    def original(self, *, exact_only=False):
        from experiments.time_cut_v2.recorded_real import recovery_plan
        self.full = {}; failed = set()
        if not exact_only:
            failed.add(self.fx.selection['blocks'][-1]['descriptors'][-1]['ordinal'])
        def rows(items):
            context = items[0]['source_context']; result = [items[0]]
            checked = {}
            for row in items:
                if row['kind'] != 'model_certificate': continue
                row.update(candidate_metrics={}, timings={}, stdout_sha256=hashlib.sha256(b'').hexdigest(), stderr_base64='')
                ordinal = row['descriptor']['ordinal']; self.full[ordinal] = deepcopy(row)
                if ordinal in failed:
                    job = LPStreamJob(context, row['verification']['block_id'], ordinal,
                                      row['verification']['model_sha256'], row['record']['model'])
                    result.append(dict(kind='unresolved_model', descriptor=row['descriptor'], timings={},
                        candidate=dict(job=job.to_dict(), generation='a'*32, response_identity=job.header('a'*32),
                            status='unresolved', reason='tiny protocol failure', stages=[], result=None,
                            metrics={}, stdout_base64='', stderr_base64='')))
                else:
                    checked[ordinal] = row; result.append(row)
                    block = next(b for b in self.fx.selection['blocks'] if b['range']['block_id'] == row['verification']['block_id'])
                    core = rr._core_report(block, checked, failed)
                    if core['complete_certificates']:
                        result.append(dict(kind='block_certificate_checkpoint', report=core,
                            transport_finalized=False, acceptance=False, cold_certificate_replay_required=True))
            reports = []
            for block in self.fx.selection['blocks']:
                core = rr._core_report(block, checked, failed)
                report = dict(core, complete=core['complete_certificates'])
                if report['complete']: report['physical_witness_not_required'] = True
                reports.append(report); result.append(dict(kind='block_report', report=report, winner_witness=None))
            self.original_footer = dict(items[-1], complete=not failed, verified_models=len(checked), blocks=reports)
            result.append(self.original_footer); items[:] = result
        def summary(value):
            value.update({key: self.original_footer[key] for key in ('complete', 'verified_models', 'blocks', 'transport')})
        document = self.planfx.document(mutate_rows=rows, mutate_summary=summary)
        self.plan_path = self.root/'recovery-plan.json'; self.plan_path.write_bytes(raw(document))
        admitted_plan = recovery_plan.admit(recovery_plan.load(self.plan_path, plan.pin(self.plan_path)['sha256'],
            deadline=time.monotonic()+30), self.fx.admitted, self.fx.base, reviewed_sources=self.fx.source,
            deadline=time.monotonic()+30)
        ancestor = document['predecessors'][0]; pin = ancestor['artifacts']['archive']
        leaves, encoding, _, _ = rr._consume(pin['path'], pin, self.fx.selection['blocks'],
            ancestor['source_context'], [], {}, lambda: None, root=True)
        history = [dict(archive={key: pin[key] for key in ('sha256', 'size_bytes')},
            source_context=ancestor['source_context'], gzip_eof=True, trailing_partial_row_bytes=0)]
        cold = rr._cold_summary(self.fx.selection['blocks'], history, leaves)
        admitted_plan.validate_cold_history(cold)
        return document, history, leaves, cold

    def fixture(self, *, exact_only=False, mutate_rows=lambda value: None,
                mutate_request=lambda value: None, mutate_summary=lambda value: None,
                mutate_run=lambda value: None, extra_evidence=False):
        from experiments.time_cut_v2.recorded_real import suffix_window_recovery as runner
        document, history, leaves, cold = self.original(exact_only=exact_only)
        self.number += 1
        attempt = self.root/('recovery'+str(self.number)); attempt.mkdir(); evidence = attempt/'evidence'
        count = self.fx.selection['window_plan']['expected_model_count']
        resources = runner.resource_plan(self.fx.values['worker_cpus'], count, cold['candidate_models'])
        values = dict(self.fx.values, recovery_plan=str(self.plan_path), recovery_plan_sha=plan.pin(self.plan_path)['sha256'])
        self.values = values
        commitment = self.fx.admitted.commitment()
        origin = dict(schema='hiroute-reviewed-controller-origin-v1', checkout_root=str(self.root.resolve()),
            controller_module=runner.MODULE,
            controller_path=str(self.root/'experiments/time_cut_v2/recorded_real/suffix_window_recovery.py'),
            python_executable=sys.executable, executable_realpath=str(Path(sys.executable).resolve()), cwd=str(self.root.resolve()))
        with runtime.BoundedEvidenceWriter(evidence, runtime.BATCH_REPLAY.worker_evidence_bytes,
                                           profile_name=runtime.BATCH_REPLAY.name) as writer:
            writer.write('block-plan.json', domain.chunks(self.fx.population))
            selection_pin = writer.write('window-selection.json', domain.chunks(self.fx.selection))
            base_pin = writer.write('base-registry.json', [self.fx.base_path.read_bytes()])
            plan_pin = writer.write('recovery-plan.json', domain.chunks(document))
            cold_pin = writer.write('cold-replay.json', domain.chunks(cold))
            context = dict(schema=rr.PREFIX+'-context-v1', source_sha256='e'*64,
                source_bundle_sha256=commitment['source_bundle_sha256'], capture_sha256=commitment['completed_replay']['capture_sha256'],
                block_plan_sha256=commitment['block_plan_sha256'], selection_sha256=selection_pin['sha256'],
                original_query_freeze_sha256=commitment['query_freeze_sha256'], resource_plan_sha256=plan.digest(resources),
                window_id=self.fx.selection['window_plan']['window_id'], base_registry_sha256=base_pin['sha256'],
                source_policy_sha256=values['source_policy_sha'], recovery_plan_sha256=plan_pin['sha256'],
                cold_replay_sha256=cold_pin['sha256'], history_sha256=plan.digest(history),
                previous_archive=history[-1]['archive'], previous_source_context_sha256=plan.digest(history[-1]['source_context']))
            run = dict(schema=rr.PREFIX+'-binding-v1', source_commit='f'*40, source_sha256='e'*64,
                invocation_origin=origin, completed_replay=commitment['completed_replay'], logical_report_sha256='5'*64,
                resource_plan=resources, base_registry=base_pin, selection=selection_pin, window_id=context['window_id'],
                source_context=context, recovery_plan=plan_pin, cold_replay=cold_pin,
                registry_admission=dict(kind='registered-window-ledger-v1', registry_sha256=values['registry_sha'],
                    registration_return_sha256=values['registry_return_sha'], source_policy_sha256=values['source_policy_sha']))
            mutate_run(run); writer.write('run-binding.json', domain.chunks(run))
            writer.write('family-summary.json', domain.chunks(dict(checked=dict(
                case_sha256=commitment['case_sha256'], bundle_sha256=commitment['source_bundle_sha256']))))
            writer.write('batch-ledger.json', domain.chunks(dict(tiny_fixture=True)))
            blocks = self.fx.selection['blocks']; rows = [rr._header(blocks, context, history, leaves)]
            checked, input_bytes = {}, 0
            for ordinal in sorted(self.full):
                if ordinal in leaves:
                    row = rr._reference(leaves[ordinal]); checked[ordinal] = leaves[ordinal]['row']
                else:
                    row = deepcopy(self.full[ordinal]); job = LPStreamJob(context, row['verification']['block_id'],
                        ordinal, row['verification']['model_sha256'], row['record']['model'])
                    row['candidate_identity'] = job.header('b'*32); input_bytes += len(job.input_bytes)
                    checked[ordinal] = row
                rows.append(row)
                block = next(b for b in blocks if b['range']['start'] <= ordinal < b['range']['end'])
                core = rr._core_report(block, checked, set())
                if core['complete_certificates']:
                    rows.append(dict(kind='block_certificate_checkpoint', report=core,
                        transport_finalized=False, acceptance=False, cold_certificate_replay_required=True))
            reports = []
            for block in blocks:
                report = dict(rr._core_report(block, checked, set()), complete=True, physical_witness_not_required=True)
                reports.append(report); rows.append(dict(kind='block_report', report=report, winner_witness=None))
            pool = None if exact_only else dict(status='complete', input_exhausted=True, all_submitted_accounted=True,
                all_processes_reaped=True, submitted_count=cold['candidate_models'], terminal_count=cold['candidate_models'],
                protocol_error_count=0, collector_error=None, input_bytes=input_bytes)
            footer = dict(kind='footer', schema=rr.FOOTER_SCHEMA, complete=True, proof_complete=True,
                verified_models=count, expected_models=count, retained_verified_models=len(leaves),
                new_verified_models=cold['candidate_models'], candidate_models=cold['candidate_models'],
                transport=pool, blocks=reports, recovery_mode='exact-only' if exact_only else 'candidates',
                historical_runtime_revalidated=False, **wr.FALSE_AUTHORITY)
            rows.append(footer); mutate_rows(rows)
            encoder = block_archive.ArchiveEncoding()
            proof = writer.write('recovery-model-proofs.jsonl.gz', encoder.chunks(rows))
            summary = dict(schema=rr.PREFIX+'-summary-v1', source_context=context, resource_plan=resources,
                invocation_origin=origin, population=commitment, selection=selection_pin, base_registry=base_pin,
                window_id=context['window_id'], recovery_plan=plan_pin, cold_replay=cold_pin,
                registry_admission=run['registry_admission'], proof_archive=proof, encoding=encoder.summary(),
                numerical_wall_seconds=0., **{key: value for key, value in footer.items() if key not in ('kind', 'schema')})
            mutate_summary(summary); writer.write('recovery-summary.json', domain.chunks(summary))
            if extra_evidence: writer.write('unexpected.json', domain.chunks({}))
            manifest = writer.finalize()
        manifest_raw = (evidence/'__manifest.json').read_bytes(); manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
        command = [sys.executable, '-B', '-m', runner.MODULE, '--worker', '--deadline', '110.0']
        for key, value in values.items():
            if value is not None:
                command.extend(['--'+key.replace('_', '-'), *([str(item) for item in value] if type(value) is list else [str(value)])])
        request = dict(profile=asdict(runtime.BATCH_REPLAY), context=dict(plan_sha256=values['replay_plan_sha'],
            source_sha256='e'*64, input_sha256=plan.digest(values), profile_name=runtime.BATCH_REPLAY.name),
            entry_monotonic=100., deadline_monotonic=110., launcher_rss_bytes_at_entry=1, command=command,
            cpu=self.fx.cpu, worker_cpus=values['worker_cpus'])
        mutate_request(request)
        report = {key: value for key, value in request.items() if key != 'command'}
        report.update(schema='hiroute-phase-v1', status='provisional', reason='tiny synthetic reviewed recovery execution',
            worker_exit_code=0, descendants_reaped=True, sampled_group_rss_peak_bytes=0, kernel_max_reaped_ru_maxrss_bytes=0,
            supervisor_kernel_peak_rss_bytes=0, supervisor_metadata_charge_bytes_before_report=0,
            worker_charged_bytes=manifest['charged_bytes'], largest_sample_gap_seconds=0., phase_wall_seconds=.1,
            reaped_cpu_seconds=0., supervisor_cpu_seconds=0., verified_manifest_sha256=manifest_sha,
            verified_manifest_size_bytes=len(manifest_raw), request_sha256=hashlib.sha256(runtime._json(request)).hexdigest())
        ready = dict(schema='hiroute-supervisor-decision-v1', status='ready',
            report_sha256=hashlib.sha256(runtime._json(report)).hexdigest(), report_size_bytes=len(runtime._json(report)),
            manifest_sha256=manifest_sha, manifest_size_bytes=len(manifest_raw))
        decision = dict(schema='hiroute-phase-decision-v1', status='completed', supervisor_exit_code=0,
            accepted_monotonic=100.2, supervisor_decision_sha256=hashlib.sha256(runtime._json(ready)).hexdigest())
        for name, value in (('request.json', request), ('result.json', report), ('supervisor-decision.json', ready), ('decision.json', decision)):
            (attempt/name).write_bytes(runtime._json(value))
        returned = dict(report, status='completed', phase_wall_seconds=.5, acceptance_receipt=dict(
            schema='hiroute-caller-return-v1', returned_monotonic=100.5,
            result_sha256=plan.pin(attempt/'result.json')['sha256'], decision_sha256=plan.pin(attempt/'decision.json')['sha256'],
            manifest_sha256=manifest_sha, manifest_size_bytes=len(manifest_raw)))
        path = self.root/('recovery-return'+str(self.number)+'.json'); path.write_bytes(raw(returned))
        self.document = document
        return SimpleNamespace(recovery_attempt=attempt, recovery_return=path, recovery_return_sha=plan.pin(path)['sha256'],
            recovery_result_sha=plan.pin(attempt/'result.json')['sha256'], recovery_decision_sha=plan.pin(attempt/'decision.json')['sha256'],
            recovery_manifest_sha=manifest_sha)

    def admit(self, args, **kwargs):
        return rr.admit_completed_recovery(args, self.fx.admitted, reviewed_sources=self.fx.source,
                                          deadline=time.monotonic()+30, **kwargs)

    def test_completed_runtime_registry_scheduling_and_cold_reconciliation(self):
        from validation.capture5.containers import detach_json
        from validation.suffix5.window_plan import next_window
        args = self.fixture(); receipt = self.admit(args)
        self.assertIs(type(receipt), wr.CheckedWindowReceipt)
        self.assertEqual(receipt.metadata()['module'], 'suffix_window_recovery')
        registry = wr.extend_registry(self.fx.base, self.fx.admitted, receipt)
        path = self.root/'new-registered.json'
        actual = wr.write_registry(registry, path, deadline=time.monotonic()+30)
        returned = self.root/'new-registration-return.json'; returned.write_bytes(raw(actual))
        from experiments.time_cut_v2.recorded_real import suffix_window
        options = SimpleNamespace(**dict(self.values, registry=str(path), registry_sha=actual['registry_sha256'],
            registry_return=str(returned), registry_return_sha=plan.pin(returned)['sha256']))
        scope, loaded = suffix_window.load_registry(options, self.fx.source,
            deadline=time.monotonic()+30, before=lambda: None)
        self.assertIs(type(scope), wr.ReceiptScope)
        self.assertEqual(scope.commitment(), self.fx.admitted.commitment())
        window = detach_json(next_window(self.fx.population, loaded.completed_block_ids(),
                                        population_plan_sha256=plan.digest(self.fx.population)))
        self.assertFalse(window['launch_required'])
        with patch('validation.suffix5.convex_checker.check_regime', side_effect=AssertionError('no numerical rerun')):
            checked = wr.reconcile_registry(loaded, scope, reviewed_sources=self.fx.source,
                                            deadline=time.monotonic()+30)
        self.assertEqual(checked.block_reports(), receipt.block_reports())
        dependencies = {row['path'] for row in receipt.metadata()['dependencies']}
        self.assertTrue({pin['path'] for pin in self.document['predecessors'][0]['artifacts'].values()
                         if pin is not None} <= dependencies)
        manifest = plan.load(args.recovery_attempt/'evidence/__manifest.json')
        self.assertTrue({str(args.recovery_attempt/'evidence'/pin['path']) for pin in manifest['files']} <= dependencies)

    def test_exact_only_completed_receipt(self):
        receipt = self.admit(self.fixture(exact_only=True))
        self.assertEqual(receipt.metadata()['module'], 'suffix_window_recovery')
        self.assertTrue(receipt.block_reports()[0]['complete'])

    def test_missing_actual_return_source_policy_foreign_command_context_reject(self):
        args = self.fixture(); args.recovery_return.unlink()
        with self.assertRaises(ValueError): self.admit(args)
        args = self.fixture()
        with self.assertRaisesRegex(ValueError, 'allowlist'):
            rr.admit_completed_recovery(args, self.fx.admitted, reviewed_sources={}, deadline=time.monotonic()+30)
        mutations = [lambda value: value['context'].update(input_sha256='0'*64),
                     lambda value: value['command'].__setitem__(3, 'foreign.module'),
                     lambda value: value['command'].__setitem__(0, '/bin/false')]
        for mutate in mutations:
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                self.admit(self.fixture(mutate_request=mutate))
        args = self.fixture(); self.fx.policy_path.write_bytes(raw(dict(schema='unreviewed', reviewed_sources={})))
        with self.assertRaises(ValueError): self.admit(args)

    def test_resource_cpu_evidence_coverage_and_late_failure_reject(self):
        with self.assertRaises(ValueError): self.admit(self.fixture(extra_evidence=True))
        with self.assertRaises(ValueError):
            self.admit(self.fixture(mutate_summary=lambda value: value['resource_plan'].update(maximum_candidate_passes=99)))
        with self.assertRaises(ValueError):
            self.admit(self.fixture(mutate_request=lambda value: value['worker_cpus'].__setitem__(0, value['cpu'])))
        # Restore fixture CPU inputs after the intentional alias mutation.
        self.fx.values['worker_cpus'] = sorted(os.sched_getaffinity(0))[1:6]
        args = self.fixture()
        with patch.object(rr, 'read_phase_result', return_value=dict(status='unresolved')):
            with self.assertRaisesRegex(ValueError, 'runtime'): self.admit(args)
        args = self.fixture()
        with patch.object(wr, 'CheckedWindowReceipt', side_effect=TimeoutError('late receipt publication')):
            with self.assertRaises(TimeoutError): self.admit(args)

    def test_bad_reference_coverage_and_zero_job_truthfulness_reject(self):
        def reference(rows): rows[1]['provenance']['archive_row_sha256'] = '0'*64
        def duplicate(rows): rows.insert(2, deepcopy(rows[1]))
        def partial(rows): rows.pop(1)
        for mutate in (reference, duplicate, partial):
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                self.admit(self.fixture(mutate_rows=mutate))
        with self.assertRaisesRegex(ValueError, 'fabricate'):
            self.admit(self.fixture(exact_only=True, mutate_rows=lambda rows: rows[-1].update(transport={})))


    def test_same_source_failed_recovery_then_exact_only_registry_admission(self):
        from experiments.time_cut_v2.recorded_real import recovery_plan
        first = self.fixture()
        evidence = first.recovery_attempt/'evidence'
        document = deepcopy(self.document)
        cold = plan.load(evidence/'cold-replay.json')
        admitted = recovery_plan.admit(recovery_plan.load(self.plan_path, plan.pin(self.plan_path)['sha256'],
            deadline=time.monotonic()+30), self.fx.admitted, self.fx.base,
            reviewed_sources=self.fx.source, deadline=time.monotonic()+30)
        history, leaves = rr._history(admitted, cold, self.fx.selection['blocks'],
            wr._Dependencies(lambda: None), lambda: None)
        context = plan.load(evidence/'recovery-summary.json')['source_context']
        proof = evidence/'recovery-model-proofs.jsonl.gz'
        added, encoding, _, _ = rr._consume(proof, plan.pin(proof), self.fx.selection['blocks'],
            context, history, leaves, lambda: None)
        leaves.update(added)
        history.append(dict(archive=plan.pin(proof), source_context=context,
            gzip_eof=True, trailing_partial_row_bytes=0))
        # A resource/publication failure after final proof bytes is still a
        # failed run. No prior successful caller return is admitted.
        for path in (first.recovery_attempt/'result.json', first.recovery_attempt/'decision.json', first.recovery_return):
            value = plan.load(path); value['status'] = 'unresolved'; value.pop('acceptance_receipt', None)
            path.write_bytes(raw(value))
        pin = self.planfx.pin
        artifacts = dict(request=pin(first.recovery_attempt/'request.json'), run_binding=pin(evidence/'run-binding.json'),
            selection=pin(evidence/'window-selection.json'), base_registry=pin(evidence/'base-registry.json'),
            source_policy=pin(self.fx.policy_path), archive=pin(proof), summary=pin(evidence/'recovery-summary.json'),
            manifest=pin(evidence/'__manifest.json'), result=pin(first.recovery_attempt/'result.json'),
            decision=pin(first.recovery_attempt/'decision.json'), actual_return=pin(first.recovery_return),
            recovery_plan=pin(evidence/'recovery-plan.json'), cold_replay=pin(evidence/'cold-replay.json'))
        document['predecessors'].append(dict(module=recovery_plan.MODULE, source_commit='f'*40,
            source_sha256='e'*64, attempt=str(first.recovery_attempt), archive_mode='finalized',
            source_context=context, artifacts=artifacts))
        next_cold = rr._cold_summary(self.fx.selection['blocks'], history, leaves)
        def repeated_original(**kwargs):
            self.plan_path = self.root/'second-recovery-plan.json'; self.plan_path.write_bytes(raw(document))
            return document, history, leaves, next_cold
        with patch.object(self, 'original', side_effect=repeated_original):
            second = self.fixture(exact_only=True)
        receipt = self.admit(second)
        self.assertEqual(receipt.metadata()['source_commit'], 'f'*40)
        self.assertTrue(receipt.block_reports()[0]['complete'])
        self.assertIn(str(proof), {row['path'] for row in receipt.metadata()['dependencies']})
        proof.chmod(0o600); proof.unlink()
        with self.assertRaises(ValueError): self.admit(second)

    def test_missing_or_changed_transitive_proof_invalidates_reconciliation(self):
        args = self.fixture(); receipt = self.admit(args)
        registry = wr.make_registry(self.fx.admitted, [receipt])
        ancestor = Path(self.document['predecessors'][0]['artifacts']['archive']['path'])
        original = ancestor.read_bytes(); ancestor.chmod(0o600); ancestor.unlink()
        with self.assertRaises(ValueError):
            wr.reconcile_registry(registry, self.fx.admitted, reviewed_sources=self.fx.source,
                                  deadline=time.monotonic()+30)
        ancestor.write_bytes(original[:-1]+bytes([original[-1]^1]))
        with self.assertRaises(ValueError):
            wr.reconcile_registry(registry, self.fx.admitted, reviewed_sources=self.fx.source,
                                  deadline=time.monotonic()+30)


if __name__ == '__main__':
    unittest.main()
