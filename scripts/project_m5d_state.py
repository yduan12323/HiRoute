#!/usr/bin/env python3
"""Create minimal shareable evidence; raw scheduler state stays private.

Provenance SHA records which original byte stream was projected. It is not proof
of independent receipt verification. No receipt paths, scheduler tokens or
incidental host configuration are retained.
"""
import argparse
import hashlib
import json
from pathlib import Path
from summarize_m5d_terminal_state import load

ROW_FIELDS = ('cgroup_cpu_usage_ns', 'denominator_included', 'status', 'reached_phase',
              'wall_elapsed_ns', 'cgroup_memory_peak_bytes', 'cgroup_memory_limit_bytes',
              'batch_and_waited_child_cpu_ns')


def pick(data, fields):
    return {k:data[k] for k in fields if k in data}


def canonical_hash(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def project(raw, original_sha256, kind):
    if kind == 'main':
        payload = pick(raw, ('charged_cpu_ns','phase_sha256','schema','stopped'))
        payload['rows'] = {k:pick(v,ROW_FIELDS) for k,v in raw['rows'].items()}
    elif kind == 'parallel':
        payload = pick(raw, ('charged_cpu_ns','charged_cpu_ns_at_start','host_cpu_ns',
                             'manifest_sha256','schema','start_index','stop_reason','stopped','launch_order'))
        # Only empty in-flight state can be exported as terminal evidence.
        if raw.get('inflight') != {}:
            raise ValueError('Cannot project nonterminal in-flight state')
        payload['inflight'] = {}
        payload['admissions'] = [pick(v,('row_id','manifest_index')) for v in raw['admissions']]
        payload['completed'] = {}
        for k,v in raw['completed'].items():
            item = pick(v, ('charged_cpu_ns','manifest_index','receipt_durable','status'))
            item['row_result'] = pick(v['row_result'],ROW_FIELDS)
            payload['completed'][k] = item
    else:
        raise ValueError('Unknown projection kind')
    return {'schema':'hiroute.m5d.public_state_projection.v1', 'kind':kind,
            'original_sha256':original_sha256, 'payload_sha256':canonical_hash(payload),
            'payload':payload}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw-input', required=True)
    p.add_argument('--kind', choices=['main','parallel'], required=True)
    p.add_argument('--output', required=True)
    args=p.parse_args()
    data, sha=load(args.raw_input)
    Path(args.output).write_text(json.dumps(project(data,sha,args.kind),indent=2,sort_keys=True)+'\n')

if __name__=='__main__':main()
