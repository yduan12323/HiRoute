"""Admit pinned failed-window history without granting it runtime authority.

The plan is an independently supplied, canonical document. Every historical
input is consumed at its own hash and size. Failed phase metadata is only linked
evidence: this module never invokes read_phase_result on a historical failure.
"""
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys

from . import plan as binding, suffix_census, suffix_window
from . import window_receipts as receipts

SCHEMA = 'hiroute-suffix-window-recovery-plan-v1'
MODULE = 'experiments.time_cut_v2.recorded_real.suffix_window_recovery'
PLAN_BYTES = 1024**2
MAX_HISTORY = 32
MANDATORY = ('request', 'run_binding', 'selection', 'base_registry', 'source_policy', 'archive')
OPTIONAL = ('summary', 'manifest', 'result', 'decision', 'actual_return', 'recovery_plan', 'cold_replay')
FILES = MANDATORY + OPTIONAL
LIMITS = dict.fromkeys(FILES, receipts.SUMMARY_LIMIT)
LIMITS.update(request=1024**2, source_policy=65536, result=65536, decision=65536,
              actual_return=65536, manifest=1024**2, recovery_plan=PLAN_BYTES,
              base_registry=receipts.REGISTRY_LIMIT, archive=512*1024**2)
_TOKEN = object()


def _pin(value, limit):
    binding.require(type(value) is dict and set(value) == {'path', 'sha256', 'size_bytes'},
                    'exact recovery artifact pin required')
    receipts._sha(value['sha256'])
    binding.require(type(value['path']) is str and Path(value['path']).is_absolute() and
                    os.path.abspath(value['path']) == value['path'] and
                    type(value['size_bytes']) is int and 0 < value['size_bytes'] <= limit,
                    'bounded absolute recovery artifact path and size required')
    return value


def load(path, sha, *, deadline, before=lambda: None):
    check = receipts._guard(deadline, before)
    value = receipts._read(path, sha, PLAN_BYTES, check)
    binding.require(hashlib.sha256(binding.canonical(value)+b'\n').hexdigest() == sha,
                    'recovery plan must use canonical JSON with one final newline')
    binding.require(type(value) is dict and set(value) == {'schema', 'historical_attempt_status',
        'original_selection', 'base_registry', 'predecessors'} and value['schema'] == SCHEMA and
        value['historical_attempt_status'] == 'failed', 'explicit failed recovery plan required')
    _pin(value['original_selection'], receipts.SUMMARY_LIMIT)
    _pin(value['base_registry'], receipts.REGISTRY_LIMIT)
    rows = value['predecessors']
    binding.require(type(rows) is list and 1 <= len(rows) <= MAX_HISTORY, 'bounded ordered recovery ancestry required')
    seen = set()
    for number, row in enumerate(rows):
        binding.require(type(row) is dict and set(row) == {'module', 'source_commit', 'source_sha256',
            'attempt', 'archive_mode', 'source_context', 'artifacts'}, 'recovery predecessor fields changed')
        binding.require(row['module'] == (suffix_window.MODULE if number == 0 else MODULE),
                        'original window followed by recovery ancestors required')
        binding.require(type(row['source_commit']) is str and len(row['source_commit']) == 40 and
            all(c in '0123456789abcdef' for c in row['source_commit']), 'full predecessor source commit required')
        receipts._sha(row['source_sha256'])
        binding.require(type(row['attempt']) is str and Path(row['attempt']).is_absolute() and
            os.path.abspath(row['attempt']) == row['attempt'] and row['attempt'] not in seen,
            'distinct absolute predecessor attempt required')
        seen.add(row['attempt'])
        binding.require(row['archive_mode'] in ('finalized', 'interrupted-prefix'),
                        'explicit finalized or interrupted-prefix archive policy required')
        binding.require(type(row['source_context']) is dict and type(row['artifacts']) is dict and
                        set(row['artifacts']) == set(FILES), 'all artifact absences must be explicit nulls')
        for name, pin in row['artifacts'].items():
            binding.require(pin is not None or name in OPTIONAL, 'mandatory recovery artifact missing: '+name)
            if pin is not None:
                _pin(pin, LIMITS[name])
        binding.require((row['artifacts']['recovery_plan'] is None) == (number == 0) and
                        (row['artifacts']['cold_replay'] is None) == (number == 0),
                        'recovery ancestors must retain their plan and cold receipt')
    binding.require(sum(row['artifacts']['archive']['size_bytes'] for row in rows) <= 512*1024**2,
                    'cumulative recovery history byte cap')
    return value


