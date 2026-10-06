"""Compose independently checked optima with their original-family witnesses.

A caller-selected numeric contract is not itself an optimality claim. Its
bounds/key must first match the independently derived regime or query result.
"""
from validation.family5.checker import require,wire_equal
from .checker import check_regime,check_query_ledger
from .witness_checker import verify_witness


def bind_contract(result,contract):
    require(type(contract) is dict,'missing physical result contract')
    status=result['status']
    if status=='attained_optimum':
        expected=dict(kind='minimum',J=result['J'],Q_total=result['Q_total'],H=result['H'],pi=result['site_action_tuple'])
    elif status=='primary_unattained':
        expected=dict(kind='primary_approach',J_inf=result['primary_infimum'],epsilon=contract.get('epsilon'))
    elif status=='secondary_unattained':
        expected=dict(kind='secondary_approach',J=result['J'],Q_inf=result['secondary_infimum'],epsilon=contract.get('epsilon'))
    else:raise ValueError('Empty family has no result witness')
    require(wire_equal(contract,expected),'physical contract differs from certified result')
    return expected


def check_result_witness(ctx,record,evidence,contract):
    result=check_regime(ctx,record);bind_contract(result,contract)
    return verify_witness(ctx,record['model']['family_id'],record['model']['word'],evidence,contract)


def check_query_witness(checked_trace,ledger,slot,evidence,contract):
    result=check_query_ledger(checked_trace,ledger)
    require(type(slot) is int and 0<=slot<len(ledger['models']),'invalid original query regime slot')
    record=ledger['models'][slot]
    require(wire_equal(record['result'],result),'physical witness regime does not attain/approach the query result')
    bind_contract(result,contract)
    return verify_witness(checked_trace.bundle,record['model']['family_id'],record['model']['word'],evidence,contract)
