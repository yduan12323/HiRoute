"""Source-bound admission of successful generic recovery executions.

A failed predecessor never becomes a completed phase. Its immutable bytes are
linked through the independently admitted recovery plan and freshly checked by
the reviewed current worker. This reader authenticates that execution and every
retained leaf; it is not a numerical checker or cryptographic code attestation.
"""
from dataclasses import asdict
import hashlib
import os
from pathlib import Path
import sys

from . import plan as binding, suffix_census, window_receipts as wr
from .archive_reader import ArchiveReader
from .runtime import BATCH_REPLAY, read_phase_result

MODULE = 'suffix_window_recovery'
PREFIX = 'hiroute-suffix-window-recovery'
ARCHIVE_SCHEMA = PREFIX + '-archive-v1'
FOOTER_SCHEMA = PREFIX + '-footer-v1'
HISTORY_BYTES = 512 * 1024**2
INPUT_BYTES = 128 * 1024**2
EVIDENCE_FILES = frozenset(('run-binding.json', 'batch-ledger.json', 'family-summary.json',
    'block-plan.json', 'base-registry.json', 'window-selection.json', 'recovery-plan.json',
    'cold-replay.json', 'recovery-model-proofs.jsonl.gz', 'recovery-summary.json'))
CERTIFICATE_FIELDS = frozenset(('kind', 'descriptor', 'record', 'verification', 'candidate_identity',
    'candidate_metrics', 'timings', 'stdout_sha256', 'stderr_base64'))


def _same(actual, expected, message):
    suffix_census.same(actual, expected, message)


def _pin(row):
    return {key: row[key] for key in ('sha256', 'size_bytes')}


def _core_report(block, checked, unresolved):
    """Fold byte-authenticated results; never turn a missing row into exclusion."""
    from validation.suffix5.aggregate_stream import StreamAggregator
    span = block['range']
    ordinals = range(span['start'], span['end'])
    missing = [ordinal for ordinal in ordinals if ordinal not in checked and ordinal not in unresolved]
    failed = [ordinal for ordinal in ordinals if ordinal in unresolved]
    aggregate, segments = None, []
    if not missing and not failed:
        folded, current, part = StreamAggregator(start=span['start']), None, None
        for descriptor in block['descriptors']:
            ordinal = descriptor['ordinal']
            result = checked[ordinal]['verification']['result']
            folded.add(ordinal, result)
            if current != descriptor['segment_id']:
                if part is not None:
                    segments.append(dict(segment_id=current, aggregate=part.summary()))
                current, part = descriptor['segment_id'], StreamAggregator(start=ordinal)
            part.add(ordinal, result)
        segments.append(dict(segment_id=current, aggregate=part.summary()))
        aggregate = folded.summary()
    return dict(schema='suffix5-checked-block-certificates-v1', range=span,
        complete_certificates=not missing and not failed,
        verified_models=span['model_count']-len(missing)-len(failed), unresolved_ordinals=failed,
        unsubmitted_ordinals=missing, aggregate=aggregate, segment_summaries=segments,
        physical_witness_verified=False, query_optimum_certified=False, literal_G8_closed=False)


def _witness(block, checked, report, witness):
    """Bind a current physical check to the deterministic winning full record."""
    binding.require((witness is not None) == report['physical_witness_verified'],
                    'recovery physical witness presence changed')
    if witness is None:
        return
    binding.require(report['complete_certificates'] and type(witness) is dict and
        witness.get('schema') == 'family5-calibrated-model-check-v1' and
        witness.get('exact_certificate_verified') is True and witness.get('physical_witness_verified') is True,
        'recovery physical winner lacks a checked receipt')
    result = report['aggregate']['result']
    binding.require(result['status'] != 'empty_restricted_family', 'physical winner for empty recovery block')
    winners = [checked[row['ordinal']] for row in block['descriptors']
               if checked[row['ordinal']]['verification']['result'] == result]
    binding.require(bool(winners), 'recovery physical winner lacks full proof bytes')
    full = min(winners, key=lambda row: row['descriptor']['ordinal'])
    _same(witness['binding'], dict(block_id=block['range']['block_id'],
        model_ordinal=full['descriptor']['ordinal'], model_sha256=full['verification']['model_sha256'],
        logical_identity=full['descriptor']['logical_identity']), 'recovery physical winner identity changed')
    _same(witness['result'], result, 'recovery physical winner result changed')
    binding.require(type(witness['checked_stage_count']) is int and
        witness['checked_stage_count'] == full['verification']['checked_stage_count'] and
        all(witness.get(key) is False for key in wr.FALSE_AUTHORITY) and
        all(witness.get(key) is not None for key in ('evidence', 'contract', 'physical_audit')),
        'recovery physical witness data or authority changed')


