"""Hand-derived rational proofs and adversarial evidence; no optimizer imports."""
from copy import deepcopy
from fractions import Fraction as F
from pathlib import Path
import subprocess
import sys
import unittest

from validation.family5 import verify_bundle
from validation.family5.checker import digest
from .independent_model import (SuffixVerificationError, build_model, closed_task,
                                strict_task, enumerate_words)
from .checker import check_regime, verify_lp_certificate, aggregate_records, check_query_ledger, _bound_audit


def initial_context(effect='S', **changes):
    case = dict(case_id='suffix-independent-certificates', H_ref=2, origin='o', destination='z',
                start_time_s=0, initial_energy_kwh=2, capacity_kwh=5, minimum_energy_kwh=0,
                reserve_kwh=0, overhead_s=1, lambda_stop_s=0, consumption_kwh_per_m=1,
                schedule=None if effect == 'C' else dict(a=10, b=20, D=3),
                sites={'s': [effect]}, site_anchors={'s': 'o'},
                charging_segments=[[0, 5, 1, 7]],
                edges=[dict(source='o', target='z', time_s=1, length_m=1)])
    case.update(changes)
    energy, start = str(case['initial_energy_kwh']), str(case['start_time_s'])
    remaining = case.get('initial_remaining_schedule', int(case['schedule'] is not None))
    piece = dict(domain=[energy, energy, True, True], m='0', b=start, chi=True,
                 rho=str(-F(energy)), pi=[], state=[case['origin'], remaining, 0])
    node = dict(kind='initial', parents=[], output=piece, params={'case': case})
    ident = digest(node)
    bundle = dict(schema='family5-v1', nodes={ident: node}, batches=[], batch_ids=[], roots=[ident])
    return verify_bundle(bundle, case), ident


def certificate(task, x, dual=(), equality_dual=None):
    x = list(map(lambda value: str(F(value)), x))
    y = ['0']*len(task['A'])
    for index, value in dual:
        y[index] = str(F(value))
    z = ['0']*len(task['equalities']) if equality_dual is None else list(map(lambda a: str(F(a)), equality_dual))
    objective = sum((F(a)*F(b) for a, b in zip(task['c'], x)), F(0))
    return dict(status='optimal', x=x, objective=str(objective), inequality_dual=y,
                equality_dual=z, exact_primal_dual_verified=True)


def hand_record(effect='S', **changes):
    ctx, ident = initial_context(effect, **changes)
    model = build_model(ctx, ident, [['s', effect]])
    if model['exclusion'] is not None:
        return ctx, dict(model=model, stages=[], result=dict(status='graph_unreachable'))
    labels = {row['label']: i for i, row in enumerate(model['lp']['rows'])}
    stages = []
    def add(name, task, x, weights=(), z=None):
        dual = [(labels[label] if type(label) is str else label, value) for label, value in weights]
        stages.append(dict(name=name, task=task, certificate=certificate(task, x, dual, z)))
    e = ctx._physics.initial
    strict = strict_task(model)
    if ctx._physics.schedule and ctx._physics.schedule[0] > ctx._physics.schedule[1]:
        # The zero service-window row requires a common Phase-I violation of 10.
        phase_task = dict(c=['0']*5+['1'], A=[row+['-1'] for row in strict['A']]+[['0']*5+['-1']],
                          b=strict['b']+['0'], equalities=[])
        phase = certificate(phase_task, [e, 0, 0, 13, 1, 10], [(labels['service_window_nonempty:0'], -1)])
        stages.append(dict(name='feasibility', task=strict,
                           certificate=dict(status='infeasible', phase_I_certificate=phase)))
        return ctx, dict(model=model, stages=stages, result=dict(status='closed_infeasible'))
    if effect == 'C' and e == ctx._physics.capacity:
        add('feasibility', strict, [e, 0, 0, 1, 0],
            [('departure_capacity:0', -1), ('prefix_energy_lower', -1), ('charge_positive:0', -1)])
        return ctx, dict(model=model, stages=stages, result=dict(status='strict_infeasible'))
    completion = 1 if effect == 'C' else 13
    add('feasibility', strict, [e, 0, 0 if effect == 'S' else 1, 13, 1], [(len(strict['A'])-1, -1)])
    primary = closed_task(model, 'J')
    primary_weights = ([('charge_completion:0', -1), ('prefix_time', -1), ('charge_positive:0', -1)]
                       if effect == 'C' else [('service_release_completion:0', -1)])
    add('primary', primary, [e, 0, 0, completion], primary_weights)
    faces = [[model['lp']['J']['coefficients'], str(completion)]]
    margin = strict_task(model, faces)
    if effect == 'C':
        add('primary_attainment', margin, [e, 0, 0, completion, 0], primary_weights, [-1])
        return ctx, dict(model=model, stages=stages,
                        result=dict(status='primary_unattained', primary_infimum='2'))
    add('primary_attainment', margin, [e, 0, 0 if effect == 'S' else 1, completion, 1],
        [(len(margin['A'])-1, -1)])
    secondary = closed_task(model, 'Q', faces)
    lower = 'service_charge_zero_lower:0' if effect == 'S' else 'charge_positive:0'
    add('secondary', secondary, [e, 0, 0, completion], [('prefix_energy_lower', -1), (lower, -1)])
    faces.append([model['lp']['Q']['coefficients'], str(e)])
    margin = strict_task(model, faces)
    if effect == 'CS':
        add('secondary_attainment', margin, [e, 0, 0, completion, 0],
            [('prefix_energy_lower', -1), ('charge_positive:0', -1)], [0, -1])
        result = dict(status='secondary_unattained', J='14', secondary_infimum='0')
    else:
        add('secondary_attainment', margin, [e, 0, 0, completion, 1], [(len(margin['A'])-1, -1)])
        result = dict(status='attained_optimum', J='14', Q_total='0', H=1,
                      site_action_tuple=[['s', 'S']], lex_key=['14', '0', 1, [['s', 'S']]])
    return ctx, dict(model=model, stages=stages, result=result)


