# Prospective treatment-only post-service completion diagnostic

This prospective gate has independent pre-run completion-gate review approval.
That approval permits preparing a frozen plan; it is not a real result or a
performance claim. Importing it or running `--plan` launches nothing. Pending
review states still refuse freezing and launchable manifests. No real experiment
has run as part of preparing this candidate.

The previous original-OD02 N128/Hmax33 post-service OFF/ON pair exhausted both
exact240-second windows before reaching the full second-layer reduction. Those
failures remain in their original records. This separately declared diagnostic
asks whether the fixed treatment can reach a useful completion/reduction stage
within an exact600-second phase. It is completion feasibility, not a same-budget
speedup comparison, a retry of the old pair, or evidence from an unexposed holdout.

## Fixed treatment and domain

There is exactly one arm, `post_service_completion_on`. It fixes HIER,
analytic-C ON, post-service objective reduction ON, support ON, envelope OFF,
q10 dyadic ALT, onward ALT, target terminal-energy routing and the historical
remaining-charge runtime. The optional convex charge-count runtime is excluded.
The original `OD02_energy_only_soc3_10`, ordered N128 pool, hierarchy, action
coverage, query and Hmax33 remain unchanged. The pre-completion source reference
is `d7a38c02f83058efe8e710989695407c5f2e9483`.
The production guard pins the95-file `src/` digest to that baseline, excluding
only the exact generated `src/hiroute.egg-info/` packaging-metadata prefix.
Metadata remains bound in the full executable closure when present. Every other
`src/` entry is pinned, so optional-runtime development cannot enter this diagnostic.

The proved reducer runs only at the existing whole next-departure-layer hook,
after scheduled service is complete (`remaining_schedule == 0`), at identical
complete physical State. Pre-service, r==1, active recording and inherited
family cases retain historical skyline behavior. Selected adjacent cells join
only for the identical original parent and connected exact energy union, with
its callback retained. The historical general coalescer remains OFF and the
existing product-order certificate is unchanged.

Generation, common-seed admission, final storage, every durable callback and
fresh full replay use historical disabled analytic/support/envelope contexts.
They never create the experimental reducer. The one fresh common seed must
independently replay; Hmax drift blocks execution without a replacement seed.

## Three-slot lifecycle and resource budget

The denominator is exactly three: one preparation, one search, one independent
full replay. Failed, blocked and timed-out slots remain visible. There is no
automatic retry, next domain, extra control or changed stop bound.
Supervisor preflight/launch exceptions also retain all three slots as
UNKNOWN/BLOCKED, with an error detail and without claiming verified cleanup.

The exact phase is600 seconds from the authenticated pre-solver entry marker
through worker exit, including post-solver finalization. The search worker has
900-second total wall and CPU ceilings; preparation keeps600-second wall/CPU
ceilings; independent replay keeps180-second wall and120-second CPU ceilings.
Every worker retains the8GiB address-space ceiling and existing bounded cache,
observer, output and cleanup policies. Aggregate declared worker reserves are
1680s wall and1620s CPU; these are not measured aggregate CPU or RSS isolation.
The parent's90-second CPU soft budget preserves an inherited hard limit that
can admit a901-second child CPU hard limit.

The old batch helper accepts only120/240-second phases and old worker caps.
This gate leaves it untouched and uses a small fixed three-slot adapter around
the same reviewed low-level supervisor. New outer schema, arm, policy and source
hashes bind preparation, phase identity, admission, durable incumbent, progress,
terminal result and fresh verification. The source closure includes this gate,
its adapter, reducer module and unchanged gate dependencies.

Timeout snapshots remain censored, including a snapshot that says `returned`.
A timeout can support only its independently replayed feasible incumbent. Exact
completion additionally needs authenticated canonical terminal status/objective
and full key, unchanged Hmax, healthy final observer and matching conserved final
operator/reducer statistics. Different valid charge witnesses are permitted and
each durable witness is freshly replayed. No positive performance result is
required.

## Preparation checks and eventual interface

Focused tests use synthetic lifecycle/admission fixtures and tiny hand-built
native graphs on CPU3, normal and `-OO`. They never load real OSM or holdout
inputs, install packages or run the proposed real diagnostic. CPU pinning is
shared-host concurrency control, not memory/I/O isolation.

After final revised-byte validation and a separately approved immutable source:

```
python -m experiments.post_service_completion_gate_v1.run --plan
python -m experiments.post_service_completion_gate_v1.run --freeze --input-directory INPUTS --output MANIFEST.json
python -m experiments.post_service_completion_gate_v1.run --gate --manifest MANIFEST.json --manifest-sha256 SHA --output NEW_OUTPUT --cpu CPU
```

These commands document an interface; they do not authorize or launch a run.
