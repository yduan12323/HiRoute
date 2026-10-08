"""Guarded, source-bound final collection for the one original C01 case.

No optimization or execution occurs on import. Historical receipts, selected
physical receipts and query rows remain provisional until the actual successful
guard return and the separate collector acceptance have both been retained.
"""
import time
ENTRY = time.monotonic()

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import resource
import stat
import sys

from . import domain, plan as binding, suffix_census, suffix_window
from .hot_jobs import read_pinned
from .runtime import (FINAL_COLLECTOR, BoundedEvidenceWriter, PlanContext,
                      _directory, _identity, _inventory, _live_checks,
                      read_phase_result, run_phase, worker_failure)
from .worker import verify_loaded

MODULE = 'experiments.time_cut_v2.recorded_real.final_collector'
SECONDS = 3600
MAX_PHYSICAL_REQUESTS = 8192
FALSE_AUTHORITY = dict(full_population_complete=False, whole_M5_complete=False,
                       full_C32_complete=False, literal_G8_closed=False)
EVIDENCE_FILES = frozenset(('run-binding.json', 'batch-ledger.json', 'family-summary.json',
    'reconciled-registry.json', 'query-plan.json', 'physical-request-rows.json',
    'physical-witnesses.jsonl', 'physical-summary.json', 'empty-partition.json',
    'query-results.jsonl', 'collector-summary.json'))
INPUT_EXCLUSIONS = frozenset(('worker', 'deadline', 'cpu', 'attempt_dir'))


def same(actual, expected, why):
    suffix_census.same(actual, expected, 'final collector: '+why)


def check_invocation_origin(source_files=None):
    """Observe this entrypoint, checkout and current interpreter explicitly."""
    root = binding.ROOT.resolve()
    expected = root/'experiments/time_cut_v2/recorded_real/final_collector.py'
    binding.require(Path.cwd().resolve() == root, 'reviewed collector checkout cwd required')
    binding.require(Path(__file__).resolve() == expected, 'reviewed collector module origin changed')
    spec = importlib.util.find_spec(MODULE)
    binding.require(spec is not None and spec.origin is not None and
                    Path(spec.origin).resolve() == expected, 'reviewed collector resolution changed')
    executable = Path(sys.executable)
    binding.require(executable.is_absolute() and executable.is_file() and
        os.access(executable, os.X_OK) and os.path.samefile(executable, '/proc/self/exe'),
        'current trusted interpreter executable required')
    package = 'experiments.time_cut_v2.recorded_real'
    for name, module in tuple(sys.modules.items()):
        if name != package and not name.startswith(package+'.'):
            continue
        relative = (Path(*name.split('.'))/'__init__.py' if name == package else
                    Path(*name.split('.')).with_suffix('.py'))
        path = Path(module.__file__).resolve()
        binding.require(path == root/relative, 'foreign loaded collector module: '+name)
        if source_files is not None:
            binding.require(relative.as_posix() in source_files and
                binding.pin(path) == source_files[relative.as_posix()], 'loaded collector source changed: '+name)
    if source_files is not None:
        relative = expected.relative_to(root).as_posix()
        binding.require(relative in source_files and binding.pin(expected) == source_files[relative],
                        'collector entry source bytes changed')
        verify_loaded({'source_files': source_files})
    return dict(schema='hiroute-reviewed-controller-origin-v1', checkout_root=str(root),
        controller_module=MODULE, controller_path=str(expected), python_executable=sys.executable,
        executable_realpath=str(executable.resolve()), cwd=str(Path.cwd().resolve()))


def input_context(args):
    return {key: str(value) if isinstance(value, Path) else value
            for key, value in vars(args).items() if key not in INPUT_EXCLUSIONS}


def worker_command(args, deadline):
    command = [sys.executable, '-B', '-m', MODULE, '--worker', '--deadline', repr(deadline)]
    for key, value in input_context(args).items():
        if value is not None:
            command.append('--'+key.replace('_', '-'))
            command.extend(map(str, value)) if key == 'worker_cpus' else command.append(str(value))
    return command


