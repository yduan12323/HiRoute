"""Supervised original-node domain audit using retained numerical evidence.

The historical producer, numerical registry, and physical collector remain bound
by their original receipts. This checker has its own committed source inventory.
"""
import argparse
import json
import math
import os
import resource
import sys
import time
from pathlib import Path

from . import parallel_replay, replay_plan, runtime, suffix_census
from . import plan as binding
from .hot_jobs import read_pinned
from .worker import prior_capture

ENTRY = time.monotonic()
PROFILE = runtime.RETAINED_NODE_AUDIT
MODULE = 'experiments.time_cut_v2.recorded_real.g8_node_batch'


def _args(request, pin):
    body = read_pinned(request, pin, 65536)
    command = body['command']
    binding.require(command[:4] == ['/home/dy/miniconda3/envs/hiroute/bin/python', '-B', '-m',
                                      'experiments.time_cut_v2.recorded_real.final_collector'] and
                    command[4:6] == ['--worker', '--deadline'], 'historical collector request changed')
    from .final_collector import parser
    args = parser().parse_args(command[4:])
    producer_root = Path(request).resolve().parents[3]
    binding.require(producer_root == Path('/home/dy/HiRoute/project'),
                    'historical collector request must come from frozen producer root')
    for key, value in vars(args).items():
        if isinstance(value, Path) and not value.is_absolute():
            setattr(args, key, producer_root/value)
    binding.require(args.worker_cpus == [1, 2, 3, 4, 5] and body['profile']['name'] == 'final-collector-v1',
                    'historical collector resource or CPU binding changed')
    # The retained request's old monotonic deadline is provenance, not the
    # new supervisor's clock. Its other pins remain unchanged.
    args.deadline = None
    return args


def _before(deadline):
    binding.require(math.isfinite(deadline) and time.monotonic() < deadline,
                    'absolute retained-node batch deadline')


def accepted_collector(cli, old, before):
    """Authenticate the accepted historical physical/numerical collection."""
    before()
    receipt = read_pinned(cli.collector_acceptance, cli.collector_acceptance_sha, 65536)
    binding.require(receipt['schema'] == 'hiroute-final-collector-acceptance-v1' and
                    receipt['status'] == 'collected' and receipt['complete'] is True and
                    receipt['source_commit'] == old.source_commit and
                    receipt['source_sha256'] == old.source_sha and
                    receipt['single_C01_case_accepted'] is True and
                    receipt['single_C01_case_bound_valid'] is True,
                    'historical collector acceptance differs')
    result = read_pinned(receipt['runtime_return']['path'],
                         receipt['runtime_return']['sha256'], 65536)
    binding.require(result['status'] == 'completed' and result['descendants_reaped'] is True and
                    result['verified_manifest_sha256'] == receipt['manifest_sha256'],
                    'historical collector actual successful return differs')
    checked = runtime.read_phase_result(receipt['raw_attempt'], successful_return=result,
                                        deadline_monotonic=cli.deadline, resource_check=before)
    binding.require(checked['status'] == 'completed', 'historical collector evidence incomplete')
    summary = read_pinned(Path(receipt['raw_attempt'])/'evidence'/receipt['summary']['path'],
                          receipt['summary']['sha256'], 1024**2)
    binding.require(summary['schema'] == 'hiroute-final-collector-summary-v1' and
                    summary['complete'] is True and summary['numerical_evidence_complete'] is True and
                    summary['physical_evidence_complete'] is True and
                    summary['original_occurrence_evidence_complete'] is True,
                    'historical collector numerical or physical evidence incomplete')
    before()
    return receipt, summary


