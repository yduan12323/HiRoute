"""Exact convex physical suffix replay, independent of LP models and solvers.

The caller supplies the *original* checked prefix family and an explicit legal
suffix word.  Only the reviewed family checker and Python's standard library
are imported.  This module checks realizability and the requested numerical
contract, not optimality or enumeration completeness; the certificate checker
must derive the result contract and bind the original family and legal word.
A valid physical witness need not reproduce a particular certified LP point.
This primitive replay does not take a band assignment; convex_evidence adds
closed arrival-band membership for composed regime and query-slot claims.
"""
from fractions import Fraction as F
from functools import wraps
import hashlib
import json

from validation.family5 import CheckedBundle, VerificationError, check_receipt


_EVENT_FIELDS = {
    'effect', 'site', 'arrival_time', 'departure_time',
    'arrival_energy', 'departure_energy',
}
_WITNESS_FIELDS = {'time', 'energy', 'rho', 'pi', 'state', 'events'}


def _require(condition, reason):
    if not condition:
        raise VerificationError(reason)


def _guard(function):
    @wraps(function)
    def guarded(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (KeyError, TypeError, IndexError, AttributeError, RecursionError) as exc:
            raise VerificationError('malformed_suffix_witness: ' + type(exc).__name__) from exc
    return guarded


def _wire_equal(a, b):
    """Recursive JSON equality: True is never 1 and an int is never a float."""
    if type(a) is not type(b):
        return False
    if type(a) is dict:
        return a.keys() == b.keys() and all(_wire_equal(a[k], b[k]) for k in a)
    if type(a) is list:
        return len(a) == len(b) and all(_wire_equal(x, y) for x, y in zip(a, b))
    return type(a) in (str, int, float, bool, type(None)) and a == b


def _number(value):
    """Physical evidence uses canonical rational strings, never numeric aliases."""
    _require(type(value) is str, 'suffix_non_string_rational')
    try:
        result = F(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise VerificationError('suffix_invalid_rational') from exc
    _require(str(result) == value, 'suffix_noncanonical_rational')
    return result


def _event(effect, site, t, u, x, y):
    return dict(effect=effect, site=site, arrival_time=str(t), departure_time=str(u),
                arrival_energy=str(x), departure_energy=str(y))


def _validate_event(event):
    _require(type(event) is dict and event.keys() == _EVENT_FIELDS,
             'suffix_invalid_event_fields')
    _require(type(event['effect']) is str and type(event['site']) is str,
             'suffix_invalid_event_identity')
    for name in _EVENT_FIELDS - {'effect', 'site'}:
        _number(event[name])


def _validate_contract(contract, J, Q, H, pi):
    _require(type(contract) is dict and type(contract.get('kind')) is str,
             'suffix_invalid_contract')
    kind = contract['kind']
    if kind == 'minimum':
        _require(contract.keys() == {'kind', 'J', 'Q_total', 'H', 'pi'},
                 'suffix_invalid_minimum_contract_fields')
        _require(J == _number(contract['J']) and Q == _number(contract['Q_total']),
                 'suffix_minimum_objective_mismatch')
        _require(type(contract['H']) is int and contract['H'] == H
                 and _wire_equal(contract['pi'], pi), 'suffix_minimum_tie_key_mismatch')
    elif kind == 'primary_approach':
        _require(contract.keys() == {'kind', 'J_inf', 'epsilon'},
                 'suffix_invalid_primary_approach_contract_fields')
        bound, epsilon = _number(contract['J_inf']), _number(contract['epsilon'])
        _require(epsilon > 0 and bound < J < bound + epsilon,
                 'suffix_primary_approach_contract')
    elif kind == 'secondary_approach':
        _require(contract.keys() == {'kind', 'J', 'Q_inf', 'epsilon'},
                 'suffix_invalid_secondary_approach_contract_fields')
        primary = _number(contract['J'])
        bound, epsilon = _number(contract['Q_inf']), _number(contract['epsilon'])
        _require(J == primary and epsilon > 0 and bound < Q < bound + epsilon,
                 'suffix_secondary_approach_contract')
    else:
        raise VerificationError('suffix_unknown_contract')
    return kind


def _check_curve(physics):
    """Validate original adjacent pieces separately from any LP assembler."""
    if not physics.curve:
        _require(all(effect == 'S' for effects in physics.sites.values()
                     for effect in effects), 'suffix_no_curve_with_charging_capability')
        return
    endpoint, old_value, old_slope = F(0), None, None
    for left, right, slope, intercept in physics.curve:
        _require(left == endpoint and right > left and slope > 0,
                 'suffix_invalid_convex_band_coverage')
        if old_value is not None:
            _require(slope*left+intercept == old_value, 'suffix_discontinuous_curve')
            _require(slope >= old_slope, 'suffix_nonconvex_curve')
        endpoint, old_value, old_slope = right, slope*right+intercept, slope
    _require(endpoint == physics.capacity, 'suffix_incomplete_curve_coverage')


def _primitive(physics, energy):
    # Evaluate the original band, not a model row or a maximum of support lines.
    values = [slope*energy+intercept for left, right, slope, intercept in physics.curve
              if left <= energy <= right]
    _require(bool(values) and all(value == values[0] for value in values),
             'suffix_energy_outside_original_curve')
    return values[0]


@_guard
def verify_witness(ctx, family_id, word, evidence, contract):
    """Replay an original prefix plus C/S/CS suffix and return its exact audit.

    ``evidence`` has exactly ``prefix``, ``suffix_events`` and ``witness``.
    ``prefix`` is the {witness, receipt} returned by family5.reconstruct.  Its
    receipt is checked against the caller's original family, including all
    recursive budget annotations.  A suffix has a selected-leg D event and a
    stop event per word pair, then a terminal D event, including self legs.

    Completion budgets do not create waiting: all events replay from the
    prefix's actual completion and use exact earliest/max schedule semantics.
    The returned key is present only for a satisfied ``minimum`` contract.
    Approaches expose their *actual* scalars, never a false optimum key.
    """
    _require(isinstance(ctx, CheckedBundle), 'suffix_requires_CheckedBundle')
    _require(type(family_id) is str and family_id in ctx._pieces,
             'suffix_original_family_missing')
    physics, piece = ctx._physics, ctx._pieces[family_id]
    _check_curve(physics)
    _require(type(word) is list and len(word) > 0, 'suffix_invalid_word')
    _require(piece.state[2] + len(word) <= physics.bound, 'suffix_stop_bound_exceeded')
    _require(piece.state[0] != physics.destination, 'suffix_departure_after_terminal_arrival')
    prefix_anchor = physics.anchors[piece.pi[-1][0]] if piece.pi else physics.origin
    _require(piece.state[0] == prefix_anchor, 'suffix_prefix_not_initial_or_post_stop_anchor')
    for action in word:
        _require(type(action) is list and len(action) == 2
                 and all(type(x) is str for x in action), 'suffix_invalid_word_action')
        site, effect = action
        _require(effect in ('C', 'S', 'CS') and effect in physics.sites.get(site, ()),
                 'suffix_unavailable_site_effect')
        _require(physics.anchors[site] != physics.destination, 'suffix_stop_at_destination')
        _require(effect == 'S' or bool(physics.curve), 'suffix_charging_without_curve')

    _require(type(evidence) is dict
             and evidence.keys() == {'prefix', 'suffix_events', 'witness'},
             'suffix_invalid_evidence_fields')
    prefix = evidence['prefix']
    _require(type(prefix) is dict and prefix.keys() == {'witness', 'receipt'},
             'suffix_invalid_prefix_fields')
    receipt, previous = prefix['receipt'], prefix['witness']
    _require(type(receipt) is dict and type(previous) is dict
             and previous.keys() == _WITNESS_FIELDS, 'suffix_invalid_prefix_evidence')
    request = receipt['contract']
    _require(type(request) is dict and request.keys() == {'kind', 'energy', 'budget'}
             and request['kind'] == 'realize_le', 'suffix_prefix_requires_reconstruction_contract')
    energy_request, budget_request = _number(request['energy']), _number(request['budget'])
    check_receipt(ctx, family_id, previous, request, receipt, require_budgets=True)

    t, energy, rho = (_number(previous[k]) for k in ('time', 'energy', 'rho'))
    _require(energy == energy_request and t <= budget_request, 'suffix_prefix_request_mismatch')
    pi = [list(action) for action in piece.pi]
    source, remaining, H = piece.state
    events = evidence['suffix_events']
    _require(type(events) is list and len(events) == 2 * len(word) + 1,
             'suffix_event_count')
    for event in events:
        _validate_event(event)
    actual_events, selected_legs, charges = [], [], []

    def drive(target, index, terminal=False):
        nonlocal t, energy, rho, source
        _require(source != physics.destination or target == physics.destination,
                 'suffix_departure_after_terminal_arrival')
        leg = physics.legs.get((source, target))
        _require(leg is not None, 'suffix_unreachable_selected_leg')
        dt, consumption, path, ids = leg
        next_energy = energy - consumption
        floor = physics.reserve if terminal else physics.floor
        _require(floor <= next_energy <= physics.capacity, 'suffix_drive_inventory_bounds')
        expected = _event('D', target, t, t + dt, energy, next_energy)
        _require(_wire_equal(events[index], expected), 'suffix_selected_drive_event_mismatch')
        actual_events.append(expected)
        selected_legs.append(dict(source=source, target=target, time=str(dt),
                                  consumption=str(consumption), path=list(path), edge_ids=list(ids)))
        t, energy, rho, source = t + dt, next_energy, rho + consumption, target

    for i, (site, effect) in enumerate(word):
        anchor = physics.anchors[site]
        drive(anchor, 2 * i)
        next_energy = _number(events[2 * i + 1]['departure_energy'])
        q = next_energy - energy
        _require(physics.floor <= energy <= next_energy <= physics.capacity,
                 'suffix_stop_inventory_bounds')
        if effect == 'S':
            _require(q == 0, 'suffix_service_changes_inventory')
        else:
            _require(q > 0, 'suffix_strict_charge_required')
        start = t + physics.overhead
        duration = F(0) if effect == 'S' else (_primitive(physics, next_energy)
                                                   - _primitive(physics, energy))
        completion = start + duration
        if effect in ('S', 'CS'):
            _require(remaining == 1 and physics.schedule is not None,
                     'suffix_invalid_service_state')
            release, deadline, duration = physics.schedule
            service_start = max(release, start)
            _require(service_start <= deadline, 'suffix_service_deadline')
            completion = max(completion, service_start + duration)
            remaining = 0
        expected = _event(effect, site, t, completion, energy, next_energy)
        _require(_wire_equal(events[2 * i + 1], expected), 'suffix_stop_event_mismatch')
        actual_events.append(expected)
        charges.append(str(q))
        pi.append([site, effect])
        H += 1
        t, energy, source = completion, next_energy, anchor
    _require(remaining == 0, 'suffix_terminal_unfulfilled_schedule')
    drive(physics.destination, 2 * len(word), terminal=True)
    expected = dict(time=str(t), energy=str(energy), rho=str(rho), pi=pi,
                    state=[physics.destination, remaining, H],
                    events=previous['events'] + actual_events)
    _require(_wire_equal(evidence['witness'], expected), 'suffix_full_witness_mismatch')
    J = t - physics.start + F(physics.case['lambda_stop_s']) * H
    Q = energy + rho
    _require(Q == energy_request + piece.rho + sum(map(F, charges)),
             'suffix_total_charge_accounting')
    kind = _validate_contract(contract, J, Q, H, pi)
    audit = dict(kind=kind, J=str(J), Q_total=str(Q), H=H, pi=pi,
                 prefix=dict(energy=str(energy_request), budget=str(budget_request),
                             time=previous['time']), charges=charges,
                 selected_legs=selected_legs,
                 witness_sha256=hashlib.sha256(json.dumps(expected, sort_keys=True,
                    separators=(',', ':'), ensure_ascii=True).encode()).hexdigest())
    if kind == 'minimum':
        audit['key'] = [str(J), str(Q), H, pi]
    return audit
