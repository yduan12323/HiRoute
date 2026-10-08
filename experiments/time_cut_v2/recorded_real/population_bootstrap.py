"""D0 catalogue bootstrap from cold-authenticated replay/count receipts only.

This creates scheduling context, never a CheckedTrace/CheckedBundle or a
numerical certificate. A live worker must independently admit genuine families
and compare this complete catalogue and population freeze before any LP.
"""
import argparse
import math
import sys
import time
from pathlib import Path

from . import plan as binding, suffix_census, model_preview, variant_scope

SCHEMA = 'hiroute-c01-d0-population-bootstrap-v1'
MAX_BYTES = 32 * 1024**2
FIELDS = ('bootstrap', 'bootstrap_sha')


def check_count_budget(request, accepted):
    """Authenticate the narrower count budget inside the 1800-second profile.

    Both objects must come from the independently pinned actual request and
    successful cold return. A report's descriptive resource_scope is insufficient.
    """
    for key in ('entry_monotonic', 'deadline_monotonic'):
        binding.require(type(request.get(key)) is float and math.isfinite(request[key]) and
                        type(accepted.get(key)) is float and math.isfinite(accepted[key]) and
                        request[key] == accepted[key], 'count request/return time binding changed: '+key)
    entry, deadline = request['entry_monotonic'], request['deadline_monotonic']
    binding.require(entry < deadline <= entry+suffix_census.SECONDS,
                    'count request exceeds reviewed 180-second budget')
    command = request['command']
    binding.require(type(command) is list and all(type(arg) is str for arg in command),
                    'count worker command strings required')
    # Reject duplicate, attached and abbreviated deadline options rather than
    # allowing argparse to select a different effective deadline.
    options = [arg for arg in command if arg.startswith('--') and
               '--deadline'.startswith(arg.split('=', 1)[0])]
    binding.require(options == ['--deadline'], 'one exact count worker deadline option required')
    position = command.index('--deadline')+1
    binding.require(position < len(command), 'count worker deadline value required')
    try:
        worker_deadline = float(command[position])
    except ValueError as error:
        raise ValueError('invalid count worker deadline value') from error
    binding.require(math.isfinite(worker_deadline) and worker_deadline == deadline,
                    'count worker deadline differs from actual request')


def catalogue_from_count(trusted, logical, before=lambda: None):
    """No checked family is fabricated: this is independently counted metadata."""
    from validation.real5_v2.suffix_context import count_language
    from validation.suffix5.block_plan import POLICY, block_ranges
    from validation.family5.checker import digest
    binding.require(logical['schema'] == 'hiroute-original-family-logical-model-count-v1',
                    'original logical count required')
    segments, seen, ordinal, words, exclusions = [], set(), 0, 0, 0
    for number, group in enumerate(logical['groups']):
        before()
        binding.require(type(group['group_index']) is int and group['group_index'] == number and
                        group['family_id'] not in seen, 'ordered original logical families required')
        seen.add(group['family_id'])
        state = group['context']['state']
        actions = group['first_actions']
        binding.require(actions == sorted(actions) and len({tuple(a) for a in actions}) == len(actions),
                        'canonical disjoint first actions required')
        suffix_census.same(group['counts'], count_language(trusted, state, actions), 'family language changed')
        for action in actions:
            before()
            counts = count_language(trusted, state, [action]); size = counts['models_per_family']
            segments.append(dict(segment_id=len(segments), group_index=number, family_id=group['family_id'],
                first_action=list(action), prefix_depth=state[2], start=ordinal, end=ordinal+size,
                model_count=size, legal_words=counts['legal_words_per_family'],
                graph_exclusions=counts['graph_exclusion_models_per_family']))
            ordinal += size; words += counts['legal_words_per_family']; exclusions += counts['graph_exclusion_models_per_family']
    for key, value in (('unique_families', len(seen)), ('unique_family_first_action_pairs', len(segments)),
            ('unique_logical_model_slots', ordinal), ('unique_logical_words', words),
            ('unique_graph_exclusions', exclusions), ('unique_reachable_band_models', ordinal-exclusions)):
        binding.require(type(logical[key]) is int and logical[key] == value, 'exact logical count changed: '+key)
    return dict(schema='suffix5-original-model-block-plan-v1', policy=POLICY,
        source_bundle_sha256=logical['source_bundle_sha256'], case_sha256=trusted.source_snapshot()['case_sha256'],
        real_input=trusted.source_snapshot(), logical_plan_sha256=digest(logical), block_size=256,
        total_models=ordinal, segments=segments, blocks=block_ranges(ordinal, 256),
        numerical_acceptance=False, literal_G8_closed=False)


