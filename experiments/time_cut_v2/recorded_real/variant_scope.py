"""Explicit C01 variant boundaries; no flag or count grants execution authority."""
from . import plan as binding

D0_PLAN_SCHEMA = 'hiroute-recorded-real-plan-v2'
D1_PLAN_SCHEMA = 'hiroute-recorded-real-plan-v1'
D0 = 'C01::HIER::D-off'
REPRESENTATION = 'exact-adjacent-cut-coalescing-v1'


def validate_variant(value):
    binding.require(type(value) is dict and type(value.get('dominance')) is bool,
                    'exact boolean dominance required')
    schema = value.get('schema')
    if schema == D1_PLAN_SCHEMA:
        binding.require(value['dominance'] is True and 'variant_id' not in value,
                        'v1 remains D1-only')
    else:
        binding.require(schema == D0_PLAN_SCHEMA and value['dominance'] is False and
                        value.get('variant_id') == D0 and value.get('state_id') == 'C01',
                        'v2 admits only explicit C01 HIER D0')
    binding.require(value.get('representation') == REPRESENTATION and
                    value.get('external_incumbent') is None,
                    'fixed representation and unseeded search required')
    return schema == D0_PLAN_SCHEMA


def physical_scope(value):
    d0 = validate_variant(value)
    binding.require(all(type(value.get(key)) is int for key in ('H_ref', 'sites', 'regions')) and
                    (value['state_id'], value['pool_id'], value['H_ref'], value['sites'], value['regions']) ==
                    ('C01', 'OD00_energy_only', 4, 8, 2047), 'fixed C01 physical population required')
    return d0


def with_variant(commitment, anchors):
    """Only cold-admitted D0 replay anchors add a new population identity."""
    if 'variant_id' not in anchors:
        return commitment
    binding.require(anchors['variant_id'] == D0 and anchors.get('dominance') is False and
                    anchors.get('representation') == REPRESENTATION,
                    'D0 completed replay variant changed')
    result = dict(commitment, variant_id=D0, dominance=False, representation=REPRESENTATION)
    result['population_freeze_sha256'] = binding.digest(result)
    return result


def is_d0_population(commitment):
    if 'variant_id' not in commitment:
        binding.require(not any(key in commitment for key in
            ('dominance', 'representation', 'population_freeze_sha256')), 'partial variant population identity')
        return False
    expected = dict(commitment)
    freeze = expected.pop('population_freeze_sha256', None)
    binding.require(expected.get('variant_id') == D0 and expected.get('dominance') is False and
                    expected.get('representation') == REPRESENTATION and
                    expected.get('completed_replay', {}).get('variant_id') == D0 and
                    expected['completed_replay'].get('dominance') is False and
                    expected['completed_replay'].get('representation') == REPRESENTATION and
                    freeze == binding.digest(expected), 'D0 population freeze changed')
    return True


def population_scope(catalogue, commitment):
    """D1 preserves its exact constants; D0 uses its own authenticated freeze."""
    d0 = is_d0_population(commitment)
    binding.require(type(catalogue['block_size']) is int and catalogue['block_size'] == 256,
                    'canonical 256-model blocks required')
    fields = ('unique_logical_models', 'queries', 'original_model_occurrences', 'empty_action_queries')
    binding.require(all(type(commitment[k]) is int and commitment[k] >= 0 for k in fields),
                    'exact nonnegative population counts required')
    binding.require(type(catalogue['total_models']) is int and
                    catalogue['total_models'] == commitment['unique_logical_models'] and
                    binding.digest(catalogue) == commitment['block_plan_sha256'],
                    'catalogue differs from frozen population')
    if not d0:
        binding.require([catalogue['total_models'], len(catalogue['blocks']),
            *[commitment[k] for k in fields]] == [695712, 2718, 695712, 12172, 7652832, 9666],
            'fixed C01 population changed')
    return d0
