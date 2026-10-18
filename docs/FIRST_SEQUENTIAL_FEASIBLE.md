# First sequentially feasible fixed-stream construction (opt-in)

`timecut5.sparse_seed.first_sequential_feasible(query, catalog, observer=None)`
consumes the existing `iter_constructive_seed_candidates` lazily. Each proposal
is independently replayed with `sequential_no_overlap=True`: a CS stop pays
parking overhead once, finishes strictly positive charging, then starts service
within its start-time window. The first passing proposal is returned immediately.
No later candidate is requested; the existing eager APIs are unchanged.

This is **sequential feasibility on a fixed candidate stream**, not sequential
optimization. The generator still uses its original concurrent CS clock, order,
beam width and pruning. A result has `status="first_feasible"` and
`generation_complete=false`, even if this happened to be the last proposal.
Neither the finite-stream minimum nor a sequential/global optimum is claimed.
Exhaustion returns `status="unknown"`, not infeasibility. Invalid inputs,
generation/source failures and callback failures propagate as exceptions; they
must likewise never be recorded as infeasibility or successful completion.

## Persistence and independent recovery

Pass the full bound Site catalog (all 149 sites in the real transport gate), not
a joint-route-derived shortlist. No joint result is read by this entry point.
The optional callback receives `observer("first_feasible", **snapshot)` before
return or further generation. Its isolated snapshot contains the full sequence,
exact Fraction charges, full four-part lexicographic key, selected-edge witnesses,
proposal ordinal/count and source-run count. Provenance includes the complete
query, query hash, graph/router/anchor/tie-policy hashes, Site/candidate/hierarchy
hashes and catalog size. Persist rationals as exact strings, never floats.

Persistence is caller-owned. Bind the saved provenance to the same source files
and rebuild an independent fresh provider/catalog. Recover the sequence and
rational charges, call `replay_sparse_seed(saved_query, fresh_catalog, sequence,
charges, sequential_no_overlap=True)`, and compare the complete key and edge
witnesses. The construction itself reports `fresh_provider_verified=false`;
only the caller's independent recovery can establish that check.

## Optional physical trace

`replay_sparse_seed(..., include_events=True)` adds exact `distance_m`,
`elapsed_s`, `arrival_time_s`, `terminal_energy_kwh`, total `overlap_s`, and
`events`. Default output is unchanged. Each event contains absolute
`arrival`, `release`, `charge_start`, `charge_done`, `service_start`,
`service_done`, `departure`, arrival/departure energy, `window_margin_s`
(latest allowed service start minus actual start), and `overlap_s` (intersection
of charging and service time intervals). Missing actions have `None` times.
Elapsed time excludes stop penalties; the lexicographic objective includes them.
Trace quantities come directly from independent physical replay, not a second
runner-side timing model. They do not establish traffic benefits by themselves.

## Bounded regression checks

`tests/m5d_recovery/test_first_sequential_feasible.py` uses only tiny source-loaded
synthetic graphs, including a full 149-Site binding on four road nodes. It checks
an eager-generation trap, concurrent-feasible/sequential-window-failing rejection,
strict positive charge, unknown/error outcomes, exact key/charge preservation,
one parking overhead, callback isolation and independent-provider JSON recovery.
Run both normal Python and `python -OO`; no real OD runs or large graph experiments
are part of these checks.
