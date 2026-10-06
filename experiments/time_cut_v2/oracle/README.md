# Independent exact PWA operator validator

This directory is deliberately separate from the production worktree. Its oracle
uses exact rational arithmetic and analytic one-variable convex minimization.
It does **not** import production Fourier–Motzkin projection, envelope,
reduction, fixed-output charge helpers, or their expected values.

## Files and execution

- `oracle.py`: independent fixed-output C/CS oracle and complete output-energy
  candidate arrangement. Only standard-library imports.
- `test_oracle.py`: 12 literal analytic self-tests; no production imports.
- `validate_production.py`: public-schema adapter, adversarial/generated cases,
  full-cell equality checks, physical witness replay, and mutation sentinels.
- `frontier_checks.py`: independent D/S transforms and pointwise preorder
  semantics on exact arrangements; directed reduction/congruence checks and
  inherited two-charge witness restrictions.
- `validation_results.json` / `validation.log`: C/CS results. Full symbolic and
  point-fuzz-only coverage are explicitly separate.
- `frontier_results.json` / `frontier.log`: directed whole-domain checks.

Run from this directory:

    python -m unittest -v test_oracle
    python validate_production.py --repo /path/to/HiRoute --symbolic-random 150 --point-random 180 --output validation_results.json
    python frontier_checks.py --repo /path/to/HiRoute --output frontier_results.json

The adapter imports `timecut5.probe` only for public input data constructors and
`timecut5.pwa` for the system under test. Expected values are computed in this
directory. `frontier_checks.py` likewise converts public pieces into independent
records before applying its own mathematical comparator.

## Independent fixed-output construction

Fix output energy y, an affine input piece tau(x)=m*x+c, one arrival charging
segment Fa(x)=ma*x+ca, and one departure segment Fd(y)=md*y+cd.

The exact arrival-energy set is the input/charging-segment intersection, further
restricted by x<y. For CS, first intersect with tau(x)<=b-h when chi is true,
or tau(x)<b-h when chi is false. An empty interval gives no output. All these
intersections are direct one-dimensional bound calculations; no variable
elimination or production feasibility solver is used.

For C, minimize this affine function over the interval:

    tau(x)+h+Fd(y)-Fa(x).

For CS, minimize the convex maximum of three affine functions:

    a+D, tau(x)+h+D, tau(x)+h+Fd(y)-Fa(x).

The closure of a nonempty bounded interval is compact. The minimum of a convex
PWA function over that closure occurs at an endpoint or a pairwise intersection
of its affine constituents (if an interval is flat, its endpoints suffice).
The fixed-output oracle evaluates precisely this finite candidate set.

It then checks attainment separately on the *exact* interval:

- With attained input, intersect all objective inequalities at the candidate
  minimum. A nonempty exact optimal face means attained output.
- Open input never attains a C minimum.
- Open input can attain a CS minimum only on the constant schedule plateau,
  with **strict** slack in both time-dependent objective inequalities. This
  also respects the already-clipped strict latest-start guard.

Across regimes/input pieces, take the minimum value and OR attainment across
all minimizing regimes. This catches both excluded arrival endpoints and tied
regimes where only one supplies an executable optimum.

## Why the energy coverage is symbolic, not a grid

Within one fixed arrival/departure regime every candidate arrival energy is an
affine path x=A*y+B: a constant interval endpoint, x=y, or the intersection of
two objective planes. Include all rational y where two candidate paths cross.
Between consecutive such knots, candidate feasibility and endpoint ordering are
constant. Evaluate every objective plane along every candidate path; each
result is affine in y. Include every crossing of these affine values, even
across different regimes, plus all departure-segment endpoints.

On every remaining open cell:

1. The feasible candidate set is constant.
2. Each candidate's maximum objective selects a fixed affine value.
3. The minimum across candidates/regimes selects a fixed affine value.
4. Strict boundary membership and the existence of an attaining optimal face
   are constant. A change would require a candidate path or objective-value
   equality already included among the knots.

Thus the exact infimum is affine and attainment is constant throughout each
open cell. Two rational evaluations identify the affine coefficients *after*
this partition has established that fact. This is not an assumption that two
samples certify an arbitrary unknown function. Every singleton knot is checked
separately, including support endpoints, charging kinks, and capacity.

The production output is further refined at its own domain endpoints and affine
intersections. On each common open cell the validator compares exact affine
coefficients and constant attainment, rather than merely comparing point
values. Singleton values/support/attainment are checked exactly.

The frontier comparator similarly refines every piece endpoint and affine-time
intersection. Support and every time-cut/rho/pi dominance predicate are then
constant on an open cell. Independent pairwise strict-dominance tests plus
quotienting mutually equivalent entries specify the expected minimal classes;
this is distinct from the production incremental reducer. Mutual coverage is
checked on the complete arrangement, with antichain/no-duplicate checks on
reduced outputs. D/S/C/CS are also compared per prefix so a correct dominating
prefix cannot conceal a faulty transform of another prefix.

## Witness checks and restrictions

For each represented C/CS cell and boundary, the adapter requests a minimum
when attained and exact budgets tau+1, tau+1/7, tau+1/997. Open boundary budgets
must fail. Returned witnesses are checked against actual analytic seed
membership, including the finite seed interval (tau,tau+1] for open input,
strict positive charge, exact charging primitive, the physical C/CS max formula,
latest-start guard, final energy/time, state, rho and pi. These are generated
witness checks, distinct from the full symbolic value/attainment check.

A separate composed witness test uses two charge stops with F1(E)=E,
F2(E)=2E, unit overheads and initial E=t=0. At final Ed=1, completion is
4-Ea. Restricting intermediate Ea to (0,1/2] gives the attained minimum 7/2;
restricting to (0,1/2) gives the same unattained infimum. Replayed witnesses must
respect the inherited restriction, including at an approach budget 10^-12.
Solving the unrestricted original prefix would fail this test.

## Limits

The complete arrangements certify entire energy domains for the **specified
finite test inputs**. They are not a formal verification of all possible code
inputs, a general complexity bound, an independent physical route REF, full
REF/FLAT/HIER acceptance, or a replacement for the missing original v0 fixture.
The 180 random point-fuzz cases are explicitly only point evidence. The seed
families are declared analytic assumptions, not independently reconstructed
road prefixes. Multi-stop witness checks are directed finite compositions, not
an exhaustive arbitrary-depth search. No push or PR is performed here.
