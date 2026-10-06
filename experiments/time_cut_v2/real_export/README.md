# Accepted native-router real-leg export (preparation only)

`export.py` leaves `src/microplan/routing.py` and `routing.cpp` unchanged. It never
constructs Igraph, a KD-tree, Python edge-weight lists, or a synthetic graph of
leg-table constants. No REF, FLAT, HIER, or Stage C optimization is invoked.

## Gates and memory

The command rehashes all six restored original files, selection artifacts,
selection policy, and hierarchy references before any real graph load. It
requires a caller-pinned selection manifest hash, and checks hashes again after
export. Only `node_id` is projected from nodes and five edge columns are read in
64K-row PyArrow batches. Original contiguous node/edge order, integer types,
endpoint ranges, null absence, and finite nonnegative weights are validated.
Exactly four contiguous native input arrays are retained. Their lightweight
owner implements the unchanged router's ownership interface.

The conservative preflight accounts for input arrays, persistent native index,
constructor offset copies, one full calibration output, and a 2 GiB
queue/Arrow/Python margin. It compares this with actual available memory,
including conventional cgroup v1/v2 limits if exposed. It stops on inadequate
availability. `/proc/self/status` and `getrusage` record current and high-water
RSS. The estimate is a conservative practical budget, not a worst-case proof
for arbitrary adversarial queue growth or unrelated concurrent allocations.

## Numerical and identity contract

All nonidentity exported labels are forward from source. Pair queries use the
largest finite binary64 cutoff, so no finite time label is truncated. Before
export, a deterministic subset of three frozen source IDs is compared against
`full(reverse=False)` bit for bit for both time and actual selected-route
length. This validates the reported subset, not every pair independently.
Every requested source is then routed once; only requested pairs are kept.

Each finite label retains its canonical float hex and exact integer ratio.
Unreachable labels are explicit and cannot receive finite placeholders.
Identity labels come directly from the native router and must be zero.
Distinct Site IDs remain separate when they share one `road:<node_id>` anchor.
Each of sixteen pools receives a complete immutable ordered-pair table, parsed
back with the existing strict immutable-table loader. Frozen per-pool eligible
actions are used, and the two SOC states reuse the same pool table.

Every original hierarchy Region ID, parent, children, and empty selected Region
is retained in each emitted restriction. These restrictions bind the original
tree hash and exact selection certificate; no reclustering occurs.

Baseline/window export first rationalizes the accepted binary64 baseline,
then computes `a=(2/5)T`, `b=(7/10)T` with rational arithmetic. The physical
model explicitly freezes consumption `1/6250`, capacity `60`, reserve `6`,
overhead `300`, penalty `600`, and the canonical PWA curve. It makes no claim of
bitwise equivalence to an older floating-point evaluator.

## Invocation

From the repository root, with Python 3.11, NumPy, PyArrow, PyYAML and g++:

```sh
PYTHONPATH=src python experiments/time_cut_v2/real_export/export.py \
  --verification /path/to/restored/verification.json \
  --selection /path/to/stage_c/concrete_selection \
  --selection-sha256 <frozen-manifest-sha256> \
  --output /path/outside/repository/real_leg_export \
  --mode preflight
```

Modes are `preflight`, `calibrate`, and `export`. Export repeats its own preflight
and real subset calibration before retaining selected pairs. Logs expose each
phase and source completion. Outputs include source/hash checks, resource
reports, native/compiler/config provenance, calibration, source-row checkpoint,
16 immutable tables, 16 exact tree restrictions, resolved states and final
manifest. An exception produces `failure.json`; an incomplete checkpoint is
never a completed export. Full road-path edge witnesses are not serialized.

Tests: `PYTHONPATH=src python -m pytest -q tests/test_real_export_streaming.py`.

`verify_export.py --output ... --selection ...` performs a separate read-only
compact audit. It checks every table hash and numerical record, reconstructs
each Region's selected membership directly from the original serialized tree,
checks co-attached Site identities and eligible effects, verifies shared pair
consistency, and recomputes exact baseline windows. It does not load road arrays.
