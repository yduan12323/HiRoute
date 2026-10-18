# Prospective post-service objective-aware reducer diagnostic

This is an isolated prospective experiment with pre-run mathematical,
implementation and gate review approval. That approval permits preparing a
frozen plan; it is not a real-graph result or a performance claim. No real run
has occurred as part of this preparation. It does not run on import, and
`--plan` remains non-launchable. `--freeze`, `--gate` and workers still refuse
launchable manifests whenever `REVIEW_STATUS` is pending.

The planned fixed-order arms are `post_service_off` then `post_service_on`.
Both fix analytic-C ON, HIER, support ON, envelope OFF, target energy routing,
q10 dyadic ALT, onward ALT and remaining-charge bounds. They retain the exact
previously exposed `OD02_energy_only_soc3_10`, original ordered N128 pool,
original hierarchy, query and Hmax33. Selection comes from prior DEV exposure;
it is not outcome-blind sampling or holdout. The baseline source for the
preceding analytic OFF/ON experiment is commit
`46b088e5e62d49a3fbcf22cea1af9f8e72694b36`.

Only the reducer at the existing full next-departure-layer hook changes. OFF
uses the historical skyline through the new reducer's disabled fallback. ON
may use the separately proved objective-aware rule only after all scheduled
service is complete and at identical complete physical departure State. The
factory must independently admit its live problem and complete-layer contract.
Pre-service, r==1, active recording and inherited `_family` cases keep historical
skyline behavior. This rule does not broaden the meaning of the existing
product-order certificate. No old gate, engine default or certificate changes.

Inside the treatment, adjacent selected energy cells are joined only when they
come from the identical original parent, their exact interval union is connected,
and the original callback is retained. This narrow selected-parent run compaction
is explicitly separate from the historical general coalescer, which remains OFF.

Generation, seed admission, final storage, fresh full replay and every durable
incumbent callback retain disabled analytic/support/envelope contexts and never
install the new reducer. Both arms share one fresh independently checked seed;
Hmax drift blocks the pair, without replacement seeds or domains.

## Lifecycle and accounting

The existing supervisor owns one preparation, two exact searches and two fresh
replay slots, retaining all five denominator slots even on failure. Each exact
phase is 240 seconds through worker exit, including finalization. Existing
stage/CPU, observer, routing-cache and 8GiB address-space caps stay fixed. One
heavy worker runs at a time. No automatic rerun, next domain or historical
pooling is permitted.

The distinct outer schema, arms, fixed analytic policy and reducer policy are
bound through domain/source hashes, manifest, phase identity, admission record,
progress snapshots, durable incumbent and final verification. The executable
closure includes the new module, this gate and its unchanged gate dependencies.

Analytic and support counters retain their existing meanings. New reducer
statistics are separate and count repeated cell/candidate visits rather than
unique prefixes. Live snapshots are detached scalars and nontransactional.
TIMEOUT snapshots remain censored even if they say `returned`; they prove no
final conservation or exact completion. A timeout supports only its freshly
replayed feasible incumbent.

Authenticated completion additionally requires exact terminal payload/full key,
unchanged Hmax, final observer health and matching final statistics. If both
complete, canonical exact status/objective/full-key answers must agree; charge
witness bytes may differ and each witness is independently replayed. Both
successes and failures remain in the ledger. No positive performance result is
required, and one fixed-order shared-host pair cannot establish a general
speedup.

## Preparation checks

Focused tests use synthetic/mocked lifecycle checks and tiny hand-built native
graphs, pinned to CPU3. They never load real OSM/holdout inputs, install packages
or launch the planned real experiment. Normal and `-OO` Python runs must pass. Pinning is
shared-host concurrency control, not memory or I/O isolation.

After final revised-byte review, installed validation and explicit authorization
for the local immutable execution source, the interface is:

```
python -m experiments.post_service_gate_v1.run --plan
python -m experiments.post_service_gate_v1.run --freeze --input-directory INPUTS --output MANIFEST.json
python -m experiments.post_service_gate_v1.run --gate --manifest MANIFEST.json --manifest-sha256 SHA --output NEW_OUTPUT --cpu CPU
```

These commands document the interface; pre-run review does not itself launch
the experiment. Local authorized execution does not imply source publication.
