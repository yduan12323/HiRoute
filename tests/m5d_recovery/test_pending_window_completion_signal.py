"""Real SIGINT/SIGTERM polling and owned-cleanup checks; tiny subprocesses only."""
import json
import os
from pathlib import Path
import selectors
import signal
import sys
import tempfile
import unittest
from unittest.mock import patch

from experiments.mechanism_recovery_v1 import supervisor


class PollSignalProxy:
    """Deliver a real OS signal inside EpollSelector's protected poll call.

    This makes the old InterruptedError-swallowing bug deterministic, while
    the owned worker is a real process. Other epoll operations stay unchanged.
    """
    def __init__(self,backend,signum):
        self.backend=backend;self.signum=signum;self.delivered=False

    def __getattr__(self,name):return getattr(self.backend,name)

    def poll(self,*args):
        if not self.delivered:
            self.delivered=True;os.kill(os.getpid(),self.signum)
        return self.backend.poll(*args)


class CompletionSignalTests(unittest.TestCase):
    def test_cancellation_exception_is_not_a_selector_eintr(self):
        self.assertTrue(issubclass(supervisor.SupervisorCancellation,RuntimeError))
        self.assertFalse(issubclass(supervisor.SupervisorCancellation,OSError))
        self.assertFalse(issubclass(supervisor.SupervisorCancellation,InterruptedError))

    def test_both_signals_during_poll_fail_closed_and_clean_owned_worker(self):
        cpu=min(os.sched_getaffinity(0))
        # Without the fix the protected EpollSelector call swallows cancellation,
        # and this worker returns a SUCCESS receipt. That outcome must fail QA.
        code=("import os,json,time;time.sleep(.15);"
              "json.dump({'status':'SUCCESS'},open(os.environ['HIROUTE_WORKER_RECEIPT'],'w'))")
        for signum in (signal.SIGINT,signal.SIGTERM):
            with self.subTest(signal=signum),tempfile.TemporaryDirectory() as temp:
                out=Path(temp)/'run';proxies=[]
                def selector():
                    value=selectors.EpollSelector();proxy=PollSignalProxy(value._selector,signum)
                    value._selector=proxy;proxies.append(proxy);return value
                limits=supervisor.Limits(wall_seconds=3,cpu_seconds=2,address_space_bytes=256*1024**2,
                    cpu=cpu,poll_seconds=.01,cleanup_seconds=2)
                before={sig:signal.getsignal(sig) for sig in (signal.SIGINT,signal.SIGTERM,signal.SIGXCPU)}
                with patch.object(supervisor.selectors,'DefaultSelector',side_effect=selector):
                    result=supervisor.run([sys.executable,'-c',code],output_dir=out,limits=limits)
                self.assertTrue(proxies[0].delivered)
                self.assertEqual(result['status'],'FAILED');self.assertEqual(result['reason'],'supervisor_exception')
                self.assertEqual(result['error'],'SupervisorCancellation: Supervisor signal '+str(signum))
                self.assertTrue(result['cleanup_verified']);self.assertIsNone(result['worker_receipt'])
                self.assertEqual(supervisor.read_result(out),result)
                worker=json.loads((out/'worker.json').read_bytes())
                current=supervisor._stat(worker['pid'])
                self.assertTrue(current is None or current[0]!=worker['start_ticks'])
                self.assertEqual({sig:signal.getsignal(sig) for sig in before},before)

    def test_real_worker_signals_parent_during_native_poll_and_orphan_is_cleaned(self):
        cpu=min(os.sched_getaffinity(0))
        for signum in (signal.SIGINT,signal.SIGTERM):
            with self.subTest(signal=signum),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);out=root/'run';polling=out/'artifacts/polling';spawned=out/'artifacts/spawned.json'
                # A real detached grandchild exercises ownership cleanup. Parent
                # and worker are pinned to the same CPU, and the worker waits for
                # the marker immediately preceding the native epoll poll call.
                code=("import os,json,time,subprocess,sys;"
                      "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(10)'],start_new_session=True);"
                      f"json.dump({{'pid':p.pid}},open({str(spawned)!r},'w'));"
                      f"marker={str(polling)!r};"
                      "\nwhile not os.path.exists(marker):time.sleep(.001)\n"
                      f"os.kill(os.getppid(),{int(signum)});time.sleep(.15);"
                      "json.dump({'status':'SUCCESS'},open(os.environ['HIROUTE_WORKER_RECEIPT'],'w'))")
                class MarkPollingSelector(selectors.EpollSelector):
                    def select(self,timeout=None):
                        polling.write_text('polling')
                        return super().select(timeout)
                limits=supervisor.Limits(wall_seconds=3,cpu_seconds=2,address_space_bytes=256*1024**2,
                    cpu=cpu,poll_seconds=.5,cleanup_seconds=2)
                with patch.object(supervisor.selectors,'DefaultSelector',MarkPollingSelector):
                    result=supervisor.run([sys.executable,'-c',code],output_dir=out,limits=limits)
                self.assertEqual(result['status'],'FAILED');self.assertEqual(result['reason'],'supervisor_exception')
                self.assertEqual(result['error'],'SupervisorCancellation: Supervisor signal '+str(signum))
                self.assertTrue(result['cleanup_verified']);self.assertIsNone(result['worker_receipt'])
                self.assertEqual(supervisor.read_result(out),result)
                child=json.loads(spawned.read_bytes())['pid'];self.assertFalse(Path('/proc/'+str(child)).exists())


if __name__=='__main__':unittest.main()
