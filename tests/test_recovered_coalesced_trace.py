"""New reconstructed coalesced checker tests; no production imports or data.

All fixtures are tiny hand-authored mathematical evidence. These tests do not
re-establish historical independent-review acceptance or a real population.
"""
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from fractions import Fraction as F
from pathlib import Path
import subprocess
import sys
import unittest

from validation.family5 import CheckedBundle, VerificationError, verify_bundle
from validation.family5.checker import digest
from validation.family5.independent_oracle_v2 import Piece
from validation.trace5 import CheckedTrace, TraceVerificationError, verify_trace
from validation.trace5.coalesced import (
    CoalescedReplay, REPRESENTATION, TRACE_SCHEMA, _connected_components,
    verify_coalesced_trace,
)
from validation.trace5.test_checker_units import hand_trace


def annotate_singletons(dominance=False):
    """Add mandatory no-op compact occurrences to the published hand fixture."""
    case, bundle, old = hand_trace(dominance)
    trace = dict(schema=TRACE_SCHEMA, representation=REPRESENTATION, events=[])
    remap, coalescing_id = {}, 0
    for event in old['events']:
        if event['kind'] == 'invoke' and event['payload']['operation'] != 'initial':
            row = event['payload']
            for side, cursor in zip(('input_families', 'output_families'), row['batch_range']):
                ids = row[side]
                payload = dict(coalescing_id=coalescing_id, input_families=ids,
                    output_families=ids, input_guards=[bundle['nodes'][x]['output']['domain'] for x in ids],
                    batch_range=[cursor, cursor])
                trace['events'].append(dict(seq=len(trace['events']), kind='coalesce', payload=deepcopy(payload)))
                coalescing_id += 1
        copied = deepcopy(event)
        remap[event['seq']] = copied['seq'] = len(trace['events'])
        if copied['kind'] == 'pop':
            copied['payload']['query_seq'] = remap[copied['payload']['query_seq']]
        trace['events'].append(copied)
    return case, bundle, trace


