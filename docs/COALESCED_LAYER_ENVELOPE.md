# Opt-in coalesced completed-layer envelope

`run_layer_envelope(..., coalescing=False)` keeps the original solver result and
OFF reduction behavior. To select ON, its `problem_factory` must construct the
unrecorded adapter returned by `table_free_problem(..., coalescing=True)`.
The envelope checks the exact supported adapter and representation version and
passes its `reduce` method to either FLAT or HIER. Arbitrary reduction callbacks,
recorded lineage, and implicitly enabled coalescing adapters are not supported.
The independent `verifier_factory` still supplies a fresh full-routing problem.
Existing bound-provider and source/domain admission requirements remain intact.

Envelope schema v2 binds `coalescing` and `representation_version` alongside the
existing method, dominance, H_ref, hierarchy, bound policy and source manifests.
OFF records `false` and a null version; ON records `true` and
`exact-adjacent-cut-coalescing-v1`. Header mismatch fails closed, including
representation mode/version and bound-policy changes. Old v1 envelopes are not
accepted or silently upgraded. Both OFF and ON now write v2, so the default
envelope record format deliberately changes and is not byte-compatible with
v1. Existing default solver canonical outputs and search semantics are unchanged.

Recovery reconstructs from the original seed and compares every saved completed
layer. All reconstruction work, native route queries, independent witness replay
and reducer work must be included in recovery cost. This is not warm resume:
no callable lift is deserialized, no partial layer is restored, and no saved
lower bound is used to prune. A boundary file remains incomplete evidence even
when its feasible upper and conservative primary lower bounds coincide.

`tests/m5d_recovery/test_coalesced_layer_envelope.py` reuses the original envelope
case/binding fixture and the source-bound three-node road-provider fixture.
Fresh spawned processes run uninterrupted, stop after completed depth 1, and
reconstruct using fresh providers for FLAT/HIER × OFF/ON. Checks include full
key, physical witness, conservative lower-bound agreement, retained history,
charged cold native reconstruction, adapter/reducer validation, old-schema
rejection and mode/version/bound-policy tampering. These tiny functional checks
make no large-road performance or arbitrary mid-layer recovery claim. The fixture
recovers solver full key `(12, 2, 1, ((s, CS),))` with completed-depth-1 primary
lower bound 11. Its separately verified durable feasible witness can retain key
`(12, 5, 1, ((s, CS),))`; the existing candidate hooks do not promise to persist
the solver's final secondary-optimal witness. Both artifacts are tested separately.

Run with the environment's Python, also repeating with `-OO`:

```sh
PYTHONPATH=src python -m pytest -q \
  tests/m5d_recovery/test_coalesced_layer_envelope.py \
  tests/m5d_recovery/test_layer_envelope.py \
  tests/m5d_recovery/test_table_free_coalesced_solver.py
```