def inherited_open_context():
    """CS release plateau followed by C gives a strict inherited time ray."""
    ctx, ident = initial_context('CS', H_ref=4, start_time_s=5, lambda_stop_s=3,
        sites={'o':['CS','C']}, site_anchors={'o':'o'}, schedule=dict(a=10,b=10,D=0))
    bundle = ctx.snapshot()
    case = bundle['nodes'][ident]['params']['case']
    def stop(parent, effect, count, intercept, attained):
        piece = dict(domain=['2','5',False,True],m='0',b=str(intercept),chi=attained,
                     rho='-2',pi=[['o','CS']]+[['o','C']]*(count-1),state=['o',0,count])
        schedule = dict(a='10',b='10',D='0') if effect == 'CS' else dict(a='0',b='0',D='0')
        params = dict(effect=effect,site='o',h='1',curve=[['0','5','1','7']],**schedule)
        node = dict(kind='stop',parents=[parent],output=piece,
                    params=dict(**params,in_segment=['0','5','1','7'],out_segment=['0','5','1','7']))
        node_id = digest(node); bundle['nodes'][node_id] = node
        batch = dict(kind='stop',parents=[parent],outputs=[node_id],params=params)
        bundle['batches'].append(batch); bundle['batch_ids'].append(digest(batch))
        return node_id
    first = stop(ident,'CS',1,10,True)
    second = stop(first,'C',2,11,False)
    piece = deepcopy(bundle['nodes'][second]['output']);piece['domain']=['3','4',False,False]
    node = dict(kind='restrict',parents=[second],output=piece,
                params=dict(domain=piece['domain'],reason='hand-authored inherited open interval'))
    restricted = digest(node);bundle['nodes'][restricted]=node;bundle['roots']=[restricted]
    return verify_bundle(bundle,case),restricted


def checked_hand_trace():
    """Add an unused valid affine primitive to an existing independent trace."""
    from validation.trace5.test_checker_units import hand_trace
    from validation.trace5 import verify_trace
    case, bundle, trace = hand_trace()
    old_case_digest = digest(case)
    case['charging_segments'] = [[0, 3, 1, 0]]
    replacements = {old_case_digest: digest(case)}
    def rewrite(value):
        if type(value) is str:
            return replacements.get(value, value)
        if type(value) is list:
            return [rewrite(x) for x in value]
        if type(value) is dict:
            return {key: rewrite(child) for key, child in value.items()}
        return value
    nodes = {}
    for ident, old in bundle['nodes'].items():
        node = rewrite(old)
        if node['kind'] == 'initial':
            node['params']['case'] = deepcopy(case)
        new_id = digest(node)
        replacements[ident] = new_id
        nodes[new_id] = node
    bundle = rewrite(bundle)
    bundle['nodes'] = nodes
    bundle['batch_ids'] = [digest(batch) for batch in bundle['batches']]
    trace = rewrite(trace)
    return verify_trace(trace, bundle, case)


