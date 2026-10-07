"""Candidate v2 suffix models for continuous convex charging or no charging.

Every charging arrival band is enumerated. Departure charging time is the
maximum of all original affine support lines, represented by epigraph rows.
The reviewed affine v1 API and its wire format remain separate and unchanged.
"""
from fractions import Fraction as F
from itertools import product

from validation.family5 import CheckedBundle
from validation.family5.checker import require
from .model import plain, legal_words as _affine_legal_words


def checked_curve(ph):
    """Fail closed outside the explicitly proved physical law class."""
    curve = ph.curve
    if not curve:
        require(not any(set(effects) & {'C', 'CS'} for effects in ph.sites.values()),
                'no-curve physical case has charging capabilities')
        return curve
    require(all(len(segment) == 4 and segment[0] < segment[1] and segment[2] > 0
                for segment in curve), 'invalid positive charging segments')
    require(curve[0][0] == 0 and curve[-1][1] == ph.capacity,
            'charging curve must cover full capacity')
    for left, right in zip(curve, curve[1:]):
        require(left[1] == right[0], 'gapped or overlapping charging bands')
        require(left[2]*left[1]+left[3] == right[2]*right[0]+right[3],
                'discontinuous charging primitive')
        require(left[2] <= right[2], 'nonconvex charging primitive')
    return curve


def checked_word(ctx, family_id, word):
    require(type(ctx) is CheckedBundle, 'checked family bundle required')
    require(type(family_id) is str and family_id in ctx._pieces, 'unknown original prefix family')
    p, ph = ctx._pieces[family_id], ctx._physics
    checked_curve(ph)
    require(type(word) in (list, tuple) and 1 <= len(word) <= ph.bound-p.state[2],
            'invalid suffix stop count')
    require(p.state[0] != ph.destination, 'no continuation from terminal prefix')
    expected_anchor = ph.origin if p.state[2] == 0 else ph.anchors[p.pi[-1][0]]
    require(p.state[0] == expected_anchor, 'prefix must be initial or post-stop physical anchor')
    remaining, normalized = p.state[1], []
    for action in word:
        require(type(action) in (list, tuple) and len(action) == 2, 'invalid suffix action')
        site, effect = action
        require(type(site) is str and type(effect) is str and effect in ph.sites.get(site, ()),
                'unavailable suffix action')
        require(ph.anchors[site] != ph.destination, 'terminal Site action forbidden')
        require(effect in ('C', 'S', 'CS'), 'unsupported suffix action')
        if effect != 'S':
            require(bool(ph.curve), 'charging action requires original physical curve')
        if effect in ('S', 'CS'):
            require(remaining == 1 and ph.schedule is not None, 'service already fulfilled or missing')
            remaining = 0
        normalized.append((site, effect))
    require(remaining == 0, 'suffix has not fulfilled required service')
    return p, ph, tuple(normalized)


def legal_words(ctx, family_id, first_actions):
    require(type(ctx) is CheckedBundle, 'checked family bundle required')
    require(type(family_id) is str and family_id in ctx._pieces, 'unknown original prefix family')
    checked_curve(ctx._physics)
    words = _affine_legal_words(ctx, family_id, first_actions)
    for word in words:
        checked_word(ctx, family_id, word)
    return words


def _legs(prefix, ph, word):
    source, legs = prefix.state[0], []
    for index, target in enumerate([ph.anchors[site] for site, _ in word]+[ph.destination]):
        leg = ph.legs.get((source, target))
        if leg is None:
            return (), dict(kind='unreachable_selected_leg', leg_index=index,
                            source=source, target=target)
        legs.append(leg)
        source = target
    return legs, None


def band_assignments(ctx, family_id, word):
    """Complete ordered regimes; one graph exclusion per physical word."""
    prefix, ph, word = checked_word(ctx, family_id, word)
    _, exclusion = _legs(prefix, ph, word)
    if exclusion is not None:
        return (None,)
    return tuple(product(*(range(len(ph.curve)) if effect != 'S' else (None,)
                           for _, effect in word)))


