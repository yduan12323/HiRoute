"""Run one frozen, original-model suffix window through the existing guard.

No work is performed on import. The controller uses authenticated receipt
scope, never a fabricated checked family. Only a fresh worker admission may
enumerate descriptors and construct matrices. A successful raw run remains
available if subsequent receipt registration fails.
"""
import time
ENTRY = time.monotonic()

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import resource
import sys
from types import SimpleNamespace

from . import block_pilot, domain, plan as binding, suffix_census
from .block_archive import ArchiveEncoding, QuotaWriter, checked_records
from .hot_jobs import read_pinned
from .runtime import (BATCH_REPLAY, BoundedEvidenceWriter, PlanContext,
                      _exclusive_json, _live_checks, run_phase, worker_failure)
from .worker import verify_loaded

SECONDS = 900
MAX_MODELS = 8192
MAX_BLOCKS = 32
MAX_INPUT_BYTES = 128 * 1024**2
MODULE = 'experiments.time_cut_v2.recorded_real.suffix_window'
FALSE_AUTHORITY = dict(query_optimum_certified=False, full_population_complete=False,
                       literal_G8_closed=False)
EVIDENCE_FILES = frozenset(('run-binding.json', 'batch-ledger.json', 'family-summary.json',
    'block-plan.json', 'base-registry.json', 'window-selection.json',
    'model-proofs.jsonl.gz', 'window-summary.json'))
INPUT_EXCLUSIONS = frozenset(('worker', 'deadline', 'cpu', 'attempt_dir'))
SEED_FIELDS = ('seed_attempt', 'seed_return', 'old_archive', 'old_summary', 'old_selection',
               'seed_result_sha', 'seed_decision_sha')
REGISTRY_FIELDS = ('registry', 'registry_sha', 'registry_return', 'registry_return_sha')


def check_invocation_origin(source_files=None):
    """Observe this trusted invocation, without claiming remote attestation.

    This deliberately requires the reviewed checkout as cwd and the current
    interpreter. A successful arbitrary run_phase command is not equivalent
    to an independently observed invocation of this controller.
    """
    root = binding.ROOT.resolve()
    expected = root/'experiments/time_cut_v2/recorded_real/suffix_window.py'
    binding.require(Path.cwd().resolve() == root, 'reviewed controller checkout cwd required')
    binding.require(Path(__file__).resolve() == expected, 'reviewed controller module origin changed')
    specification = importlib.util.find_spec(MODULE)
    binding.require(specification is not None and specification.origin is not None and
                    Path(specification.origin).resolve() == expected,
                    'reviewed child module resolution changed')
    executable = Path(sys.executable)
    binding.require(executable.is_absolute() and executable.is_file() and
                    os.access(executable, os.X_OK) and os.path.samefile(executable, '/proc/self/exe'),
                    'current trusted interpreter executable required')
    for name, module in tuple(sys.modules.items()):
        package = 'experiments.time_cut_v2.recorded_real'
        if name != package and not name.startswith(package+'.'):
            continue
        path = Path(module.__file__).resolve()
        relative = (Path(*name.split('.'))/'__init__.py' if name == package else
                    Path(*name.split('.')).with_suffix('.py'))
        binding.require(path == root/relative, 'foreign loaded controller module: '+name)
        if source_files is not None:
            binding.require(relative.as_posix() in source_files and
                binding.pin(path) == source_files[relative.as_posix()], 'loaded controller source bytes changed: '+name)
    if source_files is not None:
        # The -m entry is named __main__, so include it independently of the
        # ordinary module-name scan above.
        relative = expected.relative_to(root).as_posix()
        binding.require(relative in source_files and binding.pin(expected) == source_files[relative],
                        'controller entry source bytes changed')
        verify_loaded({'source_files': source_files})
    return dict(schema='hiroute-reviewed-controller-origin-v1', checkout_root=str(root),
        controller_module=MODULE, controller_path=str(expected), python_executable=sys.executable,
        executable_realpath=str(executable.resolve()), cwd=str(Path.cwd().resolve()))


