# Continuous convex suffix model v2

This is an additive, separately reviewable extension. Every previously tracked
v1 source file, API, model, ledger and evidence package is unchanged. The v2
candidate modules are `convex_model`, `convex_query` and `convex_witness`;
`solver` and its rational candidate certificates are reused without changes.
The independent modules are `independent_convex_model`, `convex_checker`,
`convex_witness_checker` and `convex_evidence`. The independent author derived
the rows without reading the new candidate implementation.

No A/B/C or frozen TRACE01 numerical model is admitted by this extension's
unit-evidence tools. New independent source/model review is required before
any frozen-model use. Resource/capture admission, real immutable directed-leg
support, optional coalescing and literal G8 closure remain separate.

## Physical scope and exact coverage

A nonempty original charging primitive must cover `[0,B]` in ordered positive
width segments. Slopes are positive and nondecreasing; adjacent intervals meet
exactly and their affine values agree exactly. Thus the primitive is continuous,
strictly increasing and convex, and equals the maximum of its original affine
support lines on `[0,B]`. Equal adjacent slopes and nonzero primitive intercepts
are valid. Gaps, overlaps, discontinuities and decreasing slopes fail closed.

An empty primitive is accepted only if the checked physical case has no C/CS
capability at any Site. Such a suffix contains only S; no dummy primitive,
charging band or charging-completion row is introduced. The original family
checker independently prevents charging ancestors in such a case.

`build_models(ctx, family_id, word)` enumerates the entire Cartesian product of
closed original arrival bands in lexicographic order. `arrival_bands` is aligned
with every suffix action: a zero-based integer for C/CS, null for S. At a shared
breakpoint either adjacent band can contain the same physical plan. Each band
assignment has a distinct model identity; this overlap is optimization-domain
coverage and never an extra production semantic action.

Road reachability is tested before band expansion. An unreachable physical word
has exactly one graph-exclusion model, with `arrival_bands=null` and `lp=null`.
An S-only reachable word instead has an aligned list of nulls and an ordinary
LP. The family/word language may also be empty, yielding zero models. Graph
exclusion, empty word language, closed LP infeasibility and strict infeasibility
are retained as different facts.

`build_model(ctx, family_id, word, arrival_bands)` constructs one explicit v2
regime. It requires an assignment even for a one-segment curve; the v1 API does
not silently switch formats. A v2 query ledger always uses the v2 schema and
enumerates every original family, legal word and band assignment in that order.

## Wire format and exact rows

`convex_model.schema.json` gives the structural model schema. It is only a
structural description: acceptance additionally requires the independent
assembler's exact wire equality, canonical rational strings, original checked
case/bundle/family identity and complete ordered query coverage.

The model schema is `family5-suffix-model-v2`. Its exact fields are `schema`,
`family_id`, `word`, `case_sha256`, `family_bundle_sha256`, `H`, `pi`,
`arrival_bands`, `exclusion`, `lp`. The query schema is
`family5-suffix-query-ledger-v2`; its fields are unchanged from v1. The record
fields remain `model`, `stages`, `result`. All numeric LP entries are canonical
rational strings. Integers, booleans and floats cannot stand in for those strings
or for one another in typed identities/flags.

Variables remain `E_prefix,T_prefix,q_0,T_1,...,q_(k-1),T_k`. Each row stores a
label, a full coefficient vector, its right-hand side, and a Boolean strict flag.
Every ordinary row is `coefficients · variables <= rhs`; strict rows use `<`.
The first three rows are the original inherited lower/upper energy and time
rows, with their original endpoint and chi strictness unchanged.

For stop k, let `d` be accumulated selected-leg consumption through its arrival,
`x = E_prefix + sum(q_previous) - d`, `q=q_k`, and `y=x+q`. The existing arrival
floor and departure capacity rows remain first, with the current charge excluded
from arrival inventory. For selected arrival segment `(lo_i,hi_i,a_i,b_i)`:

1. `arrival_band_lower:k` is `-x <= -lo_i`, closed.
2. `arrival_band_upper:k` is `x <= hi_i`, closed.
3. `charge_positive:k` is `-q < 0`, strict.
4. For every original support line j, `charge_completion:k:j` is
   `T_previous - T_k + (a_j-a_i)*(E_prefix+sum(q_previous)) + a_j*q
   <= -drive-overhead + (a_j-a_i)*d + b_i-b_j`, closed.

