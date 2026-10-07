"""Reconstructed real-family adapter over the published exact PR7 checker.

The _verify_bundle body is copied from validation.family5.checker; only physics
construction is injected. Published CheckedBundle identity and all mathematical
checks, detached JSON ownership and content hashes remain unchanged. This is
new source, not acceptance of an unavailable historical implementation.
"""
from dataclasses import replace
from fractions import Fraction as F
from itertools import product
from types import MappingProxyType
import json
import time

from validation.family5 import checker as base
from validation.family5 import independent_oracle_v2 as oracle
from validation.family5.checker import (
    CheckedBundle, VerificationError, _validation_api, require, wire_equal,
    _plain, _freeze, canonical, digest, rational, _domain, _piece, _restrict,
    _restricted, _same_piece, _exact, _regime,
)
from .input import TrustedRealCase
from .physical_state import verify_physical_states


@_validation_api
def _verify_bundle(bundle, trusted_case, physics, *, batch_executor=None):
    """Validate all nodes and complete recorded operator invocations exactly.

    Raises VerificationError on rejection. Returns an immutable CheckedBundle.
    The caller supplies the physical case independently of the bundle. This
    does not certify that an external search emitted every required invocation.
    """
    started = time.perf_counter()
    data = json.loads(canonical(bundle))
    require(set(data) == {'schema', 'nodes', 'batches', 'batch_ids', 'roots'}, 'invalid_bundle_fields')
    require(data['schema'] == 'family5-v1', 'unsupported_schema')
    nodes, batches = data['nodes'], data['batches']
    require(isinstance(nodes, dict) and nodes, 'missing_provenance')
    require(isinstance(batches, list) and len(batches) == len(data['batch_ids']), 'missing_batch_digests')
    require(all(x in nodes for x in data['roots']), 'unknown_root')
    pieces, colors, order = {}, {}, []
    def visit(ident):
        require(ident in nodes, 'missing_parent', node=ident)
        require(colors.get(ident) != 1, 'cyclic_proof_graph', node=ident)
        if colors.get(ident) == 2:
            return
        colors[ident] = 1
        n = nodes[ident]
        require(set(n) == {'kind', 'parents', 'output', 'params'}, 'invalid_node_fields', node=ident)
        require(isinstance(n['parents'], list) and isinstance(n['params'], dict), 'invalid_node_containers')
        for parent in n['parents']:
            visit(parent)
        require(digest(n) == ident, 'node_hash_mismatch', node=ident)
        pieces[ident] = _piece(n['output'])
        p = pieces[ident]
        require(physics.floor <= p.lo <= p.hi <= physics.capacity, 'piece_energy_bounds', node=ident)
        require(p.state[2] <= physics.bound, 'piece_exceeds_stop_bound')
        colors[ident] = 2; order.append(ident)
    for ident in nodes:
        visit(ident)
    checked_cells = 0
    regime_cache = {}
    def regime(parent, params):
        key = parent, canonical(params)
        if key not in regime_cache:
            regime_cache[key] = _regime(pieces[parent], params)
        return regime_cache[key]
    def last_nonidentity_actions(ident):
        n = nodes[ident]
        if n['kind'] == 'select':
            return last_nonidentity_actions(n['parents'][n['params']['chosen']])
        if n['kind'] == 'guarded_union':
            return set().union(*(last_nonidentity_actions(x) for x in n['parents']))
        if n['kind'] in ('restrict', 'retag'):
            return last_nonidentity_actions(n['parents'][0])
        if n['kind'] == 'drive' and pieces[n['parents'][0]].state[0] == n['params']['site']:
            return last_nonidentity_actions(n['parents'][0])
        return {n['kind']}
    def drive_params(parent, q):
        require(set(q) == {'site', 'duration', 'consumption', 'floor'}, 'invalid_drive_params')
        p = pieces[parent]; target = q['site']
        require(target in {*physics.anchors.values(), physics.destination, p.state[0]}, 'nonsemantic_drive_endpoint')
        leg = physics.legs.get((p.state[0], target))
        require(leg is not None, 'unreachable_selected_leg')
        require((rational(q['duration']), rational(q['consumption'])) == leg[:2], 'wrong_selected_leg', source=p.state[0], target=target)
        require(rational(q['floor']) == (physics.reserve if target == physics.destination else physics.floor), 'wrong_drive_floor')
        require(p.state[0] != physics.destination or target == physics.destination, 'departure_after_terminal_arrival')
        if target == physics.destination:
            require(p.state[1] == 0, 'terminal_unfulfilled_schedule')
        if target != p.state[0]:
            require('drive' not in last_nonidentity_actions(parent), 'consecutive_drive_waypoint_detour')
    def stop_params(parent, q, individual):
        expected = {'effect', 'site', 'h', 'a', 'b', 'D', 'curve'} | ({'in_segment', 'out_segment'} if individual else set())
        require(set(q) == expected, 'invalid_stop_params')
        p = pieces[parent]; effect, site = q['effect'], q['site']
        require(effect in physics.sites.get(site, ()), 'unavailable_site_effect')
        anchor = physics.anchors[site]
        require(p.state[0] == anchor and anchor != physics.destination, 'invalid_stop_anchor_or_terminal')
        require(p.state[2] < physics.bound, 'stop_bound_exceeded')
        require(rational(q['h']) == physics.overhead, 'wrong_stop_overhead')
        if effect in ('S', 'CS'):
            require(physics.schedule is not None and p.state[1] == 1, 'invalid_service_state')
            expected_schedule = physics.schedule
        else:
            expected_schedule = (F(0), F(0), F(0))
        require(tuple(rational(q[k]) for k in ('a', 'b', 'D')) == expected_schedule, 'wrong_service_parameters')
        expected_curve = physics.curve if effect in ('C', 'CS') else ()
        require(tuple(tuple(map(rational, r)) for r in q['curve']) == expected_curve, 'wrong_charging_curve')
        if individual:
            if effect == 'S':
                require(q['in_segment'] is None and q['out_segment'] is None, 'service_segment_guard')
            else:
                require(tuple(map(rational, q['in_segment'])) in physics.curve
                        and tuple(map(rational, q['out_segment'])) in physics.curve, 'false_charging_segment_guard')
    for ident in order:
        n, p = nodes[ident], pieces[ident]
        kind, parents, q = n['kind'], n['parents'], n['params']
        if kind == 'initial':
            require(not parents and set(q) == {'case'}, 'invalid_initial_node')
            require(canonical(q['case']) == canonical(trusted_case), 'trusted_case_mismatch')
            expected = oracle.Piece(physics.initial, physics.initial, True, True, F(0), physics.start,
                                    True, -physics.initial, (), (physics.origin, physics.remaining, 0))
            _same_piece(p, expected, 'wrong_initial_piece')
        elif kind == 'drive':
            require(len(parents) == 1, 'drive_parent_count')
            drive_params(parents[0], q)
            expected = oracle.transform([pieces[parents[0]]], 'D', q)
            require(len(expected) == 1, 'nonempty_drive_from_empty_domain')
            _same_piece(p, expected[0], 'drive_output_mismatch')
        elif kind == 'stop':
            require(len(parents) == 1, 'stop_parent_count')
            stop_params(parents[0], q, True)
            checked_cells += _exact([p], _restricted(regime(parents[0], q), n['output']['domain']), 'stop_regime_output_mismatch')
        elif kind in ('restrict', 'select'):
            if kind == 'restrict':
                require(len(parents) == 1 and set(q) == {'domain', 'reason'} and isinstance(q['reason'], str), 'invalid_restriction')
                parent = parents[0]
            else:
                require(parents and set(q) == {'domain', 'chosen', 'mode'}, 'invalid_selection')
                require(type(q['chosen']) is int and 0 <= q['chosen'] < len(parents), 'invalid_chosen_parent')
                require(q['mode'] in ('union', 'reduction'), 'invalid_selection_mode')
                parent = parents[q['chosen']]
            expected = _restrict(pieces[parent], q['domain'])
            require(expected is not None and tuple(q['domain']) == tuple(n['output']['domain']), 'selection_or_restriction_domain')
            # No record may claim a requested guard extending beyond its parent.
            require((expected.lo, expected.hi, expected.lc, expected.rc) == _domain(q['domain']), 'enlarged_ancestor_guard')
            _same_piece(p, expected, 'restriction_or_selected_parent_output')
            if kind == 'select' and q['mode'] == 'union':
                require(len({pieces[x].family() for x in parents}) == 1, 'union_crosses_family_key')
                checked_cells += _exact([p], _restricted([pieces[x] for x in parents], q['domain']), 'union_local_minimum_or_attainment')
        elif kind == 'guarded_union':
            require(parents and set(q) == {'guards'} and len(q['guards']) == len(parents), 'invalid_guarded_union')
            for parent, guard in zip(parents, q['guards']):
                old = pieces[parent]
                require(wire_equal(guard, nodes[parent]['output']['domain']), 'guarded_union_parent_guard')
                require((p.m, p.b, p.chi, p.rho, p.pi, p.state) ==
                        (old.m, old.b, old.chi, old.rho, old.pi, old.state), 'guarded_union_changes_metadata')
            checked_cells += _exact([p], [pieces[x] for x in parents], 'guarded_union_connected_coverage')
        elif kind == 'retag':
            require(len(parents) == 1 and set(q) == {'anchor'}, 'invalid_retag')
            old = pieces[parents[0]]
            require(old.pi and old.state[0] == old.pi[-1][0], 'retag_requires_site_state')
            require(physics.anchors.get(old.pi[-1][0]) == q['anchor'], 'retag_wrong_physical_anchor')
            _same_piece(p, replace(old, state=(q['anchor'], *old.state[1:])), 'retag_changes_nonanchor_fields')
        else:
            raise VerificationError(f'unsupported node kind {kind}')
    owned = set()
    if batch_executor is not None:
        from .batch_jobs import BatchExecutor
        require(type(batch_executor) is BatchExecutor, 'unsupported_batch_executor')
        batch_executor.start((i, data['batch_ids'][i], batch['kind']) for i, batch in enumerate(batches)
                             if batch['kind'] in ('union', 'reduction'))
    for i, batch in enumerate(batches):
        require(set(batch) == {'kind', 'parents', 'outputs', 'params'}, 'invalid_batch_fields')
        require(digest(batch) == data['batch_ids'][i], 'batch_hash_mismatch', batch=i)
        kind, parents, outputs, q = (batch[k] for k in ('kind', 'parents', 'outputs', 'params'))
        require(all(x in nodes for x in parents+outputs), 'missing_batch_node')
        # A repeated identical support item does not change a cut closure.
        # Multiplicity requires an independently attested invocation manifest;
        # never invent a semantic rejection merely from repeated support IDs.
        ps, os = [pieces[x] for x in parents], [pieces[x] for x in outputs]
        if kind == 'drive':
            for parent in parents:
                drive_params(parent, q)
                actual_ids = [x for x in outputs if nodes[x]['parents'] == [parent]]
                for x in actual_ids:
                    require(nodes[x]['kind'] == 'drive' and nodes[x]['params'] == q, 'drive_batch_output_origin')
                expected = oracle.transform([pieces[parent]], 'D', q)
                require(len(set(actual_ids)) == len(expected), 'drive_batch_source_coverage')
                checked_cells += _exact([pieces[x] for x in actual_ids], expected, 'drive_batch_closure')
            require(all(nodes[x]['kind'] == 'drive' and len(nodes[x]['parents']) == 1 and nodes[x]['parents'][0] in parents for x in outputs), 'unrelated_drive_batch_output')
        elif kind == 'stop':
            for parent in parents:
                stop_params(parent, q, False)
            expected_pairs = [(None, None)] if q['effect'] == 'S' else list(product(physics.curve, repeat=2))
            matched = set()
            for parent in parents:
                for ins, outs in expected_pairs:
                    params = {**q, 'in_segment': _plain(ins), 'out_segment': _plain(outs)}
                    actual_ids = [x for x in outputs if nodes[x]['kind'] == 'stop' and nodes[x]['parents'] == [parent]
                                  and canonical(nodes[x]['params']) == canonical(params)]
                    matched.update(actual_ids)
                    actual = [pieces[x] for x in actual_ids]
                    checked_cells += _exact(actual, regime(parent, params), 'stop_batch_missing_regime_or_cell')
            require(matched == set(outputs), 'unrelated_stop_batch_output')
        elif kind in ('union', 'reduction'):
            require(not q, 'unexpected_selection_batch_params')
            for x in outputs:
                n = nodes[x]
                require(n['kind'] == 'select' and n['parents'] == parents and n['params']['mode'] == kind, 'selection_batch_origin')
            if kind == 'union':
                require(not ps or len({p.family() for p in ps}) == 1, 'union_batch_crosses_family_key')
            if batch_executor is not None:
                # Every origin/parent/parameter check above remains serial.
                # Only the complete independent scalar batch obligation moves.
                batch_executor.submit(i, data['batch_ids'][i], kind, ps, os)
            elif kind == 'union':
                checked_cells += _exact(ps, os, 'union_batch_missing_minimum_or_attainment')
            else:
                try:
                    certificate = oracle.equivalent(ps, os)
                    oracle.antichain(list(dict.fromkeys(os)))
                except AssertionError as exc:
                    raise VerificationError(f'reduction_full_key_coverage: {exc}') from exc
                checked_cells += certificate['cells']
        else:
            raise VerificationError(f'unsupported batch kind {kind}')
        owned.update(outputs)
    require(all(ident in owned for ident, n in nodes.items() if n['kind'] in ('drive', 'stop', 'select')), 'operator_node_missing_complete_batch')
    if batch_executor is not None:
        checked_cells += batch_executor.finish()
    summary = dict(schema='family5-check-v1', verified=True, nodes=len(nodes), batches=len(batches),
                   checked_affine_cells=checked_cells, distinct_stop_regimes=len(regime_cache),
                   case_sha256=digest(trusted_case), bundle_sha256=digest(data),
                   elapsed_s=time.perf_counter()-started,
                   scope='recorded_synthetic_cut_families_only',
                   trace_invocation_completeness='separate_recorder_attestation_required',
                   literal_G8_closed=False)
    return CheckedBundle(_freeze(data), physics, MappingProxyType(pieces), _freeze(summary))


