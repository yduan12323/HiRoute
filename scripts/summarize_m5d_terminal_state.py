#!/usr/bin/env python3
"""Audit the frozen M5-D terminal state, never inferring exactness from timeout.

Inputs are immutable evidence, not live process status. JSON duplicate keys and
inconsistent row/accounting identities are rejected even under Python -OO.
"""
import argparse
from collections import Counter, defaultdict
from decimal import Decimal
import hashlib
import json
from pathlib import Path


class EvidenceError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise EvidenceError(message)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key: ' + key)
        result[key] = value
    return result


def load(path):
    raw = Path(path).read_bytes()
    return json.loads(raw, object_pairs_hook=unique_object), hashlib.sha256(raw).hexdigest()


def load_projection(path, expected_kind):
    wrapper, file_sha = load(path)
    require(wrapper.get('schema') == 'hiroute.m5d.public_state_projection.v1', 'projection schema')
    require(wrapper.get('kind') == expected_kind, 'projection kind')
    original = wrapper.get('original_sha256', '')
    require(isinstance(original, str) and len(original) == 64 and all(c in '0123456789abcdef' for c in original), 'original provenance hash')
    payload = wrapper.get('payload')
    require(isinstance(payload, dict), 'projection payload')
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    require(digest == wrapper.get('payload_sha256'), 'projection payload hash mismatch')
    return payload, file_sha, original


def integer(value, name):
    require(type(value) is int and value >= 0, 'invalid nonnegative integer: ' + name)
    return value


def hours(ns):
    return str(Decimal(ns) / Decimal(3_600_000_000_000))


