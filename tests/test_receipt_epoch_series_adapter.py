"""Bounded protocol fixtures; these deliberately never execute an LP controller."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.receipt_epoch.series_adapter import Adapter, AdmissionError, Journal, pin, pinned_json, run_controller_once, production_command, ProductionHooks
from tools.receipt_epoch import driver, series_adapter


def check(value):
    if not value: pytest.fail('explicit fixture check failed')


class Epoch:
    def __init__(self, fail=None):
        self.ops=[]; self.fail=fail; self.invalidated=False; self.terminal_after=None

    def call(self, op, payload, *, seconds):
        check(seconds == 180)
        self.ops.append(op)
        if op == self.fail: raise EOFError('private pipe closed')
        if op == 'prepare' and self.terminal_after is not None and self.ops.count('prepare') > self.terminal_after:
            return dict(terminal=True,window_plan=dict(launch_required=False))
        if op == 'prepare': return dict(token=dict(epoch='private', generation=len(self.ops)),
            window_plan=dict(launch_required=True,window_id='W022',population_plan_sha256='0'*64,
                             block_ids=list(range(673,705)),expected_model_count=8192))
        if op == 'cold': return dict(status='incrementally-authenticated',
            completed_models=172288+self.ops.count('cold')*8192,
            completed_blocks=673+self.ops.count('cold')*32)
        if op == 'cancel-prepared': return dict(cancelled=True,at_safe_boundary=True,numerical_launch=False)
        return dict(status=op)

    def invalidate(self): self.invalidated=True


class Hooks:
    def __init__(self, fail=None): self.fail=fail; self.launches=0; self.checks=0; self.advances=0
    def source_check(self):
        self.checks += 1
        if self.fail == 'source': raise AdmissionError('source changed')
    def idle_check(self): pass
    def prepare(self, prepared, targets):
        return dict(argv=['frozen-controller'], targets=targets,index=getattr(self,'index',22))
    def launch(self, command):
        self.launches += 1
        if self.fail == 'launch': raise RuntimeError('controller failed')
        return dict(exit_code=0)
    def cold(self, observed, command):
        if self.fail == 'cold': raise AdmissionError('return failed')
        return {key:dict(path=key, size_bytes=1, sha256='0'*64)
                for key in ('registry','registration_return','runtime_return')}
    def advance(self, result):
        self.advances += 1
        if self.fail == 'advance': raise AdmissionError('advance failed')


def fixture(tmp_path, fail=None, epoch_fail=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    root=tmp_path/'journal'; journal=Journal(root); epoch=Epoch(epoch_fail); hooks=Hooks(fail)
    registry=tmp_path/'registry.json'; registry.write_text(json.dumps(dict(entries=[dict(attempt='old-attempt')])))
    returned=tmp_path/'return.json'
    returned.write_text(json.dumps(dict(status='registered', registry=pin(registry),
        registration_return=dict(path='registration',size_bytes=1,sha256='0'*64),
        runtime_return=dict(path='runtime',size_bytes=1,sha256='0'*64))))
    adapter=Adapter(epoch,journal,[pin(returned)],dict(actual='prefix',code_pins=[],reviewed_sources=[]),hooks)
    return adapter,epoch,hooks,root


@pytest.mark.parametrize('count', [0, 2])
def test_ordered_bootstrap_and_pause(tmp_path,count):
    adapter,epoch,hooks,root=fixture(tmp_path)
    adapter.retained=adapter.retained*count
    adapter.bootstrap()
    for _ in range(2): adapter.run_one(dict(attempt='new',registry='r',registration_return='s',runtime_return='t'))
    adapter.pause(); adapter.journal.close()
    check(epoch.ops == ['establish']+['prepare','cold']*count+['prepare','cold']*2+['pause','close'])
    check(hooks.launches == 2 and adapter.state == 'closed' and epoch.invalidated)
    check([json.loads(line)['operation'] for line in (root/'events.jsonl').read_text().splitlines()].count('launch-intent') == 2)


def test_bounded_four_windows_keep_one_epoch_and_pause(tmp_path):
    adapter,epoch,hooks,root=fixture(tmp_path)
    adapter.bootstrap()
    targets=[dict(attempt=f'a{i}',registry=f'r{i}',registration_return=f's{i}',runtime_return=f't{i}')
             for i in range(4)]
    adapter.run_bounded(targets,lambda:False,remaining_windows=4)
    check(epoch.ops == ['establish','prepare','cold']+['prepare','cold']*4+['pause','close'])
    check(hooks.launches == hooks.advances == 4 and adapter.state == 'closed')
    check((root/'events.jsonl').read_text().count('launch-intent') == 4)
    adapter.journal.close()


def test_remaining_catalogue_bound_runs_once_then_pauses(tmp_path):
    adapter,epoch,hooks,root=fixture(tmp_path)
    adapter.bootstrap()
    targets=[dict(attempt=f'a{i}',registry=f'r{i}',registration_return=f's{i}',runtime_return=f't{i}')
             for i in range(54)]
    adapter.run_bounded(targets,lambda:False,remaining_windows=54)
    check(hooks.launches == hooks.advances == 54 and adapter.state == 'closed')
    check(epoch.ops[-2:] == ['pause','close'])
    check((root/'events.jsonl').read_text().count('launch-intent') == 54)
    adapter.journal.close()


def test_adapter_rejects_targets_beyond_remaining_catalogue(tmp_path):
    adapter,epoch,hooks,root=fixture(tmp_path)
    adapter.bootstrap()
    targets=[dict(attempt=f'a{i}',registry=f'r{i}',registration_return=f's{i}',runtime_return=f't{i}')
             for i in range(55)]
    with pytest.raises(AdmissionError):
        adapter.run_bounded(targets,lambda:False,remaining_windows=54)
    check(hooks.launches == 0 and adapter.state == 'ready')
    adapter.pause();adapter.journal.close()


def test_requested_pause_waits_for_current_cold(tmp_path):
    adapter,epoch,hooks,_=fixture(tmp_path)
    adapter.bootstrap()
    targets=[dict(attempt=f'a{i}',registry=f'r{i}',registration_return=f's{i}',runtime_return=f't{i}')
             for i in range(4)]
    adapter.run_bounded(targets,lambda:hooks.launches >= 1,remaining_windows=4)
    check(hooks.launches == hooks.advances == 1)
    check(epoch.ops[-4:] == ['prepare','cold','pause','close'])
    adapter.journal.close()


def test_pause_during_preflight_prevents_new_private_prepare(tmp_path):
    adapter,epoch,hooks,root=fixture(tmp_path)
    adapter.bootstrap()
    pause={'value':False}
    original=hooks.source_check
    def source_check():
        original();pause['value']=True
    hooks.source_check=source_check
    adapter.run_bounded([dict(attempt='a',registry='r',registration_return='s',runtime_return='t')],
                        lambda:pause['value'],remaining_windows=1)
    check(hooks.launches == 0 and epoch.ops == ['establish','prepare','cold','pause','close'])
    check('pause-before-prepare' in (root/'events.jsonl').read_text())
    adapter.journal.close()


@pytest.mark.parametrize('stage', ['after-private-prepare','before-launch-intent'])
def test_pause_after_prepare_cancels_private_token_without_intent(tmp_path,stage):
    adapter,epoch,hooks,root=fixture(tmp_path)
    adapter.bootstrap()
    pause={'value':False}
    if stage == 'after-private-prepare':
        original=epoch.call
        def call(op,payload,*,seconds):
            result=original(op,payload,seconds=seconds)
            if op == 'prepare': pause['value']=True
            return result
        epoch.call=call
    else:
        original=hooks.prepare
        def prepare(prepared,targets):
            result=original(prepared,targets);pause['value']=True;return result
        hooks.prepare=prepare
    adapter.run_bounded([dict(attempt='a',registry='r',registration_return='s',runtime_return='t')],
                        lambda:pause['value'],remaining_windows=1)
    ops=[json.loads(line)['operation'] for line in (root/'events.jsonl').read_text().splitlines()]
    check(hooks.launches == 0 and 'launch-intent' not in ops and 'cold' == ops[2])
    check('cancel-prepared' in ops and 'abandoned-prepared-no-launch' in ops)
    check(ops[-3:] == ['pause','close','safe-pause'] and epoch.invalidated)
    adapter.journal.close()


def test_pause_during_real_private_ipc_prepare_closes_without_launch(tmp_path):
    sidecar=pytest.importorskip('tools.receipt_epoch.sidecar')
    import sys,threading
    if sys.platform == 'darwin': pytest.skip('RLIMIT_AS private service requires Linux')
    script='''
import sys,time
from tools.receipt_epoch import sidecar
class Micro:
 def __init__(self): self.pending=False
 @classmethod
 def establish(cls,**kwargs): return cls()
 def prepare(self,**kwargs):
  time.sleep(.25);self.pending=True
  return {'token':{'micro':'nonce'},'window_plan':{'launch_required':True}}
 def cold(self,**kwargs):
  self.pending=False
  return {'completed_models':180480,'completed_blocks':705,'status':'incrementally-authenticated'}
 def cancel_prepared(self,**kwargs):
  self.pending=False
  return {'cancelled':True,'at_safe_boundary':True,'numerical_launch':False}
 def request_pause(self): return {'at_safe_boundary':not self.pending}
 def invalidate(self): self.pending=False
class Origin:
 expected={'verifier_root':'.'}
 pins=[]
 def phase_check(self,deadline): pass
sidecar.Epoch=Micro;sidecar.SourceBinding=Origin
sidecar._live_checks=lambda *args,**kwargs:None
sidecar.serve(sys.stdin.buffer,sys.stdout.buffer,origin=Origin())
'''
    parent=sidecar.Parent([sys.executable,'-B','-c',script],cwd=Path(__file__).parents[1],
                          stderr_path=tmp_path/'private.stderr')
    adapter,_,hooks,root=fixture(tmp_path)
    adapter.epoch=parent
    pause={'value':False}
    timer=None
    try:
        adapter.bootstrap()
        timer=threading.Timer(.05,lambda:pause.__setitem__('value',True));timer.start()
        adapter.run_bounded([dict(attempt='a',registry='r',registration_return='s',runtime_return='t')],
                            lambda:pause['value'],remaining_windows=1)
        timer.join()
        ops=[json.loads(line)['operation'] for line in (root/'events.jsonl').read_text().splitlines()]
        check(hooks.launches == 0 and 'launch-intent' not in ops)
        check('cancel-prepared' in ops and ops[-1] == 'safe-pause')
        check(parent.process.returncode == 0)
    finally:
        if timer is not None: timer.join()
        parent.invalidate();adapter.journal.close()


@pytest.mark.parametrize('count', [4,54])
def test_terminal_private_plan_never_launches_empty_window(tmp_path,count):
    adapter,epoch,hooks,root=fixture(tmp_path)
    adapter.bootstrap();epoch.terminal_after=2
    targets=[dict(attempt=f'a{i}',registry=f'r{i}',registration_return=f's{i}',runtime_return=f't{i}')
             for i in range(count)]
    adapter.run_bounded(targets,lambda:False,remaining_windows=count)
    check(hooks.launches == hooks.advances == 1)
    check('terminal-no-launch' in (root/'events.jsonl').read_text())
    check(epoch.ops[-4:] == ['cold','prepare','pause','close'])
    adapter.journal.close()


def test_advance_failure_stops_batch_without_retry(tmp_path):
    adapter,epoch,hooks,root=fixture(tmp_path,fail='advance')
    adapter.bootstrap()
    targets=[dict(attempt=f'a{i}',registry=f'r{i}',registration_return=f's{i}',runtime_return=f't{i}')
             for i in range(2)]
    with pytest.raises(AdmissionError): adapter.run_bounded(targets,lambda:False,remaining_windows=2)
    check(hooks.launches == 1 and hooks.advances == 1 and epoch.invalidated)
    check('failed-stopped' in (root/'events.jsonl').read_text())
    adapter.journal.close()


def test_bounded_target_contract_rejects_gaps_aliases_and_excess(tmp_path):
    first=[tmp_path/f'{name}23' for name in ('a','r','s','t')]
    later=[[str(n),*(str(tmp_path/f'{name}{n}') for name in ('a','r','s','t'))]
           for n in (24,25,26)]
    args=SimpleNamespace(window_count=4,next_index=23,retained_window_return=[('p','0')]*5,
        attempt_target=first[0],registry_target=first[1],registration_target=first[2],
        runtime_target=first[3],future_window_target=later)
    check(len(driver.series_targets(args,series_adapter,4))==4)
    args.future_window_target[1][0]='27'
    with pytest.raises(ValueError): driver.series_targets(args,series_adapter,4)
    args.future_window_target[1][0]='25'
    args.future_window_target[2][1]=str(first[0])
    with pytest.raises(ValueError): driver.series_targets(args,series_adapter,4)
    args.window_count=5
    with pytest.raises(ValueError): driver.series_targets(args,series_adapter,4)


def test_remaining_window_count_uses_pinned_catalogue_plan():
    preparation=dict(previous_completed_blocks=list(range(1569)),
        resource_plan=dict(maximum_blocks=32),
        population=dict(unique_logical_models=844440),
        window_plan=dict(block_ids=list(range(1569,1601)),
            population=dict(total_blocks=3299,block_size=256,total_models=844440)))
    check(driver.remaining_window_count(preparation,51)==54)
    preparation['window_plan']['block_ids'][0]=1568
    with pytest.raises(ValueError):driver.remaining_window_count(preparation,51)
    preparation['window_plan']['block_ids'][0]=1569
    preparation['previous_completed_blocks'][0]=1
    with pytest.raises(ValueError):driver.remaining_window_count(preparation,51)


@pytest.mark.parametrize('count', [1,4,54,55,0])
def test_cli_count_stops_at_remaining_catalogue(tmp_path,count):
    first=[tmp_path/f'{name}51' for name in ('a','r','s','t')]
    later=[[str(n),*(str(tmp_path/f'{name}{n}') for name in ('a','r','s','t'))]
           for n in range(52,51+count)]
    args=SimpleNamespace(window_count=count,next_index=51,retained_window_return=[('p','0')]*33,
        attempt_target=first[0],registry_target=first[1],registration_target=first[2],
        runtime_target=first[3],future_window_target=later)
    if 1 <= count <= 54:
        check(len(driver.series_targets(args,series_adapter,54))==count)
    else:
        with pytest.raises(ValueError):driver.series_targets(args,series_adapter,54)


@pytest.mark.parametrize('failure', ['source','launch','cold'])
def test_fail_stop_no_duplicate_launch(tmp_path,failure):
    adapter,epoch,hooks,root=fixture(tmp_path,fail=failure)
    if failure == 'source':
        with pytest.raises(AdmissionError): adapter.bootstrap()
    else:
        adapter.bootstrap()
        with pytest.raises((AdmissionError,RuntimeError)): adapter.run_one(dict(attempt='new',registry='r',registration_return='s',runtime_return='t'))
    with pytest.raises(AdmissionError): adapter.run_one({})
    check(epoch.invalidated and hooks.launches <= 1)
    check('failed-stopped' in (root/'events.jsonl').read_text())
    adapter.journal.close()


def test_eof_invalidates_epoch(tmp_path):
    adapter,epoch,hooks,_=fixture(tmp_path,epoch_fail='cold')
    with pytest.raises(EOFError): adapter.bootstrap()
    check(epoch.invalidated and hooks.launches == 0)
    adapter.journal.close()


def test_retained_bytes_are_not_status_authority(tmp_path):
    adapter,epoch,hooks,_=fixture(tmp_path)
    Path(adapter.retained[0]['path']).write_text('{"status":"passed"}')
    with pytest.raises(AdmissionError): adapter.bootstrap()
    check(epoch.ops == ['establish'] and hooks.launches == 0 and epoch.invalidated)
    adapter.journal.close()


def test_pinned_json_parses_single_identity_checked_read(tmp_path,monkeypatch):
    path=tmp_path/'input.json';path.write_text('{"value":7}')
    row=pin(path)
    monkeypatch.setattr(Path,'read_bytes',lambda self: pytest.fail('second pathname read'))
    check(pinned_json(row,64) == {'value':7})
    with pytest.raises(AdmissionError): pinned_json(row,4)


def test_restart_must_rebootstrap(tmp_path):
    first,epoch,hooks,_=fixture(tmp_path/'first')
    first.bootstrap(); first.pause(); first.journal.close()
    second,other,_,_=fixture(tmp_path/'second')
    second.bootstrap(); second.journal.close()
    check(other.ops[0] == 'establish' and other.ops[1:3] == ['prepare','cold'])


def test_occupied_output_fails_before_private_prepare_or_launch(tmp_path):
    adapter,epoch,hooks,_=fixture(tmp_path)
    adapter.bootstrap()
    occupied=tmp_path/'occupied'; occupied.write_bytes(b'prior attempt')
    with pytest.raises(AdmissionError):
        adapter.run_one(dict(attempt=str(occupied),registry='r',registration_return='s',runtime_return='t'))
    check(epoch.ops == ['establish','prepare','cold'] and hooks.launches == 0 and epoch.invalidated)
    adapter.journal.close()


@pytest.mark.parametrize('mode', ['success','nonzero','missing'])
def test_real_subprocess_observer_fake_controller(tmp_path, mode):
    script=tmp_path/'fake_controller.py'
    script.write_text('import json,sys\n'
        'if sys.argv[1] == "nonzero": sys.exit(7)\n'
        'if sys.argv[1] == "missing": print(json.dumps({"status":"registered"})); sys.exit(0)\n'
        'print(json.dumps({"status":"registered","registry":{"path":"r"},'
        '"registration_return":{"path":"s"},"runtime_return":{"path":"t"}}))\n')
    import sys
    command=dict(argv=[sys.executable,str(script),mode],cwd=str(tmp_path),maximum_launches=1,no_retry=True)
    observed=tmp_path/'observed'
    if mode == 'success':
        report,actual=run_controller_once(command,observed,environment=dict(__import__('os').environ))
        check(report['exit_code'] == 0 and actual['registry']['path'] == 'r')
    else:
        with pytest.raises(AdmissionError):
            run_controller_once(command,observed,environment=dict(__import__('os').environ))
    check((observed/'launch-manifest.json').is_file() and (observed/'controller-observation.json').is_file())
    check(len(list(observed.glob('launch-manifest.json'))) == 1)


def test_production_command_uses_controller_parser_and_resource_plan(tmp_path):
    import argparse
    class FrozenSuffix:
        MODULE='experiments.time_cut_v2.recorded_real.suffix_window'
        SEED_FIELDS=('seed_archive',)
        @staticmethod
        def parser():
            p=argparse.ArgumentParser()
            for name in ('registry','registry_sha','registry_return','registry_return_sha',
                         'registry_output','registration_return_output','attempt_dir','bootstrap',
                         'bootstrap_sha','maximum_blocks','seed_archive'):
                p.add_argument('--'+name.replace('_','-'))
            p.add_argument('--worker-cpus',nargs=5,type=int,required=True)
            p.add_argument('--cpu',type=int,required=True)
            return p
        @staticmethod
        def input_context(args):
            return {key:getattr(args,key) for key in ('registry','registry_sha','registry_return',
                'registry_return_sha','registry_output','registration_return_output','worker_cpus')}
        @staticmethod
        def runtime_return_path(args): return str(args.registry_output)+'.run-return.json'
        @staticmethod
        def admission_mode(args): return 'registry'
        @staticmethod
        def resource_plan(cpus, count): return dict(worker_cpus=cpus,expected_models=count,persistent_workers=4)
    targets=dict(attempt=str(tmp_path/'attempt'),registry=str(tmp_path/'registry'),
        registration_return=str(tmp_path/'registration'),runtime_return=str(tmp_path/'registry.run-return.json'))
    old=['python','-B','-m',FrozenSuffix.MODULE,'--worker-cpus','1','2','3','4','5','--cpu','6']
    previous={key:dict(path=str(tmp_path/key),sha256='0'*64) for key in ('registry','registration_return')}
    command=production_command(FrozenSuffix,old,previous,dict(expected_model_count=8192),targets,
        python='/trusted/python',root=tmp_path,source_commit='a'*40,source_sha='b'*64)
    check(command['argv'][:4] == ['/trusted/python','-B','-m',FrozenSuffix.MODULE])
    check(command['resource_plan']['expected_models'] == 8192 and command['persistent_workers'] == 4)
    check(len(command['resource_plan']['worker_cpus']) == 5)
    check('--maximum-blocks' not in command['argv'] and '--bootstrap' not in command['argv'])


def test_frozen_3ad_parser_and_resource_plan_positive_negative(tmp_path):
    """Read-only integration against the actual frozen controller and retained 021 argv."""
    import subprocess,sys
    root=Path('/home/dy/HiRoute/project')
    series=root/'results/milestone_5_validation/C01.D0.remaining-series.3ad6e38.from-window001'
    window=series/'window021.20261008T212437Z'
    if not (window/'window021.command.json').exists(): pytest.skip('frozen server evidence unavailable')
    script='''
import json,sys
from pathlib import Path
root,draft,out=map(Path,sys.argv[1:])
sys.path[:0]=[str(draft),str(root/'src'),str(root)]
from experiments.time_cut_v2.recorded_real import suffix_window
from tools.receipt_epoch.series_adapter import production_command
window=root/'results/milestone_5_validation/C01.D0.remaining-series.3ad6e38.from-window001/window021.20261008T212437Z'
prior=json.loads((window/'window021.command.json').read_text())
returned=json.loads((window/'window021.observation.001/controller.stdout.json').read_text())
actual={key:returned[key] for key in ('registry','registration_return','runtime_return')}
registry=out/'window022.registry.json'
targets=dict(attempt=str(out/'attempt'),registry=str(registry),
 registration_return=str(out/'window022.registration-return.json'),
 runtime_return=str(registry)+'.run-return.json')
planned=dict(expected_model_count=8192)
value=production_command(suffix_window,prior['argv'],actual,planned,targets,
 python=sys.executable,root=root,source_commit='3ad6e385903b631579df059b48d9ea6037728da7',
 source_sha='9b3f2a1b1c2a3b36533ea42e744b94e33f5929730ec7cfe11aa0f2e586caf5ad')
if len(value['resource_plan']['worker_cpus']) != 5 or value['resource_plan']['persistent_workers'] != 4:
 raise RuntimeError('frozen positive five-slot/four-LP contract failed')
cpus=value['resource_plan']['worker_cpus']
try: suffix_window.resource_plan(cpus[:4],8192)
except ValueError: pass
else: raise RuntimeError('frozen resource planner accepted four slots')
bad=list(prior['argv']); start=bad.index('--worker-cpus'); del bad[start+5]
try: production_command(suffix_window,bad,actual,planned,targets,
 python=sys.executable,root=root,source_commit='3ad6e385903b631579df059b48d9ea6037728da7',
 source_sha='9b3f2a1b1c2a3b36533ea42e744b94e33f5929730ec7cfe11aa0f2e586caf5ad')
except SystemExit: pass
else: raise RuntimeError('frozen parser accepted four --worker-cpus')
print(json.dumps(dict(cpu_slots=len(cpus),lp_workers=value['resource_plan']['persistent_workers'])))
'''
    result=subprocess.run([sys.executable,'-I','-B','-c',script,str(root),
        str(Path(__file__).parents[1]),str(tmp_path)],cwd=root,text=True,
        capture_output=True,timeout=20)
    check(result.returncode == 0)
    check(json.loads(result.stdout) == dict(cpu_slots=5,lp_workers=4))


@pytest.mark.parametrize('mode', ['success','nonzero','missing'])
def test_saved_observer_interface(tmp_path,monkeypatch,mode):
    import sys
    if sys.platform == 'darwin': pytest.skip('sealed observer execution requires Linux')
    original=tmp_path/'original.json'; original.write_text(json.dumps(dict(environment={})))
    first=tmp_path/'first.json'; first.write_text(json.dumps(dict(historical_and_policy_pins=[],population={})))
    observer=tmp_path/'observer.py'
    observer.write_text('import json,pathlib,sys\n'
        'p=json.loads(pathlib.Path(sys.argv[1]).read_text()); o=pathlib.Path(p["output_dir"]); '
        'd=o/(p["label"]+".observation.001")\n'
        'if '+repr(mode)+' == "nonzero": sys.exit(4)\n'
        'returned={"status":"registered"} if '+repr(mode)+' == "missing" else '
        '{"status":"registered","registry":{"path":"r"},"registration_return":{"path":"s"},'
        '"runtime_return":{"path":"t"}}\n'
        'raw=json.dumps(returned).encode(); stdout=d/"controller.stdout.json"; stdout.write_bytes(raw)\n'
        'import hashlib\n'
        'row={"path":str(stdout),"size_bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}\n'
        '(d/"controller-observation.json").write_text(json.dumps({"exit_code":0,"launches":1,'
        '"automatic_retry":False,"stdout":row}))\n')
    def fake_command(_module,_argv,_actual,plan,targets,**kwargs):
        return dict(schema='hiroute-epoch-series-command-v1',argv=['fake'],cwd=str(tmp_path),
                    resource_plan={},window_plan=plan,maximum_launches=1,no_retry=True)
    monkeypatch.setattr('tools.receipt_epoch.series_adapter.production_command',fake_command)
    hooks=ProductionHooks(suffix_window=object(),python=sys.executable,root=tmp_path,
        source_commit='a'*40,source_sha='b'*64,original_command=pin(original),
        original_preparation=pin(first),observer=pin(observer),source_check=lambda:None,
        idle_check=lambda:None,previous_argv=['old'],index=22,completed_models=172288)
    out=tmp_path/'new-output'
    targets=dict(attempt=str(tmp_path/'new-attempt'),registry=str(out/'window022.registry.json'),
        registration_return=str(out/'window022.registration-return.json'),
        runtime_return=str(out/'window022.registry.json.run-return.json'))
    plan=dict(launch_required=True,policy='first-32-outstanding-canonical-blocks-v1',
        completed_block_ids=list(range(673)),expected_model_count=8192,window_id='W022',block_ids=list(range(673,705)))
    command=hooks.prepare(dict(window_plan=plan,previous_actual={}),targets)
    if mode == 'nonzero':
        with pytest.raises(AdmissionError): hooks.launch(command)
    else:
        observed=hooks.launch(command)
        if mode == 'missing':
            with pytest.raises(KeyError): hooks.cold(observed,command)
        else: check(hooks.cold(observed,command)['registry']['path'] == 'r')
    check((out/'prepared.json').is_file() and (out/'window022.observation.001'/'observer.stdout.txt').is_file())


def test_real_observer_envelope_stops_verified_fake_child(tmp_path,monkeypatch):
    import os,sys,time
    if sys.platform != 'linux': pytest.skip('verified descendant cleanup requires /proc')
    monkeypatch.setattr('tools.receipt_epoch.series_adapter.OBSERVER_ENVELOPE_SECONDS',.25)
    monkeypatch.setattr('tools.receipt_epoch.series_adapter.OBSERVER_CLEANUP_GRACE_SECONDS',.1)
    out=tmp_path/'output';out.mkdir()
    controller=dict(argv=[sys.executable,'-c','import time;time.sleep(30)'])
    command_path=out/'window022.command.json';command_path.write_text(json.dumps(controller))
    prepared_path=out/'prepared.json'
    prepared_path.write_text(json.dumps(dict(label='window022',output_dir=str(out),command_path=str(command_path))))
    observer=tmp_path/'fake_observer.py'
    observer.write_text('import json,pathlib,subprocess,sys,time\n'
        'p=json.loads(pathlib.Path(sys.argv[1]).read_text());'
        'out=pathlib.Path(p["output_dir"]);obs=out/(p["label"]+".observation.001")\n'
        'cmd=json.loads(pathlib.Path(p["command_path"]).read_text());'
        'child=subprocess.Popen(cmd["argv"],start_new_session=True)\n'
        '(obs/"launch.json").write_text(json.dumps({"pid":child.pid,"argv":cmd["argv"]}))\n'
        '(obs/"child.pid").write_text(str(child.pid))\n'
        'time.sleep(30)\n')
    hooks=ProductionHooks(suffix_window=object(),python=sys.executable,root=tmp_path,
        source_commit='a'*40,source_sha='b'*64,original_command=pin(command_path),
        original_preparation=pin(prepared_path),observer=pin(observer),source_check=lambda:None,
        idle_check=lambda:None,previous_argv=['old'],index=22,completed_models=172288)
    hooks.prepared_path=prepared_path
    with pytest.raises(TimeoutError):
        hooks.launch(dict(prepared=pin(prepared_path),command=pin(command_path)))
    pid_file=out/'window022.observation.001/child.pid'
    check(pid_file.is_file())
    pid=int(pid_file.read_text())
    for _ in range(20):
        path=Path('/proc')/str(pid)/'stat'
        if not path.exists() or path.read_text().rsplit(')',1)[1].split()[0]=='Z': break
        time.sleep(.1)
    else: pytest.fail('fake controller descendant remained running after observer envelope')


@pytest.mark.parametrize('swap',['prepared','command','preparation'])
def test_reviewed_observer_rejects_swapped_prepared_command_and_preparation(tmp_path,swap):
    import subprocess,sys
    if sys.platform!='linux': pytest.skip('reviewed observer is pinned to Linux production')
    source=Path(__file__).parents[1]/'tools/receipt_epoch/series_observer.py'
    out=tmp_path/'out';out.mkdir();label='window022'
    obs=out/(label+'.observation.001');obs.mkdir()
    command=out/(label+'.command.json');command.write_text('{"argv":[]}')
    preparation=out/'preparation.json';preparation.write_text('{"population":{}}')
    prepared=out/'prepared.json'
    prepared.write_text(json.dumps(dict(output_dir=str(out),label=label,window_id='W022',
        command=pin(command),preparation=pin(preparation))))
    original=pin(prepared)
    def invoke():
        return subprocess.run([sys.executable,'-B',str(source),str(prepared),
            original['sha256'],str(original['size_bytes'])],capture_output=True,text=True,timeout=10)
    if swap=='prepared': prepared.write_text(prepared.read_text()+' ')
    if swap=='command': command.write_text('{"argv":["swapped"]}')
    if swap=='preparation': preparation.write_text('{"population":{"swapped":true}}')
    result=invoke()
    check(result.returncode!=0)
    check(not (obs/'launch.json').exists())


@pytest.mark.parametrize('mode',['timeout','nonzero'])
def test_real_observer_cleans_only_owned_multisession_descendants(tmp_path,monkeypatch,mode):
    import os,subprocess,sys,time
    if sys.platform!='linux': pytest.skip('multi-session ownership requires /proc')
    monkeypatch.setattr('tools.receipt_epoch.series_adapter.OBSERVER_ENVELOPE_SECONDS',1.2)
    monkeypatch.setattr('tools.receipt_epoch.series_adapter.OBSERVER_CLEANUP_GRACE_SECONDS',.2)
    sentinel=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],start_new_session=True)
    out=tmp_path/'output';out.mkdir()
    prepared=out/'prepared.json';prepared.write_text(json.dumps(dict(output_dir=str(out),label='window022')))
    grand=tmp_path/'grand.py';grand.write_text('import time;time.sleep(30)\n')
    child=tmp_path/'child.py'
    child.write_text('import pathlib,subprocess,sys,time\n'
        'p=subprocess.Popen([sys.executable,sys.argv[1]],start_new_session=True)\n'
        'pathlib.Path(sys.argv[2]).write_text(str(p.pid))\n'
        'time.sleep(30)\n')
    observer=tmp_path/'observer.py'
    observer.write_text('import json,pathlib,subprocess,sys,time\n'
        'd=pathlib.Path(json.loads(pathlib.Path(sys.argv[1]).read_text())["output_dir"])/"window022.observation.001"\n'
        'p=subprocess.Popen([sys.executable,sys.argv[4],sys.argv[5],str(d/"grand.pid")],start_new_session=True)\n'
        '(d/"child.pid").write_text(str(p.pid))\n'
        'while not (d/"grand.pid").exists():time.sleep(.01)\n'
        'time.sleep(.4)\n'
        'if sys.argv[6]=="nonzero":sys.exit(4)\n'
        'time.sleep(30)\n')
    # This fixture's fake observer accepts two extra script paths after the
    # prepared pin arguments; the production wrapper itself accepts only three.
    class MultiHooks(ProductionHooks):
        def launch(self, command):
            self.observer_source=pin(observer)
            return super().launch(command)
    hooks=MultiHooks(suffix_window=object(),python=sys.executable,root=tmp_path,
        source_commit='a'*40,source_sha='b'*64,original_command=pin(prepared),
        original_preparation=pin(prepared),observer=pin(observer),source_check=lambda:None,
        idle_check=lambda:None,previous_argv=['old'],index=22,completed_models=0)
    hooks.prepared_path=prepared
    # Embed fixture controls in the prepared path via a small trampoline script.
    observer.write_text(observer.read_text().replace('sys.argv[4],sys.argv[5]',
        repr(str(child))+','+repr(str(grand))).replace('sys.argv[6]',repr(mode)))
    hooks.observer_source=pin(observer)
    try:
        with pytest.raises((TimeoutError,AdmissionError)):
            hooks.launch(dict(prepared=pin(prepared)))
        obs=out/'window022.observation.001'
        check((obs/'child.pid').is_file() and (obs/'grand.pid').is_file())
        for name in ('child.pid','grand.pid'):
            pid=int((obs/name).read_text())
            for _ in range(30):
                path=Path('/proc')/str(pid)/'stat'
                if not path.exists() or path.read_text().rsplit(')',1)[1].split()[0]=='Z': break
                time.sleep(.1)
            else: pytest.fail('owned separate-session descendant survived cleanup')
        check(sentinel.poll() is None)
    finally:
        sentinel.terminate();sentinel.wait(timeout=5)


def test_observer_output_cap_checked_after_fast_exit(tmp_path):
    import sys
    if sys.platform!='linux': pytest.skip('observer wrapper requires /proc')
    out=tmp_path/'output';out.mkdir()
    prepared=out/'prepared.json';prepared.write_text(json.dumps(dict(output_dir=str(out),label='window022')))
    observer=tmp_path/'observer.py'
    observer.write_text('import os\n'
        'os.write(1,b"x"*(16*1024**2+1))\n')
    hooks=ProductionHooks(suffix_window=object(),python=sys.executable,root=tmp_path,
        source_commit='a'*40,source_sha='b'*64,original_command=pin(prepared),
        original_preparation=pin(prepared),observer=pin(observer),source_check=lambda:None,
        idle_check=lambda:None,previous_argv=['old'],index=22,completed_models=0)
    hooks.prepared_path=prepared
    with pytest.raises(TimeoutError): hooks.launch(dict(prepared=pin(prepared)))
    check((out/'window022.observation.001/observer.stdout.txt').stat().st_size>16*1024**2)


def test_adapter_with_real_private_parent_ipc_and_fake_epoch(tmp_path):
    sidecar=pytest.importorskip('tools.receipt_epoch.sidecar')
    import sys
    if sys.platform == 'darwin': pytest.skip('RLIMIT_AS private service requires Linux')
    script='''
import sys
from tools.receipt_epoch import sidecar
class Micro:
 def __init__(self): self.pending=False
 @classmethod
 def establish(cls,**kwargs): return cls()
 def prepare(self,**kwargs):
  self.pending=True
  return {'token':{'micro':'nonce'},'window_plan':{'launch_required':True}}
 def cold(self,**kwargs):
  self.pending=False
  return {'completed_models':172288,'status':'incrementally-authenticated'}
 def request_pause(self): return {'at_safe_boundary':not self.pending}
 def invalidate(self): self.pending=False
class Origin:
 expected={'verifier_root':'.'}
 pins=[]
 def phase_check(self,deadline): pass
sidecar.Epoch=Micro
sidecar.SourceBinding=Origin
sidecar._live_checks=lambda *args,**kwargs:None
sidecar.serve(sys.stdin.buffer,sys.stdout.buffer,origin=Origin())
'''
    parent=sidecar.Parent([sys.executable,'-B','-c',script],cwd=Path(__file__).parents[1],
                          stderr_path=tmp_path/'private.stderr')
    adapter,_,hooks,_=fixture(tmp_path)
    adapter.epoch=parent
    try:
        adapter.bootstrap()
        check(parent.live and adapter.last_result['completed_models'] == 172288)
        adapter.run_one(dict(attempt='new',registry='r',registration_return='s',runtime_return='t'))
        check(hooks.launches == 1 and parent.live)
        adapter.pause()
        check(not parent.live and parent.process.returncode == 0)
    finally:
        parent.invalidate();adapter.journal.close()


def test_persistent_launch_intent_blocks_restart_duplicate(tmp_path):
    adapter,epoch,hooks,_=fixture(tmp_path/'first')
    adapter.journal.launch_ledger=tmp_path
    adapter.bootstrap()
    targets=dict(attempt='new',registry='r',registration_return='s',runtime_return='t')
    adapter.run_one(targets);adapter.pause();adapter.journal.close()
    check(len(list(tmp_path.glob('plan-*.launch-intent.json'))) == 1 and hooks.launches == 1)
    restarted,other,other_hooks,_=fixture(tmp_path/'second')
    restarted.journal.launch_ledger=tmp_path
    other_hooks.index=23  # display index and output names do not change the private plan key
    restarted.bootstrap()
    other_targets=dict(attempt='other-attempt',registry='other-registry',
                       registration_return='other-registration',runtime_return='other-runtime')
    with pytest.raises(FileExistsError): restarted.run_one(other_targets)
    check(other_hooks.launches == 0 and other.invalidated)
    restarted.journal.close()


def test_real_private_ipc_death_fails_before_controller(tmp_path):
    sidecar=pytest.importorskip('tools.receipt_epoch.sidecar')
    import sys
    if sys.platform == 'darwin': pytest.skip('RLIMIT_AS private service requires Linux')
    script='''
import sys
from tools.receipt_epoch.sidecar import encode,_receive,AS_BYTES
from tools.receipt_epoch.epoch import PROTOCOL
instance='a'*64
sys.stdout.buffer.write(encode(dict(protocol=PROTOCOL,instance=instance,as_bytes=AS_BYTES)))
sys.stdout.buffer.flush()
request=_receive(sys.stdin.buffer)
sys.stdout.buffer.write(encode(dict(protocol=PROTOCOL,instance=instance,
    sequence=request['sequence'],result={'status':'full-prefix-reconciled'})))
sys.stdout.buffer.flush()
'''
    parent=sidecar.Parent([sys.executable,'-B','-c',script],cwd=Path(__file__).parents[1])
    adapter,_,hooks,_=fixture(tmp_path)
    adapter.epoch=parent
    try:
        with pytest.raises((EOFError,BrokenPipeError,ValueError)):
            adapter.bootstrap()
        check(adapter.state == 'failed' and hooks.launches == 0 and not parent.live)
    finally:
        parent.invalidate();adapter.journal.close()


def test_real_private_ipc_timeout_fails_before_controller(tmp_path):
    sidecar=pytest.importorskip('tools.receipt_epoch.sidecar')
    import sys
    if sys.platform == 'darwin': pytest.skip('RLIMIT_AS private service requires Linux')
    script='''
import sys,time
from tools.receipt_epoch.sidecar import encode,_receive,AS_BYTES
from tools.receipt_epoch.epoch import PROTOCOL
instance='a'*64
sys.stdout.buffer.write(encode(dict(protocol=PROTOCOL,instance=instance,as_bytes=AS_BYTES)))
sys.stdout.buffer.flush()
request=_receive(sys.stdin.buffer)
sys.stdout.buffer.write(encode(dict(protocol=PROTOCOL,instance=instance,
    sequence=request['sequence'],result={'status':'full-prefix-reconciled'})))
sys.stdout.buffer.flush()
_receive(sys.stdin.buffer)
time.sleep(30)
'''
    parent=sidecar.Parent([sys.executable,'-B','-c',script],cwd=Path(__file__).parents[1])
    class FastDeadline:
        def call(self,operation,payload,*,seconds):
            check(seconds == 180)
            return parent.call(operation,payload,seconds=.05 if operation == 'prepare' else seconds)
        def invalidate(self): parent.invalidate()
    adapter,_,hooks,_=fixture(tmp_path)
    adapter.epoch=FastDeadline()
    try:
        with pytest.raises(TimeoutError): adapter.bootstrap()
        check(adapter.state == 'failed' and hooks.launches == 0 and not parent.live)
    finally:
        parent.invalidate();adapter.journal.close()


def test_full_private_ipc_to_saved_observer_path(tmp_path,monkeypatch):
    sidecar=pytest.importorskip('tools.receipt_epoch.sidecar')
    import sys
    if sys.platform == 'darwin': pytest.skip('RLIMIT_AS private service requires Linux')
    original=tmp_path/'original.json';original.write_text(json.dumps(dict(environment={})))
    first=tmp_path/'first.json';first.write_text(json.dumps(dict(historical_and_policy_pins=[],population={})))
    observer=tmp_path/'observer.py'
    observer.write_text('import json,pathlib,sys,hashlib\n'
        'p=json.loads(pathlib.Path(sys.argv[1]).read_text()); d=pathlib.Path(p["output_dir"])/'
        '(p["label"]+".observation.001")\n'
        'raw=json.dumps({"status":"registered","registry":{"path":"r"},'
        '"registration_return":{"path":"s"},"runtime_return":{"path":"t"}}).encode()\n'
        'f=d/"controller.stdout.json";f.write_bytes(raw)\n'
        '(d/"controller-observation.json").write_text(json.dumps({"exit_code":0,"launches":1,'
        '"automatic_retry":False,"stdout":{"path":str(f),"size_bytes":len(raw),'
        '"sha256":hashlib.sha256(raw).hexdigest()}}))\n')
    monkeypatch.setattr('tools.receipt_epoch.series_adapter.production_command',
        lambda *args,**kwargs:dict(schema='hiroute-epoch-series-command-v1',argv=['fake'],
            cwd=str(tmp_path),resource_plan={},maximum_launches=1,no_retry=True))
    plan=dict(launch_required=True,policy='first-32-outstanding-canonical-blocks-v1',
        completed_block_ids=[],expected_model_count=8192,window_id='W022',block_ids=list(range(32)))
    script='''
import sys
from tools.receipt_epoch import sidecar
class Micro:
 def __init__(self): self.pending=False
 @classmethod
 def establish(cls,**kwargs): return cls()
 def prepare(self,**kwargs):
  self.pending=True
  return {'token':{'private':'nonce'},'window_plan':PLAN,'previous_actual':{}}
 def cold(self,**kwargs):
  self.pending=False
  return {'completed_models':172288,'status':'incrementally-authenticated'}
 def request_pause(self): return {'at_safe_boundary':not self.pending}
 def invalidate(self): self.pending=False
class Origin:
 expected={'verifier_root':'.'}
 pins=[]
 def phase_check(self,deadline): pass
sidecar.Epoch=Micro;sidecar.SourceBinding=Origin
sidecar._live_checks=lambda *args,**kwargs:None
sidecar.serve(sys.stdin.buffer,sys.stdout.buffer,origin=Origin())
'''.replace('PLAN',repr(plan))
    parent=sidecar.Parent([sys.executable,'-B','-c',script],cwd=Path(__file__).parents[1])
    fixture_adapter,_,_,_=fixture(tmp_path/'fixture')
    hooks=ProductionHooks(suffix_window=object(),python=sys.executable,root=tmp_path,
        source_commit='a'*40,source_sha='b'*64,original_command=pin(original),
        original_preparation=pin(first),observer=pin(observer),source_check=lambda:None,
        idle_check=lambda:None,previous_argv=['old'],index=22,completed_models=172288)
    fixture_adapter.epoch=parent;fixture_adapter.hooks=hooks
    out=tmp_path/'new-output'
    targets=dict(attempt=str(tmp_path/'new-attempt'),registry=str(out/'window022.registry.json'),
        registration_return=str(out/'window022.registration-return.json'),
        runtime_return=str(out/'window022.registry.json.run-return.json'))
    try:
        fixture_adapter.bootstrap()
        fixture_adapter.run_one(targets)
        fixture_adapter.pause()
        check(parent.process.returncode == 0 and (out/'window022.observation.001'/'controller-observation.json').is_file())
        check(fixture_adapter.last_result['status'] == 'incrementally-authenticated')
    finally:
        parent.invalidate();fixture_adapter.journal.close()