def resource_plan(cpus, cpu=0):
    binding.require(type(cpus) is list and cpus == [1, 2, 3, 4, 5] and
        all(type(value) is int for value in cpus) and type(cpu) is int and cpu == 0,
        'fixed supervisor CPU 0 and coordinator/family CPUs 1 through 5 required')
    p = FINAL_COLLECTOR
    same([p.wall_seconds, p.child_as_bytes, p.group_rss_bytes, p.evidence_bytes,
          p.supervisor_evidence_bytes, p.host_reserve_bytes, p.disk_floor_bytes],
         [3600, 16*1024**3, 20*1024**3, 1024**3, 16*1024**2, 16*1024**3, 20*1024**3],
         'fixed collector guard changed')
    return dict(name='C01-final-collector-v1', absolute_seconds=SECONDS, supervisor_cpu=cpu,
        worker_cpus=cpus, family_workers=4, family_worker_as_bytes=1024**3,
        coordinator_as_bytes=p.child_as_bytes, group_rss_bytes=p.group_rss_bytes,
        evidence_charge_bytes=p.evidence_bytes, worker_evidence_bytes=p.worker_evidence_bytes,
        supervisor_evidence_bytes=p.supervisor_evidence_bytes,
        host_available_floor_bytes=p.host_reserve_bytes, disk_floor_bytes=p.disk_floor_bytes,
        maximum_physical_requests=MAX_PHYSICAL_REQUESTS, numerical_solver_calls=0)


def load_registry(args, policy, *, admitted=None, deadline, before):
    from . import window_receipts as receipts
    options = dict(registration_return=args.registry_return,
        registration_return_sha=args.registry_return_sha, reviewed_sources=policy,
        deadline=deadline, before=before)
    scope = admitted if admitted is not None else receipts.scope_from_registered_registry(
        args.registry, args.registry_sha, **options)
    registry = receipts.load_scheduling_registry(args.registry, args.registry_sha, scope, **options)
    require_complete_registry(scope, registry)
    before()
    return scope, registry


def require_complete_registry(scope, registry):
    from .window_receipts import CheckedRegistry, ReceiptScope
    from .indexed_population import AdmittedSuffixPopulation
    binding.require(type(registry) is CheckedRegistry and
        type(scope) in (ReceiptScope, AdmittedSuffixPopulation), 'authenticated final registry required')
    catalogue = scope.plan() if type(scope) is ReceiptScope else scope.population.plan()
    commitment, metadata = scope.commitment(), registry.metadata()
    same([catalogue['block_size'], catalogue['total_models'], len(catalogue['blocks']),
          commitment['unique_logical_models'], commitment['queries'],
          commitment['original_model_occurrences'], commitment['empty_action_queries']],
         [256, 695712, 2718, 695712, 12172, 7652832, 9666], 'fixed C01 population changed')
    same(metadata['population'], commitment, 'registry population changed')
    same([row['range'] for row in metadata['blocks']], catalogue['blocks'],
         'final registry lacks full canonical block coverage')
    same(metadata['completed_models'], catalogue['total_models'], 'final registry model coverage incomplete')
    return commitment


def retained_snapshot(args, registry, before):
    """Continuity only; actual byte authentication belongs to cold admission.

    Keep original archives external. Include the complete admitted historical
    runtime trees, not just their manifest payloads: journals, control files,
    spools and directory identities must remain unchanged after cold admission.
    This is metadata continuity, without another archive byte-hash pass.
    """
    from .window_receipts import COMMON_PATHS
    paths = {Path(getattr(args, name)) for name in COMMON_PATHS
             if name not in ('replay_attempt', 'logical_attempt')}
    paths.update((args.registry, args.registry_return, args.source_policy))
    entries = registry.metadata()['entries']
    attempts = {Path(args.replay_attempt), Path(args.logical_attempt)}
    for entry in entries:
        attempts.add(Path(entry['attempt']))
        paths.update(Path(row['path']) for row in entry['dependencies'])
    rows = {}
    for path in sorted(paths):
        before()
        rows[str(path.absolute())] = file_identity(path)
    for root in sorted(attempts):
        before()
        for relative, identity in attempt_snapshot(root, before).items():
            path = str((root/relative).absolute())
            if path in rows:
                # Ordinary dependency identities omit nlink; closed-tree
                # identities retain the existing runtime inventory's 7 fields.
                previous = rows[path]
                comparable = (identity[0], identity[1], identity[2], *identity[4:]) \
                    if len(previous) == 6 else identity
                same(previous, comparable, 'retained input changed during tree inventory: '+path)
            rows[path] = identity
    return rows


def file_identity(path):
    from .archive_reader import _open_regular
    fd = _open_regular(path)
    try:
        info = os.fstat(fd)
        return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
                info.st_mtime_ns, info.st_ctime_ns)
    finally:
        os.close(fd)


def check_snapshot(snapshot, before):
    for path, expected in snapshot.items():
        before()
        binding.require(type(expected) is tuple and len(expected) in (6, 7) and
                        all(type(value) is int for value in expected), 'live input identity required')
        if len(expected) == 6:
            actual = file_identity(path)
        else:
            from .archive_reader import _open_regular
            binding.require(stat.S_ISDIR(expected[2]) or stat.S_ISREG(expected[2]),
                            'regular historical tree entry required')
            fd = _directory(Path(path)) if stat.S_ISDIR(expected[2]) else _open_regular(path)
            try:
                actual = _identity(os.fstat(fd))
            finally:
                os.close(fd)
        same(actual, expected, 'retained input changed: '+path)


