"""Review-only incremental authentication of actual ordinary window returns.

The trusted parent supplies independently observed caller pins and an exact
reviewed code-file inventory. JSON alone is never execution attestation. This
API launches no controller, LP, recovery series, or collector. A real launcher
and its original-checkout/code attestation require a separate admission review.
"""
from contextlib import contextmanager
from dataclasses import asdict
import os
from pathlib import Path
import secrets
import time
from types import SimpleNamespace

from experiments.time_cut_v2.recorded_real import plan as binding
from experiments.time_cut_v2.recorded_real import window_receipts as receipts
from experiments.time_cut_v2.recorded_real.bootstrap_executor import validate_pinned_policy
from experiments.time_cut_v2.recorded_real.runtime import CAPTURE, read_phase_result
from validation.suffix5.window_plan import next_window
from validation.capture5.containers import detach_json

from .closure import Closure, _path

PROTOCOL = 'hiroute-private-receipt-epoch-v1-review'
KEYS = ('registry', 'registration_return', 'runtime_return')
_FACTORY = object()


def _owned(value):
    return receipts._owned(value)


def _same(actual, expected, why):
    binding.require(binding.canonical(actual) == binding.canonical(expected), why)


def _rows(actual):
    binding.require(type(actual) is dict and set(actual) == set(KEYS), 'epoch actual three caller pins required')
    value = _owned(actual)
    for row in value.values():
        binding.require(type(row) is dict and set(row) == {'path', 'size_bytes', 'sha256'},
                        'epoch exact actual return pin required')
        _path(row['path']); receipts._sha(row['sha256'])
        binding.require(type(row['size_bytes']) is int and 0 <= row['size_bytes'] <= receipts.REGISTRY_LIMIT,
                        'epoch caller return size cap')
    binding.require(len({row['path'] for row in value.values()}) == 3, 'epoch caller pins alias')
    return value


def _read(row, before, limit=receipts.REGISTRY_LIMIT):
    return receipts._read(row['path'], row['sha256'], limit, before, size=row['size_bytes'])


def _load(actual, sources, deadline, before, scope=None):
    registry, returned = actual['registry'], actual['registration_return']
    options = dict(registration_return=Path(returned['path']), registration_return_sha=returned['sha256'],
                   reviewed_sources=sources, deadline=deadline, before=before)
    if scope is None:
        scope = receipts.scope_from_registered_registry(registry['path'], registry['sha256'], **options)
    loaded = receipts.load_scheduling_registry(registry['path'], registry['sha256'], scope, **options)
    _read(registry, before); _read(returned, before, 65536)
    return scope, loaded


def _spec_args(attempt, row, before):
    runtime = _read(row, before, 65536)
    binding.require(runtime.get('status') == 'completed' and runtime.get('descendants_reaped') is True,
                    'epoch actual completed/reaped runtime return required')
    receipt = runtime['acceptance_receipt']
    return SimpleNamespace(window_attempt=Path(attempt), window_return=Path(row['path']),
        window_return_sha=row['sha256'], window_result_sha=receipt['result_sha256'],
        window_decision_sha=receipt['decision_sha256'], window_manifest_sha=runtime['verified_manifest_sha256'])


def _request(entry, before):
    # The enclosing registry pin is externally retained; _admit will bind this
    # request to the actual return and all final supervisor decisions as well.
    request_path = Path(entry['attempt'])/'request.json'
    pins = [row for row in entry['dependencies'] if row['path'] == str(request_path)]
    binding.require(len(pins) == 1, 'epoch independently retained request pin required')
    request = _read(pins[0], before, 1024**2)
    return receipts._command(request, entry['module']), request


