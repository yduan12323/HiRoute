"""Review draft: fail-stop orchestration around an already attested private epoch.

The caller owns source attestation, the exclusive series lock, the unchanged
controller/observer implementation, and independent pins for retained returns.
No report in the journal can restore an epoch. Every invocation first establishes
017 and cold-authenticates 018--021 (plus any later retained registrations).
"""
import hashlib
import ctypes
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
from . import origin

OBSERVER_ENVELOPE_SECONDS = 1200
OBSERVER_CLEANUP_GRACE_SECONDS = 10


def _subreaper(value):
    """Process-local Linux adoption of this launch's orphaned descendants."""
    libc=ctypes.CDLL(None,use_errno=True)
    previous=ctypes.c_int()
    if libc.prctl(37,ctypes.byref(previous),0,0,0)!=0:
        raise OSError(ctypes.get_errno(),'read child subreaper state')
    if libc.prctl(36,int(value),0,0,0)!=0:
        raise OSError(ctypes.get_errno(),'set child subreaper state')
    return previous.value


def _process_rows():
    rows={}
    for path in Path('/proc').iterdir():
        if not path.name.isdigit(): continue
        try:
            if path.stat().st_uid!=os.getuid(): continue
            fields=(path/'stat').read_text().rsplit(')',1)[1].split()
            rows[int(path.name)]=dict(state=fields[0],ppid=int(fields[1]),
                pgid=int(fields[2]),sid=int(fields[3]),start=int(fields[19]))
        except (OSError,ValueError,IndexError): continue
    return rows


def _extend_owned(owned, observer_pid, observer_start, baseline):
    rows=_process_rows()
    if observer_pid in rows and rows[observer_pid]['start']==observer_start:
        owned[observer_pid]=observer_start
    for _ in range(len(rows)+1):
        new={pid:row['start'] for pid,row in rows.items() if row['state']!='Z' and
             (row['ppid'] in owned and rows.get(row['ppid'],{}).get('start')==owned[row['ppid']])}
        if all(owned.get(pid)==start for pid,start in new.items()): break
        owned.update(new)
    # Subreaper adoption: only later-created, independent-session children.
    for pid,row in rows.items():
        if row['ppid']==os.getpid() and (pid not in baseline or baseline[pid]!=row['start']) and \
           row['start']>=observer_start and row['sid']!=os.getsid(0) and pid!=observer_pid:
            owned[pid]=row['start']
    return rows


class AdmissionError(RuntimeError):
    pass


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()+b'\n'


def pin(path, *, limit=16*1024**2):
    _, row, _ = origin.consume(path, limit=limit)
    return row


def pinned_json(row, limit):
    if (type(row) is not dict or set(row) != {'path', 'size_bytes', 'sha256'} or
        type(row['size_bytes']) is not int or not 0 <= row['size_bytes'] <= limit):
        raise AdmissionError('invalid independently pinned input')
    raw, actual, _ = origin.consume(row['path'], limit=limit)
    if actual != row:
        raise AdmissionError('independently pinned input changed')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise AdmissionError('duplicate JSON key')
            result[key] = value
        return result
    def nonfinite(_):
        raise AdmissionError('nonfinite JSON')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)


def sealed_script(row):
    """Return an anonymous read-only fd with the independently pinned bytes."""
    raw, actual, _ = origin.consume(row['path'], limit=2*1024**2)
    if actual != row: raise AdmissionError('saved observer bytes changed before execution')
    with tempfile.TemporaryFile(prefix='hiroute-pinned-observer-') as staged:
        staged.write(raw);staged.flush();os.fsync(staged.fileno())
        os.fchmod(staged.fileno(),0o400)
        fd=os.open(f'/proc/self/fd/{staged.fileno()}',os.O_RDONLY|os.O_CLOEXEC)
    try:
        if hashlib.sha256(os.read(fd,len(raw)+1)).digest() != hashlib.sha256(raw).digest():
            raise AdmissionError('anonymous observer byte copy changed')
        os.lseek(fd,0,os.SEEK_SET)
        return fd
    except BaseException:
        os.close(fd); raise


