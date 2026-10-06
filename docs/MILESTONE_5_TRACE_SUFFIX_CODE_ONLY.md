# Optional family and invocation validation tools

This feature provides opt-in family provenance, a tiny-HIER invocation trace,
and independent restricted-suffix validation. Its publication scope is source,
hand-authored synthetic fixtures, tests and this document. It includes no
captured acceptance runs, real queries, road/Site exports or certificate data.
It does not close literal G8 or establish complete A/B/C population acceptance.

## Production hooks and coalescing boundary

`timecut5.provenance.Recorder` is an explicit context for immutable family nodes,
original parent restrictions, operator batches and observed witness callbacks.
Outside that context, newly created pieces are untraced. Known recorded
families must stay within their original recording context; stale or foreign
bindings fail closed.

`timecut5.invocation_trace.InvocationTrace(recorder)` additionally records HIER
execution occurrences. Content family identities and integer invocation/group
identities serve different purposes. A successful family reconstruction alone
does not prove that every solver invocation was exported.

Existing public defaults and PR4's private reducer callbacks are preserved.
Optional exact coalescing remains explicitly selected and untraced-only. Its
early `_family` rejection is unchanged, including singleton/no-merge inputs.
Starting coalesced solving inside a Recorder therefore fails closed. This
guard belongs to the optional solver adapter. The standalone `coalesce_pieces`
primitive preserves PR4's unchanged-singleton behavior and rejects actual
merges of known proof families. This feature adds no certified guarded-union
bridge for traced coalescing. Opt-in
recording and its diagnostics are not a performance acceptance result.

## Independent repository tooling

- `validation.family5` reconstructs supported physical cut families and checks
  original-family membership, exact minimum/budget/approach contracts, and
  physical witness receipts. Its active analytic oracle is v2.
- `validation.trace5.verify_trace(trace, bundle, trusted_case)` checks the
  supported complete tiny-HIER grammar and exports exact node queries. Scope
  is positive-time synthetic graphs, the independently rebuilt balanced tree
  with sorted Site identities and leaf size 1, no external incumbent, and no
  coalescing. Real Region configurations require a separate trusted contract.
- `validation.suffix5` constructs finite suffix-word candidates and independently
  checks rational LP certificates, inherited-family constraints, strict faces,
  complete query ledgers, lexicographic results and physical suffix witnesses.
  Its proof model requires one positive affine charging segment covering the
  full battery interval, at most one service window, and the original finite
  stop bound. Unsupported curves fail closed.

Candidate LP generation uses NumPy/SciPy, already declared project dependencies.
The independent model, certificate and witness replay paths use the standard
library and do not import the production solver or optimizer. Floating solver
status is never sufficient for an acceptance claim. Uncertified candidates or
exhausted budgets remain unresolved, with completed stages retained.

Use `validation.suffix5.evidence.check_result_witness` or
`check_query_witness` to bind an optimal/approach witness claim to its
independently certified result. A caller-selected physical witness contract
alone does not establish optimality. Callers must supply trusted cases and
expected integrity anchors; a self-consistent untrusted bundle is not its own
authority.

`SolveBudget` checks actual candidate-call counts and wall/RSS limits at call
boundaries, and passes the remaining time to the optimizer. These are not a
continuous hard process or memory guard. The separately artifact-bound frozen
model compiler, pilot runner and their captured results are outside this
source-only feature. No reviewed-package seal claim is made by this feature's
generic helpers.

## Synthetic fixtures and tests

The two files in `tests/fixtures/invocation_trace_*.json` are hand-authored toy
graphs using alphabetic vertex names and small rational quantities. The first
covers complete invocation grammar; the A06 regression exercises a synthetic
piecewise charging/envelope case in the trace layer. That trace regression
does not expand the one-segment restricted-suffix proof model.

The generic helpers under `experiments/time_cut_v2/family_faithfulness`,
`invocation_trace`, and `restricted_suffix` accept explicit input/output paths.
The restricted-suffix helpers included here are only `make_unit_evidence.py`
and `replay_unit_evidence.py`. Synthetic unit evidence generation reuses
`tests/test_restricted_suffix_v1.py`;
independent replay requires only the repository validation packages. They do
not download inputs or launch the omitted frozen pilot automatically.

Run from the repository root in the Python 3.11 project environment:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. python -m pytest -q \
  tests/test_family* tests/test_invocation_trace_v1.py \
  tests/test_restricted_suffix_v1.py tests/test_trace_coalescing_integration.py \
  validation/family5/test_checker_units.py \
  validation/trace5/test_checker_units.py \
  validation/suffix5/test_certificate_checker.py \
  validation/suffix5/test_witness_checker.py
```

The `timecut5` hooks are included in the production wheel. `validation.*` and
the experiment helpers remain repository tooling and are not packaged in that
wheel. Installed-wheel integration tests therefore provide those tools and
synthetic fixtures separately while importing `timecut5` from site-packages.