def attempt_snapshot(root, before):
    """Track the entire closed output/control tree, including newly added files."""
    from .archive_reader import _open_regular
    fd = _directory(root)
    os.close(fd)
    rows = _inventory(root, before)
    for relative, identity in rows.items():
        before()
        path = root/relative
        fd = _directory(path) if stat.S_ISDIR(identity[2]) else _open_regular(path)
        try:
            same(_identity(os.fstat(fd)), identity, 'attempt changed during inventory')
        finally:
            os.close(fd)
    same(_inventory(root, before), rows, 'attempt changed during inventory')
    return rows


def check_case(args):
    original = read_pinned(args.historical_plan, args.historical_plan_sha, 4*1024**2)
    binding.require(original['state_id'] == 'C01' and original['H_ref'] == 4 and original['sites'] == 8 and
        original['regions'] == 2047 and original['dominance'] is True and original['external_incumbent'] is None,
        'fixed C01 physical population required')
    return original


def checked_chunks(chunks, before):
    for chunk in chunks:
        before()
        binding.require(type(chunk) is bytes and len(chunk) <= 65536, 'bounded immutable output chunk required')
        yield chunk
    before()


def write_json(writer, name, value, before):
    return writer.write(name, checked_chunks(domain.chunks(value), before))


def stream_physical(plan, admitted, registry, writer, *, deadline, before):
    """One synchronous producer; retain only compact pointers, never witnesses."""
    from .query_witnesses import replay_selected_witnesses
    summary, requests = plan.summary(), plan.physical_requests()
    rows = plan.physical_request_rows()
    binding.require(len(requests) <= MAX_PHYSICAL_REQUESTS, 'physical request count cap')
    same(rows, [dict(model_ordinal=n, **requests[n]) for n in sorted(requests)], 'physical request map differs')
    same(binding.digest(rows), summary['physical_request_rows_sha256'], 'physical request hash differs')
    same(len(binding.canonical(rows)), summary['physical_request_bytes'], 'physical request bytes differ')
    write_json(writer, 'physical-request-rows.json', rows, before)
    del rows
    compact, pointers, points, coverage = {}, {}, {}, None
    offset = 0

    def produce(sink):
        nonlocal coverage, offset
        def emit(row):
            nonlocal offset
            before()
            n = row['model_ordinal']
            binding.require(type(n) is int and n in requests and n not in compact,
                            'foreign or duplicate physical witness ordinal')
            binding.require(row['schema'] == 'hiroute-selected-query-model-witness-v1' and
                row['provisional'] is True and row['physical_receipt']['physical_witness_verified'] is True,
                'fresh provisional physical receipt required')
            same(row['descriptor'], requests[n]['descriptor'], 'physical witness descriptor differs')
            same(row['result'], requests[n]['result'], 'physical witness result differs')
            same(row['physical_receipt']['result'], row['result'], 'physical receipt result differs')
            for key in ('population_sha256', 'physical_request_rows_sha256'):
                same(row['provenance'][key], summary[key], 'physical witness '+key+' differs')
            same(row['provenance']['registry_sha256'], summary['registry_metadata_sha256'],
                 'physical witness registry differs')
            receipt_sha = binding.digest(row)
            compact[n] = dict(model_ordinal=n, descriptor_sha256=binding.digest(row['descriptor']),
                model_sha256=row['model_sha256'], record_sha256=row['record_sha256'],
                result_sha256=binding.digest(row['result']), provenance_sha256=binding.digest(row['provenance']),
                receipt_sha256=receipt_sha)
            points[n] = {key: row['physical_receipt']['physical_audit'][key]
                         for key in ('kind', 'J', 'Q_total', 'H', 'pi')}
            digest, size = hashlib.sha256(), 0
            for chunk in checked_chunks(domain.chunks(row), before):
                sink(chunk); digest.update(chunk); size += len(chunk)
            pointers[n] = dict(path='physical-witnesses.jsonl', row_index=len(pointers),
                byte_offset=offset, size_bytes=size, row_sha256=digest.hexdigest(), receipt_sha256=receipt_sha)
            offset += size
            before()
        coverage = replay_selected_witnesses(admitted, registry, requests, emit,
                                             deadline=deadline, before=before)
        binding.require(coverage['selected_replay_complete'] is True and set(compact) == set(requests),
                        'incomplete physical witness coverage')
        same(coverage['selected_models'], len(requests), 'physical replay count differs')
        same(coverage['witnesses'], [compact[n] for n in sorted(compact)], 'physical compact coverage differs')
        for key in ('population_sha256', 'physical_request_rows_sha256', 'physical_request_bytes'):
            same(coverage[key], summary[key], 'completed physical '+key+' differs')
        same(coverage['registry_sha256'], summary['registry_metadata_sha256'], 'completed physical registry differs')
        before()
    archive = writer.write_from_callback('physical-witnesses.jsonl', produce)
    before()
    same(archive['size_bytes'], offset, 'physical receipt stream bytes differ')
    return dict(coverage=coverage, archive=archive,
                receipts={n: dict(compact[n], pointer=pointers[n], physical_point=points[n])
                          for n in sorted(compact)})


