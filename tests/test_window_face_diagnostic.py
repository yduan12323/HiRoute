"""Synthetic models and fake native results only; never invoke an optimizer."""
from copy import deepcopy
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import signal
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from experiments.time_cut_v2.recorded_real import window_face_diagnostic as d
from experiments.time_cut_v2.recorded_real import candidate_memory
from validation.suffix5 import basis_exchange as e, vendor_lp as v


def candidate(x, y, status=0):
    return SimpleNamespace(status=status, success=status == 0, message='synthetic candidate',
        x=x, fun=0, ineqlin=SimpleNamespace(marginals=y, residual=[0]*len(y)),
        eqlin=SimpleNamespace(marginals=[], residual=[]))


def inspect(task, native):
    return d.inspect_task(task, v, e, native, lambda: 25.0)


class InputTests(unittest.TestCase):
    def test_fixed_identities_and_pins(self):
        self.assertEqual(d.MODEL_PINS, {
            411229: 'd7907fccf77af692c12e6461ea3efc3c833d9069480210f463df7bbcad43de1d',
            411238: '42cb0dbdd68141bb4c34ad4dce4c8ab834fc3ed13829bdecd54df7188346d1ad',
            412024: '0751c5b99298931f9eacdca9182ac8ef7ac2e912191e1b4d0cb2369fcf65008c'})
        self.assertEqual(set(d.DESCRIPTOR_PINS), set(d.MODEL_PINS))
        self.assertEqual(d.INPUT_BYTES, 15593)
        self.assertEqual(d.INPUT_SHA, '82569746f926588db80ffb8f2170336c367772149283d8792ec7053df790e3e7')
        self.assertEqual(len(d.SOURCE_PINS), 4)

    def rows(self):
        return [dict(ordinal=o, model=dict(synthetic=o), descriptor=dict(ordinal=o),
                     canonical_model_sha256=d.digest(dict(synthetic=o))) for o in d.MODEL_PINS]

    def consume(self, rows, transform=None, tamper=False):
        model_pins = {r['ordinal']: d.digest(r['model']) for r in self.rows()}
        descriptors = {r['ordinal']: d.digest(r['descriptor']) for r in self.rows()}
        raw = d.canonical(rows)
        if transform:
            raw = transform(raw)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'models.json'
            path.write_bytes(raw[:-1]+b' ' if tamper else raw)
            with patch.multiple(d, INPUT_SHA=hashlib.sha256(raw).hexdigest(), INPUT_BYTES=len(raw),
                                MODEL_PINS=model_pins, DESCRIPTOR_PINS=descriptors):
                return d.selected_models(path)

    def test_consumed_bytes_bound_before_parse(self):
        rows = self.rows()
        self.assertEqual(set(self.consume(rows)), set(d.MODEL_PINS))
        with self.assertRaisesRegex(ValueError, 'consumed model input'):
            self.consume(rows, tamper=True)

    def test_missing_duplicate_wrong_model_and_descriptor(self):
        rows = self.rows()
        with self.assertRaisesRegex(ValueError, 'three fixed'):
            self.consume(rows[:-1])
        bad = deepcopy(rows); bad[1] = bad[0]
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.consume(bad)
        bad = deepcopy(rows); bad[0]['model']['synthetic'] = 0
        with self.assertRaisesRegex(ValueError, 'model pin'):
            self.consume(bad)
        bad = deepcopy(rows); bad[0]['descriptor']['extra'] = 'wrong'
        with self.assertRaisesRegex(ValueError, 'descriptor pin'):
            self.consume(bad)
        bad = deepcopy(rows); bad[0]['ordinal'] = True
        with self.assertRaisesRegex(ValueError, 'ordinal'):
            self.consume(bad)

    def test_duplicate_json_key_and_symlink_rejected(self):
        with self.assertRaisesRegex(ValueError, 'duplicate JSON'):
            self.consume(self.rows(), lambda raw: raw.replace(b'"ordinal":411229', b'"ordinal":411229,"ordinal":411229', 1))
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)/'target'; target.write_text('x')
            link = Path(folder)/'link'; link.symlink_to(target)
            with self.assertRaises(OSError):
                d.selected_models(link)