def _upstream_closure(entry, values, before):
    """Close the capture phase behind the already authenticated replay command.

    All request bytes must be independently retained dependencies, not a new
    unpinned pathname scan. Unknown command shapes fail closed for review.
    """
    roots, pins = {values['replay_attempt'], values['logical_attempt']}, []
    path = str(Path(values['replay_attempt'])/'request.json')
    request_pins = [pin for pin in entry['dependencies'] if pin['path'] == path]
    binding.require(len(request_pins) == 1, 'epoch full upstream replay request dependency required')
    request = _read(request_pins[0], before, 1024**2)
    argv = request['command']
    binding.require(type(argv) is list and len(argv) > 5 and argv[1:5] ==
        ['-B', '-m', receipts.MODULE_PREFIX+'parallel_replay', '--worker'],
        'epoch only reviewed complete parallel replay upstream supported')
    fields = ('capture_attempt', 'capture_return', 'capture_return_sha')
    supplied = {}
    for field in fields:
        option = '--'+field.replace('_', '-')
        binding.require(argv.count(option) == 1 and argv.index(option)+1 < len(argv),
                        'epoch exact upstream capture path/pin options required')
        supplied[field] = argv[argv.index(option)+1]
    roots.add(_path(supplied['capture_attempt']))
    returned = _path(supplied['capture_return']); receipts._sha(supplied['capture_return_sha'])
    capture_pin = dict(path=returned, size_bytes=os.lstat(returned).st_size,
                       sha256=supplied['capture_return_sha'])
    pins.append(capture_pin)
    historical_path = _path(values['historical_plan'])
    historical_pins = [pin for pin in entry['dependencies'] if pin['path'] == historical_path and
                       pin['sha256'] == values['historical_plan_sha']]
    binding.require(len(historical_pins) == 1, 'epoch independently retained historical plan required')
    historical_pin = historical_pins[0]
    historical = _read(historical_pin, before, 1024**2)
    commit = historical['source_commit']
    binding.require(type(commit) is str and len(commit) == 40 and
                    all(c in '0123456789abcdef' for c in commit), 'epoch historical capture commit required')
    receipts._sha(historical['source_sha256']); receipts._sha(historical['input_sha256'])
    binding.require(type(historical['source_files']) is dict and bool(historical['source_files']) and
                    binding.digest(historical['source_files']) == historical['source_sha256'],
                    'epoch historical capture source inventory changed')
    contract = dict(returned=capture_pin, historical_plan=historical_pin, source_commit=commit,
        context=dict(plan_sha256=historical_pin['sha256'], source_sha256=historical['source_sha256'],
                     input_sha256=historical['input_sha256'], profile_name=CAPTURE.name))
    return roots, pins, [(supplied['capture_attempt'], contract)]


def _authenticate_capture(attempt, contract, deadline, before):
    """Use the producer's historical plan domain, not the window census domain.

    The independently retained historical plan's exact bytes include its commit
    and source inventory. The accepted capture request must bind that same plan.
    Original worker.verify_plan authenticated that commit at capture execution;
    capture returns contain its four-field context, not a separate commit label.
    """
    accepted = read_phase_result(attempt, successful_return=_read(contract['returned'], before, 65536),
        deadline_monotonic=deadline, resource_check=before)
    binding.require(accepted.get('status') == 'completed' and accepted.get('descendants_reaped') is True,
                    'epoch original capture runtime is not cold authenticated')
    _same(accepted['profile'], asdict(CAPTURE), 'epoch original capture profile changed')
    _same(accepted['context'], contract['context'], 'epoch historical capture source/input/plan context changed')
    request_pin = dict(path=str(Path(attempt)/'request.json'), size_bytes=os.lstat(Path(attempt)/'request.json').st_size,
                       sha256=accepted['request_sha256'])
    request = _read(request_pin, before, 1024**2)
    argv = request['command']
    binding.require(type(argv) is list and len(argv) == 12 and
        argv[1:4] == ['-B', '-m', receipts.MODULE_PREFIX+'worker'], 'epoch original capture command changed')
    fields = {}
    for i in range(4, len(argv), 2):
        key = argv[i]
        binding.require(key in ('--phase','--plan','--plan-sha','--deadline') and key not in fields,
                        'epoch original capture command options changed')
        fields[key] = argv[i+1]
    binding.require(fields['--phase'] == 'capture' and
        fields['--plan'] == contract['historical_plan']['path'] and
        fields['--plan-sha'] == contract['historical_plan']['sha256'] and
        float(fields['--deadline']) == request['deadline_monotonic'],
        'epoch capture commit/plan binding differs from authenticated historical plan')
    historical = _read(contract['historical_plan'], before, 1024**2)
    _same(historical['source_commit'], contract['source_commit'], 'epoch historical capture commit changed')
    before()
    return accepted


