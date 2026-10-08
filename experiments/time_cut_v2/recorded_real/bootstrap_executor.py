"""Explicit reviewed executor bindings for an immutable D0 bootstrap.

The version-one source policy stays unchanged. Version two may approve an
exact bootstrap/population for another reviewed execution checkpoint; it never
replaces authentication of the historical bootstrap or its upstream returns.
"""
import hashlib

from . import plan as binding

POLICY_V1 = 'hiroute-reviewed-window-sources-v1'
POLICY_V2 = 'hiroute-reviewed-window-sources-v2'
BINDING_SCHEMA = 'hiroute-d0-bootstrap-executor-binding-v1'
MAX_BINDINGS = 16
BINDING_FIELDS = frozenset(('schema', 'bootstrap_sha256', 'bootstrap_source_commit',
    'bootstrap_source_sha256', 'executor_source_commit', 'executor_source_sha256',
    'population_sha256', 'block_plan_sha256', 'variant_id'))


def _hex(value, length):
    binding.require(type(value) is str and len(value) == length and
                    all(char in '0123456789abcdef' for char in value),
                    'invalid reviewed source identity')


def policy_sources(policy):
    """Validate the complete versioned policy, without broadening its allowlist."""
    binding.require(type(policy) is dict, 'reviewed source-policy schema required')
    version = policy.get('schema')
    fields = {'schema', 'reviewed_sources'}
    if version == POLICY_V2:
        fields.add('bootstrap_executor_bindings')
    binding.require(version in (POLICY_V1, POLICY_V2) and set(policy) == fields and
                    type(policy['reviewed_sources']) is dict,
                    'reviewed source-policy schema required')
    sources = policy['reviewed_sources']
    for commit, inventory in sources.items():
        _hex(commit, 40); _hex(inventory, 64)
    if version == POLICY_V2:
        rows = policy['bootstrap_executor_bindings']
        binding.require(type(rows) is list and 0 < len(rows) <= MAX_BINDINGS,
                        'bounded explicit bootstrap executor bindings required')
        seen = set()
        for row in rows:
            binding.require(type(row) is dict and set(row) == BINDING_FIELDS and
                            row['schema'] == BINDING_SCHEMA and
                            row['variant_id'] == 'C01::HIER::D-off',
                            'strict D0 bootstrap executor binding required')
            for key in BINDING_FIELDS - {'schema', 'variant_id'}:
                _hex(row[key], 40 if key.endswith('_commit') else 64)
            for prefix in ('bootstrap', 'executor'):
                binding.require(sources.get(row[prefix+'_source_commit']) == row[prefix+'_source_sha256'],
                                'bootstrap executor binding is outside reviewed sources')
            binding.require(row['bootstrap_source_commit'] != row['executor_source_commit'],
                            'executor binding requires distinct reviewed checkpoints')
            key = (row['bootstrap_sha256'], row['executor_source_commit'])
            binding.require(key not in seen, 'duplicate or ambiguous bootstrap executor binding')
            seen.add(key)
    return sources


def validate_pinned_policy(policy, expected_sha):
    binding.require(hashlib.sha256(binding.canonical(policy)+b'\n').hexdigest() == expected_sha,
                    'source policy must use canonical JSON with one final newline')
    return policy_sources(policy)


def admit_executor(args, authenticated_bootstrap, reviewed_sources, cache):
    """Bind the actual new executor only after complete frozen-bootstrap admission."""
    policy = cache.read(args.source_policy, args.source_policy_sha, 65536)
    sources = validate_pinned_policy(policy, args.source_policy_sha)
    binding.require(policy['schema'] == POLICY_V2,
                    'new bootstrap executor requires an explicit version-two source policy')
    for commit, inventory in sources.items():
        binding.require(reviewed_sources.get(commit) == inventory,
                        'executor source policy is outside the independent reviewed allowlist')
    population = authenticated_bootstrap['population']
    from .variant_scope import is_d0_population
    binding.require(is_d0_population(population), 'executor mapping is D0-only')
    expected = dict(schema=BINDING_SCHEMA, bootstrap_sha256=args.bootstrap_sha,
        bootstrap_source_commit=authenticated_bootstrap['source_commit'],
        bootstrap_source_sha256=authenticated_bootstrap['source_sha256'],
        executor_source_commit=args.source_commit, executor_source_sha256=args.source_sha,
        population_sha256=binding.digest(population),
        block_plan_sha256=population['block_plan_sha256'], variant_id=population['variant_id'])
    matches = [row for row in policy['bootstrap_executor_bindings']
               if row['bootstrap_sha256'] == args.bootstrap_sha and
               row['executor_source_commit'] == args.source_commit]
    binding.require(len(matches) == 1, 'exact reviewed bootstrap executor binding required')
    binding.require(binding.canonical(matches[0]) == binding.canonical(expected),
                    'bootstrap executor binding changed source, variant or population')
    return expected