class ObservationTests(unittest.TestCase):
    task = dict(c=['-1'], A=[['1']], b=['2'], equalities=[])

    def hooks(self):
        return (v.linprog, v.solve_rational_equalities, v.verify_certificate, e.recover_exchange)

    def test_candidate_native_settings_and_denial_flags(self):
        old = self.hooks(); calls = []
        def native(*a, **kwargs):
            calls.append(kwargs)
            return candidate([2], [-1])
        report = inspect(self.task, native)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]['options'], dict(primal_feasibility_tolerance=1e-9,
            dual_feasibility_tolerance=1e-9, time_limit=25.0))
        self.assertEqual(calls[0]['bounds'], [(None, None)])
        self.assertEqual(calls[0]['method'], 'highs')
        self.assertEqual(report['outcome'], 'exact_candidate_returned')
        self.assertEqual(report['candidate_certificate']['objective'], '-2')
        self.assertEqual(report['native_pass_attempts'], 1)
        self.assertEqual(report['native_passes'][0]['ineqlin']['marginals'], [-1.0])
        self.assertTrue(all(value is False or value == 0 for value in d.DENIALS.values()))
        for k, value in d.DENIALS.items():
            self.assertEqual(report[k], value)
        self.assertEqual(self.hooks(), old)

    def test_tolerance_mutation_rejected_without_native(self):
        def fake_exact(*a):
            return v.linprog([], method='highs', bounds=[(None, None)],
                             options=dict(primal_feasibility_tolerance=1e-8, dual_feasibility_tolerance=1e-9))
        with patch.object(v, 'exact_lp', fake_exact):
            native = unittest.mock.Mock()
            report = inspect(self.task, native)
        native.assert_not_called()
        self.assertIn('tolerances/options changed', report['error'])

    def test_second_native_pass_phase_one_rejected(self):
        calls = []
        def native(*a, **k):
            calls.append(1)
            return candidate(None, [], status=2)
        report = inspect(self.task, native)
        self.assertEqual(calls, [1])
        self.assertEqual(report['native_pass_attempts'], 1)
        self.assertIn('Phase-I prohibited', report['error'])

    def test_explicit_second_native_call_rejected(self):
        def fake_exact(*args):
            for _ in range(2):
                v.linprog([], bounds=[(None, None)], method='highs',
                          options=dict(primal_feasibility_tolerance=1e-9, dual_feasibility_tolerance=1e-9))
        native = unittest.mock.Mock(return_value=candidate([2], [-1]))
        with patch.object(v, 'exact_lp', fake_exact):
            report = inspect(self.task, native)
        self.assertEqual(native.call_count, 1)
        self.assertEqual(report['native_pass_attempts'], 2)
        self.assertIn('second native pass', report['error'])

    def test_existing_exchange_result_and_exact_entry_preserved(self):
        task = dict(c=['-1', '0'], A=[['1', '0'], ['0', '1'], ['0', '1']],
                    b=['0', '1.000002', '1'], equalities=[])
        old = self.hooks()
        report = inspect(task, lambda *a, **k: candidate([0, 1.000001], [-1, 0, 0]))
        self.assertEqual(report['outcome'], 'exact_candidate_returned')
        entry = report['exchange_entries'][0]
        self.assertEqual(entry['selected_rows'], [0, 1])
        self.assertEqual(entry['basis'], [0, 1])
        self.assertEqual(entry['rest'], [2])
        self.assertEqual(entry['trials_observed'], 2)
        self.assertEqual(entry['outcome'], 'exact_candidate_returned')
        self.assertTrue(any(row.get('violated_inequalities') for row in report['exact_checks']['first']))
        samples = report['eliminations']['first']+report['eliminations']['last']
        primal = [row for row in samples if row['kind'] == 'primal']
        stationarity = [row for row in samples if row['kind'] == 'stationarity']
        self.assertTrue(primal)
        self.assertTrue(stationarity)
        self.assertTrue(all(row['task_row_identities'] is not None for row in primal))
        self.assertTrue(all('violated_inequalities' in row for row in primal if 'result' in row))
        self.assertTrue(all('violated_inequalities' not in row for row in stationarity))
        self.assertTrue(any(row.get('classification') == 'primal_infeasible' for row in primal))
        self.assertEqual(self.hooks(), old)

    def test_more_than_512_observations_do_not_change_order_or_result(self):
        seen = []
        checked = []
        def fake_check(c, A, b, eq, certificate):
            checked.append(certificate['sequence'])
            return True
        def fake_eliminate(rows, rhs, seed):
            seen.append(rhs[0])
            return (F(rhs[0]),), 1
        def fake_exact(c, A, b, eq):
            v.linprog([], bounds=[(None, None)], method='highs',
                      options=dict(primal_feasibility_tolerance=1e-9, dual_feasibility_tolerance=1e-9))
            for n in range(650):
                v.solve_rational_equalities([(F(1),)], [F(n)], (F(0),))
                v.verify_certificate(c, A, b, eq, dict(sequence=n))
            return dict(status='synthetic unchanged result')
        with patch.object(v, 'solve_rational_equalities', fake_eliminate), patch.object(v, 'exact_lp', fake_exact), patch.object(v, 'verify_certificate', fake_check):
            old = self.hooks()
            report = inspect(self.task, lambda *a, **k: candidate([2], [-1]))
            self.assertEqual(self.hooks(), old)
        self.assertEqual(seen, list(map(F, range(650))))
        self.assertEqual(checked, list(range(650)))
        self.assertEqual(report['exact_checks']['total'], 650)
        self.assertEqual(report['candidate_certificate'], dict(status='synthetic unchanged result'))
        records = report['eliminations']
        self.assertEqual((records['total'], records['retained'], records['omitted']), (650, 32, 618))
        self.assertTrue(records['truncated'])
        self.assertEqual(records['first'][0]['observation'], 1)
        self.assertEqual(records['last'][-1]['observation'], 650)

    def test_exchange_trial_count_and_stop_reason_are_observed(self):
        for count, message, outcome in (
            (513, 'Exact basis-exchange trial cap exhausted', 'trial_cap_exhausted'),
            (70, 'Exact basis-exchange neighborhood did not certify the candidate', 'neighborhood_exhausted')):
            def fake_exchange(c, A, b, eq, candidate_, selected_rows):
                basis, rest = [0], [1]
                for trials in range(1, count+1):
                    position, entering, proposed = 0, 1, [1]
                    v.solve_rational_equalities([A[0]], [b[0]], candidate_['x'])
                raise v.UncertifiedLP(message)
            def fake_exact(c, A, b, eq):
                v.linprog([], bounds=[(None, None)], method='highs',
                          options=dict(primal_feasibility_tolerance=1e-9, dual_feasibility_tolerance=1e-9))
                return e.recover_exchange(c, A, b, eq, dict(x=(F(0),)), [0])
            with patch.object(e, 'recover_exchange', fake_exchange), patch.object(v, 'exact_lp', fake_exact):
                report = inspect(self.task, lambda *a, **k: candidate([2], [-1]))
            entry = report['exchange_entries'][0]
            self.assertEqual(entry['trials_observed'], count)
            self.assertEqual(entry['basis'], [0])
            self.assertEqual(entry['rest'], [1])
            self.assertEqual(entry['outcome'], outcome)
            self.assertEqual(report['eliminations']['total'], count)
            self.assertTrue(report['eliminations']['truncated'])

    def test_backend_error_and_interrupt_restore_every_hook_and_timer(self):
        for exception in (RuntimeError('fake failure'), TimeoutError('fake timeout'), KeyboardInterrupt()):
            old = self.hooks()
            old_signal = signal.getsignal(signal.SIGALRM)
            def native(*a, **k):
                raise exception
            if isinstance(exception, KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    with d.deadline(time.monotonic()+1):
                        inspect(self.task, native)
            else:
                with d.deadline(time.monotonic()+1):
                    report = inspect(self.task, native)
                self.assertIn(type(exception).__name__, report['error'])
            self.assertEqual(self.hooks(), old)
            self.assertEqual(signal.getsignal(signal.SIGALRM), old_signal)
            self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))

    def test_interruption_during_each_hook_install_restores_all_hooks(self):
        class InterruptedNamespace(SimpleNamespace):
            def __setattr__(self, name, value):
                super().__setattr__(name, value)
                if name == self.__dict__.get('interrupt_on') and not self.__dict__.get('interrupted'):
                    self.__dict__['interrupted'] = True
                    raise TimeoutError('interrupted while installing '+name)
        for target in ('linprog', 'solve_rational_equalities', 'verify_certificate', 'recover_exchange'):
            backend = InterruptedNamespace(linprog=v.linprog, solve_rational_equalities=v.solve_rational_equalities,
                verify_certificate=v.verify_certificate, exact_lp=v.exact_lp, dot=v.dot)
            exchange = InterruptedNamespace(recover_exchange=e.recover_exchange,
                MAX_EXCHANGE_TRIALS=e.MAX_EXCHANGE_TRIALS)
            before = (backend.linprog, backend.solve_rational_equalities, backend.verify_certificate, exchange.recover_exchange)
            if target == 'recover_exchange':
                exchange.interrupt_on = target
            else:
                backend.interrupt_on = target
            report = d.inspect_task(self.task, backend, exchange, lambda *a, **k: None, lambda: 25.0)
            self.assertIn('interrupted while installing', report['error'])
            self.assertEqual(before, (backend.linprog, backend.solve_rational_equalities,
                                     backend.verify_certificate, exchange.recover_exchange))

    def test_interruption_during_handler_install_restores_timer(self):
        original = signal.signal
        handler = signal.getsignal(signal.SIGALRM)
        interrupted = False
        def install_then_interrupt(sig, value):
            nonlocal interrupted
            result = original(sig, value)
            if not interrupted:
                interrupted = True
                raise TimeoutError('interrupted handler installation')
            return result
        with patch.object(d.signal, 'signal', side_effect=install_then_interrupt):
            with self.assertRaisesRegex(TimeoutError, 'handler installation'):
                with d.deadline(time.monotonic()+1):
                    self.fail('body must not execute')
        self.assertEqual(signal.getsignal(signal.SIGALRM), handler)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))

    def test_alarm_during_each_hook_cleanup_waits_until_every_hook_is_restored(self):
        class AlarmNamespace(SimpleNamespace):
            def __setattr__(self, name, value):
                super().__setattr__(name, value)
                if (name == self.__dict__.get('alarm_on') and
                    value is self.__dict__.get('original_value') and not self.__dict__.get('alarmed')):
                    self.__dict__['alarmed'] = True
                    signal.raise_signal(signal.SIGALRM)
        for target in ('linprog', 'solve_rational_equalities', 'verify_certificate', 'recover_exchange'):
            backend = AlarmNamespace(linprog=v.linprog, solve_rational_equalities=v.solve_rational_equalities,
                verify_certificate=v.verify_certificate, exact_lp=lambda *a: dict(status='synthetic'), dot=v.dot)
            exchange = AlarmNamespace(recover_exchange=e.recover_exchange, MAX_EXCHANGE_TRIALS=e.MAX_EXCHANGE_TRIALS)
            old = (backend.linprog, backend.solve_rational_equalities, backend.verify_certificate, exchange.recover_exchange)
            target_object = exchange if target == 'recover_exchange' else backend
            target_object.alarm_on = target
            target_object.original_value = getattr(target_object, target)
            old_mask = signal.pthread_sigmask(signal.SIG_BLOCK, set())
            with self.assertRaises(TimeoutError):
                with d.deadline(time.monotonic()+1):
                    d.inspect_task(self.task, backend, exchange, lambda *a, **k: None, lambda: 25.0)
            self.assertEqual(old, (backend.linprog, backend.solve_rational_equalities,
                                  backend.verify_certificate, exchange.recover_exchange))
            self.assertEqual(signal.pthread_sigmask(signal.SIG_BLOCK, set()), old_mask)
            self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))

    def test_pending_alarm_during_timer_cleanup_is_consumed_before_old_handler(self):
        original = signal.setitimer
        handler = signal.getsignal(signal.SIGALRM)
        alarmed = False
        def alarm_when_canceling(which, seconds, *args):
            nonlocal alarmed
            if seconds == 0 and not alarmed:
                alarmed = True
                signal.raise_signal(signal.SIGALRM)
            return original(which, seconds, *args)
        with patch.object(d.signal, 'setitimer', side_effect=alarm_when_canceling):
            with self.assertRaisesRegex(TimeoutError, 'timer cleanup'):
                with d.deadline(time.monotonic()+1):
                    pass
        self.assertEqual(signal.getsignal(signal.SIGALRM), handler)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))
        self.assertNotIn(signal.SIGALRM, signal.sigpending())

    def test_real_signal_restores_hooks(self):
        old = self.hooks(); handler = signal.getsignal(signal.SIGALRM)
        def native(*a, **k):
            signal.raise_signal(signal.SIGALRM)
        with d.deadline(time.monotonic()+1):
            report = inspect(self.task, native)
        self.assertIn('TimeoutError', report['error'])
        self.assertEqual(self.hooks(), old)
        self.assertEqual(signal.getsignal(signal.SIGALRM), handler)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))


