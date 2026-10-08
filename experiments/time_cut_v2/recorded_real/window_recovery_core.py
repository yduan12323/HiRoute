"""Cold, source-bound recovery of one independently admitted original window.

History is supplied oldest first; there is no archive discovery or successful
historical-run admission here. Only authenticated full proof rows become leaf
references. A live session owns those bytes and rechecks them at the exact join.
The controller owns source/input admission, the process guard and publication.
"""
import base64
from dataclasses import dataclass, field
import hashlib
import json
import math
import time
from weakref import WeakKeyDictionary

from . import block_archive, block_replay, plan as binding
from .archive_reader import ArchiveReader
from .lp_stream_jobs import LPStreamJob
from validation.suffix5.block_certificates import BlockCertificates
from validation.suffix5 import calibration
from validation.suffix5.independent_convex_model import build_model, exact_json

MAX_BLOCKS = 32
MAX_MODELS = 8192
MAX_INPUT_BYTES = 128 * 1024**2
MAX_HISTORY_BYTES = 512 * 1024**2
MAX_SECONDS = 900
ARCHIVE_SCHEMA = 'hiroute-suffix-window-recovery-archive-v1'
FOOTER_SCHEMA = 'hiroute-suffix-window-recovery-footer-v1'
FALSE_AUTHORITY = dict(query_optimum_certified=False, full_population_complete=False,
                       literal_G8_closed=False)
CERTIFICATE_FIELDS = {'kind', 'descriptor', 'record', 'verification', 'candidate_identity',
                      'candidate_metrics', 'timings', 'stdout_sha256', 'stderr_base64'}
_LIVE = WeakKeyDictionary()
_KEY = object()


def _copy(value):
    return json.loads(binding.canonical(value))


def _pin(summary):
    return dict(sha256=summary['compressed_sha256'], size_bytes=summary['compressed_bytes'])


def _guard(state):
    state.before()
    binding.require(time.monotonic() < state.deadline, 'window recovery absolute deadline')


def _limit(state):
    _guard(state)
    return float(min(state.deadline, time.monotonic() + 30))


@dataclass(frozen=True)
class ArchiveInput:
    """Reader pins and source context must be admitted independently by caller."""
    reader: ArchiveReader
    source_context: dict


@dataclass
class _State:
    ctx: object
    blocks: list
    deadline: float
    before: object
    history: list
    leaves: dict
    current_source: bytes | None = None
    records_started: bool = False
    jobs_started: bool = False
    expected: dict = field(init=False)

    def __post_init__(self):
        self.expected = {row['ordinal']: block['range']['block_id']
                         for block in self.blocks for row in block['descriptors']}

    @property
    def candidates(self):
        return sorted(set(self.expected) - self.leaves.keys())


class RecoverySession:
    """Non-serializable live cold admission; public flags cannot forge it."""
    __slots__ = ('__weakref__',)

    def __init__(self, key=None, state=None):
        binding.require(key is _KEY and type(state) is _State, 'live cold recovery admission required')
        _LIVE[self] = state

    def summary(self):
        state = _state(self)
        expected = state.expected
        return _copy(dict(schema='hiroute-cold-window-recovery-v1',
            population_sha256=binding.digest(state.blocks), expected_models=len(expected),
            retained_verified_models=len(state.leaves), candidate_models=len(state.candidates),
            candidate_ordinals=state.candidates, certified_ordinals=sorted(state.leaves),
            history=state.history, previous_archive=state.history[-1]['archive'],
            certificate_refs=[json.loads(state.leaves[i][1]) for i in sorted(state.leaves)],
            coverage=[dict(range=block['range'],
                verified_models=sum(row['ordinal'] in state.leaves for row in block['descriptors']),
                candidate_ordinals=[row['ordinal'] for row in block['descriptors']
                                    if row['ordinal'] not in state.leaves]) for block in state.blocks],
            historical_runtime_revalidated=False, **FALSE_AUTHORITY))

    def candidate_jobs(self, source_context):
        """Filter first; retained IDs never enter either candidate model builder."""
        state = _state(self)
        source = _bind_source(state, source_context)
        binding.require(not state.jobs_started and not state.records_started,
                        'candidate job input is single-use and precedes recovery records')
        state.jobs_started = True
        return _candidate_jobs(state, source)

    def records(self, source_context, outcomes=None):
        state = _state(self)
        source = _bind_source(state, source_context)
        binding.require(not state.records_started, 'recovery exact join is single-use')
        binding.require((outcomes is None) == (not state.candidates),
                        'exact-only recovery requires no candidate transport')
        state.records_started = True
        return _records(state, source, outcomes)


