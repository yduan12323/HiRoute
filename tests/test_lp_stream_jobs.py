"""Small fake/hand-certificate tests. Never invoke a numerical optimizer."""
import base64
from copy import deepcopy
import hashlib
import io
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from experiments.time_cut_v2.recorded_real import lp_stream_jobs as stream
from experiments.time_cut_v2.recorded_real import lp_stream_worker as worker
from experiments.time_cut_v2.recorded_real import lp_jobs as old

METRICS = dict(versions=dict(python='test', numpy='test', scipy='test'), cpu_seconds=0.,
    wall_seconds=0., pass_count=0, peak_rss_bytes=0, rss_source=old.RSS_SOURCE,
    rusage_peak_rss_bytes=0)


def job(ordinal=0):
    model = dict(exclusion='graph_unreachable', ordinal=ordinal)
    return stream.LPStreamJob(dict(source='tiny-fixture'), ordinal // 256, ordinal,
                              old.digest(model), model)


def frames(value, generation):
    header = value.header(generation)
    def frame(kind, **kw):
        return dict(schema=stream.FRAME_SCHEMA, job=header, kind=kind, **kw)
    return [frame('started', metrics=METRICS), frame('final', status='complete',
        stage_count=0, stage_sha256s=[], result=dict(status='graph_unreachable'),
        reason=None, metrics=METRICS), frame('done')]


def wire(rows):
    return b''.join(old.canonical(row) + b'\n' for row in rows)


FAKE = r'''
import os,sys,time
from experiments.time_cut_v2.recorded_real.lp_stream_jobs import *
os.sched_setaffinity(0,{int(sys.argv[1])})
generation=sys.argv[2]
mode=sys.argv[3]
count=0
for raw in sys.stdin.buffer:
    request=decode(raw)
    job=LPStreamJob.from_dict(request['job'])
    header=job.header(generation)
    count+=1
    if mode=='sleep' and job.model_ordinal:
        time.sleep(10)
    if mode=='timeout_restart' and job.model_ordinal==0:
        time.sleep(10)
    if mode=='restart' and job.model_ordinal==0:
        os.write(1,b'not-json\n')
        time.sleep(10)
    if mode=='restart' and job.model_ordinal and os.environ.get('HIROUTE_FAKE_RESTART_RELEASE'):
        while not os.path.exists(os.environ['HIROUTE_FAKE_RESTART_RELEASE']):
            time.sleep(.005)
    if mode in ('stdout','stderr'):
        fd=1 if mode=='stdout' else 2
        for _ in range(40):os.write(fd,b'x'*65536)
        time.sleep(10)
    metrics=dict(versions=dict(python='test',numpy='test',scipy='test'),cpu_seconds=0.,
        wall_seconds=0.,pass_count=0,peak_rss_bytes=0,rss_source=RSS_SOURCE,rusage_peak_rss_bytes=0)
    result=dict(status='graph_unreachable',pid=os.getpid(),count=count,
        affinity=sorted(os.sched_getaffinity(0)),pgid=os.getpgrp())
    def emit(kind,**kw):
        os.write(1,canonical(dict(schema=FRAME_SCHEMA,job=header,kind=kind,**kw))+b'\n')
    emit('started',metrics=metrics)
    if mode=='missing':
        sys.exit(0)
    if mode=='wronghash':header['input_sha256']='f'*64
    emit('final',status='complete',stage_count=0,stage_sha256s=[],result=result,
         reason=None,metrics=metrics)
    emit('done')
    if mode=='duplicate':emit('done')
    if mode=='trailing':os.write(1,b'x\n')
    if mode=='partial_trailing':os.write(1,b'{')
    if mode=='late':
        time.sleep(.03)
        os.write(1,b'x\n')
    if mode=='shutdown_hang':
        time.sleep(10)
'''


REAL_WORKER_FAKE_SOLVER = r'''
import importlib,os,resource,sys
from experiments.time_cut_v2.recorded_real import lp_stream_worker as worker
sys.path.insert(0,sys.argv[1])
del sys.argv[1]
class Budget:
    passes=0
    def __init__(self,**kw):pass
    def check(self):pass
def solve(model,budget,on_stage):
    cached=importlib.import_module('lp_import_marker')
    return dict(model=model,stages=[],result=dict(status='graph_unreachable',
        token=id(cached.token),imports=cached.imports,pid=os.getpid(),
        as_limit=list(resource.getrlimit(resource.RLIMIT_AS)),
        core_limit=list(resource.getrlimit(resource.RLIMIT_CORE))))
original=worker.serve
def serve(generation):
    return original(generation,solve=solve,budget_factory=Budget,
                    versions=dict(python='test',numpy='test',scipy='test'))
worker.serve=serve
worker.main()
'''


