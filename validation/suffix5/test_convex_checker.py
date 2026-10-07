"""Independently authored v2 proofs and physics, with no candidate imports."""
from copy import deepcopy
from fractions import Fraction as F
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import unittest

from validation.family5 import VerificationError, reconstruct, verify_bundle
from validation.family5.checker import digest
from validation.trace5 import verify_trace
from .independent_convex_model import (SuffixVerificationError, build_model,
    build_models, closed_task, strict_task, enumerate_words, validate_curve)
from .convex_checker import check_regime, check_query_ledger, aggregate_records
from .convex_witness_checker import verify_witness, _check_curve
from .convex_evidence import check_result_witness, check_query_witness
from .test_certificate_checker import initial_context, certificate, inherited_open_context
from .test_witness_checker import event, evidence

CURVE = [[0, 2, 1, 7], [2, 4, 2, 5], [4, 5, 4, -3]]


def context(effect='C', **changes):
    changes.setdefault('charging_segments', CURVE)
    return initial_context(effect, **changes)


def hand_record(effect='C', band=1, attained=False):
    ctx, ident = context(effect, reserve_kwh=2 if attained else 0)
    model = build_model(ctx, ident, [['s', effect]], [None if effect == 'S' else band])
    labels = {row['label']: i for i, row in enumerate(model['lp']['rows'])}
    stages = []
    def add(name, task, x, weights=(), z=None):
        dual = [(labels[key] if isinstance(key, str) else key, value) for key, value in weights]
        stages.append(dict(name=name, task=task, certificate=certificate(task, x, dual, z)))
    strict = strict_task(model)
    if effect != 'S' and band == 2:
        # Original E=2 and this arrival band's E>=4 conflict. Their equally
        # weighted relaxed rows prove Phase-I minimum one, without an LP solve.
        phase = dict(c=['0']*5+['1'], A=[row+['-1'] for row in strict['A']]+[['0']*5+['-1']],
                     b=strict['b']+['0'], equalities=[])
        proof = certificate(phase, [3, 0, 1, 20, 1, 1],
                            [(labels['prefix_energy_upper'], '-1/2'),
                             (labels['arrival_band_lower:0'], '-1/2')])
        stages.append(dict(name='feasibility', task=strict,
                           certificate=dict(status='infeasible', phase_I_certificate=proof)))
        return ctx, dict(model=model, stages=stages, result=dict(status='closed_infeasible'))
    add('feasibility', strict, [2, 0, 0 if effect == 'S' else 1, 13, 1],
        [(len(strict['A'])-1, -1)])
    completion = 3 if attained else (1 if effect == 'C' else 13)
    q = 1 if attained else 0
    if effect == 'C':
        difference = 1 if band == 0 else 0
        weights = [('charge_completion:0:1', -1), ('prefix_time', -1)]
        if attained:
            weights += [('terminal_reserve', -2), ('prefix_energy_upper', -(2-difference))]
        else:
            weights += [('charge_positive:0', -2)]
            if difference:
                weights += [('prefix_energy_lower', -difference)]
    else:
        weights = [('service_release_completion:0', -1)]
    add('primary', closed_task(model, 'J'), [2, 0, q, completion], weights)
    faces = [[model['lp']['J']['coefficients'], str(completion)]]
    margin = strict_task(model, faces)
    if effect == 'C' and not attained:
        add('primary_attainment', margin, [2, 0, 0, 1, 0],
            [(name, F(weight, 2)) for name, weight in weights], ['-1/2'])
        result = dict(status='primary_unattained', primary_infimum='2')
        return ctx, dict(model=model, stages=stages, result=result)
    add('primary_attainment', margin, [2, 0, 0 if effect == 'S' else 1, completion, 1],
        [(len(margin['A'])-1, -1)])
    lower = 'service_charge_zero_lower:0' if effect == 'S' else 'charge_positive:0'
    weights = [('terminal_reserve', -1)] if attained else [('prefix_energy_lower', -1), (lower, -1)]
    add('secondary', closed_task(model, 'Q', faces), [2, 0, q, completion], weights)
    faces.append([model['lp']['Q']['coefficients'], str(2+q)])
    margin = strict_task(model, faces)
    if effect == 'CS':
        add('secondary_attainment', margin, [2, 0, 0, completion, 0], weights, [0, -1])
        result = dict(status='secondary_unattained', J='14', secondary_infimum='0')
    else:
        add('secondary_attainment', margin, [2, 0, q, completion, 1], [(len(margin['A'])-1, -1)])
        result = dict(status='attained_optimum', J=str(completion+1), Q_total=str(q), H=1,
                      site_action_tuple=[['s', effect]], lex_key=[str(completion+1), str(q), 1, [['s', effect]]])
    return ctx, dict(model=model, stages=stages, result=result)