def summarize(manifest, state, parallel, manifest_hash):
    require(state.get('schema') == 'hiroute.m5d.main_batch_state.v1', 'main schema')
    require(parallel.get('schema') == 'hiroute.m5d.parallel_continuation_state.v3', 'parallel schema')
    require(state.get('phase_sha256') == parallel.get('manifest_sha256') == manifest_hash, 'manifest binding mismatch')
    require(state.get('stopped') is True and parallel.get('stopped') is True, 'nonterminal snapshot')
    require(parallel.get('stop_reason') == 'all_fixed_rows_completed' and parallel.get('inflight') == {}, 'unfinished continuation')
    planned = manifest['rows']
    ids = [r['row_id'] for r in planned]
    require(len(ids) == len(set(ids)), 'duplicate manifest row ID')
    require(set(state['rows']) == set(ids), 'missing or unexpected result row IDs')
    start = integer(parallel['start_index'], 'start_index')
    require(start <= len(ids), 'invalid start_index')
    expected_continuation = ids[start:]
    require(parallel['launch_order'] == expected_continuation, 'missing, duplicated or reordered launch IDs')
    require(set(parallel['completed']) == set(expected_continuation), 'continuation row set mismatch')
    admissions = parallel['admissions']
    require([r['row_id'] for r in admissions] == expected_continuation, 'admission row order mismatch')
    require([r['manifest_index'] for r in admissions] == list(range(start, len(ids))), 'admission manifest indexes mismatch')
    normalized, phases, statuses = [], Counter(), Counter()
    pairs = defaultdict(dict)
    by_od = defaultdict(Counter)
    by_method = defaultdict(Counter)
    for index, planned_row in enumerate(planned):
        rid = planned_row['row_id']
        row = state['rows'][rid]
        status = row['status']
        # This audit is specifically for the completed censored main matrix.
        # Future exact rows need their own optimality/witness proof audit.
        require(status in ('time_limit', 'incumbent_search_failed'), 'unsupported status needs proof-aware audit: ' + status)
        require(row.get('denominator_included') is True, 'excluded denominator: ' + rid)
        cpu = integer(row['cgroup_cpu_usage_ns'], rid + ' CPU')
        phase = row.get('reached_phase', 'unknown')
        require(phase in ('unknown', 'seed_started', 'seed_failed'), 'unrecognized observed phase')
        if index >= start:
            completed = parallel['completed'][rid]
            require(completed['manifest_index'] == index, 'completed index mismatch')
            require(completed.get('receipt_durable') is True, 'receipt not durable')
            require(completed['status'] == status and completed['charged_cpu_ns'] == cpu, 'completed status/CPU mismatch')
            require(completed['row_result'] == row, 'main and continuation row disagree')
        method = planned_row['method']
        require(method in ('flat', 'hier'), 'unknown method')
        pair = (planned_row['query_id'], planned_row['candidate_prefix_count'])
        require(method not in pairs[pair], 'duplicate method within paired binding')
        pairs[pair][method] = rid
        phases[phase] += 1
        statuses[status] += 1
        od = planned_row['query_id'].split('_', 1)[0]
        by_od[od][status] += 1
        by_method[method][status] += 1
        normalized.append(dict(planned_row, status=status, denominator_included=True,
                               cgroup_cpu_usage_ns=cpu, reached_phase_observed=phase,
                               solver_completion='not_exact',
                               wall_elapsed_ns=row.get('wall_elapsed_ns'),
                               cgroup_memory_peak_bytes=row.get('cgroup_memory_peak_bytes'),
                               cgroup_memory_limit_bytes=row.get('cgroup_memory_limit_bytes')))
    require(all(set(v) == {'flat', 'hier'} for v in pairs.values()), 'unpaired method rows')
    row_cpu = sum(r['cgroup_cpu_usage_ns'] for r in normalized)
    serial_cpu = sum(r['cgroup_cpu_usage_ns'] for r in normalized[:start])
    parallel_cpu = row_cpu - serial_cpu
    require(row_cpu == state['charged_cpu_ns'] == parallel['charged_cpu_ns'], 'total row CPU mismatch')
    require(serial_cpu == parallel['charged_cpu_ns_at_start'], 'serial carry-in CPU mismatch')
    host = integer(parallel['host_cpu_ns'], 'host_cpu_ns')
    # batch_and_waited_child_cpu_ns is a cumulative host snapshot. Never sum it.
    snapshots = [integer(r.get('batch_and_waited_child_cpu_ns', 0), 'host snapshot') for r in state['rows'].values()]
    require(max(snapshots, default=0) <= host, 'host total less than cumulative snapshot')
    report = {
        'schema': 'hiroute.m5d.terminal_state_audit.v1',
        'manifest_sha256': manifest_hash,
        'evidence_kind': 'uploaded_terminal_snapshots_not_live_status',
        'denominator': len(ids), 'recorded_terminal_rows': len(ids),
        'status_counts': dict(sorted(statuses.items())), 'exact_rows': 0,
        'exact_completion_rate': 0, 'resource_interruption_rows': statuses['time_limit'],
        'resource_interruption_rate': statuses['time_limit'] / len(ids),
        'observed_phase_counts': dict(sorted(phases.items())),
        'phase_warning': 'Serial rows without reached_phase remain unknown; do not classify all timeouts as pre-search.',
        'paired_bindings': len(pairs), 'paired_exact_bindings': 0,
        'paired_exact_subset_fraction': 0, 'paired_end_to_end_speedup': None,
        'paired_speedup_display': 'NA',
        'paired_speedup_reason': 'No pair has two proof-verified exact completions. Censored durations are not speedups.',
        'by_od': {k: dict(sorted(v.items())) for k,v in sorted(by_od.items())},
        'by_method': {k: dict(sorted(v.items())) for k,v in sorted(by_method.items())},
        'cpu_accounting': {
            'row_cgroup_ns': row_cpu, 'row_cgroup_hours': hours(row_cpu),
            'serial_row_cgroup_ns': serial_cpu, 'parallel_row_cgroup_ns': parallel_cpu,
            'parallel_host_cumulative_ns': host, 'parallel_host_hours': hours(host),
            'main_rows_plus_parallel_host_known_subtotal_ns': row_cpu + host,
            'main_rows_plus_parallel_host_known_subtotal_hours': hours(row_cpu + host),
            'sum_per_row_host_snapshots': 'FORBIDDEN: cumulative values would double-count',
            'pre_main_conservative_cpu_hours_from_manifest': manifest.get('conservative_cpu_hours_before_main'),
            'original_48_cpu_hour_ledger_complete': False,
            'unreconciled_components': ['serial controller/host overhead', 'transition overhead and final tails', 'complete original experiment ledger reconciliation'],
            'later_experiments': 'Separate continuation/diagnostic ledgers; never substitute into the original 192-row matrix.'},
        'acceptance': {'main_matrix_executed': True, 'computational_benefit_demonstrated': False,
                       'm5d_complete': False, 'final_classification': None,
                       'current_interpretation': 'Main matrix limited by seed/search cost; full milestone conclusion pending D5/D6/D8 gaps.'}
    }
    return report, normalized


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--state', required=True)
    parser.add_argument('--parallel-state', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    manifest, mh = load(args.manifest)
    state, sh, original_sh = load_projection(args.state, 'main')
    parallel, ph, original_ph = load_projection(args.parallel_state, 'parallel')
    report, rows = summarize(manifest, state, parallel, mh)
    report['input_sha256'] = {'frozen_manifest': mh, 'main_public_projection': sh, 'parallel_public_projection': ph}
    report['original_uploaded_raw_sha256'] = {'main_state': original_sh, 'parallel_state': original_ph}
    report['provenance_limit'] = 'Public projections contain selected fields from owner-uploaded raw states. Original raw hashes identify provenance; the public files alone cannot reconstruct raw bytes or independently validate server receipts.'
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'terminal_summary.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    (out / 'benchmark_results.jsonl').write_text(''.join(json.dumps(r, sort_keys=True) + '\n' for r in rows))
    print(json.dumps({'denominator': report['denominator'], 'counts': report['status_counts'], 'speedup': 'NA'}))

if __name__ == '__main__':
    main()
