"""Tiny real subprocess tests: no graph, solver, server, or external input."""
import json
import os
from pathlib import Path
import resource
import signal
import sys

import pytest

# Experiments are intentionally independent of the installed src package.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from experiments.mechanism_recovery_v1.supervisor import Limits, read_result, run

SUCCESS = "import os,json;json.dump({'status':'SUCCESS'},open(os.environ['HIROUTE_WORKER_RECEIPT'],'w'))"


def limits(**overrides):
    values = dict(wall_seconds=3, cpu_seconds=1, address_space_bytes=256 * 1024**2,
                  cpu=min(os.sched_getaffinity(0)), stdout_bytes=4096, stderr_bytes=4096,
                  file_output_bytes=65536, poll_seconds=.01, cleanup_seconds=2)
    values.update(overrides)
    return Limits(**values)


def launch(tmp_path, code, **kwargs):
    return run([sys.executable, '-c', code], output_dir=tmp_path/'run', limits=limits(**kwargs))


def test_success_receipt_environment_and_parent_limits(tmp_path):
    before = resource.getrlimit(resource.RLIMIT_CPU)
    code = "import os; assert os.environ['OMP_NUM_THREADS']=='1'; assert len(os.sched_getaffinity(0))==1;" + SUCCESS
    result = launch(tmp_path, code, cpu_seconds=10)
    assert result['status'] == 'SUCCESS'
    assert result['cleanup_verified'] is True
    assert result['aggregate_memory_hard_limit'] is False
    assert read_result(tmp_path/'run') == result
    assert resource.getrlimit(resource.RLIMIT_CPU) == before


def test_wall_timeout_is_owned_and_bounded(tmp_path):
    result = launch(tmp_path, 'import time;time.sleep(10)', wall_seconds=.12)
    assert result['status'] == 'TIMEOUT'
    assert result['reason'] == 'wall_timeout'
    assert result['cleanup_verified']
    assert result['wall_seconds'] < 3


def test_cpu_limit_real_busy_child(tmp_path):
    result = launch(tmp_path, 'while True: pass', wall_seconds=5)
    assert result['reason'] == 'cpu_limit'
    assert result['status'] == 'TIMEOUT'
    assert result['returncode'] == -signal.SIGXCPU
    assert result['cleanup_verified']


def test_detached_child_cleanup(tmp_path):
    code = ("import subprocess,sys,os,json;"
            "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],start_new_session=True);"
            "json.dump({'status':'SUCCESS','child_pid':p.pid},open(os.environ['HIROUTE_WORKER_RECEIPT'],'w'))")
    result = launch(tmp_path, code)
    assert result['status'] == 'SUCCESS'
    assert result['cleanup_verified']
    assert not Path('/proc/'+str(result['worker_receipt']['child_pid'])).exists()


@pytest.mark.parametrize('channel', ['stdout', 'stderr'])
def test_output_overflow(tmp_path, channel):
    fd = 1 if channel == 'stdout' else 2
    result = launch(tmp_path, f'import os;os.write({fd},b"x"*100000)')
    assert result['reason'] == channel+'_limit'
    assert result['status'] == 'FAILED'
    assert (tmp_path/'run'/(channel+'.txt')).stat().st_size == 4096
    assert result['cleanup_verified']


def test_aggregate_file_output_overflow(tmp_path):
    code = ("import os,pathlib; d=pathlib.Path(os.environ['HIROUTE_OUTPUT_DIR']);"
            "[(d/str(i)).write_bytes(b'x'*40000) for i in range(3)];" + SUCCESS)
    result = launch(tmp_path, code)
    assert result['reason'] == 'file_output_limit'
    assert result['status'] == 'FAILED'


@pytest.mark.parametrize('receipt', ['{}', '{"status":"SUCCESS","status":"FAILED"}', '{"status":"SUCCESS","v":NaN}', 'garbage'])
def test_malformed_worker_receipt_unknown(tmp_path, receipt):
    code = "import os;open(os.environ['HIROUTE_WORKER_RECEIPT'],'w').write(" + repr(receipt) + ')'
    result = launch(tmp_path, code)
    assert result['status'] == 'UNKNOWN'
    assert result['cleanup_verified']