def hand_charging_trace(dominance=False):
    """One positive C action: two affine cells become a certified guarded union."""
    case = dict(case_id='reconstructed-coalesced-hand-charge', H_ref=1, origin='o', destination='z',
        start_time_s=0, initial_energy_kwh=2, capacity_kwh=5, minimum_energy_kwh=0,
        reserve_kwh=2, overhead_s=1, lambda_stop_s=0, consumption_kwh_per_m=1,
        schedule=None, sites={'c': ['C']}, charging_segments=[[0, 5, 1, 0]],
        edges=[dict(source='o', target='c', time_s=1, length_m=1),
               dict(source='c', target='z', time_s=1, length_m=1)])
    bundle = dict(schema='family5-v1', nodes={}, batches=[], batch_ids=[], roots=[])
    trace = dict(schema=TRACE_SCHEMA, representation=REPRESENTATION, events=[])
    invocation_id = coalescing_id = 0

    def event(kind, **payload):
        seq = len(trace['events'])
        trace['events'].append(dict(seq=seq, kind=kind, payload=deepcopy(payload)))
        return seq

    def node(kind, parents, output, params):
        record = dict(kind=kind, parents=parents, output=output, params=params)
        ident = digest(record)
        bundle['nodes'][ident] = record
        return ident

    def batch(kind, parents, outputs, params):
        record = dict(kind=kind, parents=parents, outputs=outputs, params=params)
        bundle['batches'].append(record)
        bundle['batch_ids'].append(digest(record))

    def compact(parents, merged_domain=None):
        nonlocal coalescing_id
        guards = [bundle['nodes'][x]['output']['domain'] for x in parents]
        outputs = list(parents)
        if merged_domain is not None:
            output = deepcopy(bundle['nodes'][parents[0]]['output'])
            output['domain'] = merged_domain
            outputs = [node('guarded_union', parents, output, dict(guards=guards))]
        cursor = len(bundle['batches'])
        event('coalesce', coalescing_id=coalescing_id, input_families=parents,
              output_families=outputs, input_guards=guards, batch_range=[cursor, cursor])
        coalescing_id += 1
        return outputs

    def invoke(operation, parents, outputs, params, begin):
        nonlocal invocation_id
        ident = invocation_id
        invocation_id += 1
        event('invoke', invocation_id=ident, operation=operation, input_families=parents,
              output_families=outputs, params=params, batch_range=[begin, len(bundle['batches'])])
        return ident

    def piece(domain, m, b, rho, count, anchor):
        return dict(domain=domain, m=str(m), b=str(b), chi=True, rho=str(rho),
            pi=[] if count == 0 else [['c', 'C']], state=[anchor, 0, count])

    event('run_start', case_sha256=digest(case), dominance=dominance, H_ref=1,
          regions=dict(id=0, members=['c'], children=[]))
    initial = node('initial', [], piece(['2', '2', True, True], 0, 0, -2, 0, 'o'), dict(case=case))
    invoke('initial', [], [initial], {}, 0)
    event('layer_start', depth=0, groups=[dict(group_id=0, families=[initial])])
    compact([initial])
    batch('drive', [initial], [], dict(site='z', duration='2', consumption='2', floor='2'))
    compact([])
    invoke('finish', [initial], [], dict(group_id=0, source='layer', advance_id=None), 0)
    event('expansion_start', group_id=0)
    query_seq = event('query', group_id=0, region_id=0, effect='C', actions=[['c', 'C']],
                     bound='3', classification='queued', queue_serial=1)
    for effect in ('S', 'CS'):
        event('query', group_id=0, region_id=0, effect=effect, actions=[], bound=None,
              classification='empty_actions', queue_serial=None)
    event('pop', group_id=0, query_seq=query_seq, decision='leaf', incumbent_key=None)
    begin = len(bundle['batches'])
    compact([initial])
    params = dict(site='c', duration='1', consumption='1', floor='0')
    driven = node('drive', [initial], piece(['1', '1', True, True], 0, 1, -1, 0, 'c'), params)
    batch('drive', [initial], [driven], params)
    params = dict(effect='C', site='c', h='1', a='0', b='0', D='0', curve=[['0', '5', '1', '0']])
    raw = [node('stop', [driven], piece(domain, 1, 1, -1, 1, 'c'),
                dict(**params, in_segment=['0', '5', '1', '0'], out_segment=['0', '5', '1', '0']))
           for domain in (['1', '5', False, False], ['5', '5', True, True])]
    batch('stop', [driven], raw, params)
    selected = [node('select', raw, deepcopy(bundle['nodes'][ident]['output']),
                     dict(domain=bundle['nodes'][ident]['output']['domain'], chosen=index, mode='union'))
                for index, ident in enumerate(raw)]
    batch('union', raw, selected, {})
    advanced = compact(selected, ['1', '5', False, True])
    advance_id = invoke('advance', [initial], advanced, dict(group_id=0, site='c', effect='C'), begin)

    def finish(parents, group_id, source, advance):
        begin = len(bundle['batches'])
        compact(parents)
        params = dict(site='z', duration='1', consumption='1', floor='2')
        terminal = node('drive', parents, piece(['2', '4', True, True], 1, 3, 0, 1, 'z'), params)
        batch('drive', parents, [terminal], params)
        compact([terminal])
        invoke('finish', parents, [terminal], dict(group_id=group_id, source=source, advance_id=advance), begin)
        return terminal

    terminal = finish(advanced, 0, 'leaf', advance_id)
    witness = dict(time='5', energy='2', rho='0', pi=[['c', 'C']], state=['z', 0, 1], events=[
        dict(effect='initial', site='o', arrival_time='0', departure_time='0', arrival_energy='2', departure_energy='2'),
        dict(effect='D', site='c', arrival_time='0', departure_time='1', arrival_energy='2', departure_energy='1'),
        dict(effect='C', site='c', arrival_time='1', departure_time='4', arrival_energy='1', departure_energy='3'),
        dict(effect='D', site='z', arrival_time='4', departure_time='5', arrival_energy='3', departure_energy='2')])
    key = ['5', '2', 1, [['c', 'C']]]
    event('candidate', group_id=0, source='leaf', family_id=terminal, energy='2',
          witness=witness, key=key, improved=True)
    event('expansion_end', group_id=0, covered_actions=[['c', 'C']])
    if dominance:
        begin = len(bundle['batches'])
        compact(advanced)
        selected = [node('select', advanced, piece(domain, 1, 1, -1, 1, 'c'),
                        dict(domain=domain, chosen=0, mode='reduction'))
                    for domain in (['1', '5', False, False], ['5', '5', True, True])]
        batch('reduction', advanced, selected, {})
        reduced = compact(selected, ['1', '5', False, True])
        invoke('reduce', advanced, reduced, dict(depth=0, state=['c', 0, 1]), begin)
        advanced = reduced
    event('layer_end', depth=0, reason='continue', next_groups=[advanced])
    event('layer_start', depth=1, groups=[dict(group_id=1, families=advanced)])
    terminal = finish(advanced, 1, 'layer', None)
    event('candidate', group_id=1, source='layer', family_id=terminal, energy='2',
          witness=witness, key=key, improved=False)
    event('layer_end', depth=1, reason='stop_bound', next_groups=[])
    canonical = dict(scope='bounded_H_ref_diagnostic', H_ref=1,
        result=dict(status='attained_optimum', J='5', Q_total='2', H=1,
                    site_action_tuple=[['c', 'C']], lex_key=key, charges=['2'], witness_replayed=True))
    event('run_end', canonical=canonical, terminal_families=[terminal],
          terminal_family_id=terminal, terminal_witness=witness)
    bundle['roots'] = [terminal]
    return case, bundle, trace


