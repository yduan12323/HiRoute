# Window .051: three first-feasibility observations

This diagnostic is prepared for a separately approved run. It performs one native
feasibility call for each retained ordinal 411229, 411238 and 412024. It does not
retry a model, run Phase I, solve the later certificate stages, accept a regime,
complete the query, or grant G8. These flags remain false even if exact recovery
returns a certificate. No real LP was run while preparing the code/tests.

The extracted JSON is exactly 15,593 bytes, SHA-256
`82569746f926588db80ffb8f2170336c367772149283d8792ec7053df790e3e7`,
from the 7,074,715-byte retained archive
`35c23a251ac67f3a502bdad044e1ca2d1e5703d2f09879996f14a317430a7c23`.
The parser hashes the bytes it consumes, rejects duplicate keys/identities and
verifies all model and descriptor hashes with the repository's `plan.digest`.
The original models have 8 variables/28 rows; unchanged `solver.strict_task`
adds the strict slack, giving 9 variables/30 rows for the feasibility task.

The unchanged `vendor_lp`, `solver`, `basis_exchange` and `candidate_memory`
source files are pinned before and after execution, including loaded paths.
Native method, bounds and tolerances stay unchanged; only the remaining resource
time limit is added, as in `SolveBudget`. CPU affinity plus the four one-thread
environment variables limit parallelism. Limits are 1 GiB address space, 768 MiB
own-exec Linux VmHWM, 30 seconds/model, 105 seconds total including initialization
and output, and a separately required external 110-second timeout. A report is
created exclusively and is at most 4 MiB. VmHWM read failures fail closed.

For each model the report includes the pinned task, native status, primal point,
objective, residuals and marginals, the exact exchange-entry seed and greedy
selected rows, the independent exchange basis and ordered entering rows, and the
actual number of exchange trials. Errors distinguish exhausted neighborhood,
512-trial cap and interruption/failure. Basis/rest/seed plus the source-pinned
nested position/entering order reproduce each primal trial; dual eliminations
are identified separately. Each elimination/check contributes to a complete
count and canonical event-stream SHA-256. Only the first 16 and last 16 events
are retained; `retained`, `omitted` and `truncated` explicitly state sampling.
Each retained elimination has a matrix/RHS/seed hash, rank/result or error. Exact
row/RHS matching records original task row identities (`a:index` or `e:index`,
including duplicates), distinguishes primal systems from stationarity, and adds
primal violated-row residuals and failure classifications where applicable. Filling the sample buffer never
interrupts recovery. Full coefficient matrices are not copied into each event.

An unresolved diagnostic result remains useful evidence; diagnostic completion
only means the observation run finished under its guards. It never implies that
these three models or the rest of the population have been accepted.

## Verification without native optimization

Run `python -m unittest discover -s tests -p test_window_face_diagnostic.py -v`.
All fixtures are synthetic and every native result is fake. The suite covers
fixed identities, input binding/rejection, native options, a second-pass/Phase-I
block, more than 512 observations without truncating backend execution, exact
exchange entry/trial/stop metadata, interruptions and timer/hook restoration,
own-exec memory failures, source changes and exclusive bounded output.

## Reproduce the canonical input without optimization

The input is `plan.canonical(selected_rows) + b'\n'`, sorted by ordinal. The
original extracted file is preserved separately; its pretty-printing is not the
consumer format. The following preparation reads the already retained archive,
checks the compressed bytes against its fixed SHA-256, verifies each extracted
model and descriptor, and writes only a new canonical input file. It does not
import or invoke the optimizer. Set `C01_WINDOW051_ARCHIVE` to the verified local
archive and `C01_DIAGNOSTIC_MODELS` to a new local path. It refuses an existing
output, a symlinked archive, an unexpected hash, oversized input/decode, missing
or duplicated targets, and any canonical-byte mismatch.