def production_command(suffix_window, previous_argv, previous_actual, private_plan,
                       targets, *, python, root, source_commit, source_sha):
    """Apply the original series driver's exact parser/input_context path.

    `suffix_window` must be imported from the independently attested frozen
    verifier, and `previous_argv` from an authenticated controller return.
    The caller checks source, policy, population, and the private plan first.
    """
    if type(previous_argv) is not list or previous_argv[1:4] != ['-B','-m',suffix_window.MODULE]:
        raise AdmissionError('previous production command shape changed')
    Adapter._fresh_targets(targets)
    args = suffix_window.parser().parse_args(previous_argv[4:])
    args.bootstrap = args.bootstrap_sha = args.maximum_blocks = None
    for key in suffix_window.SEED_FIELDS: setattr(args,key,None)
    for option, actual_key in (('registry','registry'),('registry_return','registration_return')):
        setattr(args,option,Path(previous_actual[actual_key]['path']))
        setattr(args,option+'_sha',previous_actual[actual_key]['sha256'])
    args.attempt_dir = Path(targets['attempt'])
    args.registry_output = Path(targets['registry'])
    args.registration_return_output = Path(targets['registration_return'])
    if str(suffix_window.runtime_return_path(args)) != targets['runtime_return']:
        raise AdmissionError('planned runtime return path differs from production controller')
    argv=[str(python),'-B','-m',suffix_window.MODULE]
    for key,value in suffix_window.input_context(args).items():
        if value is None: continue
        argv.append('--'+key.replace('_','-'))
        if key == 'worker_cpus': argv.extend(map(str,value))
        else: argv.append(str(value))
    argv += ['--cpu',str(args.cpu),'--attempt-dir',str(args.attempt_dir)]
    parsed = suffix_window.parser().parse_args(argv[4:])
    if (suffix_window.admission_mode(parsed) != 'registry' or parsed.maximum_blocks is not None or
        '--maximum-blocks' in argv or '--bootstrap' in argv or len(args.worker_cpus) != 5):
        raise AdmissionError('ordinary five-CPU continuation changed')
    resource_plan=suffix_window.resource_plan(args.worker_cpus, private_plan['expected_model_count'])
    if resource_plan['persistent_workers'] != 4:
        raise AdmissionError('ordinary four-LP-worker resource plan changed')
    return dict(schema='hiroute-epoch-series-command-v1',argv=argv,cwd=str(root),
        source_commit=source_commit,source_sha256=source_sha,window_plan=private_plan,
        resource_plan=resource_plan,previous_return_pins=list(previous_actual.values()),
        ordinary_continuation=True,maximum_launches=1,no_retry=True,
        standard_controller_seconds=900,controller_as_bytes=512*1024**2,
        group_rss_bytes=20*1024**3,persistent_workers=4,
        metadata_as_bytes=2*1024**3,metadata_deadline_seconds=180)


def run_controller_once(command, observation_dir, *, environment, timeout=900):
    """One local subprocess observation; no retry and no metadata deadline on LP.

    The frozen controller owns its runtime/resource guards. This observer records
    an exit, stdout, stderr, and the actual registered return if present.
    """
    if timeout != 900 or command.get('maximum_launches') != 1 or command.get('no_retry') is not True:
        raise AdmissionError('standard numerical launch contract changed')
    observation_dir=Path(observation_dir)
    observation_dir.mkdir(mode=0o700,parents=False,exist_ok=False)
    manifest=observation_dir/'launch-manifest.json'
    with manifest.open('xb') as out: out.write(_canonical(command))
    start=time.monotonic()
    stdout=observation_dir/'controller.stdout.json'
    stderr=observation_dir/'controller.stderr.txt'
    with stdout.open('xb') as out, stderr.open('xb') as err:
        process=subprocess.Popen(command['argv'],cwd=command['cwd'],env=environment,
                                 stdout=out,stderr=err,start_new_session=True)
        try: code=process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGTERM)
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL);process.wait()
            code=process.returncode
            timed_out=True
        else: timed_out=False
    observation=dict(schema='hiroute-epoch-series-observation-v1',exit_code=code,
        timed_out=timed_out,wall_seconds=time.monotonic()-start,stdout=pin(stdout),stderr=pin(stderr),
        launch_manifest=pin(manifest),launches=1,automatic_retry=False)
    with (observation_dir/'controller-observation.json').open('xb') as out: out.write(_canonical(observation))
    if timed_out or code != 0: raise AdmissionError('controller failed; original observation retained')
    returned=pinned_json(observation['stdout'],4*1024**2)
    if returned.get('status') != 'registered' or not all(key in returned for key in
        ('registry','registration_return','runtime_return')):
        raise AdmissionError('controller omitted actual registered return')
    return observation, {key:returned[key] for key in ('registry','registration_return','runtime_return')}


