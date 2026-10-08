"""Source-bound receipts for completed, independently checked suffix windows.

This is cold authentication of a reviewed verifier's successful execution, not
a new numerical replay. Neither this module nor its registry creates a checked
family/trace. The caller must supply independently admitted population inputs,
an independently reviewed source allowlist, and retained actual caller returns.
"""
from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

from . import plan as binding, suffix_census
from .archive_reader import ArchiveReader, _open_regular, _pairs, _nonfinite
from .runtime import BATCH_REPLAY, REPLAY, _directory, read_phase_result

_ADMISSION = object()
REGISTRY_LIMIT = 16 * 1024**2
SUMMARY_LIMIT = 32 * 1024**2
SEED_COMMIT = 'bf61640ceaf6dcafe28f7ab12d95e94c8f19bb93'
SEED_SOURCE = '846ded63e7e3f6a3da5cc81d5f717deea2e4746a75e282d333291dbb05dcb579'
SEED_RETURN = 'fe8898371ee9b5ae2c485b7799aed8cfa1690382b10ce7ab7a4367471541c25b'
SEED_MANIFEST = '07e9ff2ae9c689d185c13afadc81fea12ecc513b1418ee7de12e4704f5fffc3a'
SEED_SUMMARY = '1c2eb936c3102dbe8ba335ef03612e2273cbb13b4fd18c1830c8238e89b8dc44'
SEED_PROOF = '7418fd57074e240bba2d517466c04c1a688a32917f15506e6c8c656fe0e0506f'
SEED_COLD = 'ce91a921780783a41d1cd5a206811fc36b616c74a0153c6bd8a20060017e4524'
SEED_MODELS = 1024
SEED_RETAINED_MODELS = 1022
FALSE_AUTHORITY = dict(query_optimum_certified=False, full_population_complete=False,
                       literal_G8_closed=False)
MODULE_PREFIX = 'experiments.time_cut_v2.recorded_real.'
COMMON_PATHS = ('historical_plan', 'replay_plan', 'replay_attempt', 'replay_return',
                'logical_attempt', 'logical_return', 'capture')
COMMON_PINS = ('historical_plan_sha', 'replay_plan_sha', 'replay_return_sha',
               'replay_manifest_sha', 'replay_result_sha', 'replay_decision_sha',
               'query_index_sha', 'source_commit', 'source_sha', 'logical_return_sha',
               'logical_report_sha', 'logical_source_sha')
WINDOW_OPTIONALS = ('seed_attempt', 'seed_return', 'old_archive', 'old_summary', 'old_selection',
                    'seed_result_sha', 'seed_decision_sha', 'registry', 'registry_sha',
                    'registry_return', 'registry_return_sha')


def _guard(deadline, before):
    binding.require(type(deadline) is float and math.isfinite(deadline) and callable(before),
                    'finite receipt deadline and callback required')
    def check():
        before()
        binding.require(time.monotonic() < deadline, 'receipt admission deadline')
    check()
    return check


def _sha(value):
    binding.require(type(value) is str and len(value) == 64 and
                    all(c in '0123456789abcdef' for c in value), 'exact SHA256 required')
    return value


def _read(path, sha, limit, before, *, size=None, decode=True, with_pin=False):
    """Hash the actual bounded consumed bytes, without links or mutable aliases."""
    _sha(sha)
    before()
    fd = _open_regular(path)
    try:
        initial = os.fstat(fd)
        binding.require(initial.st_size <= limit and (size is None or initial.st_size == size),
                        'receipt file size cap/pin')
        chunks, digest, count = [], hashlib.sha256(), 0
        while True:
            before()
            raw = os.read(fd, 65536)
            if not raw:
                break
            count += len(raw)
            binding.require(count <= limit, 'receipt consumed bytes cap')
            digest.update(raw)
            if decode:
                chunks.append(raw)
        final = os.fstat(fd)
        binding.require((initial.st_dev, initial.st_ino, initial.st_size, initial.st_mtime_ns, initial.st_ctime_ns) ==
                        (final.st_dev, final.st_ino, final.st_size, final.st_mtime_ns, final.st_ctime_ns),
                        'receipt file changed during consumption')
        binding.require(count == initial.st_size and digest.hexdigest() == sha,
                        'consumed receipt bytes differ from independently pinned SHA256')
    finally:
        os.close(fd)
    before()
    pin = dict(path=os.path.abspath(path), sha256=sha, size_bytes=count)
    if decode:
        value = json.loads(b''.join(chunks), object_pairs_hook=_pairs, parse_constant=_nonfinite)
        return (value, pin) if with_pin else value
    return pin


def _owned(value):
    return json.loads(binding.canonical(value))


def _population(admitted):
    from .indexed_population import AdmittedSuffixPopulation
    binding.require(type(admitted) in (AdmittedSuffixPopulation, ReceiptScope),
                    'independently admitted original population required')
    if type(admitted) is ReceiptScope:
        return admitted.plan(), admitted.commitment()
    plan, commitment = admitted.population.plan(), admitted.commitment()
    binding.require(binding.digest(plan) == admitted.population.plan_sha256 == commitment['block_plan_sha256'],
                    'admitted population plan changed')
    return plan, commitment


def _selection(admitted, selection, before):
    plan, commitment = _population(admitted)
    selection = _owned(selection)
    suffix_census.same(selection['population'], commitment, 'selection population differs from admission')
    blocks = selection['blocks']
    binding.require(type(blocks) is list and 0 < len(blocks) <= 32, 'bounded nonempty window required')
    previous, count = -1, 0
    for block in blocks:
        before()
        span = block['range']
        number = span['block_id']
        binding.require(type(number) is int and previous < number < len(plan['blocks']),
                        'foreign, repeated or unordered selected block')
        suffix_census.same(span, plan['blocks'][number], 'selected catalogue span changed')
        if type(admitted) is ReceiptScope:
            rows = block['descriptors']
            binding.require(type(rows) is list and len(rows) == span['model_count'], 'receipt descriptor coverage changed')
            for ordinal, row in zip(range(span['start'], span['end']), rows):
                binding.require(type(row) is dict and set(row) == {'ordinal', 'segment_id', 'prefix_depth',
                    'logical_identity', 'logical_identity_sha256'} and row['ordinal'] == ordinal,
                    'receipt descriptor fields/ordinal changed')
                ident = row['segment_id']
                binding.require(type(ident) is int and 0 <= ident < len(plan['segments']), 'foreign descriptor segment')
                segment, identity = plan['segments'][ident], row['logical_identity']
                binding.require(segment['start'] <= ordinal < segment['end'] and
                    row['prefix_depth'] == segment['prefix_depth'] and type(identity) is dict and
                    set(identity) == {'source_bundle_sha256', 'family_id', 'word', 'arrival_bands'} and
                    identity['source_bundle_sha256'] == commitment['source_bundle_sha256'] and
                    identity['family_id'] == segment['family_id'] and identity['word'] and
                    identity['word'][0] == segment['first_action'] and
                    binding.digest(identity) == row['logical_identity_sha256'],
                    'descriptor differs from source-bound catalogue segment')
        else:
            admitted.population.check_block_descriptors(number, block['descriptors'])
        previous, count = number, count + span['model_count']
    binding.require(count <= 8192, 'window model budget exceeded')
    return selection