def fixture_smoke(cli, writer, before):
    """Small fenced domain seam check; never grants C01 acceptance."""
    from validation.family5.checker import _plain, canonical, digest
    from validation.real5_v2 import prepare_real_case
    from validation.real5_v2.coalesced import verify_coalesced_trace
    from validation.real5_v2.suffix_context import count_language
    from validation.trace5 import CheckedTrace
    from .node_domain_batch import check_domains
    fixture = read_pinned(cli.fixture_evidence, cli.fixture_sha, 1024**2)
    row, evidence = fixture['row'], fixture['evidence']
    trusted = prepare_real_case(row['query'], digest(row['query']),
        canonical(row['table']).encode(), row['table_sha256'],
        canonical(row['original_tree']).encode(), row['original_tree_sha256'])
    checked = verify_coalesced_trace(evidence['trace'], evidence['bundle'], trusted)
    if cli.fixture_mode == 'missing-empty':
        checked = CheckedTrace(checked._trace, checked.bundle, checked.summary,
                               checked.node_queries, checked.empty_action_queries[:-1])
    def projection(seq):
        item = next(x for x in checked.queries if x['query_seq'] == seq)
        roots, actions = _plain(item['family_ids']), _plain(item['actions'])
        counts = [count_language(trusted, item['state'], [action])['models_per_family']
                  for action in actions]
        ranges = []
        offset = 0
        for f in range(len(roots)):
            for a, count in enumerate(counts):
                ranges.append(dict(family_position=f, action_position=a, segment_id=0,
                    logical_start=0, logical_end=count, query_start=offset,
                    query_end=offset+count))
                offset += count
        if cli.fixture_mode == 'tamper-range': ranges[-1]['query_end'] += 1
        return dict(query_seq=seq, family_ids=roots, actions=actions,
                    recorded_bound=item['bound'], classification=item['classification'],
                    ancestry_bundle_sha256=item['ancestry_bundle_sha256'],
                    model_slots=offset, legal_completion_language_empty=offset==0,
                    ranges=ranges)
    domain = check_domains(checked, projection, before=before)
    writer.write('fixture-domain.json', (canonical(dict(schema='hiroute-g8-batch-fixture-v1',
        fixture_only=True, literal_G8_closed=False, historical_collector_sha256=cli.collector_acceptance_sha,
        domain=domain)).encode()+b'\n',))
    before()