```sh
: "${C01_WINDOW051_ARCHIVE:?verified server-local retained archive required}"
: "${C01_DIAGNOSTIC_MODELS:?new server-local canonical input path required}"
python - "$C01_WINDOW051_ARCHIVE" "$C01_DIAGNOSTIC_MODELS" <<'PY_EXTRACT'
import gzip, hashlib, io, json, os, stat, sys
from pathlib import Path
from experiments.time_cut_v2.recorded_real import window_face_diagnostic as d
archive, output = map(Path, sys.argv[1:])
ARCHIVE_BYTES = 7074715
d.require(not output.exists() and not output.is_symlink(), 'fresh input output required')
fd = os.open(archive, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
with os.fdopen(fd, 'rb') as source:
    info = os.fstat(source.fileno())
    d.require(stat.S_ISREG(info.st_mode) and info.st_size == ARCHIVE_BYTES, 'pinned regular archive required')
    raw = source.read(ARCHIVE_BYTES + 1)
d.require(len(raw) == ARCHIVE_BYTES and hashlib.sha256(raw).hexdigest() == d.ARCHIVE_SHA,
          'retained archive size/hash pin changed')
chosen, decoded = {}, 0
with gzip.GzipFile(fileobj=io.BytesIO(raw)) as source:
    while True:
        line = source.readline(8*1024**2 + 1)
        if not line:
            break
        decoded += len(line)
        d.require(len(line) <= 8*1024**2 and decoded <= 512*1024**2, 'archive decode cap')
        row = json.loads(line)
        if row.get('kind') != 'unresolved_model':
            continue
        descriptor = row['descriptor']
        ordinal = descriptor['ordinal']
        if ordinal not in d.MODEL_PINS:
            continue
        d.require(type(ordinal) is int and ordinal not in chosen, 'duplicate target ordinal')
        model = row['candidate']['job']['model']
        d.require(d.digest(model) == d.MODEL_PINS[ordinal], 'extracted model pin changed')
        d.require(d.digest(descriptor) == d.DESCRIPTOR_PINS[ordinal], 'descriptor pin changed')
        chosen[ordinal] = dict(ordinal=ordinal, canonical_model_sha256=d.MODEL_PINS[ordinal],
                               descriptor=descriptor, model=model)
d.require(set(chosen) == set(d.MODEL_PINS), 'all three target models required')
encoded = d.canonical([chosen[o] for o in sorted(chosen)]) + b'\n'
d.require(len(encoded) == d.INPUT_BYTES and hashlib.sha256(encoded).hexdigest() == d.INPUT_SHA,
          'canonical extracted-input byte pin changed')
with output.open('xb') as stream:
    stream.write(encoded)
d.selected_models(output)
print(json.dumps(dict(size_bytes=len(encoded), sha256=d.INPUT_SHA, models=sorted(chosen))))
PY_EXTRACT
```

## Prepared server command (requires separate approval)

The input transfer and server paths belong to the parent task. Before running,
set `C01_DIAGNOSTIC_MODELS` to the verified server-local JSON copy,
`C01_DIAGNOSTIC_OUTPUT` to a fresh server-local output path, and
`C01_DIAGNOSTIC_CPU` to an allowed CPU. Execute from the independently reviewed
checkout at the final diagnostic commit. This command does not authorize itself.

```sh
: "${C01_DIAGNOSTIC_MODELS:?verified server-local extracted JSON required}"
: "${C01_DIAGNOSTIC_OUTPUT:?fresh server-local output path required}"
: "${C01_DIAGNOSTIC_CPU:?allowed CPU required}"
timeout --signal=TERM --kill-after=2s 110s env \
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  PYTHONDONTWRITEBYTECODE=1 \
  python -m experiments.time_cut_v2.recorded_real.window_face_diagnostic \
  --models "$C01_DIAGNOSTIC_MODELS" \
  --output "$C01_DIAGNOSTIC_OUTPUT" \
  --cpu "$C01_DIAGNOSTIC_CPU"
```