def _report(block, checked, unresolved, row, *, root):
    binding.require(type(row) is dict and set(row) == {'kind', 'report', 'winner_witness'},
                    'recovery block report fields changed')
    supplied = row['report']
    core = _core_report(block, checked, unresolved)
    extras = {'complete', 'physical_witness_not_required'} | ({'witness_failure'} if root else set())
    binding.require(type(supplied) is dict and set(core) | {'complete'} <= set(supplied) and
        set(supplied) <= set(core) | extras and type(supplied['complete']) is bool and
        type(supplied['physical_witness_verified']) is bool, 'recovery block report contract changed')
    for key, value in core.items():
        if key != 'physical_witness_verified':
            _same(supplied[key], value, 'recovery block exact coverage changed: '+key)
    if 'physical_witness_not_required' in supplied:
        binding.require(supplied['physical_witness_not_required'] is True and core['complete_certificates'] and
            core['aggregate']['result']['status'] == 'empty_restricted_family' and row['winner_witness'] is None,
            'recovery physical witness exemption changed')
    _witness(block, checked, supplied, row['winner_witness'])
    binding.require(not supplied['complete'] or (supplied['complete_certificates'] and
        (supplied['physical_witness_verified'] or supplied.get('physical_witness_not_required') is True)),
        'false recovery block completion')
    return supplied


def _header(blocks, context, history, leaves):
    expected = {row['ordinal'] for block in blocks for row in block['descriptors']}
    candidates = sorted(expected-set(leaves))
    return dict(kind='header', schema=ARCHIVE_SCHEMA, source_context=context,
        population_sha256=binding.digest(blocks), expected_models=len(expected),
        blocks=[block['range'] for block in blocks], retained_models=len(leaves),
        candidate_models=len(candidates), candidate_ordinals=candidates, history=history,
        previous_archive=history[-1]['archive'], recovery_mode='candidates' if candidates else 'exact-only',
        historical_runtime_revalidated=False, **wr.FALSE_AUTHORITY)


def _leaf(row, archive, context, index):
    # The consumed archive remains the complete proof dependency. Keep only
    # small bindings here, not every decoded model/stage graph in controller RAM.
    compact = {key: row[key] for key in ('descriptor', 'verification')}
    return dict(row=compact, provenance=dict(archive=archive, source_context=context, archive_row_index=index,
        archive_row_sha256=hashlib.sha256(binding.canonical(row)+b'\n').hexdigest()))


def _reference(leaf):
    return dict(kind='retained_certificate_reference', descriptor=leaf['row']['descriptor'],
        verification=leaf['row']['verification'], provenance=leaf['provenance'])