def input_context(args):
    """Bind parser values without collapsing null, strings or CPU lists."""
    return {key: str(value) if isinstance(value, Path) else value
            for key, value in vars(args).items() if key not in INPUT_EXCLUSIONS}


def worker_command(args, deadline):
    command = [sys.executable, '-B', '-m', MODULE, '--worker', '--deadline', repr(deadline)]
    for key, value in input_context(args).items():
        if value is None:
            continue
        command.append('--' + key.replace('_', '-'))
        command.extend(map(str, value)) if key == 'worker_cpus' else command.append(str(value))
    return command


def resource_plan(cpus, models):
    binding.require(type(cpus) is list and len(cpus) == 5 and
        all(type(cpu) is int and cpu >= 0 for cpu in cpus) and len(set(cpus)) == 5,
        'five distinct resource-plan CPUs required')
    binding.require(type(models) is int and 0 <= models <= MAX_MODELS, 'window model cap')
    binding.require(BATCH_REPLAY.group_rss_bytes == 20*1024**3 and
        BATCH_REPLAY.host_reserve_bytes == 16*1024**3, 'fixed group and host resource policy changed')
    return dict(name='C01-suffix-window-v1', absolute_seconds=SECONDS,
        evidence_charge_bytes=512*1024**2, uncompressed_archive_bytes=512*1024**2,
        maximum_input_bytes=MAX_INPUT_BYTES, maximum_blocks=MAX_BLOCKS, maximum_models=MAX_MODELS,
        models=models, block_size=256, persistent_workers=4, candidate_as_bytes=1024**3,
        candidate_peak_rss_bytes=768*1024**2, seconds_per_model=30, maximum_passes_per_model=12,
        maximum_candidate_passes=models*12, maximum_logical_stages=models*5,
        numerical_cache_enabled=False, worker_cpus=list(cpus))


def source_policy(args, before=lambda: None):
    from .window_receipts import SEED_COMMIT, SEED_SOURCE
    before()
    policy = read_pinned(args.source_policy, args.source_policy_sha, 65536)
    binding.require(type(policy) is dict and set(policy) == {'schema', 'reviewed_sources'} and
        policy['schema'] == 'hiroute-reviewed-window-sources-v1' and
        type(policy['reviewed_sources']) is dict, 'reviewed source-policy schema required')
    binding.require(hashlib.sha256(binding.canonical(policy)+b'\n').hexdigest() == args.source_policy_sha,
        'source policy must use canonical JSON with one final newline')
    sources = policy['reviewed_sources']
    for commit, inventory in sources.items():
        binding.require(type(commit) is str and len(commit) == 40 and
            all(char in '0123456789abcdef' for char in commit) and
            type(inventory) is str and len(inventory) == 64 and
            all(char in '0123456789abcdef' for char in inventory), 'invalid reviewed source identity')
    binding.require(sources.get(args.source_commit) == args.source_sha,
                    'current source is outside reviewed source policy')
    binding.require(sources.get(SEED_COMMIT) == SEED_SOURCE,
                    'reviewed source policy must explicitly retain the accepted seed source')
    before()
    return sources


def admission_mode(args):
    if args.registry is None:
        binding.require(all(getattr(args, key) is None for key in REGISTRY_FIELDS),
                        'initial window cannot use partial registry inputs')
        binding.require(all(getattr(args, key) is not None for key in SEED_FIELDS[:5]),
                        'initial window requires the fixed seed inputs')
        return 'seed'
    binding.require(all(getattr(args, key) is not None for key in REGISTRY_FIELDS) and
        all(getattr(args, key) is None for key in SEED_FIELDS),
        'later window requires only complete registered-ledger inputs')
    return 'registry'


