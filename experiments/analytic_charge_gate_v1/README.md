# Prospective analytic-C OFF/ON diagnostic

This separate, opt-in gate fixes the previously exposed DEV domain
`OD02_energy_only_soc3_10`, original ordered N128 pool and hierarchy, and derived
Hmax33. The exact query/pool bindings are those already checked into
`docs/dev_cohort_v1_bindings.json`. Selection is based on prior DEV exposure and
its observed extension hotspot; this is not outcome-blind sampling or holdout.

Both outer arms (`analytic_off`, then `analytic_on`) use immutable inner
`method='hier'`, target routing with terminal energy, dyadic ALT q10, onward ALT,
remaining-charge bounds, skyline reduction, support prefilter ON, and envelope
sweep OFF. Only the C operator's `AnalyticCharge` context differs. No production
default, query, original action coverage, charging curve, Hmax or strict pruning
rule changes. CS remains the historical generic operator. A single fresh common
seed is generated and independently replayed on full routing; Hmax drift blocks
both searches instead of selecting a replacement seed/domain after outcomes.

## Scope and accounting

Generation, seed admission, final storage, independent full replay and each
in-search durable callback enter distinct disabled analytic/support/envelope
contexts. Search contexts are coextensive; the exact engine's own internal work
is included in search counts. There is no global monkeypatch or altered method
tag. Outer schema/configuration/policy, inner HIER method, original case,
source/native identities and manifest are bound through durable records,
admission receipts, phase identities, snapshots, results and fresh verification.

The existing five support fields keep their meaning: `projection_builds` counts
actual generic C/CS entries. Analytic statistics separately count C pair/build
entries, including analytic attempts with empty results. Only a healthy returned
snapshot matching the authenticated final result can establish:

- support.considered = empty skips + strict skips + generic builds + analytic builds
- C.considered = support-skipped C pairs + analytic C builds + generic C builds
- C generic/skipped counts are subsets of their support totals; recorded fallback
  is a subset of C generic builds.

Live samples are detached scalar but nontransactional. TIMEOUT snapshots remain
censored even if they say `returned`; they do not establish conservation, final
health or exact completion. The current original validators are not changed.

## Execution and acceptance

This code does not launch on import or create a launchable plan automatically.
From a separately reviewed immutable source, use:

```
python -m experiments.analytic_charge_gate_v1.run --plan
python -m experiments.analytic_charge_gate_v1.run --freeze --input-directory INPUTS --output MANIFEST.json
python -m experiments.analytic_charge_gate_v1.run --gate --manifest MANIFEST.json --manifest-sha256 SHA --output NEW_OUTPUT --cpu CPU
```

The reviewed supervisor is reused with one preparation, two searches and two
independent replay slots (denominator five, failures/blocked slots retained).
Each exact phase is 240 seconds, including post-solver finalization until worker
exit. Other existing caps remain: stage wall/CPU limits, verification limits,
8GiB address-space ceiling, bounded observer and bounded routing cache. One
heavy worker at a time; no automatic repeat, next domain, or historical pooling.

Operational admission requires authenticated preparation, fixed case/arm/order,
phase receipt and cleanup, fresh full replay, source/manifest/configuration
identity, and bounded progress artifacts. A TIMEOUT may support only its
replayed feasible incumbent. Completed results additionally require matching
exact terminal payload/full key, unchanged Hmax, healthy final counters and
observer. If both complete, canonical exact answers must agree (witness payload
excluded, witness independently replayed). Report both failures and successes;
no positive performance result is required. One fixed-order shared-host pair
cannot establish a general speedup.

Focused tests use synthetic/tiny native graphs only, pinned CPU1. CPU pinning
is shared-host concurrency, not memory/I/O isolation. No real graph execution,
installation or publication is part of preparing this candidate.