def test_missing_worker_receipt_and_terminal_receipt_unknown(tmp_path):
    assert launch(tmp_path, 'pass')['status'] == 'UNKNOWN'
    (tmp_path/'run'/'receipt.json').unlink()
    assert read_result(tmp_path/'run')['status'] == 'UNKNOWN'


def test_reuse_refused(tmp_path):
    launch(tmp_path, SUCCESS)
    with pytest.raises(FileExistsError):
        launch(tmp_path, SUCCESS)


def test_inherited_low_hard_cpu_rejected_before_worker(tmp_path):
    # Isolate permanent hard-limit changes from pytest and other tests.
    script = ("import resource,sys; from pathlib import Path;"
              "from experiments.mechanism_recovery_v1.supervisor import Limits,run;"
              "resource.setrlimit(resource.RLIMIT_CPU,(2,2));"
              "run([sys.executable,'-c','pass'],output_dir=sys.argv[1],"
              f"limits=Limits(1,10,268435456,{min(os.sched_getaffinity(0))}))")
    import subprocess
    p = subprocess.run([sys.executable, '-c', script, str(tmp_path/'bad')],
                       cwd=ROOT, capture_output=True, timeout=5)
    assert p.returncode != 0
    assert b'Inherited hard resource limit is too restrictive' in p.stderr
    assert not (tmp_path/'bad').exists()


def test_child_can_raise_soft_cpu_with_adequate_inherited_hard(tmp_path):
    import subprocess
    script = ("import resource,sys,json,os;"
              "from experiments.mechanism_recovery_v1.supervisor import Limits,run;"
              "hard=resource.getrlimit(resource.RLIMIT_CPU)[1];"
              "resource.setrlimit(resource.RLIMIT_CPU,(12,hard));"
              f"r=run([sys.executable,'-c',{SUCCESS!r}],output_dir=sys.argv[1],"
              f"limits=Limits(3,600,268435456,{min(os.sched_getaffinity(0))}));"
              "print(json.dumps(r));print(resource.getrlimit(resource.RLIMIT_CPU)[0])")
    p = subprocess.run([sys.executable, '-c', script, str(tmp_path/'high')],
                       cwd=ROOT, capture_output=True, timeout=6)
    assert p.returncode == 0, p.stderr
    lines = p.stdout.decode().splitlines()
    result = json.loads(lines[0])
    assert result['status'] == 'SUCCESS'
    assert result['effective_child_limits']['cpu'] == [600, 601]
    assert result['effective_child_limits']['address_space'] == [268435456]*2
    assert lines[1] == '12'


def test_per_file_limit_real_child(tmp_path):
    code = ("import os;open(os.path.join(os.environ['HIROUTE_OUTPUT_DIR'],'big'),'wb').write(b'x'*100000)")
    result = launch(tmp_path, code)
    assert result['status'] == 'FAILED'
    assert (tmp_path/'run'/'artifacts'/'big').stat().st_size <= 65536
    assert result['cleanup_verified']


def test_final_entry_limit(tmp_path):
    code = ("import os,pathlib; d=pathlib.Path(os.environ['HIROUTE_OUTPUT_DIR']);"
            "[(d/str(i)).touch() for i in range(10)];" + SUCCESS)
    result = launch(tmp_path, code, max_output_entries=5)
    assert result['reason'] == 'output_entry_limit'


def test_unverified_cleanup_never_authorizes_success(tmp_path, monkeypatch):
    import experiments.mechanism_recovery_v1.supervisor as supervisor
    real_children = supervisor._children
    calls = 0
    def cannot_verify(pid):
        nonlocal calls
        calls += 1
        # First call is admission; subsequent calls cannot establish emptiness.
        return set() if calls == 1 else real_children(pid) | {999999999}
    monkeypatch.setattr(supervisor, '_children', cannot_verify)
    result = launch(tmp_path, SUCCESS, cleanup_seconds=.05)
    assert result['status'] == 'UNKNOWN'
    assert not result['cleanup_verified']
    assert read_result(tmp_path/'run')['status'] == 'UNKNOWN'


def test_incomplete_success_shaped_receipt_is_unknown(tmp_path):
    from experiments.mechanism_recovery_v1.supervisor import SCHEMA
    (tmp_path/'receipt.json').write_text(json.dumps(dict(schema=SCHEMA, complete=True,
        cleanup_verified=True, status='SUCCESS')))
    assert read_result(tmp_path)['status'] == 'UNKNOWN'