def _state(session):
    binding.require(type(session) is RecoverySession and session in _LIVE,
                    'live cold recovery session required')
    return _LIVE[session]


def _context(source):
    binding.require(type(source) is dict, 'independently admitted source context required')
    exact_json(source)
    raw = binding.canonical(source)
    binding.require(len(raw) <= 16384, 'source context byte cap')
    return json.loads(raw)


def _bind_source(state, source):
    _guard(state)
    source = _context(source)
    raw = binding.canonical(source)
    binding.require(state.current_source is None or state.current_source == raw,
                    'current recovery source context changed')
    state.current_source = raw
    return source


def _header(state, source):
    return dict(kind='header', schema=ARCHIVE_SCHEMA, source_context=source,
        population_sha256=binding.digest(state.blocks), expected_models=len(state.expected),
        blocks=[block['range'] for block in state.blocks],
        retained_models=len(state.leaves), candidate_models=len(state.candidates),
        candidate_ordinals=state.candidates, history=state.history,
        previous_archive=state.history[-1]['archive'],
        recovery_mode='candidates' if state.candidates else 'exact-only',
        historical_runtime_revalidated=False, **FALSE_AUTHORITY)


def _leaf(row, archive, source, index):
    raw = binding.canonical(row)
    provenance = dict(archive=archive, archive_row_index=index,
        archive_row_sha256=hashlib.sha256(raw + b'\n').hexdigest(), source_context=source)
    return raw, binding.canonical(provenance)


def _check_full(state, certifier, row, source):
    binding.require(type(row) is dict and set(row) == CERTIFICATE_FIELDS and
                    row['kind'] == 'model_certificate', 'full certificate record fields')
    ordinal = row['descriptor']['ordinal']
    block_replay.same(row['descriptor'], certifier.descriptor(ordinal), 'retained descriptor changed')
    record = row['record']
    job = LPStreamJob(source, state.expected[ordinal], ordinal,
                      binding.digest(record['model']), record['model'])
    block_replay.same(row['candidate_identity'], job.header(row['candidate_identity']['generation']),
                      'full certificate source or candidate identity changed')
    with calibration.verification_deadline(_limit(state)):
        verified = certifier.check(ordinal, record)
    _guard(state)
    block_replay.same(verified, row['verification'], 'full certificate exact verification changed')
    return verified


def _job(state, certifier, outcome, source, candidates, seen):
    binding.require(type(outcome) is dict, 'candidate outcome required')
    job = LPStreamJob.from_dict(outcome['job'])
    ordinal = job.model_ordinal
    binding.require(ordinal in candidates and ordinal not in seen and
                    job.block_id == state.expected[ordinal], 'foreign or duplicate recovery candidate')
    block_replay.same(job.source_context, source, 'recovery candidate source changed')
    block_replay.same(outcome['response_identity'], job.header(outcome['generation']),
                      'recovery response identity changed')
    # Unresolved is a transport disposition, never a license to change models.
    if outcome['status'] == 'unresolved':
        identity = certifier.descriptor(ordinal)['logical_identity']
        with calibration.verification_deadline(_limit(state)):
            model = build_model(state.ctx, identity['family_id'], identity['word'], identity['arrival_bands'])
            block_replay.same(job.model, model, 'unresolved candidate model changed')
    else:
        binding.require(outcome['status'] == 'complete', 'unknown recovery candidate status')
    return job


def _checkpoint(certifier, number):
    return dict(kind='block_certificate_checkpoint', report=certifier.summary(number),
                transport_finalized=False, acceptance=False, cold_certificate_replay_required=True)


def _witness(state, certifier, number):
    winner = certifier.winner(number)
    if winner is None:
        return None
    with calibration.verification_deadline(_limit(state)):
        value = calibration.verify_model(state.ctx, dict(block_id=number,
            model_ordinal=winner['model_ordinal'], model_sha256=binding.digest(winner['record']['model']),
            logical_identity=winner['descriptor']['logical_identity']), winner['record'])
    _guard(state)
    return value