def _consume(path, pin, blocks, context, history, leaves, before, *, root=False, incomplete=False, raw_limit=None):
    """Authenticate a whole chronological archive and resolve every backward leaf."""
    from .block_replay import transport_complete
    from .lp_stream_jobs import LPStreamJob
    reader = ArchiveReader(path, compressed_sha256=pin['sha256'], compressed_bytes=pin['size_bytes'],
                           allow_incomplete=incomplete, before=before)
    if raw_limit is not None:
        reader.limit_raw_bytes(raw_limit)
    expected = {row['ordinal']: (block['range']['block_id'], row)
                for block in blocks for row in block['descriptors']}
    by_id = {block['range']['block_id']: block for block in blocks}
    candidates = set(expected)-set(leaves)
    checked, added, unresolved, seen, missing = {}, {}, set(), set(), set()
    retained_seen, reports = set(), []
    header = footer = pending = None
    phase, input_bytes = 'retained', 0
    for index, row in enumerate(reader):
        before()
        binding.require(type(row) is dict and type(row.get('kind')) is str, 'typed recovery proof row required')
        kind = row['kind']
        if index == 0:
            header = dict(kind='header', schema='hiroute-suffix-block-proof-archive-v1', source_context=context,
                expected_models=len(expected), blocks=[b['range'] for b in blocks], certificate_reuse_enabled=False) if root else _header(blocks, context, history, leaves)
            _same(row, header, 'recovery archive header lineage or source changed')
            continue
        binding.require(footer is None, 'recovery proof row after footer')
        if pending is not None:
            binding.require(kind == 'block_certificate_checkpoint', 'missing immediate recovery checkpoint')
        if kind == 'retained_certificate_reference':
            binding.require(not root and phase == 'retained' and set(row) ==
                {'kind', 'descriptor', 'verification', 'provenance'}, 'unexpected recovery reference fields or phase')
            ordinal = row['descriptor']['ordinal']
            binding.require(type(ordinal) is int and ordinal in leaves and ordinal not in retained_seen,
                            'foreign or duplicate retained recovery proof')
            _same(row, _reference(leaves[ordinal]), 'recovery reference differs from full ancestor leaf')
            retained_seen.add(ordinal)
            checked[ordinal] = leaves[ordinal]['row']
        elif kind in ('model_certificate', 'unresolved_model'):
            binding.require(phase in ('retained', 'candidate') and (root or retained_seen == set(leaves)),
                            'candidate before full retained coverage or after reporting')
            phase = 'candidate'
            descriptor = row['descriptor']; ordinal = descriptor['ordinal']
            binding.require(type(ordinal) is int and ordinal in candidates and ordinal not in seen,
                            'foreign or duplicate recovery candidate')
            block_id, original = expected[ordinal]
            _same(descriptor, original, 'recovery original candidate descriptor changed')
            if kind == 'model_certificate':
                binding.require(set(row) == CERTIFICATE_FIELDS, 'full recovery certificate fields changed')
                _, size = wr._check_record(row, original, block_id, context)
                added[ordinal] = _leaf(row, _pin(pin), context, index)
                checked[ordinal] = added[ordinal]['row']
            else:
                binding.require(set(row) == {'kind', 'descriptor', 'candidate', 'timings'},
                                'unresolved recovery row fields changed')
                outcome = row['candidate']; job = LPStreamJob.from_dict(outcome['job'])
                binding.require(job.model_ordinal == ordinal and job.block_id == block_id and
                                (root or outcome['status'] == 'unresolved'), 'unresolved recovery job changed')
                _same(job.source_context, context, 'unresolved recovery source changed')
                _same(outcome['response_identity'], job.header(outcome['generation']), 'unresolved recovery response changed')
                identity = dict(source_bundle_sha256=job.model['family_bundle_sha256'],
                    **{key: job.model[key] for key in ('family_id', 'word', 'arrival_bands')})
                _same(identity, descriptor['logical_identity'], 'unresolved recovery logical model changed')
                size = len(job.input_bytes)
                unresolved.add(ordinal)
            input_bytes += size
            binding.require(input_bytes <= INPUT_BYTES, 'recovery consumed candidate input byte cap')
            seen.add(ordinal)
        elif kind == 'block_certificate_checkpoint':
            binding.require(pending is not None, 'unexpected recovery checkpoint')
            _same(row, dict(kind='block_certificate_checkpoint', report=_core_report(by_id[pending], checked, unresolved),
                transport_finalized=False, acceptance=False, cold_certificate_replay_required=True),
                'recovery checkpoint differs from full certificate bytes')
            pending = None
        elif kind == 'unsubmitted_model':
            binding.require(not root and phase in ('retained', 'candidate', 'missing') and
                retained_seen == set(leaves) and set(row) == {'kind', 'descriptor', 'reason'} and
                row['reason'] == 'recovery transport provided no candidate disposition',
                'unexpected recovery unsubmitted disposition')
            phase = 'missing'; ordinal = row['descriptor']['ordinal']
            binding.require(type(ordinal) is int and ordinal in candidates and ordinal not in seen | missing,
                            'foreign or duplicate missing recovery model')
            _same(row['descriptor'], expected[ordinal][1], 'missing recovery descriptor changed')
            missing.add(ordinal)
        elif kind == 'block_report':
            binding.require(len(reports) < len(blocks) and (root or
                (retained_seen == set(leaves) and seen | missing == candidates)), 'premature recovery block report')
            phase = 'reports'
            reports.append(_report(blocks[len(reports)], checked, unresolved, row, root=root))
        elif kind == 'footer':
            binding.require(phase == 'reports' and len(reports) == len(blocks), 'recovery footer lacks block reports')
            pool = row.get('transport')
            if not root and not candidates:
                binding.require(pool is None and input_bytes == 0, 'exact-only recovery cannot fabricate transport')
                clean = True
            else:
                clean = transport_complete(pool, len(candidates))
                binding.require(type(pool.get('input_bytes')) is int and input_bytes <= pool['input_bytes'] <= INPUT_BYTES and
                    (pool.get('all_submitted_accounted') is not True or pool['input_bytes'] == input_bytes),
                    'recovery transport input bytes differ from consumed models')
            binding.require(not clean or seen == candidates, 'recovery complete transport coverage changed')
            binding.require(all(report['complete'] == (clean and report['complete_certificates'] and
                (report['physical_witness_verified'] or report.get('physical_witness_not_required') is True))
                for report in reports), 'recovery report completion disagrees with transport')
            complete = clean and len(checked) == len(expected) and all(report['complete'] for report in reports)
            if root:
                expected_footer = dict(kind='footer', schema='hiroute-suffix-block-proof-footer-v1', complete=complete,
                    verified_models=len(checked), expected_models=len(expected), transport=pool, blocks=reports,
                    **wr.FALSE_AUTHORITY)
            else:
                expected_footer = dict(kind='footer', schema=FOOTER_SCHEMA, complete=complete, proof_complete=complete,
                    verified_models=len(checked), expected_models=len(expected), retained_verified_models=len(leaves),
                    new_verified_models=len(added), candidate_models=len(candidates), transport=pool, blocks=reports,
                    recovery_mode='candidates' if candidates else 'exact-only', historical_runtime_revalidated=False,
                    **wr.FALSE_AUTHORITY)
            _same(row, expected_footer, 'recovery footer coverage or authority changed')
            footer = row
        else:
            raise ValueError('unknown recovery proof record kind')
        if kind in ('model_certificate', 'retained_certificate_reference', 'unresolved_model'):
            block_id = expected[ordinal][0]
            if _core_report(by_id[block_id], checked, unresolved)['complete_certificates']:
                pending = block_id
    before()
    encoding = reader.summary
    binding.require(header is not None and type(encoding) is dict and
        (not encoding['gzip_eof'] or (footer is not None and pending is None)) and
        (footer is None or encoding['trailing_partial_row_bytes'] == 0),
        'recovery archive incomplete grammar or trailing partial row')
    return added, encoding, footer, reports