def build_model(ctx, family_id, word, arrival_bands):
    """One explicit band assignment, with no LP execution or hidden pruning."""
    prefix, ph, word = checked_word(ctx, family_id, word)
    legs, exclusion = _legs(prefix, ph, word)
    if exclusion is not None:
        require(arrival_bands is None, 'graph exclusion must have null band assignment')
    else:
        require(type(arrival_bands) in (list, tuple) and len(arrival_bands) == len(word),
                'arrival bands must align with every suffix stop')
        for (_, effect), band in zip(word, arrival_bands):
            if effect == 'S':
                require(band is None, 'S has no charging band')
            else:
                require(type(band) is int and 0 <= band < len(ph.curve),
                        'invalid original arrival band')
    result = dict(schema='family5-suffix-model-v2', family_id=family_id, word=plain(word),
                  case_sha256=ctx.summary['case_sha256'],
                  family_bundle_sha256=ctx.summary['bundle_sha256'],
                  H=prefix.state[2]+len(word), pi=plain(prefix.pi+word),
                  arrival_bands=plain(arrival_bands), exclusion=exclusion, lp=None)
    if exclusion is not None:
        return result
    width = 2+2*len(word)
    names = ['E_prefix', 'T_prefix']
    for i in range(len(word)):
        names.extend((f'q_{i}', f'T_{i+1}'))
    rows = []

    def row(label, terms, rhs, strict=False):
        vector = [F(0)]*width
        for index, value in terms.items():
            vector[index] += F(value)
        rows.append(dict(label=label, coefficients=list(map(str, vector)),
                         rhs=str(F(rhs)), strict=strict))

    row('prefix_energy_lower', {0: -1}, -prefix.lo, not prefix.lc)
    row('prefix_energy_upper', {0: 1}, prefix.hi, not prefix.rc)
    row('prefix_time', {0: prefix.m, 1: -1}, -prefix.b, not prefix.chi)
    consumption, charges = F(0), []
    for i, ((_, effect), leg, band) in enumerate(zip(word, legs, arrival_bands)):
        duration, energy = leg[:2]
        consumption += energy
        qi, previous, ti = 2+2*i, 1+2*i, 3+2*i
        prior_charges = tuple(charges)
        row(f'arrival_floor:{i}', {0: -1, **{j: -1 for j in prior_charges}},
            -ph.floor-consumption)
        charges.append(qi)
        row(f'departure_capacity:{i}', {0: 1, **{j: 1 for j in charges}},
            ph.capacity+consumption)
        if effect != 'S':
            lo, hi, arrival_slope, arrival_intercept = ph.curve[band]
            row(f'arrival_band_lower:{i}', {0: -1, **{j: -1 for j in prior_charges}},
                -lo-consumption)
            row(f'arrival_band_upper:{i}', {0: 1, **{j: 1 for j in prior_charges}},
                hi+consumption)
            row(f'charge_positive:{i}', {qi: -1}, 0, True)
            for j, (_, _, slope, intercept) in enumerate(ph.curve):
                delta = slope-arrival_slope
                row(f'charge_completion:{i}:{j}',
                    {previous: 1, ti: -1, 0: delta, qi: slope,
                     **{q: delta for q in prior_charges}},
                    -duration-ph.overhead+delta*consumption+arrival_intercept-intercept)
        else:
            row(f'service_charge_zero_upper:{i}', {qi: 1}, 0)
            row(f'service_charge_zero_lower:{i}', {qi: -1}, 0)
        if effect in ('S', 'CS'):
            a, b, service_duration = ph.schedule
            row(f'service_window_nonempty:{i}', {}, b-a)
            row(f'latest_service_start:{i}', {previous: 1}, b-duration-ph.overhead)
            row(f'service_release_completion:{i}', {ti: -1}, -a-service_duration)
            row(f'service_own_completion:{i}', {previous: 1, ti: -1},
                -duration-ph.overhead-service_duration)
    row('terminal_reserve', {0: -1, **{j: -1 for j in charges}},
        -ph.reserve-consumption-legs[-1][1])
    J, Q = [F(0)]*width, [F(0)]*width
    J[-1], Q[0] = F(1), F(1)
    for qi in charges:
        Q[qi] = F(1)
    result['lp'] = dict(variables=names, rows=rows,
        J=dict(coefficients=list(map(str, J)),
               constant=str(legs[-1][0]-ph.start+F(ph.case['lambda_stop_s'])*result['H'])),
        Q=dict(coefficients=list(map(str, Q)), constant=str(prefix.rho)))
    return result


def build_models(ctx, family_id, word):
    return [build_model(ctx, family_id, word, bands)
            for bands in band_assignments(ctx, family_id, word)]


def query_models(checked_trace, query_seq):
    require(type(query_seq) is int, 'query occurrence must be an exact integer')
    matches = [q for q in checked_trace.export_queries() if q['query_seq'] == query_seq]
    require(len(matches) == 1, 'query occurrence missing or ambiguous')
    query, models = matches[0], []
    for family_id in query['family_ids']:
        for word in legal_words(checked_trace.bundle, family_id, query['actions']):
            models.extend(build_models(checked_trace.bundle, family_id, word))
    return query, models