def _candidate_jobs(state, source):
    from .block_pilot import model_jobs
    candidates = set(state.candidates)
    selected = [dict(range=block['range'], descriptors=[row for row in block['descriptors']
                 if row['ordinal'] in candidates]) for block in state.blocks]
    selected = [block for block in selected if block['descriptors']]
    used = 0
    for job in model_jobs(state.ctx, dict(blocks=selected), source, lambda: _guard(state)):
        _guard(state)
        used += len(job.input_bytes)
        binding.require(used <= MAX_INPUT_BYTES, 'cumulative recovery candidate input cap')
        yield job


def _records(state, source, outcomes):
    _guard(state)
    certifier = BlockCertificates(state.ctx, state.blocks)
    candidates = set(state.candidates)
    yield _header(state, source)
    for ordinal in sorted(state.leaves):
        _guard(state)
        raw, provenance_raw = state.leaves[ordinal]
        row, provenance = json.loads(raw), json.loads(provenance_raw)
        binding.require(provenance['archive_row_sha256'] == hashlib.sha256(raw+b'\n').hexdigest(),
                        'retained leaf row hash changed')
        verified = _check_full(state, certifier, row, provenance['source_context'])
        yield dict(kind='retained_certificate_reference', descriptor=row['descriptor'],
                   verification=verified, provenance=provenance)
        if certifier.summary(state.expected[ordinal])['complete_certificates']:
            yield _checkpoint(certifier, state.expected[ordinal])
    seen, fresh, input_bytes = set(), 0, 0
    for outcome in (() if outcomes is None else outcomes):
        _guard(state)
        job = _job(state, certifier, outcome, source, candidates, seen)
        ordinal = job.model_ordinal
        input_bytes += len(job.input_bytes)
        binding.require(input_bytes <= MAX_INPUT_BYTES, 'cumulative recovery candidate input cap')
        started, cpu = time.monotonic(), time.process_time()
        descriptor = certifier.descriptor(ordinal)
        if outcome['status'] == 'unresolved':
            certifier.unresolved(ordinal, 'new unresolved candidate')
            row = dict(kind='unresolved_model', descriptor=descriptor, candidate=outcome)
        else:
            record = dict(model=job.model, stages=outcome['stages'], result=outcome['result'])
            # Invalid purported certificates fail closed. They are never rewritten
            # as a retry disposition or accepted via a stale checker return.
            with calibration.verification_deadline(_limit(state)):
                verified = certifier.check(ordinal, record)
            _guard(state)
            row = dict(kind='model_certificate', descriptor=descriptor, record=record,
                verification=verified, candidate_identity=outcome['response_identity'],
                candidate_metrics=outcome['metrics'],
                stdout_sha256=hashlib.sha256(base64.b64decode(outcome['stdout_base64'], validate=True)).hexdigest(),
                stderr_base64=outcome['stderr_base64'])
            fresh += 1
        row['timings'] = dict(exact_check_wall_seconds=time.monotonic()-started,
                              exact_check_cpu_seconds=time.process_time()-cpu)
        seen.add(ordinal)
        yield row
        if certifier.summary(job.block_id)['complete_certificates']:
            yield _checkpoint(certifier, job.block_id)
    _guard(state)
    pool = None if outcomes is None else _copy(outcomes.summary)
    if pool is not None:
        _transport_bytes(pool, input_bytes)
    clean = outcomes is None or block_replay.transport_complete(pool, len(candidates))
    binding.require(not clean or seen == candidates, 'gap in completed recovery transport')
    for ordinal in sorted(candidates-seen):
        _guard(state)
        yield dict(kind='unsubmitted_model', descriptor=certifier.descriptor(ordinal),
                   reason='recovery transport provided no candidate disposition')
    reports = []
    for block in state.blocks:
        _guard(state)
        number = block['range']['block_id']
        report, witness = certifier.summary(number), None
        if clean and report['complete_certificates']:
            # A physical check failure invalidates this attempt. No inherited
            # flag or physical receipt substitutes for this fresh checked ctx.
            witness = _witness(state, certifier, number)
            report['physical_witness_verified'] = witness is not None
            if witness is None:
                report['physical_witness_not_required'] = True
        report['complete'] = clean and report['complete_certificates'] and (
            report['physical_witness_verified'] or report.get('physical_witness_not_required') is True)
        reports.append(report)
        yield dict(kind='block_report', report=report, winner_witness=witness)
    _guard(state)
    complete = clean and len(state.leaves)+fresh == len(state.expected) and all(r['complete'] for r in reports)
    yield _footer(state, complete, fresh, pool, reports)


