"""Hand-authored physical evidence and adversarial suffix replay tests.

No candidate model, witness builder, production code, or LP implementation is
used to construct these checks.  Each tiny route has explicit primitive events.
"""
from copy import deepcopy
from fractions import Fraction as F
import unittest

from validation.family5 import VerificationError, check_witness, reconstruct, verify_bundle
from validation.family5.checker import digest
from validation.family5.test_checker_units import hand_bundle
from validation.suffix5.witness_checker import verify_witness


def initial_context(**changes):
    case = dict(case_id='suffix-witness-hand-authored', H_ref=4, origin='o', destination='z',
                start_time_s=0, initial_energy_kwh=2, capacity_kwh=5, minimum_energy_kwh=0,
                reserve_kwh=0, overhead_s=1, lambda_stop_s=0, consumption_kwh_per_m=1,
                schedule=None, sites={'c': ['C']}, charging_segments=[[0, 5, 1, 7]],
                edges=[dict(source='o', target='c', time_s=1, length_m=1),
                       dict(source='c', target='z', time_s=1, length_m=1)])
    case.update(changes)
    remaining = case.get('initial_remaining_schedule', int(case['schedule'] is not None))
    energy, start = str(case['initial_energy_kwh']), str(case['start_time_s'])
    output = dict(domain=[energy, energy, True, True], m='0', b=start, chi=True,
                  rho=str(-F(energy)), pi=[], state=[case['origin'], remaining, 0])
    node = dict(kind='initial', parents=[], output=output, params={'case': case})
    ident = digest(node)
    bundle = dict(schema='family5-v1', nodes={ident: node}, batches=[], batch_ids=[], roots=[ident])
    return verify_bundle(bundle, case), ident


def event(effect, site, t, u, x, y):
    return dict(effect=effect, site=site, arrival_time=str(t), departure_time=str(u),
                arrival_energy=str(x), departure_energy=str(y))


def evidence(prefix, events, *, time, energy, rho, pi, destination='z'):
    return dict(prefix=prefix, suffix_events=events,
                witness=dict(time=str(time), energy=str(energy), rho=str(rho), pi=pi,
                             state=[destination, 0, len(pi)],
                             events=prefix['witness']['events'] + deepcopy(events)))


def one_stop(effect='C', q=F(1), *, schedule=None, budget='0', **case_changes):
    ctx, ident = initial_context(sites={'c': [effect]}, schedule=schedule, **case_changes)
    prefix = reconstruct(ctx, ident, '2', budget)
    completion = 2 + q if effect != 'S' else F(2)
    if schedule is not None and effect in ('S', 'CS'):
        completion = max(completion, F(schedule['a']) + F(schedule['D']))
    events = [event('D', 'c', 0, 1, 2, 1),
              event(effect, 'c', 1, completion, 1, 1 + q),
              event('D', 'z', completion, completion + 1, 1 + q, q)]
    data = evidence(prefix, events, time=completion + 1, energy=q, rho=0, pi=[['c', effect]])
    contract = dict(kind='minimum', J=str(completion + 1), Q_total=str(q), H=1, pi=[['c', effect]])
    return ctx, ident, [['c', effect]], data, contract


