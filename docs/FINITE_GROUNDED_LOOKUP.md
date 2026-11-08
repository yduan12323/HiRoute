# Development-only finite lookup

The independent model's seven immutable total arrays are expanded into balanced
finite If expressions. Each array has an exact ordered vector of values and a
constant default. For any integer i in [0,n), the balanced tree reaches exactly
leaf i; otherwise the outer guard returns the original K-array default. This
is a total-function identity, not just a relaxed valid-index approximation.
Time and length retain exact rationals; unreachable entries retain false and
zero numeric placeholders. Action rank zero and out-of-range ranks retain zero
AS/AT and false C/S. Distinct source/target maps and literal aliases are retained.

GroundedLookup now uses a selection hook whose default is unchanged Select.
FiniteGroundedLookup reuses the exact same transition, inactive-suffix and
terminal construction, replacing only that hook. Original input ownership,
original array expressions and Encoding.ground_trace remain available for
solver-free grounding and unchanged independent physical replay. The finite
trace is renamed onto the original action selectors; both continuous copies,
strict support, attainment and full lexicographic objective remain unchanged.
No table entries, actions, slots, or repeated visits are omitted.

The optional internal finite_lookup flag is false by default. Public solve and
solve_real, and the previously reviewed real consumer, retain their original
encoding. No real query or real-scale construction is enabled by this stage.

Tiny tests prove each of seven array expansions equal for every integer index
using an UNSAT disequality check, compare bounded outside and inside index
pairs by exact simplification, exercise seed grounding/inactive suffixes,
verify there are no array nodes in the finite physical formula, compare eight
analytic outcomes and two strict-support/primary-face traps, and test ownership
and index typing. Runtime or real-scale tractability is not established.

Stage ceiling is 120 CPU seconds inside the existing 28,800 total, carried from
18,494.237071745. Historical closed attempts and all UNKNOWN results remain.
Source-bound tests and controller charges are kept outside Git; independent
review of the exact commit is required before any next-stage admission.