def _footer(state, complete, fresh, pool, reports):
    return dict(kind='footer', schema=FOOTER_SCHEMA, complete=complete, proof_complete=complete,
        verified_models=len(state.leaves)+fresh, expected_models=len(state.expected),
        retained_verified_models=len(state.leaves), new_verified_models=fresh,
        candidate_models=len(state.candidates), transport=pool, blocks=reports,
        recovery_mode='candidates' if state.candidates else 'exact-only',
        historical_runtime_revalidated=False, **FALSE_AUTHORITY)


def _transport_bytes(pool, observed_bytes):
    binding.require(type(pool) is dict and type(pool.get('input_bytes')) is int and
        observed_bytes <= pool['input_bytes'] <= MAX_INPUT_BYTES, 'recovery transport input byte accounting')
    binding.require(pool.get('all_submitted_accounted') is not True or pool['input_bytes'] == observed_bytes,
                    'accounted recovery transport input bytes differ from actual outcomes')


def publish_proofs(session, source_context, writer, outcomes=None):
    """Use the unchanged bounded canonical JSONL/gzip writer grammar."""
    state = _state(session)
    encoding, footer = block_archive.ArchiveEncoding(), {}
    def rows():
        for row in session.records(source_context, outcomes):
            _guard(state)
            if row['kind'] == 'footer':
                footer.update(row)
            yield row
    pin = writer.write('recovery-model-proofs.jsonl.gz', encoding.chunks(rows()))
    binding.require(encoding.complete and footer.get('kind') == 'footer', 'incomplete recovery proof archive')
    return dict(archive=pin, encoding=encoding.summary(), footer=footer)


def open_recovery(ctx, blocks, history, *, deadline, before=lambda: None):
    """Cold-check a bounded, chronological, independently source-pinned lineage.

    Callers admit the original selection and every source context independently.
    The root uses the old archive grammar; descendants use only this new grammar.
    All inputs are exhausted/authenticated before the live session is returned.
    """
    now = time.monotonic()
    binding.require(type(deadline) is float and math.isfinite(deadline) and
                    now < deadline <= now+MAX_SECONDS, 'finite at-most-900-second recovery deadline required')
    binding.require(callable(before) and type(blocks) is list and 0 < len(blocks) <= MAX_BLOCKS,
                    'bounded original window declarations required')
    count = 0
    for block in blocks:
        binding.require(type(block) is dict and type(block.get('descriptors')) is list and
                        0 < len(block['descriptors']) <= 256, 'bounded original block descriptors required')
        count += len(block['descriptors'])
    binding.require(count <= MAX_MODELS, 'original window model cap')
    exact_json(blocks)
    blocks = _copy(blocks)
    BlockCertificates(ctx, blocks)
    binding.require(type(history) is list and bool(history), 'ordered pinned archive history required')
    state = _State(ctx, blocks, deadline, before, [], {})
    inputs, charged = [], 0
    for item in history:
        _guard(state)
        binding.require(type(item) is ArchiveInput and type(item.reader) is ArchiveReader,
                        'independently admitted bounded archive input required')
        charged += item.reader._expected_bytes
        binding.require(charged <= MAX_HISTORY_BYTES, 'cumulative compressed recovery history cap')
        inputs.append((item.reader, _context(item.source_context)))
    raw_bytes = 0
    for reader, source in inputs:
        _guard(state)
        reader.limit_raw_bytes(MAX_HISTORY_BYTES-raw_bytes)
        if not state.history:
            receipt = block_replay.replay_blocks(reader, ctx, blocks, source, deadline=deadline,
                before=lambda: _guard(state), replay_profile='window32/8192')
            summary = receipt.summary()
            archive = _pin(summary['archive'])
            refs = {r['model_ordinal']: r for r in summary['certificate_refs']}
            added = {}
            for row in receipt.certificates():
                ordinal = row['descriptor']['ordinal']
                added[ordinal] = _leaf(row, archive, source, refs[ordinal]['archive_row_index'])
        else:
            added = _replay_recovery(state, reader, source)
            archive = _pin(reader.summary)
        _guard(state)
        pin = reader.summary
        raw_bytes += pin['uncompressed_bytes']
        binding.require(raw_bytes <= MAX_HISTORY_BYTES, 'cumulative uncompressed recovery history cap')
        binding.require(all(entry['archive'] != archive for entry in state.history),
                        'duplicate or cyclic recovery archive history')
        state.leaves.update(added)
        state.history.append(dict(archive=archive, source_context=source,
            gzip_eof=pin['gzip_eof'], trailing_partial_row_bytes=pin['trailing_partial_row_bytes']))
    _guard(state)
    return RecoverySession(_KEY, state)


