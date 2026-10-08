"""Replay selected original query representatives, never whole-query authority.

Requires a genuine admitted population and a cold-reconciled registry. Only
entries containing requests are consumed again, including their recovery
histories; loser dependencies were already reconciled. Callbacks are provisional until the completed return: any
late archive, deadline, physical check or callback failure aborts the call.
Full certificates are streamed one at a time, not retained in this helper.
The caller owns cumulative disk/RSS budgets and transactional publication.
"""
import hashlib
from pathlib import Path
import time

from validation.family5 import CheckedBundle
from validation.suffix5 import calibration
from validation.suffix5.aggregate_stream import _parse_result
from . import plan as binding, suffix_census, window_receipts as receipts
from . import window_recovery_receipts as recovery_receipts
from .archive_reader import ArchiveReader
from .indexed_population import AdmittedSuffixPopulation

MAX_SELECTED_MODELS = 8192
MAX_REQUEST_BYTES = 16 * 1024**2
PHYSICAL_SECONDS = 30
MAX_RECOVERY_HISTORY = 32
RECOVERY_PLAN_BYTES = 1024**2
_STATUSES = ('attained_optimum', 'primary_unattained', 'secondary_unattained')


def _same(actual, expected, reason):
    suffix_census.same(actual, expected, reason)


def _row_pin(pin, position, row, context):
    return dict(archive=pin, archive_row_index=position,
                archive_row_sha256=hashlib.sha256(binding.canonical(row) + b'\n').hexdigest(),
                source_context=context)


def _requests(admitted, requested, deadline, check):
    binding.require(type(requested) is dict and len(requested) <= MAX_SELECTED_MODELS,
                    'bounded integer-ordinal witness request map required')
    owned, total = {}, 2
    for ordinal, request in requested.items():
        binding.require(type(ordinal) is int and ordinal >= 0 and type(request) is dict and
                        set(request) == {'descriptor', 'result'}, 'exact witness request fields/ordinal required')
        raw = binding.canonical(dict(model_ordinal=ordinal, **request))
        total += len(raw) + int(bool(owned))
        binding.require(total <= MAX_REQUEST_BYTES, 'selected witness request byte cap')
        owned[ordinal] = receipts._owned(request)
    for ordinal, request in owned.items():
        check()
        with calibration.verification_deadline(float(min(deadline, time.monotonic() + PHYSICAL_SECONDS))):
            expected = list(admitted.population.descriptors(ordinal, ordinal + 1))
            binding.require(len(expected) == 1, 'selected ordinal is absent from admitted population')
            _same(request['descriptor'], expected[0], 'selected descriptor differs from admitted population')
            _same(binding.digest(request['descriptor']['logical_identity']),
                  request['descriptor']['logical_identity_sha256'], 'selected logical identity hash changed')
            _parse_result(request['result'])
            binding.require(request['result']['status'] in _STATUSES, 'selected query requires a physical representative')
    check()
    return owned, total


def _entry_blocks(entry):
    return {ordinal: block['range']['block_id'] for block in entry['blocks']
            for ordinal in range(block['range']['start'], block['range']['end'])}


def _reference(entry, row, context, top_pin):
    binding.require(entry['module'] == 'block_resume', 'references require the fixed seed grammar')
    binding.require(set(row) == {'kind', 'descriptor', 'verification', 'provenance'},
                    'unknown retained reference grammar')
    ref = row['provenance']
    binding.require(type(ref) is dict and set(ref) == {'archive', 'source_context', 'archive_row_index',
                    'archive_row_sha256'}, 'unknown retained reference provenance')
    pin = ref['archive']
    binding.require(type(pin) is dict and set(pin) == {'sha256', 'size_bytes'}, 'exact retained archive pin required')
    receipts._sha(pin['sha256']); receipts._sha(ref['archive_row_sha256'])
    binding.require(type(ref['archive_row_index']) is int and ref['archive_row_index'] > 0,
                    'exact retained row index required')
    _same(pin, context['previous_archive'], 'reference differs from seed previous archive')
    _same(ref['source_context'], context['previous_source_context'], 'reference previous source context changed')
    binding.require(pin['sha256'] != top_pin['sha256'], 'cyclic retained archive reference')
    candidates = [p for p in entry['dependencies'] if p['sha256'] == pin['sha256']]
    binding.require(len(candidates) == 1 and candidates[0]['size_bytes'] == pin['size_bytes'],
                    'missing or conflicting retained archive dependency')
    return candidates[0]


