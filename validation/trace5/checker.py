"""Replay a complete tiny-HIER invocation grammar without production imports.

The independent family checker establishes each physical cut and operator image.
This module establishes the additional search-call, queue, coverage and incumbent
obligations. It neither solves numerical suffix problems nor closes literal G8.
"""
from collections import defaultdict
from dataclasses import dataclass, replace
from fractions import Fraction as F
from functools import wraps
from itertools import combinations, product
import heapq
import json
import time

from validation.family5 import CheckedBundle, VerificationError, check_witness, verify_bundle
from validation.family5.checker import canonical, digest, _freeze, _plain, wire_equal
from validation.family5 import independent_oracle_v2 as oracle


class TraceVerificationError(VerificationError):
    """A trace does not describe the complete supported deterministic search."""


def require(condition, reason, **details):
    if not condition:
        raise TraceVerificationError(json.dumps(dict(reason=reason, **details), sort_keys=True, default=str))


def equal(actual, expected, reason):
    require(wire_equal(actual, expected), reason, actual=actual, expected=expected)


def _api(function):
    @wraps(function)
    def checked(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except TraceVerificationError:
            raise
        except VerificationError as exc:
            raise TraceVerificationError(f'family_validation: {exc}') from exc
        except (KeyError, TypeError, ValueError, IndexError, AttributeError, RecursionError) as exc:
            raise TraceVerificationError(f'malformed_trace: {type(exc).__name__}: {exc}') from exc
    return checked


def _json(value):
    """Reject type aliases before detaching rather than normalizing them away."""
    if type(value) is dict:
        require(all(type(k) is str for k in value), 'non_string_json_key')
        for child in value.values():
            _json(child)
    elif type(value) is list:
        for child in value:
            _json(child)
    else:
        require(type(value) in (str, int, bool, type(None)), 'non_exact_json_type', type=type(value).__name__)


def _r(value):
    require(type(value) is str, 'non_string_trace_rational')
    result = F(value)
    equal(value, str(result), 'noncanonical_trace_rational')
    return result


def _dispatch_cells(pieces):
    """Ordered dispatch cells with crossings restricted to simultaneous support.

    The frozen semantic oracle may use a finer global arrangement for proving
    coverage. Invocation identity additionally depends on this documented
    dispatch partition: a crossing between pieces on disjoint energy domains
    must not introduce a new output-family occurrence.
    """
    if not pieces:
        return []
    knots = {endpoint for p in pieces for endpoint in (p.lo, p.hi)}
    for left, right in combinations(pieces, 2):
        slope = left.m-right.m
        if slope:
            crossing = (right.b-left.b)/slope
            if max(left.lo, right.lo) <= crossing <= min(left.hi, right.hi):
                knots.add(crossing)
    return list(oracle.cells(knots))


@dataclass(frozen=True)
class CheckedTrace:
    """Detached immutable checked run and exact original node-query population."""
    _trace: object
    bundle: CheckedBundle
    summary: object
    node_queries: tuple
    empty_action_queries: tuple

    def snapshot(self):
        return _plain(self._trace)

    def query_snapshot(self):
        return _plain(self.node_queries)

    def export_queries(self):
        return self.query_snapshot()

    @property
    def queries(self):
        return self.node_queries

    @property
    def exact_node_query_freeze(self):
        return self.node_queries


class _Replay:
    def __init__(self, trace, bundle, trusted_case):
        _json(trace)
        self.trace = json.loads(canonical(trace))
        equal(sorted(self.trace), ['events', 'schema'], 'trace_fields')
        equal(self.trace['schema'], 'family5-hier-trace-v1', 'trace_schema')
        require(type(self.trace['events']) is list, 'events_not_list')
        for seq, event in enumerate(self.trace['events']):
            require(type(event) is dict and set(event) == {'seq', 'kind', 'payload'}, 'event_fields')
            equal(event['seq'], seq, 'event_sequence')
            require(type(event['kind']) is str and type(event['payload']) is dict, 'event_types')
        if isinstance(bundle, CheckedBundle):
            equal(json.loads(canonical(trusted_case)), _plain(bundle._physics.case), 'checked_bundle_case')
            self.ctx = bundle
        else:
            _json(bundle)
            self.ctx = verify_bundle(bundle, trusted_case)
        self.data = self.ctx.snapshot()
        self.nodes = self.data['nodes']
        self.pieces = self.ctx._pieces
        self.ph = self.ctx._physics
        self.case = _plain(self.ph.case)
        self.penalty = F(self.case['lambda_stop_s'])
        self.cursor = self.batch_cursor = self.invocation_id = self.group_id = 0
        self.accounted = set()
        self.regions = {}
        self.node_queries, self.empty_queries = [], []
        self.incumbent = None
        self.terminals = []
        self.counts = defaultdict(int)
        self.ancestries = {}

    def event(self, kind, fields):
        require(self.cursor < len(self.trace['events']), 'missing_event', expected=kind, seq=self.cursor)
        event = self.trace['events'][self.cursor]
        equal(event['kind'], kind, 'unexpected_event_kind')
        require(set(event['payload']) == set(fields), 'event_payload_fields', kind=kind,
                actual=sorted(event['payload']), expected=sorted(fields))
        self.cursor += 1
        self.counts[kind] += 1
        return event['payload'], event['seq']

    def exact_event(self, kind, payload):
        actual, seq = self.event(kind, payload)
        equal(actual, payload, 'event_payload_mismatch')
        return seq

    def region(self, data):
        require(type(data) is dict and set(data) == {'id', 'members', 'children'}, 'region_fields')
        ident, members, children = (data[k] for k in ('id', 'members', 'children'))
        require(type(ident) is int and ident >= 0 and ident not in self.regions, 'region_id')
        require(type(members) is list and all(type(x) is str and x in self.ph.sites for x in members), 'region_members')
        equal(members, sorted(set(members)), 'region_member_order_or_duplicates')
        require(type(children) is list, 'region_children')
        self.regions[ident] = data
        for child in children:
            self.region(child)
        if children:
            flattened = [member for child in children for member in child['members']]
            equal(flattened, members, 'region_children_not_ordered_exact_partition')
            require(all(child['members'] for child in children), 'empty_region_child')
        return data

    def trusted_regions(self):
        """The preregistered pilot uses balanced binary Regions, leaf_size=1.

        This configuration is fixed independently of the trace. A future real
        Region adapter must receive separately trusted configuration evidence.
        """
        def build(members, ident):
            children = []
            if len(members) > 1:
                mid = len(members)//2
                children = [build(members[:mid], 2*ident+1), build(members[mid:], 2*ident+2)]
            return dict(id=ident, members=members, children=children)
        return build(sorted(self.ph.sites), 0)

    def node(self, kind, parents, piece, params):
        record = dict(kind=kind, parents=parents, output=_plain(piece.dump()), params=params)
        ident = digest(record)
        require(ident in self.nodes, 'missing_exact_operator_node', kind=kind, record=record)
        equal(self.nodes[ident], record, 'operator_node_mismatch')
        self.accounted.add(ident)
        return ident

    def batch(self, kind, parents, params, expected=None):
        require(self.batch_cursor < len(self.data['batches']), 'missing_operator_batch', kind=kind)
        batch = self.data['batches'][self.batch_cursor]
        self.batch_cursor += 1
        equal(batch['kind'], kind, 'invocation_batch_kind')
        equal(batch['parents'], parents, 'invocation_batch_sources')
        equal(batch['params'], params, 'invocation_batch_params')
        outputs = batch['outputs']
        require(type(outputs) is list and all(type(x) is str for x in outputs), 'batch_output_types')
        if expected is not None:
            equal(outputs, expected, 'invocation_batch_exact_image')
        self.accounted.update(outputs)
        return outputs

    def drive(self, parents, target, floor):
        leg = self.ph.legs[self.pieces[parents[0]].state[0], target]
        params = dict(site=target, duration=str(leg[0]), consumption=str(leg[1]), floor=str(floor))
        outputs = []
        for parent in parents:
            for p in oracle.transform([self.pieces[parent]], 'D', params):
                outputs.append(self.node('drive', [parent], p, params))
        return self.batch('drive', parents, params, outputs)

    def selection(self, parents, mode):
        ps, outputs = [self.pieces[x] for x in parents], []
        for lo, hi, e in _dispatch_cells(ps):
            eligible = [i for i, p in enumerate(ps) if p.contains(e)]
            if not eligible:
                continue
            if mode == 'union':
                value = min(ps[i].tau(e) for i in eligible)
                tied = [i for i in eligible if ps[i].tau(e) == value]
                chosen = [next((i for i in tied if ps[i].chi), tied[0])]
            else:
                retained = []
                for i in eligible:
                    if any(oracle.dominates(ps[j], ps[i], e) for j in retained):
                        continue
                    retained = [j for j in retained if not oracle.dominates(ps[i], ps[j], e)]
                    retained.append(i)
                chosen = [i for i in eligible if i in retained]
            for i in chosen:
                p = replace(ps[i], lo=lo, hi=hi, lc=lo == hi, rc=lo == hi)
                params = dict(domain=[str(lo), str(hi), lo == hi, lo == hi], chosen=i, mode=mode)
                outputs.append(self.node('select', parents, p, params))
        return self.batch(mode, parents, {}, outputs)

    def stop(self, incoming, site, effect):
        schedule = self.ph.schedule if effect in ('S', 'CS') else (F(0), F(0), F(0))
        a, b, duration = schedule
        curve = self.ph.curve if effect in ('C', 'CS') else ()
        params = dict(effect=effect, site=site, h=str(self.ph.overhead), a=str(a), b=str(b),
                      D=str(duration), curve=_plain(curve))
        outputs = self.batch('stop', incoming, params)
        require(len(outputs) == len(set(outputs)), 'duplicate_raw_stop_output')
        pairs = [(None, None)] if effect == 'S' else list(product(curve, repeat=2))
        ordering, previous = [], {}
        for ident in outputs:
            n, p = self.nodes[ident], self.pieces[ident]
            require(n['kind'] == 'stop' and len(n['parents']) == 1 and n['parents'][0] in incoming,
                    'stop_output_source')
            q = n['params']
            require(set(q) == set(params) | {'in_segment', 'out_segment'}, 'stop_output_params')
            equal({k: q[k] for k in params}, params, 'stop_output_context')
            pair = (None, None) if effect == 'S' else tuple(tuple(F(x) for x in q[k]) for k in ('in_segment', 'out_segment'))
            require(pair in pairs, 'stop_output_regime')
            parent_index, regime_index = incoming.index(n['parents'][0]), pairs.index(pair)
            key = parent_index, regime_index
            require(p.lc == p.rc == (p.lo == p.hi), 'raw_stop_cell_shape')
            if key in previous:
                old = previous[key]
                require(old.hi <= p.lo and not (old.hi == p.lo and old.rc and p.lc), 'overlapping_raw_stop_cells')
            previous[key] = p
            ordering.append((parent_index, regime_index, p.lo, p.hi))
        require(ordering == sorted(ordering), 'raw_stop_cell_order')
        if effect in ('S', 'CS') and a > b:
            equal(outputs, [], 'inverted_schedule_nonempty')
            return []
        return self.selection(outputs, 'union')

    def invoke(self, operation, parents, params):
        invocation, _ = self.event('invoke', ('invocation_id', 'operation', 'input_families',
                                             'output_families', 'params', 'batch_range'))
        current_id = self.invocation_id
        self.invocation_id += 1
        equal(invocation['invocation_id'], current_id, 'invocation_id_sequence')
        equal(invocation['operation'], operation, 'invocation_operation')
        equal(invocation['input_families'], parents, 'invocation_input_families')
        equal(invocation['params'], params, 'invocation_parameters')
        begin = self.batch_cursor
        if operation == 'initial':
            initial = oracle.Piece(self.ph.initial, self.ph.initial, True, True, F(0), self.ph.start,
                True, -self.ph.initial, (), (self.ph.origin, self.ph.remaining, 0))
            outputs = [self.node('initial', [], initial, dict(case=self.case))]
        elif operation == 'finish':
            require(parents, 'empty_finish_input')
            state = self.pieces[parents[0]].state
            outputs = []
            if state[1] == 0:
                if state[0] == self.ph.destination:
                    for parent in parents:
                        p = self.pieces[parent]
                        lo = max(self.ph.reserve, p.lo)
                        if lo > p.hi or lo == p.hi and not p.contains(lo):
                            continue
                        q = replace(p, lo=lo, lc=p.contains(lo))
                        guard = _plain(q.dump())['domain']
                        outputs.append(self.node('restrict', [parent], q,
                                                  dict(domain=guard, reason='terminal_reserve')))
                elif (state[0], self.ph.destination) in self.ph.legs:
                    outputs = self.drive(parents, self.ph.destination, self.ph.reserve)
        elif operation == 'advance':
            require(parents, 'empty_advance_input')
            state = self.pieces[parents[0]].state
            site, effect = params['site'], params['effect']
            anchor = self.ph.anchors[site]
            outputs = []
            if state[0] != self.ph.destination and anchor != self.ph.destination and (state[0], anchor) in self.ph.legs:
                require(state[2] < self.ph.bound, 'advance_exceeds_H_ref')
                require(effect in self.ph.sites[site], 'unavailable_advance_effect')
                require(effect == 'C' or state[1] == 1 and self.ph.schedule is not None, 'advance_service_state')
                incoming = self.drive(parents, anchor, self.ph.floor)
                raw = self.stop(incoming, site, effect)
                for ident in raw:
                    p = self.pieces[ident]
                    outputs.append(ident if p.state[0] == anchor else
                        self.node('retag', [ident], replace(p, state=(anchor, *p.state[1:])), dict(anchor=anchor)))
        elif operation == 'reduce':
            outputs = self.selection(parents, 'reduction')
        else:
            raise TraceVerificationError('unknown_invocation')
        equal(invocation['output_families'], outputs, 'invocation_output_families')
        equal(invocation['batch_range'], [begin, self.batch_cursor], 'invocation_batch_span')
        self.counts[f'invoke_{operation}'] += 1
        return outputs, current_id

    def candidate(self, families, group_id, source):
        for ident in families:
            p = self.pieces[ident]
            if p.m == 0:
                energy = (p.lo + p.hi) / 2
            else:
                energy, included = (p.lo, p.lc) if p.m > 0 else (p.hi, p.rc)
                if not included:
                    delta = min((p.hi-p.lo)/2, F(1)/(2*abs(p.m)))
                    energy += delta if p.m > 0 else -delta
            row, _ = self.event('candidate', ('group_id', 'source', 'family_id', 'energy', 'witness', 'key', 'improved'))
            equal(row['group_id'], group_id, 'candidate_group')
            equal(row['source'], source, 'candidate_source')
            equal(row['family_id'], ident, 'candidate_family_order')
            equal(row['energy'], str(energy), 'candidate_approach_energy')
            check_witness(self.ctx, ident, row['witness'], dict(kind='approach', energy=str(energy), epsilon='1'))
            witness = row['witness']
            require(p.state[0] == self.ph.destination and p.state[1] == 0 and energy >= self.ph.reserve,
                    'candidate_not_terminal')
            key = (_r(witness['time'])-self.ph.start+self.penalty*p.state[2],
                   energy+p.rho, p.state[2], p.pi)
            equal(row['key'], _plain(key), 'candidate_key')
            improved = self.incumbent is None or key < self.incumbent
            equal(row['improved'], improved, 'candidate_improvement')
            if improved:
                self.incumbent = key
                self.counts['incumbent_updates'] += 1

    def actions(self, region, effect, remaining):
        return [] if effect in ('S', 'CS') and not remaining else [
            [site, effect] for site in region['members']
            if self.ph.anchors[site] != self.ph.destination and effect in self.ph.sites[site]]

    def bound(self, families, actions, effect):
        state = self.pieces[families[0]].state
        reachable = [(self.ph.legs.get((state[0], self.ph.anchors[site])),
                      self.ph.legs.get((self.ph.anchors[site], self.ph.destination))) for site, _ in actions]
        reachable = [(a, b) for a, b in reachable if a is not None and b is not None]
        if not reachable:
            return None
        lower = min(p.tau(p.lo if p.m > 0 else p.hi if p.m < 0 else (p.lo+p.hi)/2)
                    for p in (self.pieces[x] for x in families))
        value = lower + min(a[0] for a, _ in reachable) + self.ph.overhead
        if effect in ('S', 'CS'):
            a, _, duration = self.ph.schedule
            value = max(a, value)+duration
        return value + min(b[0] for _, b in reachable)-self.ph.start+self.penalty*(state[2]+1)

    def ancestry(self, families):
        key = tuple(families)
        if key not in self.ancestries:
            reachable = set()
            def visit(ident):
                if ident in reachable:
                    return
                reachable.add(ident)
                for parent in self.nodes[ident]['parents']:
                    visit(parent)
            for ident in families:
                visit(ident)
            evidence = dict(schema='family5-transitive-ancestry-v1', roots=families,
                            nodes={x: self.nodes[x] for x in sorted(reachable)})
            self.ancestries[key] = dict(sha256=digest(evidence), node_ids=sorted(reachable),
                                       nodes=evidence['nodes'])
        return self.ancestries[key]

    def leg(self, source, target):
        value = self.ph.legs.get((source, target))
        return None if value is None else dict(source=source, target=target, time=str(value[0]),
                    consumption=str(value[1]), path=list(value[2]), edge_ids=list(value[3]))

    def freeze_query(self, seq, group_id, families, region, effect, actions, bound, classification, serial):
        p = self.pieces[families[0]]
        ancestry = self.ancestry(families)
        row = dict(schema='family5-exact-node-query-v1', query_seq=seq, group_id=group_id,
            family_ids=list(families), cuts=[dict(family_id=x, cut=self.nodes[x]['output']) for x in families],
            ancestry_bundle_sha256=ancestry['sha256'], ancestry_node_ids=ancestry['node_ids'],
            ancestry_nodes=ancestry['nodes'], source_bundle_sha256=self.ctx.summary['bundle_sha256'],
            case_sha256=self.ctx.summary['case_sha256'], trusted_case=self.case,
            region_id=region['id'], region_members=region['members'], region_tree_sha256=self.region_digest,
            actions=actions, effect=effect, state=_plain(p.state), rho=str(p.rho), pi=_plain(p.pi),
            H_remaining=self.ph.bound-p.state[2], bound=None if bound is None else str(bound),
            classification=classification, queue_serial=serial, disposition=classification,
            leg_context=[dict(site=site, incoming=self.leg(p.state[0], self.ph.anchors[site]),
                             onward=self.leg(self.ph.anchors[site], self.ph.destination)) for site, _ in actions])
        if classification == 'unreachable':
            row['physical_exclusion'] = 'every_action_lacks_selected_incoming_or_onward_leg'
        self.node_queries.append(row)
        return row

    def expand(self, group_id, families, root):
        state = self.pieces[families[0]].state
        if state[0] == self.ph.destination:
            self.exact_event('skip_terminal', dict(group_id=group_id))
            return []
        self.exact_event('expansion_start', dict(group_id=group_id))
        expected = {tuple(a) for effect in ('C', 'S', 'CS') for a in self.actions(root, effect, state[1])}
        covered, queue, output = set(), [], []
        serial = 0
        def cover(actions):
            values = set(map(tuple, actions))
            require(len(values) == len(actions) and not covered.intersection(values), 'duplicate_action_coverage')
            covered.update(values)
        def enqueue(region, effect):
            nonlocal serial
            actions = self.actions(region, effect, state[1])
            value = self.bound(families, actions, effect) if actions else None
            classification = 'empty_actions' if not actions else 'unreachable' if value is None else 'queued'
            qserial = None
            if classification == 'queued':
                serial += 1
                qserial = serial
            payload = dict(group_id=group_id, region_id=region['id'], effect=effect, actions=actions,
                bound=None if value is None else str(value), classification=classification, queue_serial=qserial)
            seq = self.exact_event('query', payload)
            if not actions:
                self.empty_queries.append(dict(query_seq=seq, **payload))
                return
            row = self.freeze_query(seq, group_id, families, region, effect, actions, value, classification, qserial)
            if value is None:
                cover(actions)
            else:
                heapq.heappush(queue, (value, effect, region['id'], qserial, seq, row))
        for effect in ('C', 'S', 'CS'):
            enqueue(root, effect)
        while queue:
            value, effect, region_id, _, seq, row = heapq.heappop(queue)
            region = self.regions[region_id]
            decision = ('prune' if self.incumbent is not None and value > self.incumbent[0]
                        else 'split' if region['children'] else 'leaf')
            pop_seq = self.exact_event('pop', dict(group_id=group_id, query_seq=seq, decision=decision,
                                                incumbent_key=_plain(self.incumbent)))
            row.update(disposition=decision, pop_seq=pop_seq, incumbent_key=_plain(self.incumbent))
            self.counts[f'disposition_{decision}'] += 1
            if self.incumbent is not None and value == self.incumbent[0] and decision != 'prune':
                self.counts['equality_nodes_retained'] += 1
            if decision == 'prune':
                cover(row['actions'])
            elif decision == 'split':
                for child in region['children']:
                    enqueue(child, effect)
            else:
                for site, action_effect in row['actions']:
                    cover([[site, action_effect]])
                    advanced, advance_id = self.invoke('advance', families,
                        dict(group_id=group_id, site=site, effect=action_effect))
                    if advanced:
                        output.extend(advanced)
                        finished, _ = self.invoke('finish', advanced,
                            dict(group_id=group_id, source='leaf', advance_id=advance_id))
                        self.candidate(finished, group_id, 'leaf')
        require(covered == expected, 'incomplete_action_coverage')
        self.exact_event('expansion_end', dict(group_id=group_id, covered_actions=_plain(sorted(covered))))
        return output

    def groups(self, families):
        groups = {}
        for ident in families:
            groups.setdefault(self.pieces[ident].family(), []).append(ident)
        return list(groups.values())

    def canonical_result(self):
        ps = [replace(self.pieces[x], b=self.pieces[x].b-self.ph.start) for x in self.terminals]
        expected = oracle.terminal_expected(ps, penalty=self.penalty, reserve=self.ph.reserve)
        status = expected['status']
        if status == 'infeasible':
            result = dict(status='infeasible_within_H_ref')
        elif status == 'infimum_unattained':
            result = (dict(status='primary_unattained', primary_infimum=expected['J'])
                      if expected['unattained_component'] == 'J' else
                      dict(status='secondary_unattained', J=expected['J'], secondary_infimum=expected['Q']))
        else:
            key = [expected['J'], expected['Q'], expected['H'], expected['pi']]
            result = dict(status=status, J=expected['J'], Q_total=expected['Q'], H=expected['H'],
                          site_action_tuple=expected['pi'], lex_key=key, witness_replayed=True)
        return dict(scope='bounded_H_ref_diagnostic', H_ref=self.ph.bound, result=result)

    def run(self):
        start, _ = self.event('run_start', ('case_sha256', 'dominance', 'H_ref', 'regions'))
        equal(start['case_sha256'], self.ctx.summary['case_sha256'], 'trace_trusted_case')
        equal(start['H_ref'], self.ph.bound, 'trace_stop_bound')
        require(type(start['dominance']) is bool, 'dominance_type')
        self.dominance = start['dominance']
        equal(start['regions'], self.trusted_regions(), 'trusted_region_configuration')
        root = self.region(start['regions'])
        equal(root['members'], sorted(self.ph.sites), 'root_region_site_coverage')
        self.region_digest = digest(root)
        initial, _ = self.invoke('initial', [], {})
        layer = [initial]
        for depth in range(self.ph.bound+1):
            groups = [dict(group_id=self.group_id+i, families=ids) for i, ids in enumerate(layer)]
            self.group_id += len(groups)
            self.exact_event('layer_start', dict(depth=depth, groups=groups))
            for group in groups:
                require(all(self.pieces[x].state[2] == depth for x in group['families']), 'layer_stop_count')
                finished, _ = self.invoke('finish', group['families'],
                    dict(group_id=group['group_id'], source='layer', advance_id=None))
                self.terminals.extend(finished)
                self.candidate(finished, group['group_id'], 'layer')
            if depth == self.ph.bound:
                self.exact_event('layer_end', dict(depth=depth, reason='stop_bound', next_groups=[]))
                break
            following = []
            for group in groups:
                following.extend(self.expand(group['group_id'], group['families'], root))
            if self.dominance:
                by_state = {}
                for ident in following:
                    by_state.setdefault(self.pieces[ident].state, []).append(ident)
                reduced = []
                for state, ids in by_state.items():
                    output, _ = self.invoke('reduce', ids, dict(depth=depth, state=_plain(state)))
                    reduced.extend(output)
                following = reduced
            layer = self.groups(following)
            reason = 'continue' if layer else 'empty'
            self.exact_event('layer_end', dict(depth=depth, reason=reason, next_groups=layer))
            if not layer:
                break
        result, _ = self.event('run_end', ('canonical', 'terminal_families', 'terminal_witness', 'terminal_family_id'))
        equal(result['terminal_families'], self.terminals, 'terminal_family_sequence')
        equal(self.data['roots'], self.terminals, 'bundle_terminal_roots')
        expected = self.canonical_result()
        actual = result['canonical']
        if expected['result']['status'] == 'attained_optimum':
            require(type(actual) is dict and type(actual.get('result')) is dict, 'canonical_shape')
            target = expected['result']
            J, Q = F(target['J']), F(target['Q_total'])
            winners = []
            for ident in self.terminals:
                p = self.pieces[ident]
                e = Q-p.rho
                if (p.contains(e) and p.chi and e >= self.ph.reserve and p.state[2] == target['H']
                        and _plain(p.pi) == target['site_action_tuple']
                        and p.tau(e)-self.ph.start+self.penalty*p.state[2] == J):
                    winners.append((ident, e))
            require(winners, 'missing_attained_terminal_family')
            ident, energy = winners[0]
            equal(result['terminal_family_id'], ident, 'terminal_winner_family')
            witness = result['terminal_witness']
            check_witness(self.ctx, ident, witness, dict(kind='minimum', energy=str(energy)))
            charges = [str(F(ev['departure_energy'])-F(ev['arrival_energy'])) for ev in witness['events']
                       if ev['effect'] in ('C', 'CS')]
            expected['result']['charges'] = charges
        else:
            equal(result['terminal_family_id'], None, 'unattained_terminal_family')
            equal(result['terminal_witness'], None, 'unattained_terminal_witness')
        equal(actual, expected, 'canonical_terminal_status_or_key')
        equal(self.cursor, len(self.trace['events']), 'trailing_events')
        equal(self.batch_cursor, len(self.data['batches']), 'unconsumed_operator_batches')
        equal(sorted(self.accounted), sorted(self.nodes), 'unaccounted_family_nodes')
        return expected


@_api
def verify_trace(trace, bundle, trusted_case):
    """Verify all events and exact query contexts; return immutable evidence.

Only the small synthetic graph adapter and preregistered deterministic balanced
Regions with leaf_size=1 are supported. The trusted physical case comes from the
caller; the Region tree is rebuilt from its Site IDs. No external incumbent or
coalescing is accepted. Future real Regions need independently supplied trusted
configuration, never a Region configuration inferred from the trace itself.
    """
    started = time.perf_counter()
    replay = _Replay(trace, bundle, trusted_case)
    result = replay.run()
    queries = replay.node_queries
    summary = dict(schema='family5-hier-trace-check-v1', verified=True,
        trace_sha256=digest(replay.trace), bundle_sha256=replay.ctx.summary['bundle_sha256'],
        case_sha256=replay.ctx.summary['case_sha256'], region_tree_sha256=replay.region_digest,
        events=replay.cursor, invocations=replay.invocation_id, groups=replay.group_id,
        nodes=len(replay.nodes), batches=replay.batch_cursor, counts=dict(sorted(replay.counts.items())),
        exact_node_queries=len(queries), empty_action_queries=len(replay.empty_queries),
        unreachable_node_queries=sum(row['classification'] == 'unreachable' for row in queries),
        query_freeze_sha256=digest(queries), canonical=result,
        elapsed_s=time.perf_counter()-started, scope='complete_synthetic_tiny_hier_invocation_trace',
        region_configuration='deterministic_balanced_binary_leaf_size_1',
        numerical_suffix_optimization='not_run', literal_G8_closed=False)
    return CheckedTrace(_freeze(replay.trace), replay.ctx, _freeze(summary),
                        _freeze(queries), _freeze(replay.empty_queries))