def _command(request, module):
    command = request['command']
    binding.require(type(command) is list and len(command) > 5 and
                    type(command[0]) is str and command[0].startswith('/') and
                    command[1:5] == ['-B', '-m', MODULE_PREFIX + module, '--worker'],
                    'reviewed worker module command required')
    values, position = {}, 5
    while position < len(command):
        key = command[position]
        binding.require(type(key) is str and key.startswith('--'), 'worker command option required')
        key = key[2:].replace('-', '_')
        binding.require(key not in values, 'duplicate worker command option')
        width = 5 if key == 'worker_cpus' else 1
        raw = command[position+1:position+1+width]
        binding.require(len(raw) == width and all(type(v) is str for v in raw), 'worker option value missing')
        values[key] = [int(v) for v in raw] if width == 5 else raw[0]
        position += width + 1
    required = set(COMMON_PATHS + COMMON_PINS) | {'deadline', 'worker_cpus'}
    extras = {'old_archive', 'old_summary', 'old_selection'} if module == 'block_resume' else {
        'source_policy', 'source_policy_sha', 'registry_output', 'registration_return_output'}
    if module == 'suffix_window':
        from .population_bootstrap import FIELDS
        bootstrap = set(FIELDS) if any(key in values for key in FIELDS) else set()
        binding.require(set(values) <= required | extras | set(WINDOW_OPTIONALS) | bootstrap | {'maximum_blocks'}, 'unknown window command option')
        for key in WINDOW_OPTIONALS:
            values.setdefault(key, None)
        extras |= set(WINDOW_OPTIONALS) | bootstrap
        if 'maximum_blocks' in values:
            raw_limit = values['maximum_blocks']
            binding.require(raw_limit.isdecimal() and str(int(raw_limit)) == raw_limit and
                            1 <= int(raw_limit) <= 32, 'window block cap')
            values['maximum_blocks'] = int(raw_limit)
            extras.add('maximum_blocks')
    binding.require(set(values) == required | extras, 'reviewed worker command options changed')
    binding.require(float(values['deadline']) == request['deadline_monotonic'] and
                    values['worker_cpus'] == request['worker_cpus'], 'worker deadline/CPU binding changed')
    context = binding.digest({key: (str(value) if module == 'block_resume' else value)
                              for key, value in values.items() if key != 'deadline'})
    suffix_census.same(request['context'], dict(plan_sha256=values['replay_plan_sha'],
        source_sha256=values['source_sha'], input_sha256=context, profile_name=BATCH_REPLAY.name),
        'runtime does not bind reviewed command inputs')
    return values


def _source(commit, source, module, reviewed_sources):
    binding.require(module in ('block_resume', 'suffix_window', 'suffix_window_recovery') and type(commit) is str and
                    len(commit) == 40 and all(c in '0123456789abcdef' for c in commit),
                    'fixed reviewed module and full source commit required')
    if module == 'block_resume':
        binding.require(commit == SEED_COMMIT and source == SEED_SOURCE,
                        'only the independently reviewed accepted seed source is allowed')
    else:
        binding.require(type(reviewed_sources) is dict and commit in reviewed_sources and
                        reviewed_sources[commit] == source, 'window source is outside reviewed allowlist')
    _sha(source)


class CheckedWindowReceipt:
    """Immutable source-bound execution receipt, deliberately not CheckedBundle."""
    __slots__ = ('_metadata', '_reports')

    def __init__(self, metadata, reports, *, _token=None):
        binding.require(_token is _ADMISSION, 'completed window admission required')
        object.__setattr__(self, '_metadata', binding.canonical(metadata))
        object.__setattr__(self, '_reports', binding.canonical(reports))

    def __setattr__(self, *_):
        raise AttributeError('immutable checked window receipt')

    def metadata(self):
        return json.loads(self._metadata)

    def block_reports(self):
        return json.loads(self._reports)


class ReceiptScope:
    """Source-authenticated catalogue context; no mathematical checked object."""
    __slots__ = ('_plan', '_commitment')

    def __init__(self, plan, commitment, *, _token=None):
        binding.require(_token is _ADMISSION, 'authenticated receipt scope factory required')
        from validation.suffix5.window_plan import _population as validate_catalogue
        plan = validate_catalogue(plan, commitment['block_plan_sha256'])
        binding.require(plan['source_bundle_sha256'] == commitment['source_bundle_sha256'] and
                        plan['case_sha256'] == commitment['case_sha256'] and
                        plan['logical_plan_sha256'] == commitment['logical_plan_sha256'] and
                        plan['total_models'] == commitment['unique_logical_models'],
                        'receipt catalogue and admitted population differ')
        object.__setattr__(self, '_plan', binding.canonical(plan))
        object.__setattr__(self, '_commitment', binding.canonical(commitment))

    def __setattr__(self, *_):
        raise AttributeError('immutable receipt scope')

    def plan(self):
        return json.loads(self._plan)

    def commitment(self):
        return json.loads(self._commitment)


class CheckedRegistry:
    """An admitted compact registry; scheduling-only loads have no report bodies."""
    __slots__ = ('_metadata', '_receipts')

    def __init__(self, metadata, receipts, *, _token=None):
        binding.require(_token is _ADMISSION, 'checked registry factory required')
        raw = binding.canonical(metadata)
        binding.require(len(raw) <= REGISTRY_LIMIT, 'compact registry byte cap')
        object.__setattr__(self, '_metadata', raw)
        object.__setattr__(self, '_receipts', tuple(receipts))

    def __setattr__(self, *_):
        raise AttributeError('immutable checked registry')

    def metadata(self):
        return json.loads(self._metadata)

    def completed_block_ids(self):
        return tuple(row['range']['block_id'] for row in self.metadata()['blocks'])

    def block_reports(self):
        binding.require(len(self._receipts) == len(self.metadata()['entries']),
                        'scheduling registry requires cold reconciliation before aggregation')
        return sorted((row for receipt in self._receipts for row in receipt.block_reports()),
                      key=lambda row: row['range']['block_id'])


def _compact_report(report, entry_id):
    return dict(range=report['range'], entry_id=entry_id, summary_sha256=binding.digest(report),
                aggregate_sha256=binding.digest(report['aggregate']),
                segments=[dict(segment_id=row['segment_id'], start=row['aggregate']['start'],
                    end=row['aggregate']['end'], summary_sha256=binding.digest(row))
                    for row in report['segment_summaries']])


def _check_record(row, descriptor, block_id, source_context):
    """Check byte/source linkage; numerical authority belongs to the reviewed run."""
    from .lp_stream_jobs import LPStreamJob
    suffix_census.same(row['descriptor'], descriptor, 'proof descriptor differs from original catalogue')
    record, verification = row['record'], row['verification']
    model = record['model']
    identity = dict(source_bundle_sha256=model['family_bundle_sha256'],
                    **{key: model[key] for key in ('family_id', 'word', 'arrival_bands')})
    suffix_census.same(identity, descriptor['logical_identity'], 'proof model logical identity changed')
    suffix_census.same(verification, dict(model_ordinal=descriptor['ordinal'], block_id=block_id,
        logical_identity_sha256=descriptor['logical_identity_sha256'], model_sha256=binding.digest(model),
        record_sha256=binding.digest(record), result=record['result'], checked_stage_count=len(record['stages']),
        independent_certificate_verified=True, physical_witness_verified=False,
        query_optimum_certified=False, literal_G8_closed=False), 'checked proof bytes/result binding changed')
    candidate = row['candidate_identity']
    job = LPStreamJob(source_context, block_id, descriptor['ordinal'], binding.digest(model), model)
    suffix_census.same(candidate, job.header(candidate['generation']), 'proof candidate source identity changed')
    return verification['result'], len(job.input_bytes)


def _reports(blocks, results, supplied, before):
    from validation.suffix5.aggregate_stream import StreamAggregator
    binding.require(len(supplied) == len(blocks), 'completed report count differs from selected blocks')
    for block, report in zip(blocks, supplied):
        before()
        span = block['range']
        suffix_census.same(report['range'], span, 'completed report span differs from catalogue')
        binding.require(report['schema'] == 'suffix5-checked-block-certificates-v1' and
            report['complete'] is True and report['complete_certificates'] is True and
            type(report['verified_models']) is int and report['verified_models'] == span['model_count'] and
            report['unresolved_ordinals'] == [] and report['unsubmitted_ordinals'] == [],
            'only complete exhaustive checked block reports are admitted')
        for key in ('query_optimum_certified', 'literal_G8_closed'):
            binding.require(report[key] is False, 'block report claims unsupported authority')
        aggregate, current, segment, segments = StreamAggregator(start=span['start']), None, None, []
        for descriptor in block['descriptors']:
            ordinal = descriptor['ordinal']
            binding.require(ordinal in results, 'gap in completed proof dispositions')
            result = results[ordinal]
            aggregate.add(ordinal, result)
            if descriptor['segment_id'] != current:
                if segment is not None:
                    segments.append(dict(segment_id=current, aggregate=segment.summary()))
                current, segment = descriptor['segment_id'], StreamAggregator(start=ordinal)
            segment.add(ordinal, result)
        segments.append(dict(segment_id=current, aggregate=segment.summary()))
        suffix_census.same(report['aggregate'], aggregate.summary(), 'block aggregate differs from checked results')
        suffix_census.same(report['segment_summaries'], segments, 'block segment identity/range/aggregate changed')
        empty = aggregate.summary()['result']['status'] == 'empty_restricted_family'
        binding.require((empty and report.get('physical_witness_not_required') is True) or
                        (not empty and report['physical_witness_verified'] is True),
                        'completed block lacks checked physical winner')