def hand_ledger():
    checked = checked_hand_trace()
    query = checked.export_queries()[0]
    records = []
    for family_id in query['family_ids']:
        for word in enumerate_words(checked.bundle, family_id, query['actions']):
            model = build_model(checked.bundle, family_id, word)
            if model['exclusion'] is not None:
                records.append(dict(model=model, stages=[], result=dict(status='graph_unreachable')))
                continue
            labels = {row['label']: i for i, row in enumerate(model['lp']['rows'])}
            faces, stages = [], []
            for name, task, x, dual in [
                ('feasibility', strict_task(model), [2, 0, 0, 2, 1], 'margin'),
                ('primary', closed_task(model, 'J'), [2, 0, 0, 2], 'primary')]:
                weights = [(len(task['A'])-1, -1)] if dual == 'margin' else [
                    (labels['service_own_completion:0'], -1), (labels['prefix_time'], -1)]
                stages.append(dict(name=name, task=task, certificate=certificate(task, x, weights)))
            faces.append([model['lp']['J']['coefficients'], '2'])
            task = strict_task(model, faces)
            stages.append(dict(name='primary_attainment', task=task,
                certificate=certificate(task, [2, 0, 0, 2, 1], [(len(task['A'])-1, -1)])))
            task = closed_task(model, 'Q', faces)
            stages.append(dict(name='secondary', task=task,
                certificate=certificate(task, [2, 0, 0, 2], [(labels['prefix_energy_lower'], -1),
                            (labels['service_charge_zero_lower:0'], -1)])))
            faces.append([model['lp']['Q']['coefficients'], '2'])
            task = strict_task(model, faces)
            stages.append(dict(name='secondary_attainment', task=task,
                certificate=certificate(task, [2, 0, 0, 2, 1], [(len(task['A'])-1, -1)])))
            result = dict(status='attained_optimum', J='3', Q_total='0', H=1,
                          site_action_tuple=[['s', 'S']], lex_key=['3', '0', 1, [['s', 'S']]])
            records.append(dict(model=model, stages=stages, result=result))
    ledger = dict(schema='family5-suffix-query-ledger-v1', query_seq=query['query_seq'],
                  query_sha256=digest(query), trace_sha256=checked.summary['trace_sha256'],
                  models=records, result=aggregate_records(records))
    return checked, ledger


