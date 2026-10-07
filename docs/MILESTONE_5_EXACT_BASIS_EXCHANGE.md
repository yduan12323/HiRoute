# Exact recovery after an unresolved floating candidate

The original fast certificate check and greedy active-row reconstruction remain
first. Their successful certificates are unchanged. Only exhaustion of greedy
reconstruction enters a deterministic one-row basis exchange search.

A floating optimizer can select a dual support whose rational face is empty:
distinct exact bounds may round to the same binary64 value. Greedy primal
completion can also choose an inactive nearby inequality. The fallback retains
all original equalities, removes only redundant rows from the *candidate basis*,
and tries exchanging one chosen inequality for one remaining inequality.
No original model constraint is removed from the acceptance test.

For every trial it solves the candidate primal equations and dual stationarity
using rational elimination, then checks every original primal inequality and
equality, every dual sign, stationarity, and strong duality. The independent
certificate checker repeats those obligations. Solver tolerances, objectives,
strict-margin tests, and sequential objective-face construction are unchanged.
It makes no extra native optimizer call.

The search is intentionally incomplete: at most512 exchanges, with fallback
dimensions capped at32 variables,256 inequalities and32 equalities. A deficient
candidate basis, exhausted neighborhood, resource deadline or failed certificate
remains unresolved. The existing candidate wall/RSS/address-space guards apply
to exact reconstruction too. A later full run must retain any unresolved model.

Synthetic tests exercise a wrong dual face separated by2^-81 in objective, a
greedy inactive row, unchanged old success paths, exact equality preservation,
infeasibility rejection and the finite trial cap. They invoke no native LP.
Real unresolved models require a separately admitted server retry with their
original identities; these tests are not a real-result acceptance claim.
