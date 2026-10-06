"""Optimizer-free reconstruction of the restricted suffix LP semantics.

This module is intentionally separate from the candidate model builder.  Its
only non-stdlib dependency is the already checked, immutable physical family
bundle.  Recorded LP matrices are never an input to semantic construction.
"""
from fractions import Fraction as F
from functools import wraps
import json

from validation.family5 import CheckedBundle, VerificationError


class SuffixVerificationError(VerificationError):
    """Unsupported semantics, malformed evidence, or an invalid certificate."""


def require(condition, reason):
    if not condition:
        raise SuffixVerificationError(reason)


def api(function):
    @wraps(function)
    def checked(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except SuffixVerificationError:
            raise
        except (KeyError, TypeError, ValueError, IndexError, AttributeError,
                ZeroDivisionError, RecursionError) as exc:
            raise SuffixVerificationError(
                f'malformed_suffix_evidence: {type(exc).__name__}: {exc}') from exc
    return checked


def exact_json(value):
    """Validate before detaching; do not normalize bool/int/float aliases."""
    if type(value) is dict:
        require(all(type(key) is str for key in value), 'non_string_json_key')
        for child in value.values():
            exact_json(child)
    elif type(value) is list:
        for child in value:
            exact_json(child)
    else:
        require(type(value) in (str, int, bool, type(None)), 'non_exact_json_type')


def wire_equal(left, right):
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return left.keys() == right.keys() and all(wire_equal(left[k], right[k]) for k in left)
    if type(left) is list:
        return len(left) == len(right) and all(wire_equal(a, b) for a, b in zip(left, right))
    return type(left) in (str, int, bool, type(None)) and left == right


def same(left, right, reason):
    require(wire_equal(left, right), reason)


def rational(value):
    require(type(value) is str, 'non_string_rational')
    number = F(value)
    require(str(number) == value, 'noncanonical_rational')
    return number


def _context(ctx, family_id):
    require(type(ctx) is CheckedBundle, 'requires_trusted_CheckedBundle')
    require(type(family_id) is str and family_id in ctx._pieces, 'unknown_original_family')
    ph, p = ctx._physics, ctx._pieces[family_id]
    require(len(ph.curve) == 1, 'requires_one_affine_charging_segment')
    lo, hi, slope, _ = ph.curve[0]
    require(lo == 0 and hi == ph.capacity and slope > 0, 'unsupported_charging_segment')
    require(p.state[0] != ph.destination, 'suffix_after_terminal_arrival')
    expected_anchor = ph.origin if p.state[2] == 0 else ph.anchors[p.pi[-1][0]]
    require(p.state[0] == expected_anchor, 'requires_origin_or_retagged_post_stop_prefix')
    return ph, p


def _action(ph, action, remaining):
    require(type(action) is list and len(action) == 2, 'invalid_suffix_action')
    site, effect = action
    require(type(site) is str and type(effect) is str, 'invalid_suffix_action_type')
    require(site in ph.sites and effect in ph.sites[site], 'unavailable_suffix_effect')
    require(ph.anchors[site] != ph.destination, 'suffix_stop_at_destination')
    require(effect in ('C', 'S', 'CS'), 'unsupported_suffix_effect')
    if effect != 'C':
        require(remaining == 1 and ph.schedule is not None, 'illegal_suffix_service_state')
        remaining = 0
    return remaining


@api
def enumerate_words(ctx, family_id, first_actions):
    """All finite legal terminal words; graph-invalid words are retained."""
    ph, p = _context(ctx, family_id)
    exact_json(first_actions)
    require(type(first_actions) is list, 'first_actions_not_list')
    require(len(first_actions) == len({tuple(x) for x in first_actions}), 'duplicate_first_action')
    limit = ph.bound-p.state[2]
    require(limit > 0, 'no_remaining_suffix_stops')
    for action in first_actions:
        _action(ph, action, p.state[1])
    answer = []

    def visit(word, remaining):
        if not remaining:
            answer.append([list(x) for x in word])
        if len(word) == limit:
            return
        actions = sorted({(site, effect) for site, effects in ph.sites.items()
                          if ph.anchors[site] != ph.destination for effect in effects
                          if effect == 'C' or remaining})
        for action in actions:
            updated = _action(ph, list(action), remaining)
            visit(word+[action], updated)

    for action in first_actions:
        visit([tuple(action)], _action(ph, action, p.state[1]))
    return answer


@api
def build_model(ctx, family_id, word):
    """Regenerate ordered rows from original checked prefix and explicit word."""
    ph, prefix = _context(ctx, family_id)
    exact_json(word)
    require(type(word) is list and 0 < len(word) <= ph.bound-prefix.state[2], 'suffix_stop_bound')
    remaining = prefix.state[1]
    for action in word:
        remaining = _action(ph, action, remaining)
    require(remaining == 0, 'terminal_unfulfilled_service')
    word = json.loads(json.dumps(word))
    result = dict(schema='family5-suffix-model-v1', family_id=family_id, word=word,
                  case_sha256=ctx.summary['case_sha256'],
                  family_bundle_sha256=ctx.summary['bundle_sha256'],
                  H=prefix.state[2]+len(word), pi=[list(x) for x in prefix.pi]+word,
                  exclusion=None, lp=None)
    source = prefix.state[0]
    legs = []
    for i, target in enumerate([ph.anchors[site] for site, _ in word]+[ph.destination]):
        leg = ph.legs.get((source, target))
        if leg is None:
            result['exclusion'] = dict(kind='unreachable_selected_leg', leg_index=i,
                                       source=source, target=target)
            return result
        legs.append(leg)
        source = target

    count = len(word)
    variables = ['E_prefix', 'T_prefix']
    for i in range(count):
        variables.extend([f'q_{i}', f'T_{i+1}'])
    width = len(variables)
    rows = []

    def row(label, terms, rhs, strict=False):
        coefficients = [F(0)]*width
        for index, value in terms:
            coefficients[index] += value
        rows.append(dict(label=label, coefficients=list(map(str, coefficients)),
                         rhs=str(F(rhs)), strict=strict))

    row('prefix_energy_lower', [(0, -1)], -prefix.lo, not prefix.lc)
    row('prefix_energy_upper', [(0, 1)], prefix.hi, not prefix.rc)
    row('prefix_time', [(0, prefix.m), (1, -1)], -prefix.b, not prefix.chi)
    consumption = F(0)
    charge_indices = []
    slope = ph.curve[0][2]
    for i, (_, effect) in enumerate(word):
        duration, energy = legs[i][:2]
        consumption += energy
        charge, previous, finish = 2+2*i, 1+2*i, 3+2*i
        row(f'arrival_floor:{i}', [(0, -1)]+[(j, -1) for j in charge_indices],
            -ph.floor-consumption)
        charge_indices.append(charge)
        row(f'departure_capacity:{i}', [(0, 1)]+[(j, 1) for j in charge_indices],
            ph.capacity+consumption)
        if effect == 'S':
            row(f'service_charge_zero_upper:{i}', [(charge, 1)], 0)
            row(f'service_charge_zero_lower:{i}', [(charge, -1)], 0)
        else:
            row(f'charge_positive:{i}', [(charge, -1)], 0, True)
            row(f'charge_completion:{i}', [(previous, 1), (finish, -1), (charge, slope)],
                -duration-ph.overhead)
        if effect != 'C':
            a, b, service_duration = ph.schedule
            row(f'service_window_nonempty:{i}', [], b-a)
            row(f'latest_service_start:{i}', [(previous, 1)], b-duration-ph.overhead)
            row(f'service_release_completion:{i}', [(finish, -1)], -a-service_duration)
            row(f'service_own_completion:{i}', [(previous, 1), (finish, -1)],
                -duration-ph.overhead-service_duration)
    row('terminal_reserve', [(0, -1)]+[(j, -1) for j in charge_indices],
        -ph.reserve-consumption-legs[-1][1])
    j_coefficients, q_coefficients = [F(0)]*width, [F(0)]*width
    j_coefficients[-1] = F(1)
    q_coefficients[0] = F(1)
    for index in charge_indices:
        q_coefficients[index] = F(1)
    result['lp'] = dict(variables=variables, rows=rows,
        J=dict(coefficients=list(map(str, j_coefficients)),
               constant=str(legs[-1][0]-ph.start+F(ph.case['lambda_stop_s'])*result['H'])),
        Q=dict(coefficients=list(map(str, q_coefficients)), constant=str(prefix.rho)))
    return result


def closed_task(model, objective, faces=()):
    """Build an ordinary LP task, retaining all original rows in order."""
    lp = model['lp']
    require(objective in ('J', 'Q'), 'invalid_suffix_objective')
    return dict(c=list(lp[objective]['coefficients']),
                A=[list(row['coefficients']) for row in lp['rows']],
                b=[row['rhs'] for row in lp['rows']],
                equalities=[[list(row), value] for row, value in faces])


def strict_task(model, faces=()):
    """Common margin on original strict rows only; there is no charge quantum."""
    lp = model['lp']
    width = len(lp['variables'])
    return dict(c=['0']*width+['-1'],
                A=[list(row['coefficients'])+['1' if row['strict'] else '0'] for row in lp['rows']]
                  +[['0']*width+['-1'], ['0']*width+['1']],
                b=[row['rhs'] for row in lp['rows']]+['0', '1'],
                equalities=[[list(row)+['0'], value] for row, value in faces])
