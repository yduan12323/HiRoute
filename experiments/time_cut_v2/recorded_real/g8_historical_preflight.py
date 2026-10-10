"""Read-only path, origin and byte preflight for retained C01 D1 leaves.

This does not admit mathematical certificates or report G8 acceptance.
"""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sys
import time

from . import plan as binding, recovery_plan, suffix_census, suffix_window
from . import window_receipts as wr, window_recovery_receipts as recovery
from .g8_node_batch import _args, accepted_collector
from .hot_jobs import read_pinned
from .runtime import _directory, read_phase_result


LEAF_SHAPES = {
    'C01::HIER::D-on': (86, {'block_resume': 1, 'suffix_window': 83, 'suffix_window_recovery': 2}),
    'C01::HIER::D-off': (105, {'suffix_window': 105}),
}


def preflight(registry, producer_root, reviewed_sources, *, variant_id, deadline, before=lambda: None):
    root = wr.historical_root(producer_root)
    binding.require(variant_id in LEAF_SHAPES, 'unsupported retained registry variant')
    leaf_count, expected_modules = LEAF_SHAPES[variant_id]
    binding.require(registry['schema'] == 'hiroute-checked-window-registry-v1' and
                    len(registry['entries']) == leaf_count, 'fixed retained registry leaf count changed')
    counts, hashed, recovery_leaves = Counter(), set(), 0
    def guard():
        before()
        binding.require(time.monotonic() < deadline, 'retained path preflight deadline')
    def pinned(path, sha, size, limit=1024**3):
        path = wr.historical_path(str(path), root)
        key = (path, sha)
        if key not in hashed:
            wr._read(path, sha, limit, guard, size=size, decode=False)
            hashed.add(key)
        return path
    for entry in registry['entries']:
        guard()
        module = entry['module']; counts[module] += 1
        binding.require(module in ('block_resume','suffix_window','suffix_window_recovery'),
                        'foreign retained leaf module')
        attempt = Path(wr.historical_path(entry['attempt'], root))
        fd = _directory(attempt); os.close(fd)
        returned = wr._read(wr.historical_path(entry['successful_return'], root),
                            entry['successful_return_sha256'], 65536, guard)
        runtime = read_phase_result(attempt, successful_return=returned,
                                    deadline_monotonic=deadline, resource_check=guard)
        binding.require(runtime.get('status') == 'completed' and runtime['descendants_reaped'] is True and
                        runtime['verified_manifest_sha256'] == entry['manifest_sha256'],
                        'retained leaf runtime return or manifest differs')
        request = wr._read(attempt/'request.json', runtime['request_sha256'], 1024**2, guard)
        manifest = wr._read(attempt/'evidence/__manifest.json', entry['manifest_sha256'], 1024**2, guard)
        files = {row['path']: row for row in manifest['files']}
        binding.require(len(files) == len(manifest['files']) and 'run-binding.json' in files,
                        'retained leaf manifest lacks unique run binding')
        run_pin=files['run-binding.json']
        run=wr._read(attempt/'evidence/run-binding.json', run_pin['sha256'],
                     wr.SUMMARY_LIMIT, guard, size=run_pin['size_bytes'])
        if module == 'suffix_window_recovery':
            values = recovery_plan.command(request, producer_root=root)
            recovery._origin(run['invocation_origin'], request, producer_root=root)
            plan_document = recovery_plan.load(values['recovery_plan'], values['recovery_plan_sha'],
                                               deadline=deadline, before=guard)
            for ancestor in plan_document['predecessors']:
                recovery_leaves += 1
                binding.require(wr.historical_path(ancestor['attempt'],root) == ancestor['attempt'],
                                'recovery predecessor escapes producer root')
                for pin in ancestor['artifacts'].values():
                    if pin is not None:
                        pinned(pin['path'], pin['sha256'], pin['size_bytes'])
        else:
            values = wr._command(request, module, producer_root=root)
            if module == 'suffix_window':
                wr.window_origin(run['invocation_origin'], request, root)
        wr._source(values['source_commit'], values['source_sha'], module, reviewed_sources)
        binding.require(run['source_commit'] == values['source_commit'] and
                        run['source_sha256'] == values['source_sha'],
                        'retained request differs from run source')
        if 'source_policy' in values and values['source_policy'] is not None:
            policy = wr._read(values['source_policy'], values['source_policy_sha'], 65536, guard)
            binding.require(policy['reviewed_sources'].get(values['source_commit']) == values['source_sha'] and
                            all(reviewed_sources.get(k) == v for k,v in policy['reviewed_sources'].items()),
                            'retained leaf source policy differs from reviewed sources')
        dependencies = entry['dependencies']
        binding.require(len(dependencies) == len({(d['path'],d['sha256']) for d in dependencies}),
                        'duplicate retained dependency')
        for dep in dependencies:
            pinned(dep['path'], dep['sha256'], dep['size_bytes'])
    binding.require(dict(counts) == expected_modules,
                    'retained registry module population changed')
    return dict(schema='hiroute-historical-path-preflight-v1',
        producer_root=str(root), variant_id=variant_id, leaves=sum(counts.values()), modules=dict(counts),
        recovery_predecessors=recovery_leaves, distinct_hashed_dependencies=len(hashed),
        source_and_origin_paths_verified=True, mathematical_acceptance=False,
        lp_calls=0, full_batch_attempt_started=False)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('collector_request','collector_acceptance','checker_commit','checker_source_sha'):
        p.add_argument('--'+name.replace('_','-'),required=True)
    for name in ('collector_request_sha','collector_acceptance_sha'):
        p.add_argument('--'+name.replace('_','-'),required=True)
    p.add_argument('--deadline-seconds',type=int,default=300)
    args=p.parse_args(argv)
    deadline=time.monotonic()+args.deadline_seconds
    args.deadline=deadline
    suffix_census.check_sources(binding.ROOT,args.checker_commit,args.checker_source_sha)
    old=_args(Path(args.collector_request),args.collector_request_sha)
    receipt, summary = accepted_collector(args,old,lambda: binding.require(time.monotonic()<deadline,'preflight deadline'))
    sources=suffix_window.source_policy(old)
    registry=read_pinned(old.registry,old.registry_sha,wr.REGISTRY_LIMIT)
    variant_id = receipt.get('variant_id', 'C01::HIER::D-on')
    from .variant_scope import is_d0_population
    binding.require((variant_id == 'C01::HIER::D-off') == is_d0_population(summary['population']),
                    'retained registry variant differs from collector population')
    result=preflight(registry,old.producer_root,sources,variant_id=variant_id,deadline=deadline)
    print(json.dumps(result,sort_keys=True))
    return 0

if __name__=='__main__': raise SystemExit(main())
