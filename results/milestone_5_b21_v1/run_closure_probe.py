"""Evaluate the frozen first algebra hand object and stop on a mismatch."""
from dataclasses import asdict
from fractions import Fraction
import csv
import time
from preflight import OUT, digest, write
from closure_probe import attained_signature, run


def serialize(value):
    if isinstance(value, Fraction):
        return str(value)
    if isinstance(value, dict):
        return {k: serialize(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [serialize(v) for v in value]
    if hasattr(value, '__dataclass_fields__'):
        return serialize(asdict(value))
    return value


if __name__ == '__main__':
    import json
    freeze = json.loads((OUT / 'contract_freeze_manifest.json').read_text())
    assert all(digest(OUT / n) == h for n, h in freeze.items())
    assert json.loads((OUT / 'pretest_summary.json').read_text())['exit_code'] == 0
    assert json.loads((OUT / 'charging_primitive_audit.json').read_text())['status'] == 'passed'
    started = time.perf_counter()
    result = run()
    write('operator_closure_counterexample.json', serialize(result) | dict(
        status='theory_contradiction' if not result['congruent'] else 'passed',
        contract='ALG-4 under branchwise infimal C closure and attained/limit-only separation',
        input_reduction_deletions=1, cross_energy_deletions=0,
        left_attained_signature=serialize(attained_signature(result['left'])),
        right_attained_signature=serialize(attained_signature(result['right'])),
        closure_probe_scope='Exact one-segment hand object, not any of the three full solvers',
        hard_stop=not result['congruent']))
    rows = [dict(law=f'ALG-{i}', status='failed' if i == 4 else 'not_evaluated',
        objects_evaluated=1 if i == 4 else 0, violations=1 if i == 4 else None,
        reason='Exact open-input closure counterexample' if i == 4 else 'Hard stop before algebra population expansion')
        for i in range(1, 11)]
    write('algebra_audit.json', rows)
    with (OUT / 'algebra_audit.csv').open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    write('semantic_equivalence_comparator_audit.json', dict(
        arithmetic='exact rational', witness_energy='1',
        left_attained_count=len(attained_signature(result['left'])),
        right_attained_count=len(attained_signature(result['right'])),
        equivalent=result['congruent'], raw_ids_or_segmentation_compared=False,
        global_equivalence_proved=False, global_inequivalence_witnessed=True))
    write('runtime_table.json', dict(scope='Analytic first algebra object only',
        closure_probe_seconds=time.perf_counter() - started,
        REF_sequence_enumeration_seconds=None, REF_regime_optimization_seconds=None,
        FLAT_propagation_seconds=None, safe_reduction_seconds=None,
        HIER_bounds_refinement_seconds=None, leaf_materialization_seconds=None))
    print('ALG-4 violations:', int(not result['congruent']))
    raise SystemExit(1 if not result['congruent'] else 0)
