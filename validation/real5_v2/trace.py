"""Reconstructed baseline real HIER grammar over trusted original Regions.

The invocation and exact family mathematics remain the published PR7 grammar.
Real pair totals supply incoming time; onward lower bound is exactly zero. A
selected Site need not have a direct terminal leg to remain a legal action.
"""
from dataclasses import replace
from fractions import Fraction as F
import time

from validation.trace5.checker import (
    CheckedTrace, TraceVerificationError, _Replay, _api, require, equal,
    _plain, _freeze, canonical, digest, oracle, check_witness,
)
from .input import TrustedRealCase
from .family import _checked


class RealPhysicsReplayMixin:
    """Real physical inputs and original-Region semantics for trace grammars."""
    def __init__(self, trace, bundle, trusted_case):
        require(isinstance(trusted_case, TrustedRealCase), "trusted_real_case_required")
        self.trusted_real_case = trusted_case
        checked = _checked(bundle, trusted_case)
        super().__init__(trace, checked, trusted_case.case_snapshot())

    def trusted_regions(self):
        return _plain(self.trusted_real_case.regions)

    def region(self, data):
        require(type(data) is dict and set(data) == {"id", "members", "children"}, "region_fields")
        ident, members, children = (data[k] for k in ("id", "members", "children"))
        require(type(ident) is int and ident >= 0 and ident not in self.regions, "region_id")
        require(type(members) is list and all(type(s) is str and s in self.ph.sites for s in members), "region_members")
        require(len(members) == len(set(members)), "duplicate_region_member")
        require(type(children) is list, "region_children")
        self.regions[ident] = data
        for child in children:
            self.region(child)
        if children:
            flattened = [member for child in children for member in child["members"]]
            require(len(flattened) == len(set(flattened)) and set(flattened) == set(members),
                    "region_children_not_exact_partition")
        return data

    def bound(self, families, actions, effect):
        state = self.pieces[families[0]].state
        incoming = [self.ph.legs.get((state[0], self.ph.anchors[site])) for site, _ in actions]
        incoming = [leg for leg in incoming if leg is not None]
        if not incoming:
            return None
        lower = min(piece.tau(piece.lo if piece.m > 0 else piece.hi if piece.m < 0 else
                              (piece.lo+piece.hi)/2) for piece in (self.pieces[x] for x in families))
        value = lower + min(leg[0] for leg in incoming) + self.ph.overhead
        if effect in ("S", "CS"):
            a, _, duration = self.ph.schedule
            value = max(a, value)+duration
        return value-self.ph.start+self.penalty*(state[2]+1)

    def freeze_query(self, *args, **kwargs):
        row = super().freeze_query(*args, **kwargs)
        row["schema"] = "family5-exact-real-node-query-v2"
        row["real_input"] = self.trusted_real_case.source_snapshot()
        row["onward_travel_lower_bound"] = "0"
        if row["classification"] == "unreachable":
            row["physical_exclusion"] = "every_action_lacks_selected_incoming_leg"
        return row

    def leg(self, source, target):
        table = self.trusted_real_case.table
        leg = table.pair(source, target)
        physical = self.ph.legs.get((source, target))
        return dict(source=source, target=target, reachable=leg.reachable,
                    time=None if leg.time is None else str(leg.time),
                    actual_length=None if leg.actual_length is None else str(leg.actual_length),
                    consumption=None if physical is None else str(physical[1]),
                    time_hex=leg.time_hex, actual_length_hex=leg.length_hex,
                    label_direction=leg.label_direction, table_sha256=table.payload_sha256,
                    scope="immutable_selected_totals")

    def run(self):
        return self._run_original_tree()

    def _run_original_tree(self):
        start, _ = self.event('run_start', ('case_sha256', 'dominance', 'H_ref', 'regions'))
        equal(start['case_sha256'], self.ctx.summary['case_sha256'], 'trace_trusted_case')
        equal(start['H_ref'], self.ph.bound, 'trace_stop_bound')
        require(type(start['dominance']) is bool, 'dominance_type')
        self.dominance = start['dominance']
        equal(start['regions'], self.trusted_regions(), 'trusted_region_configuration')
        root = self.region(start['regions'])
        equal(sorted(root['members']), sorted(self.ph.sites), 'root_region_site_coverage')
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


class RealReplay(RealPhysicsReplayMixin, _Replay):
    pass


@_api
def verify_trace(trace, bundle, trusted_case):
    """Verify a complete baseline HIER run using separately pinned real inputs."""
    started = time.perf_counter()
    replay = RealReplay(trace, bundle, trusted_case)
    result = replay.run()
    queries = replay.node_queries
    summary = dict(schema="real5-v2-hier-trace-check-v1", verified=True,
        trace_sha256=digest(replay.trace), bundle_sha256=replay.ctx.summary["bundle_sha256"],
        case_sha256=replay.ctx.summary["case_sha256"], region_tree_sha256=replay.region_digest,
        events=replay.cursor, invocations=replay.invocation_id, groups=replay.group_id,
        nodes=len(replay.nodes), batches=replay.batch_cursor, counts=dict(sorted(replay.counts.items())),
        exact_node_queries=len(queries), empty_action_queries=len(replay.empty_queries),
        unreachable_node_queries=sum(row["classification"] == "unreachable" for row in queries),
        query_freeze_sha256=digest(queries), canonical=result,
        elapsed_s=time.perf_counter()-started, scope="complete_real_immutable_leg_hier_invocation_trace",
        region_configuration="separately_pinned_original_tree_with_empty_children",
        numerical_suffix_optimization="not_run", literal_G8_closed=False,
        real_input_sources=trusted_case.source_snapshot(), reconstructed_checker=True)
    return CheckedTrace(_freeze(replay.trace), replay.ctx, _freeze(summary),
                        _freeze(queries), _freeze(replay.empty_queries))