def emit_queries(plan, partition, physical, emit, *, before=lambda: None):
    """Merge exact trace event IDs; retain unchanged joins, tie runs and audits."""
    from .query_collection import QueryCollectionPlan, EmptyOccurrencePartition
    binding.require(type(plan) is QueryCollectionPlan and type(partition) is EmptyOccurrencePartition and
                    callable(emit), 'completed original query plan and recovered partition required')
    summary, report = plan.summary(), partition.report()
    for key in ('population_sha256', 'query_collection_rows_sha256'):
        same(report[key], summary[key], 'empty partition '+key+' differs')
    recovered = report['recovered']
    same(recovered['exact_queries'], summary['queries'], 'empty partition nonempty count differs')
    same(recovered['empty_action_queries'], summary['empty_action_queries'], 'empty partition count differs')
    same(recovered['empty_action_sha256'], summary['empty_action_sha256'], 'empty partition hash differs')
    same(recovered['trace_sha256'], summary['original_trace_sha256'], 'empty partition trace differs')
    same(recovered['total_query_events'], summary['queries']+summary['empty_action_queries'], 'event count differs')
    empty, audits = recovered['rows'], recovered['audits']
    same(len(empty), summary['empty_action_queries'], 'empty rows missing')
    same(len(audits), len(empty), 'empty audits missing')
    same(binding.digest(empty), summary['empty_action_sha256'], 'exact recovered empty rows differ')
    same(len(recovered['query_ids']), recovered['total_query_events'], 'global query IDs missing')
    expected_bindings = plan.query_bindings()
    same(binding.digest(expected_bindings), summary['query_bindings_sha256'], 'query bindings hash differs')
    requests, receipts = plan.physical_requests(), physical['receipts']
    binding.require(set(receipts) == set(requests), 'missing or foreign physical receipt map')
    before()
    query_iter = iter(plan.iter_queries(before=before))
    row = next(query_iter, None)
    nonempty_count = empty_count = physical_bindings = occurrences = 0
    previous = -1
    seen_bindings, used_physical = set(), set()
    row_digest = hashlib.sha256()
    statuses, bounds = Counter(), Counter()
    for seq in recovered['query_ids']:
        before()
        binding.require(type(seq) is int and seq > previous, 'duplicate or unordered global query ID')
        previous = seq
        if empty_count < len(empty) and empty[empty_count]['query_seq'] == seq:
            source, audit = empty[empty_count], audits[empty_count]
            same(audit['query_seq'], seq, 'empty audit query ID differs')
            binding.require(source['actions'] == [] and source['classification'] == 'empty_actions' and
                source['bound'] is None and source['queue_serial'] is None, 'exact empty-action row required')
            result = audit['result']
            same(result, dict(status='empty_restricted_family'), 'empty result differs')
            same(audit['audit'], dict(bound_valid=True, bound_status='vacuous_empty_restricted_family',
                bound_gap=None, recorded_bound=None, primary_infimum=None), 'empty audit differs')
            final = dict(schema='hiroute-final-original-query-v1', query_seq=seq,
                occurrence_kind='empty_actions', original_empty_row=source, result=result,
                bound_audit=audit['audit'], query_optimum_certified=True, physical_witness_required=False,
                physical_witness_verified=False, **FALSE_AUTHORITY)
            empty_count += 1
        else:
            binding.require(row is not None and row['query_binding']['query_seq'] == seq,
                            'missing, duplicate or foreign nonempty query ID')
            q = row['query_binding']
            binding.require(nonempty_count < len(expected_bindings), 'extra nonempty query row')
            same(q, expected_bindings[nonempty_count], 'distinct original query binding differs')
            binding.require(q['binding_id'] not in seen_bindings, 'duplicate query binding')
            same(binding.digest({key: value for key, value in q.items() if key != 'binding_id'}),
                 q['binding_id'], 'query binding digest differs')
            seen_bindings.add(q['binding_id'])
            joined = row['joined']; result = joined['aggregate']['result']
            same(q['projection_sha256'], binding.digest(joined['projection']), 'query projection binding differs')
            same(q['result_sha256'], binding.digest(result), 'query result binding differs')
            n = q['model_ordinal']; receipt = None
            if n is not None:
                binding.require(type(n) is int and n in receipts and row['physical_witness_required'] is True,
                                'query selected physical witness missing')
                receipt = receipts[n]
                same(receipt['descriptor_sha256'], q['descriptor_sha256'], 'query descriptor binding differs')
                same(receipt['result_sha256'], q['result_sha256'], 'query physical result binding differs')
                same(receipt['model_ordinal'], n, 'query physical ordinal differs')
                same(receipt['pointer']['receipt_sha256'], receipt['receipt_sha256'], 'query receipt pointer differs')
                used_physical.add(n); physical_bindings += 1
            else:
                binding.require(row['physical_witness_required'] is False and
                    result['status'] == 'empty_restricted_family', 'nonempty result lacks selected witness')
            row_digest.update(binding.canonical(row)+b'\n')
            occurrences += joined['projection']['model_slots']
            final = dict(schema='hiroute-final-original-query-v1', query_seq=seq,
                occurrence_kind='nonempty_actions', query_binding=q, joined=joined,
                result=result, bound_audit=joined['bound_audit'], physical_receipt=receipt,
                physical_witness_required=n is not None, physical_witness_verified=n is not None,
                query_optimum_certified=True, **FALSE_AUTHORITY)
            nonempty_count += 1
            row = next(query_iter, None)
        statuses[result['status']] += 1
        bounds[final['bound_audit']['bound_status']] += 1
        # Negative exact gaps are mathematical findings. An approach witness at
        # fixed epsilon need not itself lie below the bound; never invent a point.
        final['bound_counterexample'] = final['bound_audit']['bound_status'] == 'violated'
        final['point_level_counterexample_claimed'] = False
        emit(final)
        before()
    binding.require(row is None, 'unconsumed nonempty query row')
    same([nonempty_count, empty_count, physical_bindings, occurrences],
         [summary['queries'], summary['empty_action_queries'], summary['physical_query_bindings'],
          summary['original_model_occurrences']], 'final original occurrence coverage differs')
    same(len(expected_bindings), nonempty_count, 'query binding coverage differs')
    same(row_digest.hexdigest(), summary['query_collection_rows_sha256'], 're-emitted query-row digest differs')
    binding.require(used_physical == set(requests), 'unused physical witness request')
    allowed = {'satisfied', 'violated', 'missing_bound_for_nonempty_family', 'vacuous_empty_restricted_family'}
    binding.require(set(bounds) <= allowed, 'unknown bound disposition')
    violations, missing = bounds['violated'], bounds['missing_bound_for_nonempty_family']
    before()
    return dict(complete=True, numerical_evidence_complete=True, physical_evidence_complete=True,
        original_occurrence_evidence_complete=True, original_nonempty_queries=nonempty_count,
        empty_action_queries=empty_count, total_query_events=nonempty_count+empty_count,
        verified_unique_logical_models=summary['unique_logical_models'], complete_blocks=summary['complete_blocks'],
        original_model_occurrences=occurrences, physical_query_bindings=physical_bindings,
        unique_physical_requests=len(requests), zero_length_queries=summary['zero_length_queries'],
        all_excluded_nonempty_queries=summary['all_excluded_nonempty_queries'],
        query_collection_rows_sha256=row_digest.hexdigest(), result_counts=dict(statuses),
        bound_status_counts=dict(bounds), bound_valid_queries=bounds['satisfied']+bounds['vacuous_empty_restricted_family'],
        bound_counterexample_queries=violations, missing_bound_queries=missing,
        single_C01_case_bound_valid=violations == missing == 0,
        single_C01_case_accepted=violations == missing == 0,
        single_C01_case_bound_status='counterexample' if violations else 'missing_bounds' if missing else 'satisfied',
        point_level_counterexample_claimed=False, **FALSE_AUTHORITY)


