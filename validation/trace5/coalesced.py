"""Reconstructed v2 checker for recorded exact connected-cut coalescing.

This is newly reconstructed source above the published v1 family/trace
checkers, not a recovery of previously accepted independent-review source.
The physical/search grammar stays inherited from v1. Only explicit compact
occurrences and their exact guarded-union lineage extend that grammar.
No production coalescer, solver, projection, or recorder is imported.
"""
from dataclasses import replace
from fractions import Fraction as F
import json
import time

from validation.family5 import independent_oracle_v2 as oracle
from validation.family5.checker import canonical, digest, _freeze, _plain
from .checker import CheckedTrace, TraceVerificationError, _Replay, _api, _json, equal, require


TRACE_SCHEMA = 'family5-hier-trace-v2'
REPRESENTATION = 'exact-adjacent-cut-coalescing-v1'


def _connected_components(pieces):
    """Independently construct interval-graph components, in dispatch order.

    Groups follow first appearance of their complete mathematical signature.
    Inside a group, components follow their first domain in exact interval
    order. Each component preserves original input order for witness dispatch.
    Pairwise graph connectivity deliberately does not reuse the producer's
    running-union sweep. Open/open contact is not an edge; a singleton covering
    that knot connects both sides. No tolerance or energy sampling is used.
    """
    groups = {}
    for index, p in enumerate(pieces):
        key = (p.state, p.rho, p.pi, p.m, p.b, p.chi)
        groups.setdefault(key, []).append(index)

    def domain_order(index):
        p = pieces[index]
        return p.lo, not p.lc, p.hi, not p.rc, index

    for indices in groups.values():
        ordered = sorted(indices, key=domain_order)
        adjacency = {index: [] for index in ordered}
        for offset, left_index in enumerate(ordered):
            left = pieces[left_index]
            for right_index in ordered[offset + 1:]:
                right = pieces[right_index]
                connected = (left.hi > right.lo or
                             left.hi == right.lo and (left.rc or right.lc))
                if connected:
                    adjacency[left_index].append(right_index)
                    adjacency[right_index].append(left_index)
        seen = set()
        for seed in ordered:
            if seed in seen:
                continue
            pending, members = [seed], []
            while pending:
                current = pending.pop()
                if current in seen:
                    continue
                seen.add(current)
                members.append(current)
                pending.extend(adjacency[current])
            members.sort()
            lo = min(pieces[index].lo for index in members)
            hi = max(pieces[index].hi for index in members)
            lc = any(pieces[index].lo == lo and pieces[index].lc for index in members)
            rc = any(pieces[index].hi == hi and pieces[index].rc for index in members)
            yield members, replace(pieces[members[0]], lo=lo, hi=hi, lc=lc, rc=rc)