def _archive(path, pin, encoding, blocks, source_context, summary, before, *, retained=None):
    reader = ArchiveReader(path, compressed_sha256=pin['sha256'], compressed_bytes=pin['size_bytes'], before=before)
    expected = {row['ordinal']: (block['range']['block_id'], row)
                for block in blocks for row in block['descriptors']}
    results, reports, header, footer, retained_seen = {}, [], None, None, set()
    submitted_input_bytes = 0
    for position, row in enumerate(reader):
        before()
        kind = row.get('kind')
        binding.require(footer is None, 'proof row after final footer')
        if position == 0:
            header = row
            suffix_census.same(header['source_context'], source_context, 'proof source context changed')
            suffix_census.same(header['blocks'], [block['range'] for block in blocks], 'archive catalogue selection changed')
            schema = 'hiroute-suffix-block-resume-archive-v1' if retained is not None else 'hiroute-suffix-block-proof-archive-v1'
            binding.require(kind == 'header' and header['schema'] == schema and
                            header['expected_models'] == len(expected), 'completed archive header changed')
        elif kind in ('model_certificate', 'retained_certificate_reference'):
            ordinal = row['descriptor']['ordinal']
            binding.require(type(ordinal) is int and ordinal in expected and ordinal not in results,
                            'foreign or duplicate completed model disposition')
            block_id, descriptor = expected[ordinal]
            if kind == 'model_certificate':
                results[ordinal], size = _check_record(row, descriptor, block_id, source_context)
                submitted_input_bytes += size
                binding.require(submitted_input_bytes <= summary['resource_plan']['maximum_input_bytes'],
                                'completed candidate input byte cap exceeded')
            else:
                binding.require(retained is not None and ordinal in retained, 'missing transitive retained proof')
                expected_row = retained[ordinal]
                suffix_census.same(row, expected_row, 'retained reference differs from immutable old proof/cold receipt')
                results[ordinal] = row['verification']['result']
                retained_seen.add(ordinal)
        elif kind == 'block_certificate_checkpoint':
            binding.require(retained is None and row['acceptance'] is False and
                            row['cold_certificate_replay_required'] is True,
                            'checkpoint cannot supply acceptance')
        elif kind == 'block_report':
            report = row['report']
            witness = row['winner_witness']
            if report.get('physical_witness_verified') is True:
                binding.require(type(witness) is dict and witness.get('physical_witness_verified') is True,
                                'completed report lacks retained physical witness')
            reports.append(report)
        elif kind == 'footer':
            footer = row
        else:
            raise ValueError('unresolved, unsubmitted or unknown completed archive row')
    binding.require(header is not None and footer is not None and set(results) == set(expected),
                    'completed archive has missing header/footer/model dispositions')
    binding.require(retained is None or retained_seen == set(retained), 'retained proof coverage changed')
    suffix_census.same(encoding, dict(complete=True, **{key: reader.summary[key] for key in
                        ('uncompressed_bytes', 'uncompressed_sha256', 'rows', 'encoding')}),
                        'completed archive encoding differs from consumed bytes')
    footer_schema = 'hiroute-suffix-block-resume-footer-v1' if retained is not None else 'hiroute-suffix-block-proof-footer-v1'
    binding.require(footer['schema'] == footer_schema and footer['complete'] is True and
                    footer['verified_models'] == footer['expected_models'] == len(expected),
                    'completed archive footer changed')
    for document in (footer, summary):
        for key in FALSE_AUTHORITY:
            binding.require(document[key] is False, 'window claims unsupported full-population authority')
    suffix_census.same(footer['blocks'], reports, 'archive final reports changed')
    suffix_census.same(summary['blocks'], reports, 'summary differs from archive reports')
    suffix_census.same(footer['transport'], summary['transport'], 'completed transport summary changed')
    from .block_replay import transport_complete
    binding.require(transport_complete(footer['transport'], 2 if retained is not None else len(expected)),
                    'completed receipt transport coverage changed')
    binding.require(type(footer['transport'].get('input_bytes')) is int and
                    footer['transport']['input_bytes'] == submitted_input_bytes,
                    'transport candidate input bytes differ from consumed full models')
    _reports(blocks, results, reports, before)
    return reports


class _Dependencies:
    """One reconciliation's input-byte cache, never a certificate authority."""
    def __init__(self, before):
        self.before, self.rows, self.decoded, self.used = before, {}, {}, set()
        self.admitted = {}
        self.phases = {}

    def read(self, path, sha, limit, *, decode=True, size=None):
        key = (os.path.abspath(path), sha)
        self.used.add(key)
        if decode and key not in self.decoded:
            self.decoded[key], self.rows[key] = _read(path, sha, limit, self.before, size=size, with_pin=True)
        elif key not in self.rows:
            self.rows[key] = _read(path, sha, limit, self.before, size=size, decode=False)
        binding.require(self.rows[key]['size_bytes'] <= limit and
                        (size is None or self.rows[key]['size_bytes'] == size), 'cached dependency size cap/pin')
        self.before()
        return _owned(self.decoded[key] if decode else self.rows[key])