def load_registry(args, reviewed_sources, *, admitted=None, deadline, before):
    """Use metadata-only controller scope or compare against fresh worker input."""
    from . import window_receipts as receipts
    if admission_mode(args) == 'seed':
        scope = admitted if admitted is not None else receipts.scope_from_seed(
            args, deadline=deadline, before=before)
        registry = receipts.admit_seed_resume(args, scope, deadline=deadline, before=before)
    else:
        options = dict(registration_return=args.registry_return,
            registration_return_sha=args.registry_return_sha, reviewed_sources=reviewed_sources,
            deadline=deadline, before=before)
        scope = admitted if admitted is not None else receipts.scope_from_registered_registry(
            args.registry, args.registry_sha, **options)
        registry = receipts.load_scheduling_registry(args.registry, args.registry_sha, scope, **options)
    binding.require(type(registry) is receipts.CheckedRegistry, 'typed checked registry required')
    for entry in registry.metadata()['entries']:
        binding.require(reviewed_sources.get(entry['source_commit']) == entry['source_sha256'],
                        'registry history is outside reviewed source policy')
    before()
    return scope, registry


def registry_admission(args):
    from .window_receipts import SEED_RETURN, SEED_MANIFEST
    if admission_mode(args) == 'seed':
        return dict(kind='seed-resume-v1', successful_return_sha256=SEED_RETURN,
                    manifest_sha256=SEED_MANIFEST, source_policy_sha256=args.source_policy_sha)
    return dict(kind='registered-window-ledger-v1', registry_sha256=args.registry_sha,
                registration_return_sha256=args.registry_return_sha,
                source_policy_sha256=args.source_policy_sha)


def plan_window(scope, registry):
    from .window_receipts import CheckedRegistry, ReceiptScope
    from .indexed_population import AdmittedSuffixPopulation
    from validation.capture5.containers import detach_json
    from validation.suffix5.window_plan import next_window
    binding.require(type(registry) is CheckedRegistry, 'typed checked registry required')
    binding.require(type(scope) in (ReceiptScope, AdmittedSuffixPopulation),
                    'authenticated original population scope required')
    plan = scope.plan() if type(scope) is ReceiptScope else scope.population.plan()
    commitment = scope.commitment()
    binding.require(plan['block_size'] == 256 and plan['total_models'] == 695712 and
        len(plan['blocks']) == 2718 and commitment['original_model_occurrences'] == 7652832,
        'fixed full C01 numerical population changed')
    suffix_census.same(registry.metadata()['population'], commitment, 'registry population changed')
    return detach_json(next_window(plan, registry.completed_block_ids(),
                                   population_plan_sha256=commitment['block_plan_sha256']))


def freeze_selection(admitted, registry, before=lambda: None):
    from .indexed_population import AdmittedSuffixPopulation
    binding.require(type(admitted) is AdmittedSuffixPopulation,
                    'fresh genuine admitted suffix population required for descriptors')
    window = plan_window(admitted, registry)
    plan = admitted.population.plan()
    blocks = []
    for number in window['block_ids']:
        before()
        rows = list(admitted.population.block(number))
        admitted.population.check_block_descriptors(number, rows)
        blocks.append(dict(range=plan['blocks'][number], descriptors=rows))
    before()
    return dict(schema='hiroute-suffix-window-selection-v1', population=admitted.commitment(),
        window_plan=window, blocks=blocks, selection_uses_outcomes=False, numerical_cache_enabled=False,
        maximum_candidate_passes=window['expected_model_count']*12,
        maximum_logical_stages=window['expected_model_count']*5)


def publish_proofs(ctx, selection, source_context, writer, outcomes, *, deadline, before):
    encoding, footer = ArchiveEncoding(), {}
    def rows():
        for row in checked_records(ctx, selection['blocks'], source_context, outcomes,
                                   deadline=deadline, before=before):
            before()
            if row['kind'] == 'footer':
                footer.update(row)
            if row['kind'] == 'block_certificate_checkpoint':
                print(json.dumps(dict(kind='provisional-block-progress',
                    block_id=row['report']['range']['block_id'], acceptance=False,
                    cold_certificate_replay_required=True), sort_keys=True), flush=True)
            yield row
    pin = writer.write('model-proofs.jsonl.gz', encoding.chunks(rows()))
    before()
    binding.require(encoding.complete and footer.get('kind') == 'footer', 'incomplete window proof archive')
    return dict(archive=pin, encoding=encoding.summary(), footer=footer)


