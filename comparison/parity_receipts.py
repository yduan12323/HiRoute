"""Durable, fail-closed receipts for the small gate's Core parity calls."""
import json
import os
from pathlib import Path

METHODS = ('flat_bb_strong', 'scale')


def atomic_json(path, value):
    """A terminated writer leaves either the previous or the new valid JSON."""
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('w') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def run_parity(cases, rows, output, solve_core, normalize, *, case_sha256,
               independent_ok):
    """Record all slots before Core, and stop on the first error or mismatch.

    An uncatchable termination leaves the active slot ``running`` (uncertain),
    subsequent slots ``not_run``, and passed/finalized false. An exception is
    a failed gate, including SystemExit(0); it never becomes a successful CLI.
    Checkpoint I/O errors propagate rather than allowing an unaudited success.
    """
    if len(cases) != len(rows) or any(c['id'] != r['id'] for c, r in zip(cases, rows)):
        raise ValueError('case/independent receipt mismatch')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    receipt = output / 'results.json'
    if receipt.exists():
        raise FileExistsError('preserve existing parity receipt; use a fresh output directory')
    for row in rows:
        row['core'] = [dict(method=method, status='not_run') for method in METHODS]
    result = dict(schema='hiroute.compact_gate.v1', passed=False, finalized=False,
                  parity_complete=False, phase='core_parity_in_progress',
                  new_real_rows=0, case_sha256=case_sha256, rows=rows)

    def checkpoint(*, final=False, phase='core_parity_in_progress'):
        slots = [(r['id'], c) for r in rows for c in r['core']]
        result.update(finalized=final, phase=phase,
                      parity_complete=bool(slots) and all(
                          c['status'] in ('completed', 'mismatch') for _, c in slots),
                      remaining_unrun=[dict(case_id=i, method=c['method'])
                                       for i, c in slots if c['status'] == 'not_run'],
                      uncertain=[dict(case_id=i, method=c['method'])
                                 for i, c in slots if c['status'] == 'running'])
        result['passed'] = bool(final and independent_ok and slots and all(
            r.get('analytic_match') is True for r in rows) and all(
            c['status'] == 'completed' and c.get('match') is True for _, c in slots))
        atomic_json(receipt, result)

    checkpoint()
    if not independent_ok:
        checkpoint(final=True, phase='independent_failed')
        return result
    for case, row in zip(cases, rows):
        for slot in row['core']:
            slot['status'] = 'running'
            checkpoint()
            try:
                semantic = normalize(solve_core(case, slot['method']))
                slot.update(semantic=semantic, match=semantic == row['semantic'])
                slot['status'] = 'completed' if slot['match'] else 'mismatch'
            except BaseException as exc:
                slot.update(status='core_error' if isinstance(exc, Exception)
                            else 'core_interrupted', match=False,
                            error_type=type(exc).__name__, error=repr(exc))
                checkpoint(final=True, phase='core_parity_failed')
                return result
            checkpoint()
            if not slot['match']:
                checkpoint(final=True, phase='core_parity_failed')
                return result
    checkpoint(final=True, phase='core_parity_complete')
    return result