class CoalescedReplay(_Replay):
    """Explicit v2 grammar, composable with an independently trusted adapter.

    Calling run() directly retains the published tiny synthetic Region
    configuration. Another adapter must provide its own trusted physical
    context and Region validation; the v2 header never supplies either.
    """

    def __init__(self, trace, bundle, trusted_case):
        _json(trace)
        require(type(trace) is dict, 'coalesced_trace_not_object')
        equal(sorted(trace), ['events', 'representation', 'schema'], 'coalesced_trace_fields')
        equal(trace['schema'], TRACE_SCHEMA, 'coalesced_trace_schema')
        equal(trace['representation'], REPRESENTATION, 'coalesced_trace_representation')
        detached = json.loads(canonical(trace))
        super().__init__(dict(schema='family5-hier-trace-v1', events=detached['events']),
                         bundle, trusted_case)
        self.trace = detached
        self.coalescing_id = 0

    def compact(self, parents):
        """Consume one exact occurrence, including empty and singleton calls."""
        row, _ = self.event('coalesce', ('coalescing_id', 'input_families',
                                        'output_families', 'input_guards', 'batch_range'))
        equal(row['coalescing_id'], self.coalescing_id, 'coalescing_id_sequence')
        self.coalescing_id += 1
        equal(row['input_families'], parents, 'coalescing_input_families')
        equal(row['input_guards'], [self.nodes[x]['output']['domain'] for x in parents],
              'coalescing_input_guards')
        equal(row['batch_range'], [self.batch_cursor, self.batch_cursor], 'coalescing_batch_span')
        outputs = []
        for indices, piece in _connected_components([self.pieces[x] for x in parents]):
            cluster = [parents[index] for index in indices]
            if len(cluster) == 1:
                outputs.append(cluster[0])
                continue
            guards = [self.nodes[x]['output']['domain'] for x in cluster]
            outputs.append(self.node('guarded_union', cluster, piece, dict(guards=guards)))
            self.counts['coalescing_merged_clusters'] += 1
        equal(row['output_families'], outputs, 'coalescing_output_families')
        self.counts['coalescing_input_families'] += len(parents)
        self.counts['coalescing_output_families'] += len(outputs)
        return outputs

    def _physical(self, operation, parents, params):
        """Reconstruct the published v1 operation between the two compacts.

        This mirrors the physical branch of _Replay.invoke, using only the
        inherited independent node/batch/selection checks. Event bookkeeping
        is separate because the producer emits invoke after the entire call.
        """
        if operation == 'initial':
            initial = oracle.Piece(self.ph.initial, self.ph.initial, True, True,
                F(0), self.ph.start, True, -self.ph.initial, (),
                (self.ph.origin, self.ph.remaining, 0))
            return [self.node('initial', [], initial, dict(case=self.case))]
        if operation == 'finish':
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
            return outputs
        if operation == 'advance':
            require(parents, 'empty_advance_input')
            state = self.pieces[parents[0]].state
            site, effect = params['site'], params['effect']
            anchor = self.ph.anchors[site]
            outputs = []
            if (state[0] != self.ph.destination and anchor != self.ph.destination
                    and (state[0], anchor) in self.ph.legs):
                require(state[2] < self.ph.bound, 'advance_exceeds_H_ref')
                require(effect in self.ph.sites[site], 'unavailable_advance_effect')
                require(effect == 'C' or state[1] == 1 and self.ph.schedule is not None,
                        'advance_service_state')
                incoming = self.drive(parents, anchor, self.ph.floor)
                raw = self.stop(incoming, site, effect)
                for ident in raw:
                    p = self.pieces[ident]
                    outputs.append(ident if p.state[0] == anchor else
                        self.node('retag', [ident], replace(p, state=(anchor, *p.state[1:])),
                                  dict(anchor=anchor)))
            return outputs
        if operation == 'reduce':
            return self.selection(parents, 'reduction')
        raise TraceVerificationError('unknown_invocation')

    def invoke(self, operation, parents, params):
        begin = self.batch_cursor
        source = parents if operation == 'initial' else self.compact(parents)
        outputs = self._physical(operation, source, params)
        if operation != 'initial':
            outputs = self.compact(outputs)
        invocation, _ = self.event('invoke', ('invocation_id', 'operation', 'input_families',
                                             'output_families', 'params', 'batch_range'))
        current_id = self.invocation_id
        self.invocation_id += 1
        equal(invocation['invocation_id'], current_id, 'invocation_id_sequence')
        equal(invocation['operation'], operation, 'invocation_operation')
        equal(invocation['input_families'], parents, 'invocation_input_families')
        equal(invocation['params'], params, 'invocation_parameters')
        equal(invocation['output_families'], outputs, 'invocation_output_families')
        equal(invocation['batch_range'], [begin, self.batch_cursor], 'invocation_batch_span')
        self.counts[f'invoke_{operation}'] += 1
        return outputs, current_id


@_api
def verify_coalesced_trace(trace, bundle, trusted_case):
    """Check reconstructed v2 tiny-HIER evidence and return unchanged CheckedTrace.

    Physical trust, action coverage, queue order, bounds, incumbents, exact
    node-query freezes, terminal results, and complete node/batch accounting
    retain their published v1 obligations. This adds no numerical suffix run,
    real-population acceptance, or literal G8 claim.
    """
    started = time.perf_counter()
    replay = CoalescedReplay(trace, bundle, trusted_case)
    result = replay.run()
    queries = replay.node_queries
    summary = dict(schema='family5-hier-trace-check-v2', verified=True,
        representation=REPRESENTATION, reconstruction_status='newly_reconstructed_source',
        trace_sha256=digest(replay.trace), bundle_sha256=replay.ctx.summary['bundle_sha256'],
        case_sha256=replay.ctx.summary['case_sha256'], region_tree_sha256=replay.region_digest,
        events=replay.cursor, invocations=replay.invocation_id, groups=replay.group_id,
        coalescings=replay.coalescing_id, nodes=len(replay.nodes), batches=replay.batch_cursor,
        counts=dict(sorted(replay.counts.items())), exact_node_queries=len(queries),
        empty_action_queries=len(replay.empty_queries),
        unreachable_node_queries=sum(row['classification'] == 'unreachable' for row in queries),
        query_freeze_sha256=digest(queries), canonical=result,
        elapsed_s=time.perf_counter()-started,
        scope='complete_synthetic_tiny_hier_coalesced_invocation_trace',
        region_configuration='deterministic_balanced_binary_leaf_size_1',
        numerical_suffix_optimization='not_run', literal_G8_closed=False)
    return CheckedTrace(_freeze(replay.trace), replay.ctx, _freeze(summary),
                        _freeze(queries), _freeze(replay.empty_queries))
