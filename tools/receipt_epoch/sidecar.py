"""Private pipe service and watchdog for review-only receipt epoch operations.

No sockets, numerical launcher, disk resume, or real-series CLI are provided.
The owning parent must independently attest the process/code and caller pins.
Each request has a fresh absolute deadline shared on one host's monotonic clock.
Only this metadata-only child is signalled on protocol/timeout failure.
"""
import json
import hashlib
import math
import os
import resource
import secrets
import select
import signal
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from experiments.time_cut_v2.recorded_real import plan as binding
from experiments.time_cut_v2.recorded_real.archive_reader import _pairs, _nonfinite

from .epoch import Epoch, PROTOCOL
from .origin import SourceBinding, digest as source_digest
from experiments.time_cut_v2.recorded_real.runtime import BATCH_REPLAY, _live_checks

MAX_FRAME = 4*1024**2
AS_BYTES = 2*1024**3
STDERR_BYTES = 64*1024


def encode(value):
    raw = binding.canonical(value)
    binding.require(len(raw) <= MAX_FRAME, 'epoch IPC frame cap')
    return struct.pack('!I', len(raw))+raw


def decode(raw):
    return json.loads(raw, object_pairs_hook=_pairs, parse_constant=_nonfinite)


def _blocking_read(stream, count):
    chunks = []
    while count:
        raw = stream.read(count)
        if not raw:
            raise EOFError('epoch private pipe closed')
        count -= len(raw); chunks.append(raw)
    return b''.join(chunks)


def _receive(stream):
    count, = struct.unpack('!I', _blocking_read(stream, 4))
    binding.require(0 < count <= MAX_FRAME, 'epoch IPC frame cap')
    return decode(_blocking_read(stream, count))


def serve(reader, writer, *, origin):
    """Any exception/EOF/reply failure invalidates the entire in-memory epoch."""
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    ceiling = min([AS_BYTES]+[v for v in (soft, hard) if v != resource.RLIM_INFINITY])
    resource.setrlimit(resource.RLIMIT_AS, (ceiling, ceiling))
    instance, epoch, sequence = secrets.token_hex(32), None, 0
    try:
        binding.require(type(origin) is SourceBinding, 'independently bound tool/verifier source origin required')
        writer.write(encode(dict(protocol=PROTOCOL, instance=instance, as_bytes=ceiling,
                                 source_contract_sha=source_digest(origin.expected))))
        writer.flush()
        while True:
            request = _receive(reader)
            binding.require(type(request) is dict and set(request) ==
                {'protocol', 'instance', 'sequence', 'operation', 'deadline', 'payload'}, 'epoch exact IPC request required')
            binding.require(request['protocol'] == PROTOCOL and request['instance'] == instance and
                type(request['sequence']) is int and request['sequence'] == sequence+1, 'epoch stale or foreign IPC request')
            sequence += 1
            deadline = request['deadline']
            binding.require(type(deadline) is float and math.isfinite(deadline) and
                time.monotonic() < deadline <= time.monotonic()+180, 'epoch fresh IPC deadline required')
            def before():
                binding.require(time.monotonic() < deadline, 'epoch metadata 180-second phase deadline')
                _live_checks(BATCH_REPLAY, Path(origin.expected['verifier_root']), deadline,
                             pending_metadata_bytes=32*1024**2)
            origin.phase_check(deadline)
            operation, payload = request['operation'], request['payload']
            binding.require(type(payload) is dict, 'epoch IPC payload object required')
            if operation == 'establish':
                binding.require(epoch is None and set(payload) == {'actual', 'code_pins', 'reviewed_sources'},
                                'epoch establish exactly once per process')
                binding.require(binding.canonical(payload['code_pins']) == binding.canonical(origin.pins),
                                'epoch source pins differ from independently bound import inventory')
                epoch = Epoch.establish(**payload, deadline=deadline, before=before)
                result = dict(status='full-prefix-reconciled', protocol=PROTOCOL)
            else:
                binding.require(epoch is not None, 'epoch process has no full-prefix authority')
                if operation == 'prepare':
                    binding.require(set(payload) == {'targets'}, 'epoch exact prepare payload required')
                    result = epoch.prepare(**payload, deadline=deadline, before=before)
                elif operation == 'cold':
                    binding.require(set(payload) == {'token', 'actual'}, 'epoch exact cold payload required')
                    result = epoch.cold(**payload, deadline=deadline, before=before)
                elif operation == 'pause':
                    binding.require(not payload, 'epoch pause has no authority payload')
                    result = epoch.request_pause()
                elif operation == 'close':
                    binding.require(not payload, 'epoch close has no authority payload')
                    epoch.invalidate()
                    result = dict(status='closed')
                else:
                    raise ValueError('unknown epoch operation')
            origin.phase_check(deadline); before()
            writer.write(encode(dict(protocol=PROTOCOL, instance=instance, sequence=sequence, result=result)))
            writer.flush()
            before()
            if operation == 'close':
                break
    finally:
        if epoch is not None:
            epoch.invalidate()