def worker(cli):
    writer = None
    stage = 'source-binding'
    def before(): _before(cli.deadline)
    try:
        before()
        binding.require(os.environ.get('HIROUTE_PROFILE') == PROFILE.name and
                        int(os.environ['HIROUTE_EVIDENCE_CAP_BYTES']) == PROFILE.worker_evidence_bytes,
                        'fixed retained-node profile differs')
        binding.require(cli.worker_cpus == [1,2,3,4,5] and
                        os.sched_getaffinity(0) == set(cli.worker_cpus), 'fixed family CPU group differs')
        binding.require(not any(n == 'validation' or n.startswith(('validation.', 'timecut5'))
                                for n in sys.modules), 'math imported before NoOptimization fence')
        sys.meta_path.insert(0, suffix_census.NoOptimization())
        sources = suffix_census.check_sources(binding.ROOT, cli.checker_commit, cli.checker_source_sha)
        old = _args(cli.collector_request, cli.collector_request_sha)
        old.deadline = cli.deadline
        collector_receipt, collector_summary = accepted_collector(cli, old, before)
        if cli.fixture_mode is not None:
            stage = 'fenced-retained-evidence-fixture'
            writer = runtime.BoundedEvidenceWriter(os.environ['HIROUTE_EVIDENCE_ROOT'],
                PROFILE.worker_evidence_bytes, profile_name=PROFILE.name)
            fixture_smoke(cli, writer, before)
            suffix_census.check_sources(binding.ROOT, cli.checker_commit, cli.checker_source_sha)
            accepted_collector(cli, old, before)
            writer.finalize()
            return 0
        from . import suffix_window
        policy = suffix_window.source_policy(old, before)
        original, current = replay_plan.verify(binding.ROOT, cli.live_plan, cli.live_plan_sha,
                                               old.historical_plan, old.historical_plan_sha, cli.deadline)
        capture, capture_sha = prior_capture(original, old.historical_plan_sha,
            cli.capture_attempt, cli.capture_manifest_sha, cli.capture_result_sha,
            cli.capture_decision_sha, cli.deadline,
            successful_return_path=cli.capture_return,
            successful_return_sha=cli.capture_return_sha)
        binding.require(capture_sha == binding.pin(old.capture)['sha256'],
                        'live replay capture differs from retained collector')
        writer = runtime.BoundedEvidenceWriter(os.environ['HIROUTE_EVIDENCE_ROOT'],
            PROFILE.worker_evidence_bytes, profile_name=PROFILE.name)
        from validation.real5_v2.batch_jobs import BatchExecutor, WORKER_AS
        binding.require(WORKER_AS == 1024**3, 'family child AS differs')
        from .node_domain_batch import cold_collect
        output = None
        stage = 'live-trace-and-cold-registry'
        def checked_trace(checked):
            nonlocal output
            binding.require(output is None, 'multiple live checked traces')
            output = cold_collect(checked, binding.ROOT, old, policy, before=before)
            binding.require(binding.canonical(output['population']) ==
                            binding.canonical(collector_summary['population']) and
                            output['query_plan']['query_collection_rows_sha256'] ==
                            collector_summary['query_collection_rows_sha256'] and
                            output['domain']['total_query_events'] ==
                            collector_summary['total_query_events'],
                            'live original domain differs from accepted numerical/physical collection')
            output['historical_collector_acceptance_sha256'] = cli.collector_acceptance_sha
            output['historical_collector_manifest_sha256'] = collector_receipt['manifest_sha256']
            from . import domain
            writer.write('original-node-domain-batch.json', domain.chunks(output))
            before()
        with BatchExecutor(tuple(cli.worker_cpus[1:]), float(cli.deadline-10), capture_sha,
                           kernel='interval-join-v1') as pool:
            binding.require(len(pool.slots) == 4 and
                            all(slot.process.poll() is None for slot in pool.slots),
                            'four live family workers required')
            os.sched_setaffinity(0, {cli.worker_cpus[0]})
            summary = parallel_replay.replay(original, current, binding.ROOT, writer,
                old.historical_plan_sha, cli.live_plan_sha, capture, capture_sha, pool,
                before, shared_query_digest=True, on_checked_trace=checked_trace)
        binding.require(output is not None and summary['structural_verified'] is True and
                        summary['solver_calls'] == 0 and pool.snapshot()['complete'] is True,
                        'live replay or batch join incomplete')
        stage = 'final-binding'
        suffix_census.check_sources(binding.ROOT, cli.checker_commit, cli.checker_source_sha)
        binding.require(sources == suffix_census.source_inventory(binding.ROOT),
                        'checker source changed during execution')
        _args(cli.collector_request, cli.collector_request_sha)
        accepted_collector(cli, old, before)
        replay_plan.verify(binding.ROOT, cli.live_plan, cli.live_plan_sha,
                           old.historical_plan, old.historical_plan_sha, cli.deadline)
        before(); writer.finalize(); before()
        return 0
    except BaseException as exc:
        runtime.worker_failure(type(exc).__name__, str(exc)[:4096], stage)
        return 1
    finally:
        if writer is not None: writer.close()


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--worker', action='store_true')
    for key in ('collector_request','collector_acceptance','live_plan','capture_attempt','capture_return','attempt_dir'):
        p.add_argument('--'+key.replace('_','-'), type=Path, required=True)
    for key in ('collector_request_sha','collector_acceptance_sha','live_plan_sha','capture_manifest_sha',
                'capture_result_sha','capture_decision_sha','capture_return_sha',
                'checker_commit','checker_source_sha'):
        p.add_argument('--'+key.replace('_','-'), required=True)
    p.add_argument('--worker-cpus', type=int, nargs=5, required=True)
    p.add_argument('--cpu', type=int)
    p.add_argument('--deadline', type=float)
    p.add_argument('--fixture-evidence', type=Path)
    p.add_argument('--fixture-sha')
    p.add_argument('--fixture-mode', choices=('pass','tamper-range','missing-empty'))
    return p