def command(request):
    """Parse only the new entrypoint; old optional-null hashing stays unchanged."""
    from .suffix_window_recovery import parser, input_context
    argv = request['command']
    binding.require(type(argv) is list and len(argv) > 5 and type(argv[0]) is str and
        Path(argv[0]).is_absolute() and argv[1:5] == ['-B', '-m', MODULE, '--worker'] and
        all(type(v) is str for v in argv), 'reviewed recovery worker command required')
    options = [x for x in argv[5:] if x.startswith('--')]
    binding.require(len(options) == len(set(options)), 'duplicate recovery command option')
    try:
        args = parser().parse_args(argv[4:])
    except SystemExit as error:
        raise ValueError('reviewed recovery command options changed') from error
    binding.require(args.worker and args.cpu is None and args.attempt_dir is None and
        args.deadline == request['deadline_monotonic'] and args.worker_cpus == request['worker_cpus'],
        'recovery worker deadline/CPU binding changed')
    values = input_context(args)
    suffix_census.same(request['context'], dict(plan_sha256=values['replay_plan_sha'],
        source_sha256=values['source_sha'], input_sha256=binding.digest(values),
        profile_name=suffix_window.BATCH_REPLAY.name), 'recovery command input context changed')
    return dict(values, deadline=args.deadline)


def _relative(pin, name):
    return dict(path=name, sha256=pin['sha256'], size_bytes=pin['size_bytes'])


def _origin(origin, request, module):
    binding.require(type(origin) is dict and set(origin) == {'schema', 'checkout_root', 'controller_module',
        'controller_path', 'python_executable', 'executable_realpath', 'cwd'} and
        origin['schema'] == 'hiroute-reviewed-controller-origin-v1' and origin['controller_module'] == module and
        all(type(origin[k]) is str and Path(origin[k]).is_absolute() for k in
            ('checkout_root', 'controller_path', 'python_executable', 'executable_realpath', 'cwd')) and
        origin['controller_path'] == str(Path(origin['checkout_root']) / (module.replace('.', '/')+'.py')) and
        origin['cwd'] == origin['checkout_root'] == str(binding.ROOT.resolve()) and
        request['command'][0] == origin['python_executable'] == sys.executable and
        origin['executable_realpath'] == str(Path(sys.executable).resolve()),
        'historical reviewed controller origin changed')


class AdmittedRecoveryPlan:
    """Detached metadata, never a mathematical or successful-runtime receipt."""
    __slots__ = ('_value', '_selection', '_history', '_dependencies')

    def __init__(self, value, selection, history, dependencies, *, _token=None):
        binding.require(_token is _TOKEN, 'independent failed-plan admission required')
        for name, item in (('_value', value), ('_selection', selection), ('_history', history),
                           ('_dependencies', dependencies)):
            object.__setattr__(self, name, binding.canonical(item))

    def __setattr__(self, *_):
        raise AttributeError('immutable admitted recovery plan')

    def document(self): return json.loads(self._value)
    def selection(self): return json.loads(self._selection)
    def history(self): return json.loads(self._history)
    def dependencies(self): return json.loads(self._dependencies)

    def validate_cold_history(self, cold):
        history = cold['history']
        suffix_census.same([{k: item[k] for k in ('archive', 'source_context')} for item in history],
                          self.history(), 'cold replay admitted history changed')
        for predecessor, actual in zip(self.document()['predecessors'], history):
            finalized = predecessor['archive_mode'] == 'finalized'
            binding.require(actual['gzip_eof'] is finalized and
                (not finalized or actual['trailing_partial_row_bytes'] == 0),
                'cold archive finalization differs from explicit recovery plan')

    def archive_inputs(self, before=lambda: None):
        from .archive_reader import ArchiveReader
        from .window_recovery_core import ArchiveInput
        result = []
        for row in self.document()['predecessors']:
            pin = row['artifacts']['archive']
            result.append(ArchiveInput(ArchiveReader(pin['path'], compressed_sha256=pin['sha256'],
                compressed_bytes=pin['size_bytes'], allow_incomplete=row['archive_mode'] == 'interrupted-prefix',
                before=before), row['source_context']))
        return result


