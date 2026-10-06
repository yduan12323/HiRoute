# Independent bounded C/S/CS reference

This is a new Milestone-5 bounded diagnostic oracle. It does not replace the
archived B21 oracle, production FLAT, any hierarchy proof, or historical
Stage-A20/Stage-B64/Stage-C32 validation. The 18 positive-domain v2 analytic fixtures
are additional validation only. The originally frozen v1 set and its results are
preserved exploratory tests of a wider nonnegative domain, not acceptance tests. All archived sources and results stay unchanged.

## Independence and scope

`model.py` implements an independent road/path selection, regime construction,
sequence enumerator and original-semantics witness replay. `lp.py` adapts the
archived rational-certificate technique, with explicit zero-dimensional and
infeasible-equality support. `solver.py` performs global sequential optimal-face
selection. None imports `timecut5` or `stopplan4r`, and production must not import
these routines as its optimization or witness implementation.

The domain is a finite directed graph and an explicit diagnostic stop bound
`H_ref`. Legal action sequences include revisiting a site and zero-length self
legs. Only static directed-unreachable extensions, disallowed effects, already
fulfilled service effects and extensions past the terminal destination are
excluded from enumeration. Energy infeasibility is decided by exact continuous
regimes, not by a discrete SOC/charge grid. `H_ref` is not a production bound.
The result `infeasible_within_H_ref` never asserts unrestricted infeasibility.

The intentionally slow reference enumerates all simple paths for each anchor in
small directed graphs, then chooses `(time, node tuple, edge-ID tuple)`. Edge
length and energy come from the chosen fastest path, never shortest distance.
The production-domain validator requires positive road-edge times and lengths,
while selected identity legs remain zero. An explicit exploratory flag permits
nonnegative edge costs, including cycles without an undefined zero-cycle tie rule. It is not suitable for large OSM instances.

## Fixture contract

Input is the unchanged `results/milestone_4r_b2_b21/hand_cases.json` schema:

- `H_ref`, `origin`, `destination`, `start_time_s`
- `initial_energy_kwh`, `capacity_kwh`, `minimum_energy_kwh`, `reserve_kwh`
- `consumption_kwh_per_m`, `overhead_s`, `lambda_stop_s`
- `sites`: mapping of site identity to explicitly allowed `C`, `S`, `CS` effects
- `edges`: directed `source`, `target`, `time_s`, `length_m`; optional unique
  string `edge_id` (`id` accepted as fallback), else `input:{index:08d}`
- `charging_segments`: `[lo, hi, slope, intercept]` rows for a continuous strictly
  increasing cumulative primitive covering the battery domain
- `schedule`: one `{a,b,D}` object or null; earliest service start is
  `max(a, arrival_time + overhead_s)` and must be at most `b`
- optional `initial_remaining_schedule`: exact integer `0` or `1`, default `1`
  iff a schedule is supplied. An explicit `0` preserves a schedule definition
  but marks it already fulfilled; explicit `1` without a schedule is invalid.

No implicit `CS` capability is inferred from separate `C` and `S` entries.
An empty capability list and no schedule/station are valid. Finite integer,
Fraction, decimal string, or decimal-float inputs are interpreted rationally;
bools, nonfinite values, inconsistent bounds and malformed primitives are
rejected. Production inputs require positive stop overhead and positive
road-edge time/length. `allow_nonnegative_extension=True` is an explicitly labeled
exploratory opt-in for the preserved v1 cases; it is never production acceptance.
Decimal strings are recommended for reproducible inputs. Site and
node identities are nonempty strings.

For `C` or `CS`, each charge is strictly positive. Charging and service begin
after the same per-stop overhead. A `CS` completion is the maximum of charging
completion and scheduled service completion. Service can be fulfilled once;
there are no charging site reservations, site-specific rates, multiple service
windows, or time-dependent road costs in this fixture schema.

## Exactness and attainment

For each sequence, arrival/departure charging segments, early/late schedule
regimes, and the two `CS` max branches are enumerated. Overlapping closed
boundaries are harmless; they are never evidence of open-domain attainment.
Each continuous closure LP is solved by a floating-point candidate solver,
then checked entirely using rational arithmetic:

1. rational primal feasibility;
2. rational inequality dual signs and dual stationarity;
3. exact primal/dual objective equality;
4. for infeasible LPs, a positive exact Phase-I optimum (also handling equality
   constraints), or an explicitly checked impossible constant constraint.

Any uncertified or unsupported regime makes the whole case `unresolved`; it is
never skipped to make an apparent optimum. This is conservative and can report
unresolved for numerically ill-conditioned valid rational input.

Strict feasibility maximizes a common slack `s` subject to `0<=s<=1` and
`q_j>=s`. Any exact positive slack suffices. The cap of one only bounds an
auxiliary LP; it is not a minimum charge. After proving the strict domain
nonempty, the same test is performed on the exact J-optimal face and then on
the joint exact J/Q-optimal face. In a convex regime with a nonempty strict
domain, mixing a strict point with any closure point proves the entire closed
polyhedron is the closure of the strict domain. This justifies its infima.

