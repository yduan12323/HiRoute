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

## One admitted real attempt: input complete, optimization UNKNOWN

Clean producer `721d3c401aafd937606e7c91046233b30f163388` generated all4225
entries and the complete manifest. Its SHA256 is
`aef97213706c4045760a5c53f1cd4a3d41e25b6961fef4b2f7ce15b7a961c7dd`.
Numeric542632bytes, index1335626bytes and compressed paths63036250bytes,
plus manifest, total64915300bytes. This is the first complete immutable table
for this frozen query; it is not an independently certified road shortest-path
table. Old incomplete artifacts remain outside Git and are not promoted.

| Phase | Terminal outcome | Conservative CPU seconds | Elapsed seconds | Peak whole-tree RSS bytes |
|---|---|---:|---:|---:|
| Actual native build and immutable-input preflight | COMPLETE | 4.043662 | 3.743099 | 283656192 |
| Complete split generation | COMPLETE4225/4225 | 100.601701 | 97.872470 | 1528676352 |
| All frames/input and upper validation | COMPLETE | 11.995349 | 10.696614 | 66846720 |
| One independent optimization entry | UNKNOWN120wall | 122.802852001 | 120.089707 | 1370816512 |

All4225 frames passed structural/identity/coverage/time checks. Twenty-seven
fixed/sample/upper route pairs passed raw edge replay. The independently
replayed concrete upper key is
`(4495362171241/96250000,355450183/3125000,3,Pi)`, with Pi
`[(node/13098561677,CS),(node/13353329772,C),(node/12996141012,C)]`.
This yields complete relevant H20 under the already proved table-time bound;
H20 was derived after full input validation, never imposed as an artificial cap.

The optimizer was stopped by the external120wall guard. Its child consumed
117.368303CPU;122.802852001 includes controller/tail accounting. Wall sampling
closed at120.089707s; no longer query allowance was given. Peak RSS stayed
below1989853184byte dynamic cap, host available RAM>=3461251072bytes; no
memory/disk guard caused this stop. There is no optimization terminal receipt,
returned optimal plan, certified objective or infeasibility result.

The first `supported-disjunction` audit is only `started`, with a276348194byte
SMT artifact. It has no completed solver result. Existing counters cannot
partition input/model construction, serialization and solver time; file size
is not evidence that serialization alone caused the timeout. No extra profiling,
solver retry, input change or alternative query followed. All recorded worker
and controller identities are terminal and the controller stopped downstream.

The900CPU stage closes at261.118003002:10fixed setup/report reservation,
10.466626001development including the original initialization failure,
4.043662preflight,100.601701generation,11.995349validation,
122.802852001optimization and1.207813close. Global research is
18229.782734743/28800, remaining10570.217265257. Map preparation remains
652.040677976/900. Prior fees are not refunded. Ordinary software CI reserves
9000capacityCPU full and180 per physical/input component for PR/main;
full-job actual CPU is unmeasured. See [small results](split_selected_leg_results.json).

The narrow transport obstruction is resolved for this instance, and the full
independent model has an attempted real entry. Real independent optimality and
performance remain unestablished. Historical Strong/Scale UNKNOWN rows supply
only status/key references, not contemporary timing controls. The production
95%/60s and median10s goals, larger/full domains, four-positive-charge coverage,
external comparative evidence and independent holdout gaps remain.

The next decision should use this completed input and query artifact, not
repeat table generation. A bounded structural review of grounded lookup sharing
may determine whether the independent formulation can avoid large repeated
array-store expressions without freeing any input index. It requires proof and
a separate prospective admission before another real query. No runtime benefit
is predicted from artifact size, and this stage does not authorize that work.
