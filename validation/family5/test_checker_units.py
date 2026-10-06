"""Independent hand-authored evidence tests; no production imports."""
from copy import deepcopy
from fractions import Fraction as F
import unittest

from .checker import verify_bundle, reconstruct, check_witness, check_receipt, digest, VerificationError, _fiber_point


def hand_bundle():
    case = dict(case_id='checker-hand-authored-linear', H_ref=4, origin='o', destination='z',
                start_time_s=0, initial_energy_kwh=2, capacity_kwh=5, minimum_energy_kwh=0,
                reserve_kwh=0, overhead_s=1, lambda_stop_s=0, consumption_kwh_per_m=1,
                schedule=None, sites={'c': ['C']}, charging_segments=[[0, 5, 1, 0]],
                edges=[dict(source='o', target='c', time_s=1, length_m=1),
                       dict(source='c', target='z', time_s=1, length_m=1)])
    bundle = dict(schema='family5-v1', nodes={}, batches=[], batch_ids=[], roots=[])
    def node(kind, parents, output, params):
        n = dict(kind=kind, parents=parents, output=output, params=params)
        ident = digest(n); bundle['nodes'][ident] = n
        return ident
    def batch(kind, parents, outputs, params):
        b = dict(kind=kind, parents=parents, outputs=outputs, params=params)
        bundle['batches'].append(b); bundle['batch_ids'].append(digest(b))
    def piece(domain, m, b, rho, count, anchor):
        return dict(domain=domain, m=str(m), b=str(b), chi=True, rho=str(rho),
                    pi=[['c', 'C'] for _ in range(count)], state=[anchor, 0, count])
    root = node('initial', [], piece(['2','2',True,True], 0, 0, -2, 0, 'o'), {'case':case})
    dp = dict(site='c', duration='1', consumption='1', floor='0')
    drive = node('drive', [root], piece(['1','1',True,True], 0, 1, -1, 0, 'c'), dp)
    batch('drive', [root], [drive], dp)
    stop = dict(effect='C',site='c',h='1',a='0',b='0',D='0',curve=[['0','5','1','0']])
    sp = {**stop, 'in_segment':['0','5','1','0'], 'out_segment':['0','5','1','0']}
    first = node('stop', [drive], piece(['1','5',False,True], 1, 1, -1, 1, 'c'), sp)
    batch('stop', [drive], [first], stop)
    ids = {}
    for label, domain in [('A',['1','3/2',False,False]),('B',['2','5/2',False,False])]:
        p = deepcopy(bundle['nodes'][first]['output']); p['domain'] = domain
        restricted = node('restrict', [first], p, dict(domain=domain,reason='independent ancestor guard'))
        output = piece([domain[0],'5',False,True], 1, 2, -1, 2, 'c')
        second = node('stop', [restricted], output, sp)
        batch('stop', [restricted], [second], stop)
        final = deepcopy(output); final['domain'] = ['3','4',True,True]
        ids[label] = node('restrict', [second], final,
                          dict(domain=final['domain'],reason='independent final guard'))
    guarded = node('guarded_union', [ids['A'], ids['B']], deepcopy(final),
                   dict(guards=[['3','4',True,True],['3','4',True,True]]))
    ids['guarded'] = guarded; bundle['roots'] = [guarded]
    return case, bundle, ids


