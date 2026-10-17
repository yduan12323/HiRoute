"""Caller-owned bounded energy evidence, separate from solver authorization.

No implicit threads or process exits. Background use requires an explicit caller
failure channel. A timeout reader always reports censored/unknown final health.
"""
import hashlib
import json
import os
import stat
from pathlib import Path
import threading
import time


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',', ':'),allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class ObservationError(RuntimeError):
    pass


def _publish(path,raw,*,immutable=False):
    path=Path(path)
    temporary=path.with_name('.'+path.name+'.pending')
    with temporary.open('xb') as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno())
    if immutable:
        os.link(temporary,path);temporary.unlink()
    else:os.replace(temporary,path)
    fd=os.open(path.parent,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)


def _read(path,limit):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size>limit:raise ValueError('Bounded regular evidence required')
        raw=stream.read(limit+1)
    if len(raw)>limit:raise ValueError('Evidence byte cap exceeded')
    return raw


def _loads(raw):
    def unique(pairs):
        value={}
        for key,item in pairs:
            if key in value:raise ValueError('Duplicate evidence field')
            value[key]=item
        return value
    return json.loads(raw,object_pairs_hook=unique)


class EnergyObservation:
    """Single-context evidence sink with a sticky, caller-visible error state.

    on_async_error(error) is an explicit caller-owned notification/termination
    contract. It must notify a supervising parent even during long native work.
    If it fails, both errors remain latched. No callback/no background sampling.
    The callback's absence at timeout is never proof that final health was good.
    """
    def __init__(self,output,*,run_identity,interval=0.25,on_async_error=None):
        if (type(run_identity) is not dict or not 1<=len(run_identity)<=32 or
                any(type(k) is not str or not k or len(k)>128 or type(v) is not str or len(v)>512
                    for k,v in run_identity.items()) or len(canonical(run_identity))>8192):
            raise ValueError('Bounded explicit caller-owned run identity required')
        if type(interval) not in (int,float) or not 0.01<=interval<=60:
            raise ValueError('Observation interval must be .01..60 seconds')
        if on_async_error is not None and not callable(on_async_error):
            raise ValueError('Explicit asynchronous failure callback required')
        self.output=Path(output);self.output.mkdir(parents=True,exist_ok=False)
        self.binding=canonical(run_identity);self.binding_sha=sha(self.binding)
        self.interval_ns=int(interval*1e9);self.on_async_error=on_async_error
        self.owner=threading.get_ident();self.pid=os.getpid();self.lock=threading.RLock()
        self.error=None;self.callback_error=None;self._error_lock=threading.Lock()
        self.role=None;self.mode=None;self.policy_sha=None;self.screen=None;self.guard=None
        self.certificate=None;self.query_sha=None;self.last_ns=None;self.sequence=0
        self.background_users=0
        self.final_complete=False;self.io_cpu_ns=0;self.io_wall_ns=0;self.setup={}

    def check(self):
        if self.pid!=os.getpid():raise ObservationError('Observation process changed')
        if self.error is not None:
            raise ObservationError('Energy observation failed: '+self.error+
                ('; callback failed: '+self.callback_error if self.callback_error else ''))

    def _fail(self,error):
        first=False
        with self._error_lock:
            if self.error is None:self.error=type(error).__name__+': '+str(error);first=True
        if first and threading.get_ident()!=self.owner and self.on_async_error is not None:
            try:self.on_async_error(ObservationError(self.error))
            except BaseException as failure:self.callback_error=type(failure).__name__+': '+str(failure)
        self.check()

    def bind_context(self,config,role,policy,owned):
        self.check()
        if self.role is not None or threading.get_ident()!=self.owner:
            raise ObservationError('One owner-thread context per observation')
        self.role=role;self.mode='on' if config.terminal_energy is not None else 'off'
        self.policy_sha=None if policy is None else sha(canonical(policy))
        if owned is not None:self.setup=dict(graph_copy_cpu_ns=owned.copy_cpu_ns,
            graph_copy_wall_ns=owned.copy_wall_ns,graph_copy_retained_bytes=32*owned.edge_count)
        self.sample(force=True)

    def bind_guard(self,guard):
        self.check();self.guard=guard
        self.setup.update(guard_install_cpu_ns=guard.install_cpu_ns,guard_install_wall_ns=guard.install_wall_ns)

    def activated(self,screen):
        self.check()
        if self.role!='search' or self.mode!='on' or self.screen is not None:
            raise ObservationError('Unexpected screen activation')
        self.screen=screen;self.query_sha=screen.query_sha256
        receipt=json.loads(screen._receipt_bytes)
        for key in ('setup_cpu_ns','setup_wall_ns','build_with_first_validation_cpu_ns',
                'build_with_first_validation_wall_ns','second_validation_cpu_ns','second_validation_wall_ns',
                'activation_cpu_ns','activation_wall_ns','construction_packed_scratch_bytes','construction_potential_bytes'):
            if key in receipt:self.setup[key]=receipt[key]
        record=dict(schema='hiroute.package_energy_certificate.v1',run_identity_sha256=self.binding_sha,
            policy_sha256=self.policy_sha,created_monotonic_ns=time.monotonic_ns(),receipt=receipt)
        raw=canonical(record)
        try:
            if len(raw)>262144:raise ObservationError('Certificate byte cap exceeded')
            cpu,wall=time.thread_time_ns(),time.monotonic_ns()
            _publish(self.output/'certificate.json',raw,immutable=True)
            self.setup.update(certificate_publication_cpu_ns=time.thread_time_ns()-cpu,
                certificate_publication_wall_ns=time.monotonic_ns()-wall)
            self.certificate=dict(filename='certificate.json',sha256=sha(raw))
            self.sample(force=True)
        except BaseException as error:self._fail(error)

    def inactive_problem(self,problem):
        self.check()
        if self.role=='search':self.query_sha=sha(canonical(problem.case))
        self.sample(force=True)

    def sample(self,*,force=False):
        self.check()
        background=threading.get_ident()!=self.owner
        if background and self.on_async_error is None:
            self._fail(ObservationError('Background evidence requires a caller failure channel'))
        try:
            with self.lock:
                self.check();now=time.monotonic_ns()
                if self.last_ns is not None and now<self.last_ns:raise ObservationError('Monotonic clock moved backward')
                if not force and self.last_ns is not None and now-self.last_ns<self.interval_ns:return None
                calls,completed,rejected,status=(0,0,0,'inactive') if self.screen is None else self.screen._observation_state
                gs,pending,guarded=('inactive',0,0) if self.guard is None else self.guard._observation_state
                if not 0<=rejected<=completed<=calls or calls-completed>1 or not 0<=pending<=2:
                    raise ObservationError('Invalid sampled counter state')
                if status=='error' or gs=='invalid':raise ObservationError('Screen or routing operation failed')
                lifecycle='inactive' if self.screen is None else 'validated' if status=='active' else 'disabled'
                value=dict(schema='hiroute.package_energy_status.v1',run_identity=json.loads(self.binding),
                    run_identity_sha256=self.binding_sha,policy_sha256=self.policy_sha,role=self.role,
                    mode=self.mode,lifecycle=lifecycle,query_sha256=self.query_sha,certificate=self.certificate,
                    sequence=self.sequence+1,sampled_monotonic_ns=now,snapshot_interval_ns=self.interval_ns,
                    final_complete=self.final_complete,counters=dict(calls_started=calls,decisions_completed=completed,
                        rejected_immediate_finishes=rejected,guard_pending_operations=pending,guarded_operations_completed=guarded),
                    counter_coherence='screen and routing tuples independently sampled',setup=self.setup,
                    observer_io_cpu_ns=self.io_cpu_ns,observer_io_wall_ns=self.io_wall_ns,
                    observer_io_scope='previous completed publications only; excludes current write, serialization, throttle and lock wait')
                raw=canonical(value)
                if len(raw)>16384:raise ObservationError('Status byte cap exceeded')
                cpu,wall=time.thread_time_ns(),time.monotonic_ns()
                _publish(self.output/'status.json',raw)
                self.io_cpu_ns+=time.thread_time_ns()-cpu;self.io_wall_ns+=time.monotonic_ns()-wall
                self.sequence+=1;self.last_ns=now
                return dict(path=str(self.output/'status.json'),sha256=sha(raw))
        except BaseException as error:self._fail(error)

    def complete(self,context):
        self.check()
        if (context.observation is not self or not context._closed or not context._verified_close
                or threading.get_ident()!=self.owner or self.background_users):
            raise ObservationError('Authenticated context closure and stopped heartbeat required')
        if self.screen is not None and (self.screen.calls!=self.screen.completed or self.guard.pending):
            raise ObservationError('Outstanding operation cannot be complete')
        self.final_complete=True
        try:
            result=self.sample(force=True)
            # Commit only after status publication and its directory fsync. The
            # final link is the last fallible operation; lost crash durability
            # of this name rejects completeness safely. Keep its staging file.
            raw=canonical(dict(schema='hiroute.package_energy_complete.v1',
                status_sha256=result['sha256'],run_identity_sha256=self.binding_sha))
            temporary=self.output/'.complete.pending'
            with temporary.open('xb') as stream:
                stream.write(raw);stream.flush();os.fsync(stream.fileno())
            os.link(temporary,self.output/'complete.json')
            return result
        except BaseException as error:
            self.final_complete=False
            self._fail(error)