def physical(effect='C', energy=F(2), q=F(1), schedule=None, **changes):
    if effect != 'C' and schedule is None:
        schedule = dict(a=10, b=20, D=3)
    ctx, ident = context(effect, initial_energy_kwh=str(energy), schedule=schedule, **changes)
    prefix = reconstruct(ctx, ident, str(energy), '0')
    # Hand-derived original primitive, separately from the checker or model.
    def value(x):
        return x+7 if x <= 2 else 2*x+5 if x <= 4 else 4*x-3
    completion = F(1)+(value(energy+q)-value(energy) if effect != 'S' else 0)
    if effect != 'C':
        completion = max(completion, max(F(schedule['a']), F(1))+F(schedule['D']))
    rows = [event('D', 'o', 0, 0, energy, energy),
            event(effect, 's', 0, completion, energy, energy+q),
            event('D', 'z', completion, completion+1, energy+q, energy+q-1)]
    pi = [['s', effect]]
    data = evidence(prefix, rows, time=completion+1, energy=energy+q-1,
                    rho=1-energy, pi=pi)
    contract = dict(kind='minimum', J=str(completion+1), Q_total=str(q), H=1, pi=pi)
    return ctx, ident, pi, data, contract


def pruned_charge_trace():
    """Entire two-node hand trace: direct finish dominates a charge query."""
    ctx, initial = context('C', H_ref=1)
    bundle = ctx.snapshot()
    case = bundle['nodes'][initial]['params']['case']
    output = dict(domain=['1', '1', True, True], m='0', b='1', chi=True,
                  rho='-1', pi=[], state=['z', 0, 0])
    params = dict(site='z', duration='1', consumption='1', floor='0')
    node = dict(kind='drive', parents=[initial], output=output, params=params)
    terminal = digest(node); bundle['nodes'][terminal] = node
    batch = dict(kind='drive', parents=[initial], outputs=[terminal], params=params)
    bundle['batches'] = [batch]; bundle['batch_ids'] = [digest(batch)]; bundle['roots'] = [terminal]
    witness = dict(time='1', energy='1', rho='-1', pi=[], state=['z', 0, 0],
        events=[event('initial', 'o', 0, 0, 2, 2), event('D', 'z', 0, 1, 2, 1)])
    trace = dict(schema='family5-hier-trace-v1', events=[])
    def emit(kind, **payload):
        seq = len(trace['events'])
        trace['events'].append(dict(seq=seq, kind=kind, payload=payload))
        return seq
    emit('run_start', case_sha256=digest(case), dominance=False, H_ref=1,
         regions=dict(id=0, members=['s'], children=[]))
    emit('invoke', invocation_id=0, operation='initial', input_families=[], output_families=[initial],
         params={}, batch_range=[0, 0])
    emit('layer_start', depth=0, groups=[dict(group_id=0, families=[initial])])
    emit('invoke', invocation_id=1, operation='finish', input_families=[initial], output_families=[terminal],
         params=dict(group_id=0, source='layer', advance_id=None), batch_range=[0, 1])
    key = ['1', '0', 0, []]
    emit('candidate', group_id=0, source='layer', family_id=terminal, energy='1',
         witness=witness, key=key, improved=True)
    emit('expansion_start', group_id=0)
    seq = emit('query', group_id=0, region_id=0, effect='C', actions=[['s', 'C']], bound='2',
               classification='queued', queue_serial=1)
    for effect in ('S', 'CS'):
        emit('query', group_id=0, region_id=0, effect=effect, actions=[], bound=None,
             classification='empty_actions', queue_serial=None)
    emit('pop', group_id=0, query_seq=seq, decision='prune', incumbent_key=key)
    emit('expansion_end', group_id=0, covered_actions=[['s', 'C']])
    emit('layer_end', depth=0, reason='empty', next_groups=[])
    result = dict(status='attained_optimum', J='1', Q_total='0', H=0, site_action_tuple=[],
                  lex_key=key, witness_replayed=True, charges=[])
    emit('run_end', canonical=dict(scope='bounded_H_ref_diagnostic', H_ref=1, result=result),
         terminal_families=[terminal], terminal_family_id=terminal, terminal_witness=witness)
    return verify_trace(trace, bundle, case)


