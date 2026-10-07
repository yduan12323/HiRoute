"""Compose checked v2 optima with witnesses in the selected arrival bands.

The physical checker alone establishes original-family/word realizability.
Composition additionally checks the certified numerical contract and the closed
arrival-band membership of each charging stop, so a per-regime claim cannot be
supported by a valid physical witness from a different band assignment.
"""
from fractions import Fraction as F

from validation.family5.checker import require, wire_equal
from .convex_checker import check_regime, check_query_ledger
from .convex_witness_checker import verify_witness


def bind_contract(result, contract):
    require(type(contract) is dict, 'missing physical result contract')
    status = result['status']
    if status == 'attained_optimum':
        expected = dict(kind='minimum', J=result['J'], Q_total=result['Q_total'],
                        H=result['H'], pi=result['site_action_tuple'])
    elif status == 'primary_unattained':
        expected = dict(kind='primary_approach', J_inf=result['primary_infimum'],
                        epsilon=contract.get('epsilon'))
    elif status == 'secondary_unattained':
        expected = dict(kind='secondary_approach', J=result['J'], Q_inf=result['secondary_infimum'],
                        epsilon=contract.get('epsilon'))
    else:
        raise ValueError('Empty family has no result witness')
    require(wire_equal(contract, expected), 'physical contract differs from certified result')
    return expected


def _check_bands(ctx, model, evidence):
    """Run after semantic model checking and exact physical event replay."""
    for index, ((_, effect), band) in enumerate(zip(model['word'], model['arrival_bands'])):
        if effect == 'S':
            require(band is None, 'physical service has a charging band')
            continue
        arrival = F(evidence['suffix_events'][2*index+1]['arrival_energy'])
        lo, hi, _, _ = ctx._physics.curve[band]
        require(lo <= arrival <= hi, 'physical witness outside certified arrival band',
                stop_index=index, arrival_energy=str(arrival), arrival_band=band,
                band_domain=[str(lo), str(hi)])


def check_result_witness(ctx, record, evidence, contract):
    """Certify this regime's numerical contract and physical band membership."""
    result = check_regime(ctx, record)
    bind_contract(result, contract)
    model = record['model']
    audit = verify_witness(ctx, model['family_id'], model['word'], evidence, contract)
    _check_bands(ctx, model, evidence)
    return audit


def check_query_witness(checked_trace, ledger, slot, evidence, contract):
    """Certify the query contract through a member of the selected regime."""
    result = check_query_ledger(checked_trace, ledger)
    require(type(slot) is int and 0 <= slot < len(ledger['models']), 'invalid original query regime slot')
    record = ledger['models'][slot]
    require(wire_equal(record['result'], result),
            'physical witness regime does not attain/approach the query result')
    bind_contract(result, contract)
    model = record['model']
    audit = verify_witness(checked_trace.bundle, model['family_id'], model['word'], evidence, contract)
    _check_bands(checked_trace.bundle, model, evidence)
    return audit