def worker(args):
    raw_writer = writer = pool = None
    stage = 'binding'
    def before():
        binding.require(type(args.deadline) is float and math.isfinite(args.deadline) and
                        time.monotonic() < args.deadline, 'suffix window absolute deadline')
    try:
        before()
        origin = check_invocation_origin()
        binding.require(os.environ.get('HIROUTE_PROFILE') == BATCH_REPLAY.name and
            os.environ.get('HIROUTE_EVIDENCE_CAP_BYTES') == str(BATCH_REPLAY.worker_evidence_bytes),
            'wrong suffix window group guard')
        resource_plan(args.worker_cpus, 0)
        binding.require(os.sched_getaffinity(0) == set(args.worker_cpus), 'five inherited CPUs required')
        binding.require(not any(name == 'validation' or name.startswith(('validation.', 'timecut5')) or
            name.split('.')[0] in ('numpy', 'scipy', 'sympy') for name in sys.modules),
            'mathematics imported before window fence')
        sys.meta_path.insert(0, suffix_census.NoOptimization())
        sources = suffix_census.check_sources(binding.ROOT, args.source_commit, args.source_sha)
        suffix_census.same(check_invocation_origin(sources), origin, 'worker invocation origin changed')
        policy = source_policy(args, before)
        index, trusted, _, anchors = suffix_census.completed_inputs(binding.ROOT, args, args.deadline, before)
        original = read_pinned(args.historical_plan, args.historical_plan_sha, 4*1024**2)
        binding.require(original['state_id'] == 'C01' and original['H_ref'] == 4 and original['sites'] == 8 and
            original['regions'] == 2047 and original['dominance'] is True and original['external_incumbent'] is None,
            'fixed C01 physical population required')
        raw_writer = BoundedEvidenceWriter(os.environ['HIROUTE_EVIDENCE_ROOT'],
            BATCH_REPLAY.worker_evidence_bytes, profile_name=BATCH_REPLAY.name)
        writer = QuotaWriter(raw_writer, before)
        stage = 'fresh-family'
        payload = read_pinned(args.capture, index['capture_sha256'], 1024**3)
        binding.require(payload['schema'] == 'hiroute-recorded-real-capture-v1' and
            payload['source_plan_sha256'] == args.historical_plan_sha, 'capture identity changed')
        for key in ('source_sha256', 'input_sha256', 'query_sha256', 'query'):
            suffix_census.same(payload[key], original[key], 'capture ' + key + ' changed')
        suffix_census.same(payload['variant'], domain.variant(original), 'capture variant changed')
        bundle = payload['bundle']; del payload
        from validation.real5_v2.batch_jobs import BatchExecutor, WORKER_AS
        from validation.family5.checker import _plain
        from .family_gate import verify_families
        binding.require(WORKER_AS == 1024**3, 'scalar child cap changed')
        started = time.monotonic()
        with BatchExecutor(tuple(args.worker_cpus[1:]), float(args.deadline-10), index['capture_sha256'],
                           kernel='interval-join-v1') as pool:
            binding.require(len(pool.slots) == 4 and all(slot.process.poll() is None for slot in pool.slots),
                            'four family workers required')
            os.sched_setaffinity(0, {args.worker_cpus[0]})
            ctx, ledger = verify_families(bundle, trusted, pool)
        del bundle
        binding.require(all(slot.process.poll() is not None for slot in pool.slots), 'family workers not reaped')
        writer.write('batch-ledger.json', domain.chunks(ledger))
        writer.write('family-summary.json', domain.chunks(dict(checked=_plain(ctx.summary),
                                                              wall_seconds=time.monotonic()-started)))
        stage = 'cold-population-and-selection'
        from .indexed_population import admit_population
        admitted = admit_population(binding.ROOT, args, ctx, args.deadline, before)
        _, registry = load_registry(args, policy, admitted=admitted, deadline=args.deadline, before=before)
        selection = freeze_selection(admitted, registry, before)
        window = selection['window_plan']
        binding.require(window['launch_required'], 'terminal empty window must not launch a worker')
        resources = resource_plan(args.worker_cpus, window['expected_model_count'])
        admission = registry_admission(args)
        writer.write('block-plan.json', domain.chunks(admitted.population.plan()))
        base_pin = writer.write('base-registry.json', domain.chunks(registry.metadata()))
        if args.registry is not None:
            binding.require(base_pin['sha256'] == args.registry_sha, 'base registry exact bytes changed')
        selection_pin = writer.write('window-selection.json', domain.chunks(selection))
        writer.write('run-binding.json', domain.chunks(dict(schema='hiroute-suffix-window-binding-v1',
            source_commit=args.source_commit, source_sha256=args.source_sha, completed_replay=anchors,
            logical_report_sha256=args.logical_report_sha, resource_plan=resources, base_registry=base_pin,
            selection=selection_pin, window_id=window['window_id'], registry_admission=admission,
            invocation_origin=origin)))
        # Every original descriptor and band is frozen before any matrix or LP.
        context = dict(schema='hiroute-suffix-window-context-v1', source_sha256=args.source_sha,
            source_bundle_sha256=ctx.summary['bundle_sha256'], capture_sha256=index['capture_sha256'],
            block_plan_sha256=admitted.population.plan_sha256, selection_sha256=selection_pin['sha256'],
            window_id=window['window_id'], original_query_freeze_sha256=index['query_freeze_sha256'],
            resource_plan_sha256=binding.digest(resources), base_registry_sha256=base_pin['sha256'],
            source_policy_sha256=args.source_policy_sha)
        from .lp_stream_jobs import stream_results
        os.sched_setaffinity(0, set(args.worker_cpus))
        stage = 'persistent-candidates-and-exact-checks'; before(); started = time.monotonic()
        with stream_results(block_pilot.model_jobs(ctx, selection, context, before),
            cpus=tuple(args.worker_cpus[1:]), coordinator_cpu=args.worker_cpus[0],
            deadline_monotonic=float(args.deadline-10), max_jobs=window['expected_model_count'],
            max_input_bytes=MAX_INPUT_BYTES) as outcomes:
            proof = publish_proofs(ctx, selection, context, writer, outcomes, deadline=args.deadline, before=before)
        numerical_wall = time.monotonic()-started
        stage = 'final-binding'
        verify_loaded({'source_files': sources})
        suffix_census.same(check_invocation_origin(sources), origin, 'worker invocation origin changed')
        suffix_census.check_sources(binding.ROOT, args.source_commit, args.source_sha)
        suffix_census.same(source_policy(args, before), policy, 'reviewed source policy changed')
        final_admitted = admit_population(binding.ROOT, args, ctx, args.deadline, before)
        suffix_census.same(final_admitted.commitment(), admitted.commitment(), 'original query population changed')
        binding.require(binding.pin(args.capture)['sha256'] == index['capture_sha256'], 'capture changed during window')
        summary = dict(schema='hiroute-suffix-window-summary-v1', source_context=context,
            resource_plan=resources, population=admitted.commitment(), selection=selection_pin,
            base_registry=base_pin, window_id=window['window_id'], registry_admission=admission,
            proof_archive=proof['archive'], encoding=proof['encoding'], complete=proof['footer']['complete'],
            verified_models=proof['footer']['verified_models'], blocks=proof['footer']['blocks'],
            transport=proof['footer']['transport'], numerical_wall_seconds=numerical_wall, **FALSE_AUTHORITY)
        summary['invocation_origin'] = origin
        writer.write('window-summary.json', domain.chunks(summary))
        binding.require({row['path'] for row in writer.files} == EVIDENCE_FILES,
                        'window evidence coverage changed')
        before(); raw_writer.finalize(); before()
        return 0 if summary['complete'] else 1
    except BaseException as error:
        if writer is not None and pool is not None and not any(
                row['path'] == 'batch-ledger.json' for row in writer.files):
            try:
                writer.write('partial-batch-ledger.json', domain.chunks(pool.snapshot()))
            except BaseException:
                pass
        worker_failure(type(error).__name__, str(error)[:4096], stage)
        return 1
    finally:
        if raw_writer is not None:
            raw_writer.close()


