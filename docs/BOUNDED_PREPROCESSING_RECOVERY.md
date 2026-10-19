# Bounded preprocessing source recovery (real execution HELD)

This is a source-only reconstruction of the earlier held preprocessing adapter,
not a recovery of its lost live runner or historical experiment receipts. It
restores only the source dependencies needed for synthetic qualification; no
private approval identifiers, raw map bytes, historical registry, or real
results are distributed. Full graph, OD selection, and solver release remain
closed. A passing small fixture does not establish province-scale feasibility.

## Preserved semantics and repaired infrastructure

- Pyrosm 0.13.1 uses `engine="out_of_core", workers=1`. Osmium outputs explicitly
  use `pbf,pbf_dense_nodes=true`. The tiny non-dense negative fixture is retained.
- Highway candidates are filtered by exact literal exclusions derived from the
  installed Pyrosm driving filter, then unused references are pruned by another
  highway extraction. Semicolon membership remains with the original downstream
  Pyrosm filter. No wildcard or substring approximation is used. The road policy
  amendment is separately implemented in `graph.raw_way_policy`; its raw-way
  scan runs before segmentation and the normalizer remains the policy authority.
- The supervisor creates owned mode-0700 scratch and sets TMPDIR/TMP/TEMP before
  Python starts. It captures worker output unbuffered; Python is also unbuffered.
- Graph stage progress is bounded to 16 KiB, atomically replaced and fsynced,
  including its containing directory. It is an observation, never a successful
  artifact or permission to consume incomplete graph tables.
- The exposure registry validator runs in one bounded child, preserving the
  recovered schema validator and checking both caller-pinned byte and canonical
  SHA256. Parent receives only a small count/hash result, releasing the registry
  heap before graph construction. This does not verify historical completeness
  merely because the registry claims complete coverage.
- Original normalization, attachment, Site construction, and global hierarchy
  algorithms are reused. The geometry helper accepts an explicit regional CRS
  while preserving its EPSG:3035 default.

## Budget continuation contract

The original 40 CPU-hour / 48-hour ceilings cannot be expanded. A real
continuation must use `ContinuationBudget` with a reviewed cumulative debit,
transition timestamp and original absolute UTC deadline. The debit is charged
once; subsequent SELF plus waited CHILDREN accounting is measured once. Clock
advances tighten the deadline; clock rollback cannot enlarge its monotonic
allowance. `conservative_transition_debit` takes an explicit reviewed CPU
capacity, rounds uncertain active elapsed time upward and rejects negative
elapsed time. It cannot establish that an assumed process topology was true.
Never add subtotals already included in a cumulative debit. A recovered bound
is not measured historical accounting. An exhausted allowance remains exhausted.

The standalone CLI creates a fresh budget only for generated synthetic fixtures.
Real orchestration has no reconstructed release path. Source acquisition is
pinned to the dated Shandong source and SHA256 in config, and remains code-gated.
No default fixture budget may be reused to resume real preprocessing.

## Reproduction

Use Python 3.11 and the pinned scientific versions in
`experiments/shandong_preprocessing_v1/installed.txt`; the separate road policy
module also requires its pinned Python osmium dependency. The native osmium
1.18 package identities are in `environment-osmium-linux-64.lock`.

Run the recovered source tests and new bounded tests:

```
python -m unittest discover -s tests -p test_bounded_preprocessing_recovery.py
python -m unittest discover -s experiments/shandong_preprocessing_v1 -p 'test_*.py'
HIROUTE_TEST_OSMIUM=/path/to/osmium python -m unittest discover \
  -s experiments/shandong_preprocessing_v1 -p test_parser_fixture.py
```

The parser integration test uses generated tiny XML only. For conda-packaged
osmium, set LD_LIBRARY_PATH to that isolated prefix's lib directory. To run all
five generated synthetic phases, invoke `pipeline.py --fixture --output` with a
fresh owned workspace directory and explicit `--interpreter` and `--osmium`.
The shared supervisor retains per-stage limits, process-tree cleanup and logs.
Synthetic fixtures have an explicit 1 GiB sampled-tree / 3 GiB admission
threshold; real stages retain 5 GiB / 7 GiB. Both keep the 2 GiB host reserve.
These limits are recorded in each stage ledger and bound by implementation hash.

Still required before any real release: independently recovered exposure
history and source identities, reviewed conservative budget transition,
full pinned-environment integration qualification, and a reviewed enclosing
orchestrator that retains the same budget through terminal persistence. No
claim about six eligible holdouts or an empirical result follows from this code.
