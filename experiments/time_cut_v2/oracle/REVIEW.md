# Independent PWA operator review

Date: 2026-10-06 UTC.

## Decision

**PASS for the specified bounded operator test suite. No operator mismatch or
remaining operator blocker was found.** This supports proceeding to the next
bounded full-solver validation stage. It is not acceptance of an independent
physical REF, FLAT/HIER, global exactness of an untested solver, scalability, or
the missing original v0 fixture.

The implementation reviewed is `src/timecut5/pwa.py`, SHA-256:

    717519aecb50bc4e45266b1179390a3f5d9ea6b2bd3ef3df3c926a55b122e3b9

Its public seed/cut definitions are `src/timecut5/probe.py`, SHA-256:

    79226bd7dcf9ff9ceb326e2caf6cee1c471312a6e178ac024a77c27f2ea02b6d

The PWA hash was checked again after the completed runs and is unchanged.
No production files were modified by this independent reviewer.

## Results

- Independent oracle self-tests: 12 literal analytic tests passed.
- C/CS full-energy symbolic comparisons: 172 finite input cases passed across
  7,991 open cells and 8,163 singleton boundaries. Exact coefficients,
  attainment and support were compared on complete independently constructed
  arrangements. 46,548 executable witnesses were replayed.
- Separately labeled point-only fuzz: 180 additional cases passed at 1,793
  exact output energies, with 3,761 witness replays. These are not counted as
  whole-energy symbolic checks.
- D/S/lower-envelope/reduction checks: 9 directed frontiers passed 216
  whole-domain checks, covering 2,197 open cells and 2,413 singleton boundaries.
  The suite includes per-prefix transforms, reduction minimality, duplicate
  equivalence classes, idempotence, envelope order independence, and
  R(T(R(X))) versus R(T(X)) for D/S/C/CS. It replayed 1,854 one-step witnesses,
  including budgets as small as 10^-12.
- Inherited restricted two-charge witness checks: 3 passed. At final energy 1,
  the intermediate-energy restriction Ea<=1/2 yields attained infimum 7/2;
  Ea<1/2 yields the same unattained infimum. Replayed witnesses obey the
  inherited restriction at an approach budget of 10^-12.
- Mutation sentinels: the validator rejected exact-value, attainment and
  missing-support mutations. The value perturbation was only 10^-9; there is
  no numerical tolerance.

## Independence and coverage

The C/CS oracle uses one-dimensional convex max-of-affine minimization over
arrival energy with direct strict interval intersections. Production uses
strict Fourier–Motzkin projection. The oracle does not import production
projection, envelope, reduction or fixed-energy charging helpers.

Its exact energy arrangement contains arrival-candidate path intersections and
all affine candidate-objective value intersections, including those across
regimes. These boundaries prove value/attainment constancy on the resulting
cells. The validator compares affine coefficients on open cells and checks
singleton boundaries separately. The full argument and executable commands
are in `README.md`.

Adversarial cases cover open arrival-energy endpoints; forbidden Ed=Ea;
negative, zero and positive tau-F slopes; capacity endpoints; arrival and
departure charge kinks; latest-start equality for open/closed inputs; CS
plateau interiors and boundaries; tied-minimizer attainment OR; rho/pi
tradeoffs; isolated chi changes; disjoint supports; equivalent duplicates;
and inherited predecessor restrictions.

## Remaining gates

1. Independently construct and validate bounded route/physical-prefix REF
   semantics rather than treating analytic seeds as reconstructed road plans.
2. Compare full solver status and sequential complete-key semantics exactly,
   including primary and secondary nonattainment and executable replay.
3. Validate FLAT reduction off/on, and HIER action coverage, bounds and
   equal-primary handling separately.
4. Preserve the original-v0 fixture gap and all historical failures honestly.
5. Do not infer practical piece-count bounds or scale readiness from this suite.

No push, PR, deployment or scalability run is part of this review.
