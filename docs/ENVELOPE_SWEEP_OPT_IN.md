# Exact lower-envelope interval sweep, optional candidate

`timecut5.envelope_sweep.EnvelopeSweep(enabled=True)` selects a different
cell-selection algorithm only inside its explicit context. Absent context or
`enabled=False` retains the historical loop. Every recorded call also retains
the historical loop, even inside an enabled context. No default, arrangement,
frontier-dominance, charging, routing, Hmax or pruning policy changes.

## Exact endpoint and winner proof

The caller first applies the unchanged same-family check and constructs the
unchanged `_arrangement`: all original endpoint and pair-intersection knots,
their singleton cells, and every intervening open cell remain in their original
order. No irrelevant crossing is removed and no cells are coalesced.

For parent i, define `key_i(e) = (m_i*e+b_i, not chi_i, original_index_i)`.
This is a strict total order among active occurrences. Its minimum is precisely
the historical minimum time, then first attained tied parent, otherwise first
tied parent. For each unordered pair, intersect the exact parent domains.
Each directed better-parent relation holds where the affine difference is
negative, or zero when that direction owns the chi/index tie. Intersecting that
half-line with the common domain yields one exact interval, possibly empty or
a singleton. Equal affine functions use their fixed tie priority throughout.

The sweep maintains active support and, for each parent, the number of active
better-parent relations entering it. Among active parents the unique total-order
minimum has count zero; every other parent has at least that minimum entering
it. A lazy versioned heap finds the zero-count parent without rescanning all
parents. Relations already include both supports, so inactive parents never
contribute comparisons at that energy.

At a knot, apply all closed starts and open ends before selecting the singleton.
Then apply all open starts and closed ends before selecting the following open
cell. Apply each phase as a complete batch before choosing. This handles point
support, open-open gaps, simultaneous intersections, and opposite attainment at
equal times. Domain endpoints and every nonconstant comparison root belong to
the historical arrangement; missing events, negative relation counts, or an
active set without a minimum are invariant errors, never infeasibility results.

## Witness and provenance compatibility

Selections use the same original parent object and its first occurrence's
index, identical domain cell and `union` mode. The operator introduces no point
callbacks. The original constrained callback remains attached to each result,
so both attained witnesses and arbitrary positive-epsilon approaches survive.

Unrecorded output construction uses `provenance.select_many`. It materializes
parents and choices, then, for a nonempty selection batch, rejects any inherited
`_family` before constructing any output. It performs the same replacements
without repeating the all-parent guard per cell. No guard receipt or cache is
reused between calls. Empty choices retain the previous empty-selection behavior.
Its recorded branch delegates to the original `select` in identical order with
complete parents and parameters; enabled lower-envelope calls use the entire
historical path whenever a Recorder is active.

## Complexity and limitations

For M parents and C historical cells, the previous selection uses O(C*M) exact
operations, with C potentially O(M²). The candidate builds O(M²) pair relations
and endpoint actions, processes O(M²) changes using a heap, and visits C cells:
O(M² log M + C) selector operations and O(M²+C) storage. The unchanged arrangement
still costs quadratic pair work and knot sorting. These are operation counts,
not constant-time claims for arbitrary-size rational arithmetic.

Recorded provenance retains its all-parent payload and O(C*M) output cost.
The candidate also stores more events than the historical selector and may lose
on small or sparse instances. No real-road speedup or exact-completion claim is
made. It does not reduce surviving output fragmentation or route-depth growth.

`snapshot()` returns frozen detached scalar counters: calls, completed calls, input and selected
piece/cell totals, pair tests, relation intervals, event updates, heap pushes and
pops, baseline support-scan visits, recorded fallbacks and maximum input/cell
counts. No per-piece trace is exported. A concurrent heartbeat sample is not a
transactional multi-counter capture; interrupted work may be incomplete.
Both arms count a call at selector entry, after the unchanged arrangement has
finished; completion is counted separately. Time spent building that arrangement
precedes these counters and cannot be attributed to sweep selection.
Contexts require exact booleans, are single-use, and restore nested predecessors
on exceptions. Separate concurrent tasks can enter separate contexts; tasks that
inherit an active Python context inherit that observer too.

Validation compares a separately retained historical selector loop, independent
complete-cell family semantics, chosen callback identities, arbitrary-epsilon
witnesses, recorder exports and tiny FLAT/HIER physical replay. Endpoint, duplicate,
simultaneous-crossing, mutation-guard and context-isolation regressions accompany
seeded rational fuzzing. The current real projection-support gate remains on its
separate immutable source snapshot and does not include this candidate.
