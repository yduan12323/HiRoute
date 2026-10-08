"""Tiny genuine physical families and hand certificates; no LP or real archive.

Population upstream receipts and CheckedWindowReceipt instances below are
explicit protocol-only fixtures, not historical execution acceptance. Family,
model, exact certificate and physical approach checks are genuine and run
unchanged. Guarded constructor rejection is tested separately.
"""
from copy import deepcopy
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zlib

from experiments.time_cut_v2.recorded_real import block_archive, indexed_population, plan
from experiments.time_cut_v2.recorded_real import query_witnesses as qw, window_receipts as wr
from experiments.time_cut_v2.recorded_real.lp_stream_jobs import LPStreamJob
from validation.family5.checker import _plain
from validation.real5_v2.input import prepare_real_case
from validation.real5_v2.family import verify_bundle
from validation.real5_v2.suffix_context import count_language
from validation.suffix5.aggregate_stream import StreamAggregator
from validation.suffix5.independent_convex_model import build_model
from validation.suffix5.test_convex_checker import hand_record


def raw(value):
    return plan.canonical(value) + b'\n'


def hand_query_trace(rows):
    events = [dict(seq=row['query_seq'], kind='query', payload=dict(group_id=0, region_id=0,
        effect=row['actions'][0][1], actions=_plain(row['actions']), bound=row['bound'],
        classification=row['classification'], queue_serial=i+1)) for i, row in enumerate(rows)]
    events.append(dict(seq=len(events), kind='query', payload=dict(group_id=0, region_id=0,
        effect='C', actions=[], bound=None, classification='empty_actions', queue_serial=None)))
    return dict(schema='family5-hier-trace-v1', events=events)


def population(effects=('C',), attained=False):
    """Genuine immutable-real-input adapter with two hand-defined primitives."""
    old, _ = hand_record(effects[0], 1, attained)
    case = old.snapshot()['nodes'][old.roots[0]]['params']['case']
    query = {k: v for k, v in case.items() if k not in ('edges', 'sites', 'site_anchors')}
    query['H_ref'] = 1
    tree = dict(site_ids=['s'], regions=[dict(parent=-1, children=[], members=[0])])
    def number(n):
        return dict(hex=float(n).hex(), ratio=[str(x) for x in float(n).as_integer_ratio()])
    table = dict(schema='hiroute.immutable_selected_legs.v1',
        numerical_contract='binary64_totals_as_exact_rationals_v1', anchors=['o', 'z'],
        origin_anchor='o', destination_anchor='z', sites=[dict(site_id='s', anchor_id='o', effects=sorted(effects))],
        backend=dict(name='hand_physical_fixture', tie_policy='min_time_then_actual_length_then_first_discovery',
            direction_policy='forward_per_source_v1', source_sha256={'mock': 'a'*64}),
        source_sha256={'mock': 'a'*64}, selection_certificate_sha256='b'*64,
        hierarchy_sha256=plan.digest(tree), legs=[])
    for a in ('o', 'z'):
        for b in ('o', 'z'):
            n = int(a != b)
            table['legs'].append(dict(source_anchor=a, target_anchor=b, reachable=True,
                time_s=number(n), actual_length_m=number(n),
                label_direction='identity' if a == b else 'forward_from_source'))
    trusted = prepare_real_case(query, plan.digest(query), plan.canonical(table), plan.digest(table),
                                plan.canonical(tree), plan.digest(tree))
    node = dict(kind='initial', parents=[], params=dict(case=trusted.case_snapshot()),
        output=dict(domain=['2', '2', True, True], m='0', b='0', chi=True, rho='-2', pi=[],
                    state=['o', int(query['schedule'] is not None), 0]))
    ident = plan.digest(node)
    ctx = verify_bundle(dict(schema='family5-v1', nodes={ident: node}, batches=[], batch_ids=[], roots=[ident]), trusted)
    actions = [['s', effect] for effect in sorted(effects)]
    context = dict(state=_plain(ctx._pieces[ident].state), rho='-2', pi=[], H_remaining=1)
    counts = count_language(trusted, context['state'], actions)
    rows = [dict(query_seq=i, family_ids=[ident], actions=[action], ancestry_bundle_sha256='c'*64,
                 classification='queued', bound='0', **context) for i, action in enumerate(actions)]
    logical = dict(schema='hiroute-original-family-logical-model-count-v1', source_bundle_sha256=ctx.summary['bundle_sha256'],
        unique_families=1, unique_family_first_action_pairs=len(actions),
        unique_logical_model_slots=counts['models_per_family'], unique_logical_words=counts['legal_words_per_family'],
        unique_graph_exclusions=counts['graph_exclusion_models_per_family'],
        unique_reachable_band_models=counts['reachable_band_models_per_family'],
        original_occurrence_model_slots=counts['models_per_family'],
        groups=[dict(group_index=0, family_id=ident, context=context, first_actions=actions, counts=counts)],
        occurrence_bindings=[dict(query_index_position=i, query_seq=i, family_groups=[0], first_actions=row['actions'],
            model_slots=count_language(trusted, context['state'], row['actions'])['models_per_family'],
            ancestry_bundle_sha256=row['ancestry_bundle_sha256'], thin_occurrence_sha256=plan.digest(row))
            for i, row in enumerate(rows)])
    trace = hand_query_trace(rows)
    empty = [dict(query_seq=trace['events'][-1]['seq'], **trace['events'][-1]['payload'])]
    index = dict(queries=rows, bundle_sha256=ctx.summary['bundle_sha256'], case_sha256=ctx.summary['case_sha256'],
                 query_freeze_sha256='d'*64, trace_sha256=plan.digest(trace),
                 empty_action_queries=1, empty_action_sha256=plan.digest(empty))
    with patch.object(indexed_population.suffix_census, 'completed_inputs', return_value=(index, trusted, {}, {})), \
         patch.object(indexed_population.model_preview, 'logical_input', return_value=logical):
        admitted = indexed_population.admit_population(Path('.'), SimpleNamespace(), ctx, time.monotonic()+30)
    records = {}
    for descriptor in admitted.population.descriptors():
        identity = descriptor['logical_identity']; effect = identity['word'][0][1]
        band = identity['arrival_bands'][0]
        _, record = hand_record(effect, 0 if band is None else band, attained)
        record['model'] = build_model(ctx, ident, identity['word'], identity['arrival_bands'])
        records[descriptor['ordinal']] = record
    return admitted, records


class QueryWitnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.number = 0

    def archive(self, rows):
        self.number += 1
        path = self.root / ('proof%d.jsonl.gz' % self.number)
        encoder = block_archive.ArchiveEncoding()
        path.write_bytes(b''.join(encoder.chunks(rows)))
        return dict(path=str(path), **plan.pin(path))

    def fixture(self, effects=('C',), attained=False, *, seed=False, mutate=lambda rows: None,
                mutate_leaf=lambda rows: None, mutate_entry=lambda entry: None):
        admitted, records = population(effects, attained)
        blocks = admitted.population.plan()['blocks']
        context = dict(schema='protocol-only-hand-source-v1', source_bundle_sha256=admitted.ctx.summary['bundle_sha256'])
        rows = [dict(kind='header', schema='hiroute-suffix-block-proof-archive-v1', source_context=context,
                     blocks=blocks, expected_models=len(records))]
        aggregate = StreamAggregator(); parts = []; segment = None; current = None
        for descriptor in admitted.population.descriptors():
            ordinal = descriptor['ordinal']; record = records[ordinal]; result = record['result']
            job = LPStreamJob(context, 0, ordinal, plan.digest(record['model']), record['model'])
            verification = dict(model_ordinal=ordinal, block_id=0, logical_identity_sha256=descriptor['logical_identity_sha256'],
                model_sha256=plan.digest(record['model']), record_sha256=plan.digest(record), result=result,
                checked_stage_count=len(record['stages']), independent_certificate_verified=True,
                physical_witness_verified=False, query_optimum_certified=False, literal_G8_closed=False)
            rows.append(dict(kind='model_certificate', descriptor=descriptor, record=record,
                             verification=verification, candidate_identity=job.header('a'*32)))
            aggregate.add(ordinal, result)
            if descriptor['segment_id'] != current:
                if segment is not None:
                    parts.append(dict(segment_id=current, aggregate=segment.summary()))
                current = descriptor['segment_id']; segment = StreamAggregator(start=ordinal)
            segment.add(ordinal, result)
        parts.append(dict(segment_id=current, aggregate=segment.summary()))
        report = dict(range=blocks[0], aggregate=aggregate.summary(), segment_summaries=parts)
        rows.extend([dict(kind='block_report', report=report, winner_witness=None),
                     dict(kind='footer', schema='hiroute-suffix-block-proof-footer-v1', complete=not seed)])
        dependencies = []
        if seed:
            old = deepcopy(rows); mutate_leaf(old); leaf_pin = self.archive(old); dependencies = [leaf_pin]
            previous = context
            context = dict(schema='hiroute-suffix-block-resume-context-v1', previous_source_context=previous,
                           previous_archive={k:leaf_pin[k] for k in ('sha256', 'size_bytes')})
            rows[0].update(schema='hiroute-suffix-block-resume-archive-v1', source_context=context)
            for i, row in enumerate(rows[1:-2], 1):
                rows[i] = dict(kind='retained_certificate_reference', descriptor=row['descriptor'],
                    verification=row['verification'], provenance=dict(archive=context['previous_archive'],
                        source_context=previous, archive_row_index=i,
                        archive_row_sha256=hashlib.sha256(raw(row)).hexdigest()))
            rows[-1].update(schema='hiroute-suffix-block-resume-footer-v1', complete=True)
        mutate(rows)
        pin = self.archive(rows)
        entry = dict(module='block_resume' if seed else 'suffix_window', proof=pin,
            source_commit=wr.SEED_COMMIT if seed else 'f'*40, source_sha256=wr.SEED_SOURCE if seed else 'e'*64,
            source_context_sha256=plan.digest(context), population_sha256=plan.digest(admitted.commitment()),
            dependencies=dependencies)
        mutate_entry(entry)
        entry['entry_id'] = plan.digest(entry)
        entry['blocks'] = [wr._compact_report(report, entry['entry_id'])]
        # Explicit fake source-bound receipt, solely for the provenance protocol.
        receipt = wr.CheckedWindowReceipt(entry, [report], _token=wr._ADMISSION)
        registry = wr.make_registry(admitted, [receipt])
        requests = {ordinal: dict(descriptor=list(admitted.population.descriptors(ordinal, ordinal+1))[0],
                                 result=record['result']) for ordinal, record in records.items()
                    if record['result']['status'] != 'closed_infeasible'}
        return admitted, registry, requests

    def run_replay(self, fx, emit=None, **kwargs):
        output = []
        result = qw.replay_selected_witnesses(*fx, output.append if emit is None else emit,
                    deadline=kwargs.pop('deadline', time.monotonic()+30), **kwargs)
        return result, output

    def test_attained_and_both_exact_physical_approaches(self):
        for effects, attained, status in [(('C',), True, 'attained_optimum'),
                (('C',), False, 'primary_unattained'), (('CS',), False, 'secondary_unattained')]:
            with self.subTest(status=status):
                result, output = self.run_replay(self.fixture(effects, attained))
                self.assertEqual(result['selected_models'], 2)
                self.assertEqual(len(output), 2)
                for row in output:
                    checked = row['physical_receipt']
                    self.assertEqual(checked['result']['status'], status)
                    self.assertTrue(checked['physical_witness_verified'])
                    self.assertTrue(checked['exact_certificate_verified'])
                    self.assertTrue(row['provisional'])
                    self.assertFalse(row['query_optimum_certified'])
                    self.assertFalse(row['literal_G8_closed'])
                self.assertTrue(result['archives'][0]['consumed']['gzip_eof'])
                self.assertNotIn('physical_receipt', repr(result))

    def test_query_segment_loser_is_replayed_instead_of_block_winner(self):
        admitted, registry, requests = self.fixture(('CS', 'S'))
        self.assertEqual(registry.block_reports()[0]['aggregate']['result']['status'], 'attained_optimum')
        ordinal = next(i for i, r in requests.items() if r['result']['status'] == 'secondary_unattained')
        result, output = self.run_replay((admitted, registry, {ordinal: requests[ordinal]}))
        self.assertEqual(result['selected_models'], 1)
        self.assertEqual(output[0]['model_ordinal'], ordinal)
        self.assertEqual(output[0]['result']['status'], 'secondary_unattained')

    def test_seed_leaf_provenance_and_single_pass_per_archive(self):
        fx = self.fixture(seed=True)
        with patch.object(qw, 'ArchiveReader', wraps=qw.ArchiveReader) as reader:
            result, output = self.run_replay(fx)
        self.assertEqual(reader.call_count, 2)
        self.assertEqual(len(result['archives']), 2)
        for row in output:
            ancestry = row['provenance']['source_rows']
            self.assertEqual(len(ancestry), 2)
            self.assertNotEqual(ancestry[0]['archive']['sha256'], ancestry[1]['archive']['sha256'])

    def test_seed_mixes_fresh_model_rows_and_retained_leaf_rows(self):
        _, records = population()
        def mixed(rows):
            reference = rows[1]; record = records[0]
            job = LPStreamJob(rows[0]['source_context'], 0, 0, plan.digest(record['model']), record['model'])
            rows[1] = dict(kind='model_certificate', descriptor=reference['descriptor'], record=record,
                           verification=reference['verification'], candidate_identity=job.header('b'*32))
        result, output = self.run_replay(self.fixture(seed=True, mutate=mixed))
        self.assertEqual(result['selected_models'], 2)
        self.assertEqual([len(row['provenance']['source_rows']) for row in output], [1, 2])

    def test_wrong_request_and_physical_result_reject(self):
        for field in ('descriptor', 'result'):
            fx = self.fixture()
            if field == 'descriptor': fx[2][0]['descriptor']['logical_identity']['arrival_bands'] = [1]
            else: fx[2][0]['result']['primary_infimum'] = '99'
            with self.subTest(field=field), self.assertRaises(ValueError): self.run_replay(fx)
        fx = self.fixture()
        with patch.object(qw.calibration, 'verify_model', side_effect=ValueError('independent physical failure')), \
             self.assertRaisesRegex(ValueError, 'independent physical failure'):
            self.run_replay(fx)

    def test_wrong_model_certificate_is_not_authenticated_by_verified_flags(self):
        def mutate(rows):
            row = rows[1]; row['record']['stages'][0]['certificate']['x'][0] = '99'
            row['verification']['record_sha256'] = plan.digest(row['record'])
        with self.assertRaises(ValueError): self.run_replay(self.fixture(mutate=mutate))

    def test_missing_duplicate_foreign_and_unknown_rows_reject(self):
        mutations = [lambda rows: rows.pop(1), lambda rows: rows.insert(2, deepcopy(rows[1])),
                     lambda rows: rows[1]['descriptor'].__setitem__('ordinal', 999),
                     lambda rows: rows[1].__setitem__('kind', 'recovered_certificate_v99'),
                     lambda rows: rows[0]['source_context'].__setitem__('foreign', True),
                     lambda rows: rows.append(dict(kind='block_report'))]
        for change in mutations:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.run_replay(self.fixture(mutate=change))

    def test_seed_bad_index_hash_source_alias_and_recursive_rows_reject(self):
        mutations = [lambda rows: rows[1]['provenance'].__setitem__('archive_row_index', 2),
                     lambda rows: rows[1]['provenance'].__setitem__('archive_row_sha256', '0'*64),
                     lambda rows: rows[1]['provenance']['source_context'].__setitem__('foreign', True),
                     lambda rows: rows[2]['provenance'].__setitem__('archive_row_index', 1)]
        for change in mutations:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.run_replay(self.fixture(seed=True, mutate=change))
        with self.assertRaises(ValueError):
            self.run_replay(self.fixture(seed=True, mutate_entry=lambda entry: entry['dependencies'].clear()))
        with self.assertRaises(ValueError):
            self.run_replay(self.fixture(seed=True, mutate_leaf=lambda rows: rows[1].__setitem__('kind', 'retained_certificate_reference')))

    def test_partial_or_late_corrupt_archive_never_returns_completion(self):
        for corrupt in ('truncate', 'late'):
            fx = self.fixture(); pin = fx[1].metadata()['entries'][0]['proof']; path = Path(pin['path'])
            data = path.read_bytes()
            path.write_bytes(data[:-1] if corrupt == 'truncate' else data[:-1] + bytes([data[-1] ^ 1]))
            with self.subTest(corrupt=corrupt), self.assertRaises(ValueError): self.run_replay(fx)

    def test_callback_abort_deadline_and_detached_inputs(self):
        fx = self.fixture(); calls = []
        def abort(row):
            calls.append(row)
            raise RuntimeError('cancel selected replay')
        with self.assertRaisesRegex(RuntimeError, 'cancel selected replay'): self.run_replay(fx, abort)
        self.assertEqual(len(calls), 1)
        with self.assertRaises(ValueError): self.run_replay(fx, deadline=float('inf'))
        with self.assertRaises(ValueError): self.run_replay(fx, deadline=float(time.monotonic()-1))
        with qw.calibration.verification_deadline(float(time.monotonic()+30)):
            with self.assertRaisesRegex(ValueError, 'nested verification'): self.run_replay(fx)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0., 0.))
        saved = deepcopy(fx[2])
        def mutate(row):
            fx[2].clear(); row['physical_receipt']['result']['primary_infimum'] = '999'
        result, _ = self.run_replay(fx, mutate)
        self.assertEqual(result['selected_models'], len(saved))
        self.assertEqual(result['witnesses'][0]['result_sha256'], plan.digest(saved[0]['result']))

    def test_late_pin_failure_discards_already_streamed_receipts(self):
        calls = []
        fx = self.fixture(mutate_entry=lambda entry: entry['proof'].__setitem__('sha256', '0'*64))
        with self.assertRaisesRegex(ValueError, 'consumed compressed archive hash'):
            self.run_replay(fx, calls.append)
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(row['physical_receipt']['physical_witness_verified'] for row in calls))

    def test_late_verification_and_resource_callback_fail_before_completion(self):
        fx = self.fixture(); fx[2].pop(1)
        calls = []; count = 0
        original = qw.calibration.verification_deadline
        @contextmanager
        def late(deadline):
            nonlocal count
            count += 1
            with original(deadline):
                yield
            if count == 2:
                raise TimeoutError('late physical verification')
        with patch.object(qw.calibration, 'verification_deadline', late), \
             self.assertRaisesRegex(TimeoutError, 'late physical verification'):
            self.run_replay(fx, calls.append)
        self.assertEqual(calls, [])
        def checkpoint():
            if calls:
                raise RuntimeError('resource cancellation')
        with self.assertRaisesRegex(RuntimeError, 'resource cancellation'):
            self.run_replay(fx, calls.append, before=checkpoint)
        self.assertEqual(len(calls), 1)

    def test_dependency_conflicts_and_wrong_leaf_identity_reject(self):
        with self.assertRaises(ValueError):
            self.run_replay(self.fixture(seed=True, mutate_entry=lambda entry:
                entry['dependencies'].append(dict(entry['dependencies'][0], path='/foreign/proof.gz'))))
        with self.assertRaises(ValueError):
            self.run_replay(self.fixture(seed=True, mutate_leaf=lambda rows:
                rows[1]['descriptor']['logical_identity'].__setitem__('family_id', '0'*64)))
        with self.assertRaises(ValueError):
            self.run_replay(self.fixture(seed=True, mutate_leaf=lambda rows: rows.pop(1)))
        with self.assertRaises(ValueError):
            self.run_replay(self.fixture(seed=True, mutate_leaf=lambda rows: rows.insert(2, deepcopy(rows[1]))))

    def test_no_optimizer_imports_in_fresh_process(self):
        script = """
import sys
class Fence:
    def find_spec(self, name, path=None, target=None):
        if name.split('.')[0] in ('numpy', 'scipy', 'sympy', 'highspy') or name.startswith(
                ('timecut5', 'validation.suffix5.solver', 'validation.suffix5.vendor_lp')):
            raise AssertionError('optimizer import: '+name)
sys.meta_path.insert(0, Fence())
from tests.test_suffix_query_witnesses import QueryWitnessTests
case = QueryWitnessTests()
case.setUp()
try:
    result, receipts = case.run_replay(case.fixture(('CS', 'S'), seed=True))
    assert result['selected_models'] == 3 and len(receipts) == 3
finally:
    case.doCleanups()
"""
        completed = subprocess.run([sys.executable, '-B', '-c', script], capture_output=True, text=True, timeout=30)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def test_request_bytes_include_ordinals_array_and_commas(self):
        fx = self.fixture()
        exact = len(plan.canonical([dict(model_ordinal=ordinal, **request)
                                   for ordinal, request in fx[2].items()]))
        with patch.object(qw, 'MAX_REQUEST_BYTES', exact):
            result, output = self.run_replay(fx)
            self.assertEqual(result['selected_models'], 2)
            expected = plan.digest([dict(model_ordinal=ordinal, **fx[2][ordinal]) for ordinal in sorted(fx[2])])
            self.assertEqual(result['physical_request_rows_sha256'], expected)
            self.assertEqual(result['physical_request_bytes'], exact)
            self.assertEqual(output[0]['provenance']['physical_request_rows_sha256'], expected)
            reverse = (fx[0], fx[1], dict(reversed(list(fx[2].items()))))
            self.assertEqual(self.run_replay(reverse)[0]['physical_request_rows_sha256'], expected)
        with patch.object(qw, 'MAX_REQUEST_BYTES', exact-1), self.assertRaisesRegex(ValueError, 'request byte cap'):
            self.run_replay(fx)

    def test_final_detachment_has_a_resource_checkpoint_before_return(self):
        original = wr._owned
        cancelled = False
        def detach(value):
            nonlocal cancelled
            result = original(value)
            if type(value) is dict and value.get('schema') == 'hiroute-selected-query-witness-coverage-v1':
                cancelled = True
            return result
        def checkpoint():
            if cancelled:
                raise RuntimeError('cancel after final materialization')
        with patch.object(wr, '_owned', detach), self.assertRaisesRegex(RuntimeError, 'final materialization'):
            self.run_replay(self.fixture(), before=checkpoint)

    def test_checked_boundaries_and_resource_limits(self):
        fx = self.fixture()
        with self.assertRaises(ValueError): wr.CheckedRegistry(fx[1].metadata(), [])
        with self.assertRaises(ValueError): indexed_population.AdmittedSuffixPopulation(None, None, {}, {}, {})
        scheduling = wr.CheckedRegistry(fx[1].metadata(), (), _token=wr._ADMISSION)
        with self.assertRaisesRegex(ValueError, 'cold reconciliation'):
            self.run_replay((fx[0], scheduling, fx[2]))
        with self.assertRaises(ValueError): self.run_replay((SimpleNamespace(ctx=fx[0].ctx), fx[1], fx[2]))
        with patch.object(qw, 'MAX_SELECTED_MODELS', 1), self.assertRaises(ValueError): self.run_replay(fx)
        with patch.object(qw, 'MAX_REQUEST_BYTES', 1), self.assertRaises(ValueError): self.run_replay(fx)
        with self.assertRaises(ValueError): self.run_replay((fx[0], fx[1], {True: fx[2][0]}))
        with patch.object(qw, 'ArchiveReader', side_effect=AssertionError('unrequested archive read')):
            result, output = self.run_replay((fx[0], fx[1], {}))
        self.assertEqual(result['selected_models'], 0); self.assertEqual(output, [])