def compact_fixture(domains, clusters):
    """Independently valid lineage plus one isolated compact occurrence.

    Cluster membership and union endpoints are explicit test inputs, never
    calculated with the checker under test or a production implementation.
    """
    case, bundle, _ = hand_charging_trace()
    parent = next(ident for ident, node in bundle['nodes'].items() if node['kind'] == 'guarded_union')
    inputs = []
    for index, domain in enumerate(domains):
        output = deepcopy(bundle['nodes'][parent]['output'])
        output['domain'] = domain
        node = dict(kind='restrict', parents=[parent], output=output,
                    params=dict(domain=domain, reason=f'hand-cut-{index}'))
        ident = digest(node)
        bundle['nodes'][ident] = node
        inputs.append(ident)
    outputs = []
    for members, domain in clusters:
        if len(members) == 1:
            outputs.append(inputs[members[0]])
        else:
            output = deepcopy(bundle['nodes'][inputs[members[0]]]['output'])
            output['domain'] = domain
            node = dict(kind='guarded_union', parents=[inputs[i] for i in members], output=output,
                        params=dict(guards=[domains[i] for i in members]))
            ident = digest(node)
            bundle['nodes'][ident] = node
            outputs.append(ident)
    payload = dict(coalescing_id=0, input_families=inputs, output_families=outputs,
                   input_guards=domains, batch_range=[0, 0])
    trace = dict(schema=TRACE_SCHEMA, representation=REPRESENTATION,
                 events=[dict(seq=0, kind='coalesce', payload=deepcopy(payload))])
    return case, bundle, trace, inputs, outputs


def renumber(trace):
    """Renumber event positions, preserving surviving query references."""
    remap = {event['seq']: index for index, event in enumerate(trace['events'])}
    for index, event in enumerate(trace['events']):
        event['seq'] = index
        if event['kind'] == 'pop':
            event['payload']['query_seq'] = remap.get(event['payload']['query_seq'], -1)