class IdentityTests(unittest.TestCase):
    def test_frozen_nested_inputs_and_compact_identity(self):
        source, model = {'source': {'revision': 'a'}}, {'payload': ['x']}
        value = stream.LPStreamJob(source, 0, 3, old.digest(model), model)
        frozen = value.input_bytes
        source['source']['revision'] = 'b'
        model['payload'].append('y')
        value.model['payload'].append('z')
        value.source_context['source']['revision'] = 'c'
        self.assertEqual(value.input_bytes, frozen)
        self.assertEqual(stream.LPStreamJob.from_dict(value.to_dict()), value)
        header = value.header('a' * 32)
        self.assertNotIn('model', header)
        self.assertEqual(header['input_sha256'], hashlib.sha256(frozen).hexdigest())
        altered = value.to_dict()
        altered['limits']['max_passes'] += 1
        with self.assertRaisesRegex(ValueError, 'canonical'):
            stream.LPStreamJob.from_dict(altered)
        for block, ordinal in [(True, 0), (0, True), (-1, 0), (0, -1)]:
            with self.assertRaises(ValueError):
                stream.LPStreamJob({}, block, ordinal, old.digest({}), {})

    def test_reader_reuses_strict_candidate_validation(self):
        value, generation = job(), 'a' * 32
        rows = frames(value, generation)
        for mutation in ('missing', 'duplicate', 'hash', 'generation', 'stage', 'trailing'):
            bad = deepcopy(rows)
            if mutation == 'missing':bad.pop(1)
            if mutation == 'duplicate':bad.append(bad[-1])
            if mutation == 'hash':bad[1]['job']['input_sha256'] = 'b' * 64
            if mutation == 'generation':bad[1]['job']['generation'] = 'b' * 32
            if mutation == 'stage':bad[1]['stage_count'] = 1
            raw = wire(bad) + (b'{' if mutation == 'trailing' else b'')
            reader = stream.StreamFrameReader(value, generation)
            reader.feed(raw)
            self.assertIsNotNone(reader.finish(), mutation)
        reader = stream.StreamFrameReader(value, generation)
        for byte in wire(rows):reader.feed(bytes([byte]))
        self.assertIsNone(reader.finish())

    def test_worker_executes_twice_through_loader_without_optimizer(self):
        class Budget:
            passes = 0
            def __init__(self, **kw):
                self.kw = kw
            def check(self):pass
        seen = []
        def solve(model, budget, on_stage):
            seen.append(model)
            return dict(model=model, stages=[], result=dict(status='graph_unreachable'))
        values = [job(0), job(5)]
        source = io.BytesIO(b''.join(stream.request_bytes(v, 'a' * 32,
                            time.monotonic() + 10) for v in values))
        output = io.BytesIO()
        worker.serve('a' * 32, source=source, output=output, solve=solve,
                     budget_factory=Budget, versions=METRICS['versions'])
        self.assertEqual(seen, [v.model for v in values])
        self.assertEqual(len(output.getvalue().splitlines()), 6)

    def test_worker_refuses_retained_high_water(self):
        source = io.BytesIO(stream.request_bytes(job(), 'a' * 32, time.monotonic() + 5))
        with patch.object(worker, 'peak_rss_bytes', return_value=old.SOFT_RSS_MIB * 1024**2 + 1):
            with self.assertRaisesRegex(ValueError, 'retained RSS'):
                worker.serve('a' * 32, source=source, output=io.BytesIO())

    def test_two_five_stage_hand_certificates_through_stream_loader(self):
        from fractions import Fraction as F
        from validation.suffix5 import solver, vendor_lp
        model = dict(exclusion=None, lp=dict(variables=['x'], rows=[
            dict(coefficients=['-1'], rhs='0', strict=False)],
            J=dict(coefficients=['0'], constant='0'),
            Q=dict(coefficients=['0'], constant='0')), H=1, pi=[])
        values = [stream.LPStreamJob({}, 0, i, old.digest(model), model) for i in (0, 5)]
        def exact(c, A, b, equalities):
            slack = c[-1] == -1
            x, y = [F(0)] * len(c), [F(0)] * len(A)
            if slack:x[-1], y[-1] = F(1), F(-1)
            certificate = dict(status='optimal', x=x, objective=F(-1) if slack else F(0),
                inequality_dual=y, equality_dual=[F(0)] * len(equalities))
            vendor_lp.verify_certificate(c, A, b, equalities, certificate)
            return certificate
        output = io.BytesIO()
        source = io.BytesIO(b''.join(stream.request_bytes(v, 'a' * 32,
                             time.monotonic() + 5) for v in values))
        with patch.object(vendor_lp, 'exact_lp', exact), \
             patch.object(vendor_lp, 'linprog', side_effect=AssertionError('no optimizer')):
            worker.serve('a' * 32, source=source, output=output, solve=solver.solve_model,
                         budget_factory=solver.SolveBudget, versions=METRICS['versions'])
        rows = output.getvalue().splitlines(keepends=True)
        self.assertEqual(len(rows), 16)
        for i, value in enumerate(values):
            reader = stream.StreamFrameReader(value, 'a' * 32)
            reader.feed(b''.join(rows[8*i:8*(i+1)]))
            self.assertIsNone(reader.finish())
            self.assertEqual(reader.final['result']['status'], 'attained_optimum')
            self.assertEqual(len(reader.stages), 5)
            self.assertEqual(reader.final['metrics']['pass_count'], 0)