def read_status(path,*,expected_sha256,run_identity,now_ns,terminated,clean_outcome_authenticated=False):
    """Descriptive parsing after caller-verified cleanup, never continuation authority.

    `terminated=True` always overrides a worker complete flag: the interval is
    censored and health remains unknown. Observed failures independently prevail.
    """
    if type(terminated) is not bool or type(clean_outcome_authenticated) is not bool:
        raise ValueError('Explicit caller outcome flags required')
    if terminated and clean_outcome_authenticated:raise ValueError('Conflicting termination and clean outcome')
    path=Path(path)
    raw=_read(path,16384)
    if sha(raw)!=expected_sha256:raise ValueError('Status bytes differ')
    v=_loads(raw)
    if (v['schema']!='hiroute.package_energy_status.v1' or v['run_identity']!=run_identity
            or v['run_identity_sha256']!=sha(canonical(run_identity)) or type(v['final_complete']) is not bool
            or type(now_ns) is not int or type(v['sampled_monotonic_ns']) is not int
            or not 0<=v['sampled_monotonic_ns']<=now_ns):raise ValueError('Status binding/clock differs')
    if v['certificate'] is not None:
        ref=v['certificate']
        if ref['filename']!='certificate.json':raise ValueError('Fixed certificate name required')
        p=path.parent/ref['filename']
        data=_read(p,262144);cert=_loads(data)
        if (sha(data)!=ref['sha256'] or cert['run_identity_sha256']!=v['run_identity_sha256']
                or cert['policy_sha256']!=v['policy_sha256']
                or cert['receipt']['query_sha256']!=v['query_sha256']
                or cert['created_monotonic_ns']>v['sampled_monotonic_ns']):raise ValueError('Certificate binding differs')
    committed=False
    if v['final_complete']:
        commit=path.parent/'complete.json'
        try:record=_loads(_read(commit,1024))
        except FileNotFoundError:
            if clean_outcome_authenticated:raise ValueError('Clean outcome lacks completion commit')
            record=None  # interruption between durable status and commit
        if record is not None:
            if record!=dict(schema='hiroute.package_energy_complete.v1',
                    status_sha256=expected_sha256,run_identity_sha256=v['run_identity_sha256']):
                raise ValueError('Changed completion commit')
            committed=True
    counters=v['counters']
    if any(type(x) is not int or x<0 for x in counters.values()):raise ValueError('Invalid counters')
    if not counters['rejected_immediate_finishes']<=counters['decisions_completed']<=counters['calls_started']:
        raise ValueError('Counter order differs')
    return dict(sample=v,lag_ns=now_ns-v['sampled_monotonic_ns'],completion_committed=committed,censored=bool(terminated or not clean_outcome_authenticated or not committed),
        final_health='unknown' if terminated or not clean_outcome_authenticated or not committed else 'caller_authenticated_clean_outcome',
        authority='descriptive only; caller must verify cleanup, exit/error channel, resource gates and full expected certificate')


