"""Cold-check the failed fixed pilot, then propose only its two missing proofs.

The historical archive stays historical. Retained dispositions reference its
authenticated rows; only fresh candidates use the current source identity.
Execution requires the existing guarded controller and independent admissions.
"""
import time
ENTRY = time.monotonic()
import argparse
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import sys

from . import block_pilot as pilot, domain, plan as binding, suffix_census
from .archive_reader import ArchiveReader
from .block_archive import ArchiveEncoding, QuotaWriter, EVIDENCE_BYTES, RAW_ARCHIVE_BYTES
from .hot_jobs import read_pinned
from .runtime import BATCH_REPLAY, BoundedEvidenceWriter, PlanContext, run_phase, worker_failure
from .worker import verify_loaded

SECONDS = 900
OLD_ARCHIVE_SHA = 'e7371f1ec32492ff05a05907b52261d9d10ab20112be9222f5aad1d3eb8360cc'
OLD_ARCHIVE_BYTES = 756356
OLD_SUMMARY_SHA = '21ac485da78fed7ad4204bfc80f5c2d3ba63d60b61bd6707c180b907a470dd8e'
OLD_SELECTION_SHA = '51e286751fb08d2d8c38fc0b82e103b4963f9079d1741d398323a5fdef05d50b'
OLD_SOURCE_SHA = '40077c391ddf574c7d482d52834c61673efe747ae361dfb97792b2118a874851'
BLOCK_IDS = [0, 1352, 2535, 2687]
MODEL_PINS = {687940: '881b4cb7e681938fa88323567a569c4f05451b14824d6e6eb33042139d6ba7c5',
              687941: '2bdf894e31c7567faa61352163b7a47e7813a300a6afd5ee20e627de9d870246'}
FALSE_AUTHORITY = dict(query_optimum_certified=False, full_population_complete=False, literal_G8_closed=False)


def archive_pin():
    return dict(sha256=OLD_ARCHIVE_SHA, size_bytes=OLD_ARCHIVE_BYTES)


def resource_plan(cpus, *, historical=False):
    binding.require(type(cpus) is list and len(cpus) == 5 and
                    all(type(c) is int and c >= 0 for c in cpus) and len(set(cpus)) == 5,
                    'five distinct resource-plan CPUs required')
    value = dict(name='C01-four-block-persistent-resource-v1', absolute_seconds=SECONDS,
                 evidence_charge_bytes=EVIDENCE_BYTES, uncompressed_archive_bytes=RAW_ARCHIVE_BYTES,
                 maximum_input_bytes=pilot.MAX_INPUT_BYTES, models=pilot.MAX_MODELS, block_size=256,
                 persistent_workers=4, candidate_as_bytes=1024**3,
                 candidate_peak_rss_bytes=768*1024**2, seconds_per_model=30,
                 maximum_passes_per_model=12, maximum_candidate_passes=pilot.MAX_MODELS*12,
                 numerical_cache_enabled=False, worker_cpus=cpus)
    if not historical:
        value.update(name='C01-two-model-cold-continuation-v1', retained_models=pilot.MAX_MODELS-2,
                     candidate_models=2, candidate_ordinals=sorted(MODEL_PINS),
                     maximum_candidate_passes=24, maximum_logical_stages=10)
    return value


def candidate_jobs(ctx, selection, source_context, before=lambda: None):
    """Filter original descriptors before building matrices; never build 1,024 jobs."""
    selected = []
    found = []
    for block in selection['blocks']:
        rows = [row for row in block['descriptors'] if row['ordinal'] in MODEL_PINS]
        if rows:
            selected.append(dict(range=block['range'], descriptors=rows))
            found.extend(row['ordinal'] for row in rows)
    binding.require(found == sorted(MODEL_PINS), 'exact original two candidate ordinals required')
    for job in pilot.model_jobs(ctx, dict(blocks=selected), source_context, before):
        binding.require(job.model_sha256 == MODEL_PINS[job.model_ordinal], 'frozen continuation model changed')
        yield job


