"""Named tiny convex/no-curve proofs only; no acceptance-population inputs."""
from copy import deepcopy
from fractions import Fraction as F
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from validation.family5 import verify_bundle, VerificationError
from validation.family5.checker import digest
from validation.suffix5.convex_model import build_model, build_models, band_assignments
from validation.suffix5.solver import solve_model, SolveBudget, solution_point
from validation.suffix5.convex_witness import lift_point, result_contract
from validation.suffix5.query import aggregate
from validation.suffix5.convex_checker import check_regime, aggregate_records
from validation.suffix5.convex_evidence import check_result_witness
from validation.suffix5.independent_convex_model import build_models as independent_models


CURVE = [[0, 2, 1, 7], [2, 4, 2, 5], [4, 6, 4, -3]]


def tiny_case(name='cross_both'):
    case = dict(case_id='UNIT_CONVEX_SUFFIX_'+name, H_ref=2, origin='o', destination='z',
                start_time_s=0, initial_energy_kwh=1, capacity_kwh=6, minimum_energy_kwh=0,
                reserve_kwh=0, consumption_kwh_per_m=1, overhead_s=1, lambda_stop_s=0,
                schedule=None, sites={'c': ['C']}, charging_segments=deepcopy(CURVE),
                edges=[dict(source='o', target='c', time_s=1, length_m=1),
                       dict(source='c', target='z', time_s=1, length_m=5)])
    if name.startswith('departure_'):
        case['edges'][1]['length_m'] = int(name.rsplit('_', 1)[1])
    elif name.startswith('arrival_'):
        arrival = int(name.rsplit('_', 1)[1])
        case['initial_energy_kwh'] = arrival+1
        case['edges'][1]['length_m'] = arrival+1
    elif name in ('primary_open', 'secondary_open'):
        case['initial_energy_kwh'] = 3  # q tends to zero exactly at the first kink.
        case['edges'][1]['length_m'] = 1
    elif name == 'strict_empty':
        case.update(origin='c', initial_energy_kwh=6)
        case['edges'] = [dict(source='c', target='z', time_s=1, length_m=1)]
    elif name == 'graph_empty':
        case['edges'] = [dict(source='o', target='z', time_s=1, length_m=1),
                         dict(source='c', target='z', time_s=1, length_m=1)]
    elif name == 'no_curve':
        case.update(initial_energy_kwh=2, charging_segments=[], sites={'c': ['S']},
                    schedule=dict(a=2, b=2, D=3))
        case['edges'][1]['length_m'] = 1
    if name in ('secondary_open', 'charge_dominant', 'release_dominant', 'cs_tie', 'inverted_window'):
        schedule = {'secondary_open': (10, 10, 1), 'charge_dominant': (3, 3, 1),
                    'release_dominant': (20, 20, 1), 'cs_tie': (2, 2, 10),
                    'inverted_window': (3, 2, 1)}[name]
        case.update(sites={'c': ['C', 'S', 'CS']}, schedule=dict(zip(('a', 'b', 'D'), schedule)))
    return case


def initial_context(case):
    energy, start = str(case['initial_energy_kwh']), str(case['start_time_s'])
    remaining = case.get('initial_remaining_schedule', int(case['schedule'] is not None))
    piece = dict(domain=[energy, energy, True, True], m='0', b=start, chi=True,
                 rho=str(-F(energy)), pi=[], state=[case['origin'], remaining, 0])
    node = dict(kind='initial', parents=[], output=piece, params={'case': case})
    ident = digest(node)
    bundle = dict(schema='family5-v1', nodes={ident: node}, batches=[], batch_ids=[], roots=[ident])
    return verify_bundle(bundle, case), ident


def inherited_context(kind):
    from timecut5.bounded import Problem
    from timecut5.probe import Interval
    from timecut5.provenance import Recorder, restrict
    case = tiny_case('inherited_'+kind)
    case['charging_segments'] = [[lo, hi, slope, intercept-7] for lo, hi, slope, intercept in CURVE]
    case.update(H_ref=4, initial_energy_kwh=2, sites={'c': ['C', 'S', 'CS']},
                schedule=dict(a=10, b=10, D=1), reserve_kwh=4 if kind == 'time_open' else 0)
    case['edges'][1]['length_m'] = 1
    with Recorder() as recorder:
        problem = Problem(case)
        pieces = problem.advance((problem.initial_piece(),), 'c', 'C')
        if kind == 'time_open':
            pieces = problem.advance(pieces, 'c', 'S')
            pieces = problem.advance(pieces, 'c', 'C')
            piece = next(p for p in pieces if p.domain.contains(F(3)) and not p.chi)
            piece = restrict(piece, Interval(3, 3), 'tiny convex open-time guard')
        else:
            piece = next(p for p in pieces if p.domain.contains(F(3, 2)))
            piece = restrict(piece, piece.domain.intersect(Interval(1, 2, False, True)),
                             'tiny convex open-energy guard')
        bundle = recorder.export((piece,))
    return verify_bundle(bundle, case), piece._family.node_id