def _retained(values, files, evidence, selection, source_context, cache, before):
    from . import block_resume as seed
    old_selection = cache.read(values['old_selection'], seed.OLD_SELECTION_SHA, SUMMARY_LIMIT)
    old = cache.read(values['old_summary'], seed.OLD_SUMMARY_SHA, SUMMARY_LIMIT)
    cold = cache.read(evidence / 'cold-replay.json', SEED_COLD, SUMMARY_LIMIT)
    suffix_census.same(old_selection, selection, 'retained old selection changed')
    suffix_census.same(old['population'], selection['population'], 'retained population changed')
    suffix_census.same(old['proof_archive'], dict(path='model-proofs.jsonl.gz', **seed.archive_pin()),
                       'retained old proof archive changed')
    binding.require(old['complete'] is False and old['verified_models'] == SEED_RETAINED_MODELS and
                    cold['schema'] == 'hiroute-cold-replayed-blocks-v1' and
                    cold['checked_models'] == SEED_RETAINED_MODELS and cold['expected_models'] == cold['observed_models'] == SEED_MODELS and
                    cold['historical_attempt_claimed_complete'] is False and
                    cold['historical_runtime_revalidated'] is False and
                    cold['historical_archive_finalized'] is True and cold['historical_footer_present'] is True,
                    'seed requires finalized failed history and successful cold continuation')
    for key in FALSE_AUTHORITY:
        binding.require(old[key] is False and cold[key] is False, 'unsupported retained history authority')
    old_context = source_context['previous_source_context']
    suffix_census.same(old_context, old['source_context'], 'retained source context changed')
    suffix_census.same(old_context, cold['source_context'], 'cold replay source context changed')
    suffix_census.same(old['resource_plan'], seed.resource_plan(old['resource_plan']['worker_cpus'], historical=True),
                       'old verifier resource contract changed')
    expected_old = dict(schema='hiroute-suffix-block-work-context-v1', source_sha256=seed.OLD_SOURCE_SHA,
        **{key: source_context[key] for key in ('source_bundle_sha256', 'capture_sha256', 'block_plan_sha256',
                                                'selection_sha256', 'original_query_freeze_sha256')},
        resource_plan_sha256=binding.digest(old['resource_plan']))
    suffix_census.same(old_context, expected_old, 'retained inputs differ from admitted continuation')
    expected = {row['ordinal']: (block['range']['block_id'], row)
                for block in selection['blocks'] for row in block['descriptors']}
    references = {row['model_ordinal']: row for row in cold['certificate_refs']}
    binding.require(len(references) == SEED_RETAINED_MODELS and len(references) == len(cold['certificate_refs']) and
                    sorted(references) == cold['certified_ordinals'] == sorted(set(expected) - set(seed.MODEL_PINS)),
                    'cold receipt exact retained coverage changed')
    reader = ArchiveReader(values['old_archive'], compressed_sha256=seed.OLD_ARCHIVE_SHA,
                           compressed_bytes=seed.OLD_ARCHIVE_BYTES, before=before)
    retained, footer = {}, None
    for position, row in enumerate(reader):
        before()
        if row.get('kind') == 'model_certificate':
            ordinal = row['descriptor']['ordinal']
            binding.require(ordinal in references and ordinal not in retained, 'foreign or duplicate old certificate')
            block_id, descriptor = expected[ordinal]
            _check_record(row, descriptor, block_id, old_context)
            reference = references[ordinal]
            binding.require(reference['block_id'] == block_id and reference['archive_row_index'] == position and
                            reference['archive_row_sha256'] == hashlib.sha256(binding.canonical(row)+b'\n').hexdigest(),
                            'cold receipt old row pin changed')
            suffix_census.same(reference['current_verification'], row['verification'], 'cold checked result changed')
            retained[ordinal] = dict(kind='retained_certificate_reference', descriptor=descriptor,
                verification=row['verification'], provenance=dict(archive=seed.archive_pin(), source_context=old_context,
                    archive_row_index=position, archive_row_sha256=reference['archive_row_sha256']))
        elif row.get('kind') == 'footer':
            footer = row
    binding.require(set(retained) == set(references) and footer is not None and footer['complete'] is False,
                    'missing old certificate dependency or changed historical completion')
    suffix_census.same(cold['archive'], reader.summary, 'cold replay archive receipt changed')
    suffix_census.same(old['encoding'], dict(complete=True, **{key: reader.summary[key] for key in
        ('uncompressed_bytes', 'uncompressed_sha256', 'rows', 'encoding')}), 'old archive encoding changed')
    suffix_census.same(old['blocks'], footer['blocks'], 'old report/archive relationship changed')
    cache.rows[(os.path.abspath(values['old_archive']), seed.OLD_ARCHIVE_SHA)] = dict(
        path=os.path.abspath(values['old_archive']), **seed.archive_pin())
    cache.used.add((os.path.abspath(values['old_archive']), seed.OLD_ARCHIVE_SHA))
    return retained


def _upstream_phases(values, commitment, cache, deadline):
    """Keep the complete structural and logical proof graph available, once."""
    for prefix, profile in (('replay', BATCH_REPLAY), ('logical', REPLAY)):
        attempt = Path(values[prefix+'_attempt'])
        expectations = {field: values[field] for field in (
            ('replay_plan_sha', 'replay_manifest_sha', 'replay_result_sha', 'replay_decision_sha', 'query_index_sha')
            if prefix == 'replay' else ('replay_plan_sha', 'logical_source_sha', 'logical_report_sha'))}
        key = (os.path.abspath(attempt), values[prefix+'_return_sha'], binding.digest(expectations))
        if key in cache.phases:
            cache.used.update(cache.phases[key])
            continue
        used = set(cache.used)
        returned = cache.read(values[prefix+'_return'], values[prefix+'_return_sha'], 65536)
        result = read_phase_result(attempt, successful_return=returned, deadline_monotonic=deadline,
                                   resource_check=cache.before)
        binding.require(result.get('status') == 'completed', 'missing completed upstream '+prefix+' proof')
        suffix_census.same(result['profile'], asdict(profile), 'upstream '+prefix+' profile changed')
        metadata_keys = set()
        if prefix == 'replay':
            manifest_sha = values['replay_manifest_sha']
            for filename, field in (('result.json', 'replay_result_sha'), ('decision.json', 'replay_decision_sha')):
                cache.read(attempt/filename, values[field], 65536)
                metadata_keys.add((os.path.abspath(attempt/filename), values[field]))
            binding.require(result['context']['plan_sha256'] == values['replay_plan_sha'], 'upstream replay plan changed')
        else:
            manifest_sha = result['verified_manifest_sha256']
            binding.require(result['context']['plan_sha256'] == values['replay_plan_sha'] and
                            result['context']['source_sha256'] == values['logical_source_sha'],
                            'upstream logical source/plan changed')
            for filename, field in (('result.json', 'result_sha256'), ('decision.json', 'decision_sha256')):
                cache.read(attempt/filename, returned['acceptance_receipt'][field], 65536)
                metadata_keys.add((os.path.abspath(attempt/filename), returned['acceptance_receipt'][field]))
        cache.read(attempt/'request.json', result['request_sha256'], 1024**2)
        metadata_keys.add((os.path.abspath(attempt/'request.json'), result['request_sha256']))
        decision = cache.read(attempt/'decision.json', returned['acceptance_receipt']['decision_sha256'], 65536)
        ready_sha = decision['supervisor_decision_sha256']
        cache.read(attempt/'supervisor-decision.json', ready_sha, 65536)
        metadata_keys.add((os.path.abspath(attempt/'supervisor-decision.json'), ready_sha))
        binding.require(result['verified_manifest_sha256'] == manifest_sha, 'upstream manifest binding changed')
        manifest = cache.read(attempt/'evidence/__manifest.json', manifest_sha, 1024**2)
        files = {pin['path']: pin for pin in manifest['files']}
        binding.require(len(files) == len(manifest['files']), 'duplicate upstream manifest dependency')
        if prefix == 'replay':
            anchors = commitment['completed_replay']
            for field, name in (('query_index', 'query-index.json'), ('structural_summary', 'structural-summary.json'),
                                ('parallel_summary', 'parallel-summary.json')):
                suffix_census.same(files[name], anchors[field], 'original upstream proof pin changed: '+field)
        else:
            binding.require(set(files) == {'suffix-census.json'} and
                            files['suffix-census.json']['sha256'] == values['logical_report_sha'],
                            'original logical proof pin changed')
        # read_phase_result has consumed and hashed every file in this exact
        # manifest. Retain all pins; do not parse/re-hash large proof arrays.
        phase_keys = metadata_keys
        for pin in manifest['files']:
            row = dict(path=os.path.abspath(attempt/'evidence'/pin['path']),
                       sha256=pin['sha256'], size_bytes=pin['size_bytes'])
            dep_key = (row['path'], row['sha256'])
            cache.rows[dep_key] = row
            cache.used.add(dep_key); phase_keys.add(dep_key)
        # Include already consumed shared return metadata as well as new keys.
        for path, sha in ((values[prefix+'_return'], values[prefix+'_return_sha']),
                          (attempt/'evidence/__manifest.json', manifest_sha)):
            phase_keys.add((os.path.abspath(path), sha))
        phase_keys.update(cache.used-used)
        cache.phases[key] = phase_keys


def _physical_inputs(values, cache):
    """Retain immutable exported data, without reopening historical code files."""
    original = cache.read(values['historical_plan'], values['historical_plan_sha'], 4*1024**2)
    replay = cache.read(values['replay_plan'], values['replay_plan_sha'], 4*1024**2)
    inputs = original['inputs']
    roles = {'export_manifest', 'resolved_states', 'selection', 'original_tree', 'table', 'restriction'}
    binding.require(type(inputs) is dict and set(inputs) in (roles, roles | {'reference'}) and
                    binding.digest(inputs) == original['input_sha256'], 'historical physical input manifest changed')
    suffix_census.same(replay['inputs'], inputs, 'replay physical inputs differ from original export')
    suffix_census.same(replay['input_sha256'], original['input_sha256'], 'replay physical input binding changed')
    for role, pin in inputs.items():
        cache.before()
        binding.require(type(pin) is dict and set(pin) == {'path', 'sha256', 'size_bytes'} and
                        type(pin['size_bytes']) is int and 0 <= pin['size_bytes'] <= 1024**3,
                        'bounded immutable physical input pin required: '+role)
        path = binding.inside(binding.ROOT, pin['path'])
        cache.read(path, pin['sha256'], 1024**3, size=pin['size_bytes'], decode=False)