def replay_history(args, ctx, selection, index, *, deadline, before=lambda: None):
    """Authenticate consumed old bytes and bind them to independently admitted inputs.

    There is deliberately no old pilot successful-return argument. The original
    completed structural/query and logical proofs were admitted separately.
    """
    from .block_replay import replay_blocks
    before()
    old_selection = read_pinned(args.old_selection, OLD_SELECTION_SHA, 8*1024**2)
    old = read_pinned(args.old_summary, OLD_SUMMARY_SHA, 8*1024**2)
    suffix_census.same(old_selection, selection, 'old selection differs from independently admitted population')
    binding.require([b['range']['block_id'] for b in selection['blocks']] == BLOCK_IDS and
                    sum(b['range']['model_count'] for b in selection['blocks']) == pilot.MAX_MODELS,
                    'original four blocks and 1024 models required')
    binding.require(old['schema'] == 'hiroute-four-block-resource-summary-v1' and
                    old['complete'] is False and type(old['verified_models']) is int and
                    old['verified_models'] == pilot.MAX_MODELS-2, 'fixed failed 1022-certificate pilot required')
    for key in FALSE_AUTHORITY:
        binding.require(old[key] is False, 'unsupported historical population authority')
    suffix_census.same(old['population'], selection['population'], 'old population admission changed')
    binding.require(old['selection']['path'] == 'pilot-selection.json' and
                    old['selection']['sha256'] == OLD_SELECTION_SHA, 'old selection byte pin changed')
    suffix_census.same(old['proof_archive'], dict(path='model-proofs.jsonl.gz', **archive_pin()),
                       'old archive byte pin changed')
    suffix_census.same(old['resource_plan'], resource_plan(old['resource_plan']['worker_cpus'], historical=True),
                       'old candidate resource contract changed')
    old_context = dict(schema='hiroute-suffix-block-work-context-v1', source_sha256=OLD_SOURCE_SHA,
                       source_bundle_sha256=ctx.summary['bundle_sha256'], capture_sha256=index['capture_sha256'],
                       block_plan_sha256=selection['population']['block_plan_sha256'],
                       selection_sha256=OLD_SELECTION_SHA,
                       original_query_freeze_sha256=index['query_freeze_sha256'],
                       resource_plan_sha256=binding.digest(old['resource_plan']))
    suffix_census.same(old['source_context'], old_context, 'old source context differs from admitted inputs')
    reader = ArchiveReader(args.old_archive, compressed_sha256=OLD_ARCHIVE_SHA,
                           compressed_bytes=OLD_ARCHIVE_BYTES, allow_incomplete=False)
    receipt = replay_blocks(reader, ctx, selection['blocks'], old_context, deadline=deadline, before=before)
    summary = receipt.summary()
    validate_replay(receipt, selection['blocks'], old_context, archive_pin())
    encoding = dict(complete=True, **{k: summary['archive'][k] for k in
                    ('uncompressed_bytes', 'uncompressed_sha256', 'rows', 'encoding')})
    suffix_census.same(old['encoding'], encoding, 'old summary encoding differs from consumed archive')
    binding.require(len(old['blocks']) == len(summary['coverage']), 'old block report count changed')
    for supplied, checked in zip(old['blocks'], summary['coverage']):
        for key, value in checked.items():
            if key != 'physical_witness_verified':
                suffix_census.same(supplied[key], value, 'old summary differs from replayed coverage: ' + key)
    before()
    return receipt