def foreign_context():
    from timecut5.bounded import Problem
    from timecut5.probe import Interval
    from timecut5.provenance import Recorder, restrict
    case = tiny_case('foreign_ancestry')
    case['charging_segments'] = [[lo, hi, slope, intercept-7] for lo, hi, slope, intercept in CURVE]
    case.update(H_ref=4, initial_energy_kwh=2)
    case['edges'][1]['length_m'] = 1
    with Recorder() as recorder:
        problem = Problem(case)
        first = problem.advance((problem.initial_piece(),), 'c', 'C')
        roots = []
        for domain in (Interval(1, F(3, 2), False, False), Interval(2, F(5, 2), False, False)):
            selected = tuple(restrict(piece, overlap, 'tiny convex ancestral guard')
                             for piece in first if (overlap := piece.domain.intersect(domain)) is not None)
            second = problem.advance(selected, 'c', 'C')
            source = next(p for p in second if p.domain.contains(F(3)))
            roots.append(restrict(source, Interval(3, 3), 'tiny convex common final energy'))
        bundle = recorder.export(roots)
    return verify_bundle(bundle, case), [p._family.node_id for p in roots]


def unit_inputs():
    rows = []
    cases = [('cross_both', 'C'), ('departure_2', 'C'), ('departure_4', 'C'),
             ('departure_6', 'C'), ('arrival_2', 'C'), ('arrival_4', 'C'),
             ('primary_open', 'C'), ('secondary_open', 'CS'), ('charge_dominant', 'CS'),
             ('release_dominant', 'CS'), ('cs_tie', 'CS'), ('inverted_window', 'CS'),
             ('strict_empty', 'C'), ('graph_empty', 'C'), ('no_curve', 'S')]
    for name, effect in cases:
        ctx, ident = initial_context(tiny_case(name))
        rows.append((name, ctx, ident, [['c', effect]]))
    ctx, ident = initial_context(tiny_case('two_charges'))
    rows.append(('two_charges', ctx, ident, [['c', 'C'], ['c', 'C']]))
    for name, effect in [('energy_open', 'S'), ('time_open', 'C')]:
        ctx, ident = inherited_context(name)
        rows.append(('inherited_'+name, ctx, ident, [['c', effect]]))
    ctx, ids = foreign_context()
    for label, ident in zip(('A', 'B'), ids):
        rows.append(('foreign_'+label, ctx, ident, [['c', 'C']]))
    return rows