@unittest.skipUnless(hasattr(os, 'sched_getaffinity') and len(os.sched_getaffinity(0)) >= 4,
                     'four Linux CPUs required')
class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.cpus = tuple(sorted(os.sched_getaffinity(0))[:4])
        self.children = []
        self.native = stream.subprocess.Popen

    def command(self, mode='normal'):
        return lambda cpu, generation: [sys.executable, '-B', '-c', FAKE,
                                       str(cpu), generation, mode]

    def spawn(self, *args, **kwargs):
        self.assertFalse(kwargs['start_new_session'])
        self.assertNotIn('preexec_fn', kwargs)
        child = self.native(*args, **kwargs)
        self.children.append(child)
        return child

    def run_stream(self, values, mode='normal', callback=None, duration=5, **kw):
        with patch.object(stream, '_command', self.command(mode)), \
             patch.object(stream.subprocess, 'Popen', self.spawn):
            return stream.iter_results(values, cpus=self.cpus,
                deadline_monotonic=time.monotonic() + duration, on_result=callback,
                max_jobs=100, max_input_bytes=2**24, **kw)

    def assert_reaped(self):
        for child in self.children:
            self.assertIsNotNone(child.poll())
            with self.assertRaises(ChildProcessError):os.waitpid(child.pid, os.WNOHANG)

    def test_persistent_workers_ordered_digest_and_main_thread_callbacks(self):
        values = [job(i) for i in (0, 2, 7, 256, 257, 600, 900, 1000, 1001, 1002)]
        results = []
        def callback(row):
            self.assertEqual(threading.current_thread(), threading.main_thread())
            results.append(row)
        summary = self.run_stream(iter(values), callback=callback)
        self.assertEqual(summary['status'], 'complete', summary)
        self.assertEqual(summary['submitted_count'], len(values))
        self.assertEqual(summary['ordered_input_sha256'],
                         hashlib.sha256(b''.join(v.input_bytes + b'\n' for v in values)).hexdigest())
        self.assertEqual(summary['spawned_processes'], 4)
        self.assertTrue(any(r['result']['count'] > 1 for r in results))
        for row in results:
            self.assertEqual(row['result']['affinity'], [row['cpu']])
            self.assertEqual(row['result']['pgid'], os.getpgrp())
        self.assert_reaped()

    def test_real_worker_entrypoint_reuses_imports_with_hard_limits(self):
        rows = []
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'lp_import_marker.py').write_text(
                'import builtins\n'
                'builtins._lp_marker_count = getattr(builtins, "_lp_marker_count", 0) + 1\n'
                'imports = builtins._lp_marker_count\n'
                'token = object()\n')
            def command(cpu, generation):
                return [sys.executable, '-B', '-c', REAL_WORKER_FAKE_SOLVER, directory,
                        '--cpu', str(cpu), '--generation', generation]
            with patch.object(stream, '_command', command), \
                 patch.object(stream.subprocess, 'Popen', self.spawn):
                summary = stream.iter_results([job(i) for i in range(12)], cpus=self.cpus,
                    deadline_monotonic=time.monotonic() + 5, on_result=rows.append,
                    max_jobs=12, max_input_bytes=2**24)
        self.assertEqual(summary['status'], 'complete', summary)
        self.assertEqual(summary['complete_count'], 12, [r['reason'] for r in rows])
        self.assertEqual(summary['spawned_processes'], 4)
        tokens = {}
        for row in rows:
            result = row['result']
            self.assertEqual(result['imports'], 1)
            self.assertEqual(result['as_limit'], [old.CHILD_AS_BYTES] * 2)
            self.assertEqual(result['core_limit'], [0, 0])
            tokens.setdefault(row['pid'], set()).add(result['token'])
        self.assertTrue(all(len(value) == 1 for value in tokens.values()))
        self.assert_reaped()

    def test_closeable_iterator_releases_credit_only_after_resume(self):
        produced = []
        def inputs():
            for i in range(12):
                produced.append(i)
                yield job(i)
        with patch.object(stream, '_command', self.command()), \
             patch.object(stream.subprocess, 'Popen', self.spawn):
            with stream.stream_results(inputs(), cpus=self.cpus,
                    deadline_monotonic=time.monotonic() + 5,
                    max_jobs=12, max_input_bytes=2**24) as results:
                next(results)
                time.sleep(.08)
                self.assertEqual(len(produced), 4)
                self.assertIsNone(results.summary)
                next(results)
                self.assertEqual(len(produced), 5)
            self.assertIsNone(results.summary)
        self.assert_reaped()

    def test_iterator_summary_requires_exhaustion_and_clean_shutdown(self):
        with patch.object(stream, '_command', self.command()):
            with stream.stream_results([job(i) for i in range(4)], cpus=self.cpus,
                    deadline_monotonic=time.monotonic() + 5,
                    max_jobs=4, max_input_bytes=2**24) as results:
                for row in results:
                    self.assertIsNone(results.summary)
                self.assertEqual(results.summary['status'], 'complete')
                self.assertEqual(results.summary['terminal_count'], 4)
                self.assertTrue(results.summary['all_processes_reaped'])
        summary = self.run_stream([job(0)], 'shutdown_hang', duration=.25)
        self.assertEqual(summary['status'], 'unresolved')
        self.assertTrue(summary['all_processes_reaped'])
        self.assert_reaped()

    def test_only_four_input_credits_while_callback_blocked(self):
        produced, rows = [], []
        def inputs():
            for i in range(12):
                produced.append(i)
                yield job(i)
        def callback(row):
            if not rows:
                time.sleep(.12)
                self.assertEqual(produced, [0, 1, 2, 3])
            rows.append(row)
        self.assertEqual(self.run_stream(inputs(), callback=callback)['status'], 'complete')
        self.assert_reaped()

    def test_callback_exception_reaps_every_child(self):
        def fail(row):raise RuntimeError('checking failed')
        with self.assertRaisesRegex(RuntimeError, 'checking failed'):
            self.run_stream((job(i) for i in range(10)), callback=fail)
        self.assert_reaped()

    def test_malformed_job_restarts_generation_and_continues(self):
        rows = []
        # Hold the other initial credits until the malformed disposition has
        # returned. Otherwise those workers can legitimately exhaust all input
        # before the failed slot gets another job, making a restart assertion
        # depend on interpreter startup order rather than the protocol.
        with tempfile.TemporaryDirectory() as directory:
            release = Path(directory) / 'release'
            def callback(row):
                rows.append(row)
                if row['job']['model_ordinal'] == 0:release.write_bytes(b'go')
            with patch.dict(os.environ, {'HIROUTE_FAKE_RESTART_RELEASE': str(release)}):
                summary = self.run_stream([job(i) for i in range(12)], 'restart', callback)
        self.assertEqual(summary['terminal_count'], 12)
        failed = next(row for row in rows if row['job']['model_ordinal'] == 0)
        self.assertEqual(failed['status'], 'unresolved')
        later = [r for r in rows if r['cpu'] == failed['cpu'] and r is not failed]
        self.assertTrue(later)
        self.assertTrue(all(r['generation'] != failed['generation'] for r in later))
        self.assertTrue(all(r['status'] == 'complete' for r in rows if r is not failed))
        self.assert_reaped()

    def test_missing_duplicate_foreign_and_trailing_frames_fail_closed(self):
        for mode in ('missing', 'duplicate', 'wronghash', 'trailing', 'partial_trailing', 'late'):
            rows = []
            def callback(row):
                rows.append(row)
                if mode == 'late':time.sleep(.08)
            summary = self.run_stream([job(i) for i in range(4)], mode, callback)
            self.assertTrue(summary['unresolved_count'] or summary['status'] == 'unresolved',
                            (mode, summary))
            self.assert_reaped()

    def test_bounded_stdout_and_stderr(self):
        for mode, cap in [('stdout', old.STDOUT_BYTES), ('stderr', old.STDERR_BYTES)]:
            rows = []
            summary = self.run_stream([job(i) for i in range(4)], mode, rows.append)
            self.assertEqual(summary['unresolved_count'], 4)
            for row in rows:
                self.assertEqual(len(base64.b64decode(row[mode + '_base64'])), cap)
                self.assertTrue(row[mode + '_truncated'])
            self.assert_reaped()

    def test_external_deadline_runs_during_callback(self):
        rows = []
        def callback(row):
            rows.append(row)
            if len(rows) == 1:time.sleep(.45)
        summary = self.run_stream([job(i) for i in range(4)], 'sleep', callback, duration=.3)
        self.assertEqual(summary['terminal_count'], 4)
        self.assertEqual(rows[0]['status'], 'complete')
        for row in rows[1:]:
            self.assertEqual(row['status'], 'unresolved')
            self.assertLess(row['collected_monotonic'] - row['deadline_monotonic'], .15)
        self.assert_reaped()

    def test_per_model_timeout_restarts_without_resetting_global_deadline(self):
        values, rows = [job(i) for i in range(12)], []
        def callback(row):
            rows.append(row)
            if len(rows) == 1:time.sleep(1.5)
        # Keep interpreter startup inside the limit, including optimized mode.
        # The callback still blocks longer than the complete per-model budget.
        with patch.object(stream, 'LP_SECONDS', 1.0):
            summary = self.run_stream(values, 'timeout_restart', callback, duration=6)
        self.assertEqual(summary['terminal_count'], 12)
        failed = next(r for r in rows if r['job']['model_ordinal'] == 0)
        self.assertEqual(failed['status'], 'unresolved')
        self.assertAlmostEqual(failed['deadline_monotonic'] - failed['started_monotonic'], 1.0)
        self.assertLess(failed['collected_monotonic'] - failed['deadline_monotonic'], .15)
        later = [r for r in rows if r['cpu'] == failed['cpu'] and r is not failed]
        self.assertTrue(later)
        self.assertTrue(all(r['generation'] != failed['generation'] for r in later))
        self.assertEqual(summary['complete_count'], 11)
        self.assert_reaped()

    def test_input_caps_and_invalid_order_cleanup(self):
        for values in ([job(2), job(1)], [job(0), job(0)]):
            with self.assertRaisesRegex(ValueError, 'increasing'):
                self.run_stream(values)
            self.assert_reaped()
        with self.assertRaisesRegex(ValueError, 'job count'):
            with patch.object(stream, '_command', self.command()):
                stream.iter_results([job(i) for i in range(5)], cpus=self.cpus,
                    deadline_monotonic=time.monotonic() + 5, max_jobs=4,
                    max_input_bytes=2**24)
        with self.assertRaisesRegex(ValueError, 'input bytes'):
            stream.iter_results([job()], cpus=self.cpus,
                deadline_monotonic=time.monotonic() + 5, max_jobs=4, max_input_bytes=1)

    @unittest.skipUnless(len(os.sched_getaffinity(0)) >= 5, 'five Linux CPUs required')
    def test_coordinator_narrowing_keeps_collector_inherited_mask(self):
        inherited = os.sched_getaffinity(0)
        coordinator = next(c for c in sorted(inherited) if c not in self.cpus)
        observed = []
        native_spawn = self.spawn
        def spawn(*a, **kw):
            observed.append(os.sched_getaffinity(0))
            return native_spawn(*a, **kw)
        try:
            with patch.object(stream, '_command', self.command()), \
                 patch.object(stream.subprocess, 'Popen', spawn):
                summary = stream.iter_results([job(i) for i in range(8)], cpus=self.cpus,
                    coordinator_cpu=coordinator, deadline_monotonic=time.monotonic() + 5,
                    max_jobs=8, max_input_bytes=2**24,
                    on_result=lambda row:self.assertEqual(os.sched_getaffinity(0), {coordinator}))
            self.assertEqual(summary['status'], 'complete')
            self.assertTrue(all(mask == inherited for mask in observed))
        finally:
            os.sched_setaffinity(0, inherited)
        self.assert_reaped()


if __name__ == '__main__':
    unittest.main()