def _inputs(values, commitment, cache, deadline):
    """Retain the full original input snapshots, as well as proof dependencies."""
    pairs = [('historical_plan', values['historical_plan_sha'], 4*1024**2),
             ('replay_plan', values['replay_plan_sha'], 4*1024**2),
             ('replay_return', values['replay_return_sha'], 65536),
             ('logical_return', values['logical_return_sha'], 65536),
             ('capture', commitment['completed_replay']['capture_sha256'], 1024**3)]
    for key, sha, limit in pairs:
        cache.read(values[key], sha, limit, decode=False)
    anchors = commitment['completed_replay']
    suffix_census.same(values['historical_plan_sha'], anchors['historical_plan_sha256'], 'historical plan admission changed')
    suffix_census.same(values['replay_plan_sha'], anchors['replay_plan_sha256'], 'replay plan admission changed')
    suffix_census.same(values['replay_return_sha'], anchors['successful_return_sha256'], 'replay return admission changed')
    suffix_census.same(values['replay_manifest_sha'], anchors['manifest_sha256'], 'replay manifest admission changed')
    suffix_census.same(values['query_index_sha'], anchors['query_index']['sha256'], 'original query admission changed')
    _physical_inputs(values, cache)
    from .variant_scope import is_d0_population, physical_scope
    if is_d0_population(commitment):
        original = cache.read(values['historical_plan'], values['historical_plan_sha'], 4*1024**2)
        binding.require(physical_scope(original), 'D0 receipt cannot consume a D1 plan')
    _upstream_phases(values, commitment, cache, deadline)