def pending_service_trace():
    """Hand-authored reachable C query with one stop left and service pending."""
    from validation.trace5 import verify_trace
    case = dict(case_id='suffix-pending-service-language',H_ref=1,origin='o',destination='z',
        start_time_s=0,initial_energy_kwh=2,capacity_kwh=3,minimum_energy_kwh=0,
        reserve_kwh=0,overhead_s=1,lambda_stop_s=0,consumption_kwh_per_m=0,
        schedule=dict(a=0,b=10,D=0),sites={'s':['C']},charging_segments=[[0,3,1,0]],
        edges=[dict(source='o',target='s',time_s=1,length_m=1),
               dict(source='s',target='z',time_s=1,length_m=1)])
    bundle=dict(schema='family5-v1',nodes={},batches=[],batch_ids=[],roots=[])
    trace=dict(schema='family5-hier-trace-v1',events=[])
    def event(kind,**payload):
        seq=len(trace['events']);trace['events'].append(dict(seq=seq,kind=kind,payload=payload));return seq
    def node(kind,parents,piece,params):
        record=dict(kind=kind,parents=parents,output=piece,params=params)
        ident=digest(record);bundle['nodes'][ident]=record;return ident
    def batch(kind,parents,outputs,params):
        record=dict(kind=kind,parents=parents,outputs=outputs,params=params)
        bundle['batches'].append(record);bundle['batch_ids'].append(digest(record))
    invocation=0
    def invoke(operation,parents,outputs,params,begin):
        nonlocal invocation
        index=invocation;invocation+=1
        event('invoke',invocation_id=index,operation=operation,input_families=parents,
              output_families=outputs,params=params,batch_range=[begin,len(bundle['batches'])])
        return index
    root=dict(id=0,members=['s'],children=[])
    event('run_start',case_sha256=digest(case),dominance=False,H_ref=1,regions=root)
    initial_piece=dict(domain=['2','2',True,True],m='0',b='0',chi=True,rho='-2',pi=[],state=['o',1,0])
    initial=node('initial',[],initial_piece,dict(case=case))
    invoke('initial',[],[initial],{},0)
    event('layer_start',depth=0,groups=[dict(group_id=0,families=[initial])])
    invoke('finish',[initial],[],dict(group_id=0,source='layer',advance_id=None),0)
    event('expansion_start',group_id=0)
    query_seq=event('query',group_id=0,region_id=0,effect='C',actions=[['s','C']],bound='3',
                    classification='queued',queue_serial=1)
    for effect in ('S','CS'):
        event('query',group_id=0,region_id=0,effect=effect,actions=[],bound=None,
              classification='empty_actions',queue_serial=None)
    event('pop',group_id=0,query_seq=query_seq,decision='leaf',incumbent_key=None)
    drive_piece=deepcopy(initial_piece);drive_piece.update(b='1',state=['s',1,0])
    drive_params=dict(site='s',duration='1',consumption='0',floor='0')
    drive=node('drive',[initial],drive_piece,drive_params)
    batch('drive',[initial],[drive],drive_params)
    stop_params=dict(effect='C',site='s',h='1',a='0',b='0',D='0',curve=[['0','3','1','0']])
    raw=[]
    for domain in (['2','3',False,False],['3','3',True,True]):
        piece=dict(domain=domain,m='1',b='0',chi=True,rho='-2',pi=[['s','C']],state=['s',1,1])
        raw.append(node('stop',[drive],piece,
            dict(**stop_params,in_segment=['0','3','1','0'],out_segment=['0','3','1','0'])))
    batch('stop',[drive],raw,stop_params)
    output=[]
    for index,ident in enumerate(raw):
        piece=deepcopy(bundle['nodes'][ident]['output'])
        output.append(node('select',raw,piece,dict(domain=piece['domain'],chosen=index,mode='union')))
    batch('union',raw,output,{})
    advance=invoke('advance',[initial],output,dict(group_id=0,site='s',effect='C'),0)
    invoke('finish',output,[],dict(group_id=0,source='leaf',advance_id=advance),3)
    event('expansion_end',group_id=0,covered_actions=[['s','C']])
    event('layer_end',depth=0,reason='continue',next_groups=[output])
    event('layer_start',depth=1,groups=[dict(group_id=1,families=output)])
    invoke('finish',output,[],dict(group_id=1,source='layer',advance_id=None),3)
    event('layer_end',depth=1,reason='stop_bound',next_groups=[])
    event('run_end',canonical=dict(scope='bounded_H_ref_diagnostic',H_ref=1,
          result=dict(status='infeasible_within_H_ref')),terminal_families=[],
          terminal_witness=None,terminal_family_id=None)
    return verify_trace(trace,bundle,case)


