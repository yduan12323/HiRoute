"""Targeted read-only A dominance replay under retained B-frozen source."""
import hashlib
import json
import resource
import signal
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STAGE = ROOT / 'a_trace_stage'
A = STAGE / 'results/milestone_5_coalescing_prototype/frozen_A'
TRACE = STAGE / 'results/milestone_5_acceptance_b64/acceptance_populations/bound_audit/production_trace_v1'
B = ROOT/'ab_evidence_tree/results/milestone_5_acceptance_b64/acceptance_populations/stage_b/cases.json'
sys.path.insert(0, str(TRACE))
import trace_runner as runner
from traced_timecut5 import hierarchy, pwa, probe
from frozen_reference5 import lp, solver

# macOS rejects RLIMIT_AS here; the retained 56-trace server replay enforced
# 2 GiB. This local follow-up observes RSS and fails if it exceeds that cap.
signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('180 second cap')))
signal.alarm(180)
start = time.monotonic()
runner.verify_freeze()
def forbidden(*args, **kwargs):
    raise RuntimeError('NoOptimization: LP entrypoint called')
lp.linprog = lp.exact_lp = solver.exact_lp = forbidden
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

original = hierarchy.reduce_frontier
counts = Counter()
current = None
rows = []

def checked_reduce(inputs):
    inputs = tuple(inputs)
    output = original(inputs)
    counts['reduction_calls'] += 1
    if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss > 2*1024**3:
        raise MemoryError('2 GiB cap exceeded')
    counts['input_pieces'] += len(inputs)
    counts['output_pieces'] += len(output)
    cells = pwa._arrangement(inputs)
    cell_proofs=[]
    for cell in cells:
        energy = pwa._point(cell)
        before = [p.at(energy) for p in inputs if p.domain.contains(energy)]
        after = [p.at(energy) for p in output if p.domain.contains(energy)]
        if before and not after:
            raise AssertionError('Reduction removed all continuations')
        mapping=[]
        for candidate in before:
            winner_index=next((i for i,winner in enumerate(after) if probe.dominates(winner,candidate)),None)
            if winner_index is None:
                raise AssertionError(('Uncovered input cut', current, energy, candidate))
            mapping.append(winner_index)
            counts['pointwise_covered_inputs'] += 1
        counts['arrangement_cells'] += 1
        cell_proofs.append(dict(energy=str(energy), input_to_output=mapping,
                                input_count=len(before), output_count=len(after)))
    rows.append(dict(case_id=current, call=counts['reduction_calls'], input_pieces=len(inputs),
                     output_pieces=len(output), arrangement_cells=len(cells),
                     pointwise_covered=True, cell_proofs=cell_proofs))
    return output

hierarchy.reduce_frontier = checked_reduce
cases = sum((json.loads((A/n).read_text()) for n in
             ('physical_cases_h4.json', 'physical_supplement.json', 'physical_merge_supplement.json')), [])
cases += json.loads(B.read_text())
for case in cases:
    current = case['case_id']
    result = hierarchy.solve_hierarchical(case, dominance=True)
    frozen = runner.frozen(case, dominance=True)
    if runner.canonical(__import__('dataclasses').asdict(result)) != runner.canonical(__import__('dataclasses').asdict(frozen)):
        raise AssertionError(('Frozen output mismatch', current))
    counts['cases'] += 1

receipt = dict(schema='hiroute-stage-ab-targeted-dominance-observation-v1', status='passed',
               scope='28 retained A and 64 retained B cases, HIER D-on, replayed under B frozen 579c6db source; not original A producer',
               source_manifest_sha256=sha(TRACE/'trace_freeze.json'),
               original_A_results_sha256=sha(A/'FINAL_STAGE_A_RESULTS.json'),
               B_cases_sha256=sha(B),
               counts=dict(counts), rows=rows, optimizer_calls=0,
               elapsed_seconds=time.monotonic()-start,
               peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
target = ROOT/'ab_dominance_receipt_20261011.json'
with target.open('x') as f:
    json.dump(receipt, f, sort_keys=True, indent=2)
    f.write('\n')
print(json.dumps({k: receipt[k] for k in ('status','counts','optimizer_calls','elapsed_seconds','peak_rss_bytes')}, sort_keys=True))