def population_from_count(index, trusted, logical, anchors, before=lambda: None):
    binding.require(index['bundle_sha256'] == logical['source_bundle_sha256'] and
                    index['case_sha256'] == trusted.source_snapshot()['case_sha256'],
                    'count population differs from replay physical sources')
    binding.require(type(index['exact_queries']) is int and index['exact_queries'] == len(index['queries']),
                    'original query count changed')
    catalogue = catalogue_from_count(trusted, logical, before)
    commitment = dict(schema='hiroute-cold-admitted-suffix-population-v1', completed_replay=anchors,
        block_plan_sha256=binding.digest(catalogue), logical_plan_sha256=catalogue['logical_plan_sha256'],
        source_bundle_sha256=index['bundle_sha256'], case_sha256=index['case_sha256'],
        query_freeze_sha256=index['query_freeze_sha256'], queries=len(index['queries']),
        original_model_occurrences=logical['original_occurrence_model_slots'], unique_logical_models=catalogue['total_models'],
        empty_action_queries=index['empty_action_queries'], empty_action_sha256=index['empty_action_sha256'],
        numerical_acceptance=False, literal_G8_closed=False)
    commitment = variant_scope.with_variant(commitment, anchors)
    variant_scope.population_scope(catalogue, commitment)
    return catalogue, commitment


def common_inputs(args):
    from .window_receipts import COMMON_PATHS, COMMON_PINS
    return {key: str(getattr(args, key)) for key in COMMON_PATHS+COMMON_PINS}


def authenticate_inputs(args, reviewed_sources, deadline, before=lambda: None, *, cache=None):
    from . import window_receipts as receipts, replay_plan
    before()
    binding.require(reviewed_sources.get(args.source_commit) == args.source_sha,
                    'bootstrap source outside reviewed allowlist')
    original = replay_plan.historical_plan(binding.ROOT, args.historical_plan, args.historical_plan_sha)
    binding.require(variant_scope.physical_scope(original), 'bootstrap is D0-only')
    replay = replay_plan.historical_plan(binding.ROOT, args.replay_plan, args.replay_plan_sha)
    binding.require(original['source_commit'] == replay['source_commit'] == args.source_commit and
                    args.logical_source_sha == args.source_sha,
                    'initial D0 bootstrap requires one reviewed source checkpoint')
    index, trusted, summary, anchors = suffix_census.completed_inputs(binding.ROOT, args, deadline, before)
    cache = cache or receipts._Dependencies(before)
    # Actual successful returns, decisions, manifests and every upstream proof
    # remain required, even when a repaired outer JSON repeats correct counts.
    for prefix, module in (('replay', 'parallel_replay'), ('logical', 'suffix_census')):
        returned = cache.read(getattr(args, prefix+'_return'), getattr(args, prefix+'_return_sha'), 65536)
        result = receipts.read_phase_result(getattr(args, prefix+'_attempt'), successful_return=returned,
            deadline_monotonic=deadline, resource_check=before)
        binding.require(result.get('status') == 'completed', 'completed bootstrap '+prefix+' return required')
        request = cache.read(Path(getattr(args, prefix+'_attempt'))/'request.json', result['request_sha256'], 1024**2)
        command = request['command']
        binding.require(type(command) is list and len(command) > 5 and
                        command[:5] == [sys.executable, '-B', '-m', receipts.MODULE_PREFIX+module, '--worker'],
                        'reviewed bootstrap '+prefix+' worker required')
        if prefix == 'logical':
            check_count_budget(request, result)
    logical = model_preview.logical_input(args, anchors, index, trusted, summary, deadline, before)
    logical_result = cache.read(Path(args.logical_attempt)/'evidence/suffix-census.json', args.logical_report_sha, 64*1024**2)
    binding.require(logical_result.get('census_source_commit') == args.source_commit,
                    'bootstrap logical checkpoint changed')
    catalogue, commitment = population_from_count(index, trusted, logical, anchors, before)
    binding.require(variant_scope.is_d0_population(commitment), 'D0 replay/count anchors required')
    receipts._inputs(common_inputs(args), commitment, cache, deadline)
    before()
    return dict(schema=SCHEMA, source_commit=args.source_commit, source_sha256=args.source_sha,
        inputs=common_inputs(args), catalogue=catalogue, population=commitment,
        numerical_acceptance=False, literal_G8_closed=False)


