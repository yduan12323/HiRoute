# Independently replayed improvement on the frozen common-leg domain

## Result and scope

A separately admitted, solver-free verification completed on source
`c1751b55a145457c1cb1ee8abcf598518952f628`. Its candidate came from the
unchanged WD01/E18/schedule/N64 supported-disjunction query: 64 literal Sites,
78 actions, all 4,225 selected-leg pairs, and complete derived depth H20.
The original frozen input and physics were preserved.

The verified executable plan has five stops (four charging actions and one
service action), compared with the original incumbent's three stops. Its exact
primary objective is `44278258155161/962500000`, below the incumbent's
`4495362171241/96250000` by `675363557249/962500000`:
**701.6764231158442 objective seconds, or 1.502356276363285%.**
J includes stop penalties, so this is not a claim of that much travel-time saving.
Four returned charging actions do not prove four charges are necessary.

This is an attained feasible improvement, **not an optimum**, not a completed
lexicographic comparison, and not a performance benchmark. Exactness is
conditional on the supplied selected-leg table and physical contract; full
independent shortest-road selection certification remains absent.

## Evidence and chronology

- The earlier strict-bound diagnostic returned SAT and completed in 97.039582s.
  It saved no satisfying assignment; it did not certify an executable improvement.
- The subsequent extraction attempt returned SAT but hit its 120.034564s wall
  guard during extraction. It saved an unverified candidate, not an accepted
  witness. Its overall result remains UNKNOWN.
- First separate verification completed the exact helper but failed a consumer
  tuple/list comparison before final raw-path checking. It remains UNKNOWN.
- Corrected separate verification completed in **74.86032716697082s wall**,
  charged **87.714928000 CPU seconds including setup/closure**, peak tree RSS
  **368,918,528 bytes**, below its unchanged **2,195,587,072-byte** admission cap.
  No guard fired. It checked every original assertion, strict bound, midpoint
  support construction, exact physical replay, and all six returned-plan raw
  paths (4,359 edges), then source/input/origin identities and receipt hashes.
  Its own successful terminal is COMPLETE. Neither earlier UNKNOWN is rewritten.

Solver, optimizer, tactic and SMT-parser entry points were disabled in this
separate verification. The original candidate assignment is not trusted merely
because a solver produced it. Typed import requires a byte-identical regenerated
original DAG audit before exact assertion evaluation. Canonical JSON receipt
comparison fixes the later list/tuple boundary without weakening tamper checks.

Immutable terminal SHA256:
`7eddad1bc39c03853523b6b0bc76a96bc10886e1afbf84293efc4bc9caa779f3`.
Verified witness file SHA256:
`9749395544f80891035e6779d767870bf440f151e8dd2a851779c0e5a7e22531`.
Frozen original audit SHA256:
`c4bca134ea16eb12cc3717ae479b3aa825f0f97bcc4cca81be4fb335f6121b61`.
The underlying graph, tables, complete audits, candidate and run receipts remain
outside Git; these hashes are identity references, not publicly downloadable proof.

Research ledger at this completed checkpoint: **20,543.687297319 / 28,800 CPU
seconds**, remaining **8,256.312702681**. Failed stages remain charged. Ordinary
software CI is separately bounded and is not a new numerical research row.

## Code and validation

This delivery adds exact finite lookup with total defaults, identical-branch
folding, complete DAG audits, serialization-only caching, fresh incumbent
certificates, strict-bound decisions, exact witness extraction, separately bound
candidate import, and versioned final acceptance. Production search code under
src/ is unchanged. Optional experimental profiles do not become production
solver defaults. No cached SAT/model result is used as a new proof.

Incremental development was independently reviewed. The final acceptance stage
passed eight normal/eight optimized solver-free test methods (five finalizer,
three import), plus 839 root and eight explicit collection entries. Earlier
semantic/support/attainment regressions retain their own source-bound receipts;
this is not a claim of one combined final-source full research regression.
Publication CI runs all relevant tiny groups sequentially in normal/-OO modes,
retaining the existing 15-CPU-second child and 180-CPU-second cumulative limits.
The first publication CI stopped at the child CPU cap in the DAG-audit group;
its 114.313584 inclusive reserved CPU accounting remains in GitHub run
42450523469. Test-only deduplication removes two repeated finite-baseline sweeps
already covered by finite-vs-original tests, while retaining every actual
DAG-audit/certificate solve, fixture, analytic expectation and path assertion.
Imported TestCase rediscovery is removed; its original test module stays selected.
No failed run is called successful and no research/resource limit is increased.
The next run, 42450975980, stopped on an exact-deadline fixture assertion
(78.889895 inclusive reserved CPU seconds), before the deduplicated sweeps.
The fixture now uses exactly representable mocked clock values, avoiding
floating-point cancellation at the boundary. Production deadlines are unchanged;
both failed receipts remain preserved, and runtime fit still requires passing CI.


The reviewed publication head passed all four PR checks before merge. Its physical
CI completed all 18 slots at 152.381247 inclusive reserved CPU seconds. Post-merge
run 42452363488 on the identical tree exhausted admission at 171.814933 seconds:
13 slots passed, five remained UNRUN. The higher-CPU-cost admission failure is preserved.
A further test-only deduplication retains every finite-mode fixture solve and
checks its analytic expectation; the independently retained shared-array sweep
and both support traps check the same expectations, preserving transitive parity.
No cap, production code, fixture or target-mode assertion is removed. Passing
within the envelope is not assumed from this change and requires new exact-head CI.


The follow-up run 42453164512 passed 16 of 18 command slots but could not admit
the next 16 CPU-second reservation: 166.311873 inclusive CPU seconds were already
charged/reserved. Both remaining slots stayed UNRUN. All failures are retained.
The next packaging revision combines three light module groups per mode, retaining
all modules, tests and actual mode solves while removing four interpreter launches
and their per-child accounting overhead. Normal and -OO both remain, with unchanged
15 CPU child caps, 16 CPU reservations and 180 CPU total. Larger groups are ordered
last to reduce unused final-reservation space, not to claim lower computation.
The denominator becomes 14 commands; successful fit and cross-module isolation
still require exact-head CI and are not guaranteed by this packaging change.

## Taskbook gaps and next decision

M5-D is not completed by this result. Remaining gaps include:

1. Full-scale independent primary optimality and later Q/H/action-order attainment.
2. Independent complete road-selection certification for the common input.
3. Fair, preregistered FLAT/HIER paired performance and completion-rate evidence
   over the taskbook development denominator, with identical seeds/cache/settings.
4. Claims about necessary multiple charges, sequential-planning value, larger
   domains and generalizable speedups. A single five-stop witness supplies none.
5. Final holdout remains unapproved and unrun.

Recommended next step is a bounded **read-only comparison protocol audit**:
map the new feasible incumbent against the frozen FLAT/HIER seed and cost
contracts, identify which result states can be compared without changing the
question, and preregister any later one-shot bound test or paired experiment.
Do not quietly warm-start one method with this improved witness while retaining
an older seed for another. A new strict-bound SAT run could find another feasible
improvement but would not by itself close optimality or taskbook performance.
No new numerical experiment or holdout is launched by this delivery.
