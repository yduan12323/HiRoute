"""Tiny fake/hand-certificate candidate tests; no optimization or real data."""
import base64
from copy import deepcopy
from dataclasses import FrozenInstanceError
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from experiments.time_cut_v2.recorded_real import lp_jobs as jobs
from experiments.time_cut_v2.recorded_real import lp_worker as worker


VERSIONS = dict(python='test', numpy='test', scipy='test')
METRICS = dict(versions=VERSIONS, cpu_seconds=0., wall_seconds=0., pass_count=0, peak_rss_bytes=0)
STAGE = dict(name='feasibility', task=dict(c=['0'], A=[], b=[], equalities=[]),
             certificate=dict(status='infeasible', constant_constraints_verified=True))


def make_fixture(root):
    model = dict(exclusion=None, lp=dict(variables=['x'], rows=[
        dict(coefficients=['-1'], rhs='0', strict=False)],
        J=dict(coefficients=['0'], constant='0'), Q=dict(coefficients=['0'], constant='0')),
        H=1, pi=[])
    model_sha = jobs.digest(model)
    rows = [dict(selection_position=i, model=model, model_sha256=model_sha) for i in range(256)]
    raw = jobs.canonical(rows) + b'\n'
    path = Path(root) / 'model-payloads.json'
    path.write_bytes(raw)
    population = jobs.make_jobs(model_payloads_path=path, model_payloads_sha256=hashlib.sha256(raw).hexdigest(),
        model_payloads_size_bytes=len(raw), model_sha256s=[model_sha] * 8, context_sha256='b' * 64)
    return population, model


def frames(job, stages=None, result=None):
    stages = [deepcopy(STAGE)] if stages is None else stages
    result = dict(status='closed_infeasible') if result is None else result
    def frame(kind, **value):
        return dict(schema=jobs.FRAME_SCHEMA, job=job.to_dict(), kind=kind, **value)
    return [frame('started', metrics=METRICS)] + [frame('stage', stage_index=i, stage=stage)
        for i, stage in enumerate(stages)] + [frame('final', status='complete', stage_count=len(stages),
        stage_sha256s=[jobs.digest(s) for s in stages], result=result, reason=None, metrics=METRICS)]