class ReconstructedCoalescedTraceTests(unittest.TestCase):
    def test_complete_hand_traces_empty_singleton_and_genuine_merges(self):
        for maker in (annotate_singletons, hand_charging_trace):
            for dominance in (False, True):
                with self.subTest(maker=maker.__name__, dominance=dominance):
                    case, bundle, trace = maker(dominance)
                    checked = verify_coalesced_trace(trace, bundle, case)
                    self.assertIs(type(checked), CheckedTrace)
                    self.assertIs(type(checked.bundle), CheckedBundle)
                    self.assertTrue(checked.summary['verified'])
                    self.assertFalse(checked.summary['literal_G8_closed'])
                    self.assertEqual(checked.summary['coalescings'], 2 * (checked.summary['invocations'] - 1))
                    self.assertEqual(checked.snapshot(), trace)
                    self.assertEqual(checked.summary['trace_sha256'], digest(trace))
                    self.assertEqual(checked.summary['query_freeze_sha256'], digest(checked.query_snapshot()))
                    if maker is hand_charging_trace:
                        self.assertGreater(checked.summary['counts']['coalescing_merged_clusters'], 0)

    def test_v1_and_v2_are_explicitly_separate(self):
        case, bundle, v1 = hand_trace()
        verify_trace(v1, bundle, case)
        with self.assertRaises(TraceVerificationError):
            verify_coalesced_trace(v1, bundle, case)
        case, bundle, v2 = annotate_singletons()
        with self.assertRaises(TraceVerificationError):
            verify_trace(v2, bundle, case)
        v2['representation'] = 'rounded-energy-approximation'
        with self.assertRaisesRegex(TraceVerificationError, 'coalesced_trace_representation'):
            verify_coalesced_trace(v2, bundle, case)

    def test_checked_bundle_and_immutable_detached_trace(self):
        case, bundle, trace = hand_charging_trace(True)
        context = verify_bundle(bundle, case)
        checked = verify_coalesced_trace(trace, context, case)
        self.assertIs(checked.bundle, context)
        original = checked.snapshot()
        trace['events'].clear()
        bundle['nodes'].clear()
        case['sites'].clear()
        self.assertEqual(checked.snapshot(), original)
        with self.assertRaises(TypeError):
            checked.summary['verified'] = False
        with self.assertRaises(FrozenInstanceError):
            checked.node_queries = ()
        exported = checked.query_snapshot()
        exported[0]['cuts'].clear()
        self.assertTrue(checked.queries[0]['cuts'])

    def test_missing_reordered_duplicate_and_foreign_compact_events(self):
        for mutation in ('missing_input', 'missing_output', 'duplicate', 'swapped', 'foreign'):
            case, bundle, trace = hand_charging_trace(True)
            indices = [i for i, event in enumerate(trace['events']) if event['kind'] == 'coalesce']
            first = indices[0]
            if mutation.startswith('missing_'):
                trace['events'].pop(first if mutation == 'missing_input' else indices[1])
            elif mutation == 'duplicate':
                trace['events'].insert(first, deepcopy(trace['events'][first]))
            elif mutation == 'swapped':
                trace['events'][first], trace['events'][indices[1]] = trace['events'][indices[1]], trace['events'][first]
            else:
                trace['events'][first]['payload']['input_families'] = ['foreign-family']
            renumber(trace)
            with self.subTest(mutation=mutation), self.assertRaises(TraceVerificationError):
                verify_coalesced_trace(trace, bundle, case)

    def test_compact_and_invocation_metadata_tampering(self):
        for mutation in ('stale_id', 'boolean_id', 'guard', 'guard_type', 'batch_span',
                         'input_order', 'missing_parent', 'duplicate_parent', 'stale_output',
                         'invoke_span', 'invoke_input', 'invoke_output', 'unknown_field'):
            case, bundle, trace = hand_charging_trace(True)
            row = next(event['payload'] for event in trace['events']
                       if event['kind'] == 'coalesce' and len(event['payload']['input_families']) > 1)
            if mutation == 'stale_id':
                row['coalescing_id'] = 0
            elif mutation == 'boolean_id':
                row['coalescing_id'] = True
            elif mutation == 'guard':
                row['input_guards'][0][0] = '0'
            elif mutation == 'guard_type':
                row['input_guards'][0][2] = 0
            elif mutation == 'batch_span':
                row['batch_range'][1] += 1
            elif mutation == 'input_order':
                row['input_families'].reverse()
                row['input_guards'].reverse()
            elif mutation == 'missing_parent':
                row['input_families'].pop()
                row['input_guards'].pop()
            elif mutation == 'duplicate_parent':
                row['input_families'].append(row['input_families'][0])
                row['input_guards'].append(row['input_guards'][0])
            elif mutation == 'stale_output':
                row['output_families'] = [row['input_families'][0]]
            elif mutation.startswith('invoke_'):
                row = next(event['payload'] for event in trace['events']
                           if event['kind'] == 'invoke' and event['payload']['operation'] == 'advance')
                if mutation == 'invoke_span':
                    row['batch_range'][0] += 1
                elif mutation == 'invoke_input':
                    row['input_families'] = bundle['roots'][:]
                else:
                    row['output_families'] = bundle['roots'][:]
            else:
                row['ignored'] = True
            with self.subTest(mutation=mutation), self.assertRaises(TraceVerificationError):
                verify_coalesced_trace(trace, bundle, case)

    def test_exact_components_preserve_original_dispatch_order(self):
        # Domain order is 1,2,0; original callback order remains 0,1,2.
        domains = [['3', '4', False, True], ['2', '3', True, False], ['3', '3', True, True]]
        case, bundle, trace, inputs, outputs = compact_fixture(domains, [([0, 1, 2], ['2', '4', True, True])])
        replay = CoalescedReplay(trace, bundle, case)
        self.assertEqual(replay.compact(inputs), outputs)
        self.assertEqual(bundle['nodes'][outputs[0]]['parents'], inputs)
        self.assertEqual(replay.batch_cursor, 0)

    def test_nested_overlapping_and_duplicate_inputs_merge_exactly(self):
        domains = [['2', '4', True, False], ['5/2', '3', False, True], ['2', '4', True, True]]
        case, bundle, trace, inputs, outputs = compact_fixture(domains, [([0, 1, 2], ['2', '4', True, True])])
        self.assertEqual(CoalescedReplay(trace, bundle, case).compact(inputs), outputs)
        # Repeated support occurrences remain distinct guarded dispatch entries.
        piece = Piece(F(2), F(4), True, True, F(1), F(1), True, F(-1), (('c', 'C'),), ('c', 0, 1))
        members, joined = list(_connected_components([piece, piece]))[0]
        self.assertEqual(members, [0, 1])
        self.assertEqual(joined, piece)

    def test_open_open_knot_and_positive_gap_remain_separate(self):
        for domains in (
            [['2', '3', True, False], ['3', '4', False, True]],
            [['2', '5/2', True, True], ['3', '4', True, True]],
        ):
            case, bundle, trace, inputs, outputs = compact_fixture(domains, [([0], domains[0]), ([1], domains[1])])
            with self.subTest(domains=domains):
                self.assertEqual(CoalescedReplay(trace, bundle, case).compact(inputs), outputs)
                forged = deepcopy(bundle['nodes'][inputs[0]]['output'])
                forged['domain'] = ['2', '4', True, True]
                node = dict(kind='guarded_union', parents=inputs, output=forged, params=dict(guards=domains))
                ident = digest(node)
                bundle['nodes'][ident] = node
                trace['events'][0]['payload']['output_families'] = [ident]
                with self.assertRaisesRegex(VerificationError, 'guarded_union_connected_coverage'):
                    CoalescedReplay(trace, bundle, case).compact(inputs)

    def test_component_output_order_and_endpoint_flags_cannot_be_forged(self):
        domains = [['4', '5', True, True], ['2', '3', True, True]]
        case, bundle, trace, inputs, outputs = compact_fixture(domains, [([1], domains[1]), ([0], domains[0])])
        self.assertEqual(CoalescedReplay(trace, bundle, case).compact(inputs), outputs)
        trace['events'][0]['payload']['output_families'].reverse()
        with self.assertRaisesRegex(TraceVerificationError, 'coalescing_output_families'):
            CoalescedReplay(trace, bundle, case).compact(inputs)
        domains = [['2', '3', True, False], ['3', '4', True, True]]
        case, bundle, trace, inputs, outputs = compact_fixture(domains, [([0, 1], ['2', '4', True, True])])
        node = bundle['nodes'].pop(outputs[0])
        node['output']['domain'][3] = False
        wrong = digest(node)
        bundle['nodes'][wrong] = node
        trace['events'][0]['payload']['output_families'] = [wrong]
        with self.assertRaisesRegex(VerificationError, 'guarded_union_connected_coverage'):
            CoalescedReplay(trace, bundle, case).compact(inputs)

    def test_repeated_identical_input_ids_require_occurrence_exact_parents(self):
        domain = ['2', '4', True, True]
        case, bundle, trace, inputs, _ = compact_fixture([domain], [([0], domain)])
        repeated = inputs * 2
        record = dict(kind='guarded_union', parents=repeated,
                      output=deepcopy(bundle['nodes'][inputs[0]]['output']),
                      params=dict(guards=[domain, domain]))
        ident = digest(record)
        bundle['nodes'][ident] = record
        trace['events'][0]['payload'].update(input_families=repeated,
            input_guards=[domain, domain], output_families=[ident])
        self.assertEqual(CoalescedReplay(trace, bundle, case).compact(repeated), [ident])
        trace['events'][0]['payload']['output_families'] = inputs
        with self.assertRaisesRegex(TraceVerificationError, 'coalescing_output_families'):
            CoalescedReplay(trace, bundle, case).compact(repeated)

    def test_unaccounted_semantically_valid_union_is_rejected(self):
        case, bundle, trace = hand_charging_trace()
        parent = bundle['roots'][0]
        node = dict(kind='guarded_union', parents=[parent],
                    output=deepcopy(bundle['nodes'][parent]['output']),
                    params=dict(guards=[bundle['nodes'][parent]['output']['domain']]))
        bundle['nodes'][digest(node)] = node
        verify_bundle(bundle, case)
        with self.assertRaisesRegex(TraceVerificationError, 'unaccounted_family_nodes'):
            verify_coalesced_trace(trace, bundle, case)

    def test_cluster_and_group_order_are_deterministic(self):
        def p(lo, hi, **changes):
            return replace(Piece(F(lo), F(hi), True, True, F(1), F(1), True,
                                 F(-1), (('c', 'C'),), ('c', 0, 1)), **changes)
        pieces = [p(4, 5), p(2, 3, m=F(2)), p(2, 3), p(3, 4), p(3, 4, m=F(2))]
        clusters = list(_connected_components(pieces))
        self.assertEqual([members for members, _ in clusters], [[0, 2, 3], [1, 4]])
        for field, value in (('state', ('other', 0, 1)), ('rho', F(0)), ('pi', (('x', 'C'),)),
                             ('m', F(2)), ('b', F(2)), ('chi', False)):
            with self.subTest(field=field):
                self.assertEqual([ids for ids, _ in _connected_components([p(2, 3), p(2, 3, **{field: value})])],
                                 [[0], [1]])
        self.assertEqual([ids for ids, _ in _connected_components([p(4, 5), p(2, 3)])], [[1], [0]])

    def test_semantically_valid_reversed_parent_dispatch_is_rejected(self):
        domains = [['2', '4', True, True], ['3', '5', True, True]]
        case, bundle, trace, inputs, outputs = compact_fixture(domains, [([0, 1], ['2', '5', True, True])])
        original = bundle['nodes'].pop(outputs[0])
        original['parents'].reverse()
        original['params']['guards'].reverse()
        wrong = digest(original)
        bundle['nodes'][wrong] = original
        trace['events'][0]['payload']['output_families'] = [wrong]
        verify_bundle(bundle, case)  # Both dispatch choices are physically valid.
        with self.assertRaisesRegex(TraceVerificationError, 'missing_exact_operator_node'):
            CoalescedReplay(trace, bundle, case).compact(inputs)

    def test_singleton_cannot_be_retagged_as_a_redundant_union(self):
        domains = [['2', '4', True, True]]
        case, bundle, trace, inputs, _ = compact_fixture(domains, [([0], domains[0])])
        node = dict(kind='guarded_union', parents=inputs, output=deepcopy(bundle['nodes'][inputs[0]]['output']),
                    params=dict(guards=domains))
        ident = digest(node)
        bundle['nodes'][ident] = node
        trace['events'][0]['payload']['output_families'] = [ident]
        verify_bundle(bundle, case)
        with self.assertRaisesRegex(TraceVerificationError, 'coalescing_output_families'):
            CoalescedReplay(trace, bundle, case).compact(inputs)

    def test_no_production_imports_and_optimized_rejections(self):
        root = Path(__file__).resolve().parents[1]
        script = '''import sys
class DenyProduction:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'timecut5', 'hierarchy4r', 'reference5'}:
            raise RuntimeError('production import attempted: '+fullname)
sys.meta_path.insert(0, DenyProduction())
from tests.test_recovered_coalesced_trace import hand_charging_trace
from validation.trace5.coalesced import verify_coalesced_trace
from validation.trace5 import TraceVerificationError
for dominance in (False, True):
    case,bundle,trace=hand_charging_trace(dominance)
    verify_coalesced_trace(trace,bundle,case)
for key,value in [('coalescing_id',True),('input_guards',[]),('batch_range',[0,1])]:
    case,bundle,trace=hand_charging_trace()
    next(e['payload'] for e in trace['events'] if e['kind']=='coalesce')[key]=value
    try: verify_coalesced_trace(trace,bundle,case)
    except TraceVerificationError: pass
    else: raise RuntimeError('optimized checker accepted '+key)
'''
        for flags in ([], ['-O'], ['-OO']):
            with self.subTest(flags=flags):
                result = subprocess.run([sys.executable, *flags, '-c', script], cwd=root,
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