def _dependency(entry, pin):
    """Use the admitted exact path, never another file with an aliasing hash."""
    matches = [row for row in entry['dependencies'] if row['path'] == pin['path']]
    binding.require(len(matches) == 1, 'missing or ambiguous recovery dependency path')
    _same(matches[0], pin, 'recovery dependency pin changed')
    return matches[0]


def _recovery_history(entry, header, check):
    """Recover policies from the already admitted, independently pinned plan.

    No runtime is admitted here. CheckedRegistry cold reconciliation supplies
    that authority, including the actual current return and losing proofs.
    """
    context = header['source_context']
    path = str(Path(entry['proof']['path']).parent/'recovery-plan.json')
    matches = [row for row in entry['dependencies'] if row['path'] == path]
    binding.require(len(matches) == 1, 'missing or ambiguous admitted recovery plan')
    pin = _dependency(entry, matches[0])
    _same(pin['sha256'], context['recovery_plan_sha256'], 'selected recovery plan hash changed')
    document = receipts._read(path, pin['sha256'], RECOVERY_PLAN_BYTES, check, size=pin['size_bytes'])
    binding.require(hashlib.sha256(binding.canonical(document)+b'\n').hexdigest() == pin['sha256'] and
        document['schema'] == 'hiroute-suffix-window-recovery-plan-v1' and
        document['historical_attempt_status'] == 'failed', 'selected recovery plan grammar changed')
    predecessors, history = document['predecessors'], header['history']
    binding.require(type(predecessors) is list and 1 <= len(predecessors) <= MAX_RECOVERY_HISTORY and
        type(history) is list and len(history) == len(predecessors), 'bounded complete recovery history required')
    _same(binding.digest(history), context['history_sha256'], 'selected recovery history commitment changed')
    _same(header['previous_archive'], history[-1]['archive'], 'selected recovery previous archive changed')
    _same(context['previous_archive'], history[-1]['archive'], 'selected recovery previous context archive changed')
    _same(context['previous_source_context_sha256'], binding.digest(history[-1]['source_context']),
          'selected recovery previous source context changed')
    seen, total = {entry['proof']['sha256']}, 0
    for number, (ancestor, actual) in enumerate(zip(predecessors, history)):
        check()
        archive = _dependency(entry, ancestor['artifacts']['archive'])
        binding.require(ancestor['module'] == receipts.MODULE_PREFIX +
            ('suffix_window' if number == 0 else recovery_receipts.MODULE), 'recovery history module order changed')
        mode = ancestor['archive_mode']
        binding.require(mode in ('finalized', 'interrupted-prefix') and
            type(actual['gzip_eof']) is bool and actual['gzip_eof'] is (mode == 'finalized') and
            type(actual['trailing_partial_row_bytes']) is int and actual['trailing_partial_row_bytes'] >= 0 and
            (mode != 'finalized' or actual['trailing_partial_row_bytes'] == 0),
            'recovery history differs from explicit archive policy')
        _same(actual['archive'], recovery_receipts._pin(archive), 'recovery chronological archive pin changed')
        _same(actual['source_context'], ancestor['source_context'], 'recovery chronological source context changed')
        binding.require(archive['sha256'] not in seen, 'duplicate or cyclic recovery ancestry')
        seen.add(archive['sha256']); total += archive['size_bytes']
        binding.require(total <= recovery_receipts.HISTORY_BYTES, 'cumulative compressed recovery history byte cap')
    return predecessors, history


