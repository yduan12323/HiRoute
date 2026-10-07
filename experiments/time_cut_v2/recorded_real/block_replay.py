"""Cold exact replay of retained block proofs, without an optimizer.

A successful prior-run flag is never sufficient. The caller supplies a fresh
genuine CheckedBundle, independently admitted block descriptors/source context,
and an authenticated archive byte pin. Every retained certificate is checked
again. A sync-flushed interrupted prefix can contribute only complete checked
blocks; it never becomes a successful historical run.
"""
from dataclasses import dataclass, field
import hashlib
import json
import math
import time

from validation.family5.checker import require, wire_equal
from validation.suffix5.block_certificates import BlockCertificates
from validation.suffix5.calibration import verification_deadline, verify_model
from validation.suffix5.independent_convex_model import exact_json, build_model, api
from . import plan as binding
from .lp_stream_jobs import LPStreamJob


def same(actual, expected, message):
    require(wire_equal(actual, expected), message)


def transport_complete(pool, expected):
    require(type(pool) is dict, 'archived transport summary required')
    return (pool.get('status') == 'complete' and
            pool.get('input_exhausted') is True and
            pool.get('all_submitted_accounted') is True and
            pool.get('all_processes_reaped') is True and
            type(pool.get('submitted_count')) is int and pool['submitted_count'] == expected and
            type(pool.get('terminal_count')) is int and pool['terminal_count'] == expected and
            type(pool.get('protocol_error_count')) is int and pool['protocol_error_count'] == 0 and
            pool.get('collector_error', 'missing') is None)


@dataclass(frozen=True)
class ReplayedBlocks:
    """Detached cold-check receipt, distinct from a historical run acceptance."""
    _summary: bytes
    _certificates: tuple[bytes, ...] = field(repr=False)

    def summary(self):
        return json.loads(self._summary)

    def certificates(self, *, block_id=None):
        """Yield detached full certificates, including good rows in incomplete blocks.

        Original ordinals/descriptors remain attached. A later restart must
        recheck them against its fresh family and admitted population before
        joining them with new certificates; this receipt is not that join.
        """
        require(block_id is None or (type(block_id) is int and block_id >= 0),
                'original block ID required')
        for raw in self._certificates:
            row = json.loads(raw)
            if block_id is None or row['verification']['block_id'] == block_id:
                yield row