def _cold_summary(blocks, history, leaves):
    expected = {row['ordinal'] for block in blocks for row in block['descriptors']}
    candidates = sorted(expected-set(leaves))
    return dict(schema='hiroute-cold-window-recovery-v1', population_sha256=binding.digest(blocks),
        expected_models=len(expected), retained_verified_models=len(leaves), candidate_models=len(candidates),
        candidate_ordinals=candidates, certified_ordinals=sorted(leaves), history=history,
        previous_archive=history[-1]['archive'], certificate_refs=[leaves[i]['provenance'] for i in sorted(leaves)],
        coverage=[dict(range=block['range'], verified_models=sum(row['ordinal'] in leaves for row in block['descriptors']),
            candidate_ordinals=[row['ordinal'] for row in block['descriptors'] if row['ordinal'] not in leaves])
            for block in blocks], historical_runtime_revalidated=False, **wr.FALSE_AUTHORITY)


def _history(admission, cold, blocks, cache, before):
    history, leaves, compressed, raw = [], {}, 0, 0
    for number, ancestor in enumerate(admission.document()['predecessors']):
        before()
        pins = ancestor['artifacts']; archive = pins['archive']
        binding.require(compressed+archive['size_bytes'] <= HISTORY_BYTES,
                        'cumulative compressed recovery archive history byte cap')
        binding.require(all(entry['archive'] != _pin(archive) for entry in history),
                        'duplicate or cyclic recovery ancestry')
        if number:
            prior_cold = cache.read(pins['cold_replay']['path'], pins['cold_replay']['sha256'], wr.SUMMARY_LIMIT,
                                   size=pins['cold_replay']['size_bytes'])
            _same(prior_cold, _cold_summary(blocks, history, leaves), 'ancestor cold receipt differs from full proof closure')
        added, encoding, footer, reports = _consume(archive['path'], archive, blocks,
            ancestor['source_context'], history, leaves, before, root=number == 0,
            incomplete=ancestor['archive_mode'] == 'interrupted-prefix', raw_limit=HISTORY_BYTES-raw)
        compressed += encoding['compressed_bytes']; raw += encoding['uncompressed_bytes']
        binding.require(max(compressed, raw) <= HISTORY_BYTES, 'cumulative recovery archive history byte cap')
        if pins['summary'] is not None:
            summary = cache.read(pins['summary']['path'], pins['summary']['sha256'], wr.SUMMARY_LIMIT,
                                 size=pins['summary']['size_bytes'])
            _same(summary['encoding'], dict(complete=True, **{key: encoding[key] for key in
                ('uncompressed_bytes', 'uncompressed_sha256', 'rows', 'encoding')}),
                'historical recovery encoding differs from consumed bytes')
            binding.require(footer is not None, 'historical summary lacks finalized archive footer')
            for key in ('complete', 'verified_models', 'transport', 'blocks'):
                _same(summary[key], footer[key], 'historical recovery summary differs from full archive: '+key)
            binding.require(all(summary.get(key) is False for key in wr.FALSE_AUTHORITY),
                            'historical recovery summary claims unsupported authority')
        leaves.update(added)
        history.append(dict(archive=_pin(archive), source_context=ancestor['source_context'],
            gzip_eof=encoding['gzip_eof'], trailing_partial_row_bytes=encoding['trailing_partial_row_bytes']))
        cache.decoded.clear()
    _same(cold, _cold_summary(blocks, history, leaves), 'current cold recovery receipt differs from full proof closure')
    return history, leaves