def validate_replay(receipt, blocks, old_context, old_pin):
    """Require exhaustive old dispositions with precisely the two pending slots."""
    from .block_replay import ReplayedBlocks
    binding.require(type(receipt) is ReplayedBlocks, 'cold replay receipt required')
    summary = receipt.summary()
    expected = {row['ordinal'] for b in blocks for row in b['descriptors']}
    binding.require(set(MODEL_PINS) <= expected, 'continuation candidates outside original selection')
    certified = summary['certified_ordinals']
    suffix_census.same(summary['source_context'], old_context, 'retained source context changed')
    suffix_census.same({k: summary['archive'][v] for k, v in
                       (('sha256', 'compressed_sha256'), ('size_bytes', 'compressed_bytes'))},
                       old_pin, 'retained archive pin changed')
    binding.require(summary['archive']['gzip_eof'] is True and
                    summary['historical_archive_finalized'] is True and
                    summary['historical_footer_present'] is True and
                    summary['historical_attempt_claimed_complete'] is False and
                    summary['historical_runtime_revalidated'] is False,
                    'finalized failed historical archive required')
    binding.require(type(certified) is list and all(type(i) is int for i in certified) and
                    certified == sorted(expected - set(MODEL_PINS)) and
                    summary['expected_models'] == summary['observed_models'] == len(expected) and
                    summary['checked_models'] == len(certified), 'cold replay coverage differs from two-model continuation')
    binding.require([row['range'] for row in summary['coverage']] == [b['range'] for b in blocks] and
                    sorted(i for row in summary['coverage'] for i in row['unresolved_ordinals']) == sorted(MODEL_PINS) and
                    not any(row['unsubmitted_ordinals'] for row in summary['coverage']),
                    'cold replay has foreign, missing, or unexpected unresolved models')
    binding.require(all(summary[k] is False for k in FALSE_AUTHORITY), 'unsupported cold replay authority')
    refs = summary['certificate_refs']
    binding.require([r['model_ordinal'] for r in refs] == certified and
                    all(type(r['archive_row_index']) is int and r['archive_row_index'] > 0 for r in refs) and
                    len({r['archive_row_index'] for r in refs}) == len(refs), 'cold replay certificate references changed')
    return summary