def hand_ledger():
    checked = pruned_charge_trace(); query = checked.export_queries()[0]
    records = []
    for band in range(3):
        _, record = hand_record('C', band)
        record['model'] = build_model(checked.bundle, query['family_ids'][0], [['s', 'C']], [band])
        records.append(record)
    return checked, dict(schema='family5-suffix-query-ledger-v2', query_seq=query['query_seq'],
        query_sha256=digest(query), trace_sha256=checked.summary['trace_sha256'],
        models=records, result=aggregate_records(records))


class IndependentConvexTests(unittest.TestCase):
    def test_independent_hand_certificates_and_attainment(self):
        for effect, band, attained, status in [
            ('C', 0, False, 'primary_unattained'), ('C', 1, False, 'primary_unattained'),
            ('C', 2, False, 'closed_infeasible'), ('CS', 0, False, 'secondary_unattained'),
            ('CS', 1, False, 'secondary_unattained'), ('S', 0, False, 'attained_optimum'),
            ('C', 0, True, 'attained_optimum'), ('C', 1, True, 'attained_optimum')]:
            with self.subTest(effect=effect, band=band, attained=attained):
                ctx, record = hand_record(effect, band, attained)
                self.assertEqual(check_regime(ctx, record)['status'], status)

    def test_exact_zero_and_arbitrarily_small_strict_margin(self):
        from .checker import verify_lp_certificate
        for tiny in [F(0), F(1, 10**100)]:
            ctx, ident = context('C', initial_energy_kwh=str(5-tiny))
            model = build_model(ctx, ident, [['s', 'C']], [2])
            task = strict_task(model)
            labels = {row['label']: i for i, row in enumerate(model['lp']['rows'])}
            weights = [(labels[name], -1) for name in
                       ['departure_capacity:0', 'prefix_energy_lower', 'charge_positive:0']]
            proof = certificate(task, [5-tiny, 0, tiny, 1+4*tiny, tiny], weights)
            self.assertEqual(verify_lp_certificate(task, proof)['objective'], str(-tiny))
            if tiny == 0:
                record = dict(model=model, stages=[dict(name='feasibility', task=task, certificate=proof)],
                              result=dict(status='strict_infeasible'))
                self.assertEqual(check_regime(ctx, record)['status'], 'strict_infeasible')

    def test_complete_no_curve_service_ledger_preserves_empty_primitive(self):
        from .test_certificate_checker import hand_ledger as affine_ledger
        from validation.trace5.test_checker_units import hand_trace
        case, bundle, trace = hand_trace()
        checked = verify_trace(trace, bundle, case)
        _, old = affine_ledger()
        query = checked.export_queries()[0]
        ledger = deepcopy(old)
        ledger.update(schema='family5-suffix-query-ledger-v2', query_seq=query['query_seq'],
                      query_sha256=digest(query), trace_sha256=checked.summary['trace_sha256'])
        for record in ledger['models']:
            record['model'] = build_models(checked.bundle, query['family_ids'][0], record['model']['word'])[0]
        self.assertEqual(check_query_ledger(checked, ledger)['lex_key'], ['3', '0', 1, [['s', 'S']]])
        self.assertEqual(checked.bundle._physics.curve, ())
        self.assertEqual([record['model']['arrival_bands'] for record in ledger['models']], [[None], None])

    def test_support_rows_include_original_intercepts_and_all_previous_charges(self):
        ctx, ident = context('C', H_ref=3)
        model = build_model(ctx, ident, [['s', 'C'], ['s', 'C']], [0, 1])
        rows = {row['label']: row for row in model['lp']['rows']}
        self.assertEqual(rows['charge_completion:0:2']['coefficients'], ['3', '1', '4', '-1', '0', '0'])
        self.assertEqual(rows['charge_completion:0:2']['rhs'], '9')
        self.assertEqual(rows['charge_completion:1:2']['coefficients'], ['2', '0', '2', '1', '4', '-1'])
        self.assertEqual(rows['charge_completion:1:2']['rhs'], '7')
        self.assertEqual(rows['arrival_band_lower:1']['coefficients'], ['-1', '0', '-1', '0', '0', '0'])
        self.assertEqual(rows['arrival_band_lower:1']['rhs'], '-2')
        self.assertFalse(rows['arrival_band_lower:1']['strict'])

    def test_nonzero_incoming_consumption_support_rhs(self):
        ctx, ident = context('C', site_anchors={'s': 's'}, edges=[
            dict(source='o', target='s', time_s=2, length_m=1),
            dict(source='s', target='z', time_s=1, length_m=1)])
        rows = {row['label']: row for row in build_model(ctx, ident, [['s', 'C']], [0])['lp']['rows']}
        self.assertEqual(rows['charge_completion:0:2']['rhs'], '10')
        self.assertEqual(rows['arrival_band_lower:0']['rhs'], '-1')
        self.assertEqual(rows['arrival_band_upper:0']['rhs'], '3')

    def test_band_products_service_slots_and_graph_singleton(self):
        ctx, ident = context('CS', H_ref=3, sites={'s': ['C', 'S', 'CS']})
        models = build_models(ctx, ident, [['s', 'C'], ['s', 'S'], ['s', 'C']])
        self.assertEqual([m['arrival_bands'] for m in models],
                         [[a, None, b] for a in range(3) for b in range(3)])
        ctx, ident = context('C', edges=[])
        models = build_models(ctx, ident, [['s', 'C']])
        self.assertEqual(len(models), 1)
        self.assertIsNone(models[0]['arrival_bands'])
        self.assertIsNone(models[0]['lp'])
        check_regime(ctx, dict(model=models[0], stages=[], result=dict(status='graph_unreachable')))

    def test_no_curve_has_only_genuine_service_words(self):
        ctx, ident = context('S', charging_segments=[])
        word = [['s', 'S']]
        self.assertEqual(enumerate_words(ctx, ident, word), [word])
        models = build_models(ctx, ident, word)
        self.assertEqual([model['arrival_bands'] for model in models], [[None]])
        self.assertFalse(any('charge_completion' in row['label'] for row in models[0]['lp']['rows']))
        self.assertEqual(ctx._physics.curve, ())
        _, record = hand_record('S')
        record['model'] = models[0]
        self.assertEqual(check_regime(ctx, record)['status'], 'attained_optimum')
        args = physical('S', q=F(0), charging_segments=[])
        self.assertEqual(verify_witness(*args)['J'], '14')
        with self.assertRaises(VerificationError):
            context('C', charging_segments=[])
        with self.assertRaises(SuffixVerificationError):
            build_model(ctx, ident, [['s', 'C']], [0])

    def test_original_open_energy_and_time_keep_their_exact_flags(self):
        ctx, ident = inherited_open_context()
        model = build_model(ctx, ident, [['o', 'C']], [0])
        self.assertEqual([row['strict'] for row in model['lp']['rows'][:3]], [True]*3)
        self.assertEqual([row['rhs'] for row in model['lp']['rows'][:3]], ['-3', '4', '-11'])
        margin = strict_task(model, [[model['lp']['J']['coefficients'], '12']])
        self.assertEqual(margin['equalities'][0][0][-1], '0')
        self.assertEqual(model['H'], 3)
        self.assertEqual(model['lp']['Q']['constant'], '-2')

    def test_band_wire_types_range_and_missing_assignments_reject(self):
        ctx, ident = context('C')
        for bands in [None, [], [True], [1.0], ['1'], [-1], [3], [None], [0, 1]]:
            with self.subTest(bands=bands), self.assertRaises(SuffixVerificationError):
                build_model(ctx, ident, [['s', 'C']], bands)

    def test_missing_or_altered_support_rows_and_strict_flags_reject(self):
        ctx, record = hand_record('C')
        for kind in ['missing_support', 'intercept', 'strict', 'band', 'result', 'certificate']:
            bad = deepcopy(record)
            rows = bad['model']['lp']['rows']
            row = next(row for row in rows if row['label'] == 'charge_completion:0:2')
            if kind == 'missing_support': rows.remove(row)
            elif kind == 'intercept': row['rhs'] = '8'
            elif kind == 'strict': next(r for r in rows if r['label'] == 'charge_positive:0')['strict'] = False
            elif kind == 'band': bad['model']['arrival_bands'] = [0]
            elif kind == 'result': bad['result']['primary_infimum'] = '1'
            else: bad['stages'][1]['certificate']['objective'] = '0'
            with self.subTest(kind=kind), self.assertRaises(SuffixVerificationError):
                check_regime(ctx, bad)

    def test_complete_original_query_covers_every_band_exactly(self):
        checked, ledger = hand_ledger()
        audit = check_query_ledger(checked, ledger, with_audit=True)
        self.assertEqual(audit['result'], dict(status='primary_unattained', primary_infimum='2'))
        self.assertEqual(audit['audit']['regime_count'], 3)
        self.assertEqual(audit['audit']['primary_tied_regimes'], [0, 1])
        self.assertTrue(audit['audit']['bound_valid'])
        for kind in ['missing', 'duplicate', 'reorder', 'foreign_band', 'hash']:
            bad = deepcopy(ledger)
            if kind == 'missing': bad['models'].pop()
            elif kind == 'duplicate': bad['models'][2] = deepcopy(bad['models'][1])
            elif kind == 'reorder': bad['models'].reverse()
            elif kind == 'foreign_band': bad['models'][0]['model']['arrival_bands'] = [2]
            else: bad['query_sha256'] = '0'*64
            with self.subTest(kind=kind), self.assertRaises(SuffixVerificationError):
                check_query_ledger(checked, bad)

    def test_curve_validation_fails_closed_in_both_independent_paths(self):
        curves = [ [[0, 2, 2, 0], [2, 5, 1, 2]],
                   [[0, 2, 1, 0], [2, 5, 2, 0]],
                   [[0, 2, 1, 0], [3, 5, 2, -4]],
                   [[0, 3, 1, 0], [2, 5, 2, -2]],
                   [[1, 5, 1, 0]], [[0, 4, 1, 0]], [[0, 5, 0, 0]], [] ]
        for curve in curves:
            ph = SimpleNamespace(curve=tuple(tuple(map(F, row)) for row in curve), capacity=F(5), sites={'s': ('C',)})
            with self.subTest(curve=curve):
                with self.assertRaises(VerificationError): validate_curve(ph)
                with self.assertRaises(VerificationError): _check_curve(ph)
        ctx, ident = context('S', charging_segments=[[0, 2, 2, 0], [2, 5, 1, 2]])
        with self.assertRaisesRegex(SuffixVerificationError, 'nonconvex'):
            build_models(ctx, ident, [['s', 'S']])
        with self.assertRaisesRegex(VerificationError, 'nonconvex'):
            verify_witness(*physical('S', q=F(0), charging_segments=[[0, 2, 2, 0], [2, 5, 1, 2]]))

    def test_breakpoint_physical_replay_and_both_thresholds(self):
        for arrival, departure in [(0, 2), (1, 2), (2, 3), (2, 4), (3, 4), (4, 5), (1, 5), (0, 5)]:
            with self.subTest(arrival=arrival, departure=departure):
                args = physical(energy=F(arrival), q=F(departure-arrival))
                audit = verify_witness(*args)
                self.assertEqual(audit['Q_total'], str(departure-arrival))
                ctx, ident, word, data, _ = args
                t = data['suffix_events'][1]['departure_time']
                point = list(map(F, [str(arrival), '0', str(departure-arrival), t]))
                matching = []
                for model in build_models(ctx, ident, word):
                    valid = all(sum(F(a)*b for a, b in zip(row['coefficients'], point)) <= F(row['rhs'])
                                for row in model['lp']['rows'])
                    if valid: matching.append(model['arrival_bands'][0])
                expected = [i for i, (lo, hi, _, _) in enumerate(CURVE) if lo <= arrival <= hi]
                self.assertEqual(matching, expected)
        self.assertEqual(verify_witness(*physical(energy=F(1), q=F(4)))['J'], '11')

    def test_q_tends_to_zero_at_each_internal_breakpoint(self):
        tiny = F(1, 10**100)
        for energy in [F(2), F(4)]:
            args = physical(energy=energy, q=tiny)
            self.assertEqual(F(verify_witness(*args)['Q_total']), tiny)
            with self.assertRaisesRegex(VerificationError, 'strict_charge'):
                verify_witness(*physical(energy=energy, q=F(0)))

    def test_cs_release_charge_switch_deadline_equality_and_service(self):
        for effect, q, schedule, expected in [
            ('S', F(0), dict(a=1, b=1, D=0), '2'),
            ('CS', F(1), dict(a=10, b=10, D=3), '14'),
            ('CS', F(3), dict(a=0, b=1, D=1), '10'),
            ('CS', F(1), dict(a=0, b=1, D=2), '4')]:
            self.assertEqual(verify_witness(*physical(effect, q=q, schedule=schedule))['J'], expected)
        for schedule in [dict(a=2, b=1, D=0), dict(a=0, b=0, D=3)]:
            with self.assertRaisesRegex(VerificationError, 'deadline'):
                verify_witness(*physical('S', q=F(0), schedule=schedule))

    def test_result_and_query_witness_bindings_and_approaches(self):
        ctx, record = hand_record('C', 1, True)
        _, _, _, data, contract = physical(reserve_kwh=2)
        data['prefix'] = reconstruct(ctx, record['model']['family_id'], '2', '0')
        data['witness']['events'] = data['prefix']['witness']['events']+data['suffix_events']
        self.assertEqual(check_result_witness(ctx, record, data, contract)['key'], ['4', '1', 1, [['s', 'C']]])
        bad = deepcopy(contract); bad['J'] = '3'
        with self.assertRaises(VerificationError): check_result_witness(ctx, record, data, bad)
        for effect, contract in [
            ('C', dict(kind='primary_approach', J_inf='2', epsilon='1/2')),
            ('CS', dict(kind='secondary_approach', J='14', Q_inf='0', epsilon='1/2'))]:
            ctx, record = hand_record(effect, 1)
            _, _, _, data, _ = physical(effect, q=F(1, 10))
            data['prefix'] = reconstruct(ctx, record['model']['family_id'], '2', '0')
            data['witness']['events'] = data['prefix']['witness']['events']+data['suffix_events']
            audit = check_result_witness(ctx, record, data, contract)
            self.assertNotIn('key', audit)
        checked, ledger = hand_ledger()
        family = ledger['models'][1]['model']['family_id']
        _, _, _, data, _ = physical(q=F(1, 10))
        data['prefix'] = reconstruct(checked.bundle, family, '2', '0')
        data['witness']['events'] = data['prefix']['witness']['events']+data['suffix_events']
        contract = dict(kind='primary_approach', J_inf='2', epsilon='1/2')
        self.assertEqual(check_query_witness(checked, ledger, 1, data, contract)['kind'], 'primary_approach')
        with self.assertRaises(VerificationError): check_query_witness(checked, ledger, 2, data, contract)

    def test_valid_physical_approach_outside_selected_regime_band_rejects(self):
        ctx, ident = context('CS', sites={'s': ['CS', 'C']})
        word = [['s', 'CS'], ['s', 'C']]
        model = build_model(ctx, ident, word, [1, 1])
        labels = {row['label']: i for i, row in enumerate(model['lp']['rows'])}
        stages = []
        task = strict_task(model)
        stages.append(dict(name='feasibility', task=task,
            certificate=certificate(task, [2, 0, 1, 13, 1, 16, 1], [(len(task['A'])-1, -1)])))
        task = closed_task(model, 'J')
        weights = [(labels['service_release_completion:0'], -1),
                   (labels['charge_completion:1:1'], -1),
                   (labels['charge_positive:1'], -2)]
        stages.append(dict(name='primary', task=task,
            certificate=certificate(task, [2, 0, 1, 13, 0, 14], weights)))
        task = strict_task(model, [[model['lp']['J']['coefficients'], '14']])
        stages.append(dict(name='primary_attainment', task=task,
            certificate=certificate(task, [2, 0, 1, 13, 0, 14, 0],
                                    [(index, F(weight, 2)) for index, weight in weights], ['-1/2'])))
        record = dict(model=model, stages=stages,
                      result=dict(status='primary_unattained', primary_infimum='15'))
        self.assertEqual(check_regime(ctx, record), record['result'])
        contract = dict(kind='primary_approach', J_inf='15', epsilon='1/10')
        prefix = reconstruct(ctx, ident, '2', '0')
        for first_charge, expected_member in [(F(1), True), (F(2), True), (F(5, 2), False)]:
            arrival = 2+first_charge
            last_charge = F(1, 100)
            last_duration = F(2, 100) if arrival < 4 else F(4, 100)
            completion = 14+last_duration
            rows = [event('D', 'o', 0, 0, 2, 2),
                    event('CS', 's', 0, 13, 2, arrival),
                    event('D', 'o', 13, 13, arrival, arrival),
                    event('C', 's', 13, completion, arrival, arrival+last_charge),
                    event('D', 'z', completion, completion+1, arrival+last_charge, arrival+last_charge-1)]
            data = evidence(prefix, rows, time=completion+1, energy=arrival+last_charge-1,
                            rho=-1, pi=word)
            # All three are valid original-family/word approaches to J_inf=15.
            self.assertEqual(verify_witness(ctx, ident, word, data, contract)['kind'], 'primary_approach')
            if expected_member:
                check_result_witness(ctx, record, data, contract)
            else:
                with self.assertRaisesRegex(VerificationError, 'outside certified arrival band'):
                    check_result_witness(ctx, record, data, contract)

    def test_physical_foreign_prefix_and_intercept_shortcut_reject(self):
        from validation.family5.test_checker_units import hand_bundle
        case, bundle, ids = hand_bundle(); ctx = verify_bundle(bundle, case)
        prefix = reconstruct(ctx, ids['A'], '3', '5')
        rows = [event('D', 'c', 5, 5, 3, 3), event('C', 'c', 5, 7, 3, 4), event('D', 'z', 7, 8, 4, 3)]
        pi = [['c', 'C']]*3
        data = evidence(prefix, rows, time=8, energy=3, rho=0, pi=pi)
        contract = dict(kind='minimum', J='8', Q_total='3', H=3, pi=pi)
        verify_witness(ctx, ids['A'], [['c', 'C']], data, contract)
        with self.assertRaisesRegex(VerificationError, 'inherited_energy_guard'):
            verify_witness(ctx, ids['B'], [['c', 'C']], data, contract)
        ctx, ident, word, data, contract = physical(energy=F(1), q=F(4))
        data['suffix_events'][1]['departure_time'] = '5'
        with self.assertRaisesRegex(VerificationError, 'stop_event_mismatch'):
            verify_witness(ctx, ident, word, data, contract)

    def test_optimizer_disabled_normal_and_optimized_interpreters(self):
        script = r'''
import sys, unittest
class Block:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('numpy','scipy','stopplan4r','hierarchy4r','timecut5','validation.reference5')) or fullname in (
            'validation.suffix5.model','validation.suffix5.query','validation.suffix5.witness',
            'validation.suffix5.solver','validation.suffix5.vendor_lp',
            'validation.suffix5.convex_model','validation.suffix5.convex_query','validation.suffix5.convex_witness'):
            raise RuntimeError('forbidden import '+fullname)
sys.meta_path.insert(0,Block())
from validation.suffix5.test_convex_checker import IndependentConvexTests
names=[name for name in unittest.defaultTestLoader.getTestCaseNames(IndependentConvexTests)
       if name != 'test_optimizer_disabled_normal_and_optimized_interpreters']
result=unittest.TextTestRunner().run(unittest.TestSuite(IndependentConvexTests(name) for name in names))
sys.exit(0 if result.wasSuccessful() else 1)
'''
        for flags in [[], ['-O'], ['-OO']]:
            completed = subprocess.run([sys.executable]+flags+['-c', script],
                cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=60)
            self.assertEqual(completed.returncode, 0, completed.stdout+completed.stderr)


if __name__ == '__main__':
    unittest.main()
