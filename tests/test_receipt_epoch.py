"""Tiny byte/protocol fixtures and genuine small enumerated population.

Completed-source outcomes are synthetic, as in window_receipts tests; this
tests provenance/continuity, never mathematical truth or real D0 acceptance.
No LP, real-population launch, or real archive is used.
"""
from copy import deepcopy
from dataclasses import asdict
from fractions import Fraction
import io
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from experiments.time_cut_v2.recorded_real import plan, domain, window_receipts as wr
from tests import test_suffix_window_receipts as fixture_module
from tests import test_real_model_preview as preview_module
from tests.test_recovered_real_family import prepare as prepare_family
from experiments.time_cut_v2.recorded_real.logical_models import count_logical_models
from tools.receipt_epoch import closure, epoch, sidecar


def row(path):
    return dict(path=str(Path(path).absolute()), **plan.pin(path))


class ClosureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.attempt = self.root/'attempt'; (self.attempt/'evidence').mkdir(parents=True)
        for relative in ('request.json', 'spool', 'evidence/__journal.jsonl', 'evidence/proof.gz'):
            (self.attempt/relative).write_bytes(b'abcdef')
        self.snapshot = closure.Closure.capture([str(self.attempt)], [row(self.attempt/'evidence/proof.gz')], lambda: None)

    def test_all_unique_closed_files_are_stream_hashed_each_phase(self):
        with patch.object(closure, '_file', wraps=closure._file) as consumed:
            self.snapshot.rehash(lambda: None)
        self.assertEqual(consumed.call_count, 4)
        self.assertEqual({call.args[0] for call in consumed.call_args_list}, set(self.snapshot.files))

    def test_only_exact_replay_member_can_cross_default_streaming_cap(self):
        path = self.attempt/'evidence/proof.gz'; path.write_bytes(b'abcdefghijklmno')
        pin = row(path)
        with patch.object(closure, 'MAX_FILE_BYTES', 8):
            with self.assertRaisesRegex(ValueError, 'bounded closure pin'):
                closure.Closure.capture([str(self.attempt)], [pin], lambda: None)
            grant = dict(pin)
            snapshot = closure.Closure.capture([str(self.attempt)], [pin], lambda: None,
                                               replay_members={str(path): grant})
            pin['sha256'] = '0'*64; grant['size_bytes'] = 99
            self.assertEqual(snapshot.replay_members[str(path)]['size_bytes'], 15)
            self.assertEqual(snapshot.replay_members[str(path)]['sha256'], row(path)['sha256'])
            with self.assertRaises(TypeError): snapshot.replay_members[str(path)]['sha256'] = '0'*64
            snapshot.rehash(lambda: None)
            path.write_bytes(b'abcdefghijklmnn')
            with self.assertRaises(ValueError): snapshot.rehash(lambda: None)
            with self.assertRaisesRegex(ValueError, 'differs from authenticated manifest'):
                closure.Closure.capture([str(self.attempt)], [row(path)], lambda: None,
                                        replay_members={str(path): dict(snapshot.replay_members[str(path)])})

    def test_actual_hash_detects_mutation_even_if_identity_layer_is_mocked_unchanged(self):
        path = self.attempt/'evidence/proof.gz'; path.write_bytes(b'ghijkl')
        ident = self.snapshot.files[str(path)][0]
        with patch.object(closure.Closure, 'continuity'), patch.object(closure, '_identity', return_value=ident):
            with self.assertRaisesRegex(ValueError, 'historical bytes'):
                self.snapshot.rehash(lambda: None)

    def test_archive_journal_control_spool_with_restored_mtime_reject(self):
        for relative in ('request.json', 'spool', 'evidence/__journal.jsonl', 'evidence/proof.gz'):
            path = self.attempt/relative
            original = path.stat(); path.write_bytes(b'ghijkl')
            os.utime(path, ns=(original.st_atime_ns, original.st_mtime_ns))
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                self.snapshot.rehash(lambda: None)
            path.write_bytes(b'abcdef')

    def test_addition_removal_same_bytes_replacement_and_links_reject(self):
        for action in ('add', 'remove', 'replace', 'symlink', 'hardlink'):
            path = self.attempt/'spool'
            if action == 'add': (self.attempt/'foreign').write_bytes(b'x')
            elif action == 'remove': path.unlink()
            elif action == 'replace': path.unlink(); path.write_bytes(b'abcdef')
            elif action == 'symlink': path.unlink(); path.symlink_to(self.attempt/'request.json')
            else: os.link(path, self.root/'alias')
            with self.subTest(action=action), self.assertRaises((ValueError, OSError)):
                self.snapshot.rehash(lambda: None)
            # Each subsequent mutation starts from a fresh actual snapshot.
            if action == 'add': (self.attempt/'foreign').unlink()
            elif action in ('remove', 'replace', 'symlink'):
                if path.exists() or path.is_symlink(): path.unlink()
                path.write_bytes(b'abcdef')
            else: (self.root/'alias').unlink()
            self.snapshot = closure.Closure.capture([str(self.attempt)], [], lambda: None)

    def test_symlink_parent_directory_swap_and_fifo_reject(self):
        moved = self.attempt.with_name('moved'); self.attempt.rename(moved)
        self.attempt.symlink_to(moved, target_is_directory=True)
        with self.assertRaises((ValueError, OSError)): self.snapshot.rehash(lambda: None)
        self.attempt.unlink(); self.attempt.mkdir(); os.mkfifo(self.attempt/'pipe')
        with self.assertRaises(ValueError): closure.Closure.capture([str(self.attempt)], [], lambda: None)

    def test_in_read_modification_and_deadline_reject(self):
        path = self.attempt/'spool'; calls = 0
        def mutate():
            nonlocal calls
            calls += 1
            if calls == 2: path.write_bytes(b'ghijkl')
        with self.assertRaises(ValueError): closure._file(str(path), mutate)
        with self.assertRaises(TimeoutError):
            self.snapshot.rehash(lambda: (_ for _ in ()).throw(TimeoutError('phase deadline')))