@_validation_api
def verify_bundle(bundle, trusted_case):
    """Verify exact real-leg family math plus provenance-derived anchor phase."""
    require(isinstance(trusted_case, TrustedRealCase), "trusted_real_case_required")
    case = trusted_case.case_snapshot()
    checked = _verify_bundle(bundle, case, trusted_case.physics)
    verify_physical_states(checked)
    summary = dict(_plain(checked.summary), scope="recorded_real_immutable_leg_cut_families_only",
                   real_input_sources=trusted_case.source_snapshot(), reconstructed_checker=True)
    return replace(checked, summary=_freeze(summary))


def _checked(bundle, trusted_case):
    if isinstance(bundle, CheckedBundle):
        require(isinstance(trusted_case, TrustedRealCase), "trusted_real_case_required")
        require(canonical(bundle._physics.case) == canonical(trusted_case.case_snapshot()), "trusted_case_mismatch")
        require(bundle._physics == trusted_case.physics, "trusted_real_physics_mismatch")
        verify_physical_states(bundle)
        return bundle
    return verify_bundle(bundle, trusted_case)


def check_witness(bundle, node_id, witness_dict, contract=None, *, trusted_case=None):
    context = bundle if isinstance(bundle, CheckedBundle) and trusted_case is None else _checked(bundle, trusted_case)
    verify_physical_states(context)
    return base.check_witness(context, node_id, witness_dict, contract)


def check_receipt(bundle, node_id, witness_dict, contract, receipt, *, trusted_case=None, require_budgets=False):
    context = bundle if isinstance(bundle, CheckedBundle) and trusted_case is None else _checked(bundle, trusted_case)
    verify_physical_states(context)
    return base.check_receipt(context, node_id, witness_dict, contract, receipt, require_budgets=require_budgets)


def reconstruct(bundle, node_id, energy, budget, *, trusted_case=None):
    context = bundle if isinstance(bundle, CheckedBundle) and trusted_case is None else _checked(bundle, trusted_case)
    verify_physical_states(context)
    return base.reconstruct(context, node_id, energy, budget)