class GuardTests(unittest.TestCase):
    def test_own_exec_peak_and_read_failures_fail_closed(self):
        self.assertEqual(d.checked_peak(lambda: d.MAX_PEAK), d.MAX_PEAK)
        for value in (None, -1, 0, True, d.MAX_PEAK+1):
            with self.assertRaisesRegex(ValueError, 'own-exec VmHWM'):
                d.checked_peak(lambda: value)
        with patch('builtins.open', side_effect=OSError('cannot read own proc')):
            with self.assertRaisesRegex(OSError, 'own proc'):
                d.checked_peak(candidate_memory.peak_rss_bytes)

    def test_sources_verify_loaded_paths_and_before_after_bytes(self):
        root = Path(d.__file__).resolve().parents[3]
        before = d.source_pins(root, (v, e, candidate_memory))
        self.assertEqual(set(before), set(d.SOURCE_PINS))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'module.py'; path.write_text('first')
            with patch.object(d, 'SOURCE_PINS', {'module.py': hashlib.sha256(b'first').hexdigest()}):
                d.source_pins(Path(folder), (SimpleNamespace(__file__=str(path)),))
                path.write_text('other')
                with self.assertRaisesRegex(ValueError, 'source changed'):
                    d.source_pins(Path(folder))

    def test_nested_deadline_preserves_outer_absolute_deadline(self):
        handler = signal.getsignal(signal.SIGALRM)
        at = time.monotonic()+2
        with d.deadline(at):
            outer = signal.getsignal(signal.SIGALRM)
            with d.deadline(time.monotonic()+1):
                self.assertIsNot(signal.getsignal(signal.SIGALRM), outer)
            self.assertIs(signal.getsignal(signal.SIGALRM), outer)
            self.assertLessEqual(signal.getitimer(signal.ITIMER_REAL)[0], at-time.monotonic()+0.01)
        self.assertEqual(signal.getsignal(signal.SIGALRM), handler)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))

    def test_fake_full_orchestration_uses_three_calls_and_restores_timer(self):
        # The actual strict task/recovery functions run, with a hand-supplied
        # exact candidate for a synthetic zero-row-coefficient model.
        model = dict(lp=dict(variables=list(range(8)), rows=[
            dict(coefficients=['0']*8, rhs='1', strict=False) for _ in range(28)]))
        models = {o: dict(model=deepcopy(model)) for o in d.MODEL_PINS}
        calls = []
        def native(*args, **kwargs):
            calls.append(kwargs)
            return candidate([0]*8+[1], [0]*29+[-1])
        handler = signal.getsignal(signal.SIGALRM)
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)/'report.json'
            with patch.object(d, 'ENTRY', time.monotonic()), patch.object(d, 'selected_models', return_value=models), \
                 patch.object(d.os, 'sched_getaffinity', return_value={0}), patch.object(d.os, 'sched_setaffinity'), \
                 patch.object(d.resource, 'setrlimit'), patch.object(v, 'linprog', native), \
                 patch.dict(d.os.environ, dict(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1', NUMEXPR_NUM_THREADS='1')), \
                 patch('builtins.print'):
                status = d.main(['--models', 'synthetic-unused', '--output', str(output), '--cpu', '0'])
            report = json.loads(output.read_bytes())
        self.assertEqual(status, 0)
        self.assertEqual(report['status'], 'diagnostic_complete')
        self.assertEqual(len(calls), 3)
        self.assertEqual(report['sources_before'], report['sources_after'])
        self.assertTrue(report['input_verified'])
        self.assertFalse(report['acceptance'])
        self.assertTrue(all(row['diagnostic']['outcome'] == 'exact_candidate_returned' for row in report['models']))
        self.assertTrue(all(0 < call['options']['time_limit'] <= 30 for call in calls))
        self.assertEqual(signal.getsignal(signal.SIGALRM), handler)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))

    def test_exclusive_output_and_byte_cap(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'report.json'
            result = d.write_report(path, dict(test='synthetic'))
            original = path.read_bytes()
            self.assertEqual(result['sha256'], hashlib.sha256(original).hexdigest())
            with self.assertRaises(FileExistsError):
                d.write_report(path, dict(test='replace'))
            self.assertEqual(path.read_bytes(), original)
            other = Path(folder)/'too-big.json'
            with patch.object(d, 'MAX_OUTPUT', 8):
                with self.assertRaisesRegex(ValueError, 'bounded diagnostic output'):
                    d.write_report(other, dict(test='oversized'))
            self.assertFalse(other.exists())


if __name__ == '__main__':
    unittest.main()