def _replay_recovery(entry, selected, physical, check, archives):
    """Read each chronological archive once; references always name full leaves."""
    expected = _entry_blocks(entry)
    references, leaves = {}, {}
    pin = entry['proof']
    header = footer = None
    seen = set()
    reader = ArchiveReader(pin['path'], compressed_sha256=pin['sha256'],
                           compressed_bytes=pin['size_bytes'], before=check)
    for position, row in enumerate(reader):
        check()
        binding.require(type(row) is dict and footer is None, 'invalid recovery row or data after footer')
        kind = row.get('kind')
        if position == 0:
            header = row
            binding.require(kind == 'header' and row['schema'] == recovery_receipts.ARCHIVE_SCHEMA,
                            'unknown selected recovery archive header')
            _same(binding.digest(row['source_context']), entry['source_context_sha256'],
                  'selected recovery source context changed')
            _same(row['blocks'], [b['range'] for b in entry['blocks']], 'selected recovery block spans changed')
            binding.require(type(row['expected_models']) is int and row['expected_models'] == len(expected),
                            'selected recovery model count changed')
            predecessors, history = _recovery_history(entry, header, check)
            continue
        if kind in ('model_certificate', 'retained_certificate_reference'):
            ordinal = row['descriptor']['ordinal']
            binding.require(type(ordinal) is int and ordinal in expected and ordinal not in seen,
                            'foreign or duplicate selected recovery disposition')
            seen.add(ordinal)
            if kind == 'retained_certificate_reference':
                references[ordinal] = dict(row=row, source=_row_pin(pin, position, row, header['source_context']))
            elif ordinal in selected:
                physical(entry, row, expected[ordinal], header['source_context'],
                         [_row_pin(pin, position, row, header['source_context'])])
        elif kind == 'footer':
            footer = row
            binding.require(row['schema'] == recovery_receipts.FOOTER_SCHEMA and
                row['complete'] is True and row['proof_complete'] is True,
                'selected recovery lacks completed proof footer')
        else:
            binding.require(kind in ('block_report', 'block_certificate_checkpoint'), 'unknown selected recovery row')
    binding.require(header is not None and footer is not None and seen == set(expected),
                    'selected recovery missing dispositions/header/footer')
    archives.append(dict(entry_id=entry['entry_id'], archive=pin, consumed=reader.summary))
    raw_bytes, found = 0, set()
    # Read even ancestors without a selected leaf: their whole pinned bytes and
    # direct backward references authenticate this entry's chronological history.
    for number, (ancestor, authenticated) in enumerate(zip(predecessors, history)):
        dependency = ancestor['artifacts']['archive']
        context = ancestor['source_context']
        reader = ArchiveReader(dependency['path'], compressed_sha256=dependency['sha256'],
            compressed_bytes=dependency['size_bytes'], before=check,
            allow_incomplete=ancestor['archive_mode'] == 'interrupted-prefix',
            max_raw_bytes=recovery_receipts.HISTORY_BYTES-raw_bytes)
        old_header = old_footer = None
        leaf_seen, added = set(), {}
        for position, row in enumerate(reader):
            check()
            binding.require(type(row) is dict and old_footer is None, 'invalid recovery history row or data after footer')
            kind = row.get('kind')
            if position == 0:
                old_header = row
                schema = recovery_receipts.ARCHIVE_SCHEMA if number else 'hiroute-suffix-block-proof-archive-v1'
                binding.require(kind == 'header' and row['schema'] == schema, 'unknown recovery leaf archive header')
                _same(row['source_context'], context, 'recovery leaf source context changed')
                _same(row['blocks'], header['blocks'], 'recovery leaf block spans changed')
                binding.require(type(row['expected_models']) is int and row['expected_models'] == len(expected),
                                'recovery leaf model count changed')
                if number:
                    _same(row['history'], history[:number], 'recovery leaf chronological history changed')
                    _same(row['previous_archive'], history[number-1]['archive'], 'recovery leaf previous archive changed')
                continue
            if kind in ('model_certificate', 'retained_certificate_reference', 'unresolved_model', 'unsubmitted_model'):
                ordinal = row['descriptor']['ordinal']
                binding.require(type(ordinal) is int and ordinal in expected and ordinal not in leaf_seen,
                                'foreign or duplicate recovery leaf disposition')
                leaf_seen.add(ordinal)
                if kind == 'retained_certificate_reference':
                    binding.require(number > 0 and ordinal in leaves, 'missing direct full recovery ancestor')
                    _same(row, recovery_receipts._reference(leaves[ordinal]), 'recursive or changed recovery leaf reference')
                else:
                    binding.require(ordinal not in leaves, 'recovery candidate aliases an earlier full leaf')
                if kind == 'model_certificate':
                    added[ordinal] = recovery_receipts._leaf(row, recovery_receipts._pin(dependency), context, position)
                    if ordinal in selected and ordinal in references:
                        ref = references[ordinal]
                        _same(ref['row'], recovery_receipts._reference(added[ordinal]),
                              'selected recovery reference differs from direct full leaf')
                        physical(entry, row, expected[ordinal], context,
                                 [ref['source'], _row_pin(dependency, position, row, context)])
                        found.add(ordinal)
            elif kind == 'footer':
                old_footer = row
                schema = recovery_receipts.FOOTER_SCHEMA if number else 'hiroute-suffix-block-proof-footer-v1'
                # A failed runtime can have a complete proof footer. Its runtime
                # status was independently admitted, never inferred from here.
                binding.require(row['schema'] == schema and type(row['complete']) is bool,
                                'recovery history footer grammar changed')
            else:
                binding.require(kind in ('block_report', 'block_certificate_checkpoint'), 'unknown recovery history row')
        encoding = reader.summary
        binding.require(old_header is not None and (not encoding['gzip_eof'] or old_footer is not None) and
            (old_footer is None or encoding['trailing_partial_row_bytes'] == 0), 'incomplete recovery leaf grammar')
        for key in ('gzip_eof', 'trailing_partial_row_bytes'):
            _same(encoding[key], authenticated[key], 'recovery leaf differs from admitted encoding policy')
        raw_bytes += encoding['uncompressed_bytes']
        leaves.update(added)
        archives.append(dict(entry_id=entry['entry_id'], archive=dependency, consumed=encoding))
    binding.require(set(references) == set(leaves), 'selected recovery retained ancestor coverage changed')
    for ordinal, ref in references.items():
        check()
        _same(ref['row'], recovery_receipts._reference(leaves[ordinal]),
              'selected recovery reference differs from direct full ancestor')
    binding.require(found == selected & set(references), 'selected recovery full leaf coverage incomplete')