def worker(args):
    writer = pool = None
    stage = 'binding'
    observations = []
    started, cpu_started = time.monotonic(), time.process_time()
    def before():
        binding.require(type(args.deadline) is float and math.isfinite(args.deadline) and
                        time.monotonic() < args.deadline, 'final collector absolute deadline')
    def observe(name, **counts):
        before()
        row = dict(stage=name, wall_seconds=time.monotonic()-started,
                   coordinator_cpu_seconds=time.process_time()-cpu_started, **counts)
        observations.append(row)
        print(json.dumps(dict(kind='provisional-collector-progress', acceptance=False, **row), sort_keys=True), flush=True)
    try:
        before(); origin = check_invocation_origin()
        resources = resource_plan(args.worker_cpus)
        binding.require(os.environ.get('HIROUTE_PROFILE') == FINAL_COLLECTOR.name and
            os.environ.get('HIROUTE_EVIDENCE_CAP_BYTES') == str(FINAL_COLLECTOR.worker_evidence_bytes),
            'wrong final collector group guard')
        binding.require(os.sched_getaffinity(0) == set(args.worker_cpus), 'five inherited CPUs required')
        binding.require(not any(name == 'validation' or name.startswith(('validation.', 'timecut5')) or
            name.split('.')[0] in ('numpy', 'scipy', 'sympy') for name in sys.modules),
            'mathematics imported before final collector fence')
        sys.meta_path.insert(0, suffix_census.NoOptimization())
        sources = suffix_census.check_sources(binding.ROOT, args.source_commit, args.source_sha)
        same(check_invocation_origin(sources), origin, 'worker invocation origin changed')
        policy = suffix_window.source_policy(args, before)
        scope, scheduling = load_registry(args, policy, deadline=args.deadline, before=before)
        snapshot = retained_snapshot(args, scheduling, before)
        index, trusted, _, anchors = suffix_census.completed_inputs(binding.ROOT, args, args.deadline, before)
        original = check_case(args)
        payload = read_pinned(args.capture, index['capture_sha256'], 1024**3)
        binding.require(payload['schema'] == 'hiroute-recorded-real-capture-v1' and
            payload['source_plan_sha256'] == args.historical_plan_sha and
            type(payload['suffix_optimizer_calls']) is int and payload['suffix_optimizer_calls'] == 0,
            'original capture identity or optimizer scope changed')
        for key in ('source_sha256', 'input_sha256', 'query_sha256', 'query'):
            same(payload[key], original[key], 'capture '+key+' changed')
        same(payload['variant'], domain.variant(original), 'capture variant changed')
        bundle, trace = payload['bundle'], payload['trace']
        del payload  # Release unused historical callbacks; preserve the exact v2 trace.
        writer = BoundedEvidenceWriter(os.environ['HIROUTE_EVIDENCE_ROOT'],
            FINAL_COLLECTOR.worker_evidence_bytes, profile_name=FINAL_COLLECTOR.name)
        stage = 'fresh-family'
        from validation.real5_v2.batch_jobs import BatchExecutor, WORKER_AS
        from validation.family5.checker import _plain
        from .family_gate import verify_families
        binding.require(WORKER_AS == 1024**3, 'scalar family child cap changed')
        with BatchExecutor(tuple(args.worker_cpus[1:]), float(args.deadline-10), index['capture_sha256'],
                           kernel='interval-join-v1') as pool:
            binding.require(len(pool.slots) == 4 and all(slot.process.poll() is None for slot in pool.slots),
                            'four family workers required')
            os.sched_setaffinity(0, {args.worker_cpus[0]})
            ctx, ledger = verify_families(bundle, trusted, pool)
        del bundle
        binding.require(all(slot.process.poll() is not None for slot in pool.slots), 'family workers not reaped')
        binding.require(os.sched_getaffinity(0) == {args.worker_cpus[0]}, 'collector coordinator affinity changed')
        write_json(writer, 'batch-ledger.json', ledger, before)
        write_json(writer, 'family-summary.json', _plain(ctx.summary), before)
        observe(stage)
        stage = 'cold-registry'
        from .indexed_population import admit_population
        from .window_receipts import reconcile_registry
        admitted = admit_population(binding.ROOT, args, ctx, args.deadline, before)
        same(admitted.commitment(), scope.commitment(), 'fresh population differs from preflight')
        _, scheduling = load_registry(args, policy, admitted=admitted, deadline=args.deadline, before=before)
        registry = reconcile_registry(scheduling, admitted, reviewed_sources=policy, deadline=args.deadline, before=before)
        require_complete_registry(admitted, registry)
        registry_pin = write_json(writer, 'reconciled-registry.json', registry.metadata(), before)
        same(registry_pin['sha256'], args.registry_sha, 'reconciled registry bytes changed')
        observe(stage, blocks=2718, models=695712)
        stage = 'original-query-planning'
        from .query_collection import plan_query_collection
        plan = plan_query_collection(admitted, registry, before=before)
        partition = plan.recover_empty_partition(trace, before=before)
        del trace
        summary = plan.summary()
        same([summary['queries'], summary['original_model_occurrences'], summary['empty_action_queries'],
              partition.report()['recovered']['total_query_events']], [12172, 7652832, 9666, 21838],
             'fixed original query partition changed')
        write_json(writer, 'query-plan.json', summary, before)
        write_json(writer, 'empty-partition.json', partition.report(), before)
        write_json(writer, 'run-binding.json', dict(schema='hiroute-final-collector-binding-v1',
            source_commit=args.source_commit, source_sha256=args.source_sha, completed_replay=anchors,
            input_context=input_context(args), input_context_sha256=binding.digest(input_context(args)),
            resource_plan=resources, registry=registry_pin, invocation_origin=origin,
            external_dependencies_sha256=binding.digest(snapshot)), before)
        observe(stage, queries=12172, empty_queries=9666, physical_requests=summary['unique_physical_requests'])
        stage = 'selected-physical-witnesses'
        physical = stream_physical(plan, admitted, registry, writer, deadline=args.deadline, before=before)
        write_json(writer, 'physical-summary.json', dict(coverage=physical['coverage'], archive=physical['archive'],
            receipts=[physical['receipts'][n] for n in sorted(physical['receipts'])]), before)
        observe(stage, physical_requests=len(physical['receipts']))
        stage = 'original-query-results'
        collected = None
        def produce(sink):
            nonlocal collected
            def emit(row):
                for chunk in checked_chunks(domain.chunks(row), before):
                    sink(chunk)
            collected = emit_queries(plan, partition, physical, emit, before=before)
        query_pin = writer.write_from_callback('query-results.jsonl', produce)
        observe(stage, query_events=collected['total_query_events'])
        stage = 'final-binding'
        def final_check():
            before()
            same(check_invocation_origin(sources), origin, 'worker invocation origin changed')
            suffix_census.check_sources(binding.ROOT, args.source_commit, args.source_sha)
            same(suffix_window.source_policy(args, before), policy, 'reviewed source policy changed')
            check_snapshot(snapshot, before)
        final_check()
        write_json(writer, 'collector-summary.json', dict(schema='hiroute-final-collector-summary-v1',
            source_commit=args.source_commit, source_sha256=args.source_sha, population=admitted.commitment(),
            resource_plan=resources, registry=registry_pin, query_results=query_pin,
            physical_archive=physical['archive'], observations=observations, **collected), before)
        same(sorted(row['path'] for row in writer.files), sorted(EVIDENCE_FILES), 'collector evidence coverage changed')
        final_check(); writer.finalize(); final_check()
        return 0
    except BaseException as error:
        worker_failure(type(error).__name__, str(error)[:4096], stage)
        return 1
    finally:
        if writer is not None:
            writer.close()