class ProductionHooks:
    """Bind the private plan to the unchanged saved series observer interface.

    The caller supplies independently pinned source, policy, original command,
    preparation, and observer paths. These callbacks never authenticate receipts;
    only the private epoch's cold admission may do that.
    """
    def __init__(self, *, suffix_window, python, root, source_commit, source_sha,
                 original_command, original_preparation, observer, source_check,
                 idle_check, previous_argv, index, completed_models, observer_source=None):
        self.suffix_window=suffix_window; self.python=str(python); self.root=Path(root)
        self.source_commit=source_commit; self.source_sha=source_sha
        self.original_command=original_command; self.original_preparation=original_preparation
        self.observer=observer; self._source_check=source_check; self._idle_check=idle_check
        self.observer_source=observer_source or observer
        self.previous_argv=previous_argv; self.index=index; self.completed_models=completed_models
        self.prepared_path=None
        self.command_row=None

    def source_check(self):
        self._source_check()
        for row in (self.original_command,self.original_preparation,self.observer,self.observer_source):
            if pin(row['path']) != row: raise AdmissionError('saved production interface changed')

    def idle_check(self): self._idle_check()

    def prepare(self, private, targets):
        plan=private['window_plan']; previous=private['previous_actual']
        if not plan['launch_required'] or plan['policy'] != 'first-32-outstanding-canonical-blocks-v1':
            raise AdmissionError('private default selector did not authorize a window')
        label=f'window{self.index:03d}'
        out=Path(targets['registry']).parent
        if out.exists() or Path(targets['registration_return']).parent != out:
            raise AdmissionError('exclusive new output directory required')
        out.mkdir(mode=0o700,parents=False,exist_ok=False)
        original=pinned_json(self.original_command,4*1024**2)
        first=pinned_json(self.original_preparation,4*1024**2)
        command=production_command(self.suffix_window,self.previous_argv,previous,plan,targets,
            python=self.python,root=self.root,source_commit=self.source_commit,source_sha=self.source_sha)
        command['environment']=original['environment']
        command_path=out/(label+'.command.json')
        with command_path.open('xb') as stream: stream.write(_canonical(command))
        preparation=dict(status='private-epoch-default-window-prepared',source_commit=self.source_commit,
            source_sha256=self.source_sha,source_files=119,command=pin(command_path),
            actual_previous_returns=list(previous.values()),
            historical_and_policy_pins=first['historical_and_policy_pins'],
            previous_completed_blocks=plan['completed_block_ids'],
            previous_completed_models=self.completed_models,population=first['population'],
            window_plan=plan,resource_plan=command['resource_plan'],
            metadata_as_bytes=2*1024**3,metadata_deadline_seconds=180,new_lp_calls=0)
        preparation_path=out/'preparation.json'
        with preparation_path.open('xb') as stream: stream.write(_canonical(preparation))
        prepared=dict(terminal=False,index=self.index,label=label,output_dir=str(out),
            command=pin(command_path),preparation=pin(preparation_path),
            attempt_dir=targets['attempt'],window_id=plan['window_id'],
            block_ids=plan['block_ids'],expected_models=plan['expected_model_count'],
            preparation_seconds=0)
        self.prepared_path=out/'prepared.json'
        with self.prepared_path.open('xb') as stream: stream.write(_canonical(prepared))
        self.command_row=pin(command_path)
        return dict(command=self.command_row,preparation=pin(preparation_path),
                    prepared=pin(self.prepared_path),observer=self.observer,
                    observer_source=self.observer_source)

    def advance(self, result):
        if self.command_row is None or result.get('status') != 'incrementally-authenticated':
            raise AdmissionError('cannot advance without a cold-authenticated command')
        command=pinned_json(self.command_row,4*1024**2)
        if command['source_commit'] != self.source_commit or command['source_sha256'] != self.source_sha:
            raise AdmissionError('next command source changed')
        if result['actual']['registry']['path'] != command['argv'][command['argv'].index('--registry-output')+1]:
            raise AdmissionError('cold result differs from prepared command')
        if result['completed_models'] != self.completed_models+command['window_plan']['expected_model_count']:
            raise AdmissionError('cold model total differs from private selected window')
        self.previous_argv=command['argv']
        self.completed_models=result['completed_models']
        self.index+=1
        self.prepared_path=None
        self.command_row=None

    def launch(self, command):
        if self.prepared_path is None or pin(self.prepared_path) != command['prepared']:
            raise AdmissionError('prepared observer handoff changed')
        out=Path(self.prepared_path).parent; label=f'window{self.index:03d}'
        obs=out/(label+'.observation.001')
        obs.mkdir(mode=0o700,exist_ok=False)
        # The exact reviewed bytes, not a mutable pathname, become the script
        # read by Python. The sealed fd is inherited only by the observer.
        script_fd=sealed_script(self.observer_source)
        argv=[self.python,'-B',f'/proc/self/fd/{script_fd}',str(self.prepared_path),
              command['prepared']['sha256'],str(command['prepared']['size_bytes'])]
        with (obs/'observer.stdout.txt').open('xb') as stdout, (obs/'observer.stderr.txt').open('xb') as stderr:
            old_subreaper=_subreaper(1)
            process=None;owned={}
            baseline={pid:row['start'] for pid,row in _process_rows().items() if row['ppid']==os.getpid()}
            try:
                process=subprocess.Popen(argv,cwd=self.root,stdout=stdout,stderr=stderr,
                    start_new_session=True,pass_fds=(script_fd,))
                os.close(script_fd)
                script_fd=None
                rows=_process_rows()
                observer_start=rows[process.pid]['start']
                owned[process.pid]=observer_start
                deadline=time.monotonic()+OBSERVER_ENVELOPE_SECONDS  # controller retains its 900 s guard
                caps=((obs/'observer.stdout.txt',16*1024**2),
                      (obs/'observer.stderr.txt',16*1024**2),
                      (obs/'samples.jsonl',64*1024**2))
                def output_exceeded():
                    return any(path.exists() and path.stat().st_size>cap for path,cap in caps)
                while process.poll() is None:
                    _extend_owned(owned,process.pid,observer_start,baseline)
                    if time.monotonic() >= deadline or output_exceeded():
                        raise TimeoutError('observer envelope or output cap exceeded')
                    time.sleep(.5)
                if time.monotonic() >= deadline or output_exceeded():
                    raise TimeoutError('observer envelope or output cap exceeded at completion')
                code=process.returncode
                rows=_extend_owned(owned,process.pid,observer_start,baseline)
                if any(pid!=process.pid and rows.get(pid,{}).get('start')==start and
                       rows[pid]['state']!='Z' for pid,start in owned.items()):
                    raise AdmissionError('observer exited with owned descendants still running')
                if code != 0: raise AdmissionError('saved observer failed; no retry')
            except BaseException:
                if process is not None:
                    self._stop_observer_tree(process,owned,observer_start,baseline)
                raise
            finally:
                if script_fd is not None: os.close(script_fd)
                _subreaper(old_subreaper)
        observed=pin(obs/'controller-observation.json')
        return dict(observer_return=observed,observer_stdout=pin(obs/'observer.stdout.txt'),
                    observer_stderr=pin(obs/'observer.stderr.txt'))

    def _stop_observer_tree(self, process, owned, observer_start, baseline):
        """Signal only recorded pid/start identities, including separate sessions."""
        end=time.monotonic()+OBSERVER_CLEANUP_GRACE_SECONDS
        for sig in (signal.SIGTERM,signal.SIGKILL):
            while True:
                rows=_extend_owned(owned,process.pid,observer_start,baseline)
                live=[pid for pid,start in owned.items() if rows.get(pid,{}).get('start')==start and
                      rows[pid]['state']!='Z']
                if not live: break
                for pid in sorted(live,reverse=True):
                    # Recheck identity immediately before signaling; never kill a reused PID.
                    fresh=_process_rows().get(pid)
                    if fresh is not None and fresh['start']==owned[pid] and fresh['state']!='Z':
                        try: os.kill(pid,sig)
                        except ProcessLookupError: pass
                if sig==signal.SIGKILL or time.monotonic()>=end: break
                time.sleep(.1)
        try: process.wait(timeout=2)
        except subprocess.TimeoutExpired: pass
        rows=_extend_owned(owned,process.pid,observer_start,baseline)
        if any(rows.get(pid,{}).get('start')==start and rows[pid]['state']!='Z'
               for pid,start in owned.items()):
            raise AdmissionError('identified observer descendants survived cleanup')

    def cold(self, observed, command):
        row=pinned_json(observed['observer_return'],4*1024**2)
        if row.get('exit_code') != 0 or row.get('launches') != 1 or row.get('automatic_retry') is not False:
            raise AdmissionError('observer did not record one successful controller')
        stdout=row['stdout']; returned=pinned_json(stdout,4*1024**2)
        if returned.get('status') != 'registered': raise AdmissionError('controller did not register')
        return {key:returned[key] for key in ('registry','registration_return','runtime_return')}