def replay_selected_witnesses(admitted, registry, requested, emit, *, deadline, before=lambda: None):
    """Stream fresh physical receipts; return only bounded coverage/hash references.

    requested maps integer logical ordinals to {descriptor, result}. emit takes
    one detached receipt dictionary. Empty requests are allowed. Each exact
    descriptor/check/lift call has at most 30 seconds, without nested timers.
    Completed ordinary windows, the fixed seed and admitted generic recovery
    histories are supported. Retained references resolve directly to full rows.
    No optimizer, full block replay, full-query acceptance or G8 closure occurs.
    """
    check = receipts._guard(deadline, before)
    binding.require(type(admitted) is AdmittedSuffixPopulation and type(admitted.ctx) is CheckedBundle,
                    'genuine admitted population and fresh checked family required')
    binding.require(admitted.population.ctx is admitted.ctx, 'admitted physical family context changed')
    binding.require(type(registry) is receipts.CheckedRegistry and callable(emit),
                    'cold checked registry and receipt callback required')
    ctx = admitted.ctx
    _, commitment = receipts._population(admitted)
    metadata = registry.metadata()
    _same(metadata['population'], commitment, 'witness registry population differs from admission')
    binding.require(admitted.ctx.summary['bundle_sha256'] == commitment['source_bundle_sha256'],
                    'fresh physical family differs from admitted source')
    registry.block_reports()  # A scheduling-only snapshot cannot supply authority.
    requests, request_bytes = _requests(admitted, requested, deadline, check)
    request_rows_sha = binding.digest([dict(model_ordinal=ordinal, **requests[ordinal])
                                       for ordinal in sorted(requests)])
    check()
    registry_sha, population_sha = binding.digest(metadata), binding.digest(commitment)
    entries = {entry['entry_id']: entry for entry in metadata['entries']}
    groups = {}
    for ordinal in requests:
        matches = [block for block in metadata['blocks'] if block['range']['start'] <= ordinal < block['range']['end']]
        binding.require(len(matches) == 1, 'selected ordinal missing or duplicated in registry')
        entry_id = matches[0]['entry_id']
        binding.require(entry_id in entries, 'selected source entry missing from registry')
        groups.setdefault(entry_id, set()).add(ordinal)
    completed, archives = {}, []

    def physical(entry, row, block_id, context, ancestry):
        check()
        ordinal = row['descriptor']['ordinal']
        binding.require(ordinal not in completed, 'duplicate selected physical receipt')
        request = requests[ordinal]
        with calibration.verification_deadline(float(min(deadline, time.monotonic() + PHYSICAL_SECONDS))):
            receipts._check_record(row, request['descriptor'], block_id, context)
            record = row['record']
            bound = dict(model_ordinal=ordinal, block_id=block_id,
                         model_sha256=binding.digest(record['model']),
                         logical_identity=request['descriptor']['logical_identity'])
            checked = calibration.verify_model(ctx, bound, record)
            _same(checked['result'], request['result'], 'physical result differs from requested query result')
            binding.require(checked['physical_witness_verified'] is True,
                            'selected record lacks a freshly checked physical witness')
        check()
        provenance = dict(registry_sha256=registry_sha, population_sha256=population_sha,
            physical_request_rows_sha256=request_rows_sha,
            entry_id=entry['entry_id'], module=entry['module'], source_commit=entry['source_commit'],
            source_sha256=entry['source_sha256'], dependencies_sha256=binding.digest(entry['dependencies']),
            source_rows=ancestry)
        receipt = dict(schema='hiroute-selected-query-model-witness-v1', provisional=True, model_ordinal=ordinal,
            descriptor=request['descriptor'], model_sha256=bound['model_sha256'],
            record_sha256=binding.digest(record), result=checked['result'], provenance=provenance,
            physical_receipt=checked, **receipts.FALSE_AUTHORITY)
        compact = dict(model_ordinal=ordinal, descriptor_sha256=binding.digest(request['descriptor']),
            model_sha256=receipt['model_sha256'], record_sha256=receipt['record_sha256'],
            result_sha256=binding.digest(checked['result']), provenance_sha256=binding.digest(provenance),
            receipt_sha256=binding.digest(receipt))
        check()
        emit(receipts._owned(receipt))
        check()
        completed[ordinal] = compact

    for entry_id in sorted(groups):
        selected = groups[entry_id]
        check()
        entry = entries[entry_id]
        if entry['module'] == recovery_receipts.MODULE:
            _replay_recovery(entry, selected, physical, check, archives)
            continue
        binding.require(entry['module'] in ('suffix_window', 'block_resume'), 'unknown source archive grammar')
        seed = entry['module'] == 'block_resume'
        if seed:
            binding.require(entry['source_commit'] == receipts.SEED_COMMIT and
                            entry['source_sha256'] == receipts.SEED_SOURCE, 'unknown seed continuation source')
        expected = _entry_blocks(entry)
        pin = entry['proof']
        reader = ArchiveReader(pin['path'], compressed_sha256=pin['sha256'],
                               compressed_bytes=pin['size_bytes'], before=check)
        seen, references, header, footer = set(), {}, None, None
        suffix = 'resume' if seed else 'proof'
        for position, row in enumerate(reader):
            check()
            binding.require(type(row) is dict and footer is None, 'invalid row or data after archive footer')
            kind = row.get('kind')
            if position == 0:
                header = row
                binding.require(kind == 'header' and row['schema'] == 'hiroute-suffix-block-'+suffix+'-archive-v1',
                                'unknown selected archive header')
                binding.require(binding.digest(row['source_context']) == entry['source_context_sha256'],
                                'selected archive source context changed')
                _same(row['blocks'], [b['range'] for b in entry['blocks']], 'selected archive block spans changed')
                binding.require(type(row['expected_models']) is int and row['expected_models'] == len(expected),
                                'selected archive model count changed')
                continue
            if kind in ('model_certificate', 'retained_certificate_reference'):
                ordinal = row['descriptor']['ordinal']
                binding.require(type(ordinal) is int and ordinal in expected and ordinal not in seen,
                                'foreign or duplicate selected source disposition')
                seen.add(ordinal)
                if kind == 'retained_certificate_reference':
                    dependency = _reference(entry, row, header['source_context'], pin)
                if ordinal not in selected:
                    continue
                _same(row['descriptor'], requests[ordinal]['descriptor'], 'selected source descriptor changed')
                source = _row_pin(pin, position, row, header['source_context'])
                if kind == 'model_certificate':
                    physical(entry, row, expected[ordinal], header['source_context'], [source])
                else:
                    references[ordinal] = dict(row=row, dependency=dependency, source=source)
            elif kind == 'footer':
                footer = row
                binding.require(row['schema'] == 'hiroute-suffix-block-'+suffix+'-footer-v1' and
                                row['complete'] is True, 'selected archive lacks a completed footer')
            else:
                binding.require(kind in ('block_report', 'block_certificate_checkpoint'), 'unknown selected archive row')
        binding.require(header is not None and footer is not None and seen == set(expected),
                        'selected archive has missing model dispositions/header/footer')
        archives.append(dict(entry_id=entry_id, archive=pin, consumed=reader.summary))
        # The current seed has one historical archive and full leaf records.
        # Group its selected references so each pinned archive is read once.
        dependencies = {}
        aliases = {}
        for ordinal, ref in references.items():
            dependency, target = ref['dependency'], ref['row']['provenance']
            key = (dependency['path'], dependency['sha256'])
            alias = (dependency['sha256'], target['archive_row_index'])
            binding.require(alias not in aliases, 'conflicting selected reference aliases')
            aliases[alias] = ordinal
            dependencies.setdefault(key, {})[ordinal] = ref
        for refs in dependencies.values():
            dependency = next(iter(refs.values()))['dependency']
            reader = ArchiveReader(dependency['path'], compressed_sha256=dependency['sha256'],
                                   compressed_bytes=dependency['size_bytes'], before=check)
            found, leaf_seen, old_header, old_footer = set(), set(), None, None
            indices = {ref['row']['provenance']['archive_row_index']: ordinal for ordinal, ref in refs.items()}
            old_context = header['source_context']['previous_source_context']
            for position, row in enumerate(reader):
                check()
                binding.require(type(row) is dict and old_footer is None, 'invalid historical row or data after footer')
                kind = row.get('kind')
                if position == 0:
                    old_header = row
                    binding.require(kind == 'header' and row['schema'] == 'hiroute-suffix-block-proof-archive-v1',
                                    'unknown retained leaf archive grammar')
                    _same(row['source_context'], old_context, 'retained archive source context changed')
                    _same(row['blocks'], header['blocks'], 'retained archive block spans changed')
                    binding.require(row['expected_models'] == len(expected), 'retained archive model count changed')
                    continue
                binding.require(kind in ('model_certificate', 'unresolved_model', 'block_certificate_checkpoint',
                                         'block_report', 'footer'), 'unknown or recursive retained leaf grammar')
                if kind in ('model_certificate', 'unresolved_model'):
                    ordinal = row['descriptor']['ordinal']
                    binding.require(type(ordinal) is int and ordinal in expected and ordinal not in leaf_seen,
                                    'foreign or duplicate retained leaf disposition')
                    leaf_seen.add(ordinal)
                    if ordinal in refs:
                        binding.require(position == refs[ordinal]['row']['provenance']['archive_row_index'],
                                        'retained selected ordinal moved to another row')
                if position in indices:
                    ordinal = indices[position]
                    ref = refs[ordinal]
                    target = ref['row']['provenance']
                    leaf = _row_pin(dependency, position, row, old_context)
                    binding.require(kind == 'model_certificate' and leaf['archive_row_sha256'] == target['archive_row_sha256'],
                                    'retained leaf row hash/type changed')
                    _same(row['descriptor'], requests[ordinal]['descriptor'], 'retained leaf descriptor changed')
                    _same(row['verification'], ref['row']['verification'], 'retained verification alias changed')
                    physical(entry, row, expected[ordinal], old_context, [ref['source'], leaf])
                    found.add(ordinal)
                if kind == 'footer':
                    old_footer = row
                    binding.require(row['schema'] == 'hiroute-suffix-block-proof-footer-v1' and row['complete'] is False,
                                    'retained history completion/grammar changed')
            binding.require(old_header is not None and old_footer is not None and found == set(refs),
                            'missing retained leaf row/header/footer')
            archives.append(dict(entry_id=entry_id, archive=dependency, consumed=reader.summary))
    check()
    binding.require(set(completed) == set(requests), 'selected physical replay coverage incomplete')
    result = receipts._owned(dict(schema='hiroute-selected-query-witness-coverage-v1',
        registry_sha256=registry_sha, population_sha256=population_sha,
        physical_request_rows_sha256=request_rows_sha, physical_request_bytes=request_bytes,
        selected_models=len(requests),
        witnesses=[completed[k] for k in sorted(completed)], archives=archives,
        selected_replay_complete=True, **receipts.FALSE_AUTHORITY))
    check()
    return result