def _admit(spec, admitted, selection, reviewed_sources, deadline, before, cache):
    if spec.get('module') == 'suffix_window_recovery':
        from .window_recovery_receipts import _admit_recovery
        return _admit_recovery(spec, admitted, selection, reviewed_sources, deadline, before, cache)
    before()
    cache.used = set()
    plan, commitment = _population(admitted)
    cache_key = binding.digest(dict(spec=spec, population=commitment))
    if cache_key in cache.admitted:
        binding.require(selection is None, 'cached admission cannot replace externally supplied selection')
        receipt = cache.admitted[cache_key]
        cache.used = {(row['path'], row['sha256']) for row in receipt.metadata()['dependencies']}
        return receipt
    attempt, module = Path(spec['attempt']), spec['module']
    binding.require(module in ('block_resume', 'suffix_window'), 'unknown reviewed receipt contract')
    evidence = attempt / 'evidence'
    successful = cache.read(spec['successful_return'], spec['successful_return_sha256'], 65536)
    binding.require(successful.get('status') == 'completed' and 'acceptance_receipt' in successful,
                    'independently retained actual successful runtime return required')
    for name, field in (('result.json', 'result_sha256'), ('decision.json', 'decision_sha256')):
        suffix_census.same(spec[field], successful['acceptance_receipt'][field], 'external result/decision pins disagree')
        cache.read(attempt / name, spec[field], 65536)
    decision = cache.read(attempt/'decision.json', spec['decision_sha256'], 65536)
    cache.read(attempt/'supervisor-decision.json', decision['supervisor_decision_sha256'], 65536)
    result = read_phase_result(attempt, successful_return=successful, deadline_monotonic=deadline, resource_check=before)
    binding.require(result.get('status') == 'completed' and result['descendants_reaped'] is True,
                    'window runtime did not return successful checked evidence')
    suffix_census.same(result['profile'], asdict(BATCH_REPLAY), 'exact BATCH_REPLAY runtime profile required')
    suffix_census.same(result['verified_manifest_sha256'], spec['manifest_sha256'], 'pinned completed manifest changed')
    request = cache.read(attempt / 'request.json', result['request_sha256'], 1024**2)
    values = _command(request, module)
    _source(values['source_commit'], values['source_sha'], module, reviewed_sources)
    binding.require(request['deadline_monotonic'] <= request['entry_monotonic'] + 900,
                    'completed window exceeded reviewed 900-second phase budget')
    manifest = cache.read(evidence / '__manifest.json', spec['manifest_sha256'], 1024**2)
    binding.require(type(manifest['charged_bytes']) is int and manifest['charged_bytes'] <= 512*1024**2,
                    'completed window exceeds reviewed 512 MiB evidence charge')
    files = {row['path']: row for row in manifest['files']}
    binding.require(len(files) == len(manifest['files']), 'duplicate evidence path')
    seed = module == 'block_resume'
    summary_name = 'block-resume-summary.json' if seed else 'window-summary.json'
    selection_name = 'pilot-selection.json' if seed else 'window-selection.json'
    proof_name = 'continued-model-proofs.jsonl.gz' if seed else 'model-proofs.jsonl.gz'
    expected_files = {'run-binding.json', 'batch-ledger.json', 'family-summary.json', 'block-plan.json',
                      summary_name, selection_name, proof_name, 'cold-replay.json' if seed else 'base-registry.json'}
    binding.require(set(files) == expected_files, 'reviewed completed evidence file coverage changed')
    def read(name, limit=SUMMARY_LIMIT):
        pin = files[name]
        return cache.read(evidence / name, pin['sha256'], limit, size=pin['size_bytes'])
    summary, run, actual_selection = read(summary_name), read('run-binding.json'), read(selection_name)
    suffix_census.same(read('block-plan.json'), plan, 'completed run catalogue differs from independent admission')
    selection = _selection(admitted, actual_selection if selection is None else selection, before)
    suffix_census.same(actual_selection, selection, 'completed selected descriptors changed')
    prefix = 'hiroute-suffix-block-resume' if seed else 'hiroute-suffix-window'
    binding.require(run['schema'] == prefix+'-binding-v1' and summary['schema'] == (
        'hiroute-four-block-resume-summary-v1' if seed else prefix+'-summary-v1'), 'reviewed receipt schemas changed')
    suffix_census.same(run['source_commit'], values['source_commit'], 'run commit differs from command')
    suffix_census.same(run['source_sha256'], values['source_sha'], 'run source inventory differs from command')
    suffix_census.same(run['completed_replay'], commitment['completed_replay'], 'run completed inputs changed')
    suffix_census.same(run['logical_report_sha256'], values['logical_report_sha'], 'run logical population changed')
    suffix_census.same(summary['population'], commitment, 'summary population differs from independent admission')
    suffix_census.same(summary['selection'], files[selection_name], 'summary selection bytes changed')
    suffix_census.same(summary['proof_archive'], files[proof_name], 'summary full proof bytes changed')
    suffix_census.same(summary['resource_plan'], run['resource_plan'], 'run/summary resource contract changed')
    family = read('family-summary.json')['checked']
    binding.require(family['bundle_sha256'] == commitment['source_bundle_sha256'] and
                    family['case_sha256'] == commitment['case_sha256'], 'completed checked family changed')
    resources, context = summary['resource_plan'], summary['source_context']
    expected_context = dict(schema=prefix+'-context-v1',
        source_sha256=values['source_sha'], source_bundle_sha256=commitment['source_bundle_sha256'],
        capture_sha256=commitment['completed_replay']['capture_sha256'], block_plan_sha256=commitment['block_plan_sha256'],
        selection_sha256=files[selection_name]['sha256'], original_query_freeze_sha256=commitment['query_freeze_sha256'],
        resource_plan_sha256=binding.digest(resources))
    retained = None
    if seed:
        from . import block_resume
        binding.require(spec['successful_return_sha256'] == SEED_RETURN and spec['manifest_sha256'] == SEED_MANIFEST and
                        files[summary_name]['sha256'] == SEED_SUMMARY and files[proof_name]['sha256'] == SEED_PROOF and
                        files['cold-replay.json']['sha256'] == SEED_COLD, 'accepted seed pins changed')
        suffix_census.same(resources, block_resume.resource_plan(values['worker_cpus']), 'seed resource contract changed')
        binding.require([b['range']['block_id'] for b in selection['blocks']] == block_resume.BLOCK_IDS and
                        sum(b['range']['model_count'] for b in selection['blocks']) == SEED_MODELS,
                        'fixed accepted seed coverage changed')
        expected_context.update(previous_source_context=context['previous_source_context'],
            previous_archive=block_resume.archive_pin(), previous_summary_sha256=block_resume.OLD_SUMMARY_SHA,
            cold_replay_sha256=SEED_COLD)
        suffix_census.same(context, expected_context, 'seed completed source context changed')
        retained = _retained(values, files, evidence, selection, context, cache, before)
        binding.require(summary['retained_verified_models'] == SEED_RETAINED_MODELS and summary['new_verified_models'] == 2 and
                        summary['proof_complete'] is True and summary['historical_attempt_status'] == 'failed' and
                        summary['historical_runtime_revalidated'] is False, 'seed continuation coverage/status changed')
    else:
        from validation.capture5.containers import detach_json
        from validation.suffix5.window_plan import next_window
        policy = cache.read(values['source_policy'], values['source_policy_sha'], 65536)
        origin = run['invocation_origin']
        suffix_census.same(summary['invocation_origin'], origin, 'reviewed invocation origin changed')
        binding.require(type(origin) is dict and set(origin) == {'schema', 'checkout_root', 'controller_module',
            'controller_path', 'python_executable', 'executable_realpath', 'cwd'} and
            origin['schema'] == 'hiroute-reviewed-controller-origin-v1' and
            origin['controller_module'] == MODULE_PREFIX+'suffix_window' and
            origin['checkout_root'] == str(binding.ROOT.resolve()) and
            origin['controller_path'] == str(Path(origin['checkout_root'])/'experiments/time_cut_v2/recorded_real/suffix_window.py') and
            origin['cwd'] == origin['checkout_root'] and
            request['command'][0] == origin['python_executable'] == sys.executable and
            origin['executable_realpath'] == str(Path(sys.executable).resolve()) and
            all(type(origin[key]) is str and Path(origin[key]).is_absolute() for key in
                ('checkout_root', 'controller_path', 'python_executable', 'executable_realpath', 'cwd')),
            'trusted reviewed-controller origin binding required')
        from .variant_scope import is_d0_population
        from .bootstrap_executor import validate_pinned_policy
        d0 = is_d0_population(commitment)
        policy_sources = validate_pinned_policy(policy, values['source_policy_sha'])
        binding.require((d0 or policy_sources.get(SEED_COMMIT) == SEED_SOURCE) and
                        policy_sources.get(values['source_commit']) == values['source_sha'],
                        'pinned source policy does not approve completed execution')
        for commit, inventory in policy_sources.items():
            binding.require(reviewed_sources.get(commit) == inventory,
                            'historical source policy is outside current reviewed allowlist')
        if values.get('bootstrap') is not None:
            from .population_bootstrap import admit_bootstrap
            binding.require(d0 and values.get('bootstrap_sha') is not None and
                            all(values[key] is None for key in WINDOW_OPTIONALS),
                            'D0 bootstrap cannot mix seed or registry inputs')
            _, base = admit_bootstrap(SimpleNamespace(**values), reviewed_sources, deadline=deadline,
                                     before=before, admitted=admitted if type(admitted) is not ReceiptScope else None, cache=cache)
            suffix_census.same(base.metadata()['population'], commitment, 'bootstrap receipt population changed')
            base_sha = files['base-registry.json']['sha256']
            admission = dict(kind='d0-replay-count-bootstrap-v1', bootstrap_sha256=values['bootstrap_sha'],
                             source_policy_sha256=values['source_policy_sha'])
        elif values['registry'] is None:
            binding.require(not d0, 'D0 cannot use the historical D1 seed')
            binding.require(all(values[key] is None for key in ('registry_sha', 'registry_return', 'registry_return_sha')) and
                            all(values[key] is not None for key in ('seed_attempt', 'seed_return', 'old_archive',
                                                                   'old_summary', 'old_selection')),
                            'initial window requires only the fixed seed admission inputs')
            used = set(cache.used)
            seed_args = SimpleNamespace(**values)
            seed_spec = _spec(seed_args, 'seed', 'block_resume', SEED_RETURN, SEED_MANIFEST,
                              before=before)
            seed_receipt = _admit(seed_spec, admitted, None, reviewed_sources, deadline, before, cache)
            cache.used |= used
            base = make_registry(admitted, [seed_receipt])
            base_sha = files['base-registry.json']['sha256']
            admission = dict(kind='seed-resume-v1', successful_return_sha256=SEED_RETURN,
                             manifest_sha256=SEED_MANIFEST, source_policy_sha256=values['source_policy_sha'])
        else:
            binding.require(values.get('bootstrap_sha') is None, 'partial bootstrap cannot enter a later window')
            binding.require(all(values[key] is None for key in WINDOW_OPTIONALS if not key.startswith('registry')),
                            'later window cannot mix seed and registry admissions')
            base = load_scheduling_registry(values['registry'], values['registry_sha'], admitted,
                registration_return=values['registry_return'], registration_return_sha=values['registry_return_sha'],
                reviewed_sources=reviewed_sources, deadline=deadline, before=before)
            base_sha = values['registry_sha']
            admission = dict(kind='registered-window-ledger-v1', registry_sha256=values['registry_sha'],
                registration_return_sha256=values['registry_return_sha'], source_policy_sha256=values['source_policy_sha'])
        suffix_census.same(read('base-registry.json'), base.metadata(), 'copied base registry changed')
        binding.require(files['base-registry.json']['sha256'] == base_sha, 'base registry exact bytes changed')
        window = detach_json(next_window(plan, base.completed_block_ids(), population_plan_sha256=binding.digest(plan),
            maximum_blocks=values.get('maximum_blocks', 32)))
        suffix_census.same(selection['window_plan'], window, 'completed window not the first outstanding catalogue window')
        suffix_census.same([b['range'] for b in selection['blocks']], window['blocks'], 'window block selection changed')
        suffix_census.same(selection, dict(schema='hiroute-suffix-window-selection-v1', population=commitment,
            window_plan=window, blocks=selection['blocks'], selection_uses_outcomes=False,
            numerical_cache_enabled=False, maximum_candidate_passes=window['expected_model_count']*12,
            maximum_logical_stages=window['expected_model_count']*5), 'reviewed window selection contract changed')
        for doc in (run, summary):
            suffix_census.same(doc['base_registry'], files['base-registry.json'], 'base registry binding changed')
            suffix_census.same(doc['window_id'], window['window_id'], 'window ID changed')
            suffix_census.same(doc['registry_admission'], admission, 'registry admission provenance changed')
        suffix_census.same(run['selection'], files[selection_name], 'run selection binding changed')
        suffix_census.same(summary['registry_admission'], run['registry_admission'], 'registry admission changed')
        expected_context.update(window_id=window['window_id'], base_registry_sha256=base_sha,
                                source_policy_sha256=values['source_policy_sha'])
        suffix_census.same(context, expected_context, 'completed window source context changed')
        models = window['expected_model_count']
        suffix_census.same(resources, dict(name='C01-suffix-window-v1', absolute_seconds=900,
            evidence_charge_bytes=512*1024**2, uncompressed_archive_bytes=512*1024**2,
            maximum_input_bytes=128*1024**2, maximum_blocks=values.get('maximum_blocks', 32),
            maximum_models=values.get('maximum_blocks', 32)*256,
            models=models, block_size=256, persistent_workers=4, candidate_as_bytes=1024**3,
            candidate_peak_rss_bytes=768*1024**2, seconds_per_model=30, maximum_passes_per_model=12,
            maximum_candidate_passes=models*12, maximum_logical_stages=models*5,
            numerical_cache_enabled=False, worker_cpus=values['worker_cpus']), 'window resource contract changed')
        if values['registry'] is not None:
            cache.read(values['registry'], values['registry_sha'], REGISTRY_LIMIT, decode=False)
            cache.read(values['registry_return'], values['registry_return_sha'], 65536, decode=False)
    _inputs(values, commitment, cache, deadline)
    count = sum(block['range']['model_count'] for block in selection['blocks'])
    binding.require(summary['complete'] is True and type(summary['verified_models']) is int and
                    summary['verified_models'] == count, 'window summary lacks complete exact coverage')
    reports = _archive(evidence / proof_name, files[proof_name], summary['encoding'], selection['blocks'], context,
                       summary, before, retained=retained)
    entry = dict(spec, source_commit=values['source_commit'], source_sha256=values['source_sha'],
        catalogue=dict(path=str(evidence/'block-plan.json'), **{k: files['block-plan.json'][k] for k in ('sha256', 'size_bytes')}),
        summary=dict(path=str(evidence/summary_name), **{k: files[summary_name][k] for k in ('sha256', 'size_bytes')}),
        proof=dict(path=str(evidence/proof_name), **{k: files[proof_name][k] for k in ('sha256', 'size_bytes')}),
        selection=dict(path=str(evidence/selection_name), **{k: files[selection_name][k] for k in ('sha256', 'size_bytes')}),
        population_sha256=binding.digest(commitment), source_context_sha256=binding.digest(context),
        dependencies=sorted((cache.rows[key] for key in cache.used), key=lambda row: (row['sha256'], row['path'])))
    if not seed:
        entry['invocation_origin'] = origin
    entry['entry_id'] = binding.digest(entry)
    entry['blocks'] = [_compact_report(report, entry['entry_id']) for report in reports]
    before()
    receipt = CheckedWindowReceipt(entry, reports, _token=_ADMISSION)
    cache.admitted[cache_key] = receipt
    # Keep no descriptor arrays, full catalogues, selections or raw summary
    # document graphs between entries. Pin-only upstream/entry admission cache
    # survives; receipt objects own only compact metadata and block summaries.
    cache.decoded.clear()
    return receipt


