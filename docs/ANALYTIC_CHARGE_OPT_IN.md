# Optional exact analytic C operator

`timecut5.analytic_charge.AnalyticCharge(enabled=True)` selects a C-only analytic
boundary constructor and constrained midpoint lift. The default is absent;
`enabled=False` observes the original generic projection path without invoking
the new constructor. Only exact booleans are accepted. The context is single-use;
distinct nested contexts restore their predecessors even on exceptions. As with
Python context variables, child tasks inherit the same observer unless they
enter a distinct context.

CS and S remain on the historical path. Any active provenance Recorder also
forces historical C projection. Known recorded parents outside their Recorder
are rejected before the analytic path can consume them, including empty support.
No solver, experiment runner, domain, action coverage or default is changed.

## Exact boundary and structural parity

For one source `tau(x)=m*x+c`, incoming segment `Fi(x)=a*x+b`, outgoing segment
`Fo(y)`, let `I=source.domain intersect incoming_segment`, with endpoints L,U,
and `d=m-a`, `B(y)=h+Fo(y)+c-b`. Empty I yields no output. Otherwise support is
`outgoing_segment intersect (L,infinity)`; y=L is always excluded.

- d>0: output infimum is B(y)+d*L, attained iff source.chi and I.left_closed.
- d=0: output infimum is B(y), attained iff source.chi.
- d<0 and y<=U: output infimum is B(y)+d*y, always unattained because x<y.
- d<0 and y>U: output infimum is B(y)+d*U, attained iff source.chi and I.right_closed.

In particular, y=U remains unattained in the negative-slope case even if U is
closed; attainment can jump immediately to its right. A zero slope difference
can attain at an interior predecessor of an open energy interval. An open
source time cut cannot become attained through C alone.

The implementation deliberately retains more than this minimal partition:
positive d retains lower-bound lines from BOTH source.domain.lo and incoming.lo;
negative d retains upper-bound lines from BOTH source.domain.hi and incoming.hi,
plus the moving x=y line. Duplicate strictness is OR-ed by the unchanged rational
normalizer. Its ordering and the unchanged `_extract` preserve inactive knots,
singleton affine tie coefficients, and original per-pair output order. The final
historical envelope still chooses the first attaining minimum, or first minimum
when none attains. No coalescing or arbitrary tie replacement is introduced.

## Direct constrained lifting

For an attained output use T=tau_out(y); for approach epsilon use
T=tau_out(y)+epsilon/2. The predecessor-energy fiber is exactly

    I intersect {x<y} intersect {d*x <= T-B(y)}

where the last inequality is strict iff source.chi is false. A zero coefficient
is checked as an exact constant inequality; excluded equal endpoints remain
empty. Choose the midpoint of the resulting exact bounds, then the midpoint
between tau(x) and `T-h-Fo(y)+Fi(x)`. These are the same two choices as historical
`Projection.build(rows,(1,0)).lift`: energy first, time budget second. The lift
checks the original energy/time inequalities. The unchanged `_extract` calls
the ORIGINAL `source.at(x).realize_le(time_budget)` and replays the physical C
event. No unrestricted prefix re-solve, fabricated arrival time, fixed epsilon,
energy grid, or charging quantum is used. rho, pi, state and all inherited
callbacks/guards remain attached to the selected original source.

## Truthful, separate counters

`AnalyticCharge.snapshot()` returns a frozen detached record with:

- enabled
- considered_pairs: C segment pairs reaching pair iteration
- support_skipped_pairs: C pairs skipped by the existing support prefilter
- analytic_builds: entries to the new C builder, including empty results
- generic_projection_builds: actual historical C build entries
- recorded_fallback_builds: the subset of generic entries forced by Recorder
  while this analytic context is enabled

On a healthy completed scope:

    considered_pairs = support_skipped_pairs + analytic_builds + generic_projection_builds

The existing five-field `ProjectionSupportStatistics` is unchanged.
Its projection_builds continues to count GENERIC C/CS Projection.build entries;
it does not count analytic builds. With coextensive support and analytic
contexts, with every analytic-enabled C invocation inside those scopes, the
combined identity is

    support.considered_pairs = support.skipped_empty_input
        + support.skipped_strict_energy + support.projection_builds
        + analytic.analytic_builds

CS contributes only to the support counters. Recorder fallback contributes to
generic counts and never analytic builds. Independent/nested observer scopes
cannot be joined without accounting for their exact coverage. In particular,
a nested analytic context's builds belong to that nested context, not its outer
observer. Future combined experiment adapters must explicitly bind this
configuration and joined accounting; older strict validators are unchanged
and must not silently accept an unsupported analytic-enabled composition.

Counts are bounded scalar construction counters, not route decisions or engine
prunes. Updates and heartbeat snapshots are nontransactional. Interrupted or
exceptional calls can leave partial accounting; conservation is only a healthy
completed-scope check. Build counters mark entry, not successful completion.

## Evidence and limits

The focused tests compare ordered raw pieces and exact midpoint lifts against
the original FME row system on 2,520 segment-pair cases. Seeded rational unions
are also checked over complete energy cells by an independently implemented
formula oracle. Tests cover source endpoint flags, zero/positive/negative slope
differences, strict singleton hinges, inactive knots, tied sources, arbitrarily
small exact witness budgets, inherited two-charge restrictions, recorded
provenance byte parity and independent family verification, actual generic-call
counts, context isolation, and attained/primary-unattained/secondary-unattained
FLAT/HIER results with fresh physical replay where an attained witness exists.

The new path removes both generic elimination steps and their retained history
for C construction and lifting. It still creates and normalizes a constant-size
boundary-line fan and uses the unchanged extractor/envelope. Pair scanning stays
O(P*K*K). Routing, CS projection, arrangement, reduction and search costs remain.
These are finite correctness and mechanism checks, not a measured real-road
speedup, a holdout result, or a new milestone acceptance obligation.