class ReplayGrantTests(unittest.TestCase):
    def test_large_replay_member_requires_original_phase_manifest_and_dependency(self):
        attempt = '/tmp/review-only-original-replay'
        request_pin = dict(path=attempt+'/request.json', size_bytes=40, sha256='d'*64)
        request = dict(command=['python','-B','-m',epoch.receipts.MODULE_PREFIX+'parallel_replay',
                                '--worker','--deadline','1'], profile=asdict(epoch.BATCH_REPLAY))
        returned = dict(path='/tmp/review-only-replay.return.json', size_bytes=12, sha256='a'*64)
        manifest_pin = dict(path=attempt+'/evidence/__manifest.json', size_bytes=40, sha256='b'*64)
        member = dict(path='callback-receipts.json', size_bytes=closure.MAX_FILE_BYTES+1, sha256='c'*64)
        member_pin = dict(path=attempt+'/evidence/'+member['path'], size_bytes=member['size_bytes'],
                          sha256=member['sha256'])
        entry = dict(dependencies=[request_pin, returned, manifest_pin, member_pin])
        values = dict(replay_attempt=attempt, replay_return=returned['path'],
                      replay_return_sha=returned['sha256'])
        accepted = dict(status='completed', descendants_reaped=True,
                        request_sha256=request_pin['sha256'], profile=asdict(epoch.BATCH_REPLAY),
                        verified_manifest_sha256=manifest_pin['sha256'],
                        verified_manifest_size_bytes=manifest_pin['size_bytes'])
        manifest = dict(profile_name=epoch.BATCH_REPLAY.name,
                        cap_bytes=epoch.BATCH_REPLAY.worker_evidence_bytes, files=[member],
                        charged_bytes=epoch.WRITER_HEADROOM+epoch.ENTRY_CHARGE+2*member['size_bytes'])
        with patch.object(epoch, '_request', return_value=(values, {})), \
             patch.object(epoch, '_read', side_effect=[request, dict(status='completed'), manifest]), \
             patch.object(epoch, 'read_phase_result', return_value=accepted) as phase:
            self.assertEqual(epoch.authenticated_replay_members(dict(entries=[entry]), time.monotonic()+5,
                                                                 lambda: None), {member_pin['path']: member_pin})
            phase.assert_called_once()
        with patch.object(epoch, '_request', return_value=(values, {})), \
             patch.object(epoch, '_read', side_effect=[request, dict(status='completed')]), \
             patch.object(epoch, 'read_phase_result', side_effect=ValueError('original phase failed')):
            with self.assertRaisesRegex(ValueError, 'original phase failed'):
                epoch.authenticated_replay_members(dict(entries=[entry]), time.monotonic()+5, lambda: None)
        for change in (dict(accepted, request_sha256='0'*64),
                       dict(accepted, descendants_reaped=False), dict(accepted, status='unresolved')):
            with self.subTest(change=change), patch.object(epoch, '_request', return_value=(values, {})), \
                 patch.object(epoch, '_read', side_effect=[request, dict(status='completed')]), \
                 patch.object(epoch, 'read_phase_result', return_value=change), \
                 self.assertRaisesRegex(ValueError, 'return/request binding changed'):
                epoch.authenticated_replay_members(dict(entries=[entry]), time.monotonic()+5, lambda: None)
        with patch.object(epoch, '_request', return_value=(values, {})), \
             patch.object(epoch, '_read', side_effect=[request, dict(status='completed'), manifest]), \
             patch.object(epoch, 'read_phase_result', return_value=accepted):
            with self.assertRaisesRegex(ValueError, 'retained dependency pin'):
                epoch.authenticated_replay_members(dict(entries=[dict(dependencies=[request_pin, returned, manifest_pin])]),
                                                   time.monotonic()+5, lambda: None)
        wrong = dict(request, command=['python','-B','-m',epoch.receipts.MODULE_PREFIX+'parallel_profile',
                                       '--worker','--deadline','1'])
        with patch.object(epoch, '_request', return_value=(values, {})), \
             patch.object(epoch, '_read', return_value=wrong), \
             self.assertRaisesRegex(ValueError, 'only from reviewed parallel replay command'):
            epoch.authenticated_replay_members(dict(entries=[entry]), time.monotonic()+5, lambda: None)
        oversized = (epoch.BATCH_REPLAY.worker_evidence_bytes-epoch.WRITER_HEADROOM-epoch.ENTRY_CHARGE)//2+1
        over_manifest = dict(manifest, files=[dict(member, size_bytes=oversized)],
                             charged_bytes=epoch.WRITER_HEADROOM+epoch.ENTRY_CHARGE+2*oversized)
        for changed, error in ((dict(manifest, charged_bytes=manifest['charged_bytes']+1), 'charge changed'),
                               (over_manifest, 'charge changed'),
                               (dict(manifest, profile_name=epoch.CAPTURE.name), 'charge changed')):
            with self.subTest(error=error), patch.object(epoch, '_request', return_value=(values, {})), \
                 patch.object(epoch, '_read', side_effect=[request, dict(status='completed'), changed]), \
                 patch.object(epoch, 'read_phase_result', return_value=accepted), \
                 self.assertRaisesRegex(ValueError, error):
                epoch.authenticated_replay_members(dict(entries=[entry]), time.monotonic()+5, lambda: None)