Global selection minimizes J over all regimes. Only regimes attaining that J
contribute to the secondary Q face. If Q is attained globally, minimize the
finite H and site/action tuple. A primary-open regime cannot donate a fictitious
Q, and a smaller secondary-open infimum blocks a larger attained Q. A chosen
attained result is independently replayed using the original piecewise
integral/max semantics and actual selected route lengths.

## Result contract

`solve_case(case, keep_evidence=True)` returns an envelope with:

- `scope = "bounded_H_ref_diagnostic"`, `H_ref`, case ID and explicit `model_domain`
- sequence and regime counts, certified-regime count
- `all_regimes_certified`, per-sequence records, optional full regime certificates
- `result` with one of the following statuses:
  - `attained_optimum`: `J`, `Q_total`, `H`, `site_action_tuple`, `charges`,
    `lex_key=(J,Q,H,tuple)`, replayed events, road legs and terminal state
  - `primary_unattained`: `primary_infimum`, without Q/H/tuple/key
  - `secondary_unattained`: attained `J`, `primary_infimum`,
    `secondary_infimum`, without H/tuple/key
  - `infeasible_within_H_ref`: no feasible executable plan within this bound
  - `unresolved`: exact error and uncertified regime context, no asserted answer
  - `invalid_input`: input error, distinct from mathematical infeasibility

Rationals serialize as strings through `jsonable`. The accepted key has exactly
four components. Charge-vector equality is not required for production parity;
different valid witnesses can realize the same key.

## Frozen evidence and commands

Use the existing Python 3.11 environment; no installation is needed:

```sh
PY=/workspace/shared/navigation_audit/venv-python311/bin/python
$PY -m validation.reference5 results/milestone_4r_b2_b21/hand_cases.json \
  --output /tmp/ref5-original-fresh.json
$PY -m validation.reference5 results/milestone_5_reference/frozen_cases_v2.json \
  --certificates --output /tmp/ref5-analytic-fresh.json
$PY -m pytest -q tests/test_reference5.py
```

The CLI uses exclusive-create output files to avoid replacing evidence. Full
regime certificates are optional because the original case has 11,072 regimes.
All certificates are checked during every solve regardless of retention.

The positive-domain analytic fixture hash is recorded in
`results/milestone_5_reference/freeze_manifest_v2.json`. It was frozen before its
18-case REF and production comparisons. Each fixture carries independently
computed expected fields and a short analytic derivation.

The first frozen set (`frozen_cases.json`, `freeze_manifest.json`) used zero
stop overhead in 16 cases and zero road length in two of those cases. The
independent prototype admitted that wider nonnegative domain, so its successful
results (`analytic_cases_ref.json`) did not establish production parity. The
production adapter correctly rejected those out-of-domain cases. No original
v1 evidence was replaced or tuned to a solver output.

V2 repairs the hypotheses with h=1 throughout. The two CS-open cases now have
initial energy3 and road lengths1,1, preserving arbitrarily small strictly
positive feasible charge. Their analytically derived primary bounds change
from2 to3 and from12 to13, respectively. Other time expectations change exactly
by the applicable extra release overhead; the waiting case remains13. The v2
manifest records all repairs and the retained v1 hash. V1 can be reproduced only
with the explicitly exploratory `--allow-nonnegative-extension` flag.

The archived B21 probe recorded 263 static sequences and 11,070 regimes. The
new reference visits 41 directed-reachable prefixes, of which 16 are terminal
candidates, and verifies 11,072 regimes. The two extra regimes are the feasible
route but energy-infeasible service-only sequence: the old probe manually
rejected it; the new generic zero-charge-variable LP checks both schedule
branches. The original optimum remains `(44950,76,3,2C3C4S)`. This reference's
chosen valid charge vector is `(41,35)`; the archived `(28,48)` also replays to
the same key. The vector itself is not part of the accepted lexicographic key.

## Destination-boundary audit regression

A subsequent independent audit found that the initial production adapter allowed
a semantic `S` or `C` stop at the destination, whereas this reference carried
forward the frozen predecessor rule, “Destination arrival is terminal, not a
semantic stop” (M5 theory v1, section 2). The parent resolved the authority
question by expressly preserving that physical rule unless a new contract
replaces it. REF therefore required no optimizer or model change; production
needed a guard and matching replay rejection.

`audit_regression_cases.json` is a separate three-case post-discovery regression
set, frozen before comparing that guard fix. It must not be reported as an
independent holdout. It verifies destination service rejection, destination
charging rejection, and a legal selected road leg whose internal path transits
the destination before a service stop elsewhere. No additional first-transit
ban is imposed on physical road paths. The original 18 positive-domain v2
fixtures and all earlier evidence remain unchanged.

The subsequent `audit_route_grammar_cases.json` records a known drive-waypoint
regression: a battery-infeasible fastest direct route must not become a
zero-stop plan by concatenating slower drives through an intermediate site.
REF accepts a semantic site/action sequence and charges, not a free drive-event
stream. It reselects the actual fastest leg between each pair of semantic
anchors, rejects `D` as a stop effect, enforces `H_ref`, and verifies that any
optional supplied leg map equals its own independently recomputed map. An
externally substituted energy-cheaper detour therefore cannot certify a plan.
This regression is also post-discovery and is not holdout evidence.