class RecoveryWitnessTests(unittest.TestCase):
    """Protocol-only admitted history with unchanged genuine physical checks."""
    setUp = QueryWitnessTests.setUp
    archive = QueryWitnessTests.archive
    run_replay = QueryWitnessTests.run_replay

    def fixture(self, *, exact_only=False, interrupted=(), partial=b'',
                complete_history=False, mutate=lambda rows: None,
                mutate_history=lambda number, rows: None, mutate_entry=lambda entry: None,
                mutate_plan=lambda document: None):
        from experiments.time_cut_v2.recorded_real import window_recovery_receipts as rr
        ordinary = QueryWitnessTests.fixture(self, ('CS', 'S'))
        admitted, old_registry, requests = ordinary
        _, records = population(('CS', 'S'))
        descriptors = list(admitted.population.descriptors())
        blocks = admitted.population.plan()['blocks']
        history, leaves, predecessors, dependencies = [], {}, [], []
        self.number += 1
        attempt = self.root/('recovery%d' % self.number)
        attempt.mkdir()

        def context():
            return dict(schema='protocol-only-hand-recovery-context-v1', source_sha256='e'*64,
                source_bundle_sha256=admitted.ctx.summary['bundle_sha256'], history_sha256=plan.digest(history),
                previous_archive=history[-1]['archive'] if history else None,
                previous_source_context_sha256=plan.digest(history[-1]['source_context']) if history else None)

        def certificate(ordinal, source):
            descriptor, record = descriptors[ordinal], deepcopy(records[ordinal])
            job = LPStreamJob(source, 0, ordinal, plan.digest(record['model']), record['model'])
            verification = dict(model_ordinal=ordinal, block_id=0,
                logical_identity_sha256=descriptor['logical_identity_sha256'], model_sha256=plan.digest(record['model']),
                record_sha256=plan.digest(record), result=record['result'], checked_stage_count=len(record['stages']),
                independent_certificate_verified=True, physical_witness_verified=False,
                query_optimum_certified=False, literal_G8_closed=False)
            return dict(kind='model_certificate', descriptor=descriptor, record=record,
                verification=verification, candidate_identity=job.header('a'*32), candidate_metrics={},
                timings={}, stdout_sha256='a'*64, stderr_base64='')

        for number in range(2):
            source = context()
            rows = [dict(kind='header', schema=rr.ARCHIVE_SCHEMA if number else 'hiroute-suffix-block-proof-archive-v1',
                source_context=source, blocks=blocks, expected_models=len(descriptors))]
            if number:
                rows[0].update(history=deepcopy(history), previous_archive=history[-1]['archive'])
                rows.extend(deepcopy(rr._reference(leaves[i])) for i in sorted(leaves))
            fresh = {0} if number == 0 else (set(records)-set(leaves) if exact_only else {1})
            rows.extend(certificate(i, source) for i in sorted(fresh))
            rows.extend(dict(kind='unresolved_model', descriptor=descriptors[i])
                        for i in sorted(set(records)-set(leaves)-fresh))
            rows.append(dict(kind='footer', schema=rr.FOOTER_SCHEMA if number else 'hiroute-suffix-block-proof-footer-v1',
                             complete=complete_history and number > 0 and exact_only))
            if number in interrupted:
                rows.pop()
            mutate_history(number, rows)
            if number in interrupted:
                path = attempt/('ancestor%d.jsonl.gz.part' % number)
                compressor = zlib.compressobj(wbits=31)
                path.write_bytes(compressor.compress(b''.join(raw(row) for row in rows)+partial)+
                                 compressor.flush(zlib.Z_SYNC_FLUSH))
                pin = dict(path=str(path), **plan.pin(path))
            else:
                pin = self.archive(rows)
            dependencies.append(pin)
            predecessors.append(dict(module=wr.MODULE_PREFIX+('suffix_window' if number == 0 else rr.MODULE),
                source_commit='f'*40, source_sha256='e'*64, archive_mode='interrupted-prefix' if number in interrupted else 'finalized',
                source_context=source, artifacts=dict(archive=pin)))
            history.append(dict(archive=rr._pin(pin), source_context=source, gzip_eof=number not in interrupted,
                                trailing_partial_row_bytes=len(partial) if number in interrupted else 0))
            for index, row in enumerate(rows):
                if row['kind'] == 'model_certificate':
                    leaves[row['descriptor']['ordinal']] = rr._leaf(row, rr._pin(pin), source, index)

        document = dict(schema='hiroute-suffix-window-recovery-plan-v1', historical_attempt_status='failed',
                        predecessors=predecessors)
        mutate_plan(document)
        plan_path = attempt/'recovery-plan.json'; plan_path.write_bytes(raw(document))
        plan_pin = dict(path=str(plan_path), **plan.pin(plan_path)); dependencies.append(plan_pin)
        source = context(); source['recovery_plan_sha256'] = plan_pin['sha256']
        rows = [dict(kind='header', schema=rr.ARCHIVE_SCHEMA, source_context=source, blocks=blocks,
                     expected_models=len(records), history=history, previous_archive=history[-1]['archive'])]
        rows.extend(deepcopy(rr._reference(leaves[i])) for i in sorted(leaves))
        rows.extend(certificate(i, source) for i in sorted(set(records)-set(leaves)))
        rows.append(dict(kind='footer', schema=rr.FOOTER_SCHEMA, complete=True, proof_complete=True,
                         recovery_mode='exact-only' if exact_only else 'candidates',
                         transport=None if exact_only else dict(protocol_only=True)))
        mutate(rows)
        path = attempt/'recovery-model-proofs.jsonl.gz'
        path.write_bytes(b''.join(block_archive.ArchiveEncoding().chunks(rows)))
        pin = dict(path=str(path), **plan.pin(path)); dependencies.append(pin)
        entry = dict(module=rr.MODULE, proof=pin, source_commit='f'*40, source_sha256='e'*64,
            source_context_sha256=plan.digest(source), population_sha256=plan.digest(admitted.commitment()),
            dependencies=dependencies)
        mutate_entry(entry)
        entry['entry_id'] = plan.digest(entry)
        report = old_registry.block_reports()[0]
        report.update(schema='suffix5-checked-block-certificates-v1', complete_certificates=True,
                      unresolved_ordinals=[], unsubmitted_ordinals=[], verified_models=len(records))
        entry['blocks'] = [wr._compact_report(report, entry['entry_id'])]
        receipt = wr.CheckedWindowReceipt(entry, [report], _token=wr._ADMISSION)
        return admitted, wr.make_registry(admitted, [receipt]), requests

    def test_root_intermediate_and_current_full_leaves_are_checked_once(self):
        fx = self.fixture()
        with patch.object(qw, 'ArchiveReader', wraps=qw.ArchiveReader) as readers, \
             patch.object(qw.calibration, 'verify_model', wraps=qw.calibration.verify_model) as physical:
            coverage, rows = self.run_replay(fx)
        self.assertEqual(readers.call_count, 3)
        self.assertEqual(physical.call_count, 3)
        self.assertEqual(coverage['selected_models'], 3)
        by_ordinal = {row['model_ordinal']: row for row in rows}
        self.assertEqual({i: len(row['provenance']['source_rows']) for i, row in by_ordinal.items()}, {0: 2, 1: 2, 3: 1})
        self.assertEqual(by_ordinal[0]['result']['status'], 'secondary_unattained')
        self.assertEqual(by_ordinal[3]['result']['status'], 'attained_optimum')
        self.assertTrue(all(row['physical_receipt']['physical_witness_verified'] for row in rows))
        self.assertTrue(all(not row[key] for row in rows for key in wr.FALSE_AUTHORITY))

    def test_exact_only_and_failed_runtime_with_complete_proof_footer(self):
        coverage, rows = self.run_replay(self.fixture(exact_only=True, complete_history=True))
        self.assertEqual(coverage['selected_models'], 3)
        self.assertTrue(all(len(row['provenance']['source_rows']) == 2 for row in rows))
        self.assertEqual(len(coverage['archives']), 3)

    def test_explicit_interrupted_prefix_policies_and_exact_part_paths(self):
        for interrupted in ((0,), (1,), (0, 1)):
            coverage, rows = self.run_replay(self.fixture(interrupted=interrupted, partial=b'{"unfinished":'))
            self.assertEqual(len(rows), 3)
            old = coverage['archives'][1:]
            for number in interrupted:
                self.assertTrue(old[number]['archive']['path'].endswith('.part'))
                self.assertFalse(old[number]['consumed']['gzip_eof'])
                self.assertEqual(old[number]['consumed']['trailing_partial_row_bytes'], len(b'{"unfinished":'))
        def finalize(document): document['predecessors'][0]['archive_mode'] = 'finalized'
        with self.assertRaisesRegex(ValueError, 'explicit archive policy'):
            self.run_replay(self.fixture(interrupted=(0,), mutate_plan=finalize))
        def interrupt(document): document['predecessors'][1]['archive_mode'] = 'interrupted-prefix'
        with self.assertRaisesRegex(ValueError, 'explicit archive policy'):
            self.run_replay(self.fixture(mutate_plan=interrupt))

    def test_an_alias_cannot_replace_the_exact_admitted_part_path(self):
        fx = self.fixture(interrupted=(0,))
        entry = fx[1].metadata()['entries'][0]
        exact = Path(entry['dependencies'][0]['path'])
        alias = exact.with_suffix('')
        alias.write_bytes(exact.read_bytes())
        exact.unlink()
        with self.assertRaisesRegex(ValueError, 'regular and contain no symlinks'):
            self.run_replay(fx)
        exact.symlink_to(alias)
        with self.assertRaisesRegex(ValueError, 'regular and contain no symlinks'):
            self.run_replay(fx)

    def test_bad_direct_references_descriptors_and_source_aliases_reject(self):
        mutations = [lambda rows: rows[1]['provenance']['archive'].update(sha256='0'*64),
            lambda rows: rows[1]['provenance'].update(archive_row_index=99),
            lambda rows: rows[1]['provenance'].update(archive_row_sha256='0'*64),
            lambda rows: rows[1]['provenance']['source_context'].update(source_sha256='0'*64),
            lambda rows: rows[1]['verification']['result'].update(primary_infimum='99'),
            lambda rows: rows[1]['descriptor']['logical_identity'].update(family_id='0'*64)]
        for mutation in mutations:
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.run_replay(self.fixture(mutate=mutation))
        def reference_to_reference(rows):
            previous = rows[0]['history'][-1]
            rows[1]['provenance'].update(archive=previous['archive'], source_context=previous['source_context'],
                                        archive_row_index=1)
        with self.assertRaisesRegex(ValueError, 'direct full leaf'):
            self.run_replay(self.fixture(mutate=reference_to_reference))
        def duplicate_path(entry): entry['dependencies'].append(deepcopy(entry['dependencies'][0]))
        with self.assertRaisesRegex(ValueError, 'ambiguous recovery dependency'):
            self.run_replay(self.fixture(mutate_entry=duplicate_path))

    def test_missing_ancestor_plan_and_chronological_history_reject(self):
        def missing(entry): entry['dependencies'].pop(0)
        def missing_plan(entry): entry['dependencies'].pop(-2)
        def wrong_order(rows): rows[0]['history'].reverse()
        for kwargs in (dict(mutate_entry=missing), dict(mutate_entry=missing_plan), dict(mutate=wrong_order)):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError): self.run_replay(self.fixture(**kwargs))
        def recursive(number, rows):
            if number: rows[1]['provenance']['archive_row_index'] = 99
        with self.assertRaisesRegex(ValueError, 'recursive or changed'):
            self.run_replay(self.fixture(mutate_history=recursive))

    def test_nonselected_ancestor_late_corruption_and_history_budgets_reject(self):
        fx = self.fixture()
        entry = fx[1].metadata()['entries'][0]
        path = Path(entry['dependencies'][1]['path'])
        content = bytearray(path.read_bytes()); content[-8] ^= 1; path.write_bytes(content)
        # Select only the current full leaf; every historical archive is still consumed.
        with self.assertRaises(ValueError): self.run_replay((fx[0], fx[1], {3: fx[2][3]}))
        fx = self.fixture()
        with patch.object(qw.recovery_receipts, 'HISTORY_BYTES', 1), self.assertRaisesRegex(ValueError, 'history byte cap'):
            self.run_replay(fx)
        entry = fx[1].metadata()['entries'][0]
        compressed = sum(row['size_bytes'] for row in entry['dependencies'][:2])
        with patch.object(qw.recovery_receipts, 'HISTORY_BYTES', compressed), \
             self.assertRaisesRegex(ValueError, 'uncompressed archive byte cap'):
            self.run_replay(fx)
        with patch.object(qw, 'MAX_RECOVERY_HISTORY', 1), self.assertRaisesRegex(ValueError, 'bounded complete'):
            self.run_replay(fx)

    def test_missing_leaf_and_wrong_physical_proof_never_gain_authority(self):
        with self.assertRaises(ValueError): self.run_replay(self.fixture(mutate=lambda rows: rows.pop(1)))
        def bad(number, rows):
            if number == 1:
                row = next(row for row in rows if row['kind'] == 'model_certificate')
                row['record']['stages'][0]['certificate']['x'][0] = '99'
                row['verification']['record_sha256'] = plan.digest(row['record'])
        with self.assertRaises(ValueError): self.run_replay(self.fixture(mutate_history=bad))

    def test_optimizer_import_and_candidate_launch_fence(self):
        script = """
import sys
class Fence:
    def find_spec(self, name, path=None, target=None):
        if name.split('.')[0] in ('numpy', 'scipy', 'sympy', 'highspy') or name.startswith(
            ('timecut5', 'validation.suffix5.solver', 'validation.suffix5.vendor_lp',
             'experiments.time_cut_v2.recorded_real.suffix_window_recovery')):
            raise AssertionError('optimizer/candidate import: '+name)
sys.meta_path.insert(0, Fence())
from tests.test_suffix_query_witnesses import RecoveryWitnessTests
from unittest.mock import patch
case = RecoveryWitnessTests(); case.setUp()
try:
    with patch('subprocess.Popen', side_effect=AssertionError('candidate launch')):
        result, rows = case.run_replay(case.fixture(interrupted=(0, 1)))
    assert result['selected_models'] == 3 and len(rows) == 3
finally:
    case.doCleanups()
"""
        completed = subprocess.run([sys.executable, '-B', '-c', script], capture_output=True, text=True, timeout=30)
        self.assertEqual(completed.returncode, 0, completed.stdout+completed.stderr)


if __name__ == '__main__':
    unittest.main()