def wire(rows):
    return b''.join(jobs.canonical(row) + b'\n' for row in rows)


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.population, self.model = make_fixture(self.temp.name)
        self.job = self.population[0]

    def test_frozen_fixed_complete_job_identity(self):
        self.assertEqual([j.preview_position for j in self.population], list(jobs.POSITIONS))
        self.assertEqual(jobs.LPJob.from_dict(self.job.to_dict()), self.job)
        with self.assertRaises(FrozenInstanceError):
            self.job.model_sha256 = 'e' * 64
        for key, value in [('context_sha256', 'e' * 64), ('model_payloads_sha256', 'e' * 64),
                           ('preview_position', 1), ('calibration_index', True)]:
            raw = self.job.to_dict()
            raw[key] = value
            with self.assertRaises(ValueError):
                jobs.LPJob.from_dict(raw)
        raw = self.job.to_dict()
        raw['limits']['max_passes'] = 13
        with self.assertRaises(ValueError):
            jobs.LPJob.from_dict(raw)

    def test_every_frame_checks_whole_identity(self):
        for index in range(3):
            values = frames(self.job)
            values[index]['job']['context_sha256'] = 'e' * 64
            reader = jobs.FrameReader(self.job)
            reader.feed(wire(values))
            self.assertIn('identity', reader.finish())

    def test_missing_extra_duplicate_and_out_of_order_stages(self):
        valid = frames(self.job)
        cases = [valid[:1] + valid[2:], valid[:2] + valid[1:], valid + valid[1:2]]
        extra = deepcopy(valid)
        extra[1]['stage_index'] = 1
        cases.append(extra)
        incomplete = frames(self.job, [], dict(status='attained_optimum'))
        cases.append(incomplete)
        for values in cases:
            reader = jobs.FrameReader(self.job)
            reader.feed(wire(values))
            self.assertIsNotNone(reader.finish())
        reader = jobs.FrameReader(self.job)
        raw = wire(valid)
        for byte in raw:
            reader.feed(bytes([byte]))
        self.assertIsNone(reader.finish())
        self.assertEqual(reader.stages, [STAGE])

    def test_truncated_and_duplicate_json_are_unresolved(self):
        reader = jobs.FrameReader(self.job)
        reader.feed(wire(frames(self.job)[:2]) + b'{"schema":')
        self.assertIn('truncated', reader.finish())
        self.assertEqual(reader.stages, [STAGE])
        reader = jobs.FrameReader(self.job)
        reader.feed(b'{"x":1,"x":2}\n')
        self.assertIn('duplicate JSON', reader.finish())

    def test_input_file_and_selected_model_hash_pins(self):
        self.assertEqual(worker.load_model(self.job), self.model)
        path = Path(self.job.model_payloads_path)
        path.write_bytes(path.read_bytes().replace(b'"x"', b'"z"', 1))
        with self.assertRaisesRegex(ValueError, 'SHA'):
            worker.load_model(self.job)
        self.population, _ = make_fixture(self.temp.name)
        row = self.population[0].to_dict()
        row['model_sha256'] = 'e' * 64
        row.pop('schema'); row.pop('limits'); row.pop('job_sha256')
        with self.assertRaisesRegex(ValueError, 'selected model SHA'):
            worker.load_model(jobs.LPJob(**row))

    def test_hand_certificates_use_unchanged_solver(self):
        from fractions import Fraction as F
        from validation.suffix5 import solver, vendor_lp
        def exact(c, A, b, equalities):
            slack = c[-1] == -1
            x = [F(0)] * len(c)
            y = [F(0)] * len(A)
            if slack:
                x[-1], y[-1] = F(1), F(-1)
            certificate = dict(status='optimal', x=x, objective=F(-1) if slack else F(0),
                               inequality_dual=y, equality_dual=[F(0)] * len(equalities))
            vendor_lp.verify_certificate(c, A, b, equalities, certificate)
            return certificate
        output = []
        with patch.object(vendor_lp, 'exact_lp', exact), patch.object(vendor_lp, 'linprog',
                side_effect=AssertionError('no numerical optimizer in tiny tests')):
            worker.execute_candidate(self.job, deadline_monotonic=time.monotonic() + 10,
                emit=output.append, solve=solver.solve_model, budget_factory=solver.SolveBudget,
                versions=VERSIONS)
        reader = jobs.FrameReader(self.job)
        reader.feed(wire(output))
        self.assertIsNone(reader.finish())
        self.assertEqual(reader.final['result']['status'], 'attained_optimum')
        self.assertEqual(len(reader.stages), 5)
        self.assertEqual(reader.final['metrics']['pass_count'], 0)

    def test_highs_threads_preserve_options_without_optimization(self):
        from validation.suffix5 import solver, vendor_lp
        calls = []
        def fake_solve(model, budget, on_stage):
            budget.tick()
            vendor_lp.linprog('hand candidate', options={'primal_feasibility_tolerance': 1e-9,
                'dual_feasibility_tolerance': 1e-9})
            return dict(model=model, stages=[], result=dict(status='graph_unreachable'))
        with patch.object(solver, 'solve_model', fake_solve), patch.object(vendor_lp, 'linprog',
                side_effect=lambda *a, **kw: calls.append(kw)):
            output = []
            worker.execute_candidate(self.job, deadline_monotonic=time.monotonic() + 10, emit=output.append)
        self.assertEqual(calls[0]['options'], dict(threads=1, primal_feasibility_tolerance=1e-9,
                                                   dual_feasibility_tolerance=1e-9))
        self.assertEqual(output[-1]['metrics']['pass_count'], 1)

    def test_partial_stages_survive_candidate_failure(self):
        from validation.suffix5.solver import SolveBudget
        def fail(model, budget, on_stage):
            on_stage(deepcopy(STAGE))
            raise ArithmeticError('uncertified candidate')
        output = []
        worker.execute_candidate(self.job, deadline_monotonic=time.monotonic() + 10,
            emit=output.append, solve=fail, budget_factory=SolveBudget, versions=VERSIONS)
        reader = jobs.FrameReader(self.job)
        reader.feed(wire(output))
        self.assertIsNone(reader.finish())
        self.assertEqual(reader.final['status'], 'unresolved')
        self.assertEqual(reader.stages, [STAGE])
        self.assertIsNone(reader.final['result'])

    def test_candidate_import_fence(self):
        fence = worker.CandidateFence()
        for name in ('timecut5', 'timecut5.solver', 'validation.reference5', 'validation.reference5.lp'):
            with self.assertRaises(ImportError):
                fence.find_spec(name)
        self.assertIsNone(fence.find_spec('validation.suffix5.solver'))