class PhysicalSuffixWitnessTests(unittest.TestCase):
    def test_hand_authored_charge_and_affine_intercept_cancellation(self):
        args = one_stop()
        audit = verify_witness(*args)
        self.assertEqual(audit['key'], ['4', '1', 1, [['c', 'C']]])
        self.assertEqual(audit['prefix'], dict(energy='2', budget='0', time='0'))
        self.assertEqual(audit['charges'], ['1'])
        self.assertEqual(audit['selected_legs'][0]['edge_ids'], ['input:00000000'])
        self.assertEqual(audit['selected_legs'][1]['path'], ['c', 'z'])

    def test_s_and_cs_use_schedule_release_max(self):
        for effect, q in [('S', F(0)), ('CS', F(1))]:
            with self.subTest(effect=effect):
                args = one_stop(effect, q, schedule=dict(a=10, b=10, D=3))
                audit = verify_witness(*args)
                self.assertEqual(audit['J'], '14')
                self.assertEqual(audit['Q_total'], str(q))

    def test_cs_charge_dominates_schedule_completion(self):
        args = one_stop('CS', F(4), schedule=dict(a=0, b=2, D=1))
        self.assertEqual(verify_witness(*args)['J'], '7')

    def test_repeated_site_has_explicit_identity_leg(self):
        ctx, ident = initial_context(sites={'c': ['C', 'S']}, schedule=dict(a=10, b=10, D=3))
        prefix = reconstruct(ctx, ident, '2', '0')
        events = [event('D', 'c', 0, 1, 2, 1), event('C', 'c', 1, 3, 1, 2),
                  event('D', 'c', 3, 3, 2, 2), event('S', 'c', 3, 13, 2, 2),
                  event('D', 'z', 13, 14, 2, 1)]
        pi = [['c', 'C'], ['c', 'S']]
        data = evidence(prefix, events, time=14, energy=1, rho=0, pi=pi)
        contract = dict(kind='minimum', J='14', Q_total='1', H=2, pi=pi)
        audit = verify_witness(ctx, ident, pi, data, contract)
        self.assertEqual(audit['selected_legs'][1]['path'], ['c'])
        self.assertEqual(audit['selected_legs'][1]['edge_ids'], [])

    def test_ancestral_family_cannot_be_rebound_to_same_final_cut(self):
        case, bundle, ids = hand_bundle()
        ctx = verify_bundle(bundle, case)
        prefix = reconstruct(ctx, ids['A'], '3', '5')
        events = [event('D', 'c', 5, 5, 3, 3), event('C', 'c', 5, 7, 3, 4),
                  event('D', 'z', 7, 8, 4, 3)]
        pi = [['c', 'C']] * 3
        data = evidence(prefix, events, time=8, energy=3, rho=0, pi=pi)
        contract = dict(kind='minimum', J='8', Q_total='3', H=3, pi=pi)
        verify_witness(ctx, ids['A'], [['c', 'C']], data, contract)
        with self.assertRaisesRegex(VerificationError, 'inherited_energy_guard'):
            verify_witness(ctx, ids['B'], [['c', 'C']], data, contract)

    def test_prefix_budget_is_not_free_waiting(self):
        args = one_stop(budget='20')
        self.assertEqual(verify_witness(*args)['J'], '4')
        ctx, ident, word, data, contract = args
        for event_ in data['suffix_events']:
            event_['arrival_time'] = str(F(event_['arrival_time']) + 20)
            event_['departure_time'] = str(F(event_['departure_time']) + 20)
        data['witness']['events'] = data['prefix']['witness']['events'] + deepcopy(data['suffix_events'])
        data['witness']['time'] = '24'
        contract['J'] = '24'
        with self.assertRaisesRegex(VerificationError, 'selected_drive_event_mismatch'):
            verify_witness(ctx, ident, word, data, contract)

    def test_prefix_receipt_requires_every_budget_annotation(self):
        ctx, ident, word, data, contract = one_stop()
        prefix = data['prefix']
        prefix['receipt'] = check_witness(ctx, ident, prefix['witness'], prefix['receipt']['contract'])
        with self.assertRaisesRegex(VerificationError, 'missing_reconstruction_budget_annotations'):
            verify_witness(ctx, ident, word, data, contract)

    def test_full_metadata_bool_int_float_and_container_aliases_reject(self):
        for field, value in [('state', ['z', False, 1]), ('state', ['z', 0, True]),
                             ('state', ['z', 0, 1.0]), ('rho', 0),
                             ('pi', (('c', 'C'),))]:
            ctx, ident, word, data, contract = one_stop()
            data['witness'][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(VerificationError):
                verify_witness(ctx, ident, word, data, contract)
        for value in (True, 1.0):
            ctx, ident, word, data, contract = one_stop()
            contract['H'] = value
            with self.subTest(H=value), self.assertRaises(VerificationError):
                verify_witness(ctx, ident, word, data, contract)

    def test_event_and_full_prefix_chain_mutations_reject(self):
        for field, value in [('arrival_energy', '3'), ('site', 'z'), ('departure_time', '5'),
                             ('departure_energy', True), ('arrival_time', '0/1')]:
            ctx, ident, word, data, contract = one_stop()
            data['suffix_events'][0][field] = value
            with self.subTest(field=field), self.assertRaises(VerificationError):
                verify_witness(ctx, ident, word, data, contract)
        ctx, ident, word, data, contract = one_stop()
        del data['witness']['events'][0]
        with self.assertRaisesRegex(VerificationError, 'full_witness_mismatch'):
            verify_witness(ctx, ident, word, data, contract)

    def test_c_and_cs_strict_charge_reject_zero_but_accept_tiny_positive(self):
        for effect, schedule in [('C', None), ('CS', dict(a=10, b=10, D=3))]:
            with self.subTest(effect=effect):
                with self.assertRaisesRegex(VerificationError, 'strict_charge_required'):
                    verify_witness(*one_stop(effect, F(0), schedule=schedule))
                audit = verify_witness(*one_stop(effect, F(1, 10**100), schedule=schedule))
                self.assertEqual(F(audit['Q_total']), F(1, 10**100))

    def test_no_approach_is_given_an_attained_key(self):
        ctx, ident, word, data, _ = one_stop(q=F(1, 10))
        audit = verify_witness(ctx, ident, word, data,
                               dict(kind='primary_approach', J_inf='3', epsilon='1/5'))
        self.assertEqual(audit['J'], '31/10')
        self.assertNotIn('key', audit)
        ctx, ident, word, data, _ = one_stop('CS', F(1, 10), schedule=dict(a=10, b=10, D=3))
        audit = verify_witness(ctx, ident, word, data,
                               dict(kind='secondary_approach', J='14', Q_inf='0', epsilon='1/5'))
        self.assertEqual(audit['Q_total'], '1/10')
        self.assertNotIn('key', audit)

    def test_approach_requires_positive_gap_and_strict_epsilon(self):
        ctx, ident, word, data, _ = one_stop()
        for contract in [dict(kind='primary_approach', J_inf='4', epsilon='1'),
                         dict(kind='primary_approach', J_inf='3', epsilon='1'),
                         dict(kind='primary_approach', J_inf='3', epsilon='0'),
                         dict(kind='primary_approach', J_inf='5', epsilon='2'),
                         dict(kind='secondary_approach', J='4', Q_inf='1', epsilon='1'),
                         dict(kind='secondary_approach', J='4', Q_inf='0', epsilon='1'),
                         dict(kind='secondary_approach', J='3', Q_inf='0', epsilon='2')]:
            with self.subTest(contract=contract), self.assertRaises(VerificationError):
                verify_witness(ctx, ident, word, data, contract)

    def test_schedule_deadline_unfulfilled_and_duplicate_service_reject(self):
        for schedule in [dict(a=0, b=1, D=3), dict(a=10, b=9, D=3)]:
            with self.subTest(schedule=schedule), self.assertRaisesRegex(VerificationError, 'service_deadline'):
                verify_witness(*one_stop('S', F(0), schedule=schedule))
        with self.assertRaisesRegex(VerificationError, 'terminal_unfulfilled_schedule'):
            verify_witness(*one_stop('C', schedule=dict(a=10, b=10, D=3)))
        with self.assertRaisesRegex(VerificationError, 'invalid_service_state'):
            verify_witness(*one_stop('S', F(0), schedule=dict(a=10, b=10, D=3),
                                    initial_remaining_schedule=0))

    def test_floor_reserve_capacity_and_stop_bound_reject(self):
        for changes in [dict(minimum_energy_kwh=2, reserve_kwh=2),
                        dict(reserve_kwh=2), dict(H_ref=0)]:
            with self.subTest(changes=changes), self.assertRaises(VerificationError):
                verify_witness(*one_stop(**changes))
        with self.assertRaisesRegex(VerificationError, 'stop_inventory_bounds'):
            verify_witness(*one_stop(q=F(5)))

    def test_unavailable_effect_word_terminal_stop_and_empty_word_reject(self):
        for word in [[['c', 'S']], [['missing', 'C']], [], [('c', 'C')]]:
            ctx, ident, _, data, contract = one_stop()
            with self.subTest(word=word), self.assertRaises(VerificationError):
                verify_witness(ctx, ident, word, data, contract)
        with self.assertRaisesRegex(VerificationError, 'stop_at_destination'):
            verify_witness(*one_stop(site_anchors={'c': 'z'}))

    def test_missing_selected_leg_and_multiple_curve_segments_reject(self):
        with self.assertRaisesRegex(VerificationError, 'unreachable_selected_leg'):
            verify_witness(*one_stop(edges=[]))
        with self.assertRaisesRegex(VerificationError, 'one_affine_charging_segment'):
            verify_witness(*one_stop(charging_segments=[[0, 2, 1, 7], [2, 5, 2, 5]]))

    def test_original_start_and_total_stop_penalty_are_used(self):
        ctx, ident = initial_context(start_time_s=5, lambda_stop_s=3)
        prefix = reconstruct(ctx, ident, '2', '5')
        events = [event('D', 'c', 5, 6, 2, 1), event('C', 'c', 6, 8, 1, 2),
                  event('D', 'z', 8, 9, 2, 1)]
        pi = [['c', 'C']]
        data = evidence(prefix, events, time=9, energy=1, rho=0, pi=pi)
        contract = dict(kind='minimum', J='7', Q_total='1', H=1, pi=pi)
        self.assertEqual(verify_witness(ctx, ident, pi, data, contract)['J'], '7')

    def test_road_anchor_text_is_never_remapped_as_an_unrelated_site(self):
        ctx, ident = initial_context(origin='road',
            sites={'road': ['C'], 'c': ['C']}, site_anchors={'road': 'unrelated', 'c': 'c'},
            edges=[dict(source='road', target='c', time_s=1, length_m=1),
                   dict(source='c', target='z', time_s=1, length_m=1)])
        prefix = reconstruct(ctx, ident, '2', '0')
        events = [event('D', 'c', 0, 1, 2, 1), event('C', 'c', 1, 3, 1, 2),
                  event('D', 'z', 3, 4, 2, 1)]
        pi = [['c', 'C']]
        data = evidence(prefix, events, time=4, energy=1, rho=0, pi=pi)
        contract = dict(kind='minimum', J='4', Q_total='1', H=1, pi=pi)
        audit = verify_witness(ctx, ident, pi, data, contract)
        self.assertEqual(audit['selected_legs'][0]['source'], 'road')

    def test_original_prefix_must_be_initial_or_post_stop_anchor(self):
        case, bundle, _ = hand_bundle()
        ctx = verify_bundle(bundle, case)
        ident = next(k for k, v in bundle['nodes'].items() if v['kind'] == 'drive')
        prefix = reconstruct(ctx, ident, '1', '1')
        events = [event('D', 'c', 1, 1, 1, 1), event('C', 'c', 1, 3, 1, 2),
                  event('D', 'z', 3, 4, 2, 1)]
        pi = [['c', 'C']]
        data = evidence(prefix, events, time=4, energy=1, rho=0, pi=pi)
        contract = dict(kind='minimum', J='4', Q_total='1', H=1, pi=pi)
        with self.assertRaisesRegex(VerificationError, 'prefix_not_initial_or_post_stop_anchor'):
            verify_witness(ctx, ident, pi, data, contract)

    def test_second_service_is_rejected(self):
        ctx, ident = initial_context(sites={'c': ['S']}, schedule=dict(a=10, b=20, D=3))
        prefix = reconstruct(ctx, ident, '2', '0')
        events = [event('D', 'c', 0, 1, 2, 1), event('S', 'c', 1, 13, 1, 1),
                  event('D', 'c', 13, 13, 1, 1), event('S', 'c', 13, 17, 1, 1),
                  event('D', 'z', 17, 18, 1, 0)]
        pi = [['c', 'S'], ['c', 'S']]
        data = evidence(prefix, events, time=18, energy=0, rho=0, pi=pi)
        contract = dict(kind='minimum', J='18', Q_total='0', H=2, pi=pi)
        with self.assertRaisesRegex(VerificationError, 'invalid_service_state'):
            verify_witness(ctx, ident, pi, data, contract)

    def test_nonselected_slower_leg_and_positive_service_charge_reject(self):
        ctx, ident, word, data, contract = one_stop()
        data['suffix_events'][0]['departure_time'] = '2'
        with self.assertRaisesRegex(VerificationError, 'selected_drive_event_mismatch'):
            verify_witness(ctx, ident, word, data, contract)
        with self.assertRaisesRegex(VerificationError, 'service_changes_inventory'):
            verify_witness(*one_stop('S', F(1), schedule=dict(a=10, b=10, D=3)))


if __name__ == '__main__':
    unittest.main()
