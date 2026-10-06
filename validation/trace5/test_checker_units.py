"""Hand-authored complete traces and adversarial edits; no production imports."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
from fractions import Fraction as F
from pathlib import Path
import subprocess
import sys
import unittest

from validation.family5.checker import digest
from .checker import TraceVerificationError, verify_trace, _dispatch_cells
from validation.family5.independent_oracle_v2 import Piece


def hand_trace(dominance=False):
    """One exact S action, an unreachable Site, and repeated finish occurrence."""
    case = dict(case_id='trace5-hand-service', H_ref=1, origin='o', destination='z',
        start_time_s=0, initial_energy_kwh=2, capacity_kwh=3, minimum_energy_kwh=0,
        reserve_kwh=0, overhead_s=1, lambda_stop_s=0, consumption_kwh_per_m=0,
        schedule=dict(a=0, b=10, D=0), sites={'s': ['S'], 'u': ['S']}, charging_segments=[],
        edges=[dict(source='o', target='s', time_s=1, length_m=1),
               dict(source='s', target='z', time_s=1, length_m=1)])
    bundle = dict(schema='family5-v1', nodes={}, batches=[], batch_ids=[], roots=[])
    trace = dict(schema='family5-hier-trace-v1', events=[])
    def event(kind, **payload):
        seq = len(trace['events'])
        trace['events'].append(dict(seq=seq, kind=kind, payload=payload))
        return seq
    def piece(anchor, remaining, count, time):
        return dict(domain=['2', '2', True, True], m='0', b=str(time), chi=True, rho='-2',
                    pi=[] if count == 0 else [['s', 'S']], state=[anchor, remaining, count])
    def node(kind, parents, output, params):
        record = dict(kind=kind, parents=parents, output=output, params=params)
        ident = digest(record)
        bundle['nodes'][ident] = record
        return ident
    def batch(kind, parents, outputs, params):
        record = dict(kind=kind, parents=parents, outputs=outputs, params=params)
        bundle['batches'].append(record)
        bundle['batch_ids'].append(digest(record))
    invocation_count = 0
    def invoke(operation, parents, outputs, params, begin):
        nonlocal invocation_count
        ident = invocation_count
        invocation_count += 1
        event('invoke', invocation_id=ident, operation=operation, input_families=parents,
              output_families=outputs, params=params, batch_range=[begin, len(bundle['batches'])])
        return ident
    root = dict(id=0, members=['s', 'u'], children=[dict(id=1, members=['s'], children=[]),
                                                dict(id=2, members=['u'], children=[])])
    event('run_start', case_sha256=digest(case), dominance=dominance, H_ref=1, regions=root)
    initial = node('initial', [], piece('o', 1, 0, 0), dict(case=case))
    invoke('initial', [], [initial], {}, 0)
    event('layer_start', depth=0, groups=[dict(group_id=0, families=[initial])])
    invoke('finish', [initial], [], dict(group_id=0, source='layer', advance_id=None), 0)
    event('expansion_start', group_id=0)
    event('query', group_id=0, region_id=0, effect='C', actions=[], bound=None,
          classification='empty_actions', queue_serial=None)
    root_query = event('query', group_id=0, region_id=0, effect='S', actions=[['s', 'S'], ['u', 'S']],
                       bound='3', classification='queued', queue_serial=1)
    event('query', group_id=0, region_id=0, effect='CS', actions=[], bound=None,
          classification='empty_actions', queue_serial=None)
    event('pop', group_id=0, query_seq=root_query, decision='split', incumbent_key=None)
    leaf_query = event('query', group_id=0, region_id=1, effect='S', actions=[['s', 'S']],
                       bound='3', classification='queued', queue_serial=2)
    event('query', group_id=0, region_id=2, effect='S', actions=[['u', 'S']], bound=None,
          classification='unreachable', queue_serial=None)
    event('pop', group_id=0, query_seq=leaf_query, decision='leaf', incumbent_key=None)
    drive_params = dict(site='s', duration='1', consumption='0', floor='0')
    drive = node('drive', [initial], piece('s', 1, 0, 1), drive_params)
    batch('drive', [initial], [drive], drive_params)
    stop_params = dict(effect='S', site='s', h='1', a='0', b='10', D='0', curve=[])
    stop = node('stop', [drive], piece('s', 0, 1, 2),
                dict(**stop_params, in_segment=None, out_segment=None))
    batch('stop', [drive], [stop], stop_params)
    union = node('select', [stop], piece('s', 0, 1, 2),
                 dict(domain=['2', '2', True, True], chosen=0, mode='union'))
    batch('union', [stop], [union], {})
    advance_id = invoke('advance', [initial], [union], dict(group_id=0, site='s', effect='S'), 0)
    def finish(parent, group_id, source, advance_id):
        begin = len(bundle['batches'])
        params = dict(site='z', duration='1', consumption='0', floor='0')
        result = node('drive', [parent], piece('z', 0, 1, 3), params)
        batch('drive', [parent], [result], params)
        invoke('finish', [parent], [result], dict(group_id=group_id, source=source, advance_id=advance_id), begin)
        return result
    first_terminal = finish(union, 0, 'leaf', advance_id)
    def physical(effect, site, arrival, departure):
        return dict(effect=effect, site=site, arrival_time=str(arrival), departure_time=str(departure),
                    arrival_energy='2', departure_energy='2')
    witness = dict(time='3', energy='2', rho='-2', pi=[['s', 'S']], state=['z', 0, 1],
        events=[physical('initial', 'o', 0, 0), physical('D', 's', 0, 1),
                physical('S', 's', 1, 2), physical('D', 'z', 2, 3)])
    key = ['3', '0', 1, [['s', 'S']]]
    event('candidate', group_id=0, source='leaf', family_id=first_terminal, energy='2',
          witness=witness, key=key, improved=True)
    event('expansion_end', group_id=0, covered_actions=[['s', 'S'], ['u', 'S']])
    next_family = union
    if dominance:
        begin = len(bundle['batches'])
        next_family = node('select', [union], piece('s', 0, 1, 2),
                           dict(domain=['2', '2', True, True], chosen=0, mode='reduction'))
        batch('reduction', [union], [next_family], {})
        invoke('reduce', [union], [next_family], dict(depth=0, state=['s', 0, 1]), begin)
    event('layer_end', depth=0, reason='continue', next_groups=[[next_family]])
    event('layer_start', depth=1, groups=[dict(group_id=1, families=[next_family])])
    last_terminal = finish(next_family, 1, 'layer', None)
    event('candidate', group_id=1, source='layer', family_id=last_terminal, energy='2',
          witness=witness, key=key, improved=False)
    event('layer_end', depth=1, reason='stop_bound', next_groups=[])
    canonical = dict(scope='bounded_H_ref_diagnostic', H_ref=1,
        result=dict(status='attained_optimum', J='3', Q_total='0', H=1, site_action_tuple=[['s', 'S']],
                    lex_key=key, charges=[], witness_replayed=True))
    event('run_end', canonical=canonical, terminal_families=[last_terminal],
          terminal_family_id=last_terminal, terminal_witness=witness)
    bundle['roots'] = [last_terminal]
    return case, bundle, trace


class IndependentTraceUnits(unittest.TestCase):
    def test_disjoint_domain_crossing_does_not_split_dispatch(self):
        left = Piece(F(0), F(1), True, True, F(1), F(0), True, F(0), (), ('s', 0, 0))
        right = Piece(F(2), F(3), True, True, F(0), F(1, 2), True, F(0), (), ('s', 0, 0))
        cells = _dispatch_cells([left, right])
        self.assertEqual([(lo, hi) for lo, hi, _ in cells],
                         [(0, 0), (0, 1), (1, 1), (1, 2), (2, 2), (2, 3), (3, 3)])
        self.assertNotIn(F(1, 2), {v for lo, hi, _ in cells for v in (lo, hi)})
        overlapping = Piece(F(0), F(1), True, True, F(0), F(1, 2), True, F(0), (), ('s', 0, 0))
        self.assertIn((F(1, 2), F(1, 2), F(1, 2)), _dispatch_cells([left, overlapping]))

    def test_complete_hand_authored_trace_both_dominance_modes(self):
        for dominance in (False, True):
            with self.subTest(dominance=dominance):
                case, bundle, trace = hand_trace(dominance)
                checked = verify_trace(trace, bundle, case)
                self.assertTrue(checked.summary['verified'])
                self.assertEqual(checked.summary['exact_node_queries'], 3)
                self.assertEqual(checked.summary['empty_action_queries'], 2)
                self.assertEqual(checked.summary['unreachable_node_queries'], 1)
                unreachable = next(q for q in checked.queries if q['classification'] == 'unreachable')
                self.assertEqual(unreachable['actions'], (('u', 'S'),))
                self.assertIsNone(unreachable['leg_context'][0]['incoming'])
                self.assertIsNone(unreachable['leg_context'][0]['onward'])
                self.assertEqual(unreachable['H_remaining'], 1)
                self.assertEqual(checked.summary['counts']['invoke_finish'], 3)
                self.assertFalse(checked.summary['literal_G8_closed'])

    def test_immutable_detached_context_and_query_freeze(self):
        case, bundle, trace = hand_trace()
        checked = verify_trace(trace, bundle, case)
        original_digest = checked.summary['query_freeze_sha256']
        trace['events'].clear()
        bundle['nodes'].clear()
        case['sites'].clear()
        exported = checked.export_queries()
        exported[0]['cuts'].clear()
        self.assertTrue(checked.queries[0]['cuts'])
        self.assertEqual(digest(checked.query_snapshot()), original_digest)
        with self.assertRaises(TypeError):
            checked.queries[0]['H_remaining'] = 99
        with self.assertRaises(FrozenInstanceError):
            checked.node_queries = ()

    def test_missing_duplicate_and_reordered_events_rejected_after_renumber(self):
        for mutation in ('drop_query', 'drop_finish', 'duplicate_candidate', 'swap_queries'):
            case, bundle, trace = hand_trace()
            events = trace['events']
            if mutation == 'drop_query':
                events.pop(next(i for i, e in enumerate(events) if e['kind'] == 'query'))
            elif mutation == 'drop_finish':
                events.pop(next(i for i, e in enumerate(events) if e['kind'] == 'invoke' and e['payload']['operation'] == 'finish'))
            elif mutation == 'duplicate_candidate':
                i = next(i for i, e in enumerate(events) if e['kind'] == 'candidate')
                events.insert(i, deepcopy(events[i]))
            else:
                indices = [i for i, e in enumerate(events) if e['kind'] == 'query']
                events[indices[0]], events[indices[1]] = events[indices[1]], events[indices[0]]
            for i, event in enumerate(events):
                event['seq'] = i
            with self.subTest(mutation=mutation), self.assertRaises(TraceVerificationError):
                verify_trace(trace, bundle, case)

    def test_exact_scalar_types_and_action_metadata(self):
        mutations = [
            ('run_start', 'H_ref', True), ('run_start', 'dominance', 0),
            ('invoke', 'invocation_id', False), ('layer_start', 'depth', 0.0),
            ('candidate', 'improved', 1), ('query', 'queue_serial', 1.0),
            ('query', 'actions', [['s', 'C']]), ('candidate', 'energy', '4/2'),
            ('candidate', 'key', ['3', '0', True, [['s', 'S']]])]
        for kind, field, value in mutations:
            case, bundle, trace = hand_trace()
            row = next(e['payload'] for e in trace['events'] if e['kind'] == kind)
            row[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(TraceVerificationError):
                verify_trace(trace, bundle, case)

    def test_batch_span_and_source_and_orphan_nodes(self):
        for mutation in ('span', 'batch_extra', 'duplicate_raw_stop', 'foreign_finish', 'orphan'):
            case, bundle, trace = hand_trace()
            if mutation == 'span':
                row = next(e['payload'] for e in trace['events'] if e['kind'] == 'invoke' and e['payload']['operation'] == 'advance')
                row['batch_range'][1] -= 1
            elif mutation == 'batch_extra':
                bundle['batches'].append(deepcopy(bundle['batches'][-1]))
            elif mutation == 'duplicate_raw_stop':
                row = next(b for b in bundle['batches'] if b['kind'] == 'stop')
                row['outputs'] *= 2
            elif mutation == 'foreign_finish':
                row = next(e['payload'] for e in trace['events'] if e['kind'] == 'invoke' and e['payload']['operation'] == 'finish')
                row['output_families'] = bundle['roots'][:]
            else:
                parent = bundle['roots'][0]
                output = deepcopy(bundle['nodes'][parent]['output'])
                record = dict(kind='restrict', parents=[parent], output=output,
                              params=dict(domain=output['domain'], reason='unused valid family'))
                bundle['nodes'][digest(record)] = record
            bundle['batch_ids'] = [digest(b) for b in bundle['batches']]
            with self.subTest(mutation=mutation), self.assertRaises(TraceVerificationError):
                verify_trace(trace, bundle, case)

    def test_region_coverage_queue_incumbent_and_terminal_mutations(self):
        for mutation in ('region_duplicate', 'region_missing', 'queue_prune', 'incumbent', 'terminal_status', 'terminal_family', 'terminal_witness'):
            case, bundle, trace = hand_trace(True)
            if mutation.startswith('region_'):
                root = trace['events'][0]['payload']['regions']
                root['children'][1]['members'] = ['s'] if mutation == 'region_duplicate' else []
            elif mutation == 'queue_prune':
                next(e['payload'] for e in trace['events'] if e['kind'] == 'pop')['decision'] = 'prune'
            elif mutation == 'incumbent':
                next(e['payload'] for e in trace['events'] if e['kind'] == 'candidate')['improved'] = False
            elif mutation == 'terminal_status':
                trace['events'][-1]['payload']['canonical']['result'] = dict(status='infeasible_within_H_ref')
            elif mutation == 'terminal_family':
                trace['events'][-1]['payload']['terminal_family_id'] = next(iter(bundle['nodes']))
            else:
                trace['events'][-1]['payload']['terminal_witness']['time'] = '2'
            with self.subTest(mutation=mutation), self.assertRaises(TraceVerificationError):
                verify_trace(trace, bundle, case)

    def test_valid_alternative_region_partition_is_rejected(self):
        case, bundle, trace = hand_trace()
        trace['events'][0]['payload']['regions']['children'] = []
        with self.assertRaisesRegex(TraceVerificationError, 'trusted_region_configuration'):
            verify_trace(trace, bundle, case)

    def test_no_production_import_is_required(self):
        root = Path(__file__).resolve().parents[2]
        script = '''import sys
class DenyProduction:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'timecut5', 'hierarchy4r', 'reference5'}:
            raise RuntimeError('production import attempted: '+fullname)
sys.meta_path.insert(0, DenyProduction())
from validation.trace5.test_checker_units import hand_trace
from validation.trace5 import verify_trace
case,bundle,trace=hand_trace(True)
verify_trace(trace,bundle,case)
'''
        result = subprocess.run([sys.executable, '-c', script], cwd=root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)

    def test_optimized_python_executes_all_rejections(self):
        root = Path(__file__).resolve().parents[2]
        script = '''from validation.trace5.test_checker_units import hand_trace
from validation.trace5 import verify_trace, TraceVerificationError
for dominance in (False, True):
    case, bundle, trace = hand_trace(dominance)
    verify_trace(trace, bundle, case)
for kind, field, value in [('run_start','H_ref',True),('candidate','improved',1),('invoke','invocation_id',False)]:
    case, bundle, trace = hand_trace()
    next(e['payload'] for e in trace['events'] if e['kind']==kind)[field]=value
    try: verify_trace(trace,bundle,case)
    except TraceVerificationError: pass
    else: raise RuntimeError('optimized checker accepted tampered '+field)
print('optimized acceptance and rejection checks passed')
'''
        for mode in ('-O', '-OO'):
            result = subprocess.run([sys.executable, mode, '-c', script], cwd=root,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)


if __name__ == '__main__':
    unittest.main()