def main(argv=None):
    cli = parser().parse_args(argv)
    if cli.worker: return worker(cli)
    binding.require(cli.cpu == 0 and cli.worker_cpus == [1,2,3,4,5] and
                    not cli.attempt_dir.exists(), 'fresh fixed supervisor request required')
    deadline = float(ENTRY + PROFILE.wall_seconds)
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    binding.require(hard == resource.RLIM_INFINITY or hard >= PROFILE.child_as_bytes,
                    'inherited AS ceiling too small')
    resource.setrlimit(resource.RLIMIT_AS,
        (min(PROFILE.supervisor_as_bytes, soft) if soft != resource.RLIM_INFINITY
         else PROFILE.supervisor_as_bytes, hard))
    sources = suffix_census.check_sources(binding.ROOT, cli.checker_commit, cli.checker_source_sha)
    old = _args(cli.collector_request, cli.collector_request_sha)
    accepted_collector(cli, old, lambda: _before(deadline))
    binding.require((cli.fixture_mode is None and cli.fixture_evidence is None and cli.fixture_sha is None) or
                    (cli.fixture_mode is not None and cli.fixture_evidence is not None and cli.fixture_sha is not None),
                    'fixture evidence and mode must be complete')
    if cli.fixture_mode is not None:
        binding.require(binding.pin(cli.fixture_evidence)['sha256'] == cli.fixture_sha,
                        'fixture evidence changed')
    else:
        binding.require(cli.fixture_evidence is None and cli.fixture_sha is None,
                        'unexpected fixture evidence in full batch')
    if cli.fixture_mode is None:
        original, current = replay_plan.verify(binding.ROOT, cli.live_plan, cli.live_plan_sha,
                                               old.historical_plan, old.historical_plan_sha, deadline)
        binding.require(current['source_commit'] == cli.checker_commit and
                        current['source_sha256'] ==
                        binding.digest(binding.source_inventory(binding.ROOT)),
                        'live plan is not bound to committed replay source')
    from . import suffix_window
    suffix_window.source_policy(old, lambda: _before(deadline))
    command = [sys.executable, '-B', '-m', MODULE, '--worker']
    for key in ('collector_request','collector_acceptance','live_plan','capture_attempt','capture_return','attempt_dir'):
        command += ['--'+key.replace('_','-'), str(getattr(cli,key).resolve())]
    for key in ('collector_request_sha','collector_acceptance_sha','live_plan_sha','capture_manifest_sha',
                'capture_result_sha','capture_decision_sha','capture_return_sha',
                'checker_commit','checker_source_sha'):
        command += ['--'+key.replace('_','-'), getattr(cli,key)]
    if cli.fixture_mode is not None:
        command += ['--fixture-evidence', str(cli.fixture_evidence.resolve()),
                    '--fixture-sha', cli.fixture_sha, '--fixture-mode', cli.fixture_mode]
    command += ['--worker-cpus', *map(str,cli.worker_cpus), '--deadline', repr(deadline)]
    context = runtime.PlanContext(cli.live_plan_sha, cli.checker_source_sha,
        binding.digest(dict(historical_plan=old.historical_plan_sha,
                            collector_request=cli.collector_request_sha,
                            collector_acceptance=cli.collector_acceptance_sha,
                            capture_sha=binding.pin(old.capture)['sha256'],
                            historical_registry=old.registry_sha,
                            fixture_sha=cli.fixture_sha, fixture_mode=cli.fixture_mode)), PROFILE.name)
    result = runtime.run_phase(command, attempt_dir=cli.attempt_dir, profile=PROFILE,
        cpu=cli.cpu, worker_cpus=tuple(cli.worker_cpus), context=context,
        entry_monotonic=float(ENTRY), deadline_monotonic=deadline)
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] == 'completed' else 1

if __name__ == '__main__': raise SystemExit(main())