def _origin(origin, request):
    root = binding.ROOT.resolve()
    expected = dict(schema='hiroute-reviewed-controller-origin-v1', checkout_root=str(root),
        controller_module=wr.MODULE_PREFIX+MODULE,
        controller_path=str(root/'experiments/time_cut_v2/recorded_real/suffix_window_recovery.py'),
        python_executable=sys.executable, executable_realpath=str(Path(sys.executable).resolve()), cwd=str(root))
    _same(origin, expected, 'trusted reviewed recovery controller origin required')
    binding.require(request['command'][0] == sys.executable, 'recovery controller executable changed')


def _admit_recovery(spec, admitted, selection, reviewed_sources, deadline, before, cache):
    from . import recovery_plan, suffix_window, suffix_window_recovery
    from types import SimpleNamespace
    before(); cache.used = set()
    catalogue, commitment = wr._population(admitted)
    cache_key = binding.digest(dict(spec=spec, population=commitment))
    if cache_key in cache.admitted:
        binding.require(selection is None, 'cached recovery cannot replace externally supplied selection')
        receipt = cache.admitted[cache_key]
        cache.used = {(row['path'], row['sha256']) for row in receipt.metadata()['dependencies']}
        return receipt
    binding.require(spec['module'] == MODULE, 'reviewed recovery receipt contract required')
    attempt = Path(spec['attempt']); evidence = attempt/'evidence'
    successful = cache.read(spec['successful_return'], spec['successful_return_sha256'], 65536)
    binding.require(successful.get('status') == 'completed' and 'acceptance_receipt' in successful,
                    'independently retained actual successful recovery runtime return required')
    for filename, field in (('result.json', 'result_sha256'), ('decision.json', 'decision_sha256')):
        _same(spec[field], successful['acceptance_receipt'][field], 'external recovery result/decision pins disagree')
        cache.read(attempt/filename, spec[field], 65536)
    decision = cache.read(attempt/'decision.json', spec['decision_sha256'], 65536)
    cache.read(attempt/'supervisor-decision.json', decision['supervisor_decision_sha256'], 65536)
    result = read_phase_result(attempt, successful_return=successful, deadline_monotonic=deadline, resource_check=before)
    binding.require(result.get('status') == 'completed' and result['descendants_reaped'] is True,
                    'recovery runtime did not return successful checked evidence')
    _same(result['profile'], asdict(BATCH_REPLAY), 'exact recovery BATCH_REPLAY profile required')
    _same(result['verified_manifest_sha256'], spec['manifest_sha256'], 'pinned recovery manifest changed')
    request = cache.read(attempt/'request.json', result['request_sha256'], 1024**2)
    values = recovery_plan.command(request)
    wr._source(values['source_commit'], values['source_sha'], MODULE, reviewed_sources)
    binding.require(0 < request['deadline_monotonic']-request['entry_monotonic'] <= 900,
                    'recovery exceeds reviewed 900-second budget')
    manifest = cache.read(evidence/'__manifest.json', spec['manifest_sha256'], 1024**2)
    binding.require(type(manifest['charged_bytes']) is int and 0 <= manifest['charged_bytes'] <= HISTORY_BYTES,
                    'recovery exceeds reviewed 512 MiB evidence charge')
    files = {row['path']: row for row in manifest['files']}
    binding.require(len(files) == len(manifest['files']) and set(files) == EVIDENCE_FILES,
                    'reviewed recovery evidence file coverage changed')
    def read(name, limit=wr.SUMMARY_LIMIT):
        pin = files[name]
        return cache.read(evidence/name, pin['sha256'], limit, size=pin['size_bytes'])
    run, summary = read('run-binding.json'), read('recovery-summary.json')
    cold, actual_selection = read('cold-replay.json'), read('window-selection.json')
    _same(read('block-plan.json'), catalogue, 'recovery catalogue differs from independent admission')
    actual_selection = wr._selection(admitted, actual_selection, before)
    if selection is not None:
        _same(actual_selection, wr._selection(admitted, selection, before), 'recovery independently selected descriptors changed')
    selection = actual_selection
    binding.require(run['schema'] == PREFIX+'-binding-v1' and summary['schema'] == PREFIX+'-summary-v1',
                    'reviewed recovery receipt schemas changed')
    for key, expected in (('source_commit', values['source_commit']), ('source_sha256', values['source_sha']),
        ('completed_replay', commitment['completed_replay']), ('logical_report_sha256', values['logical_report_sha'])):
        _same(run[key], expected, 'recovery run input binding changed: '+key)
    origin = run['invocation_origin']; _origin(origin, request)
    _same(summary['invocation_origin'], origin, 'recovery invocation origin changed')
    policy = cache.read(values['source_policy'], values['source_policy_sha'], 65536)
    binding.require(type(policy) is dict and set(policy) == {'schema', 'reviewed_sources'} and
        policy['schema'] == 'hiroute-reviewed-window-sources-v1' and type(policy['reviewed_sources']) is dict and
        policy['reviewed_sources'].get(wr.SEED_COMMIT) == wr.SEED_SOURCE and
        policy['reviewed_sources'].get(values['source_commit']) == values['source_sha'] and
        hashlib.sha256(binding.canonical(policy)+b'\n').hexdigest() == values['source_policy_sha'] and
        all(reviewed_sources.get(commit) == inventory for commit, inventory in policy['reviewed_sources'].items()),
        'recovery pinned source policy differs from independently reviewed allowlist')
    args = SimpleNamespace(**values)
    _, base = suffix_window.load_registry(args, reviewed_sources, admitted=admitted, deadline=deadline, before=before)
    _same(read('base-registry.json'), base.metadata(), 'copied recovery base registry changed')
    if values['registry'] is not None:
        binding.require(files['base-registry.json']['sha256'] == values['registry_sha'],
                        'recovery base registry exact bytes changed')
        cache.read(values['registry'], values['registry_sha'], wr.REGISTRY_LIMIT, decode=False)
        cache.read(values['registry_return'], values['registry_return_sha'], 65536, decode=False)
    admission_metadata = suffix_window.registry_admission(args)
    plan_document = recovery_plan.load(values['recovery_plan'], values['recovery_plan_sha'], deadline=deadline, before=before)
    cache.read(values['recovery_plan'], values['recovery_plan_sha'], recovery_plan.PLAN_BYTES)
    _same(read('recovery-plan.json', recovery_plan.PLAN_BYTES), plan_document, 'copied recovery plan changed')
    binding.require(files['recovery-plan.json']['sha256'] == values['recovery_plan_sha'],
                    'recovery plan exact bytes changed')
    admission = recovery_plan.admit(plan_document, admitted, base, reviewed_sources=reviewed_sources,
                                   deadline=deadline, before=before)
    for pin in admission.dependencies():
        key = (pin['path'], pin['sha256'])
        if key in cache.rows:
            _same(cache.rows[key], pin, 'recovery dependency pin changed')
        cache.rows[key] = pin; cache.used.add(key)
    _same(admission.selection(), selection, 'recovery differs from original outstanding selection')
    binding.require(files['window-selection.json']['sha256'] == plan_document['original_selection']['sha256'] and
        files['base-registry.json']['sha256'] == plan_document['base_registry']['sha256'],
        'recovery original selection or base registry byte pins changed')
    window = selection['window_plan']; count = window['expected_model_count']
    for document in (run, summary):
        for key, expected in (('selection', files['window-selection.json']), ('base_registry', files['base-registry.json']),
            ('recovery_plan', files['recovery-plan.json']), ('cold_replay', files['cold-replay.json']),
            ('window_id', window['window_id']), ('registry_admission', admission_metadata)):
            _same(document[key], expected, 'recovery execution evidence linkage changed: '+key)
    _same(summary['population'], commitment, 'recovery population differs from independent admission')
    _same(summary['proof_archive'], files['recovery-model-proofs.jsonl.gz'], 'recovery proof byte pin changed')
    family = read('family-summary.json')['checked']
    binding.require(family['bundle_sha256'] == commitment['source_bundle_sha256'] and
                    family['case_sha256'] == commitment['case_sha256'], 'current checked recovery family changed')
    history, leaves = _history(admission, cold, selection['blocks'], cache, before)
    admission.validate_cold_history(cold)
    _same([{key: row[key] for key in ('archive', 'source_context')} for row in history], admission.history(),
          'recovery history differs from independently admitted source contexts')
    resources = suffix_window_recovery.resource_plan(values['worker_cpus'], count, count-len(leaves))
    _same(run['resource_plan'], resources, 'recovery run resource contract changed')
    _same(summary['resource_plan'], resources, 'recovery summary resource contract changed')
    context = dict(schema=PREFIX+'-context-v1', source_sha256=values['source_sha'],
        source_bundle_sha256=commitment['source_bundle_sha256'], capture_sha256=commitment['completed_replay']['capture_sha256'],
        block_plan_sha256=commitment['block_plan_sha256'], selection_sha256=files['window-selection.json']['sha256'],
        original_query_freeze_sha256=commitment['query_freeze_sha256'], resource_plan_sha256=binding.digest(resources),
        window_id=window['window_id'], base_registry_sha256=files['base-registry.json']['sha256'],
        source_policy_sha256=values['source_policy_sha'], recovery_plan_sha256=files['recovery-plan.json']['sha256'],
        cold_replay_sha256=files['cold-replay.json']['sha256'], history_sha256=binding.digest(history),
        previous_archive=history[-1]['archive'], previous_source_context_sha256=binding.digest(history[-1]['source_context']))
    _same(run['source_context'], context, 'recovery run source context changed')
    _same(summary['source_context'], context, 'recovery summary source context changed')
    wr._inputs(values, commitment, cache, deadline)
    added, encoding, footer, reports = _consume(evidence/'recovery-model-proofs.jsonl.gz',
        files['recovery-model-proofs.jsonl.gz'], selection['blocks'], context, history, leaves, before)
    binding.require(footer is not None and footer['complete'] is True and footer['proof_complete'] is True and
        len(leaves)+len(added) == count and set(leaves).isdisjoint(added), 'recovery lacks complete retained plus new coverage')
    _same(summary['encoding'], dict(complete=True, **{key: encoding[key] for key in
        ('uncompressed_bytes', 'uncompressed_sha256', 'rows', 'encoding')}),
        'recovery encoding differs from consumed bytes')
    for key in ('complete', 'proof_complete', 'verified_models', 'retained_verified_models', 'new_verified_models',
                'candidate_models', 'transport', 'blocks', 'recovery_mode', 'historical_runtime_revalidated', *wr.FALSE_AUTHORITY):
        _same(summary[key], footer[key], 'recovery summary differs from full proof archive: '+key)
    wr._reports(selection['blocks'], {ordinal: row['row']['verification']['result']
        for ordinal, row in leaves.items()} | {ordinal: row['row']['verification']['result']
        for ordinal, row in added.items()}, reports, before)
    proof_pin = files['recovery-model-proofs.jsonl.gz']
    # read_phase_result already authenticated every exact manifest file. Keep
    # that complete inventory, including the unparsed family batch ledger.
    for name, pin in files.items():
        key = (os.path.abspath(evidence/name), pin['sha256'])
        dependency = dict(path=key[0], **_pin(pin))
        if key in cache.rows:
            _same(cache.rows[key], dependency, 'current recovery evidence pin changed')
        cache.rows[key] = dependency; cache.used.add(key)
    entry = dict(spec, source_commit=values['source_commit'], source_sha256=values['source_sha'],
        catalogue=dict(path=str(evidence/'block-plan.json'), **_pin(files['block-plan.json'])),
        summary=dict(path=str(evidence/'recovery-summary.json'), **_pin(files['recovery-summary.json'])),
        proof=dict(path=str(evidence/'recovery-model-proofs.jsonl.gz'), **_pin(proof_pin)),
        selection=dict(path=str(evidence/'window-selection.json'), **_pin(files['window-selection.json'])),
        population_sha256=binding.digest(commitment), source_context_sha256=binding.digest(context),
        dependencies=sorted((cache.rows[key] for key in cache.used), key=lambda row: (row['sha256'], row['path'])),
        invocation_origin=origin)
    entry['entry_id'] = binding.digest(entry)
    entry['blocks'] = [wr._compact_report(report, entry['entry_id']) for report in reports]
    before()
    receipt = wr.CheckedWindowReceipt(entry, reports, _token=wr._ADMISSION)
    cache.admitted[cache_key] = receipt
    cache.decoded.clear()
    return receipt


def admit_completed_recovery(args, admitted, selection=None, *, reviewed_sources, deadline, before=lambda: None):
    """Admit only a current reviewed execution with its actual retained return.

    Independently trusted controller/interpreter invocation remains required.
    After extending/writing the registry, retain its actual registration return
    separately before using the new coverage for ordinary-window scheduling.
    """
    check = wr._guard(deadline, before)
    return wr._admit(wr._spec(args, 'recovery', MODULE), admitted, selection, wr._owned(reviewed_sources),
                     deadline, check, wr._Dependencies(check))