def _replay_recovery(state, reader, source):
    """Resolve only backward leaf references, retaining complete prefix rows."""
    certifier = BlockCertificates(state.ctx, state.blocks)
    expected = state.expected
    candidates = set(state.candidates)
    retained_seen, candidate_seen, missing_seen = set(), set(), set()
    new_rows, reports = {}, []
    pending, footer, started = None, None, False
    phase, input_bytes = 'retained', 0
    block_ids = [block['range']['block_id'] for block in state.blocks]
    for index, row in enumerate(reader.iter_rows(before=lambda: _guard(state))):
        _guard(state)
        binding.require(type(row) is dict and type(row.get('kind')) is str, 'typed recovery archive row required')
        if not started:
            block_replay.same(row, _header(state, source), 'recovery header population, lineage or source changed')
            started = True
            continue
        binding.require(footer is None, 'record after recovery footer')
        kind = row['kind']
        if pending is not None:
            binding.require(kind == 'block_certificate_checkpoint', 'missing immediate recovery checkpoint')
        if kind == 'retained_certificate_reference':
            binding.require(phase == 'retained' and set(row) == {'kind', 'descriptor', 'verification', 'provenance'},
                            'retained reference phase or fields changed')
            ordinal = row['descriptor']['ordinal']
            binding.require(type(ordinal) is int and ordinal in state.leaves and ordinal not in retained_seen,
                            'foreign or duplicate retained leaf reference')
            raw, provenance_raw = state.leaves[ordinal]
            full, provenance = json.loads(raw), json.loads(provenance_raw)
            block_replay.same(row['provenance'], provenance, 'unknown source or changed original leaf reference')
            block_replay.same(row['descriptor'], full['descriptor'], 'retained leaf descriptor changed')
            verified = _check_full(state, certifier, full, provenance['source_context'])
            block_replay.same(row['verification'], verified, 'retained leaf result changed')
            retained_seen.add(ordinal)
            if certifier.summary(expected[ordinal])['complete_certificates']:
                pending = expected[ordinal]
        elif kind in ('model_certificate', 'unresolved_model'):
            binding.require(phase in ('retained', 'candidate') and retained_seen == set(state.leaves),
                            'new model before complete retained-reference coverage')
            phase = 'candidate'
            ordinal = row['descriptor']['ordinal']
            binding.require(type(ordinal) is int and ordinal in candidates and ordinal not in candidate_seen,
                            'foreign or duplicate archived recovery candidate')
            block_replay.same(row['descriptor'], certifier.descriptor(ordinal), 'recovery descriptor changed')
            if kind == 'model_certificate':
                _check_full(state, certifier, row, source)
                job = LPStreamJob(source, expected[ordinal], ordinal,
                                  binding.digest(row['record']['model']), row['record']['model'])
                new_rows[ordinal] = (row, index)
            else:
                binding.require(set(row) == {'kind', 'descriptor', 'candidate', 'timings'} and
                                row['candidate']['status'] == 'unresolved', 'unresolved recovery record fields/status')
                job = _job(state, certifier, row['candidate'], source, candidates, candidate_seen)
                binding.require(job.model_ordinal == ordinal, 'unresolved descriptor/job changed')
                certifier.unresolved(ordinal, 'new unresolved candidate')
            input_bytes += len(job.input_bytes)
            binding.require(input_bytes <= MAX_INPUT_BYTES, 'cumulative archived recovery input cap')
            candidate_seen.add(ordinal)
            if certifier.summary(expected[ordinal])['complete_certificates']:
                pending = expected[ordinal]
        elif kind == 'block_certificate_checkpoint':
            binding.require(pending is not None, 'unexpected recovery checkpoint')
            block_replay.same(row, _checkpoint(certifier, pending), 'recovery checkpoint changed')
            pending = None
        elif kind == 'unsubmitted_model':
            binding.require(phase in ('retained', 'candidate', 'missing') and retained_seen == set(state.leaves),
                            'unsubmitted recovery record phase')
            phase = 'missing'
            binding.require(set(row) == {'kind', 'descriptor', 'reason'} and
                row['reason'] == 'recovery transport provided no candidate disposition', 'unsubmitted recovery record fields')
            ordinal = row['descriptor']['ordinal']
            binding.require(type(ordinal) is int and ordinal in candidates and
                            ordinal not in candidate_seen | missing_seen, 'foreign or duplicate missing candidate')
            block_replay.same(row['descriptor'], certifier.descriptor(ordinal), 'missing descriptor changed')
            missing_seen.add(ordinal)
        elif kind == 'block_report':
            binding.require(retained_seen == set(state.leaves) and candidate_seen | missing_seen == candidates,
                            'recovery report before full disposition coverage')
            phase = 'reports'
            binding.require(len(reports) < len(block_ids), 'extra recovery block report')
            _check_report(state, certifier, row, block_ids[len(reports)])
            reports.append(row['report'])
        elif kind == 'footer':
            binding.require(phase == 'reports' and len(reports) == len(block_ids), 'recovery footer lacks reports')
            pool = row.get('transport')
            if not candidates:
                binding.require(pool is None, 'exact-only recovery cannot fabricate candidate transport')
            else:
                _transport_bytes(pool, input_bytes)
            clean = not candidates or block_replay.transport_complete(pool, len(candidates))
            binding.require(not clean or candidate_seen == candidates, 'gap in archived complete recovery transport')
            binding.require(all(report['complete'] == (clean and report['complete_certificates'] and
                (report['physical_witness_verified'] or report.get('physical_witness_not_required') is True))
                for report in reports), 'recovery block completion disagrees with transport')
            complete = clean and len(state.leaves)+len(new_rows) == len(expected) and all(r['complete'] for r in reports)
            block_replay.same(row, _footer(state, complete, len(new_rows), pool, reports), 'recovery footer changed')
            footer = row
        else:
            raise ValueError('unknown recovery archive record kind')
    _guard(state)
    pin = reader.summary
    binding.require(type(pin) is dict and started, 'empty or unfinished recovery archive reader')
    binding.require(not pin['gzip_eof'] or (footer is not None and pending is None),
                    'complete recovery gzip lacks complete record grammar')
    binding.require(footer is None or pin['trailing_partial_row_bytes'] == 0,
                    'partial record after recovery footer')
    return {ordinal: _leaf(row, _pin(pin), source, index)
            for ordinal, (row, index) in new_rows.items()}