class ConvexSuffixNumerics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures = {}
        cls.budget = SolveBudget(max_passes=500, wall_seconds=60, rss_mib=256)
        for name, ctx, ident, word in unit_inputs():
            models = build_models(ctx, ident, word)
            if models != independent_models(ctx, ident, word):
                raise AssertionError('independent convex matrices disagree: '+name)
            records = [solve_model(model, cls.budget) for model in models]
            for record in records:
                if check_regime(ctx, record) != record['result']:
                    raise AssertionError('independent result mismatch')
                if record['result']['status'] in ('attained_optimum', 'primary_unattained', 'secondary_unattained'):
                    eps = F(1, 10**30)
                    evidence = lift_point(ctx, record['model'], solution_point(record, eps))
                    check_result_witness(ctx, record, evidence, result_contract(record['result'], eps))
            cls.fixtures[name] = (ctx, ident, word, records)

    def result(self, name):
        records = self.fixtures[name][3]
        result = aggregate(records)
        self.assertEqual(result, aggregate_records(records))
        return result

    def test_exact_breakpoints_and_crossing_both_thresholds(self):
        for name, J, Q in [('cross_both', '13', '5'), ('departure_2', '5', '2'),
                            ('departure_4', '9', '4'), ('departure_6', '17', '6'),
                            ('arrival_2', '5', '1'), ('arrival_4', '7', '1')]:
            with self.subTest(name=name):
                self.assertEqual(self.result(name)['lex_key'], [J, Q, 1, [['c', 'C']]])
        for name in ('arrival_2', 'arrival_4'):
            records = self.fixtures[name][3]
            self.assertEqual(sum(r['result']['status'] == 'attained_optimum' for r in records), 2)

    def test_charge_release_and_cs_equality_switches(self):
        for name, J in [('charge_dominant', '13'), ('release_dominant', '22'), ('cs_tie', '13')]:
            with self.subTest(name=name):
                self.assertEqual(self.result(name)['lex_key'], [J, '5', 1, [['c', 'CS']]])
        self.assertEqual(self.result('inverted_window'), {'status': 'empty_restricted_family'})

    def test_strict_breakpoint_limits_and_inherited_endpoints(self):
        self.assertEqual(self.result('primary_open'), dict(status='primary_unattained', primary_infimum='3'))
        self.assertEqual(self.result('secondary_open'), dict(status='secondary_unattained', J='12', secondary_infimum='0'))
        self.assertEqual(self.result('inherited_energy_open'), dict(status='secondary_unattained', J='12', secondary_infimum='0'))
        self.assertEqual(self.result('inherited_time_open')['status'], 'primary_unattained')
        for name, label in [('inherited_energy_open', 'prefix_energy_lower'), ('inherited_time_open', 'prefix_time')]:
            row = next(r for r in self.fixtures[name][3][0]['model']['lp']['rows'] if r['label'] == label)
            self.assertIs(row['strict'], True)
        self.assertEqual(self.result('strict_empty'), {'status': 'empty_restricted_family'})

    def test_multiple_charges_keep_full_key_and_complete_band_product(self):
        ctx, ident, word, records = self.fixtures['two_charges']
        self.assertEqual(len(records), 9)
        self.assertEqual([r['model']['arrival_bands'] for r in records],
                         [[i, j] for i in range(3) for j in range(3)])
        result = self.result('two_charges')
        self.assertEqual(result['lex_key'], ['14', '5', 2, word])
        self.assertEqual(sum(r['result']['status'] == 'attained_optimum' for r in records), 3)

    def test_no_curve_is_a_genuine_service_only_case(self):
        ctx, _, word, records = self.fixtures['no_curve']
        self.assertEqual(ctx._physics.curve, ())
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['model']['arrival_bands'], [None])
        self.assertEqual(self.result('no_curve')['lex_key'], ['6', '0', 1, word])
        self.assertFalse(any('charge_completion' in r['label'] for r in records[0]['model']['lp']['rows']))

    def test_graph_exclusion_is_not_multiplied_by_bands(self):
        records = self.fixtures['graph_empty'][3]
        self.assertEqual(len(records), 1)
        self.assertIsNone(records[0]['model']['arrival_bands'])
        self.assertEqual(records[0]['result'], {'status': 'graph_unreachable'})

    def test_original_foreign_prefixes_reconstruct_distinct_ancestors(self):
        observed = []
        for name in ('foreign_A', 'foreign_B'):
            ctx, _, _, records = self.fixtures[name]
            record = next(r for r in records if r['result']['status'] == 'primary_unattained')
            evidence = lift_point(ctx, record['model'], solution_point(record, F(1, 100)))
            observed.append(F(evidence['prefix']['witness']['events'][2]['departure_energy']))
        self.assertTrue(1 < observed[0] < F(3, 2))
        self.assertTrue(2 < observed[1] < F(5, 2))


class ConvexSuffixRejections(unittest.TestCase):
    def test_v2_one_segment_and_collinear_split_preserve_affine_results(self):
        from validation.suffix5.model import build_model as affine_model
        from validation.suffix5.checker import check_regime as affine_check
        for curve in ([[0, 6, 2, 7]], [[0, 2, 2, 7], [2, 6, 2, 7]]):
            with self.subTest(curve=curve):
                case = tiny_case('collinear')
                case['charging_segments'] = curve
                ctx, ident = initial_context(case)
                records = [solve_model(model) for model in build_models(ctx, ident, [['c', 'C']])]
                for record in records:
                    self.assertEqual(check_regime(ctx, record), record['result'])
                self.assertEqual(aggregate(records)['lex_key'], ['13', '5', 1, [['c', 'C']]])
                if len(curve) == 1:
                    old = solve_model(affine_model(ctx, ident, [['c', 'C']]))
                    self.assertEqual(affine_check(ctx, old), aggregate(records))

    def test_nonconvex_and_undefined_laws_fail_closed(self):
        case = tiny_case()
        case['charging_segments'] = [[0, 2, 2, 0], [2, 6, 1, 2]]
        ctx, ident = initial_context(case)
        with self.assertRaisesRegex(VerificationError, 'nonconvex'):
            build_models(ctx, ident, [['c', 'C']])
        for curve in ([], [[0, 2, 1, 0], [3, 6, 2, -3]],
                      [[0, 2, 1, 0], [2, 6, 2, 0]], [[0, 6, 0, 0]]):
            with self.subTest(curve=curve), self.assertRaises(VerificationError):
                case = tiny_case()
                case['charging_segments'] = curve
                initial_context(case)

    def test_band_identity_is_exact_and_s_has_no_band(self):
        ctx, ident = initial_context(tiny_case())
        for bands in (None, [], [True], [1.0], [-1], [3], [None], [0, 1]):
            with self.subTest(bands=bands), self.assertRaises(VerificationError):
                build_model(ctx, ident, [['c', 'C']], bands)
        ctx, ident = initial_context(tiny_case('no_curve'))
        with self.assertRaises(VerificationError):
            build_model(ctx, ident, [['c', 'S']], [0])