def admit_bootstrap(args, reviewed_sources, *, deadline, before=lambda: None, admitted=None, cache=None):
    from . import window_receipts as receipts
    cache = cache or receipts._Dependencies(before)
    manifest = cache.read(args.bootstrap, args.bootstrap_sha, MAX_BYTES)
    expected = authenticate_inputs(args, reviewed_sources, deadline, before, cache=cache)
    suffix_census.same(manifest, expected, 'bootstrap differs from authenticated replay/count population')
    scope = receipts.ReceiptScope(expected['catalogue'], expected['population'], _token=receipts._ADMISSION)
    if admitted is not None:
        suffix_census.same(admitted.population.plan(), scope.plan(), 'fresh D0 catalogue differs from bootstrap')
        suffix_census.same(admitted.commitment(), scope.commitment(), 'fresh D0 population differs from bootstrap')
    return scope, receipts.make_registry(scope, [])


def main():
    from .window_receipts import COMMON_PATHS, COMMON_PINS
    from .suffix_window import source_policy
    parser = argparse.ArgumentParser(description=__doc__)
    for key in COMMON_PATHS+('source_policy', 'output'):
        parser.add_argument('--'+key.replace('_', '-'), type=Path, required=True)
    for key in COMMON_PINS+('source_policy_sha',):
        parser.add_argument('--'+key.replace('_', '-'), required=True)
    args = parser.parse_args()
    # Metadata preparation only, like plan preparation. No worker/capture/LP
    # launch is hidden here. Read/loop bounds and the count ceiling are retained.
    import resource
    soft, hard = resource.getrlimit(resource.RLIMIT_AS)
    ceiling = suffix_census.WORKER_AS
    if soft != resource.RLIM_INFINITY:
        ceiling = min(ceiling, soft)
    if hard != resource.RLIM_INFINITY:
        ceiling = min(ceiling, hard)
    resource.setrlimit(resource.RLIMIT_AS, (ceiling, hard))
    from .runtime import _directory
    import os
    directory = _directory(args.output.parent)
    os.close(directory)
    deadline = time.monotonic()+suffix_census.SECONDS
    def before():
        binding.require(time.monotonic() < deadline, 'bootstrap preparation deadline')
    sys.meta_path.insert(0, suffix_census.NoOptimization())
    suffix_census.check_sources(binding.ROOT, args.source_commit, args.source_sha)
    value = authenticate_inputs(args, source_policy(args, before), deadline, before)
    raw = binding.canonical(value)+b'\n'
    binding.require(len(raw) <= MAX_BYTES, 'bootstrap metadata byte cap')
    from .runtime import _exclusive_json
    def publication_check():
        before()
        suffix_census.check_sources(binding.ROOT, args.source_commit, args.source_sha)
    _exclusive_json(args.output, value, MAX_BYTES, before_publish=publication_check)
    print(binding.canonical(dict(bootstrap=str(args.output), **binding.pin(args.output),
        execution_started=False, numerical_acceptance=False)).decode())


if __name__ == '__main__':
    main()