def admit(value, admitted, registry, *, reviewed_sources, deadline, before=lambda: None):
    """Link failures to the independently admitted first outstanding window.

    Metadata booleans never authorize a retained certificate. The separate
    fresh-family recovery session decides that by exact cold verification.
    """
    from validation.capture5.containers import detach_json
    from validation.suffix5.window_plan import next_window
    check = receipts._guard(deadline, before)
    binding.require(type(registry) is receipts.CheckedRegistry, 'independently checked base registry required')
    catalogue, commitment = receipts._population(admitted)
    suffix_census.same(registry.metadata()['population'], commitment, 'recovery base population changed')
    cache = receipts._Dependencies(check)
    def read(pin, *, decode=True):
        return cache.read(pin['path'], pin['sha256'],
            512*1024**2 if not decode else receipts.SUMMARY_LIMIT, size=pin['size_bytes'], decode=decode)
    selection = receipts._selection(admitted, read(value['original_selection']), check)
    suffix_census.same(read(value['base_registry']), registry.metadata(), 'independent recovery base registry changed')
    window = detach_json(next_window(catalogue, registry.completed_block_ids(),
                                    population_plan_sha256=commitment['block_plan_sha256']))
    binding.require(window['launch_required'], 'recovery requires an outstanding original window')
    suffix_census.same(selection, dict(schema='hiroute-suffix-window-selection-v1', population=commitment,
        window_plan=window, blocks=selection['blocks'], selection_uses_outcomes=False,
        numerical_cache_enabled=False, maximum_candidate_passes=window['expected_model_count']*12,
        maximum_logical_stages=window['expected_model_count']*5), 'recovery original selection contract changed')
    suffix_census.same([b['range'] for b in selection['blocks']], window['blocks'],
                      'recovery selection is not the first outstanding window')
    history = []
    for number, row in enumerate(value['predecessors']):
        check()
        pins, attempt = row['artifacts'], Path(row['attempt'])
        original = number == 0
        names = dict(request='request.json', result='result.json', decision='decision.json',
            run_binding='evidence/run-binding.json', selection='evidence/window-selection.json',
            base_registry='evidence/base-registry.json', manifest='evidence/__manifest.json',
            summary='evidence/'+('window-summary.json' if original else 'recovery-summary.json'),
            archive='evidence/'+('model-proofs.jsonl.gz' if original else 'recovery-model-proofs.jsonl.gz'),
            recovery_plan='evidence/recovery-plan.json', cold_replay='evidence/cold-replay.json')
        for name, relative in names.items():
            if pins[name] is not None:
                actual = Path(pins[name]['path'])
                # A kill between fsync/close and atomic publication leaves a
                # finalized gzip here too. Location never decides gzip policy.
                retained_archive = (name == 'archive' and
                    actual.parent == attempt/'evidence/__partial' and len(actual.name) == 9 and
                    all(c in '0123456789' for c in actual.name[:4]) and actual.name[4:] == '.part')
                binding.require(str(actual) == str(attempt/relative) or retained_archive,
                                'foreign historical artifact: '+name)
        documents = {name: read(pin) for name, pin in pins.items() if pin is not None and name != 'archive'}
        read(pins['archive'], decode=False)
        request, run = documents['request'], documents['run_binding']
        values = receipts._command(request, 'suffix_window') if original else command(request)
        binding.require(values['source_commit'] == row['source_commit'] and
            values['source_sha'] == row['source_sha256'] and
            reviewed_sources.get(row['source_commit']) == row['source_sha256'],
            'historical source outside independently reviewed policy')
        suffix_census.same(request['profile'], asdict(suffix_window.BATCH_REPLAY), 'historical resource guard changed')
        binding.require(type(request['entry_monotonic']) is float and type(request['deadline_monotonic']) is float and
            0 < request['deadline_monotonic']-request['entry_monotonic'] <= 900, 'historical wall budget changed')
        receipts._inputs(values, commitment, cache, deadline)
        policy = documents['source_policy']
        binding.require(pins['source_policy']['path'] == values['source_policy'] and
            pins['source_policy']['sha256'] == values['source_policy_sha'] and
            type(policy) is dict and set(policy) == {'schema', 'reviewed_sources'} and
            policy['schema'] == 'hiroute-reviewed-window-sources-v1' and
            policy['reviewed_sources'].get(receipts.SEED_COMMIT) == receipts.SEED_SOURCE and
            policy['reviewed_sources'].get(row['source_commit']) == row['source_sha256'] and
            hashlib.sha256(binding.canonical(policy)+b'\n').hexdigest() == pins['source_policy']['sha256'],
            'historical source-policy binding changed')
        binding.require(all(reviewed_sources.get(commit) == inventory for commit, inventory in
            policy['reviewed_sources'].items()), 'historical policy is outside current reviewed policy')
        suffix_census.same(documents['selection'], selection, 'historical original selection changed')
        suffix_census.same(documents['base_registry'], registry.metadata(), 'historical copied base registry changed')
        binding.require(pins['selection']['sha256'] == value['original_selection']['sha256'] and
            pins['base_registry']['sha256'] == value['base_registry']['sha256'], 'historical original byte pins changed')
        # Independently re-admit the historical command's base, including seed mode.
        from types import SimpleNamespace
        _, historical_base = suffix_window.load_registry(SimpleNamespace(**values), reviewed_sources,
            admitted=admitted, deadline=deadline, before=check)
        suffix_census.same(historical_base.metadata(), registry.metadata(), 'historical registry admission changed')
        prefix = 'hiroute-suffix-window' if original else 'hiroute-suffix-window-recovery'
        binding.require(run['schema'] == prefix+'-binding-v1' and
            run['source_commit'] == row['source_commit'] and run['source_sha256'] == row['source_sha256'],
            'historical run source binding changed')
        suffix_census.same(run['completed_replay'], commitment['completed_replay'], 'historical completed inputs changed')
        suffix_census.same(run['logical_report_sha256'], values['logical_report_sha'], 'historical logical proof changed')
        suffix_census.same(run['selection'], _relative(pins['selection'], 'window-selection.json'), 'historical selection pin changed')
        suffix_census.same(run['base_registry'], _relative(pins['base_registry'], 'base-registry.json'), 'historical base pin changed')
        suffix_census.same(run['window_id'], window['window_id'], 'historical window ID changed')
        suffix_census.same(run['registry_admission'], suffix_window.registry_admission(SimpleNamespace(**values)),
                          'historical registry provenance changed')
        _origin(run['invocation_origin'], request, row['module'])
        resources = run['resource_plan']
        if original:
            expected_resources = suffix_window.resource_plan(values['worker_cpus'], window['expected_model_count'])
        else:
            from .suffix_window_recovery import resource_plan
            cold = documents['cold_replay']
            expected_resources = resource_plan(values['worker_cpus'], window['expected_model_count'], cold['candidate_models'])
            ancestor_plan = documents['recovery_plan']
            suffix_census.same(ancestor_plan, dict(value, predecessors=value['predecessors'][:number]),
                              'historical recovery ancestry changed')
            binding.require(values['recovery_plan_sha'] == pins['recovery_plan']['sha256'] and
                hashlib.sha256(binding.canonical(ancestor_plan)+b'\n').hexdigest() == pins['recovery_plan']['sha256'],
                'historical pinned recovery plan changed')
            suffix_census.same([{k: item[k] for k in ('archive', 'source_context')} for item in cold['history']],
                              history, 'historical cold ancestry changed')
            suffix_census.same(run['recovery_plan'], _relative(pins['recovery_plan'], 'recovery-plan.json'),
                              'historical recovery-plan evidence binding changed')
            suffix_census.same(run['cold_replay'], _relative(pins['cold_replay'], 'cold-replay.json'),
                              'historical cold evidence binding changed')
        suffix_census.same(resources, expected_resources, 'historical candidate resource contract changed')
        context = dict(schema=prefix+'-context-v1', source_sha256=row['source_sha256'],
            source_bundle_sha256=commitment['source_bundle_sha256'], capture_sha256=commitment['completed_replay']['capture_sha256'],
            block_plan_sha256=commitment['block_plan_sha256'], selection_sha256=pins['selection']['sha256'],
            window_id=window['window_id'], original_query_freeze_sha256=commitment['query_freeze_sha256'],
            resource_plan_sha256=binding.digest(resources), base_registry_sha256=pins['base_registry']['sha256'],
            source_policy_sha256=pins['source_policy']['sha256'])
        if not original:
            context.update(recovery_plan_sha256=pins['recovery_plan']['sha256'],
                cold_replay_sha256=pins['cold_replay']['sha256'], history_sha256=binding.digest(cold['history']),
                previous_archive=history[-1]['archive'],
                previous_source_context_sha256=binding.digest(history[-1]['source_context']))
            suffix_census.same(run['source_context'], context, 'historical recovery source binding changed')
        suffix_census.same(row['source_context'], context, 'historical source context changed')
        summary = documents.get('summary')
        if summary is not None:
            binding.require(summary['schema'] == ('hiroute-suffix-window-summary-v1' if original else
                'hiroute-suffix-window-recovery-summary-v1'), 'historical summary schema changed')
            for key, expected in (('source_context', context), ('resource_plan', resources), ('population', commitment),
                ('selection', run['selection']), ('base_registry', run['base_registry']), ('window_id', window['window_id']),
                ('invocation_origin', run['invocation_origin']), ('registry_admission', run['registry_admission']),
                ('proof_archive', _relative(pins['archive'], names['archive'].split('/')[-1]))):
                suffix_census.same(summary[key], expected, 'historical summary linkage changed: '+key)
        manifest = documents.get('manifest')
        if manifest is not None:
            entries = manifest['files']
            binding.require(type(entries) is list and len(entries) <= 64 and
                type(manifest['charged_bytes']) is int and 0 <= manifest['charged_bytes'] <= 512*1024**2,
                'historical manifest bounds changed')
            files = {item['path']: item for item in entries}
            binding.require(len(files) == len(entries), 'duplicate historical manifest entry')
            expected_files = suffix_window.EVIDENCE_FILES if original else {
                'run-binding.json', 'batch-ledger.json', 'family-summary.json', 'block-plan.json',
                'base-registry.json', 'window-selection.json', 'recovery-plan.json', 'cold-replay.json',
                'recovery-model-proofs.jsonl.gz', 'recovery-summary.json'}
            binding.require(set(files) == expected_files, 'foreign historical manifest file coverage')
            for name, relative in names.items():
                if relative.startswith('evidence/') and name != 'manifest' and pins[name] is not None:
                    leaf = relative[len('evidence/'):]
                    suffix_census.same(files.get(leaf), _relative(pins[name], leaf), 'foreign historical manifest linkage: '+name)
            for leaf, item in files.items():
                binding.require(type(item) is dict and set(item) == {'path', 'sha256', 'size_bytes'} and
                    type(item['size_bytes']) is int and 0 < item['size_bytes'] <= 512*1024**2,
                    'historical manifested file bounds changed')
                cache.read(attempt/'evidence'/leaf, item['sha256'], 512*1024**2,
                           size=item['size_bytes'], decode=False)
            block_pin, family_pin = files['block-plan.json'], files['family-summary.json']
            suffix_census.same(cache.read(attempt/'evidence/block-plan.json', block_pin['sha256'],
                receipts.SUMMARY_LIMIT, size=block_pin['size_bytes']), catalogue, 'historical block catalogue changed')
            family = cache.read(attempt/'evidence/family-summary.json', family_pin['sha256'],
                receipts.SUMMARY_LIMIT, size=family_pin['size_bytes'])['checked']
            binding.require(family['bundle_sha256'] == commitment['source_bundle_sha256'] and
                family['case_sha256'] == commitment['case_sha256'], 'historical checked-family binding changed')
        for name in ('result', 'decision', 'actual_return'):
            metadata = documents.get(name)
            if metadata is None:
                continue
            binding.require(type(metadata) is dict, 'historical runtime metadata object required')
            # The launcher publishes a completed decision before its final
            # checks and actual return. An interrupted launcher can leave that
            # flag behind; only the independently retained actual return can
            # disqualify this failed-history input as a successful execution.
            binding.require(name != 'actual_return' or metadata.get('status') != 'completed',
                            'failed history cannot supply an actual successful runtime return')
            for key, expected in (('request_sha256', pins['request']['sha256']),
                                  ('context', request['context']), ('profile', request['profile'])):
                if key in metadata:
                    suffix_census.same(metadata[key], expected, 'historical '+name+' linkage changed: '+key)
            for key, artifact in (('verified_manifest_sha256', 'manifest'), ('manifest_sha256', 'manifest'),
                                  ('result_sha256', 'result'), ('report_sha256', 'result')):
                if metadata.get(key) is not None:
                    binding.require(pins[artifact] is not None and metadata[key] == pins[artifact]['sha256'],
                                    'foreign historical '+name+' artifact linkage')
        history.append(dict(archive={k: pins['archive'][k] for k in ('sha256', 'size_bytes')}, source_context=context))
    check()
    return AdmittedRecoveryPlan(value, selection, history,
        sorted(cache.rows.values(), key=lambda pin: (pin['path'], pin['sha256'])), _token=_TOKEN)