@unittest.skipUnless(hasattr(os, 'sched_getaffinity') and len(os.sched_getaffinity(0)) >= 4,
                     'four Linux CPUs required for bounded subprocess tests')
class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.population, _ = make_fixture(self.temp.name)
        self.cpus = tuple(sorted(os.sched_getaffinity(0))[:4])

    def command(self, payload=None, script=None):
        def command(job, cpu, deadline):
            raw = wire(frames(job, [], dict(status='graph_unreachable'))) if payload is None else payload(job)
            source = script or 'import os,sys; os.write(1,bytes.fromhex(sys.argv[1]))'
            return [sys.executable, '-B', '-c', source, raw.hex(), str(cpu), repr(deadline)]
        return command

    def assert_reaped(self, outcome):
        self.assertTrue(outcome['child_reaped'])
        with self.assertRaises(ChildProcessError):
            os.waitpid(outcome['pid'], os.WNOHANG)

    def test_completed_jobs_and_main_thread_callback(self):
        callbacks = []
        with patch.object(jobs, '_command', self.command()):
            result = jobs.run_jobs(self.population, cpus=self.cpus, deadline_monotonic=time.monotonic() + 5,
                on_result=lambda r: callbacks.append((r['job']['calibration_index'], threading.get_ident())))
        self.assertEqual(len(callbacks), 8)
        self.assertTrue(all(t == threading.get_ident() for _, t in callbacks))
        self.assertEqual([r['status'] for r in result], ['complete'] * 8)
        for outcome in result:
            self.assert_reaped(outcome)

    @unittest.skipUnless(len(os.sched_getaffinity(0)) >= 5, 'five distinct CPUs required')
    def test_collector_inherits_full_mask_before_main_thread_narrows(self):
        inherited = os.sched_getaffinity(0)
        coordinator = next(cpu for cpu in sorted(inherited) if cpu not in self.cpus)
        observed = []
        native = jobs.subprocess.Popen
        def spawn(*args, **kwargs):
            observed.append(os.sched_getaffinity(0))
            return native(*args, **kwargs)
        try:
            with patch.object(jobs, '_command', self.command()), patch.object(jobs.subprocess, 'Popen', spawn):
                result = jobs.run_jobs(self.population, cpus=self.cpus,
                    coordinator_cpu=coordinator, deadline_monotonic=time.monotonic() + 5,
                    on_result=lambda row: self.assertEqual(os.sched_getaffinity(0), {coordinator}))
            self.assertEqual(len(observed), 8)
            self.assertTrue(all(mask == inherited for mask in observed))
            self.assertTrue(all(row['child_reaped'] for row in result))
        finally:
            os.sched_setaffinity(0, inherited)

    def test_parent_deadline_includes_startup_and_reaps(self):
        script = 'import os,sys,time; os.write(1,bytes.fromhex(sys.argv[1])); time.sleep(10)'
        deadline = time.monotonic() + .18
        with patch.object(jobs, '_command', self.command(script=script)):
            result = jobs.run_jobs(self.population, cpus=self.cpus, deadline_monotonic=deadline)
        self.assertLess(time.monotonic() - deadline, .8)
        self.assertTrue(all(r['status'] == 'unresolved' for r in result))
        live = [r for r in result if r['pid'] is not None]
        self.assertEqual(len(live), 4)
        self.assertTrue(all(r['deadline_monotonic'] == deadline for r in live))
        for outcome in live:
            self.assert_reaped(outcome)
            self.assertIsNone(outcome['result'])

    def test_expired_deadline_launches_nothing(self):
        with patch.object(jobs.subprocess, 'Popen', side_effect=AssertionError('expired launch')):
            result = jobs.run_jobs(self.population, cpus=self.cpus, deadline_monotonic=time.monotonic())
        self.assertEqual(len(result), 8)
        self.assertTrue(all(r['pid'] is None and r['status'] == 'unresolved' for r in result))

    def test_stdout_and_stderr_byte_caps(self):
        for name, fd, cap in [('stdout', 1, jobs.STDOUT_BYTES), ('stderr', 2, jobs.STDERR_BYTES)]:
            script = ('import os,time; chunk=b"x"*65536\n'
                      'for i in range(40): os.write(' + str(fd) + ',chunk)\n'
                      'time.sleep(10)')
            # For stdout use no newline so its cap is reached before framing fails.
            with patch.object(jobs, '_command', self.command(script=script)):
                result = jobs.run_jobs(self.population, cpus=self.cpus, deadline_monotonic=time.monotonic() + 5)
            for outcome in result:
                self.assertEqual(outcome['status'], 'unresolved')
                self.assertTrue(outcome[name + '_truncated'])
                self.assertEqual(len(base64.b64decode(outcome[name + '_base64'])), cap)
                self.assert_reaped(outcome)

    def test_malformed_preserves_bounded_partial_and_continues_all_jobs(self):
        def payload(job):
            return wire(frames(job)[:2]) + b'not-json\n'
        with patch.object(jobs, '_command', self.command(payload=payload)):
            result = jobs.run_jobs(self.population, cpus=self.cpus, deadline_monotonic=time.monotonic() + 5)
        self.assertEqual(len(result), 8)
        for outcome in result:
            self.assertEqual(outcome['stages'], [STAGE])
            self.assertIn('malformed', outcome['reason'])
            self.assertTrue(base64.b64decode(outcome['stdout_base64']).endswith(b'not-json\n'))
            self.assert_reaped(outcome)

    def test_collector_enforces_deadline_while_callback_blocks(self):
        def command(job, cpu, deadline):
            raw = wire(frames(job, [], dict(status='graph_unreachable')))
            script = 'import os,sys,time; os.write(1,bytes.fromhex(sys.argv[1]));'
            if job.calibration_index:
                script += 'time.sleep(10)'
            return [sys.executable, '-B', '-c', script, raw.hex()]
        seen = []
        def callback(outcome):
            seen.append(outcome)
            if len(seen) == 1:
                time.sleep(.3)
        with patch.object(jobs, '_command', command), patch.object(jobs, 'LP_SECONDS', .12):
            result = jobs.run_jobs(self.population, cpus=self.cpus, deadline_monotonic=time.monotonic() + 2,
                                   on_result=callback)
        self.assertEqual(result[0]['status'], 'complete')
        for outcome in result[1:]:
            self.assertEqual(outcome['status'], 'unresolved')
            self.assertAlmostEqual(outcome['deadline_monotonic'] - outcome['started_monotonic'], .12)
            self.assertLess(outcome['collected_monotonic'] - outcome['deadline_monotonic'], .2)
            self.assert_reaped(outcome)

    def test_callback_exception_reaps_children(self):
        def stop(outcome):
            raise RuntimeError('callback stopped')
        children = []
        native = jobs.subprocess.Popen
        def spawn(*args, **kwargs):
            self.assertFalse(kwargs['start_new_session'])
            self.assertNotIn('preexec_fn', kwargs)
            self.assertTrue(all(kwargs['env'][name] == '1' for name in jobs.THREAD_ENV))
            child = native(*args, **kwargs)
            children.append(child)
            return child
        with patch.object(jobs, '_command', self.command()), patch.object(jobs.subprocess, 'Popen', spawn):
            with self.assertRaisesRegex(RuntimeError, 'callback stopped'):
                jobs.run_jobs(self.population, cpus=self.cpus, deadline_monotonic=time.monotonic() + 5,
                              on_result=stop)
        self.assertTrue(all(c.poll() is not None for c in children))


if __name__ == '__main__':
    unittest.main()
