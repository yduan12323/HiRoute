"""Exact, independent physical cut-family checker and constructive replayer.

Only Python's standard library and the frozen independent analytic oracle are
imported. No production projection, reduction, witness builder or REF optimizer
is used. A content hash binds identity; the analytic and recursive checks, not
that hash, establish the claimed semantics. Trace invocation completeness is a
separate recorder-attestation obligation, not a consequence of this checker.
"""
from dataclasses import dataclass, replace
from fractions import Fraction as F
from functools import wraps
from itertools import product
from types import MappingProxyType
import hashlib
import json
import time

from . import independent_oracle_v2 as oracle


class VerificationError(ValueError):
    """Malformed, unsupported, physically invalid or unfaithful evidence."""


def _validation_api(function):
    @wraps(function)
    def checked(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (KeyError, TypeError, IndexError, AttributeError, RecursionError) as exc:
            raise VerificationError(f'malformed_or_unsupported_evidence: {type(exc).__name__}: {exc}') from exc
    return checked


def require(test, reason, **detail):
    if not test:
        raise VerificationError(json.dumps(dict(reason=reason, **detail), sort_keys=True, default=str))


def wire_equal(left, right):
    """Compare JSON values without Python's bool/int/float equality aliases.

    Inputs used for evidence checks are already detached JSON values. Every
    recursive scalar/container type must match, in addition to its value.
    """
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return left.keys() == right.keys() and all(wire_equal(left[k], right[k]) for k in left)
    if type(left) is list:
        return len(left) == len(right) and all(wire_equal(a, b) for a, b in zip(left, right))
    return type(left) in (str, int, float, bool, type(None)) and left == right


def _plain(x):
    if isinstance(x, dict) or isinstance(x, MappingProxyType):
        return {k: _plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_plain(v) for v in x]
    if isinstance(x, F):
        return str(x)
    return x


def _freeze(x):
    if isinstance(x, dict):
        return MappingProxyType({k: _freeze(v) for k, v in x.items()})
    if isinstance(x, list):
        return tuple(_freeze(v) for v in x)
    return x


def canonical(x):
    return json.dumps(_plain(x), sort_keys=True, separators=(',', ':'), ensure_ascii=True)


def digest(x):
    return hashlib.sha256(canonical(x).encode()).hexdigest()


def rational(x):
    require(type(x) in (int, str) or isinstance(x, F), 'non_exact_rational', value=repr(x))
    try:
        return F(x)
    except (ValueError, ZeroDivisionError) as exc:
        raise VerificationError('invalid rational') from exc


def _domain(d):
    require(isinstance(d, (tuple, list)) and len(d) == 4, 'invalid_domain')
    lo, hi = map(rational, d[:2])
    lc, rc = d[2:]
    require(type(lc) is bool and type(rc) is bool, 'invalid_endpoint_flags')
    require(lo < hi or lo == hi and lc and rc, 'empty_recorded_domain')
    return lo, hi, lc, rc


def _piece(data):
    require(set(data) == {'domain', 'm', 'b', 'chi', 'rho', 'pi', 'state'}, 'invalid_piece_fields')
    lo, hi, lc, rc = _domain(data['domain'])
    require(type(data['chi']) is bool, 'invalid_chi')
    state = tuple(data['state'])
    require(len(state) == 3 and isinstance(state[0], str)
            and type(state[1]) is int and state[1] in (0, 1)
            and type(state[2]) is int and state[2] >= 0, 'invalid_state')
    pi = tuple(tuple(x) for x in data['pi'])
    require(all(len(x) == 2 and isinstance(x[0], str) and x[1] in ('C', 'S', 'CS') for x in pi), 'invalid_pi')
    require(len(pi) == state[2], 'pi_stop_count')
    # Recorded exact numerical fields have a single documented wire type.
    require(all(isinstance(x, str) for x in (*data['domain'][:2], data['m'], data['b'], data['rho'])), 'non_string_recorded_rational')
    return oracle.Piece(lo, hi, lc, rc, rational(data['m']), rational(data['b']), data['chi'], rational(data['rho']), pi, state)


def _restrict(p, d):
    lo, hi, lc, rc = _domain(d)
    a, b = max(lo, p.lo), min(hi, p.hi)
    ac = p.contains(a) and (a > lo or lc) and (a < hi or rc)
    bc = p.contains(b) and (b > lo or lc) and (b < hi or rc)
    if a > b or a == b and not (ac and bc):
        return None
    return replace(p, lo=a, hi=b, lc=ac, rc=bc)


def _restricted(pieces, d):
    return [q for p in pieces if (q := _restrict(p, d)) is not None]


def _same_piece(a, b, reason):
    require(a == b, reason, actual=a.dump(), expected=b.dump() if b else None)


def _exact(a, b, reason):
    try:
        return oracle.exact_family_equal(a, b)
    except AssertionError as exc:
        raise VerificationError(f'{reason}: {exc}') from exc


@dataclass(frozen=True)
class _Physics:
    case: object
    origin: str
    destination: str
    start: F
    initial: F
    floor: F
    reserve: F
    capacity: F
    overhead: F
    bound: int
    remaining: int
    sites: object
    anchors: object
    curve: tuple
    schedule: tuple | None
    legs: object

    @classmethod
    def build(cls, case):
        require('edges' in case, 'unsupported_adapter_requires_synthetic_edges')
        origin, destination = case['origin'], case['destination']
        require(isinstance(origin, str) and isinstance(destination, str), 'invalid_anchors')
        start, initial, floor, reserve, cap, h, rate, penalty = [rational(case[k]) for k in
            ('start_time_s', 'initial_energy_kwh', 'minimum_energy_kwh', 'reserve_kwh',
             'capacity_kwh', 'overhead_s', 'consumption_kwh_per_m', 'lambda_stop_s')]
        bound = case['H_ref']
        require(type(bound) is int and bound >= 0 and h > 0 and rate >= 0 and penalty >= 0
                and cap > 0 and 0 <= floor <= initial <= cap and floor <= reserve <= cap, 'invalid_physical_bounds')
        sites = {s: tuple(effects) for s, effects in case['sites'].items()}
        require(all(isinstance(s, str) and s and set(v) <= {'C', 'S', 'CS'} for s, v in sites.items()), 'invalid_site_capability')
        anchors = dict(case.get('site_anchors', {s: s for s in sites}))
        require(set(anchors) == set(sites) and all(isinstance(a, str) and a for a in anchors.values()), 'invalid_site_anchor_mapping')
        curve = tuple(tuple(map(rational, r)) for r in case['charging_segments'])
        if curve:
            require(all(len(r) == 4 and r[0] < r[1] and r[2] > 0 for r in curve), 'invalid_curve_segments')
            require(curve[0][0] == 0 and curve[-1][1] == cap, 'curve_capacity_coverage')
            require(all(x[1] == y[0] and x[2]*x[1]+x[3] == y[2]*y[0]+y[3] for x, y in zip(curve, curve[1:])), 'curve_discontinuity')
        require(curve or not any(set(v) & {'C', 'CS'} for v in sites.values()), 'missing_curve')
        schedule = tuple(rational(case['schedule'][k]) for k in ('a', 'b', 'D')) if case.get('schedule') else None
        require(schedule is None or schedule[2] >= 0, 'negative_service_duration')
        rem = case.get('initial_remaining_schedule', int(schedule is not None))
        require(type(rem) is int and rem in (0, 1) and (not rem or schedule is not None), 'invalid_initial_schedule')
        nodes = {origin, destination, *anchors.values()}
        adjacency, edge_ids = {}, set()
        for i, edge in enumerate(case['edges']):
            a, b = edge['source'], edge['target']
            dt, length = rational(edge['time_s']), rational(edge['length_m'])
            ident = edge.get('edge_id', edge.get('id', f'input:{i:08d}'))
            require(isinstance(a, str) and isinstance(b, str) and dt > 0 and length > 0, 'invalid_road_edge')
            require(isinstance(ident, str) and ident not in edge_ids, 'invalid_edge_identity')
            edge_ids.add(ident); nodes.update((a, b))
            adjacency.setdefault(a, []).append((b, dt, length, ident))
        # Enumerate simple paths rather than reusing production's Dijkstra.
        # Positive travel times imply an optimal path never repeats a node.
        legs = {}
        for source in sorted(nodes):
            candidates = {}
            def walk(node, path, ids, dt, length):
                key = dt, path, ids
                if node not in candidates or key < candidates[node][0]:
                    candidates[node] = key, length
                for target, td, ld, ident in adjacency.get(node, ()):
                    if target not in path:
                        walk(target, path+(target,), ids+(ident,), dt+td, length+ld)
            walk(source, (source,), (), F(0), F(0))
            for target, (key, length) in candidates.items():
                dt, path, ids = key
                legs[source, target] = (dt, length*rate, path, ids)
        return cls(_freeze(json.loads(canonical(case))), origin, destination, start, initial, floor, reserve,
                   cap, h, bound, rem, MappingProxyType(sites), MappingProxyType(anchors), curve,
                   schedule, MappingProxyType(legs))

    def primitive(self, e):
        values = {m*e+b for lo, hi, m, b in self.curve if lo <= e <= hi}
        require(len(values) == 1, 'energy_outside_charging_primitive', energy=str(e))
        return next(iter(values))


def _regime(source, params):
    effect, site = params['effect'], params['site']
    if effect == 'S':
        return oracle.transform([source], 'S', params)
    h, a, b, D = [rational(params[k]) for k in ('h', 'a', 'b', 'D')]
    il, ih, im, ic = map(rational, params['in_segment'])
    ol, oh, om, oc = map(rational, params['out_segment'])
    rows = [(-F(1), F(0), -source.lo, not source.lc), (F(1), F(0), source.hi, not source.rc),
            (-F(1), F(0), -il, False), (F(1), F(0), ih, False), (F(1), F(1), F(0), True)]
    objectives = [(source.m-im, om, source.b+h+oc-ic, not source.chi)]
    if effect == 'CS':
        if a > b:
            return []
        rows.append((source.m, F(0), b-h-source.b, not source.chi))
        objectives += [(F(0), F(0), a+D, False), (source.m, F(0), source.b+h+D, not source.chi)]
    return oracle.region(source, rows, objectives, ol, oh, effect, site)


@dataclass(frozen=True)
class CheckedBundle:
    """Detached immutable verified snapshot; mutation of the input cannot taint it.

    Obtain with verify_bundle. snapshot() returns a fresh mutable copy, never
    the checker-owned records. summary holds diagnostics, not a gate decision.
    """
    _data: object
    _physics: _Physics
    _pieces: object
    summary: object

    def snapshot(self):
        return _plain(self._data)

    @property
    def roots(self):
        return self._data['roots']


@_validation_api
def verify_bundle(bundle, trusted_case):
    """Validate all nodes and complete recorded operator invocations exactly.

    Raises VerificationError on rejection. Returns an immutable CheckedBundle.
    The caller supplies the physical case independently of the bundle. This
    does not certify that an external search emitted every required invocation.
    """
    started = time.perf_counter()
    data = json.loads(canonical(bundle))
    require(set(data) == {'schema', 'nodes', 'batches', 'batch_ids', 'roots'}, 'invalid_bundle_fields')
    require(data['schema'] == 'family5-v1', 'unsupported_schema')
    physics = _Physics.build(trusted_case)
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
    summary = dict(schema='family5-check-v1', verified=True, nodes=len(nodes), batches=len(batches),
                   checked_affine_cells=checked_cells, distinct_stop_regimes=len(regime_cache),
                   case_sha256=digest(trusted_case), bundle_sha256=digest(data),
                   elapsed_s=time.perf_counter()-started,
                   scope='recorded_synthetic_cut_families_only',
                   trace_invocation_completeness='separate_recorder_attestation_required',
                   literal_G8_closed=False)
    return CheckedBundle(_freeze(data), physics, MappingProxyType(pieces), _freeze(summary))


def _context(bundle, trusted_case):
    if isinstance(bundle, CheckedBundle):
        if trusted_case is not None:
            require(canonical(trusted_case) == canonical(bundle._physics.case), 'trusted_case_mismatch')
        return bundle
    require(trusted_case is not None, 'raw_bundle_requires_trusted_case_or_CheckedBundle')
    return verify_bundle(bundle, trusted_case)


def _guarded_parent(ctx, node, energy):
    for parent in node['parents']:
        if ctx._pieces[parent].contains(energy):
            return parent
    raise VerificationError('guarded_union_has_no_covering_parent')


def _event(effect, site, t, u, x, y):
    return dict(effect=effect, site=site, arrival_time=str(t), departure_time=str(u),
                arrival_energy=str(x), departure_energy=str(y))


def _witness(t, e, rho, pi, state, events):
    return dict(time=str(t), energy=str(e), rho=str(rho), pi=_plain(pi), state=_plain(state), events=events)


def _physical_step(physics, node, parent, energy):
    q, kind = node['params'], node['kind']
    x, t, rho = map(rational, (parent['energy'], parent['time'], parent['rho']))
    pi, state = tuple(map(tuple, parent['pi'])), tuple(parent['state'])
    if kind == 'drive':
        dt, consumption, path, ids = physics.legs[state[0], q['site']]
        require(energy == x-consumption and energy >= rational(q['floor']), 'drive_energy_mismatch')
        u, rho, state = t+dt, rho+consumption, (q['site'], *state[1:])
        event = _event('D', q['site'], t, u, x, energy)
    else:
        effect, site = q['effect'], q['site']
        h, a, b, D = [rational(q[k]) for k in ('h', 'a', 'b', 'D')]
        require(state[0] == physics.anchors[site] != physics.destination, 'physical_stop_anchor')
        if effect == 'S':
            require(energy == x, 'service_changes_inventory')
            u = max(a, t+h)+D
        else:
            require(energy > x, 'strict_charge_required')
            il, ih, *_ = map(rational, q['in_segment'])
            ol, oh, *_ = map(rational, q['out_segment'])
            require(il <= x <= ih and ol <= energy <= oh, 'witness_charging_segment_guard')
            u = t+h+physics.primitive(energy)-physics.primitive(x)
            if effect == 'CS':
                u = max(u, max(a, t+h)+D)
        if effect in ('S', 'CS'):
            require(state[1] == 1 and max(a, t+h) <= b, 'physical_schedule_infeasible')
        pi += ((site, effect),)
        state = (site, state[1] if effect == 'C' else 0, state[2]+1)
        event = _event(effect, site, t, u, x, energy)
    require(physics.floor <= energy <= physics.capacity, 'physical_inventory_bounds')
    return _witness(u, energy, rho, pi, state, list(parent['events'])+[event])


def _contract(piece, witness, contract):
    e, t = rational(witness['energy']), rational(witness['time'])
    if contract is None:
        return None
    require(isinstance(contract, dict) and 'energy' in contract, 'contract_requires_requested_energy')
    require(e == rational(contract['energy']), 'contract_wrong_final_energy')
    kind = contract.get('kind')
    if kind == 'minimum':
        require(piece.chi and t == piece.tau(e), 'minimum_contract', time=str(t), tau=str(piece.tau(e)))
    elif kind == 'approach':
        eps = rational(contract['epsilon'])
        require(eps > 0 and t < piece.tau(e)+eps, 'approach_contract')
        require(not piece.chi or t == piece.tau(e), 'closed_approach_requires_minimum')
    elif kind in ('realize_le', 'budget'):
        require(t <= rational(contract['budget']), 'budget_contract')
    elif kind != 'membership':
        raise VerificationError('unknown witness contract')
    return json.loads(canonical(contract))


def _membership(ctx, ident, witness, contract, budgets=None):
    require(ident in ctx._pieces, 'expected_family_id_missing', expected=ident)
    require(set(witness) == {'energy', 'time', 'rho', 'pi', 'state', 'events'}, 'invalid_witness_fields')
    events = json.loads(canonical(witness['events']))
    require(events, 'empty_witness_events')
    event_keys = {'effect', 'site', 'arrival_time', 'departure_time', 'arrival_energy', 'departure_energy'}
    for ev in events:
        require(set(ev) == event_keys and isinstance(ev['effect'], str) and isinstance(ev['site'], str), 'invalid_event_fields')
        require(all(isinstance(ev[k], str) for k in event_keys-{'effect', 'site'}), 'non_string_event_rational')
        for k in event_keys-{'effect', 'site'}:
            rational(ev[k])
    def replay(node_id, count):
        n, p = ctx._data['nodes'][node_id], ctx._pieces[node_id]
        kind, q, parents = n['kind'], n['params'], n['parents']
        parent_receipt = None
        if kind == 'initial':
            require(count == 1, 'initial_event_chain_length')
            ph = ctx._physics
            expected = _event('initial', ph.origin, ph.start, ph.start, ph.initial, ph.initial)
            require(events[0] == expected, 'initial_event_mismatch')
            result = _witness(ph.start, ph.initial, -ph.initial, (), (ph.origin, ph.remaining, 0), [expected])
        elif kind in ('restrict', 'select', 'retag', 'guarded_union'):
            parent_id = (parents[q['chosen']] if kind == 'select' else
                         _guarded_parent(ctx, n, rational(events[count-1]['departure_energy']))
                         if kind == 'guarded_union' else parents[0])
            result, parent_receipt = replay(parent_id, count)
            if kind == 'retag':
                result = {**result, 'state': [q['anchor'], *result['state'][1:]]}
        else:
            require(count >= 2, 'missing_physical_action_event')
            previous, parent_receipt = replay(parents[0], count-1)
            result = _physical_step(ctx._physics, n, previous, rational(events[count-1]['departure_energy']))
            require(result['events'][-1] == events[count-1], 'event_physical_replay_mismatch', node=node_id,
                    expected=result['events'][-1], actual=events[count-1])
        e, t = rational(result['energy']), rational(result['time'])
        require(p.contains(e), 'inherited_energy_guard', node=node_id, energy=str(e), domain=p.dump()['domain'])
        require(t > p.tau(e) or t == p.tau(e) and p.chi, 'inherited_time_cut', node=node_id)
        require((rational(result['rho']), tuple(map(tuple, result['pi'])), tuple(result['state'])) == (p.rho, p.pi, p.state), 'inherited_key_mismatch', node=node_id)
        receipt = dict(node_id=node_id, kind=kind, output_energy=str(e), output_time=str(t),
                       event_count=count, events_sha256=digest(events[:count]), parent=parent_receipt)
        if parent_receipt:
            receipt['predecessor_energy'] = parent_receipt['output_energy']
            receipt['predecessor_time'] = parent_receipt['output_time']
        if kind in ('select', 'guarded_union'):
            receipt['chosen_parent'] = parent_receipt['node_id']
        if kind == 'drive':
            source = ctx._pieces[parents[0]].state[0]
            dt, consumption, path, edge_ids = ctx._physics.legs[source, q['site']]
            receipt['selected_leg'] = dict(source=source, target=q['site'],
                time=str(dt), consumption=str(consumption), path=list(path), edge_ids=list(edge_ids))
        if kind == 'stop':
            receipt['physical_regime'] = dict(effect=q['effect'], site=q['site'],
                in_segment=_plain(q['in_segment']), out_segment=_plain(q['out_segment']))
        if budgets is not None:
            receipt['requested_budget'] = str(budgets[node_id])
        return result, receipt
    result, receipt = replay(ident, len(events))
    require(canonical(result) == canonical(witness), 'witness_final_fields_or_event_chain', expected=result)
    receipt['contract'] = _contract(ctx._pieces[ident], result, contract)
    receipt['events'] = events
    receipt['witness_sha256'] = digest(result)
    receipt['bundle_sha256'] = ctx.summary['bundle_sha256']
    return receipt


@_validation_api
def check_witness(bundle, node_id, witness_dict, contract=None, *, trusted_case=None):
    """Replay every physical action and every selected inherited ancestor guard.

    A physically valid same-key foreign-family witness is rejected. Contract
    energy is the caller's requested energy, not inferred from the witness.
    """
    return _membership(_context(bundle, trusted_case), node_id, witness_dict, contract)


@_validation_api
def check_receipt(bundle, node_id, witness_dict, contract, receipt, *, trusted_case=None, require_budgets=False):
    """Independently replay an entire stored recursive receipt.

    Ordinary membership receipts must match exactly. Reconstruction receipts
    additionally annotate every node with a budget, bind the root to the
    caller's budget, and satisfy each physical child-to-parent budget transfer.
    A feasible physical witness alone does not validate arbitrary annotations.
    Set require_budgets=True when the row claims independent reconstruction;
    this prevents complete annotation deletion from becoming an ordinary
    membership receipt. No particular feasible-point algorithm is assumed.
    """
    require(type(require_budgets) is bool, 'invalid_require_budgets_flag')
    ctx = _context(bundle, trusted_case)
    expected = _membership(ctx, node_id, witness_dict, contract)
    saved = json.loads(canonical(receipt))
    stripped = json.loads(canonical(receipt))
    chain = []
    cursor = stripped
    while cursor is not None:
        require(type(cursor) is dict, 'invalid_receipt_chain')
        require(type(cursor.get('event_count')) is int and cursor['event_count'] > 0,
                'receipt_event_count_type')
        chain.append(cursor.pop('requested_budget', None))
        cursor = cursor['parent']
    require(wire_equal(stripped, expected), 'receipt_membership_fields_mismatch')
    annotated = any(u is not None for u in chain)
    require(not require_budgets or annotated, 'missing_reconstruction_budget_annotations')
    if not annotated:
        require(wire_equal(saved, expected), 'receipt_membership_fields_mismatch')
        return saved
    require(all(isinstance(u, str) for u in chain), 'partial_or_invalid_budget_annotations')
    require(contract is not None and contract.get('kind') in ('realize_le', 'budget'),
            'annotated_receipt_requires_budget_contract')
    require(rational(chain[0]) == rational(contract['budget']), 'root_requested_budget_mismatch')
    cursor = saved
    while cursor is not None:
        ident = cursor['node_id']; node = ctx._data['nodes'][ident]; piece = ctx._pieces[ident]
        u, y, t = map(rational, (cursor['requested_budget'], cursor['output_energy'], cursor['output_time']))
        require(u > piece.tau(y) or u == piece.tau(y) and piece.chi, 'receipt_budget_outside_cut_ray', node=ident)
        require(t <= u, 'receipt_output_exceeds_requested_budget', node=ident)
        parent = cursor['parent']
        if parent is not None:
            v, x = map(rational, (parent['requested_budget'], parent['output_energy']))
            kind, q = node['kind'], node['params']
            if kind == 'drive':
                require(v+rational(q['duration']) <= u, 'receipt_drive_budget_transfer', node=ident)
            elif kind == 'stop':
                effect = q['effect']; h, a, b, D = [rational(q[k]) for k in ('h', 'a', 'b', 'D')]
                if effect in ('C', 'CS'):
                    require(v+h+ctx._physics.primitive(y)-ctx._physics.primitive(x) <= u,
                            'receipt_charge_budget_transfer', node=ident)
                if effect in ('S', 'CS'):
                    require(a <= b and v+h <= b, 'receipt_service_deadline_budget', node=ident)
                    require(a+D <= u and v+h+D <= u, 'receipt_service_completion_budget', node=ident)
            elif kind in ('restrict', 'select', 'retag', 'guarded_union'):
                require(v <= u, 'receipt_inherited_budget_transfer', node=ident)
            else:
                raise VerificationError('invalid_annotated_receipt_parent_kind')
        cursor = parent
    return saved


def _fiber_point(rows):
    """Exact feasible point of finite scalar strict/non-strict inequalities."""
    lo = hi = None; ls = hs = False
    for a, c, strict in rows:  # a*x <= c, optionally strict
        if a == 0:
            require(c > 0 or c == 0 and not strict, 'empty_strict_budget_fiber')
        elif a < 0:
            v = c/a
            if lo is None or v > lo:
                lo, ls = v, strict
            elif v == lo:
                ls = ls or strict
        else:
            v = c/a
            if hi is None or v < hi:
                hi, hs = v, strict
            elif v == hi:
                hs = hs or strict
    require(lo is not None and hi is not None and (lo < hi or lo == hi and not (ls or hs)), 'empty_strict_budget_fiber')
    # Midpoint is exact and avoids every excluded endpoint, however tiny.
    x = (lo+hi)/2
    require(all(a*x < c if s else a*x <= c for a, c, s in rows), 'fiber_point_internal_error')
    return x


@_validation_api
def reconstruct(bundle, node_id, energy, budget, *, trusted_case=None):
    """Construct an exact in-family physical prefix with completion <= budget.

    Feasible fibers use rational inequalities, including all strict faces.
    Parent budgets are only existential aids: actual events always use earliest
    service/max semantics, never discretionary waiting at a requested budget.
    """
    ctx = _context(bundle, trusted_case)
    require(node_id in ctx._pieces, 'expected_family_id_missing', expected=node_id)
    energy, budget = rational(energy), rational(budget)
    budgets = {}
    def realize(ident, y, u):
        n, p = ctx._data['nodes'][ident], ctx._pieces[ident]
        require(p.contains(y), 'reconstruction_energy_outside_family')
        require(u > p.tau(y) or u == p.tau(y) and p.chi, 'budget_outside_cut_ray')
        budgets[ident] = u
        q, kind, parents = n['params'], n['kind'], n['parents']
        if kind == 'initial':
            ph = ctx._physics
            return _witness(ph.start, ph.initial, -ph.initial, (), (ph.origin, ph.remaining, 0),
                            [_event('initial', ph.origin, ph.start, ph.start, ph.initial, ph.initial)])
        if kind in ('restrict', 'select', 'retag', 'guarded_union'):
            parent = (parents[q['chosen']] if kind == 'select' else
                      _guarded_parent(ctx, n, y) if kind == 'guarded_union' else parents[0])
            result = realize(parent, y, u)
            return {**result, 'state': [q['anchor'], *result['state'][1:]]} if kind == 'retag' else result
        parent = parents[0]; source = ctx._pieces[parent]
        if kind == 'drive':
            x, v = y+rational(q['consumption']), u-rational(q['duration'])
        else:
            effect = q['effect']
            h, a, b, D = [rational(q[k]) for k in ('h', 'a', 'b', 'D')]
            if effect == 'S':
                require(u >= a+D, 'budget_below_service_release')
                x, v = y, min(b-h, u-h-D)
            else:
                il, ih, im, ic = map(rational, q['in_segment'])
                ol, oh, om, oc = map(rational, q['out_segment'])
                require(ol <= y <= oh, 'output_segment_guard')
                rows = [(-F(1), -source.lo, not source.lc), (F(1), source.hi, not source.rc),
                        (-F(1), -il, False), (F(1), ih, False), (F(1), y, True),
                        (source.m-im, u-om*y-source.b-h-oc+ic, not source.chi)]
                if effect == 'CS':
                    require(u >= a+D, 'budget_below_service_release')
                    rows += [(source.m, b-h-source.b, not source.chi),
                             (source.m, u-h-D-source.b, not source.chi)]
                x = _fiber_point(rows)
                v = u-h-ctx._physics.primitive(y)+ctx._physics.primitive(x)
                if effect == 'CS':
                    v = min(v, b-h, u-h-D)
            # Exact earliest parent is preferable when attained; for an open
            # cut, any feasible upper budget is recursively constructible.
        if source.chi:
            require(source.tau(x) <= v, 'predecessor_budget_infeasible')
            v = source.tau(x)
        previous = realize(parent, x, v)
        result = _physical_step(ctx._physics, n, previous, y)
        require(rational(result['time']) <= u, 'reconstruction_exceeds_budget')
        return result
    witness = realize(node_id, energy, budget)
    contract = dict(kind='realize_le', energy=str(energy), budget=str(budget))
    receipt = _membership(ctx, node_id, witness, contract, budgets)
    return dict(witness=witness, receipt=receipt)