def runtime_return_path(args):
    return args.registry_output.with_name(args.registry_output.name + '.run-return.json')


def retain_return(value, path, before, *, revoke_on_failure=False):
    """Persist the actual returned value exclusively, never reconstruct it."""
    before()
    published_inode = None
    def publish():
        nonlocal published_inode
        stat = path.with_name(path.name+'.partial').stat(follow_symlinks=False)
        published_inode = (stat.st_dev, stat.st_ino)
        before()
    try:
        _exclusive_json(path, value, 65536, before_publish=publish)
        pin = binding.pin(path)
        before()
        return pin
    except BaseException:
        if published_inode is not None and revoke_on_failure:
            try:
                stat = path.stat(follow_symlinks=False)
                if (stat.st_dev, stat.st_ino) == published_inode:
                    path.unlink()
            except FileNotFoundError:
                pass
        raise


def register_completed(args, scope, registry, result, reviewed_sources, *, deadline, before,
                       retained_return=None, final_check=lambda: None):
    from . import window_receipts as receipts
    binding.require(result.get('status') == 'completed', 'only a completed runtime return can register')
    pin = retained_return or retain_return(result, runtime_return_path(args), before)
    receipt_args = SimpleNamespace(window_attempt=args.attempt_dir, window_return=runtime_return_path(args),
        window_return_sha=pin['sha256'], window_result_sha=result['acceptance_receipt']['result_sha256'],
        window_decision_sha=result['acceptance_receipt']['decision_sha256'],
        window_manifest_sha=result['verified_manifest_sha256'])
    receipt = receipts.admit_new_completed_window(receipt_args, scope, reviewed_sources=reviewed_sources,
                                                 deadline=deadline, before=before)
    updated = receipts.extend_registry(registry, scope, receipt)
    before(); final_check(); before()
    actual_registration = receipts.write_registry(updated, args.registry_output, deadline=deadline, before=before)
    # Without this separately retained actual return the fresh registry is not
    # scheduling authority, including interruption after its file was written.
    def publication_check():
        before(); final_check(); before()
    registration_pin = retain_return(actual_registration, args.registration_return_output, publication_check,
                                     revoke_on_failure=True)
    return dict(status='registered', runtime_return=dict(path=str(runtime_return_path(args)), **pin),
        registry=dict(path=str(args.registry_output), sha256=actual_registration['registry_sha256'],
                      size_bytes=actual_registration['registry_size_bytes']),
        registration_return=dict(path=str(args.registration_return_output), **registration_pin),
        completed_block_ids=list(updated.completed_block_ids()), **FALSE_AUTHORITY)