class Journal:
    """Exclusive, append-only evidence; never used as authentication authority."""
    def __init__(self, directory, *, launch_ledger=None):
        self.directory = Path(directory)
        self.directory.mkdir(mode=0o700, parents=False, exist_ok=False)
        self.path = self.directory/'events.jsonl'
        self.stream = self.path.open('xb')
        self.launch_ledger = Path(launch_ledger) if launch_ledger is not None else None

    def append(self, event):
        raw = _canonical(event)
        if self.stream.tell()+len(raw) > 16*1024**2:
            raise AdmissionError('adapter journal cap')
        self.stream.write(raw); self.stream.flush(); os.fsync(self.stream.fileno())

    def close(self):
        self.stream.close()

    def claim_launch(self, plan, command):
        if self.launch_ledger is None: return
        # The whole private plan binds window id, canonical block selection,
        # population commitment and selector policy. Paths/index are excluded.
        key=hashlib.sha256(_canonical(dict(plan=plan,budgets=dict(
            controller_seconds=900,controller_as_bytes=512*1024**2,
            group_rss_bytes=20*1024**3,metadata_seconds=180,
            metadata_as_bytes=2*1024**3,persistent_workers=4)))).hexdigest()
        marker=self.launch_ledger/('plan-'+key+'.launch-intent.json')
        with marker.open('xb') as stream:
            stream.write(_canonical(dict(schema='hiroute-epoch-series-launch-intent-v1',
                                         plan_sha256=key,window_id=plan['window_id'],
                                         journal=str(self.path),command=command,
                                         automatic_retry=False)))
            stream.flush(); os.fsync(stream.fileno())
        directory=os.open(self.launch_ledger,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try: os.fsync(directory)
        finally: os.close(directory)


class Adapter:
    """One process lifetime; callbacks must bind the frozen production controller.

    `prepare` receives the private plan and targets and must create a fresh,
    exclusive command and manifest. `launch` executes that exact command once
    through the original observer. `cold` extracts actual three pins only from
    an observed successful controller return; it never accepts a status file.
    """
    def __init__(self, epoch, journal, retained, prefix, hooks):
        self.epoch, self.journal, self.retained, self.prefix, self.hooks = epoch, journal, retained, prefix, hooks
        self.state = 'new'; self.last_result = None

    def _call(self, operation, payload):
        result = self.epoch.call(operation, payload, seconds=180)
        self.journal.append(dict(operation=operation, result=result))
        return result

    def bootstrap(self):
        if self.state != 'new': raise AdmissionError('bootstrap is one-shot')
        try:
            self.hooks.source_check()
            self.hooks.idle_check()
            self._call('establish', self.prefix)
            for row in self.retained:
                returned = pinned_json(row, 4*1024**2)
                if returned.get('status') != 'registered': raise AdmissionError('retained controller return is not registered')
                actual = {key: returned[key] for key in ('registry','registration_return','runtime_return')}
                metadata = pinned_json(actual['registry'], 16*1024**2)
                targets = {key: actual[key]['path'] for key in actual}
                targets['attempt'] = metadata['entries'][-1]['attempt']
                prepared = self._call('prepare', dict(targets=targets))
                self.last_result = self._call('cold', dict(token=prepared['token'], actual=actual))
            self.state = 'ready'
        except BaseException as error:
            self.fail(error)
            raise

    def run_one(self, targets, stop_requested=lambda: False):
        if self.state != 'ready': raise AdmissionError('adapter is not at a safe boundary')
        self.state = 'in-flight'
        try:
            self.hooks.source_check(); self.hooks.idle_check()
            self._fresh_targets(targets)
            if stop_requested():
                self.journal.append(dict(operation='pause-before-prepare'))
                self.state='ready'
                return None
            prepared = self._call('prepare', dict(targets=targets))
            if prepared['window_plan']['launch_required'] is False:
                if prepared.get('terminal') is not True:
                    raise AdmissionError('private terminal plan omitted terminal marker')
                self.journal.append(dict(operation='terminal-no-launch',
                    completed_models=self.last_result['completed_models'],
                    completed_blocks=self.last_result['completed_blocks']))
                self.state='ready'
                return None
            if stop_requested():
                return self._cancel_prepared(prepared,'after-private-prepare')
            command = self.hooks.prepare(prepared, targets)
            self._fresh_targets(targets)
            self.journal.append(dict(operation='command-prepared', command=command))
            if stop_requested():
                return self._cancel_prepared(prepared,'before-launch-intent')
            # Journal the launch intent before any controller process can exist.
            self.journal.claim_launch(prepared['window_plan'],command)
            self.journal.append(dict(operation='launch-intent', command=command))
            observed = self.hooks.launch(command)
            self.journal.append(dict(operation='observed', observation=observed))
            actual = self.hooks.cold(observed, command)
            result = self._call('cold', dict(token=prepared['token'], actual=actual))
            self.last_result = result
            self.hooks.source_check(); self.hooks.idle_check()
            self.state = 'ready'
            return result
        except BaseException as error:
            self.fail(error)
            raise

    def _cancel_prepared(self, prepared, stage):
        returned=self._call('cancel-prepared',dict(token=prepared['token']))
        if returned != dict(cancelled=True,at_safe_boundary=True,numerical_launch=False):
            raise AdmissionError('private pending prepare did not cancel at safe boundary')
        self.journal.append(dict(operation='abandoned-prepared-no-launch',stage=stage,
            token_sha256=hashlib.sha256(_canonical(prepared['token'])).hexdigest()))
        self.state='ready'
        return None

    @staticmethod
    def _fresh_targets(targets):
        required = {'attempt', 'registry', 'registration_return', 'runtime_return'}
        if type(targets) is not dict or set(targets) != required:
            raise AdmissionError('exact fresh output targets required')
        paths = [Path(value) for value in targets.values()]
        if len(set(paths)) != 4 or any(path.exists() or path.is_symlink() or
                                      path.with_name(path.name+'.partial').exists() for path in paths):
            raise AdmissionError('output target is already occupied')

    def run_bounded(self, targets_list, stop_requested):
        if self.state != 'ready' or not 1 <= len(targets_list) <= 4:
            raise AdmissionError('bounded continuation requires a ready private epoch')
        try:
            for targets in targets_list:
                if stop_requested(): break
                result=self.run_one(targets,stop_requested)
                if result is None: break
                self.hooks.advance(result)
            self.pause()
        except BaseException as error:
            if self.state != 'failed': self.fail(error)
            raise

    def pause(self):
        if self.state != 'ready': raise AdmissionError('pause requires completed cold')
        try:
            self._call('pause', {})
            self._call('close', {})
            self.state = 'closed'
            self.journal.append(dict(operation='safe-pause', collector_started=False,
                final_independent_reconcile_required=True,query_optimum_certified=False,
                literal_G8_closed=False))
        except BaseException as error:
            self.fail(error)
            raise
        finally:
            self.epoch.invalidate()

    def fail(self, error):
        self.state = 'failed'
        self.epoch.invalidate()
        self.journal.append(dict(operation='failed-stopped', error_type=type(error).__name__,
                                 message=str(error), automatic_retry=False))