def closure_inputs(metadata, actual, code_pins, before):
    """Close every whole attempt, plus consumed dependencies and direct anchors.

    Entry.dependencies omits compressed archives and closed control/journal
    namespaces. Explicit entry anchors and complete attempt trees close those
    gaps. Parsed runtime commands supply the two complete upstream trees.
    Snapshot before admission; successful admission must reproduce every entry.
    """
    code_root = Path(receipts.__file__).resolve().parents[3]
    roots = {str(Path(__file__).resolve().parent)}
    roots.update(str(code_root/folder) for folder in ('src','validation','experiments/time_cut_v2/recorded_real')
                 if (code_root/folder).is_dir())
    pins = list(actual.values())+list(code_pins)
    captures = {}
    for entry in metadata['entries']:
        before()
        binding.require(entry['module'] in ('block_resume', 'suffix_window'),
                        'epoch excludes recovery receipt contracts')
        roots.add(entry['attempt'])
        pins.extend(entry['dependencies'])
        pins.extend(entry[key] for key in ('catalogue', 'summary', 'proof', 'selection'))
        values, _ = _request(entry, before)
        upstream_roots, upstream_pins, capture_phases = _upstream_closure(entry, values, before)
        roots.update(upstream_roots); pins.extend(upstream_pins)
        for attempt, contract in capture_phases:
            binding.require(attempt not in captures or captures[attempt] == contract,
                            'epoch conflicting capture caller pins')
            captures[attempt] = contract
        if entry['module'] == 'block_resume':
            for key in ('old_archive', 'old_summary', 'old_selection'):
                historic = Path(values[key])
                binding.require(historic.parent.name == 'evidence', 'epoch retained seed closure contract unsupported')
                roots.add(str(historic.parent.parent))
        # Mandatory independent caller pointer; its size comes from the safe
        # snapshot and its SHA is authenticated by the enclosing exact entry.
        path = entry['successful_return']
        pins.append(dict(path=path, size_bytes=os.lstat(path).st_size,
                         sha256=entry['successful_return_sha256']))
    return roots, pins, captures