def controller(args):
    binding.require(args.cpu is not None and args.attempt_dir is not None,
                    'supervisor CPU and fresh suffix window attempt required')
    deadline = float(ENTRY + SECONDS)
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    binding.require(hard == resource.RLIM_INFINITY or hard >= BATCH_REPLAY.child_as_bytes,
                    'inherited AS ceiling too small')
    resource.setrlimit(resource.RLIMIT_AS,
        (min(512*1024**2, soft) if soft != resource.RLIM_INFINITY else 512*1024**2, hard))
    outputs = (args.registry_output, args.registration_return_output, runtime_return_path(args))
    resolved = [path.resolve() for path in outputs]
    binding.require(len(set(resolved)) == len(resolved) and all(
        path != args.attempt_dir.resolve() and args.attempt_dir.resolve() not in path.parents for path in resolved),
        'registration outputs must be distinct and outside the raw attempt')
    binding.require(not args.attempt_dir.exists() and all(
        path.parent.is_dir() and not path.exists() and not path.is_symlink() and
        not path.with_name(path.name+'.partial').exists() for path in outputs),
        'fresh attempt and external return/registry paths required; previous evidence is preserved')
    directories = {args.attempt_dir.parent, *(path.parent for path in outputs)}
    def before():
        for directory in directories:
            _live_checks(BATCH_REPLAY, directory, deadline, pending_metadata_bytes=32*1024**2)
    before()
    origin = check_invocation_origin()
    resource_plan(args.worker_cpus, 0)
    sources = suffix_census.check_sources(binding.ROOT, args.source_commit, args.source_sha)
    suffix_census.same(check_invocation_origin(sources), origin, 'controller invocation origin changed')
    policy = source_policy(args, before)
    scope, registry = load_registry(args, policy, deadline=deadline, before=before)
    window = plan_window(scope, registry)
    if not window['launch_required']:
        before()
        return dict(status='terminal_empty', launch_required=False, window_id=None,
                    completed_block_ids=list(registry.completed_block_ids()), **FALSE_AUTHORITY)
    before()
    suffix_census.same(check_invocation_origin(sources), origin, 'controller invocation origin changed before launch')
    result = run_phase(worker_command(args, deadline), attempt_dir=args.attempt_dir,
        profile=BATCH_REPLAY, cpu=args.cpu, worker_cpus=tuple(args.worker_cpus),
        context=PlanContext(args.replay_plan_sha, args.source_sha, binding.digest(input_context(args)), BATCH_REPLAY.name),
        entry_monotonic=float(ENTRY), deadline_monotonic=deadline)
    if result.get('status') != 'completed':
        return dict(status='unregistered', runtime_result=result, window_id=window['window_id'], **FALSE_AUTHORITY)
    try:
        retained = retain_return(result, runtime_return_path(args), before)
        def final_check():
            before()
            suffix_census.same(check_invocation_origin(sources), origin, 'controller invocation origin changed')
            verify_loaded({'source_files': sources})
            suffix_census.check_sources(binding.ROOT, args.source_commit, args.source_sha)
            suffix_census.same(source_policy(args, before), policy, 'reviewed source policy changed')
            before()
        final_check()
        return register_completed(args, scope, registry, result, policy, deadline=deadline, before=before,
                                  retained_return=retained, final_check=final_check)
    except BaseException as error:
        return dict(status='registration_failed', raw_attempt=str(args.attempt_dir),
            runtime_status=result['status'], runtime_result=result, window_id=window['window_id'],
            reason=type(error).__name__+': '+str(error)[:4096], **FALSE_AUTHORITY)


def parser():
    from .window_receipts import COMMON_PATHS, COMMON_PINS
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument('--worker', action='store_true')
    value.add_argument('--deadline', type=float)
    for key in COMMON_PATHS + ('source_policy', 'registry_output', 'registration_return_output'):
        value.add_argument('--'+key.replace('_', '-'), type=Path, required=True)
    for key in COMMON_PINS + ('source_policy_sha',):
        value.add_argument('--'+key.replace('_', '-'), required=True)
    for key in SEED_FIELDS + REGISTRY_FIELDS:
        value.add_argument('--'+key.replace('_', '-'), default=None,
                           type=str if key.endswith('_sha') else Path)
    value.add_argument('--worker-cpus', type=int, nargs=5, required=True)
    value.add_argument('--cpu', type=int)
    value.add_argument('--attempt-dir', type=Path)
    return value


def main(argv=None):
    args = parser().parse_args(argv)
    if args.worker:
        return worker(args)
    result = controller(args)
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] in ('registered', 'terminal_empty') else 1


if __name__ == '__main__':
    raise SystemExit(main())