def expanded_inputs(self):
    """Six genuine charge bands give two canonical blocks, without LP."""
    case = deepcopy(self.fx.rows[1])
    case['query']['charging_segments'] = [[str(Fraction(5*i, 6)), str(Fraction(5*(i+1), 6)),
        i+1, str(-Fraction(5*i*(i+1), 12))] for i in range(6)]
    original = self.fx.make_plan(case); trusted = prepare_family(case)
    with self.fx.writer('capture') as writer:
        cap = domain.capture(original, self.root, writer, 'a'*64); writer.finalize()
    path = self.root/'capture/capture.json'
    with self.fx.writer('replay') as writer:
        summary = domain.replay(original, self.root, writer, 'a'*64, path, cap['capture']['sha256']); writer.finalize()
    index = plan.load(self.root/'replay/query-index.json')
    logical = count_logical_models(index, trusted, summary['checked'])['logical_model_plan']
    return original, trusted, index, logical, path, cap['capture']['sha256']


class EpochTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.WindowReceiptTests()
        with patch.object(preview_module.ModelPreview, 'inputs', expanded_inputs):
            self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        manager = patch.object(epoch, '_upstream_closure', side_effect=lambda entry, values, before:
            ({values['replay_attempt'], values['logical_attempt']}, [], []))
        manager.start(); self.addCleanup(manager.stop)
        manager = patch.object(epoch, 'authenticated_replay_members', return_value={})
        manager.start(); self.addCleanup(manager.stop)
        self.root = self.fixture.root
        (self.root/'logical').mkdir()
        for attempt in (self.root/'replay', self.root/'logical'):
            (attempt/'spool').write_bytes(b'tiny mock upstream control')
        # Existing fixture independently checks the population but injects the
        # unavailable saved upstream runtime boundary, exactly as its old tests.
        self.assertGreater(self.fixture.population['total_models'], 256)
        self.first_args = self.fixture.fixture(maximum_blocks=1)
        self.first_actual, self.first_registry = self.register(self.first_args)
        code_root = Path(wr.__file__).resolve().parents[3]
        self.code_pins = [dict(path=str(code_root/name), **pin)
                          for name, pin in wr.suffix_census.source_inventory(code_root).items()]
        self.code_pins += [row(path) for path in Path(epoch.__file__).parent.glob('*.py')]

    def register(self, args):
        receipt = self.fixture.admit(args)
        checked = wr.extend_registry(self.fixture.base, self.fixture.admitted, receipt)
        path = Path(self.fixture.values['registry_output'])
        returned = wr.write_registry(checked, path, deadline=time.monotonic()+10)
        retained = Path(self.fixture.values['registration_return_output']); retained.write_bytes(plan.canonical(returned)+b'\n')
        actual = dict(registry=row(path), registration_return=row(retained), runtime_return=row(args.window_return))
        return actual, checked

    def establish(self, **kwargs):
        return epoch.Epoch.establish(self.first_actual, code_pins=self.code_pins,
            reviewed_sources=self.fixture.source, deadline=time.monotonic()+30, **kwargs)

    def targets(self):
        return dict(attempt=str(self.root/'window2'), registry=str(self.root/'registry2.json'),
            registration_return=str(self.root/'registration2.json'), runtime_return=str(self.root/'return2.json'))

    def second(self):
        f = self.fixture
        f.base = self.first_registry
        f.base_path = Path(self.first_actual['registry']['path'])
        f.values.update(registry=str(f.base_path), registry_sha=self.first_actual['registry']['sha256'],
            registry_return=self.first_actual['registration_return']['path'],
            registry_return_sha=self.first_actual['registration_return']['sha256'],
            registry_output=self.targets()['registry'], registration_return_output=self.targets()['registration_return'])
        args = f.fixture()
        actual, checked = self.register(args)
        return args, actual, checked

    def test_full_establish_then_only_new_archive_admission_and_independent_final_reconcile(self):
        with patch.object(wr, '_archive', wraps=wr._archive) as archives, \
             patch.object(wr, 'reconcile_registry', wraps=wr.reconcile_registry) as reconciles:
            state = self.establish()
            first_calls = archives.call_count
            prepared = state.prepare(self.targets(), deadline=time.monotonic()+30)
            self.assertEqual(archives.call_count, first_calls)
            args, actual, checked = self.second()
            calls_after_source_fixture = archives.call_count
            result = state.cold(prepared['token'], actual, deadline=time.monotonic()+30)
            self.assertEqual(archives.call_count, calls_after_source_fixture+1)
            self.assertEqual(reconciles.call_count, 1)
            self.assertEqual(result['completed_models'], self.fixture.population['total_models'])
            self.assertTrue(result['final_independent_reconcile_required'])
            self.assertFalse(result['query_optimum_certified']); self.assertFalse(result['literal_G8_closed'])
            wr.reconcile_registry(checked, self.fixture.admitted, reviewed_sources=self.fixture.source,
                                  deadline=time.monotonic()+30)
            self.assertEqual(reconciles.call_count, 2)

    def test_pause_waits_for_cold_boundary_and_does_not_allow_next_prepare(self):
        state = self.establish(); prepared = state.prepare(self.targets(), deadline=time.monotonic()+30)
        self.assertFalse(state.request_pause()['at_safe_boundary'])
        _, actual, _ = self.second()
        self.assertTrue(state.cold(prepared['token'], actual, deadline=time.monotonic()+30)['paused'])
        with self.assertRaisesRegex(ValueError, 'paused'): state.prepare(self.targets(), deadline=time.monotonic()+30)

    def test_expired_prepare_cold_and_failure_after_state_swap_destroy_authority(self):
        state = self.establish()
        with self.assertRaises(ValueError): state.prepare(self.targets(), deadline=time.monotonic()-1)
        self.assertFalse(state._live)
        state = self.establish(); prepared = state.prepare(self.targets(), deadline=time.monotonic()+30)
        _, actual, _ = self.second()
        with self.assertRaises(ValueError): state.cold(prepared['token'], actual, deadline=time.monotonic()-1)
        self.assertFalse(state._live)
        state = self.establish(); prepared = state.prepare(self.targets(), deadline=time.monotonic()+30)
        def interrupted_after_swap():
            if state._generation == 1: raise InterruptedError('lost acknowledgement after state swap')
        with self.assertRaises(InterruptedError):
            state.cold(prepared['token'], actual, deadline=time.monotonic()+30, before=interrupted_after_swap)
        self.assertFalse(state._live); self.assertIsNone(state._registry)

    def test_stale_prepare_token_caller_pin_and_duplicate_cold_reject(self):
        state = self.establish(); prepared = state.prepare(self.targets(), deadline=time.monotonic()+30)
        _, actual, _ = self.second()
        stale = dict(prepared['token'], generation=9)
        with self.assertRaisesRegex(ValueError, 'token'): state.cold(stale, actual, deadline=time.monotonic()+30)
        state = self.establish(); prepared = state.prepare(self.targets(), deadline=time.monotonic()+30)
        broken = deepcopy(actual); broken['runtime_return']['sha256'] = 'f'*64
        with self.assertRaises(ValueError): state.cold(prepared['token'], broken, deadline=time.monotonic()+30)
        state = self.establish(); prepared = state.prepare(self.targets(), deadline=time.monotonic()+30)
        state.cold(prepared['token'], actual, deadline=time.monotonic()+30)
        with self.assertRaises(ValueError): state.cold(prepared['token'], actual, deadline=time.monotonic()+30)

    def test_previous_archive_mutation_invalidates_prepare_and_final_full_reconcile(self):
        state = self.establish()
        archive = self.first_args.window_attempt/'evidence/model-proofs.jsonl.gz'
        info = archive.stat(); archive.chmod(0o600); archive.write_bytes(archive.read_bytes()+b'x')
        os.utime(archive, ns=(info.st_atime_ns, info.st_mtime_ns))
        with self.assertRaises(ValueError): state.prepare(self.targets(), deadline=time.monotonic()+30)
        self.assertFalse(state._live)
        with self.assertRaises(ValueError):
            wr.reconcile_registry(self.first_registry, self.fixture.admitted, reviewed_sources=self.fixture.source,
                                  deadline=time.monotonic()+30)

    def test_restarted_epoch_rejects_old_token_and_disk_report_cannot_construct_authority(self):
        first = self.establish(); prepared = first.prepare(self.targets(), deadline=time.monotonic()+30)
        first.invalidate(); restarted = self.establish()
        restarted.prepare(self.targets(), deadline=time.monotonic()+30)
        _, actual, _ = self.second()
        with self.assertRaisesRegex(ValueError, 'token'): restarted.cold(prepared['token'], actual, deadline=time.monotonic()+30)
        with self.assertRaises(ValueError): epoch.Epoch()

    def test_initial_deadline_logic_source_and_policy_allowlist_fail_closed(self):
        with self.assertRaises(ValueError):
            epoch.Epoch.establish(self.first_actual, code_pins=self.code_pins,
                reviewed_sources=self.fixture.source, deadline=time.monotonic()-1)
        forged = deepcopy(self.code_pins); forged[0]['sha256'] = '0'*64
        with self.assertRaises(ValueError):
            epoch.Epoch.establish(self.first_actual, code_pins=forged,
                reviewed_sources=self.fixture.source, deadline=time.monotonic()+30)
        with self.assertRaises(ValueError):
            epoch.Epoch.establish(self.first_actual, code_pins=self.code_pins,
                reviewed_sources={}, deadline=time.monotonic()+30)

    def test_repaired_registry_old_entry_deletion_and_reordering_reject(self):
        _, actual, checked = self.second()
        original = checked.metadata()
        for reorder in (False, True):
            state = self.establish(); prepared = state.prepare(self.targets(), deadline=time.monotonic()+30)
            entries = original['entries'][::-1] if reorder else original['entries'][1:]
            changed = wr._registry_metadata(self.fixture.admitted, entries)
            path = Path(actual['registry']['path']); path.write_bytes(plan.canonical(changed)+b'\n')
            registered = plan.load(actual['registration_return']['path'])
            registered.update(registry_sha256=plan.pin(path)['sha256'], registry_size_bytes=path.stat().st_size,
                entry_ids=[entry['entry_id'] for entry in entries],
                completed_block_ids=[block['range']['block_id'] for block in changed['blocks']])
            returned = Path(actual['registration_return']['path']); returned.write_bytes(plan.canonical(registered)+b'\n')
            forged = dict(actual, registry=row(path), registration_return=row(returned))
            with self.subTest(reorder=reorder), self.assertRaisesRegex(ValueError, 'append exactly one'):
                state.cold(prepared['token'], forged, deadline=time.monotonic()+30)
            self.assertFalse(state._live)

    def test_source_policy_same_bytes_new_path_cannot_replace_frozen_pointer(self):
        state = self.establish(); prepared = state.prepare(self.targets(), deadline=time.monotonic()+30)
        different = self.root/'different-policy.json'; different.write_bytes(self.fixture.policy_path.read_bytes())
        self.fixture.values['source_policy'] = str(different)
        _, actual, _ = self.second()
        with self.assertRaisesRegex(ValueError, 'source/policy/population'):
            state.cold(prepared['token'], actual, deadline=time.monotonic()+30)
        self.assertFalse(state._live)

    def test_foreign_population_even_with_repaired_outer_registry_return_reject(self):
        state = self.establish(); prepared = state.prepare(self.targets(), deadline=time.monotonic()+30)
        _, actual, checked = self.second()
        changed = checked.metadata(); changed['population']['unique_logical_models'] += 1
        path = Path(actual['registry']['path']); path.write_bytes(plan.canonical(changed)+b'\n')
        returned = Path(actual['registration_return']['path']); value = plan.load(returned)
        value.update(registry_sha256=plan.pin(path)['sha256'], registry_size_bytes=path.stat().st_size,
                     population_sha256=plan.digest(changed['population']))
        returned.write_bytes(plan.canonical(value)+b'\n')
        with self.assertRaises(ValueError):
            state.cold(prepared['token'], dict(actual, registry=row(path), registration_return=row(returned)),
                       deadline=time.monotonic()+30)
        self.assertFalse(state._live)

    def test_precommit_continuity_fault_cannot_advance_memory(self):
        state = self.establish(); prepared = state.prepare(self.targets(), deadline=time.monotonic()+30)
        _, actual, _ = self.second()
        original = closure.Closure.continuity
        def fail_new(snapshot, before):
            if self.targets()['attempt'] in snapshot.roots: raise InterruptedError('new closure fence interrupted')
            return original(snapshot, before)
        with patch.object(closure.Closure, 'continuity', fail_new), self.assertRaises(InterruptedError):
            state.cold(prepared['token'], actual, deadline=time.monotonic()+30)
        self.assertFalse(state._live); self.assertIsNone(state._registry)