def controller(args):
    binding.require(args.cpu is not None and args.attempt_dir is not None,
                    'supervisor CPU and fresh collector attempt required')
    resources = resource_plan(args.worker_cpus, args.cpu)
    deadline = float(ENTRY+SECONDS)
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    binding.require(hard == resource.RLIM_INFINITY or hard >= FINAL_COLLECTOR.child_as_bytes,
                    'inherited AS ceiling too small')
    resource.setrlimit(resource.RLIMIT_AS,
        (min(512*1024**2, soft) if soft != resource.RLIM_INFINITY else 512*1024**2, hard))
    outputs = (args.runtime_return_output, args.collector_output)
    resolved = [path.resolve() for path in outputs]
    binding.require(len(set(resolved)) == len(resolved) and all(path != args.attempt_dir.resolve() and
        args.attempt_dir.resolve() not in path.parents for path in resolved),
        'collector acceptance and actual return must be distinct external paths')
    binding.require(not args.attempt_dir.exists() and not args.attempt_dir.is_symlink() and all(
        path.parent.is_dir() and not path.exists() and not path.is_symlink() and
        not path.with_name(path.name+'.partial').exists() for path in outputs),
        'fresh attempt and return/acceptance paths required; previous evidence is preserved')
    directories = {args.attempt_dir.parent, *(path.parent for path in outputs)}
    def before():
        for directory in directories:
            _live_checks(FINAL_COLLECTOR, directory, deadline, pending_metadata_bytes=32*1024**2)
    before(); origin = check_invocation_origin()
    sources = suffix_census.check_sources(binding.ROOT, args.source_commit, args.source_sha)
    same(check_invocation_origin(sources), origin, 'controller origin changed')
    policy = suffix_window.source_policy(args, before)
    _, registry = load_registry(args, policy, deadline=deadline, before=before)
    snapshot = retained_snapshot(args, registry, before)
    check_case(args)
    evidence_snapshot = {}
    complete_attempt_snapshot = None
    def final_check():
        before()
        same(check_invocation_origin(sources), origin, 'controller origin changed')
        suffix_census.check_sources(binding.ROOT, args.source_commit, args.source_sha)
        same(suffix_window.source_policy(args, before), policy, 'reviewed source policy changed')
        check_snapshot(snapshot, before)
        check_snapshot(evidence_snapshot, before)
        if complete_attempt_snapshot is not None:
            same(attempt_snapshot(args.attempt_dir, before), complete_attempt_snapshot,
                 'complete collector attempt changed')
        before()
    final_check()
    result = run_phase(worker_command(args, deadline), attempt_dir=args.attempt_dir,
        profile=FINAL_COLLECTOR, cpu=args.cpu, worker_cpus=tuple(args.worker_cpus),
        context=PlanContext(args.replay_plan_sha, args.source_sha, binding.digest(input_context(args)), FINAL_COLLECTOR.name),
        entry_monotonic=float(ENTRY), deadline_monotonic=deadline)
    if result.get('status') != 'completed':
        return dict(status='unaccepted', runtime_result=result, **FALSE_AUTHORITY)
    try:
        # Preserve the actual returned object even if subsequent checks fail.
        retained = suffix_window.retain_return(result, args.runtime_return_output, before)
        from .window_receipts import _read
        evidence_snapshot[str(args.runtime_return_output)] = file_identity(args.runtime_return_output)
        same(_read(args.runtime_return_output, retained['sha256'], 65536, before,
                   size=retained['size_bytes']), result, 'retained actual runtime return changed')
        final_check()
        evidence = args.attempt_dir/'evidence'
        manifest = _read(evidence/'__manifest.json', result['verified_manifest_sha256'], 65536, before)
        files = {row['path']: row for row in manifest['files']}
        same(sorted(files), sorted(EVIDENCE_FILES), 'accepted manifest coverage changed')
        binding.require(len(files) == len(manifest['files']), 'duplicate accepted manifest path')
        evidence_snapshot.update({str(evidence/name): file_identity(evidence/name)
                                  for name in (*sorted(files), '__manifest.json')})
        complete_attempt_snapshot = attempt_snapshot(args.attempt_dir, before)
        checked = read_phase_result(args.attempt_dir, successful_return=result,
                                   deadline_monotonic=deadline, resource_check=before)
        binding.require(checked['status'] == 'completed', 'collector actual return/cold evidence incomplete')
        final_check()
        summary_pin = files['collector-summary.json']
        summary = _read(evidence/'collector-summary.json', summary_pin['sha256'], 1024**2, before,
                        size=summary_pin['size_bytes'])
        binding.require(summary['schema'] == 'hiroute-final-collector-summary-v1' and summary['complete'] is True,
                        'completed collector summary required')
        same(summary['resource_plan'], resources, 'accepted resource plan differs')
        for key, value in FALSE_AUTHORITY.items():
            same(summary[key], value, 'global authority exceeded')
        acceptance = dict(schema='hiroute-final-collector-acceptance-v1', status='collected',
            runtime_return=dict(path=str(args.runtime_return_output), **retained),
            manifest_sha256=result['verified_manifest_sha256'], summary=summary_pin,
            raw_attempt=str(args.attempt_dir), source_commit=args.source_commit, source_sha256=args.source_sha,
            complete=True, single_C01_case_bound_status=summary['single_C01_case_bound_status'],
            single_C01_case_bound_valid=summary['single_C01_case_bound_valid'],
            single_C01_case_accepted=summary['single_C01_case_accepted'], **FALSE_AUTHORITY)
        expected_acceptance = binding.canonical(acceptance)+b'\n'
        def publication_check():
            final_check()
            if args.collector_output.exists():
                same(_read(args.collector_output, hashlib.sha256(expected_acceptance).hexdigest(),
                           65536, before, size=len(expected_acceptance)), acceptance,
                     'collector acceptance bytes changed')
        pin = suffix_window.retain_return(acceptance, args.collector_output, publication_check, revoke_on_failure=True)
        return dict(acceptance, acceptance=dict(path=str(args.collector_output), **pin))
    except BaseException as error:
        return dict(status='collection_acceptance_failed', raw_attempt=str(args.attempt_dir),
            runtime_status=result['status'], runtime_result=result,
            reason=type(error).__name__+': '+str(error)[:4096], **FALSE_AUTHORITY)


def parser():
    from .window_receipts import COMMON_PATHS, COMMON_PINS
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument('--worker', action='store_true')
    value.add_argument('--deadline', type=float)
    for key in COMMON_PATHS + ('source_policy', 'registry', 'registry_return',
                                'runtime_return_output', 'collector_output'):
        value.add_argument('--'+key.replace('_', '-'), type=Path, required=True)
    for key in COMMON_PINS + ('source_policy_sha', 'registry_sha', 'registry_return_sha'):
        value.add_argument('--'+key.replace('_', '-'), required=True)
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
    return 0 if result['status'] == 'collected' else 1


if __name__ == '__main__':
    raise SystemExit(main())