class ConvexSuffixTinyLedgers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from timecut5.hierarchy import solve_hierarchical
        from timecut5.invocation_trace import InvocationTrace
        from timecut5.provenance import Recorder
        from validation.trace5 import verify_trace
        from validation.suffix5.convex_query import solve_query
        cls.ledgers = []
        for name in ('cross_both', 'no_curve'):
            case = tiny_case(name)
            case['H_ref'] = 1
            if case['charging_segments']:
                case['charging_segments'] = [[lo, hi, slope, intercept-7]
                                             for lo, hi, slope, intercept in CURVE]
            with Recorder() as recorder, InvocationTrace(recorder) as trace:
                solve_hierarchical(case)
            stream, bundle = trace.export(), recorder.export()
            bundle['roots'] = stream['events'][-1]['payload']['terminal_families']
            checked = verify_trace(stream, bundle, case)
            queries = checked.export_queries()
            if not queries:
                raise AssertionError('tiny ledger fixture produced no query')
            ledger = solve_query(checked, queries[0]['query_seq'],
                                 SolveBudget(max_passes=40, wall_seconds=30, rss_mib=256))
            cls.ledgers.append((checked, ledger))

    def test_complete_convex_and_no_curve_queries(self):
        from validation.suffix5.convex_checker import check_query_ledger
        from validation.suffix5.convex_evidence import check_query_witness
        for checked, ledger in self.ledgers:
            with self.subTest(case=checked.bundle._physics.case['case_id']):
                audit = check_query_ledger(checked, ledger, with_audit=True)
                self.assertEqual(audit['result'], ledger['result'])
                self.assertTrue(audit['audit']['bound_valid'])
                slot, record = next((slot, row) for slot, row in enumerate(ledger['models'])
                                    if row['result'] == ledger['result'])
                evidence = lift_point(checked.bundle, record['model'], solution_point(record))
                check_query_witness(checked, ledger, slot, evidence, result_contract(record['result']))

    def test_missing_repeated_or_reordered_band_regimes_reject(self):
        from validation.suffix5.convex_checker import check_query_ledger
        checked, original = self.ledgers[0]
        self.assertEqual(len(original['models']), 3)
        for mode in ('missing', 'repeat', 'reorder', 'band', 'strict', 'support', 'result'):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                ledger = deepcopy(original)
                if mode == 'missing':
                    ledger['models'].pop()
                elif mode == 'repeat':
                    ledger['models'][1] = deepcopy(ledger['models'][0])
                elif mode == 'reorder':
                    ledger['models'].reverse()
                elif mode == 'band':
                    ledger['models'][0]['model']['arrival_bands'] = [1]
                elif mode == 'strict':
                    row = next(r for r in ledger['models'][0]['model']['lp']['rows']
                               if r['label'] == 'charge_positive:0')
                    row['strict'] = False
                elif mode == 'support':
                    ledger['models'][0]['model']['lp']['rows'] = [
                        r for r in ledger['models'][0]['model']['lp']['rows']
                        if r['label'] != 'charge_completion:0:2']
                else:
                    ledger['result']['J'] = '0'
                check_query_ledger(checked, ledger)

    def test_exhausted_budget_keeps_partial_v2_evidence_unresolved(self):
        from validation.suffix5.convex_query import solve_query
        from validation.suffix5.query import UnresolvedQuery
        checked, ledger = self.ledgers[0]
        with self.assertRaises(UnresolvedQuery) as raised:
            solve_query(checked, ledger['query_seq'], SolveBudget(max_passes=1))
        self.assertEqual(len(raised.exception.planned_models), 3)
        self.assertEqual(raised.exception.failed_regime['status'], 'unresolved')
        self.assertEqual(raised.exception.partial_records, [])


if __name__ == '__main__':
    unittest.main()
