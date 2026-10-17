# Cold development evidence, 2026-10-15

## Integrated change

Only the single-site seed generator in `src/timecut5/deployable.py` changes. It rejects ineligible effects, unreachable or below-floor inbound legs, and charge-only actions without headroom before requesting outbound routing. Proposal ordering, charge values and finite beam behavior are unchanged for valid deterministic routing sources. Errors from unused outbound routes are intentionally no longer encountered; errors from required routes remain fatal. Exact solver kernels are unchanged.

The regression fixture contains only the frozen original generator function, never a replacement solver. Eight tests include 2,304 finite full-stream comparisons, service at zero headroom, attained/unattained single-CS cases, invalid inputs and source-error boundaries. Run from the repository root:

    PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python tests/m5d_recovery/test_seed_short_circuit.py
    PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 python -OO tests/m5d_recovery/test_seed_short_circuit.py

## Observed DEV comparison

[Sanitized comparison](comparison.json) records the completed controlled observations. First independently verified feasible witness appeared at 252.787 to 74.967 seconds for FLAT and 253.685 to 75.229 seconds for HIER. First-proposal source searches fell from 128 to 29; the saved witness digest is identical in all four rows. These are sequential, single-case observations, not a general speedup claim. OS caches and run order were uncontrolled. Both optimized exact phases timed out after approximately 120 seconds at depth 1. No optimum, global lower bound, gap or hierarchy-equivalence result follows.

Only the first saved witness has independently replayable route evidence. Later sampled scalar improvements are diagnostics, not saved better routes. Full source/audit inventory hashes identify retained original evidence; private inventory paths and process metadata are deliberately not reproduced. This public projection supports consistency checks, not an independent rerun of private receipts.

## Experimental work not installed

The tiny cold-query handoff coordinator, the real-graph cold adapter and the later durable-incumbent integration remain isolated experimental prototypes. This release does not install a new cold-query API, production coordinator or durability hook. The tiny handoff uses synthetic-only admission and cooperative budgets, not hard OS containment. The real-graph adapter was used only in the scoped DEV observations above.

[Durability review](durability_review.json) covers 29 author and four independent tiny tests in each Python mode: independently replayed improvements are persisted before pruning, original seed/Hmax remain unchanged, and persistence errors propagate. It has no real-graph validation; the extra verifier and source hashing require separate resource admission. It was not present in either performance arm. There is no OPEN/frontier or completed-layer resume claim. [Tiny handoff review](tiny_handoff_review.json) records its separate local gate.
