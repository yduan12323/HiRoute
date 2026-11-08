# Exact identical-branch lookup folding

Finite lookup construction recursively builds the left and right child, then
returns the child directly when z3.eq proves structural identity. Otherwise it
retains the original If(index < midpoint, left, right). Bottom-up application
exposes further identical children. The identity If(c,e,e)=e holds for every
valuation without assumptions, rounding, solver heuristics or reachability
restrictions. The outer bounds/default guard is unchanged, including when its
branches happen to coincide. Empty vectors retain their original default.

This does not change table contents, AS/AT spaces, literal aliases, action zero,
inactive slots, strict support, objectives or original Store-based grounding
and replay. Exact distinct rational values remain distinct. No host, CPU, RSS,
disk, output, deadline or cumulative-budget guard changes.

New tiny tests compare folded lookup against total Store functions for every
integer index with repeated exact rationals, mixed values, empty vectors,
Boolean reachable/unreachable/default patterns and distinct source/target maps.
They check a structural reduction on a uniform tiny vector and preservation of
the outer guard. Existing seven-function/eight-fixture, strict-support and
attainment, audit, certificate and independent replay gates run unchanged.
No full-size construction or performance conclusion belongs to this stage.
