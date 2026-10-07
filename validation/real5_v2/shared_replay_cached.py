"""Opt-in exact finalization using owned-DAG canonical byte caching.

Physical, family and ordered traversal code remains RealCoalescedReplay. The
original shared_replay verifier is retained as the differential reference.
"""
import time
from validation.family5.checker import _freeze
from validation.trace5.checker import _api,CheckedTrace
from validation.trace5.coalesced import REPRESENTATION
from validation.capture5.containers import stream_digest
from validation.capture5.query_dag_digest import QueryDagEncoder
from .shared_replay import RealCoalescedReplay

@_api
def verify_coalesced_trace(trace,bundle,trusted_case,*,on_stage=lambda *a,**k:None,metrics=None,measure_lengths=False,on_progress=None):
 started=time.perf_counter();replay=RealCoalescedReplay(trace,bundle,trusted_case);result=replay.run()
 on_stage('after_ordered_trace',replay=replay)
 on_stage('trace_digest');trace_sha=stream_digest(replay.trace)
 on_stage('query_freeze');encoder=QueryDagEncoder(replay.node_queries)
 if measure_lengths:
  on_stage('query_size_count',encoder=encoder);encoder.measure_lengths()
 encoder.progress=on_progress
 on_stage('query_digest',encoder=encoder);query_sha=encoder.digest();stats=encoder.snapshot()
 if metrics is not None:metrics.update(stats)
 on_stage('summary')
 queries=encoder.queries
 summary=dict(schema='family5-real-coalesced-hier-trace-check-v2',verified=True,
  representation=REPRESENTATION,reconstructed_checker=True,trace_sha256=trace_sha,
  bundle_sha256=replay.ctx.summary['bundle_sha256'],case_sha256=replay.ctx.summary['case_sha256'],
  region_tree_sha256=replay.region_digest,real_input=trusted_case.source_snapshot(),events=replay.cursor,
  invocations=replay.invocation_id,coalescings=replay.coalescing_id,groups=replay.group_id,
  nodes=len(replay.nodes),batches=replay.batch_cursor,counts=dict(sorted(replay.counts.items())),
  exact_node_queries=len(queries),empty_action_queries=len(replay.empty_queries),
  unreachable_node_queries=sum(row['classification']=='unreachable' for row in queries),
  query_freeze_sha256=query_sha,canonical=result,elapsed_s=time.perf_counter()-started,
  scope='complete_real_immutable_leg_coalesced_hier_invocation_trace',
  region_configuration='separately_pinned_original_tree_with_empty_children',
  numerical_suffix_optimization='not_run',literal_G8_closed=False)
 on_stage('trace_and_summary_freeze')
 checked=CheckedTrace(_freeze(replay.trace),replay.ctx,_freeze(summary),queries,_freeze(replay.empty_queries))
 on_stage('finalization_returned',metrics=stats,query_sha256=query_sha)
 return checked