PHASE_IDENTITY = {'nonce': 'unit-run-nonce', 'stage': 'search', 'source_sha256': 'a'*64,
                  'prepared_seed_sha256': 'b'*64}
PHASE_ENTRY = ('from experiments.mechanism_recovery_v1.supervisor import publish_phase_entry;'
               'publish_phase_entry();')


def launch_phase(tmp_path, code, *, seconds=.08, wall_seconds=1):
    from experiments.mechanism_recovery_v1.supervisor import PhaseBudget
    return run([sys.executable, '-c', code], output_dir=tmp_path/'run',
               limits=limits(wall_seconds=wall_seconds), cwd=ROOT,
               phase_budget=PhaseBudget(seconds, PHASE_IDENTITY))


def test_phase_kills_noncooperative_busy_child(tmp_path):
    # No cooperative checks and Python signal handlers cannot postpone SIGKILL.
    result = launch_phase(tmp_path, PHASE_ENTRY + '\nwhile True: pass')
    assert result['status'] == 'TIMEOUT'
    assert result['reason'] == 'phase_timeout'
    assert result['cleanup_verified']
    assert result['wall_seconds'] < .8
    assert result['returncode'] == -signal.SIGKILL
    assert read_result(tmp_path/'run')['reason'] == 'phase_timeout'


@pytest.mark.parametrize('mutation', ['forged', 'stale', 'future', 'extra'])
def test_invalid_phase_markers_rejected(tmp_path, mutation):
    code = ("import os,json,time,pathlib;"
            "from experiments.mechanism_recovery_v1.supervisor import PHASE_SCHEMA;"
            "d={'schema':PHASE_SCHEMA,'identity':json.loads(os.environ['HIROUTE_PHASE_IDENTITY']),"
            "'entered_monotonic':time.monotonic()};")
    code += {'forged': "d['identity']['nonce']='wrong';",
             'stale': "d['entered_monotonic']=0;",
             'future': "d['entered_monotonic']+=100;",
             'extra': "d['unrecognized']=1;"}[mutation]
    code += ("p=pathlib.Path(os.environ['HIROUTE_PHASE_MARKER']);"
             "t=p.with_suffix('.tmp');t.write_text(json.dumps(d));os.replace(t,p);time.sleep(2)")
    result = launch_phase(tmp_path, code)
    assert result['status'] == 'UNKNOWN'
    assert result['reason'] == 'invalid_phase_marker'
    assert result['cleanup_verified']


def test_changed_phase_marker_rejected(tmp_path):
    code = PHASE_ENTRY + ("import os,time,pathlib;time.sleep(.07);"
                         "p=pathlib.Path(os.environ['HIROUTE_PHASE_MARKER']);"
                         "p.write_text(p.read_text()+' ');time.sleep(2)")
    result = launch_phase(tmp_path, code, seconds=.4)
    assert result['status'] == 'UNKNOWN'
    assert result['reason'] == 'invalid_phase_marker'
    assert 'changed' in result['error']


def test_missing_phase_marker_uses_whole_deadline(tmp_path):
    result = launch_phase(tmp_path, 'import time;time.sleep(2)', wall_seconds=.12)
    assert result['status'] == 'TIMEOUT'
    assert result['reason'] == 'wall_timeout'
    assert result['phase_entered_monotonic'] is None


def test_completed_phase_and_missing_phase_success_contract(tmp_path):
    result = launch_phase(tmp_path, PHASE_ENTRY + SUCCESS, seconds=.5)
    assert result['status'] == 'SUCCESS'
    assert result['phase_entered_monotonic'] is not None
    result = launch_phase(tmp_path/'missing', SUCCESS)
    assert result['status'] == 'UNKNOWN'
    assert result['reason'] == 'missing_phase_marker'


def test_phase_kills_native_call_without_python_signal_cooperation(tmp_path):
    code = ('import ctypes;libc=ctypes.PyDLL(None);' + PHASE_ENTRY + 'libc.sleep(5)')
    result = launch_phase(tmp_path, code)
    assert result['status'] == 'TIMEOUT'
    assert result['reason'] == 'phase_timeout'
    assert result['cleanup_verified']
    assert result['returncode'] == -signal.SIGKILL
    assert result['wall_seconds'] < .8