def _spec(args, prefix, module, return_sha=None, manifest_sha=None, *, before=lambda: None):
    returned = getattr(args, prefix+'_return')
    actual_sha = return_sha or getattr(args, prefix+'_return_sha')
    result_sha, decision_sha = getattr(args, prefix+'_result_sha', None), getattr(args, prefix+'_decision_sha', None)
    if result_sha is None or decision_sha is None:
        binding.require(prefix == 'seed', 'explicit completed window result and decision pins required')
        successful = _read(returned, actual_sha, 65536, before)
        result_sha = result_sha or successful['acceptance_receipt']['result_sha256']
        decision_sha = decision_sha or successful['acceptance_receipt']['decision_sha256']
    return dict(module=module, attempt=os.path.abspath(getattr(args, prefix+'_attempt')),
        successful_return=os.path.abspath(returned), successful_return_sha256=actual_sha,
        result_sha256=result_sha, decision_sha256=decision_sha,
        manifest_sha256=manifest_sha or getattr(args, prefix+'_manifest_sha'))


def admit_seed_resume(args, admitted, *, deadline, before=lambda: None):
    """Admit only the fixed, accepted 1,024-model continuation and its old proofs."""
    check = _guard(deadline, before)
    spec = _spec(args, 'seed', 'block_resume', SEED_RETURN, SEED_MANIFEST, before=check)
    receipt = _admit(spec, admitted, None, {}, deadline, check, _Dependencies(check))
    return make_registry(admitted, [receipt])


def scope_from_seed(args, *, deadline, before=lambda: None):
    """Bootstrap controller catalogue context only from the fixed accepted seed.

    This authenticates execution provenance, not fresh mathematical replay.
    admit_seed_resume still checks the complete retained proof dependency graph.
    """
    check = _guard(deadline, before)
    spec = _spec(args, 'seed', 'block_resume', SEED_RETURN, SEED_MANIFEST, before=check)
    attempt, cache = Path(spec['attempt']), _Dependencies(check)
    successful = cache.read(spec['successful_return'], SEED_RETURN, 65536)
    for name, field in (('result.json', 'result_sha256'), ('decision.json', 'decision_sha256')):
        suffix_census.same(spec[field], successful['acceptance_receipt'][field], 'seed result/decision pin changed')
        cache.read(attempt/name, spec[field], 65536)
    result = read_phase_result(attempt, successful_return=successful, deadline_monotonic=deadline, resource_check=check)
    binding.require(result.get('status') == 'completed' and result['verified_manifest_sha256'] == SEED_MANIFEST,
                    'accepted seed execution is required for receipt scope')
    suffix_census.same(result['profile'], asdict(BATCH_REPLAY), 'seed exact runtime profile changed')
    request = cache.read(attempt/'request.json', result['request_sha256'], 1024**2)
    values = _command(request, 'block_resume')
    _source(values['source_commit'], values['source_sha'], 'block_resume', {})
    evidence = attempt/'evidence'
    manifest = cache.read(evidence/'__manifest.json', SEED_MANIFEST, 1024**2)
    files = {row['path']: row for row in manifest['files']}
    binding.require(files['block-resume-summary.json']['sha256'] == SEED_SUMMARY,
                    'seed scope summary pin changed')
    summary = cache.read(evidence/'block-resume-summary.json', SEED_SUMMARY, SUMMARY_LIMIT)
    pin = files['block-plan.json']
    plan = cache.read(evidence/'block-plan.json', pin['sha256'], SUMMARY_LIMIT, size=pin['size_bytes'])
    _inputs(values, summary['population'], cache, deadline)
    check()
    return ReceiptScope(plan, summary['population'], _token=_ADMISSION)


def scope_from_registry(registry, *, deadline, before=lambda: None):
    binding.require(type(registry) is CheckedRegistry, 'authenticated registry required for receipt scope')
    check = _guard(deadline, before)
    metadata = registry.metadata()
    binding.require(bool(metadata['entries']), 'empty registry has no authenticated catalogue source')
    pin = metadata['entries'][0]['catalogue']
    plan = _read(pin['path'], pin['sha256'], SUMMARY_LIMIT, check, size=pin['size_bytes'])
    return ReceiptScope(plan, metadata['population'], _token=_ADMISSION)


def scope_from_registered_registry(path, registry_sha, *, registration_return,
                                   registration_return_sha, reviewed_sources, deadline, before=lambda: None):
    """Controller bootstrap without rebuilding a mathematical family object.

    The externally retained registration return authenticates the metadata's
    population and its source-bound catalogue pointer; the catalogue is read
    with that exact pin before a ReceiptScope is constructed.
    """
    check = _guard(deadline, before)
    returned = _read(registration_return, registration_return_sha, 65536, check)
    binding.require(returned.get('schema') == 'hiroute-window-registry-registration-return-v1' and
                    returned.get('status') == 'registered' and returned.get('registry_sha256') == registry_sha,
                    'independently pinned actual registration return required')
    metadata = _read(path, registry_sha, REGISTRY_LIMIT, check, size=returned['registry_size_bytes'])
    binding.require(bool(metadata['entries']) and returned['population_sha256'] == binding.digest(metadata['population']),
                    'registered population commitment changed')
    for entry in metadata['entries']:
        _source(entry['source_commit'], entry['source_sha256'], entry['module'], reviewed_sources)
    pin = metadata['entries'][0]['catalogue']
    plan = _read(pin['path'], pin['sha256'], SUMMARY_LIMIT, check, size=pin['size_bytes'])
    scope = ReceiptScope(plan, metadata['population'], _token=_ADMISSION)
    load_scheduling_registry(path, registry_sha, scope, registration_return=registration_return,
        registration_return_sha=registration_return_sha, reviewed_sources=reviewed_sources,
        deadline=deadline, before=check)
    return scope