class IndependentSuffixCertificates(unittest.TestCase):
    def test_hand_derived_all_statuses(self):
        examples = [('S', {}, 'attained_optimum'), ('CS', {}, 'secondary_unattained'),
                    ('C', {}, 'primary_unattained'), ('C', {'initial_energy_kwh': 5}, 'strict_infeasible'),
                    ('S', {'schedule': dict(a=10, b=0, D=3)}, 'closed_infeasible'),
                    ('S', {'edges': []}, 'graph_unreachable')]
        for effect, changes, status in examples:
            with self.subTest(effect=effect, status=status):
                ctx, record = hand_record(effect, **changes)
                self.assertEqual(check_regime(ctx, record)['status'], status)
                self.assertEqual(check_regime(ctx, record, with_audit=True)['result'], record['result'])

    def test_service_rows_are_hand_checked(self):
        ctx, ident = initial_context()
        lp = build_model(ctx, ident, [['s', 'S']])['lp']
        expected = [([-1, 0, 0, 0], -2), ([1, 0, 0, 0], 2), ([0, -1, 0, 0], 0),
                    ([-1, 0, 0, 0], 0), ([1, 0, 1, 0], 5), ([0, 0, 1, 0], 0),
                    ([0, 0, -1, 0], 0), ([0, 0, 0, 0], 10), ([0, 1, 0, 0], 19),
                    ([0, 0, 0, -1], -13), ([0, 1, 0, -1], -4), ([-1, 0, -1, 0], -1)]
        self.assertEqual([(list(map(F, row['coefficients'])), F(row['rhs'])) for row in lp['rows']], expected)
        self.assertTrue(all(row['strict'] is False for row in lp['rows']))
        self.assertEqual(lp['J'], dict(coefficients=['0', '0', '0', '1'], constant='1'))
        self.assertEqual(lp['Q'], dict(coefficients=['1', '0', '1', '0'], constant='-2'))

    def test_actual_inherited_open_energy_time_rho_pi_and_stop_count(self):
        ctx, ident = inherited_open_context()
        model = build_model(ctx,ident,[['o','C']])
        lp=model['lp']
        self.assertEqual([row['rhs'] for row in lp['rows'][:3]],['-3','4','-11'])
        self.assertEqual([row['strict'] for row in lp['rows'][:3]],[True,True,True])
        self.assertEqual(model['H'],3)
        self.assertEqual(model['pi'],[['o','CS'],['o','C'],['o','C']])
        self.assertEqual(lp['J']['constant'],'5')
        self.assertEqual(lp['Q']['constant'],'-2')
        strict = strict_task(model)
        for original, transformed in zip(lp['rows'],strict['A']):
            self.assertEqual(transformed[-1],'1' if original['strict'] else '0')
        # No artificial strictness is attached to the objective face.
        self.assertEqual(strict_task(model,[[lp['J']['coefficients'],'12']])['equalities'][0][0][-1],'0')

    def test_all_stage_and_model_tampering_is_rejected(self):
        ctx, record = hand_record()
        mutations = []
        bad = deepcopy(record); bad['stages'].pop(); mutations.append(bad)
        bad = deepcopy(record); bad['stages'].append(deepcopy(bad['stages'][-1])); mutations.append(bad)
        bad = deepcopy(record); bad['stages'][0], bad['stages'][1] = bad['stages'][1], bad['stages'][0]; mutations.append(bad)
        for field, value in [('H', True), ('H', 1.0), ('pi', [['s', 'C']]), ('family_id', 'foreign')]:
            bad = deepcopy(record); bad['model'][field] = value; mutations.append(bad)
        for field, value in [('strict', 0), ('strict', True), ('rhs', '3'), ('label', 'wrong')]:
            bad = deepcopy(record); bad['model']['lp']['rows'][0][field] = value; mutations.append(bad)
        bad = deepcopy(record); bad['model']['lp']['J']['constant'] = '2'; mutations.append(bad)
        for field in ('A', 'b', 'c', 'equalities'):
            bad = deepcopy(record); bad['stages'][3]['task'][field] = []; mutations.append(bad)
        for field, value in [('objective', '0'), ('x', ['2','0','0','14']),
                             ('inequality_dual', ['0']*12), ('equality_dual', ['0']),
                             ('exact_primal_dual_verified', 1)]:
            bad = deepcopy(record); bad['stages'][1]['certificate'][field] = value; mutations.append(bad)
        bad = deepcopy(record); bad['result']['H'] = True; mutations.append(bad)
        bad = deepcopy(record); bad['result']['J'] = '14/1'; mutations.append(bad)
        for bad in mutations:
            with self.subTest(bad=bad), self.assertRaises(SuffixVerificationError):
                check_regime(ctx, bad)

    def test_phase_I_equality_signs_and_positive_optimum(self):
        task = dict(c=['0'], A=[], b=[], equalities=[[['1'], '0'], [['1'], '1']])
        phase_task = dict(c=['0','1'], A=[['1','-1'],['-1','-1'],['1','-1'],['-1','-1'],['0','-1']],
                          b=['0','0','1','-1','0'], equalities=[])
        proof = dict(status='infeasible', phase_I_certificate=certificate(
            phase_task, ['1/2','1/2'], [(0, '-1/2'), (3, '-1/2')]))
        self.assertEqual(verify_lp_certificate(task, proof), dict(status='infeasible', phase_I_objective='1/2'))
        for field, value in [('objective', '0'), ('x', ['1/2','0']), ('equality_dual', ['0'])]:
            bad = deepcopy(proof); bad['phase_I_certificate'][field] = value
            with self.assertRaises(SuffixVerificationError):
                verify_lp_certificate(task, bad)
        bad = deepcopy(proof); bad['phase_I_certificate']['inequality_dual'][3] = '1/2'
        with self.assertRaises(SuffixVerificationError):
            verify_lp_certificate(task, bad)

    def test_rational_aliases_rejected(self):
        task = dict(c=['1'], A=[['-1']], b=['0'], equalities=[])
        proof = certificate(task, [0], [(0,-1)])
        for value in [0, False, 0.0, '0/1', '-0', '0.0', '1/0', 'nan']:
            bad = deepcopy(proof); bad['objective'] = value
            with self.subTest(value=value), self.assertRaises(SuffixVerificationError):
                verify_lp_certificate(task, bad)

    def test_arbitrarily_small_exact_strict_margin_is_positive(self):
        tiny=F(1,10**120)
        ctx,ident=initial_context('C',initial_energy_kwh=str(5-tiny))
        model=build_model(ctx,ident,[['s','C']])
        task=strict_task(model)
        labels={row['label']:i for i,row in enumerate(model['lp']['rows'])}
        proof=certificate(task,[5-tiny,0,tiny,1+tiny,tiny],
            [(labels['departure_capacity:0'],-1),(labels['prefix_energy_lower'],-1),
             (labels['charge_positive:0'],-1)])
        self.assertEqual(verify_lp_certificate(task,proof)['objective'],str(-tiny))

    def test_legal_word_order_service_state_repeats_and_graph_exclusions(self):
        ctx, ident = initial_context('C', H_ref=3, schedule=dict(a=0,b=20,D=1),
            sites={'s':['CS','S','C'], 'u':['C']}, site_anchors={'s':'o','u':'u'})
        words = enumerate_words(ctx, ident, [['s','S'], ['s','CS']])
        self.assertEqual(words[:4], [[['s','S']], [['s','S'],['s','C']],
                          [['s','S'],['s','C'],['s','C']], [['s','S'],['s','C'],['u','C']]])
        self.assertTrue(all(sum(effect in ('S','CS') for _, effect in word) == 1 for word in words))
        missing = build_model(ctx, ident, [['s','S'], ['u','C']])
        self.assertEqual(missing['exclusion'], dict(kind='unreachable_selected_leg', leg_index=1, source='o', target='u'))
        self.assertIn([['s','S'],['u','C']], words)
        unfinished,root=initial_context('C',H_ref=1,schedule=dict(a=0,b=20,D=1))
        self.assertEqual(enumerate_words(unfinished,root,[['s','C']]),[])

    def test_aggregation_respects_attained_primary_and_secondary_faces(self):
        _, attained = hand_record('S')
        _, secondary = hand_record('CS')
        _, primary = hand_record('C')
        primary['result']['primary_infimum'] = '14'
        self.assertEqual(aggregate_records([primary, secondary, attained]), attained['result'])
        self.assertEqual(aggregate_records([primary, secondary]), secondary['result'])
        self.assertEqual(aggregate_records([primary]), primary['result'])
        lesser_H = deepcopy(attained)
        larger_H = deepcopy(attained)
        larger_H['result'].update(H=2, site_action_tuple=[['s','S'],['s','C']],
                                  lex_key=['14','0',2,[['s','S'],['s','C']]])
        later_pi = deepcopy(attained)
        later_pi['result'].update(site_action_tuple=[['z','S']], lex_key=['14','0',1,[['z','S']]])
        audit = aggregate_records([larger_H, later_pi, lesser_H, deepcopy(lesser_H)], with_audit=True)
        self.assertEqual(audit['audit']['winning_regimes'], [2,3])
        self.assertEqual(aggregate_records([]), dict(status='empty_restricted_family'))

    def test_complete_ledger_rejects_missing_extra_reordered_foreign_words(self):
        checked, ledger = hand_ledger()
        out = check_query_ledger(checked, ledger, with_audit=True)
        self.assertEqual(out['result']['J'], '3')
        self.assertEqual(out['audit']['regime_count'], 2)
        self.assertEqual(out['audit']['exclusion_counts']['graph_unreachable'], 1)
        self.assertTrue(out['audit']['bound_valid'])
        self.assertEqual(out['audit']['bound_gap'],'0')
        for kind in ('missing','extra','reverse','word','hash','sequence','result'):
            bad = deepcopy(ledger)
            if kind == 'missing': bad['models'].pop()
            elif kind == 'extra': bad['models'].append(deepcopy(bad['models'][0]))
            elif kind == 'reverse': bad['models'].reverse()
            elif kind == 'word': bad['models'][0]['model']['word'] = [['u','S']]
            elif kind == 'hash': bad['query_sha256'] = '0'*64
            elif kind == 'sequence': bad['query_seq'] = float(bad['query_seq'])
            else: bad['result']['J'] = '4'
            with self.subTest(kind=kind), self.assertRaises(SuffixVerificationError):
                check_query_ledger(checked, bad)

    def test_bound_counterexamples_and_missing_bounds_are_retained(self):
        result = dict(status='primary_unattained',primary_infimum='3/2')
        failed = _bound_audit('2',result)
        self.assertFalse(failed['bound_valid'])
        self.assertEqual(failed['bound_gap'],'-1/2')
        self.assertEqual(failed['bound_status'],'violated')
        self.assertEqual(_bound_audit(None,result)['bound_status'],'missing_bound_for_nonempty_family')
        self.assertTrue(_bound_audit(None,dict(status='empty_restricted_family'))['bound_valid'])

    def test_zero_word_pending_service_is_a_language_proof(self):
        checked=pending_service_trace();query=checked.export_queries()[0]
        self.assertEqual(query['H_remaining'],1)
        self.assertEqual(query['state'][1],1)
        self.assertEqual(query['actions'],[['s','C']])
        self.assertTrue(all(leg['incoming'] is not None and leg['onward'] is not None
                            for leg in query['leg_context']))
        ledger=dict(schema='family5-suffix-query-ledger-v1',query_seq=query['query_seq'],
                    query_sha256=digest(query),trace_sha256=checked.summary['trace_sha256'],
                    models=[],result=dict(status='empty_restricted_family'))
        outcome=check_query_ledger(checked,ledger,with_audit=True)
        self.assertTrue(outcome['audit']['legal_completion_language_empty'])
        self.assertEqual(outcome['audit']['original_query_classification'],'queued')
        self.assertEqual(outcome['audit']['regime_count'],0)
        self.assertEqual(outcome['audit']['exclusion_counts'],
            dict(graph_unreachable=0,closed_infeasible=0,strict_infeasible=0))
        self.assertEqual(outcome['audit']['bound_status'],'vacuous_empty_restricted_family')

    def test_optimized_python_and_optimizer_import_blocking(self):
        script = r'''
import sys, unittest
class Block:
    def find_spec(self, fullname, path=None, target=None):
        if (fullname.startswith(('scipy','numpy','stopplan4r','hierarchy4r','timecut5','validation.reference5'))
            or fullname in ('validation.suffix5.model','validation.suffix5.solver','validation.suffix5.vendor_lp')):
            raise RuntimeError('forbidden import '+fullname)
sys.meta_path.insert(0,Block())
from validation.suffix5.test_certificate_checker import IndependentSuffixCertificates
names=[name for name in unittest.defaultTestLoader.getTestCaseNames(IndependentSuffixCertificates)
       if name != 'test_optimized_python_and_optimizer_import_blocking']
result=unittest.TextTestRunner().run(unittest.TestSuite(IndependentSuffixCertificates(name) for name in names))
sys.exit(0 if result.wasSuccessful() else 1)
'''
        root = Path(__file__).resolve().parents[2]
        for optimization in ('', '-O', '-OO'):
            with self.subTest(optimization=optimization):
                command = [sys.executable]+([optimization] if optimization else [])+['-c',script]
                completed = subprocess.run(command, cwd=root, text=True, capture_output=True, timeout=45)
                self.assertEqual(completed.returncode, 0, completed.stdout+completed.stderr)


if __name__ == '__main__':
    unittest.main()