class Epoch:
    """One private memory authority; no serializer or disk-resume constructor."""
    __slots__ = ('_scope', '_registry', '_actual', '_closure', '_sources', '_frozen',
                 '_code_pins', '_nonce', '_generation', '_pending', '_pause', '_live')

    def __init__(self, *, _token=None):
        binding.require(_token is _FACTORY, 'epoch requires a new full reconciliation')
        self._live = False

    def invalidate(self):
        self._live = False
        self._scope = self._registry = self._closure = self._pending = None

    @contextmanager
    def _phase(self, deadline, before):
        try:
            binding.require(self._live, 'epoch is invalid; disk reports cannot restore it')
            binding.require(type(deadline) is float and deadline <= time.monotonic()+180,
                            'epoch fresh at-most-180-second phase deadline required')
            check = receipts._guard(deadline, before)
            yield check
            check()
        except BaseException:
            self.invalidate()
            raise

    @classmethod
    def establish(cls, actual, *, code_pins, reviewed_sources, deadline, before=lambda: None):
        epoch = cls(_token=_FACTORY)
        epoch._live = True
        with epoch._phase(deadline, before) as check:
            actual = _rows(actual)
            sources = _owned(reviewed_sources)
            code_pins = _owned(code_pins)
            # The trusted parent must supply an independent complete source
            # inventory. Require the actual epoch package files in that pinset.
            required = {str(Path(__file__).resolve()), str(Path(__file__).with_name('closure.py').resolve()),
                        str(Path(__file__).with_name('sidecar.py').resolve()),
                        str(Path(__file__).with_name('__init__.py').resolve()),
                        str(Path(receipts.__file__).resolve()), str(Path(binding.__file__).resolve())}
            root = Path(receipts.__file__).resolve().parents[3]
            required.update(str(root/name) for name in receipts.suffix_census.source_inventory(root))
            binding.require(required <= {row['path'] for row in code_pins}, 'epoch reviewed logic pinset incomplete')
            scope, scheduling = _load(actual, sources, deadline, check)
            metadata = scheduling.metadata()
            binding.require(bool(metadata['entries']), 'epoch needs an existing completed prefix')
            roots, pins, captures = closure_inputs(metadata, actual, code_pins, check)
            initial = Closure.capture(roots, pins, check)
            checked = receipts.reconcile_registry(scheduling, scope, reviewed_sources=sources,
                                                 deadline=deadline, before=check)
            for attempt, contract in captures.items():
                _authenticate_capture(attempt, contract, deadline, check)
            newest = checked.metadata()['entries'][-1]
            _same(actual['runtime_return']['path'], newest['successful_return'], 'epoch newest actual runtime path changed')
            _same(actual['runtime_return']['sha256'], newest['successful_return_sha256'],
                  'epoch newest actual runtime pin changed')
            runtime = _read(actual['runtime_return'], check, 65536)
            accepted = read_phase_result(newest['attempt'], successful_return=runtime,
                                         deadline_monotonic=deadline, resource_check=check)
            binding.require(accepted['status'] == 'completed', 'epoch initial actual runtime failed')
            values, request = _request(newest, check)
            frozen = {key: values[key] for key in receipts.COMMON_PATHS+receipts.COMMON_PINS+
                      ('source_policy', 'source_policy_sha', 'worker_cpus')}
            frozen['cpu'] = request['cpu']
            policy = receipts._read(frozen['source_policy'], frozen['source_policy_sha'], 65536, check)
            _same(validate_pinned_policy(policy, frozen['source_policy_sha']), sources,
                  'epoch independently reviewed policy allowlist changed')
            initial.continuity(check)
            epoch._scope, epoch._registry, epoch._closure = scope, checked, initial
            epoch._actual, epoch._sources, epoch._frozen = actual, sources, frozen
            epoch._code_pins, epoch._nonce, epoch._generation = code_pins, secrets.token_hex(32), 0
            epoch._pending, epoch._pause = None, False
        return epoch

    def request_pause(self):
        binding.require(self._live, 'invalid epoch cannot pause')
        self._pause = True
        return dict(pause_requested=True, at_safe_boundary=self._pending is None)

    def prepare(self, targets, *, deadline, before=lambda: None):
        with self._phase(deadline, before) as check:
            binding.require(not self._pause and self._pending is None, 'epoch paused or window already in flight')
            self._closure.rehash(check)
            targets = _owned(targets)
            binding.require(set(targets) == {'attempt', *KEYS}, 'epoch exact planned output paths required')
            paths = [_path(value) for value in targets.values()]
            binding.require(len(set(paths)) == 4 and all(path not in self._closure.files for path in paths),
                            'epoch output aliases historical file')
            for path in paths:
                binding.require(not any(Path(path).is_relative_to(Path(root)) for root in self._closure.roots),
                                'epoch output enters a closed historical attempt')
            plan = next_window(self._scope.plan(), self._registry.completed_block_ids(),
                               population_plan_sha256=binding.digest(self._scope.plan()))
            plan = detach_json(plan)
            binding.require(plan['launch_required'], 'epoch prefix has no outstanding window')
            token = dict(epoch=self._nonce, generation=self._generation, challenge=secrets.token_hex(32))
            pending = dict(token=token, targets=targets, plan=plan)
            self._closure.continuity(check)
            check()
            self._pending = pending
            return _owned(dict(protocol=PROTOCOL, token=token, window_plan=plan, previous_actual=self._actual))

    def cold(self, token, actual, *, deadline, before=lambda: None):
        with self._phase(deadline, before) as check:
            binding.require(self._pending is not None, 'epoch cold requires one pending window')
            _same(token, self._pending['token'], 'epoch stale or foreign prepare token')
            self._closure.rehash(check)
            actual = _rows(actual)
            for key in KEYS:
                _same(actual[key]['path'], self._pending['targets'][key], 'epoch actual return outside planned output')
            scope, scheduling = _load(actual, self._sources, deadline, check, self._scope)
            proposed = scheduling.metadata()
            previous_entries = self._registry.metadata()['entries']
            binding.require(len(proposed['entries']) == len(previous_entries)+1 and
                            proposed['entries'][:-1] == previous_entries,
                            'epoch registry must append exactly one entry without deletion or reordering')
            newest = proposed['entries'][-1]
            _same(newest['attempt'], self._pending['targets']['attempt'], 'epoch new attempt differs from plan')
            _same(newest['successful_return'], actual['runtime_return']['path'], 'epoch actual runtime path differs')
            _same(newest['successful_return_sha256'], actual['runtime_return']['sha256'], 'epoch actual runtime pin differs')
            values, request = _request(newest, check)
            expected_values = {key: values[key] for key in self._frozen if key != 'cpu'}
            expected_values['cpu'] = request['cpu']
            _same(expected_values, self._frozen, 'epoch source/policy/population inputs or resources changed')
            binding.require(values.get('maximum_blocks') is None and values.get('bootstrap') is None and
                            values['registry_output'] == self._pending['targets']['registry'] and
                            values['registration_return_output'] == self._pending['targets']['registration_return'] and
                            values['registry'] == self._actual['registry']['path'] and
                            values['registry_sha'] == self._actual['registry']['sha256'] and
                            values['registry_return'] == self._actual['registration_return']['path'] and
                            values['registry_return_sha'] == self._actual['registration_return']['sha256'],
                            'epoch requires ordinary default continuation from actual previous returns')
            roots, pins, captures = closure_inputs(proposed, actual, self._code_pins, check)
            binding.require(all(attempt in self._closure.roots and
                                contract['returned']['path'] in self._closure.files for attempt, contract in captures.items()),
                            'epoch new entry introduces a foreign original capture phase')
            candidate = Closure.capture(roots, pins, check)
            self._closure.require_extension(candidate)
            args = _spec_args(newest['attempt'], actual['runtime_return'], check)
            receipt = receipts.admit_new_completed_window(args, scope, reviewed_sources=self._sources,
                                                          deadline=deadline, before=check)
            updated = receipts.extend_registry(self._registry, scope, receipt)
            _same(updated.metadata(), proposed, 'epoch new registry differs from old plus fully admitted entry')
            exact = binding.canonical(updated.metadata())+b'\n'
            import hashlib
            binding.require(len(exact) == actual['registry']['size_bytes'] and
                            hashlib.sha256(exact).hexdigest() == actual['registry']['sha256'],
                            'epoch registry is not the exact canonical standard registration')
            _same([row['range']['block_id'] for row in receipt.metadata()['blocks']],
                  self._pending['plan']['block_ids'], 'epoch new blocks differ from default selector')
            candidate.continuity(check)
            self._closure.continuity(check)
            check()
            # No fallible publication before this single private state swap.
            self._scope, self._registry, self._closure, self._actual = scope, updated, candidate, actual
            self._generation += 1
            self._pending = None
            return _owned(dict(protocol=PROTOCOL, status='incrementally-authenticated', generation=self._generation,
                completed_models=proposed['completed_models'], completed_blocks=len(proposed['blocks']),
                actual=actual, paused=self._pause, query_optimum_certified=False, literal_G8_closed=False,
                final_independent_reconcile_required=True))