def continued_records(ctx, blocks, source_context, receipt, outcomes, *, deadline, before=lambda: None):
    """Join authentic retained certificates and actual new outcomes, never fake frames."""
    from .lp_stream_jobs import LPStreamJob
    from .block_replay import transport_complete
    from validation.suffix5.block_certificates import BlockCertificates
    from validation.suffix5.calibration import verification_deadline, verify_model
    binding.require(type(deadline) is float and math.isfinite(deadline), 'finite continuation deadline required')
    # Own declarations before running progress callbacks.
    blocks = json.loads(binding.canonical(blocks))
    source_context = json.loads(binding.canonical(source_context))
    old_context = source_context['previous_source_context']
    old_pin = source_context['previous_archive']
    summary = validate_replay(receipt, blocks, old_context, old_pin)
    binding.require(source_context['source_sha256'] != old_context['source_sha256'],
                    'continuation must name its new source identity')
    certifier = BlockCertificates(ctx, blocks)
    expected = {r['ordinal']: b['range']['block_id'] for b in blocks for r in b['descriptors']}
    refs = {r['model_ordinal']: r for r in summary['certificate_refs']}
    seen = set()
    retained = fresh = 0

    def guard():
        before()
        binding.require(time.monotonic() < deadline, 'continuation absolute deadline')

    guard()
    yield dict(kind='header', schema='hiroute-suffix-block-resume-archive-v1', source_context=source_context,
               expected_models=len(expected), blocks=[b['range'] for b in blocks],
               candidate_ordinals=sorted(MODEL_PINS), historical_attempt_status='failed',
               historical_runtime_revalidated=False, **FALSE_AUTHORITY)
    for row in receipt.certificates():
        guard()
        ordinal = row['descriptor']['ordinal']
        binding.require(ordinal in refs and ordinal not in seen, 'foreign or duplicate retained certificate')
        reference = refs[ordinal]
        suffix_census.same(row['descriptor'], certifier.descriptor(ordinal), 'retained descriptor changed')
        binding.require(reference['block_id'] == expected[ordinal] and
                        reference['archive_row_sha256'] == hashlib.sha256(binding.canonical(row)+b'\n').hexdigest(),
                        'retained original row reference changed')
        record = row['record']
        old_job = LPStreamJob(old_context, expected[ordinal], ordinal, binding.digest(record['model']), record['model'])
        suffix_census.same(row['candidate_identity'], old_job.header(row['candidate_identity']['generation']),
                           'retained candidate source identity changed')
        with verification_deadline(float(min(deadline-10, time.monotonic()+30))):
            verified = certifier.check(ordinal, record)
        # A late context-manager exception propagates before any disposition is published.
        suffix_census.same(verified, row['verification'], 'retained exact verification changed')
        suffix_census.same(verified, reference['current_verification'], 'cold reference verification changed')
        seen.add(ordinal)
        retained += 1
        yield dict(kind='retained_certificate_reference', descriptor=row['descriptor'], verification=verified,
                   provenance=dict(archive=old_pin, source_context=old_context,
                                   archive_row_index=reference['archive_row_index'],
                                   archive_row_sha256=reference['archive_row_sha256']))
    binding.require(seen == set(refs), 'cold receipt omitted retained certificates')
    candidate_seen = set()
    for outcome in outcomes:
        guard()
        job = LPStreamJob.from_dict(outcome['job'])
        ordinal = job.model_ordinal
        binding.require(ordinal in MODEL_PINS and ordinal not in seen and ordinal not in candidate_seen and
                        job.block_id == expected[ordinal] and job.model_sha256 == MODEL_PINS[ordinal],
                        'foreign, duplicate, or changed continuation candidate')
        suffix_census.same(job.source_context, source_context, 'foreign continuation source context')
        suffix_census.same(outcome['response_identity'], job.header(outcome['generation']), 'continuation response identity changed')
        descriptor = certifier.descriptor(ordinal)
        record = dict(model=job.model, stages=outcome['stages'], result=outcome['result'])
        verified = None
        failure = outcome.get('reason')
        started, cpu = time.monotonic(), time.process_time()
        if outcome['status'] == 'complete':
            try:
                with verification_deadline(float(min(deadline-10, time.monotonic()+30))):
                    verified = certifier.check(ordinal, record)
            except (ValueError, TimeoutError, MemoryError) as error:
                if verified is not None:
                    raise  # The checker published; its late exit did not authorize a receipt.
                failure = type(error).__name__ + ': ' + str(error)[:2048]
        else:
            binding.require(outcome['status'] == 'unresolved', 'unknown continuation candidate status')
        timings = dict(exact_check_wall_seconds=time.monotonic()-started,
                       exact_check_cpu_seconds=time.process_time()-cpu)
        candidate_seen.add(ordinal)
        seen.add(ordinal)
        if verified is None:
            certifier.unresolved(ordinal, failure or 'uncertified continuation candidate')
            yield dict(kind='unresolved_model', descriptor=descriptor, candidate=outcome, timings=timings)
        else:
            fresh += 1
            yield dict(kind='model_certificate', descriptor=descriptor, record=record, verification=verified,
                       candidate_identity=outcome['response_identity'], candidate_metrics=outcome['metrics'], timings=timings,
                       stdout_sha256=hashlib.sha256(base64.b64decode(outcome['stdout_base64'], validate=True)).hexdigest(),
                       stderr_base64=outcome['stderr_base64'])
    guard()
    pool = outcomes.summary
    clean = transport_complete(pool, len(MODEL_PINS))
    binding.require(not clean or candidate_seen == set(MODEL_PINS), 'gap in completed continuation transport')
    # Missing outputs remain explicit gaps even if the transport itself failed.
    for ordinal in sorted(set(MODEL_PINS) - candidate_seen):
        guard()
        yield dict(kind='unsubmitted_model', descriptor=certifier.descriptor(ordinal),
                   reason='continuation transport provided no candidate disposition')
    reports = []
    for block in blocks:
        guard()
        number = block['range']['block_id']
        report, witness = certifier.summary(number), None
        if clean and report['complete_certificates']:
            winner = certifier.winner(number)
            if winner is None:
                report['physical_witness_not_required'] = True
            else:
                try:
                    with verification_deadline(float(min(deadline-10, time.monotonic()+30))):
                        witness = verify_model(ctx, dict(block_id=number, model_ordinal=winner['model_ordinal'],
                            model_sha256=binding.digest(winner['record']['model']),
                            logical_identity=winner['descriptor']['logical_identity']), winner['record'])
                    report['physical_witness_verified'] = True
                except (ValueError, TimeoutError, MemoryError) as error:
                    witness = None
                    report['witness_failure'] = type(error).__name__ + ': ' + str(error)[:2048]
        report['complete'] = clean and report['complete_certificates'] and (
            report['physical_witness_verified'] or report.get('physical_witness_not_required') is True)
        yield dict(kind='block_report', report=report, winner_witness=witness)
        reports.append(report)
    guard()
    complete = clean and retained+fresh == len(expected) and all(r['complete'] for r in reports)
    yield dict(kind='footer', schema='hiroute-suffix-block-resume-footer-v1', complete=complete,
               proof_complete=complete, verified_models=retained+fresh, expected_models=len(expected),
               retained_verified_models=retained, new_verified_models=fresh, transport=pool, blocks=reports,
               historical_attempt_status='failed', historical_runtime_revalidated=False, **FALSE_AUTHORITY)