class UpstreamClosureTests(unittest.TestCase):
    def test_capture_tree_and_actual_return_are_closed_from_pinned_replay_request(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve(); replay = root/'replay'; replay.mkdir()
            capture = root/'capture'; capture.mkdir(); (capture/'spool').write_bytes(b'tiny capture control')
            retained = root/'capture-return.json'; retained.write_bytes(b'{"tiny":true}\n')
            historical = root/'historical.json'
            inventory = {'producer.py': dict(size_bytes=7,sha256='a'*64)}
            historical.write_bytes(plan.canonical(dict(source_commit='b'*40,source_files=inventory,
                source_sha256=plan.digest(inventory),input_sha256='c'*64))+b'\n')
            request = replay/'request.json'
            request.write_bytes(plan.canonical(dict(command=[sys.executable, '-B', '-m', wr.MODULE_PREFIX+'parallel_replay',
                '--worker', '--capture-attempt', str(capture), '--capture-return', str(retained),
                '--capture-return-sha', plan.pin(retained)['sha256']]))+b'\n')
            entry = dict(dependencies=[row(request),row(historical)])
            roots, pins, phases = epoch._upstream_closure(entry, dict(replay_attempt=str(replay),
                logical_attempt=str(root/'logical'),historical_plan=str(historical),
                historical_plan_sha=plan.pin(historical)['sha256']), lambda: None)
            self.assertIn(str(capture), roots); self.assertIn(row(retained), pins)
            self.assertEqual(phases[0][0],str(capture))
            self.assertEqual(phases[0][1]['returned'],row(retained))
            self.assertEqual(phases[0][1]['historical_plan'],row(historical))
            with self.assertRaises(ValueError):
                epoch._upstream_closure(dict(dependencies=[]), dict(replay_attempt=str(replay),
                    logical_attempt=str(root/'logical')), lambda: None)


class CaptureSourceDomainTests(unittest.TestCase):
    """Nonempty real capture closure and full runtime reader; no skipped capture.

    Records are synthetic phase metadata, not numerical/producer attestation.
    The saved caller return and all supervisor/manifest hashes are checked by
    the original read_phase_result. No return predicate or capture list is mocked.
    """
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.number=0
        self.historical=self.root/'historical.json'
        self.inventory={'producer.py':dict(size_bytes=7,sha256='a'*64)}
        self.document=dict(source_commit='b'*40,source_files=self.inventory,
            source_sha256=plan.digest(self.inventory),input_sha256='c'*64)
        self.historical.write_bytes(plan.canonical(self.document)+b'\n')
        self.context=dict(plan_sha256=row(self.historical)['sha256'],
            source_sha256=self.document['source_sha256'],input_sha256='c'*64,profile_name=epoch.CAPTURE.name)
        self.replay=self.root/'replay';self.replay.mkdir();(self.root/'logical').mkdir()
        self.values=dict(replay_attempt=str(self.replay),logical_attempt=str(self.root/'logical'),
            historical_plan=str(self.historical),historical_plan_sha=row(self.historical)['sha256'])

    def fixture(self, *, context=None, capture_plan=None):
        self.number+=1;capture_plan=self.historical if capture_plan is None else capture_plan
        command=[sys.executable,'-B','-m',wr.MODULE_PREFIX+'worker','--phase','capture',
            '--plan',str(capture_plan),'--plan-sha',row(capture_plan)['sha256'],'--deadline','110.0']
        from experiments.time_cut_v2.recorded_real.worker import CAPTURE_FILES
        saved=fixture_module.UpstreamProofGraphTests().history(self.root,'capture'+str(self.number),
            epoch.CAPTURE,sorted(CAPTURE_FILES),context=self.context if context is None else context,command=command)
        request=self.replay/'request.json'
        request.write_bytes(plan.canonical(dict(command=[sys.executable,'-B','-m',wr.MODULE_PREFIX+'parallel_replay',
            '--worker','--capture-attempt',saved['attempt'],'--capture-return',saved['returned'],
            '--capture-return-sha',saved['returned_sha']]))+b'\n')
        entry=dict(dependencies=[row(request),row(self.historical)])
        roots,pins,phases=epoch._upstream_closure(entry,self.values,lambda:None)
        self.assertEqual(len(phases),1)
        return roots,pins,phases,saved,entry

    def authenticate(self, phases):
        attempt,contract=phases[0]
        return epoch._authenticate_capture(attempt,contract,time.monotonic()+30,lambda:None)

    def test_legal_distinct_capture_and_window_inventories_pass_nonempty_real_capture_reader(self):
        roots,pins,phases,_,entry=self.fixture()
        window_sources={'b'*40:'e'*64}
        self.assertNotIn(self.context['source_sha256'],window_sources.values())
        snapshot=closure.Closure.capture(roots,pins+entry['dependencies'],lambda:None)
        accepted=self.authenticate(phases)
        self.assertEqual(accepted['status'],'completed')
        self.assertEqual(accepted['context'],self.context)
        snapshot.continuity(lambda:None)

    def test_wrong_capture_hash_input_plan_or_profile_context_reject_even_with_valid_outer_receipts(self):
        for key in ('source_sha256','input_sha256','plan_sha256','profile_name'):
            context=dict(self.context);context[key]='foreign' if key=='profile_name' else '0'*64
            _,_,phases,_,_=self.fixture(context=context)
            with self.subTest(key=key),self.assertRaises(ValueError):self.authenticate(phases)

    def test_different_capture_commit_cannot_substitute_another_plan_with_same_inventory(self):
        other=self.root/'different-commit.json';document=dict(self.document,source_commit='d'*40)
        other.write_bytes(plan.canonical(document)+b'\n')
        _,_,phases,_,_=self.fixture(capture_plan=other)
        with self.assertRaisesRegex(ValueError,'commit/plan binding'):self.authenticate(phases)

    def test_capture_return_bytes_replacement_or_link_cannot_reuse_original_return_pin(self):
        for change in ('bytes','replace','link'):
            _,_,phases,saved,_=self.fixture();path=Path(saved['returned']);original=path.read_bytes()
            if change=='bytes':path.write_bytes(original.replace(b'completed',b'provision'))
            elif change=='replace':
                replacement=path.with_suffix('.replacement');replacement.write_bytes(original+b' ');os.replace(replacement,path)
            else:
                target=path.with_suffix('.target');target.write_bytes(original);path.unlink();path.symlink_to(target)
            with self.subTest(change=change),self.assertRaises((ValueError,OSError)):self.authenticate(phases)

    def test_historical_inventory_digest_and_commit_shape_are_required(self):
        for key,value in (('source_sha256','0'*64),('source_commit','invalid')):
            document=dict(self.document);document[key]=value
            self.historical.write_bytes(plan.canonical(document)+b'\n')
            self.values['historical_plan_sha']=row(self.historical)['sha256']
            with self.subTest(key=key),self.assertRaises(ValueError):self.fixture()


class IPCTests(unittest.TestCase):
    def test_duplicate_json_nonfinite_and_oversize_frames_reject(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}'):
            with self.assertRaises(ValueError): sidecar.decode(raw)
        with self.assertRaises(ValueError): sidecar.encode({'x': 'x'*sidecar.MAX_FRAME})

    def test_external_timeout_kills_only_metadata_child_and_cannot_continue(self):
        script = '''
import sys,time
from tools.receipt_epoch.sidecar import encode,AS_BYTES
from tools.receipt_epoch.epoch import PROTOCOL
sys.stdout.buffer.write(encode(dict(protocol=PROTOCOL,instance='a'*64,as_bytes=AS_BYTES)));sys.stdout.buffer.flush()
time.sleep(30)
'''
        parent = sidecar.Parent([sys.executable, '-B', '-c', script], cwd=Path(__file__).parents[1])
        self.addCleanup(parent.invalidate)
        with self.assertRaises(TimeoutError): parent.call('prepare', {'targets': {}}, seconds=.05)
        self.assertIsNotNone(parent.process.poll()); self.assertFalse(parent.live)
        with self.assertRaises(ValueError): parent.call('prepare', {'targets': {}})

    def test_process_exit_without_reply_is_fail_closed(self):
        script = '''
import sys
from tools.receipt_epoch.sidecar import encode,AS_BYTES
from tools.receipt_epoch.epoch import PROTOCOL
sys.stdout.buffer.write(encode(dict(protocol=PROTOCOL,instance='a'*64,as_bytes=AS_BYTES)));sys.stdout.buffer.flush()
'''
        parent = sidecar.Parent([sys.executable, '-B', '-c', script], cwd=Path(__file__).parents[1])
        self.addCleanup(parent.invalidate)
        with self.assertRaises((EOFError, BrokenPipeError)): parent.call('prepare', {'targets': {}}, seconds=1)
        self.assertFalse(parent.live)

    def test_child_exception_retains_bounded_diagnostic_and_exit_status(self):
        script = f'''
import sys
sys.path.insert(0, {str(Path(__file__).parents[1])!r})
from tools.receipt_epoch.sidecar import encode,AS_BYTES
from tools.receipt_epoch.epoch import PROTOCOL
sys.stdout.buffer.write(encode(dict(protocol=PROTOCOL,instance='a'*64,as_bytes=AS_BYTES)));sys.stdout.buffer.flush()
sys.stdin.buffer.read(4)
raise ValueError('synthetic metadata refusal')
'''
        with tempfile.TemporaryDirectory() as directory:
            diagnostic = Path(directory)/'worker.stderr'
            parent = sidecar.Parent([sys.executable, '-I', '-B', '-c', script],
                                    cwd=Path(__file__).parents[1], stderr_path=diagnostic)
            self.addCleanup(parent.invalidate)
            with self.assertRaises(EOFError): parent.call('establish', {}, seconds=2)
            facts = parent.diagnostic()
            self.assertEqual(facts['child_exit_status'], 1)
            self.assertEqual(facts['stderr_path'], str(diagnostic))
            self.assertLessEqual(facts['stderr_size_bytes'], sidecar.STDERR_BYTES)
            self.assertIn(b'synthetic metadata refusal', diagnostic.read_bytes())
            self.assertFalse(parent.live)
            with self.assertRaises(FileExistsError):
                sidecar.Parent([sys.executable, '-I', '-B', '-c', script],
                               cwd=Path(__file__).parents[1], stderr_path=diagnostic)

    def test_fresh_deadlines_sequence_nonce_cap_and_pause_with_micro_service(self):
        # Pure protocol stub; all actual receipt authentication is exercised by
        # EpochTests above. No disk JSON creates a real receipt in this process.
        script = '''
import sys
from tools.receipt_epoch import sidecar
class Micro:
 def __init__(self): self.pending=False;self.pause=False
 @classmethod
 def establish(cls,**kwargs): return cls()
 def prepare(self,**kwargs): self.pending=True;return {'micro_pending':True}
 def cold(self,**kwargs): self.pending=False;return {'paused':self.pause}
 def request_pause(self): self.pause=True;return {'at_safe_boundary':not self.pending}
 def invalidate(self): self.pending=False
class MicroOrigin:
 expected={'verifier_root':'.'}
 pins=[]
 def phase_check(self,deadline): pass
sidecar.Epoch=Micro
sidecar.SourceBinding=MicroOrigin
sidecar._live_checks=lambda *args,**kwargs:None
sidecar.serve(sys.stdin.buffer,sys.stdout.buffer,origin=MicroOrigin())
'''
        parent = sidecar.Parent([sys.executable, '-B', '-c', script], cwd=Path(__file__).parents[1])
        self.addCleanup(parent.invalidate)
        parent.call('establish', dict(actual={},code_pins=[],reviewed_sources={}), seconds=1)
        parent.call('prepare', dict(targets={}), seconds=1)
        self.assertFalse(parent.call('pause', {}, seconds=1)['at_safe_boundary'])
        self.assertTrue(parent.call('cold', dict(token={},actual={}), seconds=1)['paused'])
        self.assertEqual(parent.call('close', {}, seconds=1), {'status':'closed'})
        self.assertEqual(parent.process.returncode, 0)
        parent = sidecar.Parent([sys.executable, '-B', '-c', script], cwd=Path(__file__).parents[1])
        self.addCleanup(parent.invalidate)
        parent.instance = 'b'*64
        with self.assertRaises(EOFError): parent.call('establish', dict(actual={},code_pins=[],reviewed_sources={}), seconds=1)
        self.assertFalse(parent.live)

        parent = sidecar.Parent([sys.executable, '-B', '-c', script], cwd=Path(__file__).parents[1])
        self.addCleanup(parent.invalidate)
        with self.assertRaises(EOFError):
            parent.call('establish', dict(actual={},code_pins=[{'forged':'source'}],reviewed_sources={}), seconds=1)
        self.assertFalse(parent.live)

    def test_wrong_reply_sequence_is_fail_closed(self):
        script = '''
import sys
from tools.receipt_epoch.sidecar import encode,_receive,AS_BYTES
from tools.receipt_epoch.epoch import PROTOCOL
sys.stdout.buffer.write(encode(dict(protocol=PROTOCOL,instance='a'*64,as_bytes=AS_BYTES)));sys.stdout.buffer.flush()
r=_receive(sys.stdin.buffer)
sys.stdout.buffer.write(encode(dict(protocol=PROTOCOL,instance='a'*64,sequence=r['sequence']+1,result={})));sys.stdout.buffer.flush()
import time;time.sleep(30)
'''
        parent = sidecar.Parent([sys.executable, '-B', '-c', script], cwd=Path(__file__).parents[1])
        self.addCleanup(parent.invalidate)
        with self.assertRaisesRegex(ValueError, 'foreign or stale reply'): parent.call('prepare', {}, seconds=1)
        self.assertFalse(parent.live)


if __name__ == '__main__':
    unittest.main()
