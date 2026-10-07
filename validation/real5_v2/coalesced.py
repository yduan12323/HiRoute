"""Reconstructed composition of trusted real physics and exact compact grammar.

This glue introduces no routing, optimization or new mathematical predicate.
It preserves the published CheckedTrace/CheckedBundle interchange classes.
"""
import time
from validation.family5.checker import _freeze, digest
from validation.trace5.checker import _api, CheckedTrace
from validation.trace5.coalesced import CoalescedReplay, REPRESENTATION
from .trace import RealPhysicsReplayMixin


class RealCoalescedReplay(RealPhysicsReplayMixin, CoalescedReplay):
    """The real mixin supplies physics/tree; the v2 layer checks every compact."""


@_api
def verify_coalesced_trace(trace, bundle, trusted_case):
    started = time.perf_counter()
    replay = RealCoalescedReplay(trace, bundle, trusted_case)
    result = replay.run()
    queries = replay.node_queries
    summary = dict(schema='family5-real-coalesced-hier-trace-check-v2', verified=True,
        representation=REPRESENTATION, reconstructed_checker=True,
        trace_sha256=digest(replay.trace), bundle_sha256=replay.ctx.summary['bundle_sha256'],
        case_sha256=replay.ctx.summary['case_sha256'], region_tree_sha256=replay.region_digest,
        real_input=trusted_case.source_snapshot(), events=replay.cursor,
        invocations=replay.invocation_id, coalescings=replay.coalescing_id,
        groups=replay.group_id, nodes=len(replay.nodes), batches=replay.batch_cursor,
        counts=dict(sorted(replay.counts.items())), exact_node_queries=len(queries),
        empty_action_queries=len(replay.empty_queries),
        unreachable_node_queries=sum(row['classification']=='unreachable' for row in queries),
        query_freeze_sha256=digest(queries), canonical=result,
        elapsed_s=time.perf_counter()-started,
        scope='complete_real_immutable_leg_coalesced_hier_invocation_trace',
        region_configuration='separately_pinned_original_tree_with_empty_children',
        numerical_suffix_optimization='not_run', literal_G8_closed=False)
    return CheckedTrace(_freeze(replay.trace), replay.ctx, _freeze(summary),
                        _freeze(queries), _freeze(replay.empty_queries))