def _check_report(state, certifier, row, number):
    binding.require(set(row) == {'kind', 'report', 'winner_witness'}, 'recovery block report fields')
    report = row['report']
    core = certifier.summary(number)
    binding.require(type(report) is dict and set(core) | {'complete'} <= set(report) and
        set(report) <= set(core) | {'complete', 'physical_witness_not_required'} and
        type(report['complete']) is bool and type(report['physical_witness_verified']) is bool,
        'recovery report declaration changed')
    for key, value in core.items():
        if key != 'physical_witness_verified':
            block_replay.same(report[key], value, 'recovery report exact coverage changed: '+key)
    witness = row['winner_witness']
    binding.require((witness is not None) == report['physical_witness_verified'], 'recovery witness presence changed')
    if witness is not None:
        binding.require(core['complete_certificates'], 'physical witness on incomplete recovery block')
        fresh = _witness(state, certifier, number)
        binding.require(fresh is not None, 'physical witness on empty recovery block')
        old, new = dict(witness), dict(fresh)
        old.pop('timings', None)
        new.pop('timings', None)
        block_replay.same(old, new, 'recovery physical witness changed')
    if 'physical_witness_not_required' in report:
        binding.require(report['physical_witness_not_required'] is True and core['complete_certificates'] and
            core['aggregate']['result']['status'] == 'empty_restricted_family' and witness is None,
            'recovery witness exemption changed')
    binding.require(not report['complete'] or (core['complete_certificates'] and
        (report['physical_witness_verified'] or report.get('physical_witness_not_required') is True)),
        'false recovery block completion')