@api
def replay_blocks(reader, ctx, blocks, source_context, *, deadline, before=lambda: None):
    """Return nothing authoritative until the entire pinned stream is consumed.

The reader enforces canonical JSONL, gzip/incomplete-prefix policy and byte
caps. A malformed complete record anywhere invalidates this call, even if an
earlier block had a checkpoint. Resource exceptions propagate to the caller.
"""
    from .archive_reader import ArchiveReader
    require(type(reader) is ArchiveReader, 'bounded pinned archive reader required')
    require(type(deadline) is float and math.isfinite(deadline), 'finite cold replay deadline required')
    require(type(blocks) is list and 0 < len(blocks) <= 4,
            'cold reader currently bounded to four 256-model blocks')
    require(type(source_context) is dict, 'independently admitted source context required')
    exact_json(source_context)
    exact_json(blocks)
    # The independently supplied declarations remain authoritative if a
    # progress callback or another caller mutates its own copies during I/O.
    source_context = json.loads(binding.canonical(source_context))
    blocks = json.loads(binding.canonical(blocks))
    certifier = BlockCertificates(ctx, blocks)
    expected = {row['ordinal']: block['range']['block_id']
                for block in blocks for row in block['descriptors']}
    block_ids = [block['range']['block_id'] for block in blocks]
    require(len(expected) <= 1024 and len(blocks) <= 4,
            'cold reader currently bounded to four 256-model blocks')
    header = dict(kind='header', schema='hiroute-suffix-block-proof-archive-v1',
                  source_context=source_context, expected_models=len(expected),
                  blocks=[block['range'] for block in blocks], certificate_reuse_enabled=False)
    seen = set()
    checkpoints = set()
    reports = []
    footer = None
    pending_checkpoint = None
    started = False
    report_phase = False
    accepted = 0
    certificates = {}
    certificate_refs = {}

    def guard():
        before()
        require(time.monotonic() < deadline, 'cold block replay absolute deadline')

    def validate_job(job, descriptor, identity):
        ordinal = descriptor['ordinal']
        require(job.model_ordinal == ordinal and job.block_id == expected[ordinal],
                'archived candidate block/model changed')
        same(job.source_context, source_context, 'archived candidate source changed')
        require(type(identity) is dict, 'archived candidate identity required')
        same(identity, job.header(identity.get('generation')), 'archived response identity changed')

    for row_index, row in enumerate(reader.iter_rows(before=guard)):
        guard()
        require(type(row) is dict and type(row.get('kind')) is str, 'typed archive record required')
        if not started:
            same(row, header, 'archive header differs from admitted population/source')
            started = True
            continue
        require(footer is None, 'record after archive footer')
        kind = row['kind']
        if pending_checkpoint is not None:
            require(kind == 'block_certificate_checkpoint', 'missing immediate complete-block checkpoint')
        if kind in ('model_certificate', 'unresolved_model'):
            require(not report_phase, 'model record after block reporting began')
            descriptor = row['descriptor']
            require(type(descriptor) is dict and type(descriptor.get('ordinal')) is int,
                    'typed original model descriptor required')
            ordinal = descriptor['ordinal']
            require(ordinal in expected and ordinal not in seen, 'foreign or duplicate archived model')
            same(descriptor, certifier.descriptor(ordinal), 'archived logical model descriptor changed')
            if kind == 'model_certificate':
                require(set(row) == {'kind', 'descriptor', 'record', 'verification', 'candidate_identity',
                                    'candidate_metrics', 'timings', 'stdout_sha256', 'stderr_base64'},
                        'model certificate record fields')
                record = row['record']
                job = LPStreamJob(source_context, expected[ordinal], ordinal,
                                  binding.digest(record['model']), record['model'])
                validate_job(job, descriptor, row['candidate_identity'])
                with verification_deadline(float(min(deadline, time.monotonic() + 30))):
                    verified = certifier.check(ordinal, record)
                same(row['verification'], verified, 'archived verification differs from fresh exact check')
                raw = binding.canonical(row)
                certificates[ordinal] = raw
                certificate_refs[ordinal] = dict(
                    model_ordinal=ordinal, block_id=expected[ordinal], archive_row_index=row_index,
                    archive_row_sha256=hashlib.sha256(raw + b'\n').hexdigest(),
                    current_verification=verified)
                accepted += 1
            else:
                require(set(row) == {'kind', 'descriptor', 'candidate', 'timings'}, 'unresolved record fields')
                candidate = row['candidate']
                require(type(candidate) is dict, 'unresolved candidate record required')
                job = LPStreamJob.from_dict(candidate['job'])
                validate_job(job, descriptor, candidate['response_identity'])
                identity = descriptor['logical_identity']
                with verification_deadline(float(min(deadline, time.monotonic() + 30))):
                    reconstructed = build_model(ctx, identity['family_id'], identity['word'], identity['arrival_bands'])
                    same(job.model, reconstructed, 'unresolved candidate differs from admitted model')
                # Its transcript remains diagnostic. An unresolved disposition
                # cannot acquire a certificate merely because the next run can
                # parse its model or because another model succeeds.
                certifier.unresolved(ordinal, 'retained unresolved candidate')
            seen.add(ordinal)
            block_id = expected[ordinal]
            if certifier.summary(block_id)['complete_certificates']:
                pending_checkpoint = block_id
        elif kind == 'block_certificate_checkpoint':
            require(not report_phase and pending_checkpoint is not None, 'unexpected block checkpoint')
            require(set(row) == {'kind', 'report', 'transport_finalized', 'acceptance',
                                'cold_certificate_replay_required'}, 'checkpoint fields')
            require(row['transport_finalized'] is False and row['acceptance'] is False and
                    row['cold_certificate_replay_required'] is True, 'checkpoint authority changed')
            same(row['report'], certifier.summary(pending_checkpoint), 'checkpoint differs from exact certificates')
            checkpoints.add(pending_checkpoint)
            pending_checkpoint = None
        elif kind == 'block_report':
            report_phase = True
            require(set(row) == {'kind', 'report', 'winner_witness'}, 'block report fields')
            require(len(reports) < len(block_ids), 'extra block report')
            number = block_ids[len(reports)]
            supplied = row['report']
            require(type(supplied) is dict and type(supplied.get('physical_witness_verified')) is bool and
                    type(supplied.get('complete')) is bool, 'typed block report required')
            core = certifier.summary(number)
            require(set(core) | {'complete'} <= set(supplied), 'missing block report fields')
            for key, value in core.items():
                if key != 'physical_witness_verified':
                    same(supplied.get(key), value, 'block report disagrees with cold certificate coverage: ' + key)
            require(set(supplied) <= set(core) | {'complete', 'witness_failure', 'physical_witness_not_required'},
                    'unexpected block report fields')
            if supplied.get('physical_witness_not_required') is not None:
                require(supplied['physical_witness_not_required'] is True and
                        core['complete_certificates'] and core['aggregate']['result']['status'] == 'empty_restricted_family',
                        'physical witness exclusion lacks complete empty aggregate')
            require(not supplied['complete'] or (core['complete_certificates'] and
                    (supplied['physical_witness_verified'] or supplied.get('physical_witness_not_required') is True)),
                    'false block completion claim')
            require(not supplied['physical_witness_verified'] or core['complete_certificates'],
                    'physical witness claimed for incomplete block')
            require(not supplied['physical_witness_verified'] or
                    core['aggregate']['result']['status'] != 'empty_restricted_family',
                    'physical witness claimed for empty block')
            require((row['winner_witness'] is not None) == supplied['physical_witness_verified'],
                    'physical receipt presence changed')
            reports.append(row)
        elif kind == 'footer':
            require(set(row) == {'kind', 'schema', 'complete', 'verified_models', 'expected_models',
                                'transport', 'blocks', 'query_optimum_certified', 'full_population_complete',
                                'literal_G8_closed'}, 'footer fields')
            require(row['schema'] == 'hiroute-suffix-block-proof-footer-v1' and
                    type(row['verified_models']) is int and row['verified_models'] == accepted and
                    type(row['expected_models']) is int and row['expected_models'] == len(expected),
                    'footer model counts changed')
            require(len(reports) == len(blocks), 'footer missing original block reports')
            same(row['blocks'], [r['report'] for r in reports], 'footer differs from original block reports')
            transported = transport_complete(row['transport'], len(expected))
            require(not transported or seen == set(expected), 'gap in completed transport archive')
            require(all(r['report']['complete'] == (transported and r['report']['complete_certificates'] and
                        (r['report']['physical_witness_verified'] or
                         r['report'].get('physical_witness_not_required') is True)) for r in reports),
                    'block completion disagrees with archived transport')
            complete = (transported and accepted == len(expected)
                        and all(r['report']['complete'] for r in reports))
            require(type(row['complete']) is bool and row['complete'] == complete, 'false archive completion claim')
            require(all(row[k] is False for k in ('query_optimum_certified', 'full_population_complete', 'literal_G8_closed')),
                    'archive has unsupported population authority')
            footer = row
        else:
            raise ValueError('unknown archive record kind')

    # The reader authenticates the actual compressed snapshot only at full
    # exhaustion. No result or reusable block escapes before this boundary.
    guard()
    pin = reader.summary
    require(type(pin) is dict and started, 'empty or unfinished archive reader')
    require(not pin['gzip_eof'] or (footer is not None and pending_checkpoint is None),
            'complete gzip archive lacks its complete record grammar')
    require(footer is None or pin['trailing_partial_row_bytes'] == 0,
            'partial record after archive footer')
    reusable = []
    for number in block_ids:
        guard()
        if number not in checkpoints:
            continue
        report = certifier.summary(number)
        winner = certifier.winner(number)
        witness = None
        if winner is not None:
            identity = dict(block_id=number, model_ordinal=winner['model_ordinal'],
                            model_sha256=binding.digest(winner['record']['model']),
                            logical_identity=winner['descriptor']['logical_identity'])
            with verification_deadline(float(min(deadline, time.monotonic() + 30))):
                witness = verify_model(ctx, identity, winner['record'])
            # Preserve old physical receipts as consistency checks, including
            # arrival bands and family ancestry, rather than trusting their flag.
            prior = next((r for r in reports if r['report']['range']['block_id'] == number), None)
            if prior is not None and prior['winner_witness'] is not None:
                old = dict(prior['winner_witness']); new = dict(witness)
                old.pop('timings', None); new.pop('timings', None)
                same(old, new, 'retained physical witness differs from fresh exact replay')
        report['physical_witness_verified'] = witness is not None
        report['physical_witness_not_required'] = witness is None
        report['complete'] = True
        reusable.append(dict(report=report, winner_witness=witness))
    guard()
    result = dict(schema='hiroute-cold-replayed-blocks-v1', archive=pin,
                  source_context=source_context, expected_models=len(expected), checked_models=accepted,
                  observed_models=len(seen), reusable_block_ids=[r['report']['range']['block_id'] for r in reusable],
                  certified_ordinals=sorted(certificates),
                  certificate_refs=[certificate_refs[i] for i in sorted(certificates)],
                  coverage=[certifier.summary(number) for number in block_ids],
                  blocks=reusable, historical_footer_present=footer is not None,
                  historical_archive_finalized=pin['gzip_eof'] and footer is not None,
                  historical_attempt_claimed_complete=footer is not None and footer['complete'],
                  historical_runtime_revalidated=False, query_optimum_certified=False,
                  full_population_complete=False, literal_G8_closed=False)
    return ReplayedBlocks(binding.canonical(result), tuple(certificates[i] for i in sorted(certificates)))
