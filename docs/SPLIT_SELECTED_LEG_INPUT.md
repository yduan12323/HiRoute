# Split selected-leg input, same independent optimization problem

The frozen DEV query remains WD01/E18/schedule/N64:64 literal Sites,78 actions,
65 sources by65 targets,4225 explicit directed entries including64 zero aliases.
The old build-prerequisite failure and256MiB inline-output UNKNOWN remain.
This writer does not recover, promote or consume either incomplete table.

`numeric.json` holds exact rational time/actual length and literal identities.
`paths.bin` holds one lossless zlib JSON frame per pair; `paths.index.json`
binds ordinal/endpoints, contiguous offsets, lengths, counts and encoded/decoded
SHA256. `manifest.json` is committed last, after all data files are fsynced and
made read-only. All ownership digests are derived from actual bytes; no public
digest override is accepted. No complete manifest means no admissible input.

The independent reader validates every frame and the original full input
contract, including path simplicity, endpoints, zero/unreachable forms, global
edge identity consistency and directed time/reachability consistency. It first
checks Cartesian cardinality against the explicit bounded index, then exact
set coverage. It never routes through the selected-leg table or imposes a
length triangle. The shared validator accepts a record stream; the existing
inline parser retains its input and byte-identity behavior.

An on-disk BINARY-keyed consistency map with4MiB SQLite cache avoids retaining
all path strings. Only numeric pairs are resident. Lazy paths use the owned
unbuffered file descriptor, stat identity and per-frame hashes; an opaque table
owner prevents mixing lookup traces. Numeric/index hashes bind the actual
bytes parsed. Strict bounds reject corrupt, missing, truncated, duplicate,
extra, mismatched or changed frames rather than making them unreachable.

Limits: numeric/index4MiB each, manifest1MiB, encoded paths256MiB, decoded
frame16MiB, total decoded1GiB, individual UTF-8 identity64KiB. Limits stop the
whole stage UNKNOWN, never shorten a path/domain. New output total2GiB,
process-tree RSS<=3GiB dynamically tightened to available RAM minus2GiB host
reserve and64MiB controller margin; start only with>=1GiB effective RSS and
4GiB free disk, stop below2GiB free. Single numerical worker/thread.

Fixed raw-path samples and every upper/returned plan leg are replayed against
the existing independently raw-identity-validated graph DB. Complete literal
node/string-edge tuple order and selected actual length are retained. Raw path
validity/sums are checked; canonical shortest-road selection remains the common
exact provider assumption, not an independent all-source road certificate.

The physical model and independent optimizer are unchanged: replay actual U,
derive complete relevant H, preserve repeated visits, strict support,
primary/joint-face attainment and full K. Never impose the prior conditional
H20 estimate. The120s optimizer end-to-end deadline includes input loading,
formulation, solving and returned-plan replay. Historical Strong/Scale are
key/status references only, not timing controls or optimum oracles.

The prospective900CPU stage carries17968.664731741/28800 and allocates
120development,60preflight,300generation,180validation+upper,
180optimizer/controller reservation and60close, including all failures/tails.
The prior sandbox controller initialization failed before any test result;
its1.058923CPU and denied action remain. The explicitly authorized guarded
retry passed41 tests; remaining normal physical15 and optimized56 passed,
giving56 methods per mode without repeating unchanged normal cases. Seven
new test methods cover eight semantic classes, ties, corruption, quotas,
incomplete output and ownership. No real-scale result is asserted here yet.

Ordinary CI is separately reserved as approved. No earlier precharge is
refunded. This is a common-input representation change, not a production
algorithm, hierarchy win, holdout or taskbook-completion claim.