def admit_new_completed_window(args, admitted, selection=None, *, reviewed_sources, deadline, before=lambda: None):
    """Admit an independently observed reviewed-controller execution.

    The actual retained return must come from a trusted interpreter, checkout
    and module environment. Arbitrary run_phase completion and matching source
    labels are insufficient. Runtime is byte/resource provenance, not code
    attestation. Cold scheduling needs the actual registration return pin.
    """
    check = _guard(deadline, before)
    return _admit(_spec(args, 'window', 'suffix_window'), admitted, selection,
                  _owned(reviewed_sources), deadline, check, _Dependencies(check))


def _registry_metadata(admitted, entries):
    plan, commitment = _population(admitted)
    blocks, seen, entry_ids = [], set(), set()
    for entry in entries:
        binding.require(entry['entry_id'] not in entry_ids, 'duplicate completed registry entry')
        entry_ids.add(entry['entry_id'])
        binding.require(entry['population_sha256'] == binding.digest(commitment), 'foreign registry population')
        for block in entry['blocks']:
            number = block['range']['block_id']
            binding.require(type(number) is int and 0 <= number < len(plan['blocks']) and number not in seen,
                            'foreign, duplicate or overlapping completed registry block')
            suffix_census.same(block['range'], plan['blocks'][number], 'registry catalogue span changed')
            binding.require(block['entry_id'] == entry['entry_id'], 'registry block entry changed')
            cursor = block['range']['start']
            for segment in block['segments']:
                ident = segment['segment_id']
                binding.require(type(ident) is int and 0 <= ident < len(plan['segments']), 'foreign registry segment')
                original = plan['segments'][ident]
                binding.require(segment['start'] == cursor == max(original['start'], block['range']['start']) and
                                segment['end'] == min(original['end'], block['range']['end']) and cursor < segment['end'],
                                'registry segment gap, overlap or changed catalogue span')
                _sha(segment['summary_sha256'])
                cursor = segment['end']
            binding.require(cursor == block['range']['end'], 'registry segment coverage gap')
            _sha(block['summary_sha256']); _sha(block['aggregate_sha256'])
            seen.add(number); blocks.append(block)
    return dict(schema='hiroute-checked-window-registry-v1', population=commitment,
        catalogue_sha256=binding.digest(plan['blocks']), entries=entries,
        blocks=sorted(blocks, key=lambda row: row['range']['block_id']),
        completed_models=sum(row['range']['model_count'] for row in blocks),
        authority='source-bound-completed-verifier-execution-v1', fresh_numerical_replay=False, **FALSE_AUTHORITY)


def make_registry(admitted, receipts):
    receipts = tuple(receipts)
    binding.require(all(type(receipt) is CheckedWindowReceipt for receipt in receipts), 'checked window receipts required')
    entries = [receipt.metadata() for receipt in receipts]
    return CheckedRegistry(_registry_metadata(admitted, entries), receipts, _token=_ADMISSION)


def extend_registry(registry, admitted, receipt):
    binding.require(type(registry) is CheckedRegistry and type(receipt) is CheckedWindowReceipt,
                    'checked registry and new checked receipt required')
    metadata = _registry_metadata(admitted, registry.metadata()['entries'] + [receipt.metadata()])
    receipts = registry._receipts + (receipt,) if registry._receipts or not registry.metadata()['entries'] else ()
    return CheckedRegistry(metadata, receipts, _token=_ADMISSION)


def write_registry(registry, path, *, deadline, before=lambda: None):
    """Return registration only after exclusive write and consumed-byte checking.

    Independently retain/pin this actual return. A registry SHA copied from the
    registry itself or reconstructed after interruption is not admission.
    """
    check = _guard(deadline, before)
    binding.require(type(registry) is CheckedRegistry, 'checked registry factory output required')
    raw = registry._metadata + b'\n'
    binding.require(len(raw) <= REGISTRY_LIMIT, 'registry file byte cap')
    destination = Path(os.path.abspath(path))
    parent = _directory(destination.parent)
    try:
        fd = os.open(destination.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=parent)
        with os.fdopen(fd, 'wb') as stream:
            for start in range(0, len(raw), 65536):
                check(); stream.write(raw[start:start+65536])
            stream.flush(); os.fsync(stream.fileno())
    finally:
        os.close(parent)
    sha = hashlib.sha256(raw).hexdigest()
    _read(path, sha, REGISTRY_LIMIT, check, size=len(raw), decode=False)
    metadata = registry.metadata()
    result = dict(schema='hiroute-window-registry-registration-return-v1', status='registered',
        registry_sha256=sha, registry_size_bytes=len(raw), population_sha256=binding.digest(metadata['population']),
        entry_ids=[row['entry_id'] for row in metadata['entries']],
        completed_block_ids=list(registry.completed_block_ids()), authority=metadata['authority'],
        fresh_numerical_replay=False)
    check()
    return result


def load_scheduling_registry(path, registry_sha, admitted, *, registration_return,
                             registration_return_sha, reviewed_sources, deadline, before=lambda: None):
    """Authenticate a previously registered compact snapshot for scheduling only."""
    check = _guard(deadline, before)
    reviewed_sources = _owned(reviewed_sources)
    returned = _read(registration_return, registration_return_sha, 65536, check)
    binding.require(returned['schema'] == 'hiroute-window-registry-registration-return-v1' and
                    returned['status'] == 'registered' and returned['registry_sha256'] == registry_sha and
                    returned['fresh_numerical_replay'] is False,
                    'independently pinned actual registration return required')
    metadata = _read(path, registry_sha, REGISTRY_LIMIT, check, size=returned['registry_size_bytes'])
    expected = _registry_metadata(admitted, metadata['entries'])
    suffix_census.same(metadata, expected, 'registered compact metadata changed')
    suffix_census.same(returned, dict(schema='hiroute-window-registry-registration-return-v1', status='registered',
        registry_sha256=registry_sha, registry_size_bytes=returned['registry_size_bytes'],
        population_sha256=binding.digest(expected['population']),
        entry_ids=[row['entry_id'] for row in expected['entries']],
        completed_block_ids=[row['range']['block_id'] for row in expected['blocks']],
        authority=expected['authority'], fresh_numerical_replay=False), 'registration return coverage changed')
    for entry in metadata['entries']:
        check()
        _source(entry['source_commit'], entry['source_sha256'], entry['module'], reviewed_sources)
        body = {key: value for key, value in entry.items() if key not in ('entry_id', 'blocks')}
        binding.require(binding.digest(body) == entry['entry_id'], 'registry entry commitment changed')
    return CheckedRegistry(metadata, (), _token=_ADMISSION)


def reconcile_registry(registry, admitted, *, reviewed_sources, deadline, before=lambda: None):
    """Cold-authenticate each unique entry and its dependencies before aggregation.

    It uses checked results from the reviewed executions, with no LP/checker
    re-execution. runtime's mandatory manifest pass is preserved.
    """
    binding.require(type(registry) is CheckedRegistry, 'registered scheduling snapshot required')
    check = _guard(deadline, before)
    reviewed_sources = _owned(reviewed_sources)
    cache, receipts = _Dependencies(check), []
    fields = ('module', 'attempt', 'successful_return', 'successful_return_sha256',
              'result_sha256', 'decision_sha256', 'manifest_sha256')
    for entry in registry.metadata()['entries']:
        check()
        # Each entry records only its own dependency set, independently of
        # which other entries happened to precede it in this reconciliation.
        receipt = _admit({key: entry[key] for key in fields}, admitted, None,
                         reviewed_sources, deadline, check, cache)
        actual = receipt.metadata()
        for pin in entry['dependencies']:
            suffix_census.same(cache.rows[(pin['path'], pin['sha256'])], pin, 'registry retained dependency changed')
        suffix_census.same(actual, entry, 'cold registry entry differs from registered admission')
        receipts.append(receipt)
    result = make_registry(admitted, receipts)
    suffix_census.same(result.metadata(), registry.metadata(), 'cold registry coverage changed')
    check()
    return result