from .exact_progress import ExactSearchProgress

class EnergyProgress(ExactSearchProgress):
    """Reuse the ordinary heartbeat with an explicit external error contract."""
    def __init__(self,*args,energy_observation,**kwargs):
        if type(energy_observation) is not EnergyObservation or energy_observation.on_async_error is None:
            raise ValueError('Energy heartbeat requires explicit caller failure notification')
        self.energy_observation=energy_observation
        super().__init__(*args,**kwargs)

    def _reset_active(self):
        from .exact_progress import _active
        if _active.get() is self:_active.reset(self.token)

    def __enter__(self):
        self.energy_observation.check()
        self.energy_observation.background_users+=1
        try:return super().__enter__()
        except BaseException:
            self.stop.set()
            if getattr(self,'thread_started',False):self.thread.join()
            self._reset_active()
            self.energy_observation.background_users-=1
            raise

    def __exit__(self,cls,error,tb):
        try:return super().__exit__(cls,error,tb)
        except BaseException as publication_error:
            # Preserve the solver's original exception, while making the
            # independent persistence failure sticky and caller-visible.
            try:self.energy_observation._fail(publication_error)
            except ObservationError:pass
            if error is None:raise
            return False
        finally:
            self._reset_active()
            self.energy_observation.background_users-=1

    def persist(self):
        super().persist()
        self.energy_observation.sample()
