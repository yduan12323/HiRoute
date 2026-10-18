# Optional exact C/CS projection support prefilter

`timecut5.pwa.ProjectionSupportPrefilter(enabled=True)` is an explicit,
context-local opt-in around existing operators or a solver invocation. With no
context, the historical projection arithmetic remains in use. A context with
`enabled=False` counts the historical segment-pair builds without computing
support intersections. Only exact booleans are accepted. Each instance is
single-use; distinct nested contexts restore the outer context on exit, including
exceptional exit. Concurrent tasks can enter distinct contexts independently.
As with Python context variables, child tasks that inherit an active context
inherit that same observer; create a separate context for separate accounting.

## Local support proof

For a source energy interval `I`, incoming closed charging segment `[il, ih]`,
and outgoing closed segment `[ol, oh]`, the original projection includes

- `ea` in `I` and `[il, ih]`, with the source's exact open/closed endpoints;
- `ed` in `[ol, oh]`;
- strict charging `ea < ed`.

Compute `J = I.intersect(Interval(il, ih))` using the existing exact interval
operation. If `J` is empty, the pair is impossible. Otherwise, if `J.lo >= oh`,
every candidate satisfies `ea >= J.lo >= oh >= ed`, contradicting strict
charging. Equality is impossible even if all endpoints are closed. If
`J.lo < oh`, the pair is retained, including when the lower endpoint is open.
Every remaining time, schedule, attainment and energy condition stays with the
original projector. A skip describes only this source-piece/segment pair; it is
not a route, Site, Region or unreachability conclusion.

The surviving rows are not clipped, normalized differently, reordered or
cached. Their original projection history and constrained witness lifting are
unchanged. The surviving pair iteration order and all envelope inputs remain
the same. Thus exact cuts, attainment, first-witness selection, provenance
nodes/batches and physical replay are preserved. The S-only operator is unchanged.

## Accounting and scope

`snapshot()` returns a frozen detached `ProjectionSupportStatistics` containing
`enabled`, `considered_pairs`, `skipped_empty_input`, `skipped_strict_energy`, and
`projection_builds`. Only C/CS pairs are counted. A build is counted immediately
before calling `Projection.build`; an interrupted call may have incomplete
accounting. Counts are constant-size scalars, not per-piece logs or callbacks.
Both explicit control and enabled contexts pay counter costs; the enabled arm
additionally pays exact support comparisons. No end-to-end speedup is asserted.

For P input pieces and K segments, baseline construction calls the projector
P*K*K times. The prefilter still considers those pairs but builds only the
energy-support-feasible ones. For the current three ordered positive-length
segments, the three reverse-segment pairs out of nine are always impossible;
narrow source domains can eliminate more. This does not change worst-case
search-depth combinatorics or bound envelope arrangement cost.

Tests enumerate exact support order cells independently, compare surviving
original rows, check full output against the independent analytic family oracle,
and compare witnesses, recorded provenance and tiny FLAT/HIER solver results.
They cover zero/singleton energy, segment knots, open endpoints, strict equality,
inherited restrictions, C/CS/S, exception restoration and concurrent contexts.
No charging quantization, default pruning, Hmax change or real-road acceptance
is introduced.