class Parent:
    """Serial bounded IPC; no continuation after timeout or uncertain delivery."""
    def __init__(self, command, *, cwd, env=None, expected_source_contract=None, stderr_path=None):
        binding.require(bool(command) and Path(command[0]).resolve() == Path(sys.executable).resolve(),
                        'epoch parent requires its independently trusted Python interpreter')
        self._cache = tempfile.TemporaryDirectory(prefix='hiroute-epoch-bytecode-')
        flags = ['-'+'O'*sys.flags.optimize] if sys.flags.optimize else []
        command = [command[0], '-B', *flags, '-X', 'pycache_prefix='+self._cache.name, *command[1:]]
        environment = dict(os.environ if env is None else env, PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1')
        environment.pop('PYTHONHOME', None)
        self.stderr_path = Path(stderr_path) if stderr_path is not None else None
        self._stderr = None
        try:
            if self.stderr_path is not None:
                self._stderr = self.stderr_path.open('xb')
            def child_limits():
                soft, hard = resource.getrlimit(resource.RLIMIT_FSIZE)
                ceiling = min([STDERR_BYTES]+[v for v in (soft, hard) if v != resource.RLIM_INFINITY])
                resource.setrlimit(resource.RLIMIT_FSIZE, (ceiling, ceiling))
            self.process = subprocess.Popen(command, cwd=cwd, env=environment, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=self._stderr or subprocess.PIPE,
                start_new_session=True, preexec_fn=child_limits)
        except BaseException:
            if self._stderr is not None: self._stderr.close()
            self._cache.cleanup(); raise
        self.sequence, self.live = 0, True
        os.set_blocking(self.process.stdin.fileno(), False)
        os.set_blocking(self.process.stdout.fileno(), False)
        try:
            hello = self._read(time.monotonic()+10)
            binding.require(set(hello) in ({'protocol', 'instance', 'as_bytes'},
                                           {'protocol', 'instance', 'as_bytes', 'source_contract_sha'}) and
                            hello['protocol'] == PROTOCOL and hello['as_bytes'] <= AS_BYTES and
                            type(hello['instance']) is str and len(hello['instance']) == 64,
                            'epoch reviewed process handshake required')
            if expected_source_contract is not None:
                binding.require(hello.get('source_contract_sha') == source_digest(expected_source_contract),
                                'epoch worker source contract differs from independently bound parent')
            self.instance = hello['instance']
        except BaseException:
            self.invalidate(); raise

    def diagnostic(self):
        """Bounded durable child status; never include raw stderr in audit JSON."""
        status = self.process.poll()
        result = dict(child_exit_status=status)
        if self.stderr_path is not None and self.stderr_path.exists():
            raw = self.stderr_path.read_bytes()
            binding.require(len(raw) <= STDERR_BYTES, 'epoch child stderr cap changed')
            result.update(stderr_path=str(self.stderr_path), stderr_sha256=hashlib.sha256(raw).hexdigest(),
                          stderr_size_bytes=len(raw))
        return result

    def _transfer(self, fd, count=None, raw=None, deadline=None):
        result = bytearray()
        offset = 0
        while (len(result) < count) if count is not None else (offset < len(raw)):
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise TimeoutError('epoch external hard phase deadline')
            readable, writable, _ = select.select([fd] if count is not None else [],
                                                 [fd] if raw is not None else [], [], remaining)
            if not readable and not writable:
                raise TimeoutError('epoch external hard phase deadline')
            try:
                if count is not None:
                    chunk = os.read(fd, min(65536, count-len(result)))
                    if not chunk:
                        raise EOFError('epoch IPC process exited or pipe closed')
                    result.extend(chunk)
                else:
                    written = os.write(fd, raw[offset:offset+65536])
                    if written <= 0:
                        raise EOFError('epoch IPC write failed')
                    offset += written
            except BlockingIOError:
                continue
        return bytes(result)

    def _read(self, deadline):
        fd = self.process.stdout.fileno()
        count, = struct.unpack('!I', self._transfer(fd, count=4, deadline=deadline))
        binding.require(0 < count <= MAX_FRAME, 'epoch IPC response cap')
        return decode(self._transfer(fd, count=count, deadline=deadline))

    def call(self, operation, payload, *, seconds=180):
        try:
            binding.require(self.live and type(seconds) in (int, float) and
                            not isinstance(seconds, bool) and 0 < seconds <= 180, 'epoch fresh bounded parent phase required')
            deadline = time.monotonic()+seconds
            self.sequence += 1
            message = dict(protocol=PROTOCOL, instance=self.instance, sequence=self.sequence,
                           operation=operation, deadline=float(deadline), payload=payload)
            self._transfer(self.process.stdin.fileno(), raw=encode(message), deadline=deadline)
            reply = self._read(deadline)
            binding.require(type(reply) is dict and set(reply) == {'protocol', 'instance', 'sequence', 'result'} and
                            reply['protocol'] == PROTOCOL and reply['instance'] == self.instance and
                            type(reply['sequence']) is int and reply['sequence'] == self.sequence,
                            'epoch foreign or stale reply')
            binding.require(time.monotonic() < deadline and (operation == 'close' or self.process.poll() is None),
                            'epoch reply arrived after deadline or process death')
            if operation == 'close':
                self.live = False
                self.process.wait(timeout=2)
                for stream in (self.process.stdin, self.process.stdout, self.process.stderr, self._stderr):
                    if stream is not None: stream.close()
                self._cache.cleanup()
            return reply['result']
        except BaseException:
            self.invalidate(); raise

    def invalidate(self):
        self.live = False
        if self.process.poll() is None:
            # This service cannot launch numerical children. Its process group
            # consists solely of metadata authentication, never a live window.
            os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=2)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr, self._stderr):
            if stream is not None: stream.close()
        self._cache.cleanup()


def main():
    raise ValueError('standalone service has no source contract; use pinned metadata-only driver.py')


if __name__ == '__main__':
    main()