def publish_proofs(ctx, selection, source_context, receipt, writer, outcomes, *, deadline, before=lambda: None):
    encoding, footer = ArchiveEncoding(), {}
    def rows():
        for row in continued_records(ctx, selection['blocks'], source_context, receipt, outcomes,
                                     deadline=deadline, before=before):
            before()
            if row['kind'] == 'footer':
                footer.update(row)
            yield row
    pin = writer.write('continued-model-proofs.jsonl.gz', encoding.chunks(rows()))
    binding.require(encoding.complete and footer.get('kind') == 'footer', 'incomplete continuation proof archive')
    return dict(archive=pin, encoding=encoding.summary(), footer=footer)


def worker(args):
    raw_writer = writer = pool = None
    stage = 'binding'
    def before():
        binding.require(math.isfinite(args.deadline) and time.monotonic() < args.deadline,
                        'block continuation absolute deadline')
    try:
        binding.require(os.environ.get('HIROUTE_PROFILE') == BATCH_REPLAY.name and
                        os.environ.get('HIROUTE_EVIDENCE_CAP_BYTES') == str(BATCH_REPLAY.worker_evidence_bytes),
                        'wrong continuation group guard')
        binding.require(len(args.worker_cpus) == 5 and len(set(args.worker_cpus)) == 5 and
                        os.sched_getaffinity(0) == set(args.worker_cpus), 'five inherited CPUs required')
        binding.require(not any(n == 'validation' or n.startswith(('validation.', 'timecut5')) or
                        n.split('.')[0] in ('numpy', 'scipy', 'sympy') for n in sys.modules),
                        'mathematics imported before continuation fence')
        sys.meta_path.insert(0, suffix_census.NoOptimization())
        sources = suffix_census.check_sources(binding.ROOT, args.source_commit, args.source_sha)
        before()
        index, trusted, checked, anchors = suffix_census.completed_inputs(binding.ROOT, args, args.deadline, before)
        original = read_pinned(args.historical_plan, args.historical_plan_sha, 4*1024**2)
        binding.require(original['state_id'] == 'C01' and original['H_ref'] == 4 and original['sites'] == 8 and
                        original['regions'] == 2047 and original['dominance'] is True and
                        original['external_incumbent'] is None, 'fixed C01 physical population required')
        raw_writer = BoundedEvidenceWriter(os.environ['HIROUTE_EVIDENCE_ROOT'], BATCH_REPLAY.worker_evidence_bytes,
                                           profile_name=BATCH_REPLAY.name)
        writer = QuotaWriter(raw_writer, before)
        resources = resource_plan(args.worker_cpus)
        writer.write('run-binding.json', domain.chunks(dict(schema='hiroute-suffix-block-resume-binding-v1',
            source_commit=args.source_commit, source_sha256=args.source_sha, completed_replay=anchors,
            logical_report_sha256=args.logical_report_sha, resource_plan=resources,
            historical_archive=archive_pin(), historical_summary_sha256=OLD_SUMMARY_SHA,
            historical_selection_sha256=OLD_SELECTION_SHA, historical_attempt_status='failed')))
        stage = 'fresh-family'
        payload = read_pinned(args.capture, index['capture_sha256'], 1024**3)
        binding.require(payload['schema'] == 'hiroute-recorded-real-capture-v1' and
                        payload['source_plan_sha256'] == args.historical_plan_sha, 'capture identity changed')
        for key in ('source_sha256', 'input_sha256', 'query_sha256', 'query'):
            suffix_census.same(payload[key], original[key], 'capture ' + key + ' changed')
        suffix_census.same(payload['variant'], domain.variant(original), 'capture variant changed')
        bundle = payload['bundle']
        del payload
        before()
        from validation.real5_v2.batch_jobs import BatchExecutor, WORKER_AS
        from .family_gate import verify_families
        from validation.family5.checker import _plain
        binding.require(WORKER_AS == 1024**3, 'scalar child cap changed')
        started = time.monotonic()
        with BatchExecutor(tuple(args.worker_cpus[1:]), float(args.deadline-10),
                           index['capture_sha256'], kernel='interval-join-v1') as pool:
            binding.require(len(pool.slots) == 4 and all(s.process.poll() is None for s in pool.slots),
                            'four family workers required')
            os.sched_setaffinity(0, {args.worker_cpus[0]})
            ctx, ledger = verify_families(bundle, trusted, pool)
        del bundle
        binding.require(all(s.process.poll() is not None for s in pool.slots), 'family workers not reaped')
        writer.write('batch-ledger.json', domain.chunks(ledger))
        writer.write('family-summary.json', domain.chunks(dict(checked=_plain(ctx.summary), wall_seconds=time.monotonic()-started)))
        stage = 'cold-population-and-selection'
        from .indexed_population import admit_population
        admitted = admit_population(binding.ROOT, args, ctx, args.deadline, before)
        selection = pilot.freeze_selection(admitted)
        writer.write('block-plan.json', domain.chunks(admitted.population.plan()))
        selection_pin = writer.write('pilot-selection.json', domain.chunks(selection))
        binding.require(selection_pin['sha256'] == OLD_SELECTION_SHA, 'continued original selection bytes changed')
        stage = 'cold-archive-replay'
        started = time.monotonic()
        receipt = replay_history(args, ctx, selection, index, deadline=args.deadline, before=before)
        cold_seconds = time.monotonic()-started
        cold_pin = writer.write('cold-replay.json', domain.chunks(receipt.summary()))
        source_context = dict(schema='hiroute-suffix-block-resume-context-v1', source_sha256=args.source_sha,
            source_bundle_sha256=ctx.summary['bundle_sha256'], capture_sha256=index['capture_sha256'],
            block_plan_sha256=admitted.population.plan_sha256, selection_sha256=selection_pin['sha256'],
            original_query_freeze_sha256=index['query_freeze_sha256'], resource_plan_sha256=binding.digest(resources),
            previous_source_context=receipt.summary()['source_context'], previous_archive=archive_pin(),
            previous_summary_sha256=OLD_SUMMARY_SHA, cold_replay_sha256=cold_pin['sha256'])
        from .lp_stream_jobs import stream_results
        os.sched_setaffinity(0, set(args.worker_cpus))
        stage = 'two-candidates-and-exact-join'
        started = time.monotonic()
        with stream_results(candidate_jobs(ctx, selection, source_context, before), cpus=tuple(args.worker_cpus[1:]),
                            coordinator_cpu=args.worker_cpus[0], deadline_monotonic=float(args.deadline-10),
                            max_jobs=2, max_input_bytes=pilot.MAX_INPUT_BYTES) as outcomes:
            proof = publish_proofs(ctx, selection, source_context, receipt, writer, outcomes,
                                   deadline=args.deadline, before=before)
        numerical_seconds = time.monotonic()-started
        stage = 'final-binding'
        verify_loaded({'source_files': sources})
        suffix_census.check_sources(binding.ROOT, args.source_commit, args.source_sha)
        before()
        final = admit_population(binding.ROOT, args, ctx, args.deadline, before)
        suffix_census.same(final.commitment(), admitted.commitment(), 'original query population changed during continuation')
        for path, sha in ((args.capture, index['capture_sha256']), (args.old_archive, OLD_ARCHIVE_SHA),
                          (args.old_summary, OLD_SUMMARY_SHA), (args.old_selection, OLD_SELECTION_SHA)):
            binding.require(binding.pin(path)['sha256'] == sha, 'consumed source changed during continuation')
            before()
        footer = proof['footer']
        summary = dict(schema='hiroute-four-block-resume-summary-v1', source_context=source_context,
            resource_plan=resources, population=admitted.commitment(), selection=selection_pin,
            cold_replay=cold_pin, proof_archive=proof['archive'], encoding=proof['encoding'],
            complete=footer['complete'], proof_complete=footer['proof_complete'], verified_models=footer['verified_models'],
            retained_verified_models=footer['retained_verified_models'], new_verified_models=footer['new_verified_models'],
            blocks=footer['blocks'], transport=footer['transport'], cold_replay_wall_seconds=cold_seconds,
            numerical_wall_seconds=numerical_seconds, historical_attempt_status='failed',
            historical_runtime_revalidated=False, **FALSE_AUTHORITY)
        writer.write('block-resume-summary.json', domain.chunks(summary))
        before()
        binding.require({r['path'] for r in writer.files} == {'run-binding.json', 'batch-ledger.json', 'family-summary.json',
            'block-plan.json', 'pilot-selection.json', 'cold-replay.json', 'continued-model-proofs.jsonl.gz',
            'block-resume-summary.json'}, 'continuation output coverage changed')
        raw_writer.finalize()
        before()
        return 0 if summary['complete'] else 1
    except BaseException as error:
        if writer is not None and pool is not None and not any(r['path'] == 'batch-ledger.json' for r in writer.files):
            try:
                writer.write('partial-batch-ledger.json', domain.chunks(pool.snapshot()))
            except BaseException:
                pass
        worker_failure(type(error).__name__, str(error)[:4096], stage)
        return 1
    finally:
        if raw_writer is not None:
            raw_writer.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--worker', action='store_true')
    p.add_argument('--deadline', type=float)
    for name in ('historical-plan', 'replay-plan', 'replay-attempt', 'replay-return', 'logical-attempt',
                 'logical-return', 'capture', 'old-archive', 'old-summary', 'old-selection'):
        p.add_argument('--'+name, type=Path, required=True)
    for name in ('historical-plan-sha', 'replay-plan-sha', 'replay-return-sha', 'replay-manifest-sha',
                 'replay-result-sha', 'replay-decision-sha', 'query-index-sha', 'source-commit', 'source-sha',
                 'logical-return-sha', 'logical-report-sha', 'logical-source-sha'):
        p.add_argument('--'+name, required=True)
    p.add_argument('--worker-cpus', type=int, nargs=5, required=True)
    p.add_argument('--cpu', type=int)
    p.add_argument('--attempt-dir', type=Path)
    args = p.parse_args()
    if args.worker:
        return worker(args)
    binding.require(args.cpu is not None and args.attempt_dir is not None, 'supervisor CPU and fresh continuation attempt required')
    deadline = float(ENTRY+SECONDS)
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    binding.require(hard == resource.RLIM_INFINITY or hard >= BATCH_REPLAY.child_as_bytes, 'inherited AS ceiling too small')
    resource.setrlimit(resource.RLIMIT_AS, (min(512*1024**2, soft) if soft != resource.RLIM_INFINITY else 512*1024**2, hard))
    suffix_census.check_sources(binding.ROOT, args.source_commit, args.source_sha)
    argv = [sys.executable, '-B', '-m', 'experiments.time_cut_v2.recorded_real.block_resume', '--worker',
            '--deadline', repr(deadline), '--worker-cpus', *map(str, args.worker_cpus)]
    for key, value in vars(args).items():
        if key not in ('worker', 'deadline', 'worker_cpus', 'cpu', 'attempt_dir'):
            argv += ['--'+key.replace('_', '-'), str(value)]
    context = binding.digest({k: str(v) for k, v in vars(args).items()
                              if k not in ('worker', 'deadline', 'cpu', 'attempt_dir')})
    result = run_phase(argv, attempt_dir=args.attempt_dir, profile=BATCH_REPLAY, cpu=args.cpu,
                       worker_cpus=tuple(args.worker_cpus), context=PlanContext(args.replay_plan_sha,
                       args.source_sha, context, BATCH_REPLAY.name), entry_monotonic=float(ENTRY), deadline_monotonic=deadline)
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] == 'completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