The support rows occur in original segment order. They are equivalent to
`T_k >= T_previous+drive+overhead+F(y)-F(x)` on the selected arrival band. A
departure-band assignment or charge grid is unnecessary. Departure capacity,
arrival floor, positive charge and the covered primitive keep x and y in its
domain.

For S the two original zero-charge rows replace all four charging items. The
four original service rows follow for S/CS: nonempty window, latest service
start, release completion and own-service completion. CS therefore finishes at
the maximum of charging completion and scheduled service completion. The final
row is the original terminal reserve. J/Q vectors and constants retain original
start time, prefix rho, all stops, and original prefix-plus-suffix H/Pi.

## Physical equivalence, infima and attainment

Every physical original-family completion chooses a containing arrival band at
each charging stop. Its actual times and energy embed in that model with equal
J, Q, H and Pi. Conversely, every strict model point reconstructs a receipt for
the exact original prefix family no later than its prefix time budget. Actual
selected-leg execution and earliest/max suffix completion give no later time
than each LP budget, retain every inventory and Q/H/Pi, and preserve service
feasibility: earlier arrivals cannot push the service start past its latest
bound. Proof budgets are never discretionary physical waiting.

The finite union therefore has the same physical infimum. On an exact optimal
J face, the physical lift cannot improve J strictly without contradicting the
certified infimum, so J is equal there. Q is preserved identically. As in v1,
the five exact stages are strict feasibility, closed J optimum, strict J-face
feasibility, closed Q optimum on that J face, and strict J/Q-face feasibility.
A capped common rational margin applies only to original strict rows; it is
not an epsilon/charge threshold. Closure arguments mix with an existing strict
point, inside the J face only after its strict feasibility has been established.

All LP tasks are independently reconstructed and checked with exact rational
primal/dual certificates or a strictly positive common-slack Phase-I optimum.
Primary nonattainment never invents a Q value. Secondary nonattainment never
invents an attained H/Pi key. Finite-union aggregation considers Q only on
globally minimal attained J regimes and H/Pi only on attained minimal J/Q
regimes. Its audit retains every winning regime including breakpoint overlaps.

Composed physical witnesses bind the certified result contract, original
family/word, and the selected regime's arrival bands. Each actual C/CS arrival
energy must lie in its selected closed original band; either adjacent band is
valid exactly at a shared breakpoint. A separately replayed physical completion
may differ from a particular certified LP vector but must remain a member of
the claimed branch and satisfy its exact certified result contract.
`convex_evidence` enforces this for both regime and query-slot witnesses. Raw
physical replay alone proves original-family/word realizability, not branch
membership or optimality. Foreign prefixes, out-of-band branch substitutions
and fake minimum contracts reject.

## Reproducible tiny evidence

Run the two new suites with the pinned Python 3.11 runtime and `PYTHONPATH=src:.`:

    python -m unittest discover -s tests -p test_restricted_suffix_v2.py -v
    python -m unittest validation.suffix5.test_convex_checker -v

Repeat the independent suite and raw replay under `-O` and `-OO`. Its explicit
checks do not rely on assertions removed by optimization. The independent suite
blocks candidate, production and optimizer imports. The evidence generator
`experiments/time_cut_v2/convex_suffix/make_unit_evidence.py --output NEW_DIRECTORY`
accepts no external population input and requires an empty output directory.
It records only the named tiny input fixtures and all their band models, exact
certificates and physical witnesses. `replay_unit_evidence.py` takes externally
supplied input/record hashes, independently regenerates every ordered regime,
and replays with candidate/production/optimizer imports blocked.

Coverage includes arrival/departure on both internal breakpoints, departure at
capacity, crossing both thresholds, two charge stops, q tending to zero at a
breakpoint, open inherited energy/time, deadline equality, inverted windows,
charging/release/CS switches, both nonattainment classes, exact graph and strict
exclusions, genuine no-curve service, and disjoint original ancestor families.
Separate hand-authored tests exercise law, row, support-intercept, strict-flag,
band-coverage, certificate, result and witness substitution negatives.