class IndependentCheckerUnits(unittest.TestCase):
    def test_hand_authored_positive_and_ordered_guard_dispatch(self):
        case, bundle, ids = hand_bundle(); checked = verify_bundle(bundle, case)
        a = reconstruct(checked, ids['A'], '3', '5')['witness']
        b = reconstruct(checked, ids['B'], '3', '5')['witness']
        check_witness(checked, ids['guarded'], a, dict(kind='minimum',energy='3'))
        with self.assertRaisesRegex(VerificationError, 'inherited_energy_guard'):
            check_witness(checked, ids['guarded'], b)
        out = reconstruct(checked, ids['guarded'], '3', '5')
        self.assertEqual(out['receipt']['chosen_parent'], ids['A'])
        self.assertEqual(out['witness'], a)

    def test_raw_bundle_needs_independent_case_and_snapshot_is_immutable(self):
        case, bundle, ids = hand_bundle()
        with self.assertRaisesRegex(VerificationError, 'requires_trusted_case'):
            reconstruct(bundle, ids['A'], '3', '5')
        checked = verify_bundle(bundle, case)
        with self.assertRaises(TypeError):
            checked._data['nodes'][ids['A']]['params']['domain'][0] = '0'
        bundle['nodes'].clear()
        reconstruct(checked, ids['A'], '3', '5')

    def test_harmless_duplicate_support_preserves_closure(self):
        case, bundle, ids = hand_bundle()
        batch = next(b for b in bundle['batches'] if b['kind'] == 'stop')
        batch['outputs'] *= 2
        bundle['batch_ids'] = [digest(b) for b in bundle['batches']]
        verify_bundle(bundle, case)

    def test_exact_strict_fiber_and_empty_singleton(self):
        tiny = F(1, 10**120)
        self.assertEqual(_fiber_point([(-F(1), F(0), True), (F(1), tiny, True)]), tiny/2)
        self.assertEqual(_fiber_point([(-F(1), -F(2), False), (F(1), F(2), False)]), F(2))
        with self.assertRaises(VerificationError):
            _fiber_point([(-F(1), -F(2), True), (F(1), F(2), False)])

    def test_selected_leg_is_in_receipt(self):
        case, bundle, ids = hand_bundle(); checked = verify_bundle(bundle, case)
        r = reconstruct(checked, ids['A'], '3', '5')['receipt']
        while r['kind'] != 'drive':r = r['parent']
        self.assertEqual(r['selected_leg']['path'], ['o','c'])
        self.assertEqual(r['selected_leg']['edge_ids'], ['input:00000000'])

    def test_receipt_complete_budget_annotation_replay(self):
        case, bundle, ids = hand_bundle(); checked = verify_bundle(bundle, case)
        out = reconstruct(checked, ids['guarded'], '3', '5')
        r, w = out['receipt'], out['witness']; contract = r['contract']
        self.assertEqual(check_receipt(checked, ids['guarded'], w, contract, r, require_budgets=True), r)
        ordinary = check_witness(checked, ids['guarded'], w, contract)
        check_receipt(checked, ids['guarded'], w, contract, ordinary)
        with self.assertRaisesRegex(VerificationError, 'missing_reconstruction_budget_annotations'):
            check_receipt(checked, ids['guarded'], w, contract, ordinary, require_budgets=True)
        bad = deepcopy(r); bad['requested_budget'] = '6'
        with self.assertRaisesRegex(VerificationError, 'root_requested_budget_mismatch'):
            check_receipt(checked, ids['guarded'], w, contract, bad)
        bad = deepcopy(r); bad['parent']['requested_budget'] = '6'
        with self.assertRaisesRegex(VerificationError, 'inherited_budget_transfer'):
            check_receipt(checked, ids['guarded'], w, contract, bad)
        bad = deepcopy(r); del bad['parent']['requested_budget']
        with self.assertRaisesRegex(VerificationError, 'partial_or_invalid_budget_annotations'):
            check_receipt(checked, ids['guarded'], w, contract, bad)
        bad = deepcopy(r); bad['parent']['predecessor_energy'] = '4'
        with self.assertRaisesRegex(VerificationError, 'receipt_membership_fields_mismatch'):
            check_receipt(checked, ids['guarded'], w, contract, bad)

    def test_receipt_inflated_physical_parent_budget(self):
        case, bundle, ids = hand_bundle(); checked = verify_bundle(bundle, case)
        out = reconstruct(checked, ids['A'], '3', '5')
        bad = deepcopy(out['receipt']); cursor = bad
        while cursor['kind'] != 'stop':cursor = cursor['parent']
        cursor['parent']['requested_budget'] = str(F(cursor['parent']['requested_budget'])+1)
        with self.assertRaisesRegex(VerificationError, 'charge_budget_transfer'):
            check_receipt(checked, ids['A'], out['witness'], bad['contract'], bad)

    def test_receipt_service_budget_must_respect_deadline(self):
        for effect in ('S', 'CS'):
            case, _, _ = hand_bundle()
            case.update(origin='c', schedule=dict(a=10,b=10,D=3), sites={'c':[effect]})
            initial = dict(domain=['2','2',True,True],m='0',b='0',chi=True,rho='-2',pi=[],state=['c',1,0])
            ni = dict(kind='initial',parents=[],output=initial,params={'case':case}); ii = digest(ni)
            p = dict(effect=effect,site='c',h='1',a='10',b='10',D='3',curve=[] if effect=='S' else [['0','5','1','0']])
            domain = ['2','2',True,True] if effect=='S' else ['2','5',False,True]
            output = dict(domain=domain,m='0',b='13',chi=True,rho='-2',pi=[['c',effect]],state=['c',0,1])
            segment = None if effect=='S' else ['0','5','1','0']
            ns = dict(kind='stop',parents=[ii],output=output,params={**p,'in_segment':segment,'out_segment':segment}); si=digest(ns)
            batch=dict(kind='stop',parents=[ii],outputs=[si],params=p)
            bundle=dict(schema='family5-v1',nodes={ii:ni,si:ns},batches=[batch],batch_ids=[digest(batch)],roots=[si])
            checked=verify_bundle(bundle,case)
            out=reconstruct(checked,si,'2' if effect=='S' else '3','13')
            check_receipt(checked,si,out['witness'],out['receipt']['contract'],out['receipt'])
            bad=deepcopy(out['receipt']);bad['parent']['requested_budget']='10'
            with self.assertRaisesRegex(VerificationError,'service_deadline_budget'):
                check_receipt(checked,si,out['witness'],bad['contract'],bad)


if __name__ == '__main__':
    unittest.main()
